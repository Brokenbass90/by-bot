"""Funding-carry coin picker — selects coins for the carry arm (NOT directional).

The directional picker (scripts/strategy_scorer) scores coins by current PRICE
state. Carry is a different edge, so it needs a different picker: rank coins by
PERSISTENT, CONSISTENT funding you can harvest — high average funding, paid in
the same direction most of the time, on a liquid-enough market. The carry trade
collects funding by holding the perp leg hedged (e.g. short perp + long spot
when funding is positive), so we want coins where funding stays one-signed.

Composes with bot.cross_sectional (rank top-K) and bot.funding_carry_gate
(net-after-hedge GO/NO-GO). Pure / testable / additive — Codex feeds real
funding history (funding_rate_fetcher / historical store) and a liquidity flag.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

FUNDING_PERIODS_PER_YEAR = 3 * 365  # 8h funding -> 3 per day


def annualized_funding(funding_rates: Sequence[float]) -> float:
    """Mean per-interval funding -> annualized fraction (sign preserved)."""
    vals = [float(x) for x in funding_rates if isinstance(x, (int, float))]
    if not vals:
        return 0.0
    return (sum(vals) / len(vals)) * FUNDING_PERIODS_PER_YEAR


def consistency(funding_rates: Sequence[float]) -> float:
    """Fraction of intervals with the SAME sign as the mean (1.0 = never flips)."""
    vals = [float(x) for x in funding_rates if isinstance(x, (int, float))]
    if not vals:
        return 0.0
    mean = sum(vals) / len(vals)
    if mean == 0:
        return 0.0
    same = sum(1 for x in vals if (x > 0) == (mean > 0))
    return same / len(vals)


def carry_score(funding_rates: Sequence[float], *, liquid: bool = True,
                min_annual: float = 0.03, min_consistency: float = 0.6) -> float:
    """0..1 carry fitness. 0 if illiquid, funding too small, or flips too often.

    Rewards high annualized |funding| that is one-signed and consistent.
    """
    if not liquid:
        return 0.0
    ann = abs(annualized_funding(funding_rates))
    cons = consistency(funding_rates)
    if ann < min_annual or cons < min_consistency:
        return 0.0
    # squashing: 30% annualized funding ~ saturates; weight by consistency
    mag = 1.0 - math.exp(-ann / 0.30)
    return round(mag * cons, 4)


def rank_carry_candidates(symbol_funding: Dict[str, Sequence[float]], *, k: int = 8,
                          liquidity: Optional[Dict[str, bool]] = None,
                          min_annual: float = 0.03,
                          min_consistency: float = 0.6) -> List[Tuple[str, float, str]]:
    """Return top-k (symbol, score, side) for the carry arm.

    side = 'short_perp' when funding positive (collect from longs), else 'long_perp'.
    """
    liquidity = liquidity or {}
    scored: List[Tuple[str, float, str]] = []
    for sym, fr in symbol_funding.items():
        sc = carry_score(fr, liquid=liquidity.get(sym, True),
                         min_annual=min_annual, min_consistency=min_consistency)
        if sc <= 0:
            continue
        side = "short_perp" if annualized_funding(fr) > 0 else "long_perp"
        scored.append((sym, sc, side))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[: max(0, int(k))]
