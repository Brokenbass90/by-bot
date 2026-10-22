#!/usr/bin/env python3
"""Historical H1 -> existing intake/plan -> durable lifecycle -> memory Bybit.

No LIVE flag, credentials or real wire. This CLI checks integration, not edge,
authenticated source timing, real instrument minima, risk or account authority.
"""
import argparse
from decimal import Decimal as D
import hashlib,json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_execution_plan_v1 import build_plan,HOUR_MS
from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
from research_lab.kity_micro_physical_owner_v1 import SignedPostOnce,publish
from scripts.rehearse_pump4_bybit_v1 import MemoryBybit
from strategies.signals import TradeSignal


def run(root,input_path,input_sha256):
    root=Path(root).absolute();source=Path(input_path).read_bytes()
    if hashlib.sha256(source).hexdigest()!=input_sha256:raise ValueError('PIPELINE_FIXTURE_PIN')
    if root.exists() or '..' in root.parts or any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError('EXCLUSIVE_REHEARSAL_ROOT_REQUIRED')
    f=json.loads(source)
    if f['schema']!='PUMP4_PIPELINE_HISTORICAL_FIXTURE_V1':raise ValueError('FIXTURE_SCOPE')
    root.mkdir(mode=0o700,parents=True)
    stamp=f['signal_bar'][0];entry_ms=stamp+HOUR_MS
    intake=Pump4Intake(root/'intake.jsonl',f['symbol'])
    intake.seed(f['seed'],available_ms=stamp,observed_ms=stamp)
    signal=intake.accept(f['signal_bar'],available_ms=entry_ms,observed_ms=entry_ms)['decision']['signal']
    if signal is None:raise ValueError('FIXTURE_SIGNAL_MISSING')
    plan=build_plan(TradeSignal(**signal),signal_bar_open_ms=stamp,next_open_ms=entry_ms,next_open=f['next_open'])
    if plan!=f['expected_plan']:raise ValueError('FIXTURE_PLAN_PARITY')
    # Quantity/filters are explicit integration fixtures, not real TINY sizing.
    lifecycle=Pump4Lifecycle(root/'lifecycle',plan,qty='10',qty_step='1',min_qty='1',min_notional='.00000001',tick_size='.000000000000000001')
    exchange=MemoryBybit(root/'memory.json','normal')
    exchange.state.update(fixture_entry_price=str(plan['entry']));exchange.save()
    snapshots=[]
    def observe(price):
        s=exchange.state;orders=[];fills=[]
        for row in s['orders'].values():
            req=row['request'];orders.append({**{k:req[k] for k in ('symbol','side','qty','positionIdx','reduceOnly','orderLinkId')},
                **{k:row[k] for k in ('orderId','cumExecQty','orderStatus')}})
        for e in s['executions']:
            req=next(row['request'] for row in s['orders'].values() if row['orderId']==e['orderId'])
            fills.append(dict(e,symbol=plan['symbol'],side=req['side'],feeCurrency='USDT'))
        return dict(schema='PUMP4_BYBIT_OBSERVATION_V1',source_ms=entry_ms,observed_ms=entry_ms,
            pagination_complete=True,symbol=plan['symbol'],positionIdx=0,position_side='Sell' if plan['side']=='short' else 'Buy',
            held_qty=s['held'],price=str(price),orders=orders,executions=fills,
            native_stop=s['stop'] if D(s['held']) else None,funding=[],costs_complete=False)
    for price,role in zip([plan['entry'],*plan['targets']],['ENTRY','TP1','TP2']):
        result=Pump4Lifecycle.resume(root/'lifecycle').advance(observe(price),now_ms=entry_ms)
        if result.get('role')!=role:raise ValueError('PIPELINE_ROLE_'+result['status'])
        snapshots.append(dict(role=role,request=result['request']))
        exchange.state['fixture_exit_price']=str(price);exchange.save()
        SignedPostOnce('FIXTURE_KEY_NONFINANCIAL','FIXTURE_SECRET_NONFINANCIAL',root/'send-barriers',wire=exchange.wire).post('/v5/order/create',result['request'])
        exchange=MemoryBybit(exchange.path,'normal') # drop all in-memory exchange state
    final=observe(plan['targets'][1]);final['costs_complete']=True
    final['funding']=[dict(id='fixture-funding',amount='-.01',currency='USDT')]
    result=Pump4Lifecycle.resume(root/'lifecycle').advance(final,now_ms=entry_ms)
    if result['status']!='FLAT_COSTS_RECONCILED_ORDERS_OFF' or D(exchange.state['held'])!=0:raise ValueError('PIPELINE_NOT_FLAT')
    if Path(input_path).read_bytes()!=source:raise ValueError('FIXTURE_CHANGED')
    receipt=dict(schema='PUMP4_H1_THROUGH_BYBIT_ORDERS_OFF_CLI_V1',status='HISTORICAL_PIPELINE_ORDERS_OFF_PASS',
        symbol=plan['symbol'],input_sha256=input_sha256,source_provenance=f['source_provenance'],actions=snapshots,
        fill_count=len(final['executions']),entry_qty='10',tp1_qty='4',tp2_qty='6',remaining_qty=exchange.state['held'],
        durable_module_reload_after_every_order=True,process_restart='separately_tested_in_lifecycle_regression',
        actual_account_admission='NOT_PERFORMED',instrument_filters='SYNTHETIC_FIXTURE',fees_and_funding='SYNTHETIC_FIXTURE',
        economic_outcomes_recomputed=False,prospective_decisions_credited=0,real_broker_requests=0,real_broker_writes=0,
        orders_allowed=False,money_authority=False,tiny_ready=False)
    publish(root/'receipt.json',receipt);return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path)
    p.add_argument('--input',required=True,type=Path);p.add_argument('--input-sha256',required=True);a=p.parse_args()
    print(json.dumps(run(a.root,a.input,a.input_sha256),sort_keys=True))
