"""Tests for bot.wf_folds — purge+embargo walk-forward folds (H5 / CPCV-lite)."""
from bot.wf_folds import purge_embargo_folds, FoldSet
from bot.oos_selector import evaluate_candidate


def _trades(n=40, hold=50, step=100):
    return [{"entry_ts": i * step, "exit_ts": i * step + hold,
             "r": (2.0 if i % 3 else -1.0)} for i in range(n)]


def test_too_few_trades():
    fs = purge_embargo_folds(_trades(2), n_folds=4)
    assert isinstance(fs, FoldSet) and fs.folds == []


def test_clean_partition_no_loss():
    fs = purge_embargo_folds(_trades(40), n_folds=4)
    assert fs.n_folds == 4 and len(fs.folds) == 4
    assert fs.used == 40 and fs.purged == 0 and fs.embargoed == 0
    assert sum(f["trades"] for f in fs.folds) == 40


def test_straddler_is_purged():
    trades = _trades(40) + [{"entry_ts": 900, "exit_ts": 1600, "r": 9.9}]  # crosses a boundary
    fs = purge_embargo_folds(trades, n_folds=4)
    assert fs.purged >= 1
    # the 9.9 straddler must not inflate any fold
    assert all(f["net_r"] < 15 for f in fs.folds)


def test_embargo_drops_boundary_trades():
    clean = purge_embargo_folds(_trades(40), n_folds=4, embargo=0.0)
    emb = purge_embargo_folds(_trades(40), n_folds=4, embargo=120.0)
    assert emb.embargoed > 0
    assert emb.used < clean.used


def test_feeds_oos_selector():
    fs = purge_embargo_folds(_trades(40), n_folds=4)
    cand = fs.as_candidate("wf_demo")
    assert cand["id"] == "wf_demo" and len(cand["folds"]) == 4
    g = evaluate_candidate(cand, min_trades_total=20, min_trades_per_fold=3)
    assert g.passes is True and g.frac_positive == 1.0


def test_purge_removes_leakage_direction():
    # a huge straddling winner should be excluded, lowering a naive fold sum
    base = _trades(40)
    leaked = base + [{"entry_ts": 950, "exit_ts": 1500, "r": 50.0}]
    fs = purge_embargo_folds(leaked, n_folds=4)
    assert fs.purged >= 1
    assert max(f["net_r"] for f in fs.folds) < 50.0
