"""Tests for bot.preflight_check — GO/NO-GO before an expensive OOS gate."""
from bot.preflight_check import preflight, PreflightReport


def _healthy(n=80, folds_symbols=("SOL", "AVAX", "LINK", "MATIC", "LTC", "XRP")):
    return [{"ts": i * 10, "symbol": folds_symbols[i % len(folds_symbols)]} for i in range(n)]


def test_no_signals_is_nogo():
    r = preflight([], n_folds=4)
    assert isinstance(r, PreflightReport) and r.go is False and "no_signals" in r.reasons


def test_healthy_is_go():
    r = preflight(_healthy(), n_folds=4)
    assert r.go is True and "ready_for_gate" in r.reasons
    assert min(r.per_fold_trades) >= 8 and r.symbols_covered >= 3


def test_inplay_like_thin_is_nogo():
    # 21 trades, one fold with 1 -> exactly the InPlay failure, catchable in advance
    buckets = [10, 5, 1, 5]
    sig = []
    for f, cnt in enumerate(buckets):
        for k in range(cnt):
            sig.append({"ts": f * 100 + k, "symbol": ["ADA", "DOGE", "SUI"][k % 3]})
    r = preflight(sig, n_folds=4)
    assert r.go is False
    assert any("thin_fold" in x for x in r.reasons)
    assert any("too_few_total" in x for x in r.reasons)


def test_single_symbol_concentration_is_nogo():
    sig = [{"ts": i * 10, "symbol": "SUI"} for i in range(80)]
    r = preflight(sig, n_folds=4)
    assert r.go is False and any("low_symbol_coverage" in x for x in r.reasons)


def test_custom_fold_edges():
    sig = [{"ts": t, "symbol": s} for t, s in
           [(5, "A"), (15, "B"), (25, "C"), (35, "A"), (45, "B"), (55, "C")]]
    r = preflight(sig, n_folds=3, fold_edges=[0, 20, 40, 60],
                  min_trades_total=6, min_trades_per_fold=2, min_symbols=3)
    assert r.per_fold_trades == [2, 2, 2] and r.go is True


def test_total_trades_and_symbols_counted():
    r = preflight(_healthy(60), n_folds=4, min_trades_total=40)
    assert r.total_trades == 60 and r.symbols_covered == 6


def test_quality_pf_blocks_obvious_noise_when_r_available():
    sig = _healthy(60)
    for i, s in enumerate(sig):
        s["r"] = 0.2 if i % 3 == 0 else -0.4
    r = preflight(sig, n_folds=4, min_quality_trades=20, min_quality_pf=0.8)
    assert r.go is False
    assert any(x.startswith("low_quality_pf_") for x in r.reasons)
    assert r.extra["quality_checked"] is True


def test_quality_pf_caution_does_not_block_borderline_signal():
    sig = _healthy(60)
    for i, s in enumerate(sig):
        s["r"] = 0.9 if i % 2 == 0 else -1.0
    r = preflight(sig, n_folds=4, min_quality_trades=20, min_quality_pf=0.8, caution_quality_pf=1.0)
    assert r.go is True
    assert any("caution_quality_pf" in x for x in r.extra["quality_warnings"])
