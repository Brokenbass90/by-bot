"""Causal, research-only FX/CFD V3 setup candidates.

V2 showed that generic same-bar sweeps, sloped range entries, and broad
trend/retest logic did not survive costs.  V3 narrows the hypotheses:

* ``failed_break_retest_short_v3``: a completed break above a frozen horizontal
  range, a later reclaim, and only then the first failed retest from below;
* ``horizontal_range_rejection_v3``: rejection of a frozen *horizontal* range
  edge in a flat/ranging regime, with long and short evaluated separately;
* ``range_edge_expansion_retest_v3``: expansion out of a frozen horizontal
  range followed by the first intact retest, again side-separated.

Every function consumes a closed H1 prefix and emits a plan that may fill only
on a later bar through ``bot.fx_harness_v2``.  There are no broker/live imports.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

from bot.fx_calendar import session_labels
from bot.fx_contracts import FxEvent, FxInstrumentSpec, FxTradePlan
from bot.level_memory import level_respect
from bot.market_context import CLOSE, HIGH, LOW, OPEN, TS, VOL, atr, horizontal_levels
from bot.news_session_filter import entry_allowed
from bot.range_filter import RangeState, range_state


H1_SECONDS = 3600


def _f(row: Sequence[float], idx: int) -> float:
    try:
        return float(row[idx])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def _shape(row: Sequence[float]) -> Dict[str, float]:
    o, h, l, c = (_f(row, idx) for idx in (OPEN, HIGH, LOW, CLOSE))
    width = max(1e-12, h - l)
    return {
        "o": o,
        "h": h,
        "l": l,
        "c": c,
        "body": abs(c - o),
        "range": width,
        "lower_wick": max(0.0, min(o, c) - l),
        "upper_wick": max(0.0, h - max(o, c)),
        "close_location": (c - l) / width,
        "volume": _f(row, VOL),
    }


def _side(side_mode: str) -> str:
    side = str(side_mode).strip().lower()
    if side not in {"long", "short"}:
        raise ValueError("V3 candidates require a separate long or short sleeve")
    return side


def _session_news_ok(
    decision_ts: int,
    price: float,
    *,
    allowed_sessions: Sequence[str],
    events: Optional[Sequence[Dict[str, Any]]],
) -> bool:
    # A missing calendar is different from a validated calendar with no event
    # near this bar.  Research must fail closed until the historical calendar
    # adapter has supplied an explicit sequence.
    if events is None:
        return False
    if not set(session_labels(decision_ts)).intersection(allowed_sessions):
        return False
    return entry_allowed(
        decision_ts,
        events=events,
        price=price,
        avoid_low_liq_session=False,
    ).allow


def _event_id(family: str, instrument: str, side: str, event_ts: int, level: float) -> str:
    return f"{family}:{str(instrument).upper()}:{side}:{int(event_ts)}:{float(level):.8g}"


@dataclass(frozen=True)
class FrozenHorizontalRange:
    support: float
    resistance: float
    midpoint: float
    width: float
    width_atr: float
    atr_value: float
    support_touches: int
    resistance_touches: int
    range_votes: int
    ci: float
    vp: float
    adx: float
    source_last_ts: int


@dataclass(frozen=True)
class HorizontalRangeConfig:
    lookback: int = 72
    min_touches: int = 2
    tolerance_atr: float = 0.35
    min_width_atr: float = 2.0
    max_width_atr: float = 8.0
    min_range_votes: int = 2
    require_all_range_votes: bool = False


def freeze_horizontal_range(
    rows: Sequence[Sequence[float]],
    cfg: HorizontalRangeConfig,
) -> Optional[FrozenHorizontalRange]:
    """Freeze a bracketing horizontal range from the supplied historical bars."""
    base = list(rows[-max(30, int(cfg.lookback)) :])
    if len(base) < max(30, cfg.lookback):
        return None
    a = atr(base)
    if not (a == a and a > 0):
        return None
    rs: RangeState = range_state(
        base,
        lookback=cfg.lookback,
        require_all=cfg.require_all_range_votes,
        allow_sloped=False,
    )
    if not (
        rs.ok
        and rs.is_range
        and rs.regime == "flat"
        and rs.votes >= cfg.min_range_votes
    ):
        return None
    price = _f(base[-1], CLOSE)
    supports = horizontal_levels(
        base,
        side="support",
        atr_value=a,
        tol_atr=cfg.tolerance_atr,
        min_touches=cfg.min_touches,
    )
    resistances = horizontal_levels(
        base,
        side="resistance",
        atr_value=a,
        tol_atr=cfg.tolerance_atr,
        min_touches=cfg.min_touches,
    )
    below = [level for level in supports if float(level["level"]) < price]
    above = [level for level in resistances if float(level["level"]) > price]
    if not below or not above:
        return None
    support = max(below, key=lambda level: float(level["level"]))
    resistance = min(above, key=lambda level: float(level["level"]))
    lo, hi = float(support["level"]), float(resistance["level"])
    width = hi - lo
    width_atr = width / a
    if not (cfg.min_width_atr <= width_atr <= cfg.max_width_atr):
        return None
    return FrozenHorizontalRange(
        support=lo,
        resistance=hi,
        midpoint=(lo + hi) / 2.0,
        width=width,
        width_atr=width_atr,
        atr_value=a,
        support_touches=int(support.get("touches", 0)),
        resistance_touches=int(resistance.get("touches", 0)),
        range_votes=int(rs.votes),
        ci=float(rs.ci),
        vp=float(rs.vp),
        adx=float(rs.adx),
        source_last_ts=int(_f(base[-1], TS)),
    )


def _respect(
    rows: Sequence[Sequence[float]],
    level: float,
    *,
    side: str,
    min_resolved: int,
    min_score: float,
) -> tuple[bool, Dict[str, Any]]:
    stats = level_respect(
        list(rows),
        level,
        approach="from_above" if side == "long" else "from_below",
        min_history=30,
    )
    resolved = stats.bounces + stats.sweeps + stats.breaks
    score = stats.respect_score
    rated = resolved >= int(min_resolved)
    return (
        (not rated) or (score == score and score >= min_score),
        {
            "respect_rated": rated,
            "respect_score": score if score == score else None,
            "respect_resolved": resolved,
            "respect_bounces": stats.bounces,
            "respect_sweeps": stats.sweeps,
            "respect_breaks": stats.breaks,
        },
    )


@dataclass(frozen=True)
class FailedBreakRetestShortConfig:
    context_bars: int = 320
    range: HorizontalRangeConfig = field(default_factory=HorizontalRangeConfig)
    max_event_age_bars: int = 12
    min_break_body_atr: float = 0.25
    min_break_close_atr: float = 0.10
    min_break_close_location: float = 0.65
    max_reclaim_bars: int = 4
    reclaim_inside_atr: float = 0.04
    require_volume_fade: bool = True
    retest_touch_atr: float = 0.18
    retest_close_below_atr: float = 0.03
    min_retest_upper_wick_atr: float = 0.05
    max_retest_extension_atr: float = 0.35
    invalidation_close_atr: float = 0.08
    stop_buffer_atr: float = 0.12
    min_structural_rr: float = 1.15
    fallback_target_rr: float = 1.8
    max_hold_bars: int = 60
    min_respect_score: float = 0.35
    min_resolved_reactions: int = 2
    allowed_sessions: tuple[str, ...] = ("london", "london_ny_overlap", "newyork")


def failed_break_retest_short_v3(
    rows: Sequence[Sequence[float]],
    *,
    instrument: FxInstrumentSpec,
    cfg: Optional[FailedBreakRetestShortConfig] = None,
    events: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[FxTradePlan]:
    """Completed break up -> reclaim down -> later first retest from below."""
    cfg = cfg or FailedBreakRetestShortConfig()
    window = list(rows[-cfg.context_bars :])
    minimum = cfg.range.lookback + cfg.max_event_age_bars + 30
    if len(window) < minimum:
        return None
    current = _shape(window[-1])
    signal_bar_ts = int(_f(window[-1], TS))
    decision_ts = signal_bar_ts + H1_SECONDS
    if not _session_news_ok(
        decision_ts,
        current["c"],
        allowed_sessions=cfg.allowed_sessions,
        events=events,
    ):
        return None
    a = atr(window, exclude_last=True)
    if not (a == a and a > 0):
        return None

    # age>=2 forces both a later reclaim and a later retest/signal bar.
    for age in range(2, cfg.max_event_age_bars + 1):
        break_i = len(window) - 1 - age
        base = window[break_i - cfg.range.lookback : break_i]
        frozen = freeze_horizontal_range(base, cfg.range)
        if frozen is None:
            continue
        level = frozen.resistance
        event_a = frozen.atr_value
        break_bar = _shape(window[break_i])
        break_distance = break_bar["c"] - level
        if not (
            break_bar["c"] > break_bar["o"]
            and break_bar["body"] >= cfg.min_break_body_atr * event_a
            and break_distance >= cfg.min_break_close_atr * event_a
            and break_bar["close_location"] >= cfg.min_break_close_location
        ):
            continue

        reclaim_i: Optional[int] = None
        reclaim_limit = min(len(window) - 2, break_i + cfg.max_reclaim_bars)
        for idx in range(break_i + 1, reclaim_limit + 1):
            bar = _shape(window[idx])
            if bar["c"] <= level - cfg.reclaim_inside_atr * event_a:
                if not cfg.require_volume_fade or bar["volume"] < break_bar["volume"]:
                    reclaim_i = idx
                    break
        if reclaim_i is None or reclaim_i >= len(window) - 1:
            continue

        # A close back above invalidates; an earlier post-reclaim touch consumes
        # the only first-retest opportunity for this break event.
        intact = True
        for row in window[reclaim_i + 1 : -1]:
            if (
                _f(row, CLOSE) > level + cfg.invalidation_close_atr * event_a
                or _f(row, HIGH) >= level - cfg.retest_touch_atr * a
            ):
                intact = False
                break
        if not intact:
            continue
        extension = (level - current["c"]) / a
        retest_ok = (
            current["h"] >= level - cfg.retest_touch_atr * a
            and current["c"] <= level - cfg.retest_close_below_atr * a
            and current["upper_wick"] >= cfg.min_retest_upper_wick_atr * a
            and current["close_location"] <= 0.45
            and 0 <= extension <= cfg.max_retest_extension_atr
        )
        if not retest_ok:
            continue
        stop = max(
            max(_f(row, HIGH) for row in window[break_i : reclaim_i + 1]),
            current["h"],
        ) + cfg.stop_buffer_atr * a
        risk = stop - current["c"]
        target = frozen.midpoint
        structural_rr = (current["c"] - target) / risk if risk > 0 else -1.0
        if structural_rr < cfg.min_structural_rr:
            continue
        respect_ok, respect = _respect(
            base,
            level,
            side="short",
            min_resolved=cfg.min_resolved_reactions,
            min_score=cfg.min_respect_score,
        )
        if not respect_ok:
            continue
        break_ts = int(_f(window[break_i], TS))
        reclaim_ts = int(_f(window[reclaim_i], TS))
        event = FxEvent(
            event_id=_event_id(
                "failed_break_retest_short_v3",
                instrument.symbol,
                "short",
                break_ts,
                level,
            ),
            family="failed_break_retest_short_v3",
            side="short",
            signal_ts=decision_ts,
            level=level,
            level_kind="horizontal_range_resistance",
            reason="break_reclaim_then_first_failed_retest",
            metadata={
                "instrument": instrument.symbol,
                "break_ts": break_ts,
                "reclaim_ts": reclaim_ts,
                "signal_bar_ts": signal_bar_ts,
                "event_age_bars": age,
                "break_distance_atr": break_distance / event_a,
                "event_atr": event_a,
                "signal_atr": a,
                "range_width_atr": frozen.width_atr,
                "range_votes": frozen.range_votes,
                "structural_rr": structural_rr,
                **respect,
            },
        )
        return FxTradePlan(
            event=event,
            entry_type="market_next_open",
            reference_price=current["c"],
            stop_price=stop,
            target_price=target,
            target_rr=max(cfg.fallback_target_rr, structural_rr),
            max_hold_bars=cfg.max_hold_bars,
            validity_bars=1,
            allowed_fill_sessions=cfg.allowed_sessions,
            metadata={"atr": a, "sessions": session_labels(decision_ts)},
        )
    return None


@dataclass(frozen=True)
class HorizontalRangeRejectionConfig:
    context_bars: int = 280
    range: HorizontalRangeConfig = field(default_factory=HorizontalRangeConfig)
    edge_touch_atr: float = 0.15
    max_penetration_atr: float = 0.45
    reclaim_inside_atr: float = 0.04
    min_wick_atr: float = 0.08
    min_close_location: float = 0.58
    min_bars_since_edge_touch: int = 3
    stop_buffer_atr: float = 0.12
    min_structural_rr: float = 1.15
    fallback_target_rr: float = 1.5
    max_hold_bars: int = 48
    min_respect_score: float = 0.40
    min_resolved_reactions: int = 3
    allowed_sessions: tuple[str, ...] = ("london", "london_ny_overlap", "newyork")


def horizontal_range_rejection_v3(
    rows: Sequence[Sequence[float]],
    *,
    instrument: FxInstrumentSpec,
    side_mode: str,
    cfg: Optional[HorizontalRangeRejectionConfig] = None,
    events: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[FxTradePlan]:
    side = _side(side_mode)
    cfg = cfg or HorizontalRangeRejectionConfig()
    window = list(rows[-cfg.context_bars :])
    if len(window) < cfg.range.lookback + 35:
        return None
    current = _shape(window[-1])
    signal_bar_ts = int(_f(window[-1], TS))
    decision_ts = signal_bar_ts + H1_SECONDS
    if not _session_news_ok(
        decision_ts,
        current["c"],
        allowed_sessions=cfg.allowed_sessions,
        events=events,
    ):
        return None
    base = window[:-1]
    frozen = freeze_horizontal_range(base, cfg.range)
    if frozen is None:
        return None
    a = frozen.atr_value
    level = frozen.support if side == "long" else frozen.resistance
    prior = base[-max(1, int(cfg.min_bars_since_edge_touch)) :]
    if side == "long":
        quiet = all(_f(row, LOW) > level + cfg.edge_touch_atr * a for row in prior)
        penetration = (level - current["l"]) / a
        setup_ok = (
            quiet
            and current["l"] <= level + cfg.edge_touch_atr * a
            and penetration <= cfg.max_penetration_atr
            and current["c"] >= level + cfg.reclaim_inside_atr * a
            and current["lower_wick"] >= cfg.min_wick_atr * a
            and current["close_location"] >= cfg.min_close_location
        )
        stop = min(current["l"], level) - cfg.stop_buffer_atr * a
        target = frozen.midpoint
        risk = current["c"] - stop
        structural_rr = (target - current["c"]) / risk if risk > 0 else -1.0
    else:
        quiet = all(_f(row, HIGH) < level - cfg.edge_touch_atr * a for row in prior)
        penetration = (current["h"] - level) / a
        setup_ok = (
            quiet
            and current["h"] >= level - cfg.edge_touch_atr * a
            and penetration <= cfg.max_penetration_atr
            and current["c"] <= level - cfg.reclaim_inside_atr * a
            and current["upper_wick"] >= cfg.min_wick_atr * a
            and current["close_location"] <= 1.0 - cfg.min_close_location
        )
        stop = max(current["h"], level) + cfg.stop_buffer_atr * a
        target = frozen.midpoint
        risk = stop - current["c"]
        structural_rr = (current["c"] - target) / risk if risk > 0 else -1.0
    if not setup_ok or structural_rr < cfg.min_structural_rr:
        return None
    respect_ok, respect = _respect(
        base,
        level,
        side=side,
        min_resolved=cfg.min_resolved_reactions,
        min_score=cfg.min_respect_score,
    )
    if not respect_ok:
        return None
    event = FxEvent(
        event_id=_event_id(
            "horizontal_range_rejection_v3",
            instrument.symbol,
            side,
            signal_bar_ts,
            level,
        ),
        family="horizontal_range_rejection_v3",
        side=side,
        signal_ts=decision_ts,
        level=level,
        level_kind="horizontal_range_edge",
        reason="first_horizontal_edge_rejection",
        metadata={
            "instrument": instrument.symbol,
            "signal_bar_ts": signal_bar_ts,
            "range_width_atr": frozen.width_atr,
            "range_votes": frozen.range_votes,
            "penetration_atr": penetration,
            "structural_rr": structural_rr,
            **respect,
        },
    )
    return FxTradePlan(
        event=event,
        entry_type="market_next_open",
        reference_price=current["c"],
        stop_price=stop,
        target_price=target,
        target_rr=max(cfg.fallback_target_rr, structural_rr),
        max_hold_bars=cfg.max_hold_bars,
        validity_bars=1,
        allowed_fill_sessions=cfg.allowed_sessions,
        metadata={"atr": a, "sessions": session_labels(decision_ts)},
    )


@dataclass(frozen=True)
class RangeEdgeExpansionRetestConfig:
    context_bars: int = 320
    range: HorizontalRangeConfig = field(default_factory=HorizontalRangeConfig)
    retest_window_bars: int = 8
    breakout_buffer_atr: float = 0.10
    min_expansion_body_atr: float = 0.25
    min_expansion_range_atr: float = 0.55
    min_expansion_close_location: float = 0.65
    retest_touch_atr: float = 0.18
    retest_hold_atr: float = 0.03
    min_retest_wick_atr: float = 0.04
    max_entry_extension_atr: float = 0.35
    invalidation_close_atr: float = 0.08
    stop_buffer_atr: float = 0.12
    measured_move_fraction: float = 0.75
    min_structural_rr: float = 1.15
    fallback_target_rr: float = 1.8
    max_hold_bars: int = 72
    min_respect_score: float = 0.30
    min_resolved_reactions: int = 2
    allowed_sessions: tuple[str, ...] = ("london", "london_ny_overlap", "newyork")


def range_edge_expansion_retest_v3(
    rows: Sequence[Sequence[float]],
    *,
    instrument: FxInstrumentSpec,
    side_mode: str,
    cfg: Optional[RangeEdgeExpansionRetestConfig] = None,
    events: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[FxTradePlan]:
    side = _side(side_mode)
    cfg = cfg or RangeEdgeExpansionRetestConfig()
    window = list(rows[-cfg.context_bars :])
    if len(window) < cfg.range.lookback + cfg.retest_window_bars + 35:
        return None
    current = _shape(window[-1])
    signal_bar_ts = int(_f(window[-1], TS))
    decision_ts = signal_bar_ts + H1_SECONDS
    if not _session_news_ok(
        decision_ts,
        current["c"],
        allowed_sessions=cfg.allowed_sessions,
        events=events,
    ):
        return None
    a = atr(window, exclude_last=True)
    if not (a == a and a > 0):
        return None

    for age in range(1, cfg.retest_window_bars + 1):
        event_i = len(window) - 1 - age
        base = window[event_i - cfg.range.lookback : event_i]
        frozen = freeze_horizontal_range(base, cfg.range)
        if frozen is None:
            continue
        level = frozen.resistance if side == "long" else frozen.support
        event_a = frozen.atr_value
        event_bar = _shape(window[event_i])
        if side == "long":
            broke = (
                event_bar["c"] > event_bar["o"]
                and event_bar["c"] >= level + cfg.breakout_buffer_atr * event_a
                and event_bar["body"] >= cfg.min_expansion_body_atr * event_a
                and event_bar["range"] >= cfg.min_expansion_range_atr * event_a
                and event_bar["close_location"] >= cfg.min_expansion_close_location
            )
        else:
            broke = (
                event_bar["c"] < event_bar["o"]
                and event_bar["c"] <= level - cfg.breakout_buffer_atr * event_a
                and event_bar["body"] >= cfg.min_expansion_body_atr * event_a
                and event_bar["range"] >= cfg.min_expansion_range_atr * event_a
                and event_bar["close_location"] <= 1.0 - cfg.min_expansion_close_location
            )
        if not broke:
            continue

        intact = True
        for row in window[event_i + 1 : -1]:
            if side == "long":
                failed = _f(row, CLOSE) < level - cfg.invalidation_close_atr * event_a
                consumed = _f(row, LOW) <= level + cfg.retest_touch_atr * a
            else:
                failed = _f(row, CLOSE) > level + cfg.invalidation_close_atr * event_a
                consumed = _f(row, HIGH) >= level - cfg.retest_touch_atr * a
            if failed or consumed:
                intact = False
                break
        if not intact:
            continue

        if side == "long":
            extension = (current["c"] - level) / a
            retest_ok = (
                current["l"] <= level + cfg.retest_touch_atr * a
                and current["c"] >= level + cfg.retest_hold_atr * a
                and current["lower_wick"] >= cfg.min_retest_wick_atr * a
                and current["close_location"] >= 0.55
                and 0 <= extension <= cfg.max_entry_extension_atr
            )
            stop = min(current["l"], level) - cfg.stop_buffer_atr * a
            target = level + cfg.measured_move_fraction * frozen.width
            risk = current["c"] - stop
            structural_rr = (target - current["c"]) / risk if risk > 0 else -1.0
        else:
            extension = (level - current["c"]) / a
            retest_ok = (
                current["h"] >= level - cfg.retest_touch_atr * a
                and current["c"] <= level - cfg.retest_hold_atr * a
                and current["upper_wick"] >= cfg.min_retest_wick_atr * a
                and current["close_location"] <= 0.45
                and 0 <= extension <= cfg.max_entry_extension_atr
            )
            stop = max(current["h"], level) + cfg.stop_buffer_atr * a
            target = level - cfg.measured_move_fraction * frozen.width
            risk = stop - current["c"]
            structural_rr = (current["c"] - target) / risk if risk > 0 else -1.0
        if not retest_ok or target <= 0 or structural_rr < cfg.min_structural_rr:
            continue
        respect_ok, respect = _respect(
            base,
            level,
            # A broken resistance retested as support is approached from above
            # (long); a broken support retested as resistance is approached
            # from below (short).  Keep this identical to the candidate side.
            side=side,
            min_resolved=cfg.min_resolved_reactions,
            min_score=cfg.min_respect_score,
        )
        if not respect_ok:
            continue
        event_ts = int(_f(window[event_i], TS))
        event = FxEvent(
            event_id=_event_id(
                "range_edge_expansion_retest_v3",
                instrument.symbol,
                side,
                event_ts,
                level,
            ),
            family="range_edge_expansion_retest_v3",
            side=side,
            signal_ts=decision_ts,
            level=level,
            level_kind="frozen_horizontal_range_edge",
            reason="range_expansion_then_first_retest",
            metadata={
                "instrument": instrument.symbol,
                "event_ts": event_ts,
                "signal_bar_ts": signal_bar_ts,
                "retest_age_bars": age,
                "range_width_atr": frozen.width_atr,
                "range_votes": frozen.range_votes,
                "event_atr": event_a,
                "signal_atr": a,
                "structural_rr": structural_rr,
                **respect,
            },
        )
        return FxTradePlan(
            event=event,
            entry_type="market_next_open",
            reference_price=current["c"],
            stop_price=stop,
            target_price=target,
            target_rr=max(cfg.fallback_target_rr, structural_rr),
            max_hold_bars=cfg.max_hold_bars,
            validity_bars=1,
            allowed_fill_sessions=cfg.allowed_sessions,
            metadata={"atr": a, "sessions": session_labels(decision_ts)},
        )
    return None


SETUPS_V3 = {
    "failed_break_retest_short_v3": failed_break_retest_short_v3,
    "horizontal_range_rejection_v3": horizontal_range_rejection_v3,
    "range_edge_expansion_retest_v3": range_edge_expansion_retest_v3,
}


__all__ = [
    "FailedBreakRetestShortConfig",
    "FrozenHorizontalRange",
    "HorizontalRangeConfig",
    "HorizontalRangeRejectionConfig",
    "RangeEdgeExpansionRetestConfig",
    "SETUPS_V3",
    "failed_break_retest_short_v3",
    "freeze_horizontal_range",
    "horizontal_range_rejection_v3",
    "range_edge_expansion_retest_v3",
]
