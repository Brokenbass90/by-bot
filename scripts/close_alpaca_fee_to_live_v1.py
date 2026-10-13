#!/usr/bin/env python3
"""One offline fee-to-dossier closure. No broker call or automatic retry."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_dynamic_live_runtime_v1 import read_json,safe_path
from research_lab.alpaca_fee_to_live_closure_v1 import close_once
from research_lab.alpaca_live_readiness_v1 import blocked


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','manifest-sha256','terminal-capture','live-preparation'):
        p.add_argument('--'+name,required=True)
    args=p.parse_args(argv)
    try:
        raw=safe_path(args.manifest,exists=True).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=args.manifest_sha256:raise ValueError('EXTERNAL_MANIFEST_PIN_CONFLICT')
        result=close_once(read_json(args.manifest),terminal_capture=args.terminal_capture,
            live_preparation=args.live_preparation,now_ms=time.time_ns()//1000000)
    except (ValueError,KeyError,TypeError,OSError) as exc:result=blocked(str(exc))
    print(json.dumps(result))
    return 0 if result['status']=='READY_FOR_LIVE_GO' else 2


if __name__=='__main__':raise SystemExit(main())
