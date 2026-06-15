"""Cross-sectional selection — "rank, don't threshold".

The 0-candidates problem comes partly from FIXED entry thresholds (ATT1 R2>=0.80,
ASB1 5-condition regime band) that, in many regimes, cut ~90% of candidates and
leave too few trades to validate. Cross-sectional selection fixes this: instead
of "trade if score > fixed_cutoff", rank the WHOLE universe each bar by signal
strength and take the top-K (or top fraction). Frequency then adapts to current
conditions instead of collapsing to zero — and you always act on the *relatively*
best setups, which is what a portfolio actually wants.

Pairs with the existing per-strategy scorer (scripts/strategy_scorer): score all
coins for a strategy, then select cross-sectionally here. Pure / testable /
additive — does not touch the live trade path; Codex wires it as the selection
layer (replacing or complementing fixed allowlists).
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple


def select_top_k(scores: Dict[str, float], k: int, *, min_score: float = 0.0) -> List[Tuple[str, float]]:
    """Top-k symbols by score, descending, keeping only score >= min_score."""
    ranked = [(s, float(v)) for s, v in scores.items()
              if isinstance(v, (int, float)) and not math.isnan(float(v)) and float(v) >= min_score]
    ranked.sort(key=lambda kv: kv[1], reverse=True)
    return ranked[: max(0, int(k))]


def select_top_fraction(scores: Dict[str, float], frac: float = 0.2, *,
                        min_score: float = 0.0, min_count: int = 1,
                        max_count: int = 8) -> List[Tuple[str, float]]:
    """Adaptive: take the top `frac` of the universe (clamped to [min,max] count).

    Universe of 60 with frac 0.2 -> ~12 candidates; universe of 10 -> ~2. Keeps a
    sane absolute count so we never over-trade a huge universe nor starve a small one.
    """
    eligible = [(s, float(v)) for s, v in scores.items()
                if isinstance(v, (int, float)) and not math.isnan(float(v)) and float(v) >= min_score]
    if not eligible:
        return []
    k = int(round(len(eligible) * float(frac)))
    k = max(int(min_count), min(int(max_count), k))
    eligible.sort(key=lambda kv: kv[1], reverse=True)
    return eligible[:k]


def zscore_gate(scores: Dict[str, float], *, z_min: float = 1.0) -> List[Tuple[str, float]]:
    """Relative gate: keep symbols whose score is z_min std-devs above the mean.

    Adapts to the distribution: in a flat market few clear leaders pass; in a
    strong one, more do. Avoids brittle absolute cutoffs.
    """
    vals = [float(v) for v in scores.values()
            if isinstance(v, (int, float)) and not math.isnan(float(v))]
    if len(vals) < 3:
        return select_top_k(scores, 1)
    mean = sum(vals) / len(vals)
    var = sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
    sd = math.sqrt(max(0.0, var))
    if sd <= 1e-12:
        return []
    out = [(s, float(v)) for s, v in scores.items()
           if isinstance(v, (int, float)) and (float(v) - mean) / sd >= z_min]
    out.sort(key=lambda kv: kv[1], reverse=True)
    return out
