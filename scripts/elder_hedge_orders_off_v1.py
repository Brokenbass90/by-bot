#!/usr/bin/env python3
"""Explicit saved-input Elder adapter. No default source scan/network/writer."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research_lab.elder_hedge_orders_off_v1 import compile_intent,report_event
from research_lab.kity_oct15_deadline_v1 import publish_once


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--bundle',required=True)
    parser.add_argument('--bundle-sha256',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    raw=Path(args.bundle).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.bundle_sha256:raise ValueError('ELDER_BUNDLE_PIN_CONFLICT')
    value=json.loads(raw)
    intent=compile_intent(value['raw_first_record'].encode(),source_ref=value['source_ref'],
        context=value['context'],risk=value['risk'],instrument=value['instrument'],now_ms=value['observed_ms'])
    out=dict(status=intent['status'],source_use='EXPLICIT_SAVED_INPUT_NOT_FRESH_BROKER_STATE',
        bundle_sha256=args.bundle_sha256,intent=intent,report_event=report_event(intent),
        broker_writes=0,orders_allowed=False)
    publish_once(Path(args.output),(json.dumps(out,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps(dict(status=out['status'],orders_allowed=False,broker_writes=0)))
    return 0


if __name__=='__main__':raise SystemExit(main())
