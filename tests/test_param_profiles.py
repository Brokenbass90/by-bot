"""Tests for per-coin-family parameter profiles."""

from bot.param_profiles import classify_tier, resolve_params


def test_major_mid_micro_classification():
    assert classify_tier("BTCUSDT") == "major"
    assert classify_tier("SOLUSDT") == "major"
    assert classify_tier("NEARUSDT") == "mid"
    assert classify_tier("SOMENEWMEMEUSDT") == "micro"   # unseen -> default


def test_vol_fallback_for_unseen_symbol():
    # low vol -> major, mid vol -> mid, high vol -> micro
    assert classify_tier("UNSEEN", realized_vol=0.008) == "major"
    assert classify_tier("UNSEEN", realized_vol=0.020) == "mid"
    assert classify_tier("UNSEEN", realized_vol=0.050) == "micro"


def test_resolve_params_differ_by_tier():
    major = resolve_params("ASB1", "BTCUSDT")
    micro = resolve_params("ASB1", "SOMENEWMEMEUSDT")
    assert float(major["ASB1_SL_ATR_MULT"]) < float(micro["ASB1_SL_ATR_MULT"])  # majors tighter
    assert "ASB1_TIME_STOP_BARS_5M" in major


def test_unknown_strategy_returns_empty():
    assert resolve_params("NOPE", "BTCUSDT") == {}
