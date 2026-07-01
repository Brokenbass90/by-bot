"""Sleeve registry — make (strategy x side) the ATOMIC managed unit.

Owner rule: almost every directional logic must be split into short-only and
long-only sleeves, each with its OWN stats, breaker, allocation and lifecycle.
A bidirectional PF must NEVER justify live. This registry enforces that: it keys
everything by `sleeve_id = "{strategy}:{side}"`, groups decision_bus outcomes per
side, computes side-specific health (edge_monitor) and holds per-sleeve risk/stage.

Composes bot.edge_monitor + bot.champion_challenger. Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.edge_monitor import assess_sleeve, HealthReport
from bot.champion_challenger import step_sleeve, Transition


def sleeve_id(strategy: str, side: str) -> str:
    return f"{str(strategy)}:{str(side).lower()}"


def group_by_sleeve(records: Sequence[Dict[str, Any]]) -> Dict[str, List[float]]:
    """Group filled ENTER outcomes into per-(strategy,side) R-multiple lists."""
    out: Dict[str, List[float]] = {}
    for r in records:
        if r.get("decision") != "enter":
            continue
        oc = r.get("outcome") or {}
        if not oc.get("filled"):
            continue
        rm = oc.get("r_multiple")
        if rm is None or rm != rm:
            continue
        sid = sleeve_id(r.get("strategy", "?"), r.get("side", "?"))
        out.setdefault(sid, []).append(float(rm))
    return out


def sleeve_health(
    records: Sequence[Dict[str, Any]],
    baselines: Optional[Dict[str, float]] = None,
    **kw,
) -> Dict[str, HealthReport]:
    """Side-specific health per sleeve (never mixes long+short of one strategy)."""
    baselines = baselines or {}
    groups = group_by_sleeve(records)
    return {sid: assess_sleeve(rs, sleeve=sid, baseline_expectancy_R=baselines.get(sid, 0.0), **kw)
            for sid, rs in groups.items()}


@dataclass
class Sleeve:
    sleeve_id: str
    strategy: str
    side: str
    stage: str = "candidate"       # candidate|shadow|canary|champion|demoted
    risk_mult: float = 0.0         # live risk weight (0 = shadow/off)
    enabled: bool = True


class SleeveRegistry:
    """Holds the set of (strategy x side) sleeves and their live risk/stage."""

    def __init__(self) -> None:
        self._sleeves: Dict[str, Sleeve] = {}

    def register(self, strategy: str, side: str, *, stage: str = "candidate",
                 risk_mult: float = 0.0) -> Sleeve:
        sid = sleeve_id(strategy, side)
        s = Sleeve(sid, strategy, str(side).lower(), stage, risk_mult)
        self._sleeves[sid] = s
        return s

    def register_bidirectional(self, strategy: str, **kw) -> List[Sleeve]:
        """A bidirectional logic MUST register as two independent sleeves."""
        return [self.register(strategy, "long", **kw), self.register(strategy, "short", **kw)]

    def get(self, strategy: str, side: str) -> Optional[Sleeve]:
        return self._sleeves.get(sleeve_id(strategy, side))

    def set_risk(self, strategy: str, side: str, risk_mult: float) -> None:
        s = self._sleeves.get(sleeve_id(strategy, side))
        if s:
            s.risk_mult = float(risk_mult)

    def live_sleeves(self) -> List[Sleeve]:
        return [s for s in self._sleeves.values() if s.enabled and s.risk_mult > 0]

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {sid: {"stage": s.stage, "risk_mult": s.risk_mult, "enabled": s.enabled,
                      "strategy": s.strategy, "side": s.side}
                for sid, s in self._sleeves.items()}

    def apply_lifecycle(
        self,
        records: Sequence[Dict[str, Any]],
        oos_by_sleeve: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        baselines: Optional[Dict[str, float]] = None,
        **kw,
    ) -> Dict[str, Transition]:
        """Step each sleeve through champion_challenger using side-specific evidence.

        On demote -> risk_mult=0; on champion -> keep; caller sets canary risk.
        """
        oos_by_sleeve = oos_by_sleeve or {}
        baselines = baselines or {}
        groups = group_by_sleeve(records)
        out: Dict[str, Transition] = {}
        for sid, s in self._sleeves.items():
            rs = groups.get(sid, [])
            payload = {"name": sid, "stage": s.stage,
                       "oos_folds": oos_by_sleeve.get(sid, []),
                       "paper_r": rs if s.stage == "shadow" else [],
                       "live_r": rs if s.stage in ("canary", "champion") else [],
                       "baseline_expectancy_R": baselines.get(sid, 0.0)}
            t = step_sleeve(payload, **kw)
            s.stage = t.to_stage
            if t.to_stage == "demoted":
                s.risk_mult = 0.0
            out[sid] = t
        return out
