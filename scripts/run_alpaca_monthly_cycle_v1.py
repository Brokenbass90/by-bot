#!/usr/bin/env python3
"""Pinned Monthly source/book/manager ORDERS_OFF worker. No apply/order option."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_monthly_cycle_v1 import MonthlyManager
from research_lab import alpaca_monthly_source_ops_v1 as ops
from scripts.run_alpaca_monthly_source_ops_v1 import load_calendar


def verify(path,pin):
    p=ops.safe_path(path);raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('CYCLE_SPEC_PIN')
    spec=json.loads(raw)
    if (spec.get('schema')!='ALPACA_MONTHLY_CYCLE_DISABLED_V1' or spec.get('enabled') is not False
        or spec.get('orders_allowed') is not False or spec.get('money_authority') is not False):
        raise ValueError('CYCLE_ORDERS_OFF_SPEC_REQUIRED')
    required={'research_lab/alpaca_monthly_cycle_v1.py','research_lab/alpaca_monthly_source_ops_v1.py',
        'research_lab/alpaca_monthly_binding_v1.py','research_lab/alpaca_monthly_native_binding_v1.py',
        'scripts/run_alpaca_monthly_cycle_v1.py'}
    if not required.issubset(spec['files']):raise ValueError('CYCLE_SOURCE_CLOSURE_REQUIRED')
    for name,pin_ in spec['files'].items():
        p=ops.safe_path(ROOT/name)
        if not p.is_relative_to(ROOT) or ops.sha(p)!=pin_:raise ValueError('CYCLE_SOURCE_PIN:'+name)
    return spec


def latest_bundle(root,now):
    root=ops.safe_path(root)
    folders=[p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and p.name.isdigit()]
    if not folders:raise ValueError('CYCLE_NO_COMPLETED_CAPTURE')
    cache=max(folders,key=lambda p:int(p.name))
    cap=json.loads(ops.safe_path(cache/'capture.json').read_bytes())
    calendar=load_calendar(json.loads(ops.safe_path(cache/'calendar.json').read_bytes()),now)
    return ops.compile_source(cache,cap,calendar,now_ms=now)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec',required=True);p.add_argument('--spec-sha256',required=True)
    p.add_argument('--source',action='store_true');p.add_argument('--verify-only',action='store_true')
    a=p.parse_args(argv);spec=None
    try:
        spec=verify(a.spec,a.spec_sha256);now=time.time_ns()//1000000
        if a.verify_only:out=dict(status='MONTHLY_CYCLE_PACKAGE_VERIFIED_ORDERS_OFF',source_files=len(spec['files']))
        else:
            m=MonthlyManager(**spec['manager'])
            out=m.source(latest_bundle(spec['source_captures'],now),now_ms=now) if a.source else m.preview(now_ms=now)
        out={**out,'broker_writes':0,'orders_allowed':False,'money_authority':False}
        if not a.verify_only and spec.get('notifications'):
            from research_lab.alpaca_monthly_notifications_v1 import event_delivery
            out['notification']=event_delivery(spec['notifications'],now_ms=now,component='source' if a.source else 'manager')
    except (ValueError,KeyError,TypeError,OSError) as exc:
        out=dict(status='MONTHLY_CYCLE_BLOCKED',reason=str(exc),broker_writes=0,
            orders_allowed=False,money_authority=False)
        if spec and spec.get('notifications'):
            from research_lab.alpaca_monthly_notifications_v1 import event_delivery
            try:out['notification']=event_delivery(spec['notifications'],now_ms=time.time_ns()//1000000,
                failure_code='MONTHLY_CYCLE_'+type(exc).__name__.upper(),component='source' if a.source else 'manager')
            except Exception as notify_error:out['notification']=dict(status='DELIVERY_UNKNOWN_NO_RETRY',error_type=type(notify_error).__name__)
    print(json.dumps(out,sort_keys=True,allow_nan=False))
    return 2 if out['status']=='MONTHLY_CYCLE_BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
