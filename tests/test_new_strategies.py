"""Tests for range_mean_reversion_v1 + trend_pullback_v1 (Opus 2026-06-08)."""
import math
from strategies.range_mean_reversion_v1 import RangeMeanReversionV1, RMRConfig
from strategies.trend_pullback_v1 import TrendPullbackV1, TPBConfig


def _osc(n, amp=2.0, base=100.0):
    return [base + amp * math.sin(i * 0.7) for i in range(n)]


# ---- RMR1 ----
def test_rmr_long_band_fade():
    cfg = RMRConfig(bb_period=10, bb_k=0.5, rsi_period=5, rsi_os=85, atr_period=5,
                    sl_atr_mult=1.0, max_trend_slope_pct=1000.0, min_rr=0.0)
    closes = _osc(20) + [96.0]          # last bar dips below band
    highs = [c + 0.5 for c in closes]; lows = [c - 0.5 for c in closes]
    s = RangeMeanReversionV1(cfg).signal(highs, lows, closes)
    assert s is not None and s["side"] == "long", s
    assert s["sl"] < s["entry"] < s["tp"]


def test_rmr_short_band_fade():
    cfg = RMRConfig(bb_period=10, bb_k=0.5, rsi_period=5, rsi_ob=15, atr_period=5,
                    sl_atr_mult=1.0, max_trend_slope_pct=1000.0, min_rr=0.0)
    closes = _osc(20) + [104.0]
    highs = [c + 0.5 for c in closes]; lows = [c - 0.5 for c in closes]
    s = RangeMeanReversionV1(cfg).signal(highs, lows, closes)
    assert s is not None and s["side"] == "short", s
    assert s["tp"] < s["entry"] < s["sl"]


def test_rmr_rejects_strong_trend():
    cfg = RMRConfig(bb_period=10, atr_period=5, rsi_period=5)  # default flat gate
    closes = [100.0 + 2.0 * i for i in range(30)]              # steep uptrend
    highs = [c + 0.5 for c in closes]; lows = [c - 0.5 for c in closes]
    assert RangeMeanReversionV1(cfg).signal(highs, lows, closes) is None


def test_rmr_history_short():
    assert RangeMeanReversionV1().signal([1, 2], [1, 2], [1, 2]) is None


# ---- TPB1 ----
def test_tpb_long_pullback():
    cfg = TPBConfig(ema_fast=5, ema_slow=10, rsi_period=5, rsi_long_max=95,
                    atr_period=5, pullback_atr=10.0, min_trend_slope_pct=0.0)
    closes = [100.0 + 1.5 * i for i in range(25)] + [135.0]   # uptrend + small dip
    highs = [c + 0.5 for c in closes]; lows = [c - 0.5 for c in closes]
    s = TrendPullbackV1(cfg).signal(highs, lows, closes)
    assert s is not None and s["side"] == "long", s
    assert s["sl"] < s["entry"] < s["tp"]


def test_tpb_short_pullback():
    cfg = TPBConfig(ema_fast=5, ema_slow=10, rsi_period=5, rsi_short_min=5,
                    atr_period=5, pullback_atr=10.0, min_trend_slope_pct=0.0)
    closes = [200.0 - 1.5 * i for i in range(25)] + [165.0]   # downtrend + small bounce
    highs = [c + 0.5 for c in closes]; lows = [c - 0.5 for c in closes]
    s = TrendPullbackV1(cfg).signal(highs, lows, closes)
    assert s is not None and s["side"] == "short", s
    assert s["tp"] < s["entry"] < s["sl"]


def test_tpb_history_short():
    assert TrendPullbackV1().signal([1, 2], [1, 2], [1, 2]) is None
