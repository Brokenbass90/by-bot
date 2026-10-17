#!/usr/bin/env python3
"""Pinned DATA-ONLY server schedule. Explicit network; no financial capability."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research_lab.ibit_btc_collector_v1 import Collector,SourceError,CaptureStore
from research_lab.ibit_btc_data_only_v1 import NY,UTC,canonical,checked_path,_open_file

REQUIRED={'scripts/run_ibit_btc_source_ops_v1.py','scripts/collect_ibit_btc_data_only_v1.py',
          'scripts/run_ibit_btc_data_only_v1.py','research_lab/ibit_btc_collector_v1.py',
          'research_lab/ibit_btc_data_only_v1.py',
          'research_lab/vendor/etf_premiya_20261017/etf_premiya_sobytiya.py'}


def verify(path,pin):
    p=checked_path(path,regular=True)
    with _open_file(p,'rb') as f:raw=f.read(100000)
    if hashlib.sha256(raw).hexdigest()!=pin:raise SourceError('PACKAGE_PIN')
    spec=json.loads(raw)
    if spec.get('schema')!='IBIT_DATA_ONLY_SOURCE_PACKAGE_V1' or spec.get('orders_enabled') is not False:
        raise SourceError('PACKAGE_AUTHORITY')
    if not REQUIRED.issubset(spec['files']):raise SourceError('PACKAGE_CLOSURE')
    for name,digest in spec['files'].items():
        candidate=Path(name)
        if candidate.is_absolute() or '..' in candidate.parts:raise SourceError('PACKAGE_PATH')
        p=checked_path(ROOT/candidate,regular=True)
        with _open_file(p,'rb') as f:
            if hashlib.sha256(f.read()).hexdigest()!=digest:raise SourceError('SOURCE_PIN')
    return spec


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network',action='store_true')
    parser.add_argument('--spec',type=Path);parser.add_argument('--spec-sha256')
    parser.add_argument('--runtime',type=Path);parser.add_argument('--credentials',type=Path)
    args=parser.parse_args(argv)
    if not args.network:
        print(json.dumps({'status':'NO_NETWORK','orders_enabled':False}));return 0
    try:
        if not all((args.spec,args.spec_sha256,args.runtime,args.credentials)):raise SourceError('EXPLICIT_ARGUMENTS_REQUIRED')
        verify(args.spec,args.spec_sha256)
        runtime=checked_path(args.runtime);runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
        now=dt.datetime.now(UTC);session=now.astimezone(NY).date().isoformat()
        result=Collector(runtime/'collector',credentials=args.credentials,enabled=True).collect(session)
        result.update(session=session,observed_at=dt.datetime.now(UTC).isoformat(),broker_writes=0)
        # Unique immutable operation receipt; collector owns all raw/decision truth.
        CaptureStore.write(runtime/'operations'/(str(time.time_ns())+'.json'),canonical(result))
    except Exception as error:
        result={'status':'SOURCE_OPS_BLOCKED','code':error.code if isinstance(error,SourceError) else 'LOCAL_VALIDATION_ERROR',
                'orders_enabled':False,'broker_writes':0}
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    return 1 if result.get('errors') or result['status'] in ('SOURCE_OPS_BLOCKED','BLOCKED_CALENDAR') else 0


if __name__=='__main__':raise SystemExit(main())
