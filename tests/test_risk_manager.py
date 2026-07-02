"""Tests for bot.risk_manager — smart adaptive, anti-martingale risk in rails."""
from bot.risk_manager import smart_risk, RiskDecision


class _R:
    def __init__(self, dominant, confidence):
        self.dominant, self.confidence = dominant, confidence


class _H:
    def __init__(self, status):
        self.status = status


def test_healthy_favorable_keeps_base():
    d = smart_risk(0.75, regime=_R("bull", 0.6), health=_H("healthy"))
    assert isinstance(d, RiskDecision) and abs(d.risk_pct - 0.75) < 1e-9 and d.blocked is False


def test_high_vol_blocks():
    d = smart_risk(0.75, regime=_R("high_vol", 0.6), health=_H("healthy"))
    assert d.blocked is True and d.risk_pct == 0.0 and d.reason == "blocked_high_vol"


def test_halt_health_blocks():
    d = smart_risk(0.75, regime=_R("range", 0.5), health=_H("halt"))
    assert d.blocked is True and d.reason == "blocked_halt"


def test_degraded_halves():
    d = smart_risk(0.75, regime=_R("range", 0.5), health=_H("degraded"))
    assert abs(d.health_scalar - 0.5) < 1e-9 and abs(d.risk_pct - 0.375) < 1e-9


def test_anti_martingale_drawdown_cuts_risk():
    shallow = smart_risk(0.75, equity_drawdown_pct=2.0)
    deep = smart_risk(0.75, equity_drawdown_pct=8.0)
    assert deep.risk_pct < shallow.risk_pct         # deeper DD -> LESS risk, never more
    assert deep.drawdown_scalar < shallow.drawdown_scalar


def test_drawdown_floor_respected():
    d = smart_risk(0.75, equity_drawdown_pct=50.0, dd_floor=0.25)
    assert abs(d.drawdown_scalar - 0.25) < 1e-9     # never below floor


def test_vol_scalar_reduces():
    d = smart_risk(0.75, regime=_R("range", 0.5), health=_H("healthy"), vol_scalar=0.5)
    assert abs(d.risk_pct - 0.375) < 1e-9


def test_hard_cap():
    d = smart_risk(5.0, regime=_R("bull", 1.0), health=_H("healthy"), hard_cap_pct=1.0)
    assert d.risk_pct == 1.0


def test_below_min_blocks():
    d = smart_risk(0.75, equity_drawdown_pct=9.9, vol_scalar=0.1, min_live_pct=0.05)
    assert d.blocked is True and d.reason.startswith("below_min")
