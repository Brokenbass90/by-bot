"""Champion / challenger registry — promote proven sleeves, demote decayed ones.

This is the portfolio-building governor that ties the pieces together so we grow
the book HONESTLY, one proven arm at a time, and never let a rotting one bleed:

  candidate --(passes OOS via oos_selector)-->  shadow
  shadow    --(paper trades healthy via edge_monitor)-->  canary
  canary    --(live healthy + positive expectancy)-->    champion
  any live stage --(edge_monitor degraded/halt)-->        demoted

Each stage has a MINIMUM sample + health bar, so promotion is earned, not hoped.
Pure stdlib; composes bot.oos_selector + bot.edge_monitor. Deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.oos_selector import evaluate_candidate
from bot.edge_monitor import assess_sleeve

STAGES = ("candidate", "shadow", "canary", "champion", "demoted")


@dataclass
class Transition:
    name: str
    from_stage: str
    to_stage: str
    action: str                 # "promote" | "demote" | "hold"
    reason: str
    extra: Dict[str, Any] = field(default_factory=dict)


def step_sleeve(
    sleeve: Dict[str, Any],
    *,
    shadow_min_trades: int = 30,
    canary_min_trades: int = 20,
    champion_min_trades: int = 40,
    **health_kw,
) -> Transition:
    """Decide the next lifecycle stage for ONE sleeve from its evidence.

    sleeve = {name, stage, oos_folds:[{net_r,trades}], paper_r:[...], live_r:[...],
              baseline_expectancy_R}
    """
    name = str(sleeve.get("name", "?"))
    stage = str(sleeve.get("stage", "candidate"))
    base = sleeve.get("baseline_expectancy_R", 0.0) or 0.0

    def T(to, action, reason, **ex):
        return Transition(name, stage, to, action, reason, ex)

    # live stages first: health can demote from anywhere live
    def health(rs, min_tr):
        return assess_sleeve(rs, sleeve=name, baseline_expectancy_R=base,
                             min_trades=min_tr, **health_kw)

    if stage == "candidate":
        folds = sleeve.get("oos_folds") or []
        g = evaluate_candidate({"id": name, "folds": folds})
        if g.passes:
            return T("shadow", "promote", f"oos_pass:{g.reason}",
                     median_R=g.median_metric, frac_pos=g.frac_positive)
        return T("candidate", "hold", f"oos_fail:{g.reason}")

    if stage == "shadow":
        rs = sleeve.get("paper_r") or []
        h = health(rs, shadow_min_trades)
        if h.status in ("degraded", "halt"):
            return T("demoted", "demote", f"shadow_{h.status}:{h.reason}")
        if h.status == "healthy":
            return T("canary", "promote", "shadow_healthy", exp=h.live_expectancy_R)
        return T("shadow", "hold", h.reason)

    if stage == "canary":
        rs = sleeve.get("live_r") or []
        h = health(rs, canary_min_trades)
        if h.status in ("degraded", "halt"):
            return T("demoted", "demote", f"canary_{h.status}:{h.reason}")
        if h.status == "healthy" and h.live_expectancy_R > 0:
            return T("champion", "promote", "canary_proven", exp=h.live_expectancy_R)
        return T("canary", "hold", h.reason)

    if stage == "champion":
        rs = sleeve.get("live_r") or []
        h = health(rs, champion_min_trades)
        if h.status in ("degraded", "halt"):
            return T("demoted", "demote", f"champion_{h.status}:{h.reason}")
        return T("champion", "hold", h.reason)

    # demoted is terminal until an explicit re-validation resets stage to candidate
    return T("demoted", "hold", "terminal")


def run_registry(sleeves: Sequence[Dict[str, Any]], **kw) -> List[Transition]:
    """Step every sleeve; returns the transition list (promotions/demotions/holds)."""
    return [step_sleeve(s, **kw) for s in sleeves]


def portfolio_view(transitions: Sequence[Transition]) -> Dict[str, List[str]]:
    """Group sleeve names by their resulting stage (what the live book looks like)."""
    view: Dict[str, List[str]] = {s: [] for s in STAGES}
    for t in transitions:
        view.setdefault(t.to_stage, []).append(t.name)
    return view
