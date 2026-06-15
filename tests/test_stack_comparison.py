"""Tests for the control-plane (обвязка) help/hurt comparison."""

from backtest.stack_comparison import compare, _slot_filter


def _t(entry, exit, R, regime="bull_trend"):
    return {"entry_ts": entry, "exit_ts": exit, "R": R, "regime": regime}


def test_regime_gate_helps_by_dropping_losers():
    # losers are in bear regime; gate keeps only bull -> expectancy improves
    trades = [_t(1, 2, 2.0, "bull_trend"), _t(2, 3, -1.0, "bear_chop"),
              _t(3, 4, 3.0, "bull_trend"), _t(4, 5, -1.0, "bear_chop")]
    res = compare(trades, regime_ok=lambda r: "bull" in r)
    assert res["bare"]["expectancy_R"] == 0.75       # (2-1+3-1)/4
    assert res["stacked"]["expectancy_R"] == 2.5      # (2+3)/2
    assert res["verdict"] == "control-plane HELPS"
    assert res["dropped"] == 2


def test_slot_cap_can_hurt_by_dropping_winners():
    # max_concurrent=1 forces dropping an overlapping BIG winner -> hurts
    trades = [_t(1, 10, -1.0), _t(2, 11, 5.0), _t(3, 12, 4.0)]
    res = compare(trades, max_concurrent=1)
    assert res["bare"]["expectancy_R"] > res["stacked"]["expectancy_R"]
    assert "HURTS" in res["verdict"]


def test_slot_filter_limits_concurrency():
    trades = [_t(1, 10, 1.0), _t(2, 9, 1.0), _t(3, 8, 1.0)]
    kept = _slot_filter(trades, max_concurrent=2)
    assert len(kept) == 2          # third overlaps -> dropped


def test_all_blocked_flagged():
    trades = [_t(1, 2, 1.0, "bear_chop")]
    res = compare(trades, regime_ok=lambda r: "bull" in r)
    assert res["stacked"]["trades"] == 0
    assert "BLOCKS ALL" in res["verdict"]
