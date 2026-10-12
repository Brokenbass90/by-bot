#!/usr/bin/env python3
"""Explicit Dynamic LIVE runtime interface. Default reads only; never clears HALT.

Not installed or scheduled. --apply alone cannot dispatch: exact independent
LIVE book, original shared lock, actual lifecycle sources and separate owner-GO
file are required. No monthly env overlay and no PAPER credential fallback.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from research_lab.alpaca_dynamic_live_runtime_v1 import (
    LIVE, DynamicLiveClient, read_json, safe_path, run_once, result,
)
from research_lab.alpaca_dynamic_v1 import digest

POLICY_PIN='fe72557bd7c7437eda328047e81980ee762ec794ac240494ec47d3de4f6f400d'


def load_client(profile,binding,*,apply):
    from dotenv import dotenv_values
    p=safe_path(str(profile),exists=True)
    if p.parent!=Path(binding['broker_root'])/'configs':raise ValueError('ORIGINAL_LIVE_PROFILE_REQUIRED')
    env=dotenv_values(p,interpolate=False)
    if (env.get('ALPACA_BASE_URL')!=LIVE or not env.get('ALPACA_API_KEY_ID')
        or not env.get('ALPACA_API_SECRET_KEY')):raise ValueError('EXPLICIT_LIVE_CREDENTIAL_PROFILE_REQUIRED')
    configured=env.get('ALPACA_BRIDGE_LOCK_PATH')
    lock=configured or str(Path(binding['broker_root'])/'runtime/locks'/(
        'alpaca_bridge_'+hashlib.sha256((LIVE+'|'+env['ALPACA_API_KEY_ID']).encode()).hexdigest()[:16]+'.lock'))
    if lock!=binding['lock_path']:raise ValueError('ORIGINAL_PROFILE_LOCK_CONFLICT')
    return DynamicLiveClient(env['ALPACA_API_KEY_ID'],env['ALPACA_API_SECRET_KEY'],writes_enabled=apply)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy',type=Path,default=ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json')
    parser.add_argument('--intake',type=Path,required=True)
    parser.add_argument('--binding',type=Path,required=True)
    parser.add_argument('--live-profile',type=Path,required=True)
    parser.add_argument('--owner-go',type=Path)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--maintenance',action='store_true',help='owned lifecycle only; no new entry')
    parser.add_argument('--kill',action='store_true',help='scoped owned exit; requires maintenance')
    parser.add_argument('--cost-finality',type=Path,help='source-pinned external account/day reconciliation; never inferred from flatness')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    try:
        policy=read_json(str(args.policy));intake=read_json(str(args.intake));binding=read_json(str(args.binding))
        if digest(policy)!=POLICY_PIN:raise ValueError('SEALED_POLICY_CONFLICT')
        if args.kill and not args.maintenance:raise ValueError('KILL_REQUIRES_OWNED_MAINTENANCE')
        if args.cost_finality and not args.maintenance:raise ValueError('FINALITY_REQUIRES_OWNED_MAINTENANCE')
        if args.apply and not args.owner_go:raise ValueError('SEPARATE_EXACT_OWNER_GO_REQUIRED')
        client=load_client(args.live_profile,binding,apply=args.apply)
        out=run_once(intake=intake,policy=policy,binding=binding,client=client,now_ms=time.time_ns()//1_000_000,
            apply=args.apply,owner_go_path=str(args.owner_go) if args.owner_go else None,
            maintenance=args.maintenance,kill=args.kill,cost_finality_path=str(args.cost_finality) if args.cost_finality else None)
    except Exception as e:
        # No profile values/credentials or HTTP headers in receipts.
        out=result('BLOCKED_DATA',reason=str(e) or type(e).__name__,orders_allowed=False)
    raw=json.dumps(out,indent=2,allow_nan=False)+'\n'
    if args.output:
        target=safe_path(str(args.output));target.parent.mkdir(parents=True,exist_ok=True)
        import os
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(raw)
    print(raw,end='')
    return 2 if out['status'].startswith('BLOCKED') else 0


if __name__=='__main__':raise SystemExit(main())
