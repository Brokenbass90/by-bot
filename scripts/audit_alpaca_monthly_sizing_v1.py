#!/usr/bin/env python3
"""Read-only sizing audit on the already published reference lifecycle.

No portfolio/strategy simulator is called. Exit dates/fills are sealed inputs;
cash and every entry quantity are independently recalculated in event order.
The reference-scale harness calls the actual prepare_entry method without a
client, runtime, account or apply route. Its selection gate is fixture input
because selection parity was reviewed separately. Production code/caps are
neither patched nor relaxed by the uncapped reference-scale fixture.
"""
import argparse
from datetime import date
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_lab import alpaca_monthly_native_binding_v1 as candidate
from research_lab.alpaca_monthly_binding_v1 import CONTRACT,monthly_picks
from research_lab.alpaca_strategy_parity_v1 import source_pins,REFERENCE_CORE
from scripts.alpaca_adaptive_paper import prepare_intended_report
from scripts.equities_alpaca_paper_bridge import _monthly_notional_wire


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def compile_notional(cash,open_equity,weight,*,capital_ceiling):
    """Invoke production sizing code, not a copy of its formula.

    Deliberately no MonthlyNativeBinding constructor/client/dispatch in this
    offline fixture. The real constructor still rejects capital above487.42.
    Only selector/source checks already covered elsewhere are fixture inputs.
    """
    pick=dict(symbol='SIZE_FIXTURE',atr20=1.,signal_close=10.,weight=weight)
    sealed=dict(selection_id='a'*64,picks=[pick],calendar=[],signal_session='2026-10-30',
        entry_session='2026-11-02',source_available_ms=1,causal_history_sha256='b'*64)
    gate=dict(status='ENTRY_PARITY_CANDIDATE',selection=[pick],weight=weight,atr20=1.,
        causal_history_sha256=sealed['causal_history_sha256'])
    fixture=SimpleNamespace(capital=float('inf') if capital_ceiling is None else capital_ceiling,
        book=SimpleNamespace(monthly_actions=lambda *args,**kw:dict(new_symbols=[pick['symbol']])),
        _selection=lambda key:sealed)
    with patch.object(candidate.baseline,'entry_gate',return_value=gate):
        out=candidate.MonthlyNativeBinding.prepare_entry(fixture,{},sealed['selection_id'],pick['symbol'],
            quote={},now_ms=1,cash=cash,open_equity=open_equity)
    if out['status']!='MONTHLY_NATIVE_ENTRY_PREPARED_ORDERS_OFF':raise ValueError('SIZING_FIXTURE_BLOCKED')
    return out['notional']


