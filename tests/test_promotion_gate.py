"""Tests for the objective canary-promotion gate."""

from backtest.promotion_gate import evaluate, GateThresholds


def test_strong_candidate_passes():
    c = {"windows_with_trades": 4, "positive_windows": 4, "profit_factor": 1.6,
         "expectancy_R": 0.4, "trades": 35, "stack_verdict": "control-plane HELPS"}
    r = evaluate(c)
    assert r.go is True
    assert r.failed == []


def test_weak_candidate_fails_with_reasons():
    c = {"windows_with_trades": 4, "positive_windows": 1, "profit_factor": 0.8,
         "expectancy_R": -0.1, "trades": 12, "stack_verdict": "control-plane HURTS"}
    r = evaluate(c)
    assert r.go is False
    assert len(r.failed) >= 4   # frac, pf, expectancy, trades, stack


def test_pf_just_below_one_fails():
    c = {"windows_with_trades": 4, "positive_windows": 3, "profit_factor": 0.99,
         "expectancy_R": 0.1, "trades": 30}
    assert evaluate(c).go is False


def test_inf_pf_handled():
    c = {"windows_with_trades": 3, "positive_windows": 3, "profit_factor": "inf",
         "expectancy_R": 0.5, "trades": 25}
    assert evaluate(c).go is True


def test_stack_optional_when_absent():
    c = {"windows_with_trades": 3, "positive_windows": 3, "profit_factor": 1.3,
         "expectancy_R": 0.2, "trades": 22}
    assert evaluate(c).go is True   # no stack_verdict -> not blocked


def test_custom_thresholds():
    c = {"windows_with_trades": 2, "positive_windows": 2, "profit_factor": 1.2,
         "expectancy_R": 0.2, "trades": 10}
    assert evaluate(c).go is False                       # default min_trades 20
    loose = GateThresholds(min_windows=2, min_trades=8)
    assert evaluate(c, loose).go is True
