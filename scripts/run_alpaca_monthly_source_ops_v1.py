#!/usr/bin/env python3
"""Read-only source worker. Default no network, no money/apply/owner-GO mode."""
import argparse
from datetime import datetime,timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research_lab import alpaca_monthly_source_ops_v1 as ops


def verify_package(path,expected):
    path=ops.safe_path(path)
    if ops.sha(path)!=expected:raise ops.SourceBlocked('PACKAGE_SPEC_PIN')
    spec=json.loads(path.read_bytes())
    if (spec.get('schema')!='ALPACA_SOURCE_OPS_PACKAGE_V1' or spec.get('orders_allowed') is not False
        or spec.get('money_authority') is not False):raise ops.SourceBlocked('PACKAGE_AUTHORITY_CONFLICT')
    for name,pin in spec['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ops.SourceBlocked('PACKAGE_FILE_SCOPE')
        p=ops.safe_path(path.parent/'app'/name)
        if not p.is_file() or ops.sha(p)!=pin:raise ops.SourceBlocked('PACKAGE_SOURCE_DRIFT:'+name)
    return spec


def calendar_capture(profile,now_ms):
    """Reuse the existing restricted GET reader; no order endpoint/method."""
    from dotenv import dotenv_values
    from research_lab.alpaca_day_monitor_v1 import GetReader,LIVE
    env=dotenv_values(ops.safe_path(profile),interpolate=False)
    if env.get('ALPACA_BASE_URL')!=LIVE:raise ops.SourceBlocked('CALENDAR_PROFILE_BASE')
    day=datetime.fromtimestamp(now_ms/1000,ZoneInfo('America/New_York')).date()
    start=(day-timedelta(days=760)).isoformat();end=(day+timedelta(days=65)).isoformat()
    endpoint='/v2/calendar?start='+start+'&end='+end
    started=time.time_ns()//1000000
    # The NET observer intentionally accepts same-day calendar queries only.
    # Reuse its redirect/size/timeout transport without broadening that live
    # reader: this worker constructs one fixed GET calendar-range route itself.
    reader=GetReader(env['ALPACA_API_KEY_ID'],env['ALPACA_API_SECRET_KEY'])
    req=Request(LIVE+endpoint,headers=reader.headers,method='GET')
    body=json.loads(reader.open_request(req))
    return dict(schema='BROKER_CALENDAR_GET_CAPTURE_V1',method='GET',endpoint=endpoint,
      started_ms=started,completed_ms=time.time_ns()//1000000,body=body)


def load_calendar(raw,now_ms):
    if (raw['schema']!='BROKER_CALENDAR_GET_CAPTURE_V1' or raw['method']!='GET'
       or not raw['endpoint'].startswith('/v2/calendar?start=')
       or not 0<raw['started_ms']<=raw['completed_ms']<=now_ms):
        raise ops.SourceBlocked('CALENDAR_CAPTURE_CONTRACT')
    return ops.normalize_calendar(raw['body'])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path)
    p.add_argument('--package-spec',type=Path);p.add_argument('--package-spec-sha256')
    c=p.add_mutually_exclusive_group()
    c.add_argument('--calendar-source',type=Path);c.add_argument('--calendar-profile',type=Path)
    p.add_argument('--calendar-source-sha256')
    p.add_argument('--cache',type=Path,help='verify a previously captured immutable full-universe cache')
    p.add_argument('--capture',action='store_true',help='explicit public data fetch into new runtime capture directory')
    p.add_argument('--bootstrap',action='store_true',help='explicit latest-closed-session readiness check outside scheduled session')
    p.add_argument('--bind-orders-off',action='store_true',help='bind only to own source book, no monetary transport')
    a=p.parse_args(argv);now=time.time_ns()//1000000
    if not any((a.calendar_source,a.calendar_profile,a.cache,a.capture,a.bind_orders_off)):
        print(json.dumps(dict(status='SOURCE_OPS_NO_NETWORK_ORDERS_OFF',symbols=len(ops.required_symbols()),orders_allowed=False,money_authority=False)))
        return 0
    try:
        if a.package_spec:verify_package(a.package_spec,a.package_spec_sha256)
        if a.capture and a.cache:raise ops.SourceBlocked('ONE_CAPTURE_OR_CACHE')
        if (a.capture or a.bind_orders_off or a.calendar_profile) and a.runtime is None:raise ops.SourceBlocked('ISOLATED_RUNTIME_REQUIRED')
        if a.calendar_source:
            cp=ops.safe_path(a.calendar_source)
            if ops.sha(cp)!=a.calendar_source_sha256:raise ops.SourceBlocked('CALENDAR_SOURCE_PIN')
            raw=json.loads(cp.read_bytes())
        elif a.calendar_profile:raw=calendar_capture(a.calendar_profile,now)
        else:raise ops.SourceBlocked('CALENDAR_SOURCE_REQUIRED')
        now=time.time_ns()//1000000;cal=load_calendar(raw,now);plan=ops.schedule(cal,now_ms=now)
        receipt=ops.safe_path(a.runtime/'book/receipts'/(plan['signal_session']+'.json')) if a.runtime and plan['signal_session'] else None
        if receipt and receipt.exists() and a.capture:
            old=json.loads(receipt.read_bytes())
            if old.get('receipt_sha256')!=ops.digest({k:v for k,v in old.items() if k!='receipt_sha256'}):raise ops.SourceBlocked('RECEIPT_HASH')
            out=dict(status='ALREADY_BOUND_NO_RECAPTURE',source_id=old['source_id'],orders_allowed=False,money_authority=False)
        elif a.capture and not a.bootstrap and not plan['daily_due']:
            out=dict(status='NOT_DUE',schedule=plan,orders_allowed=False,money_authority=False)
        else:
            if a.capture:
                runtime=ops.safe_path(a.runtime);runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
                captures=ops.safe_path(runtime/'captures');captures.mkdir(exist_ok=True,mode=0o700)
                cache=captures/str(time.time_ns());cap=ops.capture_full(cache)
                with (cache/'calendar.json').open('x') as f:json.dump(raw,f,sort_keys=True,indent=2)
            elif a.cache:
                cache=ops.safe_path(a.cache);cap=json.loads((cache/'capture.json').read_bytes())
            else:raise ops.SourceBlocked('CAPTURE_OR_CACHE_REQUIRED')
            bundle=ops.compile_source(cache,cap,cal,now_ms=time.time_ns()//1000000)
            out=ops.bind_source(a.runtime/'book',bundle,now_ms=time.time_ns()//1000000) if a.bind_orders_off else dict(
              status=bundle['status'],source_id=bundle['source_id'],symbols=len(bundle['history']),
              latest_session=bundle['signal_session'],coverage=bundle['coverage'],cache_root=str(cache),
              schedule=plan,orders_allowed=False,money_authority=False,broker_writes=0)
        print(json.dumps(out,sort_keys=True,allow_nan=False));return 0
    except (ops.SourceBlocked,ValueError,TypeError,KeyError,OSError) as exc:
        issues=exc.issues if isinstance(exc,ops.SourceBlocked) else [type(exc).__name__]
        print(json.dumps(dict(status='DATA_BLOCKED',issues=issues,orders_allowed=False,money_authority=False,broker_writes=0)))
        return 2


if __name__=='__main__':raise SystemExit(main())
