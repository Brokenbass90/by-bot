import json

from bot.strategy_shadow_ledger import StrategyShadowLedger
from strategies.signals import TradeSignal


def _signal() -> TradeSignal:
    return TradeSignal(
        strategy="alt_support_bounce_v1",
        symbol="BTCUSDT",
        side="long",
        entry=100.0,
        sl=98.0,
        tp=104.0,
        tps=[102.0, 104.0],
        tp_fracs=[0.25, 0.75],
        time_stop_bars=12,
        reason="test",
    )


def test_shadow_lifecycle_is_next_grid_risk_zero_and_restart_safe(tmp_path):
    state = tmp_path / "state.json"
    ledger = tmp_path / "ledger.jsonl"
    shadow = StrategyShadowLedger(
        state,
        ledger,
        strategy="alt_support_bounce_v1",
        execution_interval_ms=300_000,
        fee_bps_per_side=6.0,
        slippage_bps_per_side=2.0,
    )

    assert shadow.record_signal(_signal(), decision_ts_ms=310_000)
    assert shadow.on_price("BTCUSDT", 100.0, ts_ms=599_999) == []
    assert shadow.on_price("BTCUSDT", 100.0, ts_ms=600_000) == ["fill"]
    assert shadow.on_price("BTCUSDT", 102.1, ts_ms=900_000) == ["target:0"]
    assert shadow.on_price("BTCUSDT", 97.9, ts_ms=1_200_000) == ["close:stop"]

    snapshot = shadow.snapshot()
    assert snapshot["broker_calls"] is False
    assert snapshot["closed_count"] == 1
    assert snapshot["pending"] == {}
    assert snapshot["open"] == {}

    restarted = StrategyShadowLedger(
        state,
        ledger,
        strategy="alt_support_bounce_v1",
    )
    assert restarted.snapshot()["closed_count"] == 1
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [row["event"] for row in rows] == ["decision", "fill", "target", "close"]
    assert all(row["broker_calls"] is False for row in rows)


def test_duplicate_or_overlapping_signal_is_rejected(tmp_path):
    shadow = StrategyShadowLedger(
        tmp_path / "state.json",
        tmp_path / "ledger.jsonl",
        strategy="alt_support_bounce_v1",
    )
    signal = _signal()
    assert shadow.record_signal(signal, decision_ts_ms=310_000)
    assert not shadow.record_signal(signal, decision_ts_ms=310_000)
    assert not shadow.record_signal(signal, decision_ts_ms=320_000)
