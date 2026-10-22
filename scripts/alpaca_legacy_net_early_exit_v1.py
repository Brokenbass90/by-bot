#!/usr/bin/env python3
"""HUMAN ONLY: separately approved October23 legacy NET exit through its existing owned runtime.

Default/inspection never contacts a broker. No timer, new manager, buy, HALT
clear, stop widening, monthly-book adoption or fabricated accounting finality.
"""
import argparse
import copy
from datetime import datetime
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from zoneinfo import ZoneInfo


def need(ok,why):
    if not ok:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def calendar_open(rows):
    need(isinstance(rows,list) and len(rows)==1 and rows[0]['date']=='2026-10-23','EARLY_CALENDAR_REQUIRED')
    t=datetime.fromisoformat(rows[0]['date']+'T'+rows[0]['open']).replace(tzinfo=ZoneInfo('America/New_York'))
    need(t.hour==9 and t.minute==30,'EARLY_OPEN_CHANGED')
    need(t.astimezone(ZoneInfo('Asia/Nicosia')).isoformat()=='2026-10-23T16:30:00+03:00','EARLY_DST_CONFLICT')
    return int(t.timestamp()*1000)
def window(plan,now):
    need(type(now) is int and plan['session']=='2026-10-23'
         and plan['open_ms']==1792764000000 and plan['session_open_ms']==1792762200000 and plan['end_ms']==plan['open_ms']+300000
         and plan['open_ms']<=now<plan['end_ms'],'NOT_IN_SEPARATE_EARLY_WINDOW')
def owned_identity(plan,item):
    need(plan['symbol']=='NET' and item['entry']['id']==plan['entry_order_id']
         and item['intake']['intake_sha256']==plan['intake_sha256']
         and item['intake']['plan']['symbol']=='NET'
         and Decimal(item['intake']['plan']['qty'])==Decimal(plan['initial_quantity']),
         'ORIGINAL_LEGACY_NET_IDENTITY_REQUIRED')


def load(path,pin):
    raw=Path(path).read_bytes();need(sha(raw)==pin,'NET_EXIT_MANIFEST_PIN')
    m=json.loads(raw);need(m['schema']=='NET_LEGACY_EARLY_PERSONAL_EXIT_V1','NET_EXIT_SCOPE')
    for p,want in m['files'].items():need(sha(Path(p).read_bytes())==want,'NET_EXIT_SOURCE_DRIFT')
    return m


def check_early_owner_go(m):
    pin=m.get('_manifest_sha256')
    need(isinstance(pin,str) and len(pin)==64 and all(c in '0123456789abcdef' for c in pin),'EARLY_SCOPE_PIN_REQUIRED')
    path=Path(m['new_owner_go_path'])
    need(path.is_absolute() and '..' not in path.parts and not any(p.is_symlink() for p in (path,*path.parents)),'EARLY_GO_PATH')
    st=path.stat()
    need(path.is_file() and st.st_nlink==1 and st.st_uid==os.geteuid() and st.st_mode&0o777==0o600,'EARLY_GO_CUSTODY')
    need(read(path)==dict(schema='NET_EARLY_EXIT_EXACT_OWNER_GO_V1',manifest_sha256=pin,
        owner_go_text='GO NET EARLY EXIT '+pin),'SEPARATE_EARLY_OWNER_GO_REQUIRED')


