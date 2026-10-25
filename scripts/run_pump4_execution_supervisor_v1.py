#!/usr/bin/env python3
"""Explicit selected PUMP4 account supervisor. Default: no state or requests.

--orders-off requires the physically verified isolated ORDERS_OFF selection.
--dispatch additionally requires exact pinned live scope and existing owner GO.
No install, GO creation, credentials override or physical-verifier bypass.
"""
import argparse
import json
from pathlib import Path
import signal
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.pump4_execution_supervisor_v1 import run


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--orders-off',action='store_true')
    modes.add_argument('--dispatch',action='store_true')
    parser.add_argument('--config',type=Path)
    parser.add_argument('--config-sha256')
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--poll-seconds',type=int,default=5)
    args=parser.parse_args(argv)
    if not args.orders_off and not args.dispatch:
        print(json.dumps(dict(status='ORDERS_OFF_NO_REQUESTS',broker_writes=0)))
        return 0
    if args.config is None or args.config_sha256 is None or not 5<=args.poll_seconds<=30:
        parser.error('Explicit config, config-sha256 and poll-seconds 5..30 required')
    stop=threading.Event();last=None;failed=False
    previous={sig:signal.signal(sig,lambda *_:stop.set()) for sig in (signal.SIGTERM,signal.SIGINT)}
    def output(receipt):
        nonlocal last,failed
        result=receipt['result'];failed=result['status'].startswith('BLOCKED') or receipt.get('receipt_persisted') is False
        summary=dict(status=result['status'],result=result,mode=receipt['mode'],broker_writes=receipt['broker_writes'])
        encoded=json.dumps(summary,sort_keys=True)
        if encoded!=last:print(encoded,flush=True);last=encoded
    try:
        run(args.config,args.config_sha256,dispatch=args.dispatch,orders_off=args.orders_off,
            once=args.once,poll_seconds=args.poll_seconds,stop=stop,on_receipt=output)
        return int(failed)
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps(dict(status='BLOCKED_EXECUTION_SUPERVISOR',error_type=type(exc).__name__,broker_writes=None if args.dispatch else 0)),flush=True)
        return 2
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)


if __name__=='__main__':raise SystemExit(main())
