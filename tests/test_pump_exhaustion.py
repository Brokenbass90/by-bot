"""Tests for bot.pump_exhaustion — confirmation-gated pump/dump fade."""
from bot.pump_exhaustion import impulse_exhaustion, ImpulseFadeState


def _base(n=34, px=100.0, vol=1000.0):
    return [[i, px, px + 0.2, px - 0.2, px, vol] for i in range(n)]


def test_insufficient_data():
    st = impulse_exhaustion([[i, 100, 101, 99, 100, 1] for i in range(10)])
    assert isinstance(st, ImpulseFadeState)
    assert st.ok is False and st.short_ok is False and st.long_ok is False


def test_flat_has_no_impulse():
    st = impulse_exhaustion(_base())
    assert st.ok is True
    assert st.impulse is False
    assert st.fade_side == "none"


def test_accelerating_pump_is_not_faded():
    # strong up move that keeps closing at highs -> impulse but NOT confirmed.
    r = _base() + [
        [34, 100, 106, 100, 105.8, 4000], [35, 105.8, 112, 105.5, 111.5, 5000],
        [36, 111.5, 118, 111, 117.5, 6000], [37, 117.5, 124, 117, 123.5, 7000],
    ]
    st = impulse_exhaustion(r)
    assert st.impulse is True and st.direction == "up"
    assert st.confirmed is False
    assert st.short_ok is False            # never fade strength / catch a knife
    assert st.reason in ("not_exhausted_yet", "no_reversal_confirmation")


def test_up_pump_reversal_gives_short_only():
    r = _base() + [
        [34, 100, 108, 100, 107.5, 6000], [35, 107.5, 118, 107, 117.5, 7000],
        [36, 117.5, 120, 112, 113.0, 3000], [37, 113.0, 114, 104, 105.0, 1500],
    ]
    st = impulse_exhaustion(r)
    assert st.impulse and st.direction == "up"
    assert st.exhausted and st.confirmed
    assert st.short_ok is True and st.long_ok is False
    assert st.fade_side == "short"
    assert st.retrace_frac >= 0.33


def test_down_dump_reversal_gives_long_only():
    r = _base() + [
        [34, 100, 100, 92, 92.5, 6000], [35, 92.5, 93, 82, 82.5, 7000],
        [36, 82.5, 88, 80, 87.0, 3000], [37, 87.0, 96, 86, 95.0, 1500],
    ]
    st = impulse_exhaustion(r)
    assert st.impulse and st.direction == "down"
    assert st.long_ok is True and st.short_ok is False
    assert st.fade_side == "long"


def test_side_is_mutually_exclusive():
    for r in (_base(), _base() + [[34, 100, 120, 100, 119, 8000]] * 1):
        st = impulse_exhaustion(r)
        assert not (st.short_ok and st.long_ok)
