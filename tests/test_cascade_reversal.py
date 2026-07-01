"""Tests for bot.cascade_reversal — liquidation-cascade reversal fade (H4)."""
from bot.cascade_reversal import cascade_reversal, CascadeState

N = 300


def _flat(n):
    return [[i, 100, 100.3, 99.7, 100, 1000] for i in range(n)]


def _down_rows():
    return _flat(N - 6) + [
        [N - 6, 100, 100, 97, 97.5, 5000], [N - 5, 97.5, 97.6, 95, 95.5, 6000],
        [N - 4, 95.5, 95.6, 93, 93.5, 7000], [N - 3, 93.5, 93.6, 92, 92.5, 4000],
        [N - 2, 92.5, 92.6, 91.5, 92.0, 3000], [N - 1, 92.0, 93.0, 91.8, 92.8, 2000]]


def _up_rows():
    return _flat(N - 6) + [
        [N - 6, 100, 103, 100, 102.5, 5000], [N - 5, 102.5, 105, 102, 104.5, 6000],
        [N - 4, 104.5, 107, 104, 106.5, 7000], [N - 3, 106.5, 107.5, 106, 107.0, 4000],
        [N - 2, 107, 107.6, 106.5, 107.2, 3000], [N - 1, 107.2, 108, 107, 107.8, 2000]]


_OI = [1_000_000] * (N - 4) + [1_000_000, 950_000, 940_000, 930_000]   # ~7% drop
_LIQ = [100.0] * (N - 4) + [8000, 9000, 9500, 9800]
_FUND_POS = [0.0001] * (N - 1) + [0.02]
_FUND_NEG = [0.0001] * (N - 1) + [-0.02]


def test_insufficient_data():
    st = cascade_reversal(_flat(5), [0.0], [1.0], [1.0])
    assert isinstance(st, CascadeState) and st.ok is False


def test_down_cascade_is_long_only():
    st = cascade_reversal(_down_rows(), _FUND_POS, _OI, _LIQ)
    assert st.cascade_active and st.direction == "down"
    assert st.long_ok is True and st.short_ok is False
    assert st.reason == "cascade_reversal_confirmed"
    assert 2 <= st.bars_since_start <= 5


def test_up_cascade_is_short_only():
    st = cascade_reversal(_up_rows(), _FUND_NEG, _OI, _LIQ)
    assert st.direction == "up"
    assert st.short_ok is True and st.long_ok is False


def test_calm_market_no_cascade():
    st = cascade_reversal(_flat(N), [0.0001] * N, [1_000_000] * N, [100.0] * N)
    assert st.cascade_active is False and st.long_ok is False and st.short_ok is False


def test_no_oi_flush_not_active():
    st = cascade_reversal(_down_rows(), _FUND_POS, [1_000_000] * N, _LIQ)
    assert st.cascade_active is False and st.reason == "no_oi_flush"


def test_funding_not_extreme_rejected():
    flat_funding = [0.0001] * N
    st = cascade_reversal(_down_rows(), flat_funding, _OI, _LIQ)
    assert st.cascade_active is True          # liq+oi+move present
    assert st.long_ok is False and st.reason == "funding_not_extreme"


def test_cascade_too_old_rejected():
    liq_old = [100.0] * (N - 8) + [8000] * 8   # 8 elevated bars -> trend, not reversal
    oi = [1_000_000] * (N - 3) + [950_000, 940_000, 930_000]
    st = cascade_reversal(_down_rows(), _FUND_POS, oi, liq_old)
    assert st.timing_ok is False and st.long_ok is False


def test_side_mutually_exclusive():
    for rows, fund in ((_down_rows(), _FUND_POS), (_up_rows(), _FUND_NEG), (_flat(N), [0.0001] * N)):
        st = cascade_reversal(rows, fund, _OI, _LIQ)
        assert not (st.long_ok and st.short_ok)
