import math
"""Tests for backtest.robustness (Opus 2026-06-08)."""
from backtest.robustness import jitter_rows, walk_forward_windows, aggregate_oos

DAY = 86_400_000


def _rows():
    return [
        {"ts": 1000, "o": 100.0, "h": 105.0, "l": 98.0, "c": 102.0, "v": 10.0},
        {"ts": 2000, "o": 102.0, "h": 110.0, "l": 101.0, "c": 109.0, "v": 12.0},
    ]


def test_jitter_preserves_shape_and_ts_and_volume():
    out = jitter_rows(_rows(), pct=0.002, seed=1)
    assert len(out) == 2
    assert out[0]["ts"] == 1000 and out[1]["ts"] == 2000
    assert out[0]["v"] == 10.0


def test_jitter_preserves_ohlc_invariants():
    out = jitter_rows(_rows(), pct=0.01, seed=7)
    for r in out:
        assert r["h"] >= r["o"] and r["h"] >= r["c"] and r["h"] >= r["l"]
        assert r["l"] <= r["o"] and r["l"] <= r["c"] and r["l"] <= r["h"]


def test_jitter_within_bound():
    base = _rows()
    out = jitter_rows(base, pct=0.002, seed=3)
    # close should move by at most ~0.2% (allow tiny margin)
    assert abs(out[0]["c"] - base[0]["c"]) / base[0]["c"] <= 0.0025


def test_jitter_deterministic_with_seed():
    a = jitter_rows(_rows(), pct=0.005, seed=42)
    b = jitter_rows(_rows(), pct=0.005, seed=42)
    assert a[0]["c"] == b[0]["c"] and a[1]["o"] == b[1]["o"]


def test_jitter_does_not_mutate_input():
    base = _rows()
    jitter_rows(base, pct=0.01, seed=1)
    assert base[0]["o"] == 100.0 and base[0]["h"] == 105.0


def test_jitter_list_rows():
    rows = [[1000, 100.0, 105.0, 98.0, 102.0, 10.0]]
    out = jitter_rows(rows, pct=0.002, seed=1)
    assert out[0][0] == 1000 and out[0][5] == 10.0
    assert out[0][2] >= out[0][3]  # h >= l


def test_walk_forward_basic_count_and_order():
    start = 0
    end = 100 * DAY
    folds = walk_forward_windows(start, end, is_days=60, oos_days=20)
    # folds: [0-60 IS, 60-80 OOS], step 20 -> next 20-80 IS,80-100 OOS
    assert len(folds) == 2
    for f in folds:
        assert f["is_end"] == f["oos_start"]          # OOS follows IS
        assert f["oos_end"] <= end
        assert f["is_start"] < f["is_end"] < f["oos_end"]


def test_walk_forward_oos_non_overlap_default_step():
    folds = walk_forward_windows(0, 200 * DAY, is_days=60, oos_days=20)
    oos = [(f["oos_start"], f["oos_end"]) for f in folds]
    for (s1, e1), (s2, e2) in zip(oos, oos[1:]):
        assert s2 >= e1  # non-overlapping OOS


def test_walk_forward_too_short_returns_empty():
    assert walk_forward_windows(0, 10 * DAY, is_days=60, oos_days=20) == []


def test_aggregate_oos_verdict_robust():
    folds = [
        {"profit_factor": 1.4, "return_pct": 10, "max_drawdown": 4, "trades": 30},
        {"profit_factor": 1.2, "return_pct": 6, "max_drawdown": 5, "trades": 25},
        {"profit_factor": 1.1, "return_pct": 3, "max_drawdown": 6, "trades": 20},
    ]
    s = aggregate_oos(folds)
    assert s["folds"] == 3
    assert s["profit_factor"]["median"] == 1.2
    assert s["verdict"] == "robust"


def test_aggregate_oos_verdict_fragile():
    folds = [
        {"profit_factor": 1.6, "return_pct": 20, "max_drawdown": 4, "trades": 30},
        {"profit_factor": 0.3, "return_pct": -15, "max_drawdown": 12, "trades": 25},
    ]
    s = aggregate_oos(folds)
    assert s["verdict"] == "fragile"  # one catastrophic fold


def test_aggregate_oos_empty():
    assert aggregate_oos([])["verdict"] == "no_folds"


# --- reviewer-feedback metrics (2026-06-08) ---
from backtest.robustness import geometric_mean_return, sortino_ratio, fee_sensitivity


def test_geometric_mean_below_arithmetic_for_volatile():
    vol = [0.5, -0.3, 0.4, -0.25]
    g = geometric_mean_return(vol)
    a = sum(vol) / len(vol)
    assert g < a  # geo penalises volatility


def test_geometric_mean_empty_and_wipeout():
    assert geometric_mean_return([]) == 0.0
    assert geometric_mean_return([-1.0, 0.1]) == -1.0  # a -100% trade wipes out


def test_sortino_positive_when_mostly_up():
    assert sortino_ratio([0.02, 0.01, -0.01, 0.015]) > 0


def test_sortino_no_downside_is_inf():
    assert sortino_ratio([0.01, 0.02, 0.0]) == float("inf")


def test_fee_sensitivity_detects_fragile():
    # small per-trade edge that dies as fees rise
    trades = [0.0015] * 50  # +0.15% gross per trade
    r = fee_sensitivity(trades, fee_bps_list=(6.0, 10.0), sides=2)
    assert "6bps" in r["levels"] and "10bps" in r["levels"]
    # at 6bps round-trip cost = 0.12% < 0.15% -> profitable; at 10bps = 0.20% > 0.15% -> loss
    assert r["levels"]["6bps"]["profitable"] is True
    assert r["levels"]["10bps"]["profitable"] is False
    assert r["verdict"] == "fee_fragile"


def test_fee_sensitivity_robust():
    trades = [0.01] * 30  # fat 1% edge survives high fees
    r = fee_sensitivity(trades, fee_bps_list=(6.0, 10.0))
    assert r["verdict"] == "fee_robust"
