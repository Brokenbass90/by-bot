"""Tests for bot.structure_break — BOS (continuation) + CHoCH (reversal)."""
from bot.structure_break import structure_break, StructureBreak


def _rows(closes):
    return [[i, p, p + 0.25, p - 0.25, p, 1000] for i, p in enumerate(closes)]


_UP = [100, 101, 102, 103, 102, 101, 103, 104, 105, 106, 105, 104,
       106, 107, 108, 109, 108, 107, 109, 110, 111, 112, 111, 110]
_DN = [112, 111, 110, 109, 110, 111, 109, 108, 107, 106, 107, 108,
       106, 105, 104, 103, 104, 105, 103, 102, 101, 100, 101, 102]


def test_insufficient_data():
    s = structure_break(_rows([100, 101, 100, 101]))
    assert isinstance(s, StructureBreak) and s.ok is False


def test_bos_up_is_long():
    s = structure_break(_rows(_UP) + [[24, 110, 113.5, 110, 113, 2000]])
    assert s.event == "bos" and s.direction == "up" and s.trend == "up"
    assert s.long_ok is True and s.short_ok is False


def test_choch_down_in_uptrend_is_short():
    s = structure_break(_rows(_UP) + [[24, 110, 110.2, 106, 106.5, 2000]])
    assert s.event == "choch" and s.direction == "down"
    assert s.short_ok is True and s.long_ok is False


def test_bos_down_is_short():
    s = structure_break(_rows(_DN) + [[24, 102, 102, 98.5, 99, 2000]])
    assert s.event == "bos" and s.direction == "down" and s.trend == "down"
    assert s.short_ok is True


def test_no_break():
    s = structure_break(_rows(_UP) + [[24, 110, 110.3, 109.7, 110, 1000]])
    assert s.event == "none" and s.reason == "no_break"


def test_side_mutually_exclusive():
    for tail in ([24, 110, 113.5, 110, 113, 2000], [24, 110, 110.2, 106, 106.5, 2000],
                 [24, 110, 110.3, 109.7, 110, 1000]):
        s = structure_break(_rows(_UP) + [tail])
        assert not (s.long_ok and s.short_ok)
