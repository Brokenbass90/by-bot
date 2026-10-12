"""Deterministic portfolio priority router for already-generated candidates.

The router does not create signals and never increases strategy risk. It ranks
immutable decisions produced by strategy engines and assigns a bounded number
of portfolio slots. Regime/health/execution technology can therefore be tested
through decision-ledger replay instead of re-optimising every strategy signal.

Capital authorization remains external. In ``money`` mode a candidate must
explicitly carry ``money_authorized=True``; ``shadow`` mode can rank research
candidates without broker access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class StrategyCandidate:
    decision_id: str
    ts: int
    symbol: str
    strategy: str
    side: str
    expected_net_r: float
    signal_quality: float = 1.0
    evidence_weight: float = 1.0
    regime_fit: float = 1.0
    health_mult: float = 1.0
    execution_quality: float = 1.0
    cost_stress_mult: float = 1.0
    symbol_rank: float = 0.5
    requested_risk_pct: float = 0.0
    beta_cluster: str = ""
    money_authorized: bool = False
    extra: dict = field(default_factory=dict, compare=False)

    @property
    def normalized_symbol(self) -> str:
        return str(self.symbol or "").strip().upper()

    @property
    def normalized_side(self) -> str:
        return str(self.side or "").strip().lower()


@dataclass(frozen=True)
class PriorityDecision:
    candidate: StrategyCandidate
    selected: bool
    score: float
    reason: str
    slot: int | None = None


def priority_score(candidate: StrategyCandidate) -> float:
    """Expected after-cost R discounted by independently measured reliability.

    Symbol rank is deliberately a modest 0.5..1.0 multiplier: relative rank can
    break ties, but cannot turn non-positive expectancy into an edge.
    """
    expected = max(0.0, float(candidate.expected_net_r))
    reliability = (
        _unit(candidate.signal_quality)
        * _unit(candidate.evidence_weight)
        * _unit(candidate.regime_fit)
        * _unit(candidate.health_mult)
        * _unit(candidate.execution_quality)
        * _unit(candidate.cost_stress_mult)
    )
    rank_mult = 0.5 + 0.5 * _unit(candidate.symbol_rank)
    return round(expected * reliability * rank_mult, 12)


def rank_candidates(
    candidates: Iterable[StrategyCandidate],
    *,
    now_ts: int,
    mode: str = "shadow",
    max_age_sec: int = 300,
    max_slots: int = 3,
    max_same_side: int = 2,
    max_same_cluster: int = 1,
    open_symbols: Sequence[str] = (),
    open_sides: Sequence[str] = (),
    open_clusters: Sequence[str] = (),
) -> list[PriorityDecision]:
    """Rank candidates and assign slots, returning a reason for every input."""
    mode_n = str(mode or "shadow").strip().lower()
    if mode_n not in {"shadow", "money"}:
        raise ValueError("mode must be shadow or money")

    occupied_symbols = {str(x or "").strip().upper() for x in open_symbols if str(x or "").strip()}
    side_counts = {"long": 0, "short": 0}
    for side in open_sides:
        side_n = str(side or "").strip().lower()
        if side_n in side_counts:
            side_counts[side_n] += 1
    cluster_counts: dict[str, int] = {}
    for cluster in open_clusters:
        cluster_n = str(cluster or "").strip().lower()
        if cluster_n:
            cluster_counts[cluster_n] = cluster_counts.get(cluster_n, 0) + 1

    prelim: list[tuple[StrategyCandidate, float, str | None]] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        score = priority_score(candidate)
        reason: str | None = None
        decision_id = str(candidate.decision_id or "").strip()
        side = candidate.normalized_side
        if not decision_id:
            reason = "missing_decision_id"
        elif decision_id in seen_ids:
            reason = "duplicate_decision_id"
        elif not candidate.normalized_symbol or not str(candidate.strategy or "").strip():
            reason = "invalid_identity"
        elif side not in {"long", "short"}:
            reason = "invalid_side"
        elif int(now_ts) - int(candidate.ts) > int(max_age_sec) or int(candidate.ts) > int(now_ts) + 5:
            reason = "stale_or_future_candidate"
        elif float(candidate.expected_net_r) <= 0:
            reason = "non_positive_expected_net_r"
        elif _unit(candidate.health_mult) <= 0:
            reason = "strategy_health_block"
        elif mode_n == "money" and not bool(candidate.money_authorized):
            reason = "money_not_authorized"
        elif score <= 0:
            reason = "zero_priority_score"
        seen_ids.add(decision_id)
        prelim.append((candidate, score, reason))

    eligible = sorted(
        (item for item in prelim if item[2] is None),
        key=lambda item: (-item[1], -int(item[0].ts), str(item[0].decision_id)),
    )
    selected_ids: dict[str, tuple[int, str]] = {}
    slots_left = max(0, int(max_slots) - len(occupied_symbols))

    for candidate, _score, _ in eligible:
        side = candidate.normalized_side
        symbol = candidate.normalized_symbol
        cluster = str(candidate.beta_cluster or "").strip().lower()
        reason = "selected"
        slot: int | None = None
        if slots_left <= 0:
            reason = "portfolio_slots_full"
        elif symbol in occupied_symbols:
            reason = "symbol_overlap"
        elif side_counts.get(side, 0) >= max(0, int(max_same_side)):
            reason = "same_side_cap"
        elif cluster and cluster_counts.get(cluster, 0) >= max(0, int(max_same_cluster)):
            reason = "beta_cluster_cap"
        else:
            slot = max(0, int(max_slots) - slots_left) + 1
            slots_left -= 1
            occupied_symbols.add(symbol)
            side_counts[side] = side_counts.get(side, 0) + 1
            if cluster:
                cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
        selected_ids[str(candidate.decision_id)] = (slot or 0, reason)

    out: list[PriorityDecision] = []
    for candidate, score, hard_reason in prelim:
        if hard_reason is not None:
            out.append(PriorityDecision(candidate, False, score, hard_reason, None))
            continue
        slot_i, reason = selected_ids[str(candidate.decision_id)]
        out.append(PriorityDecision(candidate, reason == "selected", score, reason, slot_i or None))
    return sorted(out, key=lambda d: (not d.selected, d.slot or 999, -d.score, d.candidate.decision_id))

