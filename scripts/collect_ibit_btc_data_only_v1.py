#!/usr/bin/env python3
"""GET-only collector. No arguments/default is NO_NETWORK with no profile read.

Network requires --network, --credentials explicit observer dotenv profile,
--store isolated physical directory and --session YYYY-MM-DD. --probe captures
without any decision: historical retrieval is not prospective evidence.
--massive-qa requires an explicit MASSIVE_API_KEY in that same profile.
--qa-only can reconcile a past existing decision without new source decisions.
Never emits credentials, response bodies, remote exception text or query URLs.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_lab.ibit_btc_collector_v1 import Collector,SourceError


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network',action='store_true',help='explicit GET-only opt-in')
    parser.add_argument('--credentials',help='explicit existing observer dotenv profile')
    parser.add_argument('--store',help='owned isolated runtime directory; physical path only')
    parser.add_argument('--session',help='one calendar session YYYY-MM-DD')
    parser.add_argument('--probe',action='store_true',help='capture-only, never writes decisions')
    parser.add_argument('--massive-qa',action='store_true')
    parser.add_argument('--qa-only',action='store_true')
    args=parser.parse_args(argv)
    if not args.network:
        print(json.dumps({'status':'NO_NETWORK','orders_enabled':False}))
        return 0
    if not args.store or not args.credentials or not args.session:
        print(json.dumps({'status':'REJECTED','code':'EXPLICIT_ARGUMENTS_REQUIRED','orders_enabled':False}),file=sys.stderr)
        return 2
    try:
        result=Collector(args.store,credentials=args.credentials,enabled=True).collect(
            args.session,massive_qa=args.massive_qa,qa_only=args.qa_only,probe=args.probe)
    except Exception as error:
        # Only SourceError fixed codes are safe to display. No repr/str leakage.
        code=error.code if isinstance(error,SourceError) else 'LOCAL_VALIDATION_ERROR'
        print(json.dumps({'status':'REJECTED','code':code,'orders_enabled':False}),file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True,ensure_ascii=False,allow_nan=False))
    return 0 if not result.get('errors') else 1


if __name__=='__main__':
    raise SystemExit(main())
