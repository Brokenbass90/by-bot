"""Tests for bot.liquidity_sweep — stop-run fade vs break-and-hold (densities)."""
from bot.liquidity_sweep import liquidity_sweep, SweepState


def _base(n=25):
    return [[i, 100, 100.5, 99.5, 100, 1000] for i in range(n)]


def test_insufficient_data():
    st = liquidity_sweep(_base(5))
    assert isinstance(st, SweepState) and st.ok is False


def test_sweep_of_highs_is_short_fade():
    rows = _base() + [[25, 100.2, 102.0, 100.0, 100.2, 3000]]   # poke above, close back below
    st = liquidity_sweep(rows)
    assert st.event == "sweep_reversal" and st.side == "short"
    assert st.short_ok is True and st.long_ok is False
    assert st.penetration_atr > 0


def test_sweep_of_lows_is_long_fade():
    rows = _base() + [[25, 99.8, 100.0, 98.0, 99.8, 3000]]
    st = liquidity_sweep(rows)
    assert st.event == "sweep_reversal" and st.side == "long" and st.long_ok is True


def test_break_hold_up_is_long():
    rows = _base() + [[25, 100.4, 101.5, 100.3, 101.2, 3000]]
    st = liquidity_sweep(rows)
    assert st.event == "break_hold" and st.side == "long" and st.long_ok is True


def test_break_hold_down_is_short():
    rows = _base() + [[25, 99.6, 99.7, 98.5, 98.8, 3000]]
    st = liquidity_sweep(rows)
    assert st.event == "break_hold" and st.side == "short" and st.short_ok is True


def test_inside_pools_no_event():
    rows = _base() + [[25, 100, 100.3, 99.7, 100, 1000]]
    st = liquidity_sweep(rows)
    assert st.event == "none" and st.reason == "inside_pools"


def test_side_mutually_exclusive():
    for last in ([25, 100.2, 102.0, 100.0, 100.2, 3000], [25, 99.8, 100.0, 98.0, 99.8, 3000],
                 [25, 100.4, 101.5, 100.3, 101.2, 3000], [25, 100, 100.3, 99.7, 100, 1000]):
        st = liquidity_sweep(_base() + [last])
        assert not (st.long_ok and st.short_ok)
