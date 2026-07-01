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
from typing import Any, Dict, Iterable, List, Optional, Sequence

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

    def best_level(
        self,
        side: str,
        *,
        min_touches: int = 0,
        kinds: Optional[Sequence[str]] = None,
        max_dist_atr: Optional[float] = None,
    ) -> Optional[Level]:
        """Nearest usable level for a side, after optional quality filters."""
        allowed = set(kinds or [])
        cands: List[Level] = []
        for lv in self.levels:
            if lv.side != side:
                continue
            if allowed and lv.kind not in allowed:
                continue
            if max_dist_atr is not None and lv.dist_atr > max_dist_atr:
                continue
            if int(lv.meta.get("touches", 0) or 0) < min_touches:
                continue
            cands.append(lv)
        return min(cands, key=lambda l: (l.dist_atr, -_LEVEL_PRIORITY.get(l.kind, 0))) if cands else None


_LEVEL_PRIORITY = {
    "horizontal": 60,
    "sloped": 50,
    "flip": 45,
    "hvn": 35,
    "liquidity": 20,
    "round": 10,
}


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
    max_age_bars: Optional[int] = None,
    pool_lookback: int = 20,
    include_round: bool = False,        # on for FX/round-level strategies
    include_liquidity: bool = True,
    merge_tol_atr: float = 0.12,
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
    window = list(rows[-int(max(lookback, 1)):])
    max_age = int(max_age_bars if max_age_bars is not None else lookback)

    def add(p: float, kind: str, meta=None):
        if not (p == p and p > 0):
            return
        side = "support" if p <= price else "resistance"
        levels.append(Level(p, kind, side, abs(p - price) / a, meta or {}))

    def fresh(lv: Dict[str, Any]) -> bool:
        last_idx = lv.get("last_idx")
        if last_idx is None:
            return True
        try:
            age = (len(window) - 1) - int(last_idx)
        except (TypeError, ValueError):
            return True
        return age <= max_age

    # horizontal touch clusters (both sides)
    for lv in horizontal_levels(window, side="support", atr_value=a, min_touches=min_touches):
        if not fresh(lv):
            continue
        add(float(lv["level"]), "horizontal", {"touches": lv.get("touches"), "last_idx": lv.get("last_idx")})
    for lv in horizontal_levels(window, side="resistance", atr_value=a, min_touches=min_touches):
        if not fresh(lv):
            continue
        add(float(lv["level"]), "horizontal", {"touches": lv.get("touches"), "last_idx": lv.get("last_idx")})

    # sloped channel lines
    ch = classify_channel(window, atr_value=a, lookback=min(lookback, len(window)))
    add(ch.get("upper_now", float("nan")), "sloped", {"r2": ch.get("upper_r2"), "regime": ch.get("regime")})
    add(ch.get("lower_now", float("nan")), "sloped", {"r2": ch.get("lower_r2"), "regime": ch.get("regime")})

    # volume HVN nodes
    for p in volume_hvns(window):
        add(float(p), "hvn", {})

    # flip / broken levels (former resistance now support and vice versa)
    res_lv = [lv for lv in horizontal_levels(window, side="resistance", atr_value=a, min_touches=min_touches) if fresh(lv)]
    sup_lv = [lv for lv in horizontal_levels(window, side="support", atr_value=a, min_touches=min_touches) if fresh(lv)]
    bsup = nearest_broken_level(window, res_lv, price, a, "support", max_age_bars=max_age)
    if bsup:
        add(float(bsup["level"]), "flip", {"was": "resistance"})
    bres = nearest_broken_level(window, sup_lv, price, a, "resistance", max_age_bars=max_age)
    if bres:
        add(float(bres["level"]), "flip", {"was": "support"})

    # liquidity pools (recent swing extremes where stops cluster)
    if include_liquidity:
        prior = window[-pool_lookback - 1:-1]
        if prior:
            add(max(_f(r, HIGH) for r in prior), "liquidity", {"pool": "high", "note": "recent_extreme"})
            add(min(_f(r, LOW) for r in prior), "liquidity", {"pool": "low", "note": "recent_extreme"})

    # round / session levels (FX)
    if include_round:
        for p in _round_levels(price, a):
            add(p, "round", {})

    levels = _merge_nearby_levels(levels, atr_value=a, merge_tol_atr=merge_tol_atr)
    sups = [l for l in levels if l.side == "support"]
    ress = [l for l in levels if l.side == "resistance"]
    nsup = min(sups, key=lambda l: l.dist_atr) if sups else None
    nres = min(ress, key=lambda l: l.dist_atr) if ress else None
    return LevelSet(True, price, a, levels, nsup, nres, "ok")


def _merge_nearby_levels(levels: Iterable[Level], *, atr_value: float, merge_tol_atr: float) -> List[Level]:
    """Collapse duplicate levels inside the same zone, preserving best source."""
    src = sorted(levels, key=lambda l: (l.side, l.price))
    if merge_tol_atr <= 0 or not src:
        return list(src)
    tol = merge_tol_atr * atr_value
    out: List[Level] = []
    for side in ("support", "resistance"):
        side_levels = [l for l in src if l.side == side]
        groups: List[List[Level]] = []
        for lv in side_levels:
            if not groups or abs(lv.price - groups[-1][-1].price) > tol:
                groups.append([lv])
            else:
                groups[-1].append(lv)
        for group in groups:
            best = max(group, key=lambda l: (_LEVEL_PRIORITY.get(l.kind, 0), -l.dist_atr))
            kinds = sorted({g.kind for g in group})
            merged = Level(
                best.price,
                best.kind,
                best.side,
                best.dist_atr,
                {**best.meta, "merged_kinds": kinds, "merged_count": len(group)},
            )
            out.append(merged)
    return sorted(out, key=lambda l: l.dist_atr)