def owner_execute(m):
    check_early_owner_go(m) # Required before loading any credential-bearing control.
    need(m.get('authority_semantics')=='CLAIM_INITIATION_WINDOW_THEN_OWNED_RECOVERY','EARLY_AUTHORITY_SEMANTICS_REQUIRED')
    plan=m['plan'];window(plan,time.time_ns()//1000000)
    # Uses the exact repaired maintenance loader, not the abandoned weekly entry path.
    p=Path(m['control_path']);s=importlib.util.spec_from_file_location('net_legacy_owned_control',p)
    control=importlib.util.module_from_spec(s);s.loader.exec_module(control)
    spec=control.load_spec(m['spec_path'])
    from research_lab import alpaca_dynamic_live_runtime_v1 as runtime
    from scripts.run_alpaca_dynamic_live_v1 import load_client
    from research_lab.kity_oct15_deadline_v1 import publish_once
    b=read(Path(spec['session_dir'])/'binding.json');intake=read(Path(spec['session_dir'])/'intake.json')
    client=load_client(spec['live_profile'],b,apply=False)
    need(client.get_account()['id']==b['account_id'],'EXACT_LIVE_ACCOUNT_REQUIRED')
    cal=client._http(runtime.LIVE+'/v2/calendar?start=2026-10-23&end=2026-10-23','GET')
    need(calendar_open(cal)==plan['session_open_ms'],'ACTUAL_CALENDAR_CONFLICT')
    clock=client.get_clock();cts=runtime.native._parse_iso_utc(clock.get('timestamp',''))
    now=time.time_ns()//1000000;window(plan,now)
    need(clock.get('is_open') is True and cts is not None and abs(now-int(cts.timestamp()*1000))<=5000,
         'FRESH_OPEN_BROKER_CLOCK_REQUIRED')
    with sqlite3.connect((Path(b['runtime'])/'live.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        rows=[json.loads(v[0]) for v in db.execute('SELECT payload FROM intents')]
    need(len(rows)==1,'EXACT_OWNED_LIFECYCLE_REQUIRED');item=rows[0];owned_identity(plan,item)
    positions=client.list_positions();net=[p for p in positions if p['symbol']=='NET']
    outroot=Path(m['output_root']);outroot.mkdir(mode=0o700,parents=True,exist_ok=True)
    def publish(name,value):
        publish_once(outroot/name,(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())
    if not net:
        orders=client.list_orders(status='open',limit=500)
        need(len(orders)<500 and not any(o['symbol']=='NET' for o in orders),'LEGACY_NET_ORDERS_STILL_OPEN')
        publish('already-flat.json',dict(status='LEGACY_NET_ALREADY_FLAT_NO_ORDER',observed_ms=now,
            entry_order_id=plan['entry_order_id'],accounting_finality='NOT_INFERRED',broker_writes=0))
        return dict(status='LEGACY_NET_ALREADY_FLAT_NO_ORDER',broker_writes=0)
    need(len(net)==1 and Decimal(net[0]['qty'])<=Decimal(plan['initial_quantity'])
         and net[0]['side']=='long','LEGACY_NET_QUANTITY_OR_SIDE_CONFLICT')
    state=read(b['ledger_path']);record=state['NET']
    need(Decimal(str(record['accepted_stop_floor']))>=Decimal('277.69'),'LEGACY_STOP_FLOOR_LOWERED')
    runtime.owned_snapshot(client,copy.deepcopy(item),copy.deepcopy(record),
        observation_ms=lambda:time.time_ns()//1000000)
    check_early_owner_go(m)
    window(plan,time.time_ns()//1000000)
    publish('personal-exit-claim.json',dict(plan=plan,at_ms=time.time_ns()//1000000,
        raw_calendar=cal,raw_clock=clock,reason='OWNER_PLANNED_OFF_PROTOCOL_EXIT'))
    writer=load_client(spec['live_profile'],b,apply=True)
    # New owner scope explicitly authorizes initiation at the durable claim.
    # Once consumed, complete only this original owned unwind under the existing
    # native permits/recovery. Do not add a late denial after native write-ahead
    # cancellation/dispatch markers: it would falsely look like an uncertain send.
    out=runtime.run_once(intake=intake,policy=read(spec['policy']),binding=b,client=writer,
        now_ms=time.time_ns()//1000000,apply=True,owner_go_path=m['existing_owner_go'],
        maintenance=True,kill=True,first_intent_path=spec['intent'])
    publish('personal-exit-result.json',dict(result=out,strategy_evidence='OFF_PROTOCOL',
        monthly_evidence_eligible=False,monthly_entry_authorized=False))
    return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest');p.add_argument('--manifest-sha256')
    p.add_argument('--owner-execute',action='store_true',help='HUMAN ONLY: owned financial exit')
    a=p.parse_args(argv)
    if not a.manifest:
        need(not a.owner_execute,'EXACT_NET_EXIT_PACKET_REQUIRED')
        print(json.dumps(dict(status='OFFLINE_NO_AUTHORITY',broker_writes=0)));return 0
    m=load(a.manifest,a.manifest_sha256)
    if not a.owner_execute:
        print(json.dumps(dict(status='NET_EXIT_PACKET_PREPARED_NOT_ARMED',plan=m['plan'],broker_requests=0,broker_writes=0)));return 0
    m['_manifest_sha256']=a.manifest_sha256
    print(json.dumps(owner_execute(m)));return 0


if __name__=='__main__':raise SystemExit(main())
