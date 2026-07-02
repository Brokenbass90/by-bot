"""Research orchestrator — the AI-under-the-hood weekly review loop.

Realizes the owner's vision: a CONSTANT shadow search that never stops, an AI layer
that governs it, and once-a-week PROPOSALS (never silent auto-changes) about what to
promote, demote, re-tune or re-test. It only composes already-validated modules:
  * oos_selector    -> rank/accept new candidates by OOS robustness;
  * edge_monitor    -> live health of running sleeves;
  * champion_challenger -> lifecycle transition per sleeve;
  * preflight_check -> is a candidate even worth a full gate yet.

CRITICAL rail: this PROPOSES, a human approves. It never optimizes params live or
flips risk on its own. Output is a human-readable weekly proposal. Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.oos_selector import evaluate_candidate
from bot.edge_monitor import assess_sleeve
from bot.champion_challenger import step_sleeve


@dataclass
class Proposal:
    generated_for: str                      # e.g. "2026-07-week27"
    actions: List[Dict[str, Any]]           # per running sleeve
    candidate_ranking: List[Dict[str, Any]] # new candidates, best first
    retest_queue: List[str]                 # demoted sleeves due for a fresh look
    summary: Dict[str, int] = field(default_factory=dict)


def _sleeve_action(s: Dict[str, Any], **kw) -> Dict[str, Any]:
    """Health + lifecycle -> a proposed action for one running sleeve."""
    name = str(s.get("name", "?"))
    stage = str(s.get("stage", "candidate"))
    rs = s.get("live_r") or s.get("paper_r") or []
    base = float(s.get("baseline_expectancy_R", 0.0) or 0.0)
    h = assess_sleeve(rs, sleeve=name, baseline_expectancy_R=base, **kw)
    t = step_sleeve({"name": name, "stage": stage,
                     "oos_folds": s.get("oos_folds", []),
                     "paper_r": rs if stage == "shadow" else [],
                     "live_r": rs if stage in ("canary", "champion") else [],
                     "baseline_expectancy_R": base}, **kw)
    if t.action == "promote":
        action = f"PROMOTE {stage}->{t.to_stage}"
    elif t.action == "demote":
        action = f"DEMOTE {stage}->demoted (stop risk)"
    else:
        action = "HOLD"
    return {"sleeve": name, "stage": stage, "action": action,
            "health": h.status, "expectancy_R": h.live_expectancy_R,
            "n": h.n, "reason": t.reason}


def weekly_review(
    running_sleeves: Sequence[Dict[str, Any]],
    new_candidates: Sequence[Dict[str, Any]],
    *,
    period_label: str = "week",
    **kw,
) -> Proposal:
    """Produce the weekly proposal: sleeve actions + candidate ranking + retest queue."""
    actions = [_sleeve_action(s, **kw) for s in running_sleeves]

    ranked: List[Dict[str, Any]] = []
    for c in new_candidates:
        g = evaluate_candidate({"id": c.get("id", "?"), "folds": c.get("folds", [])})
        pf = c.get("preflight") or {}
        ranked.append({"id": c.get("id", "?"), "oos_pass": g.passes,
                       "robustness": g.robustness, "frac_positive": g.frac_positive,
                       "median_R": g.median_metric, "preflight_go": pf.get("go"),
                       "verdict": ("GATE_PASS" if g.passes else f"NO: {g.reason}")})
    ranked.sort(key=lambda r: (bool(r["oos_pass"]), r["robustness"]), reverse=True)

    # sleeves demoted / degraded are queued for a periodic fresh-data re-test
    retest = [a["sleeve"] for a in actions if a["action"].startswith("DEMOTE") or a["health"] == "degraded"]

    summary = {
        "promote": sum(1 for a in actions if a["action"].startswith("PROMOTE")),
        "demote": sum(1 for a in actions if a["action"].startswith("DEMOTE")),
        "hold": sum(1 for a in actions if a["action"] == "HOLD"),
        "new_candidates": len(ranked),
        "candidates_gate_pass": sum(1 for r in ranked if r["oos_pass"]),
    }
    return Proposal(period_label, actions, ranked, retest, summary)


def format_proposal(p: Proposal) -> str:
    """Human-readable weekly proposal (for Telegram / review). Approve before applying."""
    L = [f"WEEKLY RESEARCH PROPOSAL — {p.generated_for}  (proposals only, approve to apply)"]
    s = p.summary
    L.append(f"summary: promote={s.get('promote',0)} demote={s.get('demote',0)} hold={s.get('hold',0)} "
             f"| new_candidates={s.get('new_candidates',0)} gate_pass={s.get('candidates_gate_pass',0)}")
    L.append("-- running sleeves --")
    for a in p.actions:
        L.append(f"  {a['sleeve']}: {a['action']} | health={a['health']} exp={a['expectancy_R']:.2f}R n={a['n']} ({a['reason']})")
    L.append("-- new candidates (best first) --")
    for r in p.candidate_ranking:
        L.append(f"  {r['id']}: {r['verdict']} | robustness={r['robustness']:.3f} preflight_go={r['preflight_go']}")
    if p.retest_queue:
        L.append(f"-- shadow re-test queue: {', '.join(p.retest_queue)}")
    return "\n".join(L)
