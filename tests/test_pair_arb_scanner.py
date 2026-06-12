"""Tests for scripts.pair_arb_scanner.scan_pairs (Opus 2026-06-08)."""
import importlib.util, math
spec = importlib.util.spec_from_file_location("pas", "scripts/pair_arb_scanner.py")
pas = importlib.util.module_from_spec(spec); spec.loader.exec_module(pas)
vpa_spec = importlib.util.spec_from_file_location("vpa", "scripts/validate_pair_arb.py")
vpa = importlib.util.module_from_spec(vpa_spec); vpa_spec.loader.exec_module(vpa)
from strategies.pair_stat_arb_v1 import PairConfig


def test_make_pairs_count():
    assert len(pas.make_pairs(["A", "B", "C"])) == 3  # AB, AC, BC


def test_scan_finds_diverged_cointegrated_pair():
    import math, statistics
    from strategies.pair_stat_arb_v1 import compute_spread
    a, b = vpa._gen_cointegrated(n=300, seed=1)
    _, _, spread = compute_spread(a[-120:], b[-120:])
    sd = statistics.pstdev(spread)
    a = list(a); a[-1] = a[-1] * math.exp(3.0 * sd)  # force divergence on A/B
    # add an unrelated random-walk symbol that should NOT be a candidate
    import random; rng = random.Random(5); c = [100.0]
    for _ in range(299): c.append(c[-1] * (1 + rng.gauss(0, 0.01)))
    pm = {"AAA": a, "BBB": b, "CCC": c}
    cands = pas.scan_pairs(
        pm,
        cfg=PairConfig(
            lookback=120,
            entry_z=1.5,
            stop_z=10.0,
            min_abs_corr=0.6,
            max_half_life=999.0,
            max_beta_drift_frac=0.0,
        ),
        max_candidates=5,
    )
    assert any(set(x["pair"].split("/")) == {"AAA", "BBB"} for x in cands)


def test_scan_empty_when_no_signal():
    a, b = vpa._gen_cointegrated(n=300, seed=2)  # unshocked -> z near 0
    cands = pas.scan_pairs({"AAA": a, "BBB": b}, cfg=PairConfig(lookback=120, entry_z=2.0))
    assert cands == []
