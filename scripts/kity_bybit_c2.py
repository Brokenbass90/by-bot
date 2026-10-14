#!/usr/bin/env python3
"""Offline independent KITY_BYBIT C2; write only new files in our private root."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.kity_bybit_c2 import canonical,digest,read_json,safe_path,reconstruct,compare

OUTPUT_ROOT=ROOT/'.private/kity_bybit_c2'
def clock_ms():return time.time_ns()//1000000


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('reconstruct');p.add_argument('--bundle',type=Path,required=True)
    p=sub.add_parser('compare')
    for name in ('codex','shadow-signal','shadow-flow'):p.add_argument('--'+name,type=Path,required=True)
    for p in sub.choices.values():p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        out=safe_path(str(args.output.absolute()))
        if not out.is_relative_to(OUTPUT_ROOT) or out==OUTPUT_ROOT:raise ValueError('OWN_OUTPUT_SCOPE_ONLY')
        if out.exists():raise ValueError('IMMUTABLE_OUTPUT_ALREADY_EXISTS')
        if args.command=='reconstruct':result=reconstruct(read_json(str(args.bundle.absolute())),now_ms=clock_ms())
        else:
            result=compare(read_json(str(args.codex.absolute())),read_json(str(args.shadow_signal.absolute())),read_json(str(args.shadow_flow.absolute())))
        result.setdefault('receipt_sha256',digest(result))
        out.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(canonical(result));f.flush();os.fsync(f.fileno())
        print(json.dumps(dict(status=result['status'],receipt_sha256=result['receipt_sha256'],output=str(out),orders_allowed=False,money_ready=False)))
        return 0 if result['status'] in {'C2_RECONSTRUCTED_ORDERS_OFF','C2_PASS_MATCH_ONLY'} else 2
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps(dict(status='BLOCKED_DATA',reason=str(exc),orders_allowed=False,money_ready=False)));return 2


if __name__=='__main__':raise SystemExit(main())
