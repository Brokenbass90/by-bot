#!/usr/bin/env python3
"""Disabled monthly/daily source worker. No apply/owner-GO/order interface.

Source and state are bound independently from the current NET monetary manager.
Default verifies a pinned package without broker access or creating a book.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research_lab.alpaca_monthly_binding_v1 import CONTRACT,MonthlyBook,strategy_identity
from research_lab.alpaca_monthly_native_binding_v1 import MonthlyNativeBinding
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.alpaca_dynamic_live_runtime_v1 import read_json,safe_path
from scripts.run_alpaca_dynamic_v1_orders_off import load_history
from research_lab.alpaca_completed_session_source_v1 import from_cache,SOURCE_PINS

REQUIRED={'scripts/run_alpaca_monthly_binding_v1.py','research_lab/alpaca_monthly_binding_v1.py',
    'research_lab/alpaca_completed_session_source_v1.py','research_lab/alpaca_strategy_parity_v1.py',
    'research_lab/alpaca_monthly_native_binding_v1.py','scripts/equities_alpaca_paper_bridge.py',
    'research_lab/alpaca_dynamic_live_runtime_v1.py',*SOURCE_PINS}


def verify_spec(path,expected):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('MONTHLY_SPEC_PIN_MISMATCH')
    spec=json.loads(raw)
    if (spec['schema']!='ALPACA_MONTHLY_DISABLED_SOURCE_BINDING_V1'
        or spec['contract']!=CONTRACT or spec['contract_sha256']!=digest(CONTRACT)
        or spec['orders_allowed'] is not False or spec['enabled'] is not False):
        raise ValueError('MONTHLY_DISABLED_CONTRACT_REQUIRED')
    if not REQUIRED.issubset(spec['files']):raise ValueError('MONTHLY_REQUIRED_SOURCE_MISSING')
    for name,pin in spec['files'].items():
        p=safe_path(str(ROOT/name),exists=True)
        if not p.is_relative_to(ROOT) or hashlib.sha256(p.read_bytes()).hexdigest()!=pin:
            raise ValueError('MONTHLY_SOURCE_PIN_MISMATCH:'+name)
    if (spec.get('strategy_identity')!=strategy_identity()
        or spec.get('legacy_dynamic_entry_authority') is not False):
        raise ValueError('EXPLICIT_MONTHLY_STRATEGY_IDENTITY_REQUIRED')
    return spec


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--spec',required=True,type=Path);ap.add_argument('--spec-sha256',required=True)
    ap.add_argument('--book',type=Path);ap.add_argument('--selection-source',type=Path)
    ap.add_argument('--daily-source',type=Path);ap.add_argument('--plan-selection')
    ap.add_argument('--daily-cache',type=Path,help='immutable raw cache corresponding to --daily-source')
    ap.add_argument('--output',type=Path)
    a=ap.parse_args(argv)
    try:
        spec=verify_spec(a.spec,a.spec_sha256)
        if sum(bool(x) for x in (a.selection_source,a.daily_source,a.plan_selection))>1:
            raise ValueError('ONE_SOURCE_OPERATION_REQUIRED')
        now=time.time_ns()//1_000_000
        if not any((a.selection_source,a.daily_source,a.plan_selection)):
            out=dict(status='MONTHLY_SOURCE_PACKAGE_VERIFIED_ORDERS_OFF',source_files=len(spec['files']),
                contract_sha256=spec['contract_sha256'],orders_allowed=False,money_authority=False,
                production_writer_installed=False)
        else:
            if a.book is None:raise ValueError('SEPARATE_MONTHLY_BOOK_REQUIRED')
            book_path=safe_path(str(a.book))
            if not book_path.is_relative_to(ROOT/'runtime'):
                raise ValueError('SEPARATE_PACKAGE_RUNTIME_REQUIRED')
            book=MonthlyBook(book_path,CONTRACT)
            if a.selection_source:
                raw=safe_path(str(a.selection_source),exists=True).read_bytes();s=json.loads(raw)
                selection=book.seal_selection(load_history(s['history']),s['calendar'],
                    signal_session=s['signal_session'],entry_session=s['entry_session'],
                    source_available_ms=s['source_available_ms'],source_sha256=hashlib.sha256(raw).hexdigest(),now_ms=now)
                out=dict(status='MONTHLY_SELECTION_BOUND_ORDERS_OFF',selection_id=selection['selection_id'],
                    orders_allowed=False,money_authority=False,production_writer_installed=False)
            elif a.daily_source:
                raw=read_json(str(a.daily_source))
                if a.daily_cache is None:raise ValueError('EXACT_DAILY_RAW_CACHE_REQUIRED')
                cache=safe_path(str(a.daily_cache),exists=True)
                if not cache.is_relative_to(ROOT/'runtime'):
                    raise ValueError('SEPARATE_PACKAGE_CACHE_REQUIRED')
                rebuilt=from_cache(cache,sorted(r['symbol'] for r in raw['raw']),raw['calendar'],
                    read_json(str(cache/'capture.json')),now_ms=now)
                if rebuilt!=raw:raise ValueError('EXACT_DAILY_SOURCE_DERIVATION_CONFLICT')
                out=book.observe_close(rebuilt,now_ms=now)
            else:out=book.monthly_actions(a.plan_selection,now_ms=now)
        out['observed_ms']=now
    except (ValueError,KeyError,TypeError,OSError) as exc:
        out=dict(status='MONTHLY_BINDING_BLOCKED',reason=str(exc),orders_allowed=False,
                 money_authority=False,production_writer_installed=False)
    raw=json.dumps(out,indent=2,allow_nan=False)+'\n'
    if a.output:
        p=safe_path(str(a.output));fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    print(raw,end='')
    return 2 if out['status']=='MONTHLY_BINDING_BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
