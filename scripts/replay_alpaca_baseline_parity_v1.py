#!/usr/bin/env python3
"""Reproduce the supplied baseline and compare its states to the OFF candidate.

No broker, new research variant, order permit, service or production state.
Output is create-exclusive. Inputs are the archived exact reference, its published
manifest/trades, and the already used 59-file historical universe.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import alpaca_honest_portfolio as hp
from research_lab import alpaca_strategy_parity_v1 as candidate
from scripts.alpaca_adaptive_paper import prepare_intended_report
from scripts.run_alpaca_honest_diagnostic import _decisions


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def core(trades):
    return [(t['symbol'],t['entry_session'],t['exit_session'],round(t['entry_fill'],9),
             round(t['exit_fill'],9),round(t['qty'],9),t['reason']) for t in trades]


def run(reference,data):
    reference=Path(reference);data=Path(data)
    manifest=json.loads((reference/'claude-ETALON.json').read_bytes())
    expected=json.loads((reference/'claude-sdelki.json').read_bytes())
    for name,value in {**manifest['code_sha256'],**manifest['config_sha256']}.items():
        if sha(reference/name)!=value:
            raise ValueError('REFERENCE_PIN_MISMATCH:'+name)
    candidate.source_pins()
    # The local runner/selector must be the actual archived validated ones.
    for name in ('backtest/alpaca_honest_portfolio.py','backtest/alpaca_exact_parity_contract.py',
                 'backtest/alpaca_bakeoff_v2_contract.py','scripts/run_alpaca_honest_diagnostic.py',
                 'strategies/alpaca_dynamic_v4_event.py'):
        if sha(ROOT/name)!=manifest['code_sha256'][name]:
            raise ValueError('LOCAL_REFERENCE_DEPENDENCY_DRIFT:'+name)
    files=sorted(data.glob('*_M5.csv'));h=hashlib.sha256()
    for f in files:
        h.update(f.name.encode());h.update(sha(f).encode())
    if len(files)!=59 or h.hexdigest()!=manifest['universe']['sha256']:
        raise ValueError('UNIVERSE_PIN_MISMATCH')
    spec=importlib.util.spec_from_file_location('alpaca_etalon_loader',reference/'research_lab/alpaca_dannye.py')
    loader=importlib.util.module_from_spec(spec);sys.modules[spec.name]=loader;spec.loader.exec_module(loader)
    raw,_=loader.chasovye(data);bars=loader.v_dnevnye(raw)
    sessions=[b.session_date for b in bars['SPY']]
    window=[s for s in sessions if date(2024,8,1)<=s<date(2026,7,11)]
    last={}
    for i,s in enumerate(sessions):last[s.strftime('%Y-%m')]=i
    schedule=[(sessions[i],sessions[i+1]) for i in sorted(last.values())
              if i+1<len(sessions) and date(2024,8,1)<=sessions[i+1]<date(2026,7,11)]
    config=json.loads((reference/'configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json').read_bytes())
    decisions=_decisions('v38_successor_gated',bars,schedule,[set(g) for g in config['clusters']])
    for decision in decisions:
        preview=prepare_intended_report(bars,signal_session=decision.signal_session,
                                        entry_session=decision.entry_session)
        actual=[(p['symbol'],p['weight'],p['atr20'],p['signal_close']) for p in preview['picks']]
        reference_picks=[(p.symbol,p.weight,p.atr_at_signal,p.signal_close) for p in decision.picks]
        if actual!=reference_picks:
            raise ValueError('SELECTOR_PARITY_MISMATCH:'+str(decision.signal_session))
    picks={(d.entry_session,p.symbol):p for d in decisions for p in d.picks}
    # Logical session clock is used ONLY for the replay of historical daily OHLC.
    # It is not a live exchange calendar or a fresh timestamp source.
    def tick(d,hour):return int(datetime(d.year,d.month,d.day,hour,tzinfo=timezone.utc).timestamp()*1000)
    calendar=[dict(session=s.isoformat(),open_ms=tick(s,13),close_ms=tick(s,21)) for s in sessions]
    states={};checks=dict(initial_stops=0,daily_pre_states=0,daily_post_states=0,stop_exits=0)
    skipped_final_close=[];exits={}
    lines,start=inspect.getsourcelines(hp.simulate_live_protection_daily_proxy)
    before=start+next(i for i,l in enumerate(lines) if 'if session == position.entry_session and bar.open' in l)
    after=start+next(i for i,l in enumerate(lines) if l.strip()=='open_value = 0.0')

    def equal(a,b,reason):
        if abs(a-b)>1e-9:raise ValueError(reason+':'+repr((a,b)))

    def trace(frame,event,arg):
        if frame.f_code is hp.simulate_live_protection_daily_proxy.__code__ and event=='line':
            if frame.f_lineno not in (before,after):return trace
            loc=frame.f_locals;session=loc['session']
            if frame.f_lineno==before:
                position=loc['position'];key=(position.entry_session,position.symbol)
                if key not in states:
                    p=picks[key]
                    states[key]=candidate.initial_state(position.symbol,position.entry_fill,p.atr_at_signal,position.entry_session.isoformat())
                    equal(states[key]['active_stop'],position.active_stop,'INITIAL_STOP_PARITY')
                    checks['initial_stops']+=1
                s=states[key]
                equal(s['active_stop'],position.active_stop,'DAILY_PRE_STOP_PARITY')
                equal(s['hwm'],position.hwm,'DAILY_PRE_HWM_PARITY')
                checks['daily_pre_states']+=1
                b=loc['bar'];bar=dict(session=str(session),open=b.open,high=b.high,low=b.low,close=b.close)
                try:r=candidate.daily_transition(s,bar,calendar,tick(session,21))
                except ValueError as exc:
                    if session!=sessions[-1] or str(exc)!='NEXT_SESSION_UNKNOWN':raise
                    # Still check final-day gap/stop exits; only next-session
                    # ratchet publication needs an absent future calendar row.
                    skipped_final_close.append(dict(symbol=position.symbol,session=str(session)))
                    return trace
                if r['status']=='REFERENCE_STOP_EXIT':exits[(session,position.symbol)]=r
                else:states[key]=r['state']
            elif frame.f_lineno==after:
                for symbol,position in loc['positions'].items():
                    if session==sessions[-1]:continue
                    s=states[(position.entry_session,symbol)]
                    equal(s['active_stop'],position.active_stop,'DAILY_POST_STOP_PARITY')
                    equal(s['hwm'],position.hwm,'DAILY_POST_HWM_PARITY')
                    checks['daily_post_states']+=1
        if event=='call' and frame.f_code.co_name=='close_position' and frame.f_code.co_filename==hp.__file__:
            loc=frame.f_locals
            if loc['reason']!='monthly_rotation_next_open':
                r=exits.pop((loc['session'],loc['position'].symbol))
                if r['exit_reason']!=loc['reason']:raise ValueError('STOP_EXIT_REASON_PARITY')
                equal(r['exit_reference'],loc['reference'],'STOP_EXIT_PRICE_PARITY')
                checks['stop_exits']+=1
        return trace if frame.f_code is hp.simulate_live_protection_daily_proxy.__code__ else None

    old=sys.gettrace()
    try:
        sys.settrace(trace)
        replay=hp.simulate_live_protection_daily_proxy(bars,window,decisions,
            initial_capital=1000,target_gross_exposure=.70,cost_bps_per_side=10,
            policy=hp.LiveProtectionDailyProxy(initial_stop_anchor='entry_fill'))
    finally:sys.settrace(old)
    if exits:raise ValueError('UNMATCHED_CANDIDATE_STOP_EXIT')
    actual_core=core(replay['trades']);expected_core=core(expected)
    # Hash is the owner's published rounded core. Also compare each numeric
    # value independently; a matching economic aggregate is not enough.
    core_pin=hashlib.sha256(json.dumps(actual_core).encode()).hexdigest()[:16]
    if core_pin!=candidate.REFERENCE_CORE or actual_core!=expected_core:
        raise ValueError('TRADE_CORE_PARITY_MISMATCH')
    summary={k:v for k,v in replay.items() if not isinstance(v,(list,dict))}
    return dict(schema='ALPACA_BASELINE_CANDIDATE_REPLAY_V1',status='OFFLINE_BASELINE_COMPONENT_PARITY_PASS',
        deployed_live_parity='BLOCKED_DYNAMIC_WEEKLY_INTRADAY',orders_allowed=False,money_authority=False,
        reference_commit=candidate.REFERENCE_COMMIT,reference_research_commit='981b62f7da598df95b0cf265902f28c920929469',
        published_manifest_sha256=sha(reference/'claude-ETALON.json'),
        universe_sha256=h.hexdigest(),universe_files=len(files),source_sha256=candidate.source_pins(),
        replay_script_sha256=sha(__file__),selection_decisions_exact=len(decisions),
        trades_core_sha16=core_pin,trades_compared=len(actual_core),numeric_tolerance=1e-9,
        checks=checks,final_close_not_evaluated_without_next_session=skipped_final_close,
        summary=summary,broker_calls=0,production_changes=0,
        limitation='Component replay; monthly production binding, rotation/retention and independent review remain separate.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference',required=True,type=Path)
    ap.add_argument('--data',required=True,type=Path)
    ap.add_argument('--output',required=True,type=Path)
    a=ap.parse_args();out=run(a.reference,a.data)
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:out[k] for k in ('status','trades_core_sha16','selection_decisions_exact','checks')}))


if __name__=='__main__':main()
