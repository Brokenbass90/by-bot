"""Tests for bot.breakout_confirm — confirmed level breakout with side split."""
from bot.breakout_confirm import breakout_confirm, BreakoutState


def _res_base():
    rows, ts = [], 0
    seg = [99.5, 100.2, 101.0, 100.3, 99.6, 100.4, 101.0, 100.2, 99.7, 100.5, 101.0, 100.1]
    for _ in range(3):
        for p in seg:
            hi = p + 0.05 if p < 100.9 else p
            rows.append([ts, p, hi, p - 0.3, p, 1000]); ts += 1
    return rows


def _sup_base():
    rows, ts = [], 0
    seg = [100.5, 99.8, 99.0, 99.7, 100.4, 99.6, 99.0, 99.8, 100.3, 99.5, 99.0, 99.9]
    for _ in range(3):
        for p in seg:
            lo = p - 0.05 if p > 99.1 else p
            rows.append([ts, p, p + 0.3, lo, p, 1000]); ts += 1
    return rows


def test_insufficient_data():
    st = breakout_confirm([[i, 100, 101, 99, 100, 1] for i in range(10)])
    assert isinstance(st, BreakoutState)
    assert st.ok is False and st.long_ok is False and st.short_ok is False


def test_confirmed_up_break_is_long_only():
    r = _res_base()
    r += [[len(r), 100.5, 101.2, 100.4, 101.0, 1000],
          [len(r) + 1, 101.0, 102.2, 100.9, 102.0, 3000],
          [len(r) + 2, 102.0, 102.4, 101.6, 102.1, 2000]]
    st = breakout_confirm(r)
    assert st.broke and st.direction == "up" and st.confirmed
    assert st.long_ok is True and st.short_ok is False
    assert st.close_beyond_atr >= 0.25
    assert not (st.long_ok and st.short_ok)


def test_confirmed_down_break_is_short_only():
    r = _sup_base()
    r += [[len(r), 99.4, 99.5, 98.0, 98.2, 3000],
          [len(r) + 1, 98.2, 98.4, 97.6, 97.9, 2000]]
    st = breakout_confirm(r)
    assert st.direction == "down" and st.confirmed
    assert st.short_ok is True and st.long_ok is False


def test_break_without_volume_or_followthrough_not_confirmed():
    r = _res_base()
    r += [[len(r), 100.5, 101.0, 100.4, 100.8, 900],
          [len(r) + 1, 100.8, 102.3, 100.7, 102.0, 900]]   # beyond buffer, low vol, ft=1
    st = breakout_confirm(r)
    assert st.broke and st.direction == "up"
    assert st.confirmed is False
    assert st.long_ok is False
    assert st.reason == "no_volume_or_followthrough"


def test_range_has_no_breakout():
    r = _res_base() + [[36, 100.0, 100.4, 99.6, 100.0, 1000]]
    st = breakout_confirm(r)
    assert st.broke is False and st.reason == "no_breakout"


def test_side_mutually_exclusive_everywhere():
    for r in (_res_base(), _sup_base(), _res_base() + [[36, 100, 105, 100, 104, 9000]]):
        st = breakout_confirm(r)
        assert not (st.long_ok and st.short_ok)
