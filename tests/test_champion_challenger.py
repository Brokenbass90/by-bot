"""Tests for bot.champion_challenger — sleeve lifecycle governor."""
from bot.champion_challenger import step_sleeve, run_registry, portfolio_view, Transition

ROBUST = [{"net_r": 1.2, "trades": 15}, {"net_r": 0.9, "trades": 14},
          {"net_r": 1.4, "trades": 16}, {"net_r": 1.0, "trades": 13}]
PEAK = [{"net_r": 8.0, "trades": 12}, {"net_r": -0.3, "trades": 11},
        {"net_r": 0.1, "trades": 10}, {"net_r": -0.2, "trades": 13}]
HEALTHY = [2.5, -1, -1, 2.5, -1, -1, 2.5, -1, 2.5, -1,
           -1, 2.5, -1, 2.5, -1, -1, 2.5, -1, 2.5, -1] * 3
DEGRADED = [0.3, -0.2] * 25


def test_candidate_passing_oos_promotes_to_shadow():
    t = step_sleeve({"name": "c", "stage": "candidate", "oos_folds": ROBUST})
    assert t.to_stage == "shadow" and t.action == "promote"


def test_candidate_failing_oos_holds():
    t = step_sleeve({"name": "c", "stage": "candidate", "oos_folds": PEAK})
    assert t.to_stage == "candidate" and t.action == "hold"
    assert t.reason.startswith("oos_fail")


def test_shadow_healthy_promotes_to_canary():
    t = step_sleeve({"name": "s", "stage": "shadow", "paper_r": HEALTHY,
                     "baseline_expectancy_R": 0.4}, max_dd_R=12)
    assert t.to_stage == "canary" and t.action == "promote"


def test_canary_proven_promotes_to_champion():
    t = step_sleeve({"name": "cn", "stage": "canary", "live_r": HEALTHY,
                     "baseline_expectancy_R": 0.4}, max_dd_R=12)
    assert t.to_stage == "champion" and t.action == "promote"


def test_champion_decay_demotes():
    t = step_sleeve({"name": "ch", "stage": "champion", "live_r": DEGRADED,
                     "baseline_expectancy_R": 0.4}, max_dd_R=12)
    assert t.to_stage == "demoted" and t.action == "demote"


def test_halt_demotes_from_canary():
    losing = [-1] * 12 + [2.5] * 10
    t = step_sleeve({"name": "x", "stage": "canary", "live_r": losing,
                     "baseline_expectancy_R": 0.4, }, canary_min_trades=20, max_dd_R=6)
    assert t.to_stage == "demoted"


def test_insufficient_shadow_holds():
    t = step_sleeve({"name": "s", "stage": "shadow", "paper_r": [2.5, -1, 2.5],
                     "baseline_expectancy_R": 0.4}, shadow_min_trades=30)
    assert t.to_stage == "shadow" and t.action == "hold"


def test_run_registry_and_portfolio_view():
    sleeves = [
        {"name": "cand_pass", "stage": "candidate", "oos_folds": ROBUST},
        {"name": "champ_decay", "stage": "champion", "live_r": DEGRADED, "baseline_expectancy_R": 0.4},
    ]
    ts = run_registry(sleeves, max_dd_R=12)
    assert all(isinstance(t, Transition) for t in ts)
    view = portfolio_view(ts)
    assert "cand_pass" in view["shadow"] and "champ_decay" in view["demoted"]
