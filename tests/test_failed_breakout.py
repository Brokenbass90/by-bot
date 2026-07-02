"""Tests for bot.failed_breakout — fade a breakout that failed (ARF2 exhaustion fix)."""
from bot.failed_breakout import failed_breakout, FailedBreakState


def _base(n=25):
    return [[i, 100, 101, 99, 100, 1000] for i in range(n)]


def _fail_up():
    return _base() + [
        [25, 100.5, 101.2, 100.3, 101.4, 3000],   # close above resistance ~101 (attempt)
        [26, 101.4, 101.5, 100.5, 101.1, 2500],
        [27, 101.1, 101.2, 100.0, 100.3, 1500],   # reclaimed back below (fail)
        [28, 100.3, 100.5, 99.8, 100.1, 1000],
        [29, 100.1, 100.4, 99.7, 100.0, 900]]


def _fail_down():
    return _base() + [
        [25, 99.5, 99.8, 98.6, 98.5, 3000],
        [26, 98.5, 99.0, 98.3, 98.7, 2500],
        [27, 98.7, 99.6, 98.6, 99.4, 1500],
        [28, 99.4, 99.7, 99.0, 99.3, 1000],
        [29, 99.3, 99.6, 99.0, 99.5, 900]]


def test_insufficient_data():
    s = failed_breakout([[i, 1, 1, 1, 1, 1] for i in range(10)])
    assert isinstance(s, FailedBreakState) and s.ok is False


def test_failed_break_above_is_short():
    s = failed_breakout(_fail_up())
    assert s.failed and s.direction == "up"
    assert s.short_ok is True and s.long_ok is False and s.reason == "failed_break_above"


def test_failed_break_below_is_long():
    s = failed_breakout(_fail_down())
    assert s.failed and s.direction == "down"
    assert s.long_ok is True and s.short_ok is False


def test_clean_range_no_failed_break():
    s = failed_breakout([[i, 100, 100.5, 99.5, 100, 1000] for i in range(35)])
    assert s.failed is False and s.reason == "no_failed_break"


def test_genuine_break_hold_is_not_a_fade():
    # broke above and STAYED above -> not a failed break -> no fade
    rows = _base() + [[25 + k, 101.5 + k * 0.2, 102 + k * 0.2, 101.3 + k * 0.2, 101.8 + k * 0.2, 2000]
                      for k in range(5)]
    s = failed_breakout(rows)
    assert s.short_ok is False       # price held above -> do not fade

def test_side_mutually_exclusive():
    for rows in (_fail_up(), _fail_down(), _base(35)):
        s = failed_breakout(rows)
        assert not (s.long_ok and s.short_ok)
