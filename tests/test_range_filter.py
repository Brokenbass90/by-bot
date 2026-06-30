"""Tests for bot.range_filter — unified range/chop gate with side split."""
import math
import random

from bot.range_filter import range_state, from_candles, RangeState


def _trending(n=220, slope=0.5):
    return [[i, 100 + i * slope, 100 + i * slope + 0.3,
             100 + i * slope - 0.3, 100 + i * slope + 0.1, 1000.0] for i in range(n)]


def _jagged_range(n=220, seed=7, noise=1.6, mid=100.0, pull=0.15):
    random.seed(seed)
    rows = []
    prev = mid
    for i in range(n):
        c = mid + pull * (prev - mid) + random.uniform(-noise, noise)
        o = prev
        h = max(o, c) + abs(random.uniform(0, 0.6))
        l = min(o, c) - abs(random.uniform(0, 0.6))
        rows.append([i, o, h, l, c, 1000.0])
        prev = c
    return rows


def test_insufficient_data_returns_not_ok():
    st = range_state([[i, 100, 101, 99, 100, 1] for i in range(10)])
    assert isinstance(st, RangeState)
    assert st.ok is False
    assert st.is_range is False


def test_trending_is_not_range():
    st = range_state(_trending())
    assert st.ok is True
    assert st.is_range is False          # a clean trend must not pass the range gate
    assert st.long_ok is False and st.short_ok is False


def test_jagged_mean_reversion_is_range():
    st = range_state(_jagged_range())
    assert st.ok is True
    assert st.is_range is True           # choppy mean-reversion -> range
    assert st.votes >= 2
    assert st.regime in ("flat", "ascending", "descending")


def test_side_split_is_one_directional():
    # invariant: long_ok and short_ok are mutually exclusive, and each implies
    # the correct channel position + that we are in range.
    for seed in range(8):
        st = range_state(_jagged_range(seed=seed))
        assert not (st.long_ok and st.short_ok)
        if st.long_ok:
            assert st.is_range and st.pos_in_channel <= 0.30 + 1e-9
            assert st.side_hint == "long"
        if st.short_ok:
            assert st.is_range and st.pos_in_channel >= 0.70 - 1e-9
            assert st.side_hint == "short"


def test_strict_mode_is_stricter():
    rows = _jagged_range()
    loose = range_state(rows, require_all=False)
    strict = range_state(rows, require_all=True)
    # strict can never be range when loose is not
    assert not (strict.is_range and not loose.is_range)


def test_from_candles_adapter_roundtrips():
    class C:
        def __init__(self, ts, o, h, l, c, v):
            self.ts, self.o, self.h, self.l, self.c, self.v = ts, o, h, l, c, v
    cnds = [C(i, 100, 101, 99, 100.5, 5) for i in range(120)]
    rows = from_candles(cnds)
    assert len(rows) == len(cnds)
    assert rows[0] == [0, 100, 101, 99, 100.5, 5]
    st = range_state(rows)
    assert isinstance(st, RangeState) and st.ok is True


def test_levels_present_on_real_shape():
    # nearest support/resistance should be finite-or-nan floats, never crash
    st = range_state(_jagged_range())
    assert isinstance(st.nearest_support, float)
    assert isinstance(st.nearest_resistance, float)
