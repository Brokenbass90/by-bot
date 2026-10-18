#!/usr/bin/env python3
"""Pinned FILE-ONLY courier after the existing Monthly source. No broker/network."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_lab import alpaca_monthly_source_ops_v1 as ops
from research_lab.alpaca_monthly_data_parity_v1 import build_delivery,publish_delivery,verify_files
from scripts.run_alpaca_monthly_source_ops_v1 import load_calendar


def completed_caches(root):
    found=[]
    for p in root.iterdir():
        if not p.is_dir() or not p.name.isdigit() or p.is_symlink():continue
        try:
            json.loads((p/'capture.json').read_bytes());json.loads((p/'calendar.json').read_bytes())
        except (FileNotFoundError,json.JSONDecodeError):continue
        found.append(p)
    return sorted(found,key=lambda p:int(p.name),reverse=True)


def candidate_bundle(cache,*,now_ms):
    cap=json.loads((cache/'capture.json').read_bytes());asof=cap['completed_ms']
    if type(asof) is not int or not 0<asof<=now_ms:raise ValueError('FUTURE_OR_UNKNOWN_CAPTURE')
    cal=load_calendar(json.loads((cache/'calendar.json').read_bytes()),asof)
    return ops.compile_source(cache,cap,cal,now_ms=asof)


def accepted_source(spec,cache,bundle):
    """Verify the original pinned source worker's identity against its own seal.

    Runs only its pure cache compiler, with no --capture/--bind or broker route.
    Receipt/source files are read-only. The different caller app path is never
    substituted into the original source identity.
    """
    receipt=ops.safe_path(Path(spec['source_receipts'])/(bundle['signal_session']+'.json'))
    if not receipt.is_file():return None
    raw=receipt.read_bytes();r=json.loads(raw)
    if r['receipt_sha256']!=ops.digest({k:v for k,v in r.items() if k!='receipt_sha256'}):
        raise ValueError('MONTHLY_SOURCE_RECEIPT_HASH')
    code='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from scripts.run_alpaca_monthly_source_ops_v1 import verify_package,load_calendar
from research_lab import alpaca_monthly_source_ops_v1 as ops
verify_package(sys.argv[2],sys.argv[3])
p=Path(sys.argv[4]);cap=json.loads((p/'capture.json').read_bytes())
cal=load_calendar(json.loads((p/'calendar.json').read_bytes()),cap['completed_ms'])
b=ops.compile_source(p,cap,cal,now_ms=cap['completed_ms'])
print(json.dumps(dict(source_id=b['source_id'],history_sha256=ops.digest(b['history']),calendar_sha256=ops.digest(cal))))
'''
    actual=json.loads(subprocess.check_output([sys.executable,'-B','-c',code,spec['source_app'],
        spec['source_package_spec'],spec['source_package_spec_sha256'],str(cache)],text=True,timeout=180))
    if (actual['source_id']!=r['source_id'] or actual['history_sha256']!=ops.digest(bundle['history'])
        or actual['calendar_sha256']!=ops.digest(bundle['calendar'])):raise ValueError('ACCEPTED_MONTHLY_SOURCE_MISMATCH')
    return dict(receipt_sha256=ops.hashlib.sha256(raw).hexdigest(),**actual)


def run(spec,*,now_ms,session=None):
    if spec.get('orders_allowed') is not False or spec.get('money_authority') is not False:
        raise ValueError('DATA_ONLY_REQUIRED')
    exports=ops.safe_path(spec['exports']);root=ops.safe_path(spec['source_captures'])
    caches=completed_caches(root)
    if not caches:raise ValueError('NO_MONTHLY_CAPTURES')
    newest=caches[0];calendar=load_calendar(json.loads((newest/'calendar.json').read_bytes()),now_ms)
    plan=ops.schedule(calendar,now_ms=now_ms);target=session or plan['signal_session']
    if session is None and not plan['daily_due']:return dict(status='NOT_DUE_DATA_ONLY',orders_allowed=False)
    if not target or not any(r['session']==target and r['close_ms']<=now_ms for r in calendar):
        raise ValueError('COMPLETED_SESSION_REQUIRED')
    if (exports/(target+'.delivery.json')).exists():
        verify_files(exports,target)
        return dict(status='ALREADY_SEALED_DATA_ONLY',session_date=target,broker_writes=0,orders_allowed=False)
    if shutil.disk_usage(exports.parent).free<512*1024*1024:raise ValueError('EXPORT_DISK_RESERVE')
    for cache in caches:
        cal=load_calendar(json.loads((cache/'calendar.json').read_bytes()),now_ms)
        cap=json.loads((cache/'capture.json').read_bytes())
        close=next((r['close_ms'] for r in cal if r['session']==target),None)
        if close is None or cap['completed_ms']<close:continue
        # A later-session cache must never fabricate an earlier as-of snapshot.
        b=candidate_bundle(cache,now_ms=now_ms)
        if b['signal_session']!=target:continue
        lineage=accepted_source(spec,cache,b)
        if lineage is None:continue
        x=build_delivery(b,now_ms=cap['completed_ms'])
        x['production_source_seal']=lineage
        x['data_sha256']=ops.digest({k:v for k,v in x.items() if k!='data_sha256'})
        return publish_delivery(exports,x)
    return dict(status='WAITING_EXACT_SESSION_CAPTURE',session_date=target,broker_writes=0,orders_allowed=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--spec');p.add_argument('--spec-sha256')
    p.add_argument('--session');a=p.parse_args(argv)
    if not a.spec:
        print(json.dumps(dict(status='NO_NETWORK_DATA_ONLY',orders_allowed=False)));return 0
    try:
        sp=ops.safe_path(a.spec)
        if ops.sha(sp)!=a.spec_sha256:raise ValueError('EXPORT_SPEC_PIN')
        spec=json.loads(sp.read_bytes())
        if spec['schema']!='ALPACA_MONTHLY58_DATA_EXPORT_SPEC_V1':raise ValueError('EXPORT_SPEC_SCHEMA')
        required={'research_lab/alpaca_monthly_data_parity_v1.py','research_lab/alpaca_monthly_source_ops_v1.py',
            'scripts/export_alpaca_monthly58_daily_v1.py','scripts/alpaca_adaptive_paper.py',
            'backtest/alpaca_honest_portfolio.py'}
        if not required<=set(spec['files']):raise ValueError('EXPORT_CODE_CLOSURE')
        for n,pin in spec['files'].items():
            if Path(n).is_absolute() or '..' in Path(n).parts or ops.sha(ops.safe_path(ROOT/n))!=pin:
                raise ValueError('EXPORT_CODE_PIN')
        out=run(spec,now_ms=time.time_ns()//1000000,session=a.session)
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as e:
        out=dict(status='DATA_EXPORT_BLOCKED',reason=str(e),orders_allowed=False,broker_writes=0)
    print(json.dumps(out,sort_keys=True));return 2 if out['status']=='DATA_EXPORT_BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
