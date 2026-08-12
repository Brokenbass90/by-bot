from __future__ import annotations

import math

import numpy as np

from backtest.engine import Candle
from scripts.collect_inplay_prospective_shadow import HORIZON_BARS, settle_event


def _candles(count: int, *, low: float = 99.5, high: float = 100.5, close: float = 100.0):
    return [Candle(i * 300_000, 100.0, high, low, close, 1.0) for i in range(count)]


def test_settle_event_uses_next_open_and_fixed_horizon_close():
    rows = _candles(HORIZON_BARS + 2, low=99.9, high=100.2, close=100.1)
    rows[1] = Candle(rows[1].ts, 101.0, 101.2, 100.9, 101.1, 1.0)
    atr = np.full(len(rows), 1.0)
    event = {"side": 1, "state": "awaiting_next_open"}
    out = settle_event(event, rows, signal_index=0, atr=atr)
    assert out["entry"] == 101.0
    assert out["entry_ts_ms"] == rows[1].ts
    assert out["exit_reason"] == "fixed_24h_close"
    assert out["exit_ts_ms"] == rows[HORIZON_BARS].ts
    assert out["state"] == "closed"


def test_settle_event_is_stop_first_and_costs_are_subtracted():
    rows = _candles(HORIZON_BARS + 2, low=99.0, high=101.0)
    atr = np.full(len(rows), 0.1)
    risk = 0.75 * math.sqrt(HORIZON_BARS) * 0.1
    rows[1] = Candle(rows[1].ts, 100.0, 102.0, 100.0 - risk - 0.01, 101.0, 1.0)
    out = settle_event({"side": 1}, rows, signal_index=0, atr=atr)
    assert out["exit_reason"] == "stop_first"
    assert out["gross_r"] == -1.0
    assert out["net_r"] < -1.0


def test_settle_event_remains_pending_without_next_bar():
    rows = _candles(1)
    out = settle_event({"side": -1}, rows, signal_index=0, atr=np.asarray([1.0]))
    assert out["state"] == "awaiting_next_open"
