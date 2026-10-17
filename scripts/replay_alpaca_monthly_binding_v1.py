#!/usr/bin/env python3
"""Replay the durable production book against SEALED baseline events.

Does not call the baseline portfolio simulator or reconstruct its 64-trade
backtest. Archived broker-like entry fills/quantities are exogenous inputs;
selection, retention/rotation, stop exits, ratchets and restart state are
computed through the candidate book. This is no new research/outcome attempt.
"""
import argparse
from datetime import date,datetime,time,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_lab.alpaca_monthly_binding_v1 import CONTRACT,MonthlyBook,entry_cid
from research_lab.alpaca_strategy_parity_v1 import REFERENCE_CORE,initial_stop,source_pins
from research_lab.alpaca_dynamic_v1 import digest
from scripts.alpaca_adaptive_paper import prepare_intended_report
from scripts.equities_alpaca_paper_bridge import _persistent_exit_tif_for_qty


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(reference,data):
    reference=Path(reference);data=Path(data);source_pins()
    code_names=('research_lab/alpaca_monthly_binding_v1.py','research_lab/alpaca_monthly_native_binding_v1.py',
        'scripts/equities_alpaca_paper_bridge.py','scripts/replay_alpaca_monthly_binding_v1.py')
    replay_code_sha256={n:sha(ROOT/n) for n in code_names}
    manifest=json.loads((reference/'claude-ETALON.json').read_text())
    expected=json.loads((reference/'claude-sdelki.json').read_text())
    decisions=json.loads((reference/'claude-resheniya.json').read_text())
    from scripts.replay_alpaca_baseline_parity_v1 import core
    if hashlib.sha256(json.dumps(core(expected)).encode()).hexdigest()[:16]!=REFERENCE_CORE:
        raise ValueError('SEALED_TRADE_CORE_CONFLICT')
    h=hashlib.sha256();files=sorted(data.glob('*_M5.csv'))
    for f in files:h.update(f.name.encode());h.update(sha(f).encode())
    if len(files)!=59 or h.hexdigest()!=manifest['universe']['sha256']:raise ValueError('UNIVERSE_CONFLICT')
    path=reference/'research_lab/alpaca_dannye.py'
    if sha(path)!=manifest['code_sha256']['research_lab/alpaca_dannye.py']:raise ValueError('LOADER_CONFLICT')
    spec=importlib.util.spec_from_file_location('sealed_monthly_source_loader',path)
    loader=importlib.util.module_from_spec(spec);sys.modules[spec.name]=loader;spec.loader.exec_module(loader)
    hourly,_=loader.chasovye(data);history=loader.v_dnevnye(hourly)
    bars={s:{str(b.session_date):b for b in rows} for s,rows in history.items()}
    dates=[b.session_date for b in history['SPY']]
    def ms(d,h,m=0):return int(datetime.combine(d,time(h,m),ZoneInfo('America/New_York')).timestamp()*1000)
    # Session labels are the SAME recorded baseline labels. Intraday execution
    # clock is a replay fixture, not a purported official historical calendar.
    calendar=[dict(session=str(d),open_ms=ms(d,9,30),close_ms=ms(d,16)) for d in dates]
    starts={d['entry_session']:d for d in decisions};entries={};seen=[];checks=dict(
        selections=0,initial_stops=0,daily_closes=0,stop_acks=0,stop_exits=0,rotations=0,
        retained=0,cooldown_decisions=0,restarts=0)
    completed=[];deferred=[];survivors=[]
    for t in expected:entries.setdefault((t['entry_session'],t['symbol']),t)
    with tempfile.TemporaryDirectory(prefix='alpaca-monthly-replay-') as tmp:
        path=Path(tmp).resolve()/'monthly.sqlite';book=MonthlyBook(path,CONTRACT)
        for day in dates:
            ds=str(day)
            if not date(2024,8,1)<=day<=date(2026,7,10):continue
            now=ms(day,9,30)
            # Activate only previously published next-session intentions.
            for a in book.stop_actions(now_ms=now)['actions']:
                stop=dict(id='ratchet-'+a['action_id'],client_order_id=a['client_order_id'],
                    symbol=a['symbol'],side='sell',type='stop',status='new',qty=a['qty'],filled_qty='0',
                    stop_price=str(a['stop_price']),time_in_force=_persistent_exit_tif_for_qty('',float(a['qty'])),
                    replaces=a['prior_stop_id'])
                book.confirm_stop(a['action_id'],stop,observed_ms=now);checks['stop_acks']+=1
            decision=starts.get(ds)
            if decision:
                signal=decision['signal_session'];available=ms(date.fromisoformat(signal),16)+1000
                selection=book.seal_selection(history,calendar,signal_session=signal,entry_session=ds,
                    source_available_ms=available,source_sha256=digest(dict(universe=h.hexdigest(),signal=signal)),
                    now_ms=available)
                if sorted(p['symbol'] for p in selection['picks'])!=sorted(decision['selected']):
                    raise ValueError('MONTHLY_SELECTION_MISMATCH:'+ds)
                checks['selections']+=1;plan=book.monthly_actions(selection['selection_id'],now_ms=now)
                checks['retained']+=len(plan['retain'])
                for a in plan['rotation_intentions']:
                    p=next(p for p in book.rows('positions') if p['symbol']==a['symbol'])
                    b=bars[a['symbol']][ds];fill=b.open*.999
                    order=dict(id='rotation-'+a['client_order_id'],client_order_id=a['client_order_id'],
                        symbol=a['symbol'],side='sell',type='market',qty=p['qty'],filled_qty=p['qty'],
                        filled_avg_price=str(fill),status='filled',filled_at=datetime.fromtimestamp(now/1000,timezone.utc).isoformat())
                    out=book.record_exit(a['symbol'],[order],reason='monthly_rotation_next_open',
                        observed_ms=now,remaining_qty='0',open_order_ids=[])
                    completed.append((p,ds,fill,out['reason']));checks['rotations']+=1
                plan=book.monthly_actions(selection['selection_id'],now_ms=now)
                if sorted(plan['new_symbols'])!=sorted(decision['bought']):raise ValueError('ADMISSION_MISMATCH:'+ds)
                selected_symbols={p['symbol'] for p in selection['picks']}
                if sorted(s for s in plan['cooldown_symbols'] if s in selected_symbols)!=sorted(decision['reentry_blocked']):
                    raise ValueError('COOLDOWN_MISMATCH:'+ds)
                checks['cooldown_decisions']+=1
                for symbol in plan['new_symbols']:
                    p=next(p for p in selection['picks'] if p['symbol']==symbol)
                    retained=entries.get((ds,symbol));b=bars[symbol][ds]
                    fill=b.open*1.001
                    if retained and abs(fill-retained['entry_fill'])>1e-9:raise ValueError('ENTRY_FILL_SOURCE_CONFLICT')
                    qty=str(retained['qty']) if retained else '1'
                    if not retained:survivors.append(dict(symbol=symbol,entry_session=ds,qty='fixture_not_size_proof'))
                    entry=dict(id='entry-'+ds+'-'+symbol,client_order_id=entry_cid(selection,symbol),
                        symbol=symbol,side='buy',type='market',status='filled',qty=qty,filled_qty=qty,
                        filled_avg_price=str(fill),filled_at=datetime.fromtimestamp(now/1000,timezone.utc).isoformat(),time_in_force='day')
                    stop=dict(id='stop-'+ds+'-'+symbol,symbol=symbol,side='sell',type='stop',status='new',
                        qty=qty,filled_qty='0',stop_price=str(initial_stop(fill,p['atr20'])),time_in_force='day')
                    # Integer fixture survivor sizes require the broker's whole
                    # share GTC; fractional actual sealed fills use DAY.
                    stop['time_in_force']=_persistent_exit_tif_for_qty('',float(qty))
                    book.bind_fill(selection['selection_id'],entry,stop);checks['initial_stops']+=1
            raw=[]
            for p in book.rows('positions'):
                b=bars[p['symbol']][ds];floor=p['daily_state']['active_stop']
                gap=b.open<=floor;hit=b.low<=floor
                if gap or hit:
                    reason='protective_stop_gap_open' if gap else 'protective_stop_intraday'
                    fill=(b.open if gap else floor)*.999
                    o=dict(id=p['native_stop_id'],symbol=p['symbol'],side='sell',type='stop',status='filled',
                        qty=p['qty'],filled_qty=p['qty'],filled_avg_price=str(fill),
                        filled_at=datetime.fromtimestamp((now+1000)/1000,timezone.utc).isoformat())
                    out=book.record_exit(p['symbol'],[o],reason=reason,observed_ms=now+1000,
                        remaining_qty='0',open_order_ids=[])
                    completed.append((p,ds,fill,out['reason']));checks['stop_exits']+=1
                else:raw.append(dict(symbol=p['symbol'],session=ds,open=b.open,high=b.high,low=b.low,close=b.close))
            if raw and day!=dates[-1]:
                close=ms(day,16);source=dict(schema='ALPACA_COMPLETED_SESSION_SOURCE_V1',
                    source='RECORDED_REGULAR_SESSION_OHLC',raw=raw,raw_sha256=digest(raw),calendar=calendar,
                    available_ms=close,completed_ms=close)
                book.observe_close(source,now_ms=close);checks['daily_closes']+=len(raw)
            elif raw:deferred.extend(dict(symbol=r['symbol'],session=ds) for r in raw)
            before=book.rows('positions');book=MonthlyBook(path,CONTRACT)
            if before!=book.rows('positions'):raise ValueError('RESTART_STATE_MISMATCH')
            checks['restarts']+=1
        actual=[]
        for p,ds,fill,reason in completed:
            actual.append(dict(symbol=p['symbol'],entry_session=p['daily_state']['entry_session'],exit_session=ds,
                entry_fill=p['daily_state']['entry_fill'],exit_fill=fill,qty=float(p['qty']),reason=reason))
        if sorted(core(actual))!=sorted(core(expected)):raise ValueError('PRODUCTION_BOOK_TRADE_CORE_MISMATCH')
        remaining=[p['symbol'] for p in book.rows('positions')]
    if replay_code_sha256!={n:sha(ROOT/n) for n in code_names}:raise ValueError('REPLAY_CODE_CHANGED_DURING_RUN')
    return dict(status='ALPACA_MONTHLY_DURABLE_BOOK_REPLAY_PASS',orders_allowed=False,money_authority=False,
        reference_trades_core_sha16=REFERENCE_CORE,trades_compared=len(actual),checks=checks,
        replay_code_sha256=replay_code_sha256,universe_sha256=h.hexdigest(),input_hashes={n:sha(reference/n) for n in
            ('claude-ETALON.json','claude-sdelki.json','claude-resheniya.json')},
        remaining=remaining,final_close_without_future_calendar=deferred,unclosed_fixture_sizes=survivors,
        coverage='Durable source/book + actual native-path tests separately. Archived entry quantities are inputs, not an independent sizing/accounting reconstruction.',
        calendar_scope='Recorded baseline sessions; replay intraday clock is a fixture. Broker calendar normalization/DST/half-day verified separately.',
        backtest_simulator_calls=0,broker_calls=0)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--data',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();out=run(a.reference,a.data)
    with a.output.open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:out[k] for k in ('status','trades_compared','checks')}))


if __name__=='__main__':main()
