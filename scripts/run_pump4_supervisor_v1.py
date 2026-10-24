#!/usr/bin/env python3
"""Persistent PUMP4 DATA/ORDERS_OFF worker. No credentials, lease or POST.

Explicit --source-mode public reuses the public exact137 collector once/hour.
--source-mode archive verifies an existing capture. Default does no requests.
SIGTERM/SIGINT stop the DATA loop after the current bounded capture; they do not
stop any financial owner. Production selected dispatch is deliberately blocked.
"""
import argparse
import json
from pathlib import Path
import signal
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.pump4_supervisor_v1 import Supervisor


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path)
    parser.add_argument('--source-mode',choices=('off','archive','public'),default='off')
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--poll-seconds',type=int,default=30)
    parser.add_argument('--max-delay-ms',type=int,default=60000)
    parser.add_argument('--dispatch',action='store_true')
    args=parser.parse_args(argv)
    if args.dispatch:
        print(json.dumps(dict(status='SELECTED_DISPATCH_NOT_WIRED',
            reason='Requires reviewed selected physical configuration, exact owner GO, original lease handoff, trusted fresh account provider and epoch/delay binding. DATA daemon never selects an owner.',broker_writes=0)))
        return 2
    if args.source_mode=='off':
        print(json.dumps(dict(status='ORDERS_OFF_NO_REQUESTS',broker_writes=0)))
        return 0
    if args.root is None or not 5<=args.poll_seconds<=60:
        parser.error('Explicit --root and --poll-seconds between 5 and 60 required')
    if args.source_mode=='archive' and args.archive is None:
        parser.error('--archive required for archive source mode')
    if args.source_mode=='public' and not args.root.absolute().is_relative_to(ROOT/'.private'):
        parser.error('Public capture root must be inside this checkout .private')
    supervisor=Supervisor(args.root,max_delay_ms=args.max_delay_ms)
    stop=threading.Event()
    previous={sig:signal.signal(sig,lambda *_:stop.set()) for sig in (signal.SIGINT,signal.SIGTERM)}
    last=None
    try:
        while not stop.is_set():
            try:
                result=supervisor.public_cycle() if args.source_mode=='public' else supervisor.process_archive(args.archive)
                summary={k:v for k,v in result.items() if k!='rows'}
                code=0
            except (ValueError,KeyError,TypeError,OSError) as exc:
                summary=dict(status='BLOCKED_DATA',reason=str(exc),broker_writes=0,orders_allowed=False)
                code=1
            encoded=json.dumps(summary,sort_keys=True)
            if encoded!=last:
                print(encoded,flush=True);last=encoded
            if args.once:
                return code
            stop.wait(args.poll_seconds)
        return 0
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)


if __name__=='__main__':raise SystemExit(main())
