#!/usr/bin/env python3
"""Bounded Oct12 PAPER ownership/recovery guard; this client cannot buy.

One reserved NET attempt only. Initial dispatch is owned by OPEN_DISPATCH_V2.
This guard never creates a reservation, changes a ranking, or loads LIVE keys.
Existing maintenance supplies native protection and quantity-proven unwind.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.alpaca_dynamic_paper import execute_paper, result, PAPER
from research_lab.alpaca_dynamic_paper_maintenance import maintain_paper, recover_initial_paper, rearm_cid, unwind_cid
from scripts.run_alpaca_dynamic_paper import PaperClient, require_source_plan, shared_lock_path

OPEN_MS = 1791811800000
UNWIND_MS = 1791898500000  # Oct13 13:35 UTC, after actual next DAY rearm window.
END_MS = 1791900000000     # Oct13 14:00 UTC; never extend silently.


class MaintenanceClient(PaperClient):
    def _request(self, method, path, payload=None):
        if method == 'POST' and path == '/v2/orders' and (payload or {}).get('side') == 'buy':
            raise ValueError('GUARD_CANNOT_SUBMIT_ENTRY')
        return super()._request(method, path, payload)


def read_state(runtime, name):
    path = Path(runtime)/name
    if not path.exists():return None
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('GUARD_STATE_IDENTITY')
    obj=json.loads(path.read_text())
    if obj['sha256'] != digest(obj['value']):raise ValueError('GUARD_STATE_HASH')
    return obj['value']


def guard_once(packet, opening_runtime, policy, client, now_ms):
    reserved=read_state(opening_runtime, 'reserve.json')
    invoking=read_state(opening_runtime, 'invoking_adapter.json')
    pending='PAPER_WAITING_FOR_DISPATCH' if now_ms<OPEN_MS+300000 else 'PAPER_NO_ENTRY'
    if reserved is None:return result(pending, reason='NO_RESERVATION')
    if invoking is None:return result(pending, reason='NO_ADAPTER_INVOKED')
    plan=reserved['value']
    if (plan['symbol']!='NET' or plan['session']!='2026-10-12'
        or invoking['parent_receipt_id']!=plan['receipt_id']
        or invoking['plan_sha256']!=digest(plan)):
        raise ValueError('GUARD_EXACT_SESSION_PLAN_CONFLICT')
    require_source_plan(Path(packet['source_book']), plan)
    identity=digest({'parent':plan['receipt_id'],'paper_account':packet['paper_account']})
    path=Path(packet['paper_runtime'])/'paper.sqlite'
    if not path.is_file() or path.is_symlink():
        return result('BLOCKED_EXECUTION',reason='NO_PERSISTED_PAPER_INTENT_NO_ENTRY')
    with sqlite3.connect(path.absolute().as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT payload FROM intents WHERE id=?',(identity,)).fetchone()
    if not row:return result('BLOCKED_EXECUTION',reason='NO_PERSISTED_PAPER_INTENT_NO_ENTRY')
    item=json.loads(row[0])
    if item['plan']!=plan or item['account']!=packet['paper_account']:
        raise ValueError('GUARD_PAPER_INTENT_CONFLICT')
    client.owned_client_ids=frozenset(['dyp-'+identity[:32],'dys-'+identity[:32],
        unwind_cid(plan['receipt_id'],packet['paper_account']),
        *[rearm_cid(plan['receipt_id'],packet['paper_account'],s['session']) for s in policy['calendar_sessions']]])
    if item.get('receipt',{}).get('status')!='PAPER_PROTECTED':
        # A persisted dispatch may recover by GET, cancellation or protection.
        # MaintenanceClient rejects every BUY even if a code regression tries one.
        if item['phase']=='STOP_DISPATCHED':
            recovery=recover_initial_paper(plan=plan,policy=policy,client=client,expected_paper_id=packet['paper_account'],
                runtime=Path(packet['paper_runtime']),now_ms=now_ms)
            if recovery['status']!='PAPER_RECOVERY_REQUIRED':return recovery
        return execute_paper(plan,policy,client,packet['paper_account'],Path(packet['paper_runtime']),now_ms,send=True)
    return maintain_paper(plan=plan,policy=policy,client=client,expected_paper_id=packet['paper_account'],
        runtime=Path(packet['paper_runtime']),now_ms=now_ms,send=True,unwind=now_ms>=UNWIND_MS)


def save(path, value):
    raw=json.dumps(value,sort_keys=True,allow_nan=False)+'\n'
    temp=path.with_suffix('.tmp')
    with temp.open('w') as f:os.chmod(temp,0o600);f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--opening-runtime',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    args=parser.parse_args()
    from dotenv import dotenv_values
    packet=json.loads(args.packet.read_text());policy=json.loads(Path(packet['policy']).read_text())
    if (packet['open_ms']!=OPEN_MS or packet['symbol']!='NET'
        or packet['attempt_authorization']!={'scope':'PAPER_ONLY','session':'2026-10-12','owner_approved':True}
        or packet['paper_account']!='4cdbfb77-d1e0-4789-86b2-341bc886efaf'
        or digest(policy)!='fe72557bd7c7437eda328047e81980ee762ec794ac240494ec47d3de4f6f400d'):
        raise ValueError('GUARD_EXACT_SCOPE_REQUIRED')
    env=dotenv_values(packet['paper_env'])
    if env['ALPACA_BASE_URL']!=PAPER:raise ValueError('GUARD_PAPER_PROFILE_ONLY')
    client=MaintenanceClient(env['ALPACA_API_KEY_ID'],env['ALPACA_API_SECRET_KEY'])
    lock=shared_lock_path(Path(packet['paper_env']),env,client.key_id)
    args.runtime.mkdir(mode=0o700,parents=True,exist_ok=True)
    # Observe from opening. The original lock serializes against the adapter;
    # absence of a reservation during its window remains pending, not terminal.
    while time.time_ns()//1000000 < OPEN_MS:time.sleep(1)
    last=None
    while time.time_ns()//1000000 < END_MS:
        now=time.time_ns()//1000000
        try:
            with lock.open('a') as handle:
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                current=guard_once(packet,args.opening_runtime,policy,client,now)
        except BlockingIOError:
            current=result('PAPER_MAINTENANCE_LOCK_BUSY',reason='ORIGINAL_SHARED_LOCK_BUSY')
        except Exception as exc:
            current=result('BLOCKED_EXECUTION',reason=str(exc) or type(exc).__name__)
        wrapped={'observed_ms':now,'deadline_ms':END_MS,'unwind_not_before_ms':UNWIND_MS,'receipt':current}
        save(args.runtime/'latest.json',wrapped)
        if current!=last:
            print(json.dumps(wrapped),flush=True);last=current
        if current['status']=='PAPER_NO_ENTRY' or current['status'].endswith('EXIT_PENDING_FINALITY'):
            save(args.runtime/'terminal.json',wrapped);return 0
        # Repeated GET recovery is permitted; no uncertain POST is resent by
        # the existing durable lifecycle. Blockers remain explicit, not PASS.
        time.sleep(1 if now<OPEN_MS+300000 else 30)
    terminal=result('BLOCKED_EXECUTION',reason='GUARD_DEADLINE_OWNER_ACTION_REQUIRED',last_receipt=last)
    save(args.runtime/'terminal.json',{'observed_ms':time.time_ns()//1000000,'receipt':terminal})
    print(json.dumps(terminal),flush=True)
    return 2


if __name__=='__main__':raise SystemExit(main())
