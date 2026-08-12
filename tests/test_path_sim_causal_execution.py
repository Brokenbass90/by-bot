import numpy as np

from research_lab.path_sim import simulate


def test_signal_close_cannot_be_used_as_entry_price():
    o = np.array([100.0, 120.0, 120.0])
    c = np.array([100.0, 120.0, 130.0])
    hi = np.array([101.0, 121.0, 131.0])
    lo = np.array([99.0, 119.0, 119.0])
    atr = np.array([10.0, 10.0, 10.0])

    result = simulate(o, c, hi, lo, atr, [0], [1], stop_atr=1.0, hb=2, cost_bps=0.0)

    assert result.tolist() == [1.0]


def test_next_open_bar_is_included_in_conservative_stop_first_path():
    o = np.array([100.0, 120.0])
    c = np.array([100.0, 125.0])
    hi = np.array([101.0, 126.0])
    lo = np.array([99.0, 109.0])
    atr = np.array([10.0, 10.0])

    result = simulate(o, c, hi, lo, atr, [0], [1], stop_atr=1.0, hb=1, cost_bps=0.0)

    assert result.tolist() == [-1.0]
