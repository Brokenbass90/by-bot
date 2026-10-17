#!/usr/bin/env python3
"""Explicit local DATA-ONLY seal/import. Default has no network or file effects."""
import argparse,json,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_lab.liq_research_delivery_v1 import seal_daily,import_snapshot


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group();g.add_argument('--seal-root',type=Path);g.add_argument('--import-from',type=Path)
    p.add_argument('--destination',type=Path);p.add_argument('--day',default=datetime.now(timezone.utc).strftime('%Y%m%d'))
    a=p.parse_args(argv)
    if not a.seal_root and not a.import_from:
        print(json.dumps({'status':'NO_NETWORK_DATA_ONLY','orders_allowed':False}));return 0
    try:
        if a.seal_root:
            if a.destination:raise ValueError('SEAL_DESTINATION_CONFLICT')
            result=seal_daily(a.seal_root,a.day)
        else:
            if not a.destination:raise ValueError('DESTINATION_REQUIRED')
            result=import_snapshot(a.import_from,a.destination,a.day)
        out={'status':'IMMUTABLE_DATA_DELIVERY_PASS',**result}
    except (ValueError,OSError,KeyError,TypeError) as e:
        out={'status':'BLOCKED_DATA_DELIVERY','error_type':type(e).__name__,'orders_allowed':False}
    print(json.dumps(out,sort_keys=True));return 2 if out['status'].startswith('BLOCKED') else 0
if __name__=='__main__':raise SystemExit(main())
