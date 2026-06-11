"""Tests for bot/dd_throttle.py (Claude 2026-06-10)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.dd_throttle import DDThrottle


def test_no_drawdown_full_risk():
    t = DDThrottle(threshold_pct=2.0, cut_mult=0.5)
    assert t.risk_scale(100.0) == 1.0
    assert t.risk_scale(105.0) == 1.0  # новый пик
    assert t.peak_equity == 105.0


def test_throttles_beyond_threshold():
    t = DDThrottle(threshold_pct=2.0, cut_mult=0.5)
    t.risk_scale(100.0)
    assert t.risk_scale(97.5) == 0.5   # dd 2.5% > 2% → тормоз
    assert t.active


def test_small_dd_not_throttled():
    t = DDThrottle(threshold_pct=2.0, cut_mult=0.5)
    t.risk_scale(100.0)
    assert t.risk_scale(98.5) == 1.0   # dd 1.5% < 2%
    assert not t.active


def test_recovery_restores_risk():
    t = DDThrottle(threshold_pct=2.0, cut_mult=0.5)
    t.risk_scale(100.0)
    assert t.risk_scale(95.0) == 0.5
    assert t.risk_scale(101.0) == 1.0  # новый пик — тормоз снят
    assert t.peak_equity == 101.0


def test_zero_peak_safe():
    t = DDThrottle()
    assert t.drawdown_pct(50.0) == 0.0
