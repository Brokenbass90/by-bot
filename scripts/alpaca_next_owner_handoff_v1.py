#!/usr/bin/env python3
"""HUMAN-only personal arming of one pre-reviewed Monday Dynamic entry.

Default inspection performs file reads only, no broker request or mutation.
Agents must never invoke --owner-arm or schedule that action. No order client
with writes enabled is constructed here. Actual entry remains a separately
scheduled, fresh-gated original runtime operation after personal arming.
"""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def sha(raw):return hashlib.sha256(raw).hexdigest()


def need(ok,reason):
    if not ok:raise ValueError(reason)


def _read(path):
    p=Path(path)
    need(p.is_absolute() and '..' not in p.parts and not any(x.is_symlink() for x in (p,*p.parents)),'HANDOFF_PATH')
    return p.read_bytes()


def inspect(path,pin,*,now_ms):
    raw=_read(path);need(sha(raw)==pin,'HANDOFF_MANIFEST_PIN')
    m=json.loads(raw);need(m['schema']=='ALPACA_NEXT_OWNER_HANDOFF_V1','HANDOFF_SCHEMA')
    need(now_ms<m['deadline_ms'],'PERSONAL_ARM_T_MINUS_15_EXPIRED')
    for group in ('old_pins','prepared_pins'):
        for p,h in m[group].items():need(sha(_read(p))==h,'HANDOFF_SOURCE_DRIFT:'+p)
    need(not Path(m['personal_arm']).exists() and not Path(m['claim']).exists(),'HANDOFF_ALREADY_USED_NO_RETRY')
    for row in m['new_units']:
        p=Path(row['target'])
        if row.get('old_sha256') is None:need(not p.exists(),'NEW_UNIT_COLLISION')
    return dict(status='ALPACA_NEXT_OWNER_PACKET_INSPECTION_PASS',scope_sha256=m['scope_sha256'],
                deadline_ms=m['deadline_ms'],broker_requests=0,broker_writes=0,financial_units_changed=False)


def _publish(path,value):
    from research_lab.alpaca_live_readiness_v1 import write_new
    from research_lab.alpaca_dynamic_v1 import canonical
    write_new(Path(path),canonical(value))


