#!/usr/bin/env python3
"""Saved capture only. Capacity PASS never creates a policy or money permit."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_lab.kity_micro_feasibility_v1 import assess_saved_capture,future_owner_proposal

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path);p.add_argument('--capture-sha256')
    p.add_argument('--future-owner-proposal',action='store_true',help='inert next-decision packet; never creates a policy')
    a=p.parse_args(argv)
    if a.capture is None:print(json.dumps({'status':'NO_NETWORK_ORDERS_OFF','orders_allowed':False}));return 0
    try:
        bounds=json.loads((ROOT/'configs/research/kity_execution_micro_owner_bounds_v3_20261015.json').read_bytes())
        out=assess_saved_capture(a.capture,a.capture_sha256,bounds)
        if a.future_owner_proposal:out=future_owner_proposal(out)
    except Exception as e:
        print(json.dumps({'status':'CAPACITY_INPUT_BLOCKED','error_type':type(e).__name__,'orders_allowed':False}));return 2
    print(json.dumps(out,sort_keys=True,allow_nan=False));return 2 if out['status'].startswith('CAPACITY_BLOCKED') else 0
if __name__=='__main__':raise SystemExit(main())
