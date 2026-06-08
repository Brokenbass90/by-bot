"""Tests for strategies.equities_swing_active_v1 (Opus 2026-06-08)."""
from strategies.equities_swing_active_v1 import (
    score_symbol, select, is_day_trade_safe, SwingConfig,
)


def uptrend(n=90, up=1.015, dn=0.990, start=100.0):
    c = [start]
    for i in range(n):
        c.append(c[-1] * (up if i % 2 == 0 else dn))
    return c


def downtrend(n=90):
    return uptrend(n, up=1.010, dn=0.985)  # net down


def all_up(n=90):
    c = [100.0]
    for _ in range(n):
        c.append(c[-1] * 1.01)
    return c


def test_uptrend_eligible_and_positive_score():
    s = score_symbol(uptrend())
    assert s["eligible"] is True, s
    assert s["score"] > 0
    assert s["rsi"] < SwingConfig().rsi_max


def test_downtrend_rejected_below_sma():
    s = score_symbol(downtrend())
    assert s["eligible"] is False
    assert s["reason"] == "below_sma"


def test_overbought_rejected():
    s = score_symbol(all_up())
    assert s["eligible"] is False
    assert s["reason"] == "overbought"


def test_history_short_rejected():
    s = score_symbol([100, 101, 102, 103])
    assert s["eligible"] is False and s["reason"] == "history_short"


def test_select_ranks_and_filters():
    uni = {
        "STRONG": uptrend(up=1.020, dn=0.990),   # bigger drift
        "MILD": uptrend(up=1.010, dn=0.995),     # smaller drift
        "DOWN": downtrend(),                      # excluded
    }
    res = select(uni, SwingConfig(top_n=5))
    syms = [r[0] for r in res]
    assert "DOWN" not in syms
    assert syms[0] == "STRONG"            # best momentum first
    assert res[0][1]["score"] >= res[-1][1]["score"]


def test_day_trade_safety():
    assert is_day_trade_safe(0, 86400 * 2, min_hold_days=2) is True   # 2 days held
    assert is_day_trade_safe(0, 3600, min_hold_days=2) is False        # same day
