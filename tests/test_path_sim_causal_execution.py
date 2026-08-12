import numpy as np

from research_lab.path_sim import _require_complete_windows, _verify_passport, simulate


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


def test_experiment_requires_physical_input_and_passport(monkeypatch):
    monkeypatch.setattr("research_lab.path_sim.INPUT_PATH", "")
    monkeypatch.setattr("research_lab.path_sim.PASSPORT_PATH", "")
    monkeypatch.setattr("research_lab.path_sim.SEARCH_END_UTC", "")
    try:
        _verify_passport()
    except RuntimeError as exc:
        assert "required" in str(exc)
    else:
        raise AssertionError("missing passport gate did not fail closed")


def test_incomplete_windows_fail_closed():
    try:
        _require_complete_windows({"_meta": {}, "0": {"skipped": "timeout"}})
    except RuntimeError as exc:
        assert "0/4" in str(exc)
    else:
        raise AssertionError("partial path simulation was accepted")
