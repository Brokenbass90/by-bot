"""Tests for bot.oos_selector — anti-overfit OOS-plateau selection."""
from bot.oos_selector import evaluate_candidate, select_robust, rank_all, Candidate


def _robust():
    return {"id": "robust", "folds": [
        {"net_r": 1.2, "trades": 15}, {"net_r": 0.9, "trades": 14},
        {"net_r": 1.4, "trades": 16}, {"net_r": 1.0, "trades": 13}]}


def _hero():
    return {"id": "hero", "folds": [
        {"net_r": 8.0, "trades": 12}, {"net_r": -0.3, "trades": 11},
        {"net_r": 0.1, "trades": 10}, {"net_r": -0.2, "trades": 13}]}


def test_robust_plateau_passes():
    g = evaluate_candidate(_robust())
    assert g.passes is True
    assert g.frac_positive == 1.0
    assert g.reason == "robust_plateau"


def test_one_window_hero_rejected():
    g = evaluate_candidate(_hero())
    assert g.passes is False
    # rejected either for instability or the peak-ratio hero gate
    assert g.reason.startswith("unstable_frac_pos") or g.reason.startswith("one_window_hero")


def test_pure_peak_is_flagged_by_peak_ratio():
    # 3 positive folds but one dominates -> frac_pos passes, peak gate must catch it
    cand = {"id": "peak", "folds": [
        {"net_r": 9.0, "trades": 20}, {"net_r": 0.2, "trades": 20},
        {"net_r": 0.15, "trades": 20}, {"net_r": 0.1, "trades": 20}]}
    g = evaluate_candidate(cand)
    assert g.passes is False
    assert g.reason.startswith("one_window_hero")


def test_insufficient_trades_rejected():
    thin = {"id": "thin", "folds": [
        {"net_r": 2.0, "trades": 2}, {"net_r": 1.5, "trades": 3}, {"net_r": 1.8, "trades": 2}]}
    g = evaluate_candidate(thin)
    assert g.passes is False and g.reason.startswith("insufficient_trades")


def test_too_few_folds_rejected():
    # SpikeFade-style: only 2 folds -> cannot judge a plateau
    sf = {"id": "sf", "folds": [{"pf": 3.7, "trades": 16}, {"pf": 2.1, "trades": 13}]}
    g = evaluate_candidate(sf)
    assert g.passes is False and g.reason.startswith("too_few_folds")


def test_unstable_half_negative_rejected():
    u = {"id": "u", "folds": [
        {"net_r": 1.5, "trades": 20}, {"net_r": -1.0, "trades": 20},
        {"net_r": 1.2, "trades": 20}, {"net_r": -0.8, "trades": 20}]}
    g = evaluate_candidate(u)
    assert g.passes is False


def test_pf_fallback_metric():
    # candidate with pf (not net_r): pf>1 profitable
    c = {"id": "pf", "folds": [
        {"pf": 1.3, "trades": 15}, {"pf": 1.2, "trades": 15},
        {"pf": 1.4, "trades": 15}, {"pf": 1.1, "trades": 15}]}
    g = evaluate_candidate(c)
    assert g.passes is True


def test_select_robust_returns_only_passing_sorted():
    winners = select_robust([_robust(), _hero()])
    assert [w.id for w in winners] == ["robust"]
    assert all(isinstance(w, Candidate) and w.passes for w in winners)


def test_rank_all_orders_passing_first():
    ranked = rank_all([_hero(), _robust()])
    assert ranked[0].id == "robust"
    assert ranked[0].passes and not ranked[-1].passes
