#!/usr/bin/env python3
"""Candidate saved-source runner. No HTTP, profile, financial apply or owner GO."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_lab.alpaca_dynamic_reselection_v1 import EventReselectionBook,CONTRACT
from research_lab.alpaca_dynamic_live_runtime_v1 import safe_path,read_json
from research_lab.alpaca_dynamic_v1 import digest
from scripts.run_alpaca_dynamic_v1_orders_off import load_history

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs',type=Path);ap.add_argument('--inputs-sha256');ap.add_argument('--book',type=Path)
    a=ap.parse_args(argv)
    if a.inputs is None:
        print(json.dumps({'status':'NO_NETWORK_ORDERS_OFF','contract':CONTRACT}));return 0
    try:
        if a.book is None:raise ValueError('OWN_CANDIDATE_BOOK_REQUIRED')
        source=safe_path(str(a.inputs.absolute()),exists=True);book=safe_path(str(a.book.absolute()))
        if source==book or source.parent==book:raise ValueError('SOURCE_BOOK_OVERLAP')
        raw=source.read_bytes()
        if len(raw)>64000000 or hashlib.sha256(raw).hexdigest()!=a.inputs_sha256:raise ValueError('INPUT_PIN')
        x=read_json(str(source));p=read_json(str(ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json'))
        if digest(p)!='fe72557bd7c7437eda328047e81980ee762ec794ac240494ec47d3de4f6f400d':raise ValueError('BASE_POLICY_PIN')
        b=EventReselectionBook(book,p)
        out=b.reselect(snapshot=x['snapshot'],history=load_history(x['history']),calendar=p['calendar_sessions'],
          source_sha256=x['source_sha256'],source_available_ms=x['source_available_ms'],now_ms=x['now_ms'])
    except Exception as e:
        out={'status':'BLOCKED_INPUT','error_type':type(e).__name__,'orders_allowed':False,'money_authority':False}
    print(json.dumps(out,sort_keys=True,allow_nan=False));return 2 if out['status'].startswith('BLOCKED') else 0
if __name__=='__main__':raise SystemExit(main())
