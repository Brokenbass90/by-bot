#!/usr/bin/env python3
"""Saved KITY packet -> seven-day virtual-clock rehearsal. No network or orders."""
import argparse
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_lab.kity_weekly_rehearsal_v1 import WeeklyRehearsal,make_profile
from research_lab.research_tiny_intake_v1 import assess_kity
from research_lab.pump4_live_observer_v1 import read_file
from research_lab.os2_shadow_journal import strict_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ('signal','entry','c2'):
        parser.add_argument('--'+n,type=Path,required=True);parser.add_argument('--'+n+'-sha256',required=True)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--fixture-fee-rate',required=True)
    parser.add_argument('--fixture-funding-interval-minutes',type=int,required=True)
    args=parser.parse_args();source={};pins={}
    for n in ('signal','entry','c2'):
        raw=read_file(getattr(args,n));pin=hashlib.sha256(raw).hexdigest()
        if pin!=getattr(args,n+'_sha256'):raise ValueError(n+'_source_pin')
        source[n]=strict_json(raw);pins[n]=pin
    if source['c2']['compared_inputs']['signal.json']!=pins['signal']:raise ValueError('C2_SIGNAL_BINDING')
    intake=assess_kity(source['signal'],source['c2'],source['entry'],dossier_legs=len(source['entry']['pozicii']),active_owner='PUMP4')
    legs=[dict(symbol=v['s'],side=v['side'],qty=str(v['kolichestvo']),entry_reference_price=str(v['cena_vhoda'])) for v in source['entry']['pozicii']]
    profile=make_profile(source['signal']['d'],legs,pins,funding_intervals={v['symbol']:args.fixture_funding_interval_minutes for v in legs})
    fee=D(args.fixture_fee_rate)
    if not fee.is_finite() or not D(0)<=fee<D(1):raise ValueError('fixture_fee_rate')
    root=args.root.absolute()
    if root.exists():raise ValueError('REHEARSAL_ROOT_MUST_BE_NEW')
    w=WeeklyRehearsal(root,profile);stages={};t=profile['entry_reference_ms'];counter=0
    def append(kind,symbol,ms,**kw):
        nonlocal counter
        counter+=1;w.append(dict(event_id='fixture-'+str(counter),kind=kind,symbol=symbol,observed_ms=ms,**kw))
    for leg in legs:
        s=leg['symbol'];q=D(leg['qty']);price=D(leg['entry_reference_price'])
        append('MODEL_ENTRY_FILL',s,t,exec_id='e-'+s,qty=str(q),price=str(price),fee_usdt=str(q*price*fee))
        append('PROTECTION',s,t,qty=str(q),stop_price=str(price*(D('.9') if leg['side']==1 else D('1.1'))),
               contract='CONTINGENCY_FIXTURE_ONLY',status='ACCEPTED')
    stages['entry_and_fixture_protection']=w.state();w=WeeklyRehearsal(root,profile)
    interval=args.fixture_funding_interval_minutes*60000
    for stamp in range((t//interval+1)*interval,profile['exit_reference_ms']+1,interval):
        for leg in legs:
            q=D(leg['qty']);mark=D(leg['entry_reference_price']);rate=D('.0001')
            append('MODEL_FUNDING',leg['symbol'],stamp,settlement_id=str(stamp),qty=str(q),mark=str(mark),rate=str(rate),
                   cash_usdt=str(-D(leg['side'])*q*mark*rate))
    stages['seven_day_funding']=w.state();w=WeeklyRehearsal(root,profile);t=profile['exit_reference_ms']+1
    for i,leg in enumerate(legs):
        s=leg['symbol'];q=D(leg['qty']);price=D(leg['entry_reference_price'])
        append('MODEL_EXIT_FILL',s,t,exec_id='x-'+s,qty=str(q),price=str(price),fee_usdt=None if i==0 else str(q*price*fee))
        append('PROTECTION',s,t,qty='0',status='CANCELLED',contract='CONTINGENCY_FIXTURE_ONLY')
    stages['flat_cost_pending']=w.state()
    if stages['flat_cost_pending']['model_capital_released']:raise ValueError('PREMATURE_RELEASE')
    first=legs[0];append('MODEL_FEE',first['symbol'],t+1,exec_id='x-'+first['symbol'],fee_usdt=str(D(first['qty'])*D(first['entry_reference_price'])*fee))
    append('MODEL_COST_FINALITY','ALL',t+2,fees_complete=True,funding_complete=True)
    stages['model_terminal']=w.state();before=w.events.path.read_bytes();after=WeeklyRehearsal(root,profile).state()
    if before!=w.events.path.read_bytes() or after!=stages['model_terminal'] or not after['terminal_complete']:
        raise ValueError('RESTART_REPLAY_OR_TERMINAL')
    result=dict(schema='KITY_WEEKLY_SAVED_PACKET_REHEARSAL_V1',status='MODEL_LIFECYCLE_PASS',observed_ms=time.time_ns()//1000000,
                source_pins=pins,profile_sha256=w.pin,event_count=len(w.events.read()),journal_sha256=hashlib.sha256(before).hexdigest(),
                legs=len(legs),hold_days=7,virtual_clock=True,source_prices='SAVED_SHADOW_ENTRY_REFERENCES_NO_FUTURE_OUTCOMES',
                fees_funding_stops='EXPLICIT_SYNTHETIC_FIXTURES_NOT_ACTUAL_BYBIT_ACCEPTANCE',
                scenario_fee_rate=str(fee),scenario_funding_interval_minutes=args.fixture_funding_interval_minutes,
                model_stages=stages,restart_replay_equal=True,broker_requests=0,broker_writes=0,
                orders_allowed=False,money_authority=False,intake_blockers=intake['blockers'])
    print(json.dumps(result,sort_keys=True,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
