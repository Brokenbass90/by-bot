"""Transport-free monthly/daily baseline candidate. Never an order dispatcher.

The existing Dynamic/NET manager is deliberately not imported or modified.
Calendar, bars and quote are caller-provided evidence, not authenticated truth.
This module does not install a schedule, grant money authority or release HALT.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

from backtest.alpaca_honest_portfolio import quantize_sell_stop
from research_lab.alpaca_dynamic_v1 import digest, instant, positive
from scripts.alpaca_adaptive_paper import prepare_intended_report


REFERENCE_COMMIT = '2e68b1f5ba6d2767c2144c5dafd8f10a6d2908c6'
REFERENCE_CORE = '2347a7ec606cd845'
REFERENCE_FILES = {
    'backtest/alpaca_honest_portfolio.py': '21c83fe9bff1659990a869a40bd2f62b8f8c3a359f88d4b398291b4096f978b8',
    'backtest/alpaca_exact_parity_contract.py': '366ced46e1625f978ea853536a3d5a3dc65083b2af4378f9291867309b539f50',
    'backtest/alpaca_bakeoff_v2_contract.py': 'd2a69eb34d4dd2ee823142888d16708c24360a5e619b912ae4e7f25505151fee',
    'strategies/alpaca_dynamic_v4_event.py': 'ca3ca15faf6cc7ca5f1804a24fd4ff5c088064d1cfaced5a37751ab387b8179a',
    'configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json': '7b1022ce47933e1de579ca4ebb950cf84675958ba62c3aee9d8337534ad6b245',
}
ROOT = Path(__file__).resolve().parents[1]


def source_pins():
    for name, expected in REFERENCE_FILES.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('REFERENCE_SOURCE_CONFLICT:'+name)
    # Include the current selector wrapper and this adapter without path-dependent
    # strategy IDs. The independently pinned reference replay checks the wrapper.
    names=[*REFERENCE_FILES,'scripts/alpaca_adaptive_paper.py','research_lab/alpaca_dynamic_v1.py',
           'research_lab/alpaca_strategy_parity_v1.py']
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}


def result(status, **fields):
    return dict(schema='ALPACA_BASELINE_PARITY_CANDIDATE_V1',status=status,
        orders_allowed=False,money_authority=False,live_deployed=False,**fields)


def _calendar(calendar):
    previous=None
    for row in calendar:
        session=date.fromisoformat(row['session'])
        start,end=instant(row['open_ms']),instant(row['close_ms'])
        if start>=end or datetime.fromtimestamp(start/1000,timezone.utc).date()!=session:
            raise ValueError('INVALID_CALENDAR')
        if previous and (previous['session']>=row['session'] or previous['close_ms']>=start):
            raise ValueError('INVALID_CALENDAR')
        previous=row
    if not previous:
        raise ValueError('MISSING_CALENDAR')


def initial_stop(entry_fill, atr20):
    """Exact reference float expression and downward price grid, no old distance."""
    fill,atr=float(positive(entry_fill)),float(positive(atr20))
    stop=fill-2.0*atr
    return quantize_sell_stop(stop if stop>0 else fill*(1.0-.05))


def entry_gate(history,calendar,*,signal_session,intended_entry_session,
               entry_session,symbol,history_available_ms,quote,now_ms):
    """Confirm the original symbol only in its monthly next-session window.

    This is a source-bound orders-OFF preview. Account, custody, caps and dispatch
    gates remain the responsibility of the existing execution owner; this receipt
    alone is never usable as an execution permit.
    """
    try:
        _calendar(calendar);now=instant(now_ms)
        actual=next((r for r in calendar if r['session']==entry_session),None)
        signal=next((r for r in calendar if r['session']==signal_session),None)
        previous=[r for r in calendar if actual and r['close_ms']<actual['open_ms']]
        monthly=(signal and actual and previous and previous[-1]['session']==signal_session
                 and signal_session[:7]!=entry_session[:7])
        if (not monthly or intended_entry_session!=entry_session
            or not actual['open_ms']<=now<actual['open_ms']+300000):
            return result('NO_SEND',reason='STALE_SIGNAL_RESELECT_FAIL')
        if not signal['close_ms']<=instant(history_available_ms)<=now:
            raise ValueError('ATR_SELECTION_SOURCE_TIME_UNKNOWN')
        cts,received=instant(quote['quote_ts']),instant(quote['received_ms'])
        if not cts<=received<=now or now-cts>300000:
            raise ValueError('QUOTE_CTS_STALE_OR_FUTURE')
        if not isinstance(quote['source'],str) or not quote['source'].strip():
            raise ValueError('QUOTE_SOURCE_UNKNOWN')
        positive(quote['ask'])
        source=source_pins()
        selection=prepare_intended_report(history,signal_session=date.fromisoformat(signal_session),
            entry_session=date.fromisoformat(entry_session))
        chosen=[p for p in selection['picks'] if p['symbol']==symbol]
        if not selection['gate_ok'] or len(chosen)!=1:
            return result('NO_SEND',reason='STALE_SIGNAL_RESELECT_FAIL',
                          revalidation_result='ORIGINAL_SYMBOL_REJECTED')
        chosen=chosen[0];atr=float(positive(chosen['atr20']))
        causal={s:[{**asdict(b),'session_date':b.session_date.isoformat()}
                   for b in bars if b.session_date<=date.fromisoformat(signal_session)]
                for s,bars in history.items()}
        out=result('ENTRY_PARITY_CANDIDATE',reference_commit=REFERENCE_COMMIT,
            reference_trades_core_sha16=REFERENCE_CORE,signal_session=signal_session,
            intended_entry_session=intended_entry_session,entry_session=entry_session,
            signal_at=signal['close_ms'],intended_entry_at=actual['open_ms'],
            signal_age_ms=now-signal['close_ms'],revalidation_result='ORIGINAL_SYMBOL_CONFIRMED',
            selection=selection['picks'],symbol=symbol,atr20=atr,atr20_session=signal_session,
            raw_stop_distance=2.0*atr,signal_close=chosen['signal_close'],weight=chosen['weight'],
            quote_ts=cts,quote_source=quote['source'],quote_sha256=digest(quote),
            history_available_ms=history_available_ms,causal_history_sha256=digest(causal),
            calendar_sha256=digest(calendar),source_sha256=source,
            selection_cadence='MONTH_END_NEXT_OPEN',ratchet_cadence='COMPLETED_DAILY_CLOSE_NEXT_SESSION')
        out['receipt_sha256']=digest(out)
        return out
    except (KeyError,ValueError,TypeError,ArithmeticError,OSError) as exc:
        return result('BLOCKED_DATA',reason=str(exc))


def fill_receipt(gate,raw_entry):
    if digest({k:v for k,v in gate.items() if k!='receipt_sha256'})!=gate.get('receipt_sha256'):
        raise ValueError('ENTRY_GATE_HASH_CONFLICT')
    if gate['status']!='ENTRY_PARITY_CANDIDATE' or gate['orders_allowed'] is not False:
        raise ValueError('INVALID_ENTRY_GATE')
    if raw_entry['symbol']!=gate['symbol']:
        raise ValueError('FILL_SYMBOL_CONFLICT')
    if (not raw_entry['id'] or raw_entry['side']!='buy' or raw_entry['type']!='limit'
        or raw_entry['status']!='filled'):
        raise ValueError('FILL_IDENTITY_CONFLICT')
    fill=float(positive(raw_entry['filled_avg_price']));qty=float(positive(raw_entry['filled_qty']))
    timestamp=datetime.fromisoformat(raw_entry['filled_at'].replace('Z','+00:00'))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError('FILL_TIMESTAMP_TIMEZONE_UNKNOWN')
    actual=int(timestamp.timestamp()*1000)
    if not gate['intended_entry_at']<=actual<gate['intended_entry_at']+300000:
        raise ValueError('FILL_OUTSIDE_INTENDED_SESSION_WINDOW')
    stop=initial_stop(fill,gate['atr20'])
    out=result('FILL_PARITY_RECEIPT',entry_gate_sha256=gate['receipt_sha256'],
        symbol=gate['symbol'],order_id=raw_entry['id'],raw_execution_sha256=digest(raw_entry),
        signal_at=gate['signal_at'],intended_entry_at=gate['intended_entry_at'],
        actual_entry_at=actual,signal_age_ms=actual-gate['signal_at'],
        atr20=gate['atr20'],atr20_session=gate['atr20_session'],actual_fill=fill,qty=qty,
        stop_price=stop,stop_distance=fill-stop,quote_ts=gate['quote_ts'],quote_source=gate['quote_source'],
        source_sha256=gate['source_sha256'])
    out['receipt_sha256']=digest(out)
    return out


def initial_state(symbol,entry_fill,atr20,entry_session):
    fill=float(positive(entry_fill));date.fromisoformat(entry_session)
    return dict(symbol=symbol,entry_fill=fill,entry_session=entry_session,
                active_stop=initial_stop(fill,atr20),hwm=fill,last_observed_session=None,
                last_bar_sha256=None)


def daily_transition(state,bar,calendar,now_ms):
    """Pure daily-proxy transition; not an instruction to retrospectively trade.

    A stop raised here is effective NEXT session. A 5min health tick cannot
    consume an unfinished daily close. Broker protection/re-arm is a separate
    existing safety path and is not implemented or called by this module.
    """
    _calendar(calendar);now=instant(now_ms);s=deepcopy(state)
    day=bar['session'];row=next((r for r in calendar if r['session']==day),None)
    if row is None:
        raise ValueError('DAILY_SESSION_UNKNOWN')
    if now<row['close_ms']:
        return result('NOT_DUE',state=s)
    o,h,l,c=(float(positive(bar[k])) for k in ('open','high','low','close'))
    if not l<=min(o,c)<=max(o,c)<=h or day<s['entry_session']:
        raise ValueError('INVALID_DAILY_BAR')
    last=s['last_observed_session'];bar_sha=digest(bar)
    if last and day<last:
        raise ValueError('STALE_DAILY_BAR')
    if last==day:
        if s['last_bar_sha256']!=bar_sha:
            raise ValueError('DAILY_BAR_CONFLICT')
        return result('ALREADY_OBSERVED',state=s)
    # Omitting a held session could omit a stop exit. Require contiguous
    # authoritative calendar observations after the entry session.
    previous=[r['session'] for r in calendar if s['entry_session']<=r['session']<day]
    if previous and last!=previous[-1]:
        raise ValueError('MISSING_DAILY_OBSERVATION')
    stop=float(positive(s['active_stop']));entry=float(positive(s['entry_fill']))
    if o<=stop:
        reason='entry_gap_below_signal_stop' if day==s['entry_session'] else 'protective_stop_gap_open'
        return result('REFERENCE_STOP_EXIT',exit_reason=reason,exit_reference=o,state=s)
    if l<=stop:
        return result('REFERENCE_STOP_EXIT',exit_reason='protective_stop_intraday',exit_reference=stop,state=s)
    hwm=max(float(positive(s['hwm'])),c)
    if (hwm/entry-1.0)*100.0+1e-12>=3.5:
        target=min(max(stop,hwm*(1.0-3.5/100.0),entry*(1.0+.5/100.0)),c*(1.0-10.0/10000.0))
        if target>stop:
            stop=quantize_sell_stop(target)
    s.update(active_stop=stop,hwm=hwm,last_observed_session=day,last_bar_sha256=bar_sha)
    following=next((r['session'] for r in calendar if r['session']>day),None)
    if following is None:
        raise ValueError('NEXT_SESSION_UNKNOWN')
    return result('DAILY_CLOSE_OBSERVED',state=s,stop_effective_session=following)
