#!/usr/bin/env python3
"""Source-accounted PUMP4 candidate. Explicit isolated ORDERS_OFF only; no GO."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research_lab.pump4_serial_source_supervisor_v1 import run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--orders-off', action='store_true')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--config-sha256')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    if not args.orders_off:
        print(json.dumps(dict(status='ORDERS_OFF_NO_REQUESTS', broker_writes=0)))
        return 0
    if not args.config or not args.config_sha256:
        parser.error('Explicit config and config-sha256 required')
    try:
        receipts = run(args.config, args.config_sha256, orders_off=True, once=args.once)
        print(json.dumps(receipts[-1], sort_keys=True))
        return int(receipts[-1]['result']['status'].startswith('BLOCKED'))
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as exc:
        print(json.dumps(dict(status='BLOCKED_SERIAL_SOURCE_OFF', error_type=type(exc).__name__, broker_writes=0)))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
