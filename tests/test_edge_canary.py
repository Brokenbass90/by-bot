"""Tests for bot/edge_canary.py (Claude 2026-06-10)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.edge_canary import EdgeCanary, rolling_pf


def _pnls(wins: int, losses: int, w: float = 2.0, l: float = 1.0):
    return [w] * wins + [-l] * losses


def test_healthy_full_mult():
    c = EdgeCanary(window=40, min_trades=12)
    v = c.assess("asb1", _pnls(10, 8))  # PF = 20/8 = 2.5
    assert v.verdict == "healthy" and v.mult == 1.0


def test_fading_and_sick_steps():
    c = EdgeCanary(window=40, min_trades=12)
    assert c.assess("x", _pnls(7, 13)).verdict == "fading"   # PF 14/13 ≈ 1.08
    assert c.assess("y", _pnls(6, 13)).verdict == "sick"     # PF 12/13 ≈ 0.92


def test_dying_then_archive_after_two_windows():
    c = EdgeCanary(window=40, min_trades=12)
    bad = _pnls(4, 13)  # PF 8/13 ≈ 0.62 < 0.70
    v1 = c.assess("bd1", bad)
    assert v1.verdict == "dying" and v1.mult == 0.25
    v2 = c.assess("bd1", bad)
    assert v2.verdict == "archive" and v2.mult == 0.0


def test_recovery_resets_streak_and_mult():
    c = EdgeCanary(window=40, min_trades=12)
    c.assess("att1", _pnls(4, 13))                    # dying, окно 1
    v = c.assess("att1", _pnls(12, 6))                # выздоровел: PF 2.0
    assert v.verdict == "healthy" and v.mult == 1.0
    v2 = c.assess("att1", _pnls(4, 13))               # снова плохо — streak заново
    assert v2.verdict == "dying"                       # не archive!


def test_few_trades_unknown_no_punishment():
    c = EdgeCanary(window=40, min_trades=12)
    v = c.assess("elder", _pnls(2, 3))
    assert v.verdict == "unknown" and v.mult == 1.0


def test_window_limits_lookback():
    c = EdgeCanary(window=10, min_trades=5)
    pnls = _pnls(0, 30) + _pnls(8, 2)  # древний кошмар + свежий блеск
    v = c.assess("s", pnls)
    assert v.verdict == "healthy"      # смотрим только последние 10


def test_rolling_pf_edge_cases():
    assert rolling_pf([]) is None
    assert rolling_pf([1.0, 2.0]) == 99.0
    assert abs(rolling_pf([2.0, -1.0]) - 2.0) < 1e-9
