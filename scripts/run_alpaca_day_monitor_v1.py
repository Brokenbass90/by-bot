#!/usr/bin/env python3
"""Pinned recurring NET GET-only observer. No money or manager interface."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_day_monitor_v1 import Monitor,collect,telegram,pin_files
from research_lab.kity_oct15_deadline_v1 import stable_bytes


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec',type=Path,required=True);p.add_argument('--spec-sha256',required=True)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--test-notification-once',action='store_true')
    mode.add_argument('--service-failure',action='store_true')
    args=p.parse_args(argv)
    raw=stable_bytes(args.spec)
    if hashlib.sha256(raw).hexdigest()!=args.spec_sha256:raise ValueError('OBSERVER_SPEC_PIN_DRIFT')
    config=json.loads(raw)
    if (config['schema']!='ALPACA_NET_DAY_READ_ONLY_MONITOR_V1' or config['symbols']!=['NET']
        or config['orders_allowed'] is not False or config['money_authority'] is not False):
        raise ValueError('READ_ONLY_NET_SCOPE_REQUIRED')
    pin_files(config['observer_files'])
    with Monitor(config['output_root'],clock=lambda:time.time_ns()//1000000) as monitor:
        sender=lambda event:telegram(config,event)
        if args.test_notification_once:out=monitor.delivery_test(sender)
        elif args.service_failure:out=monitor.service_failure(sender)
        else:
            out=monitor.once(lambda:collect(config),sender)
        print(json.dumps(dict(status=out.get('observation',out).get('status'),
            notification=out.get('notification',out).get('status'),broker_writes=0,money_authority=False)))
    return 0


if __name__=='__main__':raise SystemExit(main())
