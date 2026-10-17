#!/usr/bin/env python3
"""Original Dynamic59 source only; no entry/strategy/account owner or order API."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_lab import alpaca_dynamic_source_ops_v1 as ops
from scripts.run_alpaca_monthly_source_ops_v1 import calendar_capture,load_calendar


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path)
    p.add_argument('--package-spec',type=Path);p.add_argument('--package-spec-sha256')
    g=p.add_mutually_exclusive_group();g.add_argument('--calendar-profile',type=Path);g.add_argument('--calendar-source',type=Path)
    p.add_argument('--calendar-source-sha256');p.add_argument('--capture',action='store_true')
    p.add_argument('--cache',type=Path);p.add_argument('--bootstrap',action='store_true')
    a=p.parse_args(argv)
    if not any((a.calendar_profile,a.calendar_source,a.capture,a.cache)):
        print(json.dumps({'status':'NO_NETWORK_ORDERS_OFF','symbols':len(ops.required_symbols()),'orders_allowed':False,'money_authority':False}));return 0
    try:
        if a.package_spec:
            sp=ops.ops.safe_path(a.package_spec)
            if ops.ops.sha(sp)!=a.package_spec_sha256:raise ValueError('PACKAGE_SPEC_PIN')
            s=json.loads(sp.read_bytes())
            if (s.get('schema')!='DYNAMIC59_SOURCE_OPS_PACKAGE_V1' or s.get('money_authority') is not False
                or s.get('orders_allowed') is not False):raise ValueError('PACKAGE_SCOPE')
            for n,h in s['files'].items():
                if Path(n).is_absolute() or '..' in Path(n).parts or ops.ops.sha(ops.ops.safe_path(sp.parent/'app'/n))!=h:
                    raise ValueError('PACKAGE_FILE_PIN')
        if not a.runtime or (a.capture==bool(a.cache)):raise ValueError('ONE_CAPTURE_OR_CACHE_REQUIRED')
        runtime=ops.ops.safe_path(a.runtime);now=time.time_ns()//1000000
        if a.calendar_profile:raw=calendar_capture(a.calendar_profile,now)
        elif a.calendar_source:
            cp=ops.ops.safe_path(a.calendar_source)
            if ops.ops.sha(cp)!=a.calendar_source_sha256:raise ValueError('CALENDAR_PIN')
            raw=json.loads(cp.read_bytes())
        else:raise ValueError('CALENDAR_REQUIRED')
        now=time.time_ns()//1000000;cal=load_calendar(raw,now);plan=ops.ops.schedule(cal,now_ms=now)
        old=ops.ops.safe_path(runtime/'sources'/(plan['signal_session']+'.json')) if plan['signal_session'] else None
        if a.capture and old and old.exists():
            bundle=json.loads(old.read_bytes())
            rebuilt=ops.compile_source(bundle['cache_root'],bundle['cache_capture'],bundle['calendar'],now_ms=now)
            if rebuilt!=bundle:raise ValueError('SAVED_SOURCE_CONFLICT')
            out=ops.seal_source(runtime/'sources',bundle)
        elif a.capture and not a.bootstrap and not plan['daily_due']:
            out={'status':'NOT_DUE','schedule':plan,'orders_allowed':False,'money_authority':False}
        else:
            runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
            if a.capture:
                captures=ops.ops.safe_path(runtime/'captures');captures.mkdir(exist_ok=True,mode=0o700)
                cache=captures/str(time.time_ns());cap=ops.capture_full(cache)
                with (cache/'calendar.json').open('x') as f:json.dump(raw,f,sort_keys=True)
            else:cache=ops.ops.safe_path(a.cache);cap=json.loads((cache/'capture.json').read_bytes())
            bundle=ops.compile_source(cache,cap,cal,now_ms=time.time_ns()//1000000)
            out=ops.seal_source(runtime/'sources',bundle)
        out.update(symbols=59,broker_writes=0)
    except (ValueError,TypeError,KeyError,OSError) as e:
        out={'status':'DYNAMIC59_DATA_BLOCKED','error_type':type(e).__name__,'orders_allowed':False,'money_authority':False,'broker_writes':0}
    print(json.dumps(out,sort_keys=True));return 2 if out['status'].endswith('BLOCKED') else 0
if __name__=='__main__':raise SystemExit(main())
