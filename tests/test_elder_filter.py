"""Tests for bot.elder_filter — directional confluence gate on top of legs."""
from bot.elder_filter import elder_bias, ElderBias


def _trend(n=260, start=200.0, slope=0.5):
    return [[i, start + i * slope, start + i * slope + 0.3,
             start + i * slope - 0.3, start + i * slope + 0.1, 1000 + (i % 3) * 10]
            for i in range(n)]


def _flat(n=260, px=100.0):
    return [[i, px, px + 0.4, px - 0.4, px, 1000] for i in range(n)]


def test_insufficient_data():
    st = elder_bias([[i, 100, 101, 99, 100, 1000] for i in range(20)])
    assert isinstance(st, ElderBias)
    assert st.ok is False


def test_uptrend_blocks_shorts():
    st = elder_bias(_trend(start=100, slope=0.5))
    assert st.ok and st.tide == "up" and st.bias == "long"
    assert st.allow_long is True
    assert st.allow_short is False        # do not fade a clear uptide


def test_downtrend_blocks_longs():
    st = elder_bias(_trend(start=300, slope=-0.5))
    assert st.tide == "down" and st.bias == "short"
    assert st.allow_short is True
    assert st.allow_long is False


def test_flat_allows_both():
    st = elder_bias(_flat())
    assert st.tide == "flat" and st.bias == "neutral"
    assert st.allow_long is True and st.allow_short is True


def test_micro_ema_gap_is_not_a_tide():
    # near-constant series must read flat, not a float-noise trend
    st = elder_bias(_flat(px=100.0))
    assert st.tide == "flat"


def test_require_with_tide_is_stricter():
    flat = _flat()
    loose = elder_bias(flat, require_with_tide=False)
    strict = elder_bias(flat, require_with_tide=True)
    # in flat, loose allows both, strict allows neither
    assert loose.allow_long and loose.allow_short
    assert not strict.allow_long and not strict.allow_short


def test_htf_rows_used_for_tide():
    # uptrending HTF should permit longs even if trading tf is flat
    st = elder_bias(_flat(), htf_rows=_trend(start=100, slope=0.5))
    assert st.tide == "up"
    assert st.allow_short is False
