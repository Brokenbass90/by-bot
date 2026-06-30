import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.adaptive_context import adaptive_params, get_adaptive_context, context_snapshot


def _row(i, o, h, l, c, v=100.0):
    return [i, o, h, l, c, v]


def _flat(n=60, lo=100.0, hi=110.0):
    rows = []
    for i in range(n):
        if i % 2 == 0:
            rows.append(_row(i, lo + 2, lo + 3, lo, lo + 1))
        else:
            rows.append(_row(i, hi - 3, hi, hi - 2, hi - 1))
    return rows


def test_adaptive_params_regimes():
    flat = adaptive_params(2.0, "flat")
    assert flat["min_touches"] == 3 and flat["tol_atr"] == 0.30
    hv = adaptive_params(6.0, "ascending")
    assert hv["pivot_left"] == 3 and hv["tol_atr"] >= 0.5  # high vol widens
    norm = adaptive_params(2.0, "descending")
    assert norm["tol_atr"] == 0.40


def test_get_adaptive_context_runs_and_snapshots():
    rows = _flat()
    r = get_adaptive_context(rows)
    assert r["ctx"] is not None
    assert r["regime"] in ("flat", "ascending", "descending", "unknown")
    assert "params" in r and "tol_atr" in r["params"]
    snap = r["snapshot"]
    assert "regime" in snap and "params" in snap and "broken_support" in snap


def test_tuner_override_hook():
    rows = _flat()
    def my_tuner(snapshot):
        return {"min_touches": 2, "tol_atr": 0.5}  # external override
    r = get_adaptive_context(rows, tuner=my_tuner)
    assert r["params"]["min_touches"] == 2
    assert r["params"]["tol_atr"] == 0.5


def test_tuner_failure_is_safe():
    rows = _flat()
    def bad_tuner(snapshot):
        raise RuntimeError("api down")
    r = get_adaptive_context(rows, tuner=bad_tuner)
    assert r["ctx"] is not None  # falls back to rule-based, no crash


def test_empty_safe():
    r = get_adaptive_context([])
    assert r["ctx"] is None and r["regime"] == "unknown"
