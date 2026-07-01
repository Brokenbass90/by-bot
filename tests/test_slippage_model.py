"""Tests for bot.slippage_model — honest slippage calibration & application."""
from bot.slippage_model import (fill_slippage_bps, calibrate_from_fills,
                                estimate_bps, apply_slippage)


def test_adverse_sign():
    assert abs(fill_slippage_bps(100, 100.1, "long") - 10.0) < 1e-6   # bought higher
    assert abs(fill_slippage_bps(100, 99.9, "short") - 10.0) < 1e-6   # sold lower
    assert fill_slippage_bps(100, 99.9, "long") < 0                   # bought cheaper = favorable


def test_calibrate_per_symbol():
    fills = ([{"symbol": "SOL", "side": "long", "expected_price": 100, "fill_price": 100.1}] * 25 +
             [{"symbol": "LINK", "side": "short", "expected_price": 10, "fill_price": 9.97}] * 25)
    t = calibrate_from_fills(fills)
    assert t["SOL"]["n"] == 25 and abs(t["SOL"]["median_bps"] - 10.0) < 1e-6
    assert abs(t["LINK"]["median_bps"] - 30.0) < 1e-6


def test_estimate_uses_calibration_when_enough_data():
    t = {"SOL": {"median_bps": 12.0, "p90_bps": 25.0, "n": 40}}
    assert estimate_bps("SOL", table=t) == 12.0
    assert estimate_bps("SOL", table=t, use_p90=True) == 25.0


def test_estimate_falls_back_to_default_when_thin():
    t = {"SOL": {"median_bps": 12.0, "p90_bps": 25.0, "n": 3}}
    assert estimate_bps("SOL", table=t, default_bps=6.0) == 6.0
    assert estimate_bps("UNKNOWN", table=t, default_bps=6.0) == 6.0


def test_context_multipliers():
    assert estimate_bps("X", context="inplay", default_bps=6.0, inplay_mult=5.0) == 30.0
    assert estimate_bps("X", context="illiquid", default_bps=6.0, illiquid_mult=8.0) == 48.0


def test_notional_scaling_is_sublinear():
    small = estimate_bps("X", default_bps=10.0, notional=500, notional_ref=500)
    big = estimate_bps("X", default_bps=10.0, notional=2000, notional_ref=500)
    assert small == 10.0 and big == 20.0          # sqrt(4)=2x, not 4x


def test_apply_slippage_is_adverse():
    assert apply_slippage(100, "long", 10) > 100    # buy fills higher
    assert apply_slippage(100, "short", 10) < 100   # sell fills lower
