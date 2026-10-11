"""Synthetic counterexamples: legacy risk-zero writer is not the new F1 protocol.

These document promotion limits without modifying an existing writer or reading
prospective outcomes. They deliberately do not assert research KEEP/KILL.
"""
import json
from bot.strategy_shadow_ledger import StrategyShadowLedger
from strategies.signals import TradeSignal


def signal():
    return TradeSignal(strategy='alt_support_bounce_v1',symbol='BTCUSDT',side='long',
        entry=100,sl=98,tp=104,tps=[102,104],tp_fracs=[.15,.85],time_stop_bars=576)


def ledger(tmp_path):
    return StrategyShadowLedger(tmp_path/'state.json',tmp_path/'ledger.jsonl',
                                strategy='alt_support_bounce_v1')


def events(tmp_path):
    return [json.loads(x) for x in (tmp_path/'ledger.jsonl').read_text().splitlines()]


def test_fill_after_boundary_uses_late_received_price_not_exact_bar_open(tmp_path):
    x=ledger(tmp_path)
    assert x.record_signal(signal(),decision_ts_ms=310000)
    # Actual next M5 open is at 600000; a first observation 30s later can differ.
    x.on_price('BTCUSDT',101,ts_ms=630000)
    fill=next(e for e in events(tmp_path) if e['event']=='fill')
    assert fill['fill_after_ms']==600000
    assert fill['fill_ts_ms']==630000
    assert fill['fill_price']==101*(1+2/10000)


def test_ohlc_stop_touch_between_ticks_is_not_observed_by_legacy_writer(tmp_path):
    x=ledger(tmp_path)
    assert x.record_signal(signal(),decision_ts_ms=310000)
    x.on_price('BTCUSDT',100,ts_ms=600000)
    # A bar with low 97 and high 104 touches both SL and TP. OHLC baseline's
    # stop-first rule would exit SL; ticker-only writer cannot see that low.
    x.on_price('BTCUSDT',104.1,ts_ms=900000)
    close=next(e for e in events(tmp_path) if e['event']=='close')
    assert close['close_reason']=='targets'
    assert 'funding' not in close and 'source_hash' not in close and 'config_hash' not in close


def test_corrupt_legacy_state_resets_without_preserving_pending_identity(tmp_path):
    x=ledger(tmp_path)
    assert x.record_signal(signal(),decision_ts_ms=310000)
    (tmp_path/'state.json').write_text('{corrupt')
    reopened=ledger(tmp_path)
    assert reopened.snapshot()['pending']=={}
    assert reopened.record_signal(signal(),decision_ts_ms=310000)
    ds=[e for e in events(tmp_path) if e['event']=='decision']
    assert len(ds)==2 and ds[0]['signal_id']==ds[1]['signal_id']


def test_closed_unit_is_signal_id_not_legacy_web_decision_id(tmp_path):
    x=ledger(tmp_path)
    assert x.record_signal(signal(),decision_ts_ms=310000)
    x.on_price('BTCUSDT',100,ts_ms=600000)
    x.on_price('BTCUSDT',97,ts_ms=900000)
    close=next(e for e in events(tmp_path) if e['event']=='close')
    assert close['signal_id'] and 'decision_id' not in close