def _install(path,raw):
    p=Path(path)
    need(p.parent==Path('/etc/systemd/system') and not p.is_symlink(),'UNIT_INSTALL_SCOPE')
    temp=p.with_name('.'+p.name+'.next-owner.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(temp,p);fd=os.open(p.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def owner_arm(path,pin):
    need(os.geteuid()==0,'VPS_ROOT_PERSONAL_START_REQUIRED')
    now=time.time_ns()//1000000;inspect(path,pin,now_ms=now)
    m=json.loads(_read(path))
    need(Path(m['app_root'])==Path('/opt/bybot-research/alpaca-next-entry-20261019-v1/app'),'HANDOFF_APP_SCOPE')
    from scripts.alpaca_next_entry_control_v1 import load_spec,verify_selected_units
    from research_lab.alpaca_dynamic_live_runtime_v1 import read_json,account_lock,safe_path
    from research_lab.alpaca_dynamic_live_lineage_v1 import reconcile_live_lineage
    from research_lab.alpaca_next_entry_scope_v1 import check_scope,APPROVAL_SHA256
    from scripts.run_alpaca_dynamic_live_v1 import load_client
    spec=load_spec(m['control_spec'],m['control_spec_sha256']);policy=read_json(spec['policy'])
    binding=read_json(spec['binding']);scope=read_json(spec['scope']);check_scope(scope,policy)
    need(scope['scope_sha256']==m['scope_sha256'],'HANDOFF_SCOPE_PIN')
    allowed={'alpaca-oct15-owned-manager.service','alpaca-net-day-monitor.service',
             'alpaca-dynamic-next-entry-20261019.service','alpaca-dynamic-next-entry-20261019.timer'}
    need({Path(r['target']).name for r in m['new_units']}==allowed,'HANDOFF_EXACT_UNIT_SET')
    need(Path(binding['lock_path']).stat().st_ino==m['account_lock_inode'],'ORIGINAL_ACCOUNT_LOCK_INODE')
    halt=safe_path(binding['halt_path'],exists=True)
    need(sha(halt.read_bytes())==m['halt_sha256'],'ORIGINAL_HALT_CHANGED')
    control=[sys.executable,'-B',str(Path(m['app_root'])/'scripts/alpaca_next_entry_control_v1.py'),
             '--spec',m['control_spec'],'--spec-sha256',m['control_spec_sha256']]
    def run(*args):return subprocess.check_output(list(args),text=True,stderr=subprocess.STDOUT).strip()
    _publish(m['claim'],dict(status='PERSONAL_ARM_IN_PROGRESS_NO_BLIND_RETRY',observed_ms=now,scope_sha256=m['scope_sha256']))
    changed=[];cleared=False
    try:
        original=read_json(binding['portfolio_bindings'][0]['path'])
        # Data accounting only; the original broker and journal authenticate it.
        lineage=reconcile_live_lineage(original,policy,load_client(spec['live_profile'],binding,apply=False),
            now_ms=time.time_ns()//1000000,apply=True)
        with account_lock(binding):
            # Recheck all sources under custody; the claim is already durable.
            for group in ('old_pins','prepared_pins'):
                for p,h in m[group].items():need(sha(_read(p))==h,'HANDOFF_SOURCE_DRIFT:'+p)
            need(time.time_ns()//1000000<m['deadline_ms'],'PERSONAL_ARM_EXPIRED')
            need(sha(halt.read_bytes())==m['halt_sha256'],'ORIGINAL_HALT_CHANGED')
            for row in m['new_units']:
                _install(row['target'],_read(row['prepared']));changed.append(row['target'])
            run('systemctl','daemon-reload')
            verify_selected_units(spec,m['control_spec_sha256'])
            _publish(spec['personal_arm'],dict(schema='ALPACA_DYNAMIC_PERSONAL_SESSION_ARM_V1',scope_sha256=scope['scope_sha256'],
                owner_approval_text_sha256=APPROVAL_SHA256,personal_owner_start=True,session=scope['session'],attempts_allowed=1,auto_repeat=False))
            for mode in ('--prepare','--ready'):
                out=json.loads(run(*control,mode));need(out['status'] in {'STATIC_PREPARED','READY_TO_DISPATCH'},'CONTROL_PREPARATION_FAILED')
            # Exact archived historical entry HALT only. A newly created HALT
            # after this point always inhibits the scheduled entry as usual.
            archived=Path(m['archived_halt']);need(not archived.exists(),'HALT_ARCHIVE_COLLISION')
            os.rename(halt,archived);cleared=True
            for parent in (halt.parent,archived.parent):
                fd=os.open(parent,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
            run('systemctl','enable','--now','alpaca-dynamic-next-entry-20261019.timer')
            timer=run('systemctl','show','alpaca-dynamic-next-entry-20261019.timer','-p','ActiveState,NextElapseUSecRealtime')
            need('ActiveState=active' in timer,'ENTRY_TIMER_NOT_ACTIVE')
            result=dict(status='MONDAY_PERSONALLY_ARMED_PENDING_FRESH_OPENING',scope_sha256=m['scope_sha256'],
                observed_ms=time.time_ns()//1000000,source_lineage_writes=lineage['source_book_writes'],timer=timer,
                financial_unit_count=len(changed),broker_writes=0,entry_executed=False,actual_opening_pass=False)
            _publish(m['receipt'],result);return result
    except Exception as exc:
        # Future-only timer is still at least fifteen minutes away. Do not
        # restore a partially selected financial writer blindly or erase claims.
        try:run('systemctl','disable','--now','alpaca-dynamic-next-entry-20261019.timer')
        except Exception:pass
        if cleared and not halt.exists():
            try:os.rename(m['archived_halt'],halt)
            except Exception:pass
        result=dict(status='ARM_FAILED_NO_AUTOMATIC_RETRY',error_type=type(exc).__name__,
                    changed_units=changed,broker_writes=0,entry_executed=False,manual_reconciliation_required=True)
        if not Path(m['receipt']).exists():_publish(m['receipt'],result)
        raise


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',required=True);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--owner-arm',action='store_true');a=p.parse_args(argv)
    try:out=owner_arm(a.manifest,a.manifest_sha256) if a.owner_arm else inspect(a.manifest,a.manifest_sha256,now_ms=time.time_ns()//1000000)
    except Exception as exc:out=dict(status='BLOCKED_OWNER_HANDOFF',reason=str(exc),broker_writes=0)
    print(json.dumps(out,sort_keys=True));return 2 if out['status'].startswith('BLOCKED') else 0


if __name__=='__main__':raise SystemExit(main())