def run(reference,data):
    reference=Path(reference);data=Path(data);source_pins()
    code_names=('research_lab/alpaca_monthly_native_binding_v1.py','scripts/equities_alpaca_paper_bridge.py',
        'scripts/audit_alpaca_monthly_sizing_v1.py')
    pins={n:sha(ROOT/n) for n in code_names}
    manifest=json.loads((reference/'claude-ETALON.json').read_text())
    trades=json.loads((reference/'claude-sdelki.json').read_text())
    decisions=json.loads((reference/'claude-resheniya.json').read_text())
    from scripts.replay_alpaca_baseline_parity_v1 import core
    if hashlib.sha256(json.dumps(core(trades)).encode()).hexdigest()[:16]!=REFERENCE_CORE:
        raise ValueError('REFERENCE_TRADE_CORE_CONFLICT')
    h=hashlib.sha256();files=sorted(data.glob('*_M5.csv'))
    for p in files:h.update(p.name.encode());h.update(sha(p).encode())
    if len(files)!=59 or h.hexdigest()!=manifest['universe']['sha256']:raise ValueError('UNIVERSE_CONFLICT')
    loader_path=reference/'research_lab/alpaca_dannye.py'
    if sha(loader_path)!=manifest['code_sha256']['research_lab/alpaca_dannye.py']:raise ValueError('LOADER_CONFLICT')
    spec=importlib.util.spec_from_file_location('sealed_sizing_loader',loader_path)
    loader=importlib.util.module_from_spec(spec);sys.modules[spec.name]=loader;spec.loader.exec_module(loader)
    raw,_=loader.chasovye(data);history=loader.v_dnevnye(raw)
    bars={s:{str(b.session_date):b for b in rows} for s,rows in history.items()}
    by_entry={(t['entry_session'],t['symbol']):t for t in trades}
    by_exit={};by_day={d['entry_session']:d for d in decisions}
    for t in trades:by_exit.setdefault(t['exit_session'],[]).append(t)
    cash=float(manifest['params']['initial_capital']);positions={};comparisons=[];opened=0;closed=0
    cap_checks=[];retained=0;sequential_cash=0;selections=0
    maximum=dict(notional_error=0.,qty_error=0.,wire_notional_error=0.,wire_qty_error=0.)
    def settle(t):
        nonlocal cash,closed
        p=positions.pop(t['symbol'])
        if p['entry_session']!=t['entry_session']:raise ValueError('LIFECYCLE_SOURCE_CONFLICT')
        # Independently computed quantity, never the archived expected quantity.
        cash+=p['qty']*t['exit_fill'];closed+=1
    last=None
    for d in (b.session_date for b in history['SPY']):
        if not date(2024,8,1)<=d<date(2026,7,11):continue
        day=str(d);last=day
        for t in sorted(by_exit.get(day,[]),key=lambda t:t['symbol']):
            if t['reason']=='monthly_rotation_next_open':settle(t)
        decision=by_day.get(day)
        if decision:
            report=prepare_intended_report(history,signal_session=date.fromisoformat(decision['signal_session']),entry_session=d)
            picks=monthly_picks(report['picks']);selections+=1
            if sorted(p['symbol'] for p in picks)!=sorted(decision['selected']):raise ValueError('SELECTION_SOURCE_CONFLICT')
            equity=cash+sum(p['qty']*bars[s][day].open for s,p in positions.items())
            retained+=len(positions)
            bought=[];prior_cash=cash
            for p in picks:
                symbol=p['symbol']
                if symbol not in decision['bought']:continue
                if symbol in positions:raise ValueError('ARCHIVED_BUY_ALREADY_HELD')
                notional=compile_notional(cash,equity,p['weight'],capital_ceiling=None)
                fill=bars[symbol][day].open*1.001;qty=notional/fill
                wire=_monthly_notional_wire(notional);wire_qty=float(Decimal(wire)/Decimal(str(fill)))
                if Decimal(wire)>Decimal(str(notional)):raise ValueError('WIRE_NOTIONAL_ROUNDED_UP')
                capped=compile_notional(cash,equity,p['weight'],capital_ceiling=float(CONTRACT['capital_ceiling_usd']))
                expected_cap=min(cash,min(equity,487.42)*.70*p['weight'])
                if abs(capped-expected_cap)>1e-9:raise ValueError('PRODUCTION_CEILING_CONFLICT')
                cap_checks.append(dict(entry_session=day,symbol=symbol,production_notional=capped))
                expected=by_entry.get((day,symbol))
                if expected:
                    expected_notional=expected['entry_fill']*expected['qty']
                    errors=dict(notional_error=abs(notional-expected_notional),qty_error=abs(qty-expected['qty']),
                        wire_notional_error=abs(float(wire)-notional),wire_qty_error=abs(wire_qty-expected['qty']))
                    if abs(fill-expected['entry_fill'])>1e-9 or any(v>1e-9 for v in errors.values()):
                        raise ValueError('SIZING_PARITY_MISMATCH:'+json.dumps(dict(day=day,symbol=symbol,errors=errors)))
                    for key in maximum:maximum[key]=max(maximum[key],errors[key])
                    comparisons.append(dict(entry_session=day,symbol=symbol,cash_before=cash,open_equity=equity,
                        weight=p['weight'],notional=notional,qty=qty,wire_notional=wire,errors=errors))
                positions[symbol]=dict(entry_session=day,qty=qty,entry_fill=fill)
                cash-=qty*fill;opened+=1;bought.append(symbol)
                if cash<prior_cash:sequential_cash+=1
                prior_cash=cash
            if sorted(bought)!=sorted(decision['bought']):raise ValueError('ARCHIVED_BUY_SET_CONFLICT')
        for t in by_exit.get(day,[]):
            if t['reason']!='monthly_rotation_next_open':settle(t)
    equity=cash+sum(p['qty']*bars[s][last].close for s,p in positions.items())
    if len(comparisons)!=64 or closed!=64 or opened!=66 or abs(equity-manifest['summary']['final_equity'])>1e-9:
        raise ValueError('REFERENCE_CASH_CURVE_CONFLICT')
    if pins!={n:sha(ROOT/n) for n in code_names}:raise ValueError('CODE_CHANGED_DURING_AUDIT')
    return dict(schema='ALPACA_MONTHLY_SIZING_PARITY_AUDIT_V1',status='ALPACA_MONTHLY_SIZING_PARITY_PASS',
        orders_allowed=False,money_authority=False,broker_calls=0,production_changes=0,
        source_code_sha256=pins,source_universe_sha256=h.hexdigest(),reference_core_sha16=REFERENCE_CORE,
        input_sha256={n:sha(reference/n) for n in ('claude-ETALON.json','claude-sdelki.json','claude-resheniya.json')},
        compared_closed_entries=len(comparisons),all_entries_computed=opened,closed_lifecycles=closed,
        monthly_selections=selections,retained_position_marks=retained,sequential_cash_debits=sequential_cash,
        production_ceiling_cases=len(cap_checks),production_capital_ceiling_usd=CONTRACT['capital_ceiling_usd'],
        numeric_tolerance=1e-9,maximum_absolute_errors=maximum,remaining_symbols=sorted(positions),
        reference_final_equity_error=abs(equity-manifest['summary']['final_equity']),comparisons=comparisons,
        reference_scale_fixture='Initial cash1000; no production constructor/client/runtime; selection gates supplied as reviewed fixtures. prepare_entry itself computes every notional. Live ceiling487.42 remains enforced.',
        limitation='Known exit dates/fills are sealed inputs, not independent exit/edge evidence or predictions of actual future broker fills. No simulator/outcome judge invoked.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=run(a.reference,a.data)
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:out[k] for k in ('status','compared_closed_entries','all_entries_computed','maximum_absolute_errors','reference_final_equity_error')}))


if __name__=='__main__':main()
