"""Unified level provider — ONE call gives every strategy ALL level types.

Today each leg computes a SUBSET of levels (ATT1 sloped only, InPlay horizontal+flip,
ARF2 not on the contract). That's inconsistent and leaves edges on the table. This
aggregates every level source market_context knows about into one typed LevelSet so
any sleeve consumes the complete picture and can fade/bounce/break at the nearest
REAL level regardless of which mechanism produced it.

Types: horizontal (touch clusters), sloped (channel/trendlines), hvn (volume nodes),
flip (recently broken levels acting as opposite), liquidity (recent swing pools),
round (round-number / FX levels). Row [ts,o,h,l,c,v]. Pure stdlib + market_context.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.market_context import (
    horizontal_levels, sloped_level, volume_hvns, nearest_broken_level,
    classify_channel, atr, HIGH, LOW, CLOSE,
)


def _f(row, i):
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


@dataclass
class Level:
    price: float
    kind: str                 # horizontal|sloped|hvn|flip|liquidity|round
    side: str                 # "support" (below price) | "resistance" (above price)
    dist_atr: float
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LevelSet:
    ok: bool
    price: float
    atr: float
    levels: List[Level]
    nearest_support: Optional[Level]
    nearest_resistance: Optional[Level]
    reason: str = ""

    def by_kind(self, kind: str) -> List[Level]:
        return [l for l in self.levels if l.kind == kind]


def _round_levels(price: float, atr_value: float, n: int = 2) -> List[float]:
    if not (price == price and price > 0):
        return []
    step = 10 ** (math.floor(math.log10(price)) - 1)   # ~1% grid
    base = round(price / step) * step
    return [base + k * step for k in range(-n, n + 1) if base + k * step > 0]


def unified_levels(
    rows: Sequence[Sequence[float]],
    *,
    lookback: int = 60,
    min_touches: int = 2,
    pool_lookback: int = 20,
    include_round: bool = False,        # on for FX/round-level strategies
    atr_value: Optional[float] = None,
) -> LevelSet:
    """Aggregate all level types into one typed set with nearest support/resistance."""
    n = len(rows)
    if n < max(lookback, pool_lookback + 2, 20):
        return LevelSet(False, float("nan"), float("nan"), [], None, None, "insufficient_data")
    a = float(atr_value) if (atr_value is not None and atr_value == atr_value and atr_value > 0) else atr(rows)
    if not (a == a and a > 0):
        return LevelSet(False, float("nan"), float("nan"), [], None, None, "no_atr")
    price = _f(rows[-1], CLOSE)
    levels: List[Level] = []

    def add(p: float, kind: str, meta=None):
        if not (p == p and p > 0):
            return
        side = "support" if p <= price else "resistance"
        levels.append(Level(p, kind, side, abs(p - price) / a, meta or {}))

    # horizontal touch clusters (both sides)
    for lv in horizontal_levels(rows, side="support", atr_value=a, min_touches=min_touches):
        add(float(lv["level"]), "horizontal", {"touches": lv.get("touches"), "last_idx": lv.get("last_idx")})
    for lv in horizontal_levels(rows, side="resistance", atr_value=a, min_touches=min_touches):
        add(float(lv["level"]), "horizontal", {"touches": lv.get("touches"), "last_idx": lv.get("last_idx")})

    # sloped channel lines
    ch = classify_channel(rows, atr_value=a, lookback=lookback)
    add(ch.get("upper_now", float("nan")), "sloped", {"r2": ch.get("upper_r2"), "regime": ch.get("regime")})
    add(ch.get("lower_now", float("nan")), "sloped", {"r2": ch.get("lower_r2"), "regime": ch.get("regime")})

    # volume HVN nodes
    for p in volume_hvns(rows):
        add(float(p), "hvn", {})

    # flip / broken levels (former resistance now support and vice versa)
    res_lv = horizontal_levels(rows, side="resistance", atr_value=a, min_touches=min_touches)
    sup_lv = horizontal_levels(rows, side="support", atr_value=a, min_touches=min_touches)
    bsup = nearest_broken_level(rows, res_lv, price, a, "support")
    if bsup:
        add(float(bsup["level"]), "flip", {"was": "resistance"})
    bres = nearest_broken_level(rows, sup_lv, price, a, "resistance")
    if bres:
        add(float(bres["level"]), "flip", {"was": "support"})

    # liquidity pools (recent swing extremes where stops cluster)
    prior = rows[-pool_lookback - 1:-1]
    add(max(_f(r, HIGH) for r in prior), "liquidity", {"pool": "high"})
    add(min(_f(r, LOW) for r in prior), "liquidity", {"pool": "low"})

    # round / session levels (FX)
    if include_round:
        for p in _round_levels(price, a):
            add(p, "round", {})

    sups = [l for l in levels if l.side == "support"]
    ress = [l for l in levels if l.side == "resistance"]
    nsup = min(sups, key=lambda l: l.dist_atr) if sups else None
    nres = min(ress, key=lambda l: l.dist_atr) if ress else None
    return LevelSet(True, price, a, levels, nsup, nres, "ok")
