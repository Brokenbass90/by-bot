"""Research-only liquidity/room audit for ATT1 short geometry.

The production ATT1 contract proves that a mathematical pivot projection was
used.  It does not prove that the projection is the market level responsible
for the reaction, that the signal actually reached it, or that enough room
remains before the nearest opposing support.  This module makes those claims
explicit for the Geometry V2 challenger without changing the live champion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import inf, isfinite
from typing import Any, Sequence

from bot.chart_geometry import (
    _atr_from_rows,
    cluster_horizontal_levels,
    find_pivots,
    pivot_trendlines,
)
from bot.liquidity_map import LiqMapConfig, LiquidityMap


@dataclass(frozen=True)
class Att1ShortGeometryV2Decision:
    allowed: bool
    classification: str
    blockers: tuple[str, ...]
    atr: float
    trendline_level: float | None
    slope_pct_per_day: float | None
    r2: float | None
    pivot_count: int
    pivot_anchors: tuple[tuple[int, int, float], ...]
    pivot_sequence_descending: bool | None
    countertrend_pivot_steps: int
    max_countertrend_pivot_step_atr: float | None
    signal_high: float
    entry: float
    entry_distance_atr: float | None
    line_touch_gap_atr: float | None
    horizontal_origin: float | None
    horizontal_origin_touches: int
    horizontal_origin_source: str | None
    nearest_support: float | None
    nearest_support_source: str | None
    room_to_support_r: float | None
    signal_reached_line: bool

    @property
    def primary_blocker(self) -> str:
        return self.blockers[0] if self.blockers else "allowed"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_PROFILE_BLOCKERS: dict[str, frozenset[str]] = {
    "line_quality": frozenset(
        {
            "no_resistance_trendline",
            "insufficient_confirmed_pivots",
            "resistance_not_descending",
            "pivot_fit_too_weak",
        }
    ),
    "pivot_sequence": frozenset({"non_monotonic_resistance_pivots"}),
    "touch_lateness": frozenset(
        {
            "projected_line_not_reached",
            "entry_above_resistance",
            "entry_too_far_after_rejection",
        }
    ),
    "room": frozenset({"opposing_support_too_close"}),
    "attribution": frozenset({"setup_belongs_to_horizontal_family"}),
}


def enforced_geometry_v2_blockers(
    decision: Att1ShortGeometryV2Decision,
    profile: str,
) -> tuple[str, ...]:
    """Select preregistered blocker families for decomposition experiments."""
    normalized = str(profile or "all").strip().lower()
    if normalized == "all":
        selected = set(decision.blockers)
    else:
        families = [part.strip() for part in normalized.split("+") if part.strip()]
        if not families or any(part not in _PROFILE_BLOCKERS for part in families):
            # Unknown profiles fail closed in case a deployment typo ever
            # reaches this research path.
            selected = set(decision.blockers)
        else:
            allowed_names: set[str] = set()
            for family in families:
                allowed_names.update(_PROFILE_BLOCKERS[family])
            selected = {blocker for blocker in decision.blockers if blocker in allowed_names}
    if "invalid_or_short_geometry_input" in decision.blockers:
        selected.add("invalid_or_short_geometry_input")
    return tuple(blocker for blocker in decision.blockers if blocker in selected)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def descending_pivot_sequence_quality(
    prices: Sequence[float],
    *,
    atr: float,
    max_countertrend_step_atr: float = 0.0,
) -> dict[str, Any]:
    """Describe whether short resistance anchors are actual lower highs.

    A negative regression slope can hide a final higher high when the oldest
    anchor is far above the others.  This helper records that distinction for
    a research-only challenger; it does not alter the ATT1 champion by itself.
    """
    values = [float(value) for value in prices]
    if len(values) < 2 or not isfinite(float(atr)) or float(atr) <= 0.0:
        return {
            "descending": None,
            "countertrend_steps": 0,
            "max_countertrend_step_atr": None,
        }
    tolerance = max(0.0, float(max_countertrend_step_atr))
    steps_atr = [
        (values[index] - values[index - 1]) / float(atr)
        for index in range(1, len(values))
    ]
    countertrend = [step for step in steps_atr if step > tolerance]
    return {
        "descending": not countertrend,
        "countertrend_steps": len(countertrend),
        "max_countertrend_step_atr": max(countertrend, default=0.0),
    }


def evaluate_att1_short_geometry_v2(
    rows: Sequence[Sequence[Any]],
    *,
    entry: float,
    sl: float,
    pivot_left: int = 2,
    pivot_right: int = 3,
    max_pivots_used: int = 3,
    max_pivot_age: int = 16,
    min_descending_slope_pct_day: float = 0.03,
    min_r2: float = 0.65,
    max_entry_distance_atr: float = 0.75,
    max_touch_miss_atr: float = 0.10,
    min_room_to_support_r: float = 0.80,
    horizontal_tolerance_atr: float = 0.35,
) -> Att1ShortGeometryV2Decision:
    """Audit whether a short belongs to a tradable descending-line setup.

    A valid V2 short must use a confirmed descending resistance, actually reach
    its projected zone, execute before the rejection becomes stale, and retain
    adequate room before the nearest confirmed horizontal support.  A strong
    horizontal resistance near the reaction is reported separately so a flat
    fade is not mislabeled as ATT1.
    """
    sample = list(rows)
    signal_high = _f(sample[-1][2]) if sample else 0.0
    atr = _atr_from_rows(sample, 14) if sample else 0.0
    risk = float(sl) - float(entry)
    blockers: list[str] = []

    if len(sample) < 20 or atr <= 0.0 or risk <= 0.0:
        blockers.append("invalid_or_short_geometry_input")
        return Att1ShortGeometryV2Decision(
            allowed=False,
            classification="invalid",
            blockers=tuple(blockers),
            atr=float(atr),
            trendline_level=None,
            slope_pct_per_day=None,
            r2=None,
            pivot_count=0,
            pivot_anchors=(),
            pivot_sequence_descending=None,
            countertrend_pivot_steps=0,
            max_countertrend_pivot_step_atr=None,
            signal_high=float(signal_high),
            entry=float(entry),
            entry_distance_atr=None,
            line_touch_gap_atr=None,
            horizontal_origin=None,
            horizontal_origin_touches=0,
            horizontal_origin_source=None,
            nearest_support=None,
            nearest_support_source=None,
            room_to_support_r=None,
            signal_reached_line=False,
        )

    lines = pivot_trendlines(
        sample,
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        max_pivots_used=max_pivots_used,
        max_pivot_age=max_pivot_age,
        min_r2=0.0,
        min_slope_pct_day=0.0,
        max_slope_pct_day=999.0,
        resistance_max_positive_pct_day=999.0,
    )
    resistance = dict(lines.get("resistance") or {})
    trendline_level = _f(resistance.get("projection_now"), float("nan"))
    slope_pct_day = _f(resistance.get("slope_pct_per_day"), float("nan"))
    r2 = _f(resistance.get("r2"), float("nan"))
    pivot_count = int(resistance.get("pivot_count") or 0)
    pivot_anchors = tuple(
        (
            int(point.get("index") or 0),
            int(point.get("ts_ms") or 0),
            _f(point.get("price")),
        )
        for point in list(resistance.get("pivots") or [])
    )
    pivot_sequence = descending_pivot_sequence_quality(
        [point[2] for point in pivot_anchors],
        atr=float(atr),
    )

    if not resistance:
        blockers.append("no_resistance_trendline")
        trendline_level = float("nan")
        slope_pct_day = float("nan")
        r2 = float("nan")
    else:
        if pivot_count < 3:
            blockers.append("insufficient_confirmed_pivots")
        if slope_pct_day > -abs(float(min_descending_slope_pct_day)):
            blockers.append("resistance_not_descending")
        if pivot_sequence["descending"] is False:
            blockers.append("non_monotonic_resistance_pivots")
        if r2 < float(min_r2):
            blockers.append("pivot_fit_too_weak")

    entry_distance_atr = None
    touch_gap_atr = None
    signal_reached_line = False
    if trendline_level == trendline_level:
        entry_distance_atr = (trendline_level - float(entry)) / atr
        touch_gap_atr = (trendline_level - signal_high) / atr
        signal_reached_line = bool(signal_high >= trendline_level)
        if touch_gap_atr > float(max_touch_miss_atr):
            blockers.append("projected_line_not_reached")
        if entry_distance_atr < 0.0:
            blockers.append("entry_above_resistance")
        elif entry_distance_atr > float(max_entry_distance_atr):
            blockers.append("entry_too_far_after_rejection")

    pivots = find_pivots(sample, left=pivot_left, right=pivot_right)
    levels = cluster_horizontal_levels(
        sample,
        pivots,
        atr=atr,
        tolerance_atr=horizontal_tolerance_atr,
        min_touches=2,
        max_levels=16,
    )
    # Fractal levels alone can miss equal-high/equal-low liquidity pools.  Use
    # both independent detectors and retain provenance so the chart can prove
    # which market structure actually caused a veto.
    liquidity = LiquidityMap(
        LiqMapConfig(
            pivot_left=2,
            pivot_right=2,
            cluster_tol_pct=0.25,
            min_touches=2,
            max_age_bars=max(20, len(sample)),
        )
    ).build(
        [_f(row[2]) for row in sample],
        [_f(row[3]) for row in sample],
    )

    origin_candidates: list[tuple[float, int, str]] = [
        (float(level.price), int(level.touches), "horizontal_pivots")
        for level in levels
        if level.price > float(entry) and level.side_bias in {"resistance", "mixed"}
    ]
    origin_candidates.extend(
        (float(pool.price), int(pool.touches), "equal_high_liquidity")
        for pool in liquidity.get("above", [])
        if pool.price > float(entry)
    )
    origin_candidates.sort(key=lambda item: (abs(item[0] - signal_high), -item[1]))
    origin = origin_candidates[0] if origin_candidates else None

    support_candidates: list[tuple[float, int, str]] = [
        (float(level.price), int(level.touches), "horizontal_pivots")
        for level in levels
        if level.price < float(entry) and level.side_bias in {"support", "mixed"}
    ]
    support_candidates.extend(
        (float(pool.price), int(pool.touches), "equal_low_liquidity")
        for pool in liquidity.get("below", [])
        if pool.price < float(entry)
    )
    support_candidates.sort(key=lambda item: float(entry) - item[0])
    support = support_candidates[0] if support_candidates else None
    room_r = inf if support is None else (float(entry) - support[0]) / risk
    if support is not None and room_r < float(min_room_to_support_r):
        blockers.append("opposing_support_too_close")

    classification = "descending_trendline_rejection"
    if origin is not None and abs(origin[0] - signal_high) <= atr * horizontal_tolerance_atr:
        classification = "horizontal_resistance_rejection"
        origin_gap = abs(origin[0] - signal_high)
        line_gap = inf if trendline_level != trendline_level else abs(trendline_level - signal_high)
        if (
            slope_pct_day == slope_pct_day
            and (slope_pct_day >= 0.0 or r2 < float(min_r2) or origin_gap <= line_gap)
        ):
            blockers.append("setup_belongs_to_horizontal_family")

    return Att1ShortGeometryV2Decision(
        allowed=not blockers,
        classification=classification,
        blockers=tuple(dict.fromkeys(blockers)),
        atr=float(atr),
        trendline_level=None if trendline_level != trendline_level else float(trendline_level),
        slope_pct_per_day=None if slope_pct_day != slope_pct_day else float(slope_pct_day),
        r2=None if r2 != r2 else float(r2),
        pivot_count=int(pivot_count),
        pivot_anchors=pivot_anchors,
        pivot_sequence_descending=pivot_sequence["descending"],
        countertrend_pivot_steps=int(pivot_sequence["countertrend_steps"]),
        max_countertrend_pivot_step_atr=(
            None
            if pivot_sequence["max_countertrend_step_atr"] is None
            else float(pivot_sequence["max_countertrend_step_atr"])
        ),
        signal_high=float(signal_high),
        entry=float(entry),
        entry_distance_atr=None if entry_distance_atr is None else float(entry_distance_atr),
        line_touch_gap_atr=None if touch_gap_atr is None else float(touch_gap_atr),
        horizontal_origin=None if origin is None else float(origin[0]),
        horizontal_origin_touches=0 if origin is None else int(origin[1]),
        horizontal_origin_source=None if origin is None else str(origin[2]),
        nearest_support=None if support is None else float(support[0]),
        nearest_support_source=None if support is None else str(support[2]),
        room_to_support_r=None if support is None else float(room_r),
        signal_reached_line=bool(signal_reached_line),
    )
