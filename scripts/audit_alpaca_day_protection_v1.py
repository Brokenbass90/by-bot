#!/usr/bin/env python3
"""Audit one saved GET-only DAY readback. No credentials, dispatcher or scheduler."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_day_protection_v1 import evaluate
from research_lab.kity_oct15_deadline_v1 import publish_once


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture-json',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--replay-recorded-time',action='store_true',help='offline replay only; never a fresh observation')
    args=p.parse_args(argv)
    source=json.loads(args.capture_json.read_bytes())
    now=source['completed_ms'] if args.replay_recorded_time else time.time_ns()//1000000
    observation=evaluate(source,now_ms=now)
    payload=dict(schema='ALPACA_DAY_PROTECTION_AUDIT_RECEIPT_V1',
        mode='OFFLINE_SAVED_SOURCE_REPLAY' if args.replay_recorded_time else 'CAPTURE_FRESHNESS_CHECK',
        replay_is_fresh_broker_observation=False,observation=observation,
        observer_activated=False,notifications_sent=0,orders_allowed=False,money_authority=False)
    publish_once(args.output.resolve(),(json.dumps(payload,indent=2,allow_nan=False)+'\n').encode())
    print(json.dumps(dict(status=observation['status'],mode=payload['mode'],
        observer_activated=False,orders_allowed=False)))
    return 2 if observation['issues'] else 0


if __name__=='__main__':raise SystemExit(main())
