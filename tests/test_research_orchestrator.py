"""Tests for bot.research_orchestrator — weekly AI proposal loop (in rails)."""
from bot.research_orchestrator import weekly_review, format_proposal, Proposal

HEALTHY = [2.5, -1, -1, 2.5, -1, -1, 2.5, -1, 2.5, -1,
           -1, 2.5, -1, 2.5, -1, -1, 2.5, -1, 2.5, -1] * 2
DEGRADED = [0.3, -0.2] * 25
ROBUST = [{"net_r": 1.2, "trades": 15}, {"net_r": 0.9, "trades": 14},
          {"net_r": 1.4, "trades": 16}, {"net_r": 1.0, "trades": 13}]
WEAK = [{"net_r": 8.0, "trades": 12}, {"net_r": -0.3, "trades": 11},
        {"net_r": 0.1, "trades": 10}, {"net_r": -0.2, "trades": 13}]


def _run():
    running = [
        {"name": "att1:short", "stage": "canary", "live_r": HEALTHY, "baseline_expectancy_R": 0.4},
        {"name": "arf2:short", "stage": "champion", "live_r": DEGRADED, "baseline_expectancy_R": 0.4},
    ]
    cands = [{"id": "smart_grid", "folds": ROBUST, "preflight": {"go": True}},
             {"id": "inplay_v4", "folds": WEAK, "preflight": {"go": False}}]
    return weekly_review(running, cands, period_label="2026-w27", max_dd_R=12)


def test_returns_proposal():
    p = _run()
    assert isinstance(p, Proposal) and p.generated_for == "2026-w27"


def test_healthy_canary_proposed_promote():
    p = _run()
    att1 = next(a for a in p.actions if a["sleeve"] == "att1:short")
    assert att1["action"].startswith("PROMOTE") and att1["health"] == "healthy"


def test_degraded_champion_proposed_demote():
    p = _run()
    arf2 = next(a for a in p.actions if a["sleeve"] == "arf2:short")
    assert arf2["action"].startswith("DEMOTE")
    assert "arf2:short" in p.retest_queue          # queued for fresh re-test


def test_candidates_ranked_pass_first():
    p = _run()
    assert p.candidate_ranking[0]["id"] == "smart_grid"
    assert p.candidate_ranking[0]["oos_pass"] is True
    assert p.candidate_ranking[-1]["oos_pass"] is False


def test_summary_counts():
    p = _run()
    assert p.summary["promote"] == 1 and p.summary["demote"] == 1
    assert p.summary["candidates_gate_pass"] == 1


def test_format_is_human_readable():
    txt = format_proposal(_run())
    assert "WEEKLY RESEARCH PROPOSAL" in txt and "approve to apply" in txt
    assert "att1:short" in txt and "smart_grid" in txt
