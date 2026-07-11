"""Three causal, side-separated FX/CFD V2 strategy families.

These are research plans, not live order code:

* impulse_breakout_retest_v2 — a level is frozen before an impulse, then a
  later bar retests it; breakout and retest can never be the same bar.
* sweep_reclaim_bounce_v2 — a bounded stop run closes back through a horizontal
  or sloped pool, with regime/tide and side-specific level-memory checks.
* regime_range_reversion_v2 — non-martingale range/chop execution at a frozen
  horizontal/sloped edge, targeting the channel midpoint.

Every call consumes only the supplied closed-bar prefix.  Every plan has a
unique event id and an explicit next-open or limit execution contract.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Sequence

from bot.elder_filter import elder_bias
from bot.failed_breakout import failed_breakout
from bot.fx_calendar import session_labels
from bot.fx_contracts import FxEvent, FxInstrumentSpec, FxTradePlan
from bot.level_memory import level_respect
from bot.liquidity_sweep import liquidity_sweep
from bot.market_context import (
    CLOSE,
    HIGH,
    LOW,
    OPEN,
    TS,
    atr,
    horizontal_levels,
    sloped_level,
)
from bot.news_session_filter import entry_allowed
from bot.range_filter import range_state
from bot.regime_hmm import regime_probs
from bot.structure_break import structure_break


H1_SECONDS = 3600


def _f(row: Sequence[float], idx: int) -> float:
    try:
        return float(row[idx])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def _ema(values: Sequence[float], period: int) -> float:
    vals = [float(v) for v in values if float(v) == float(v)]
    if not vals:
        return float("nan")
    k = 2.0 / (max(1, int(period)) + 1.0)
    out = vals[0]
    for value in vals[1:]:
        out = value * k + out * (1.0 - k)
    return out


def _allowed_side(side: str, mode: str) -> bool:
    mode = str(mode).lower()
    if mode not in {"long", "short", "both"}:
        raise ValueError("side_mode must be long, short or both")
    return mode == "both" or mode == side


def _liquid_and_news_ok(
    ts: int,
    price: float,
    *,
    sessions: Sequence[str],
    events: Optional[Sequence[Dict[str, Any]]],
) -> bool:
    if not set(session_labels(ts)).intersection(set(sessions)):
        return False
    # Session is handled by the DST-aware calendar above.  This call adds the
    # event blackout; events=None is permitted for research but recorded by the gate.
    return entry_allowed(ts, events=events, price=price, avoid_low_liq_session=False).allow


def _event_id(
    family: str,
    instrument: str,
    side: str,
    event_ts: int,
    kind: str,
    level: Optional[float] = None,
) -> str:
    base = f"{family}:{str(instrument).upper()}:{side}:{int(event_ts)}:{kind}"
    return f"{base}:{float(level):.8g}" if level is not None else base


def _bar_shape(row: Sequence[float]) -> Dict[str, float]:
    o, h, l, c = (_f(row, OPEN), _f(row, HIGH), _f(row, LOW), _f(row, CLOSE))
    rng = max(1e-12, h - l)
    return {
        "o": o,
        "h": h,
        "l": l,
        "c": c,
        "body": abs(c - o),
        "lower_wick": max(0.0, min(o, c) - l),
        "upper_wick": max(0.0, h - max(o, c)),
        "close_location": (c - l) / rng,
    }


def _trend_side(rows: Sequence[Sequence[float]], a: float, *, fast: int, slow: int, slope_bars: int,
                min_sep_atr: float, min_slope_atr: float) -> str:
    closes = [_f(row, CLOSE) for row in rows]
    if len(closes) < slow + slope_bars + 2 or not (a > 0):
        return "none"
    ef, es = _ema(closes[-slow * 2:], fast), _ema(closes[-slow * 2:], slow)
    old = _ema(closes[-slow * 2:-slope_bars], slow)
    sep = (ef - es) / a
    slope = (es - old) / a if old == old else 0.0
    if sep >= min_sep_atr and slope >= min_slope_atr:
        return "long"
    if sep <= -min_sep_atr and slope <= -min_slope_atr:
        return "short"
    return "none"


def _respect_meta(
    rows: Sequence[Sequence[float]],
    level: float,
    side: str,
    *,
    min_resolved: int,
    min_score: float,
    approach: Optional[str] = None,
) -> tuple[bool, Dict[str, Any]]:
    approach_mode = approach or ("from_above" if side == "long" else "from_below")
    stats = level_respect(list(rows), level, approach=approach_mode, min_history=30)
    resolved = stats.bounces + stats.sweeps + stats.breaks
    rated = resolved >= int(min_resolved)
    score = stats.respect_score
    allowed = not rated or (score == score and score >= float(min_score))
    return allowed, {
        "respect_rated": rated,
        "respect_score": score if score == score else None,
        "respect_resolved": resolved,
        "respect_bounces": stats.bounces,
        "respect_sweeps": stats.sweeps,
        "respect_breaks": stats.breaks,
    }


@dataclass(frozen=True)
class ImpulseBreakoutRetestConfig:
    context_bars: int = 280
    level_lookback: int = 48
    retest_window_bars: int = 8
    min_touches: int = 2
    breakout_buffer_atr: float = 0.12
    min_impulse_body_atr: float = 0.22
    max_impulse_body_atr: float = 1.80
    retest_touch_atr: float = 0.20
    retest_hold_atr: float = 0.04
    min_rejection_wick_atr: float = 0.05
    max_entry_extension_atr: float = 0.45
    trend_fast: int = 34
    trend_slow: int = 120
    trend_slope_bars: int = 6
    min_trend_sep_atr: float = 0.08
    min_trend_slope_atr: float = 0.01
    min_sloped_r2: float = 0.55
    min_respect_score: float = 0.25
    min_resolved_reactions: int = 2
    level_unbroken_bars: int = 12
    stop_buffer_atr: float = 0.16
    target_rr: float = 2.0
    max_hold_bars: int = 72
    allowed_sessions: tuple[str, ...] = ("london", "london_ny_overlap", "newyork")


def _break_levels(base: Sequence[Sequence[float]], side: str, a: float,
                  cfg: ImpulseBreakoutRetestConfig) -> list[Dict[str, Any]]:
    out: list[Dict[str, Any]] = []
    source_side = "resistance" if side == "long" else "support"
    for lv in horizontal_levels(
        list(base), side=source_side, atr_value=a, min_touches=cfg.min_touches
    ):
        out.append({
            "kind": "horizontal",
            "event_level": float(lv["level"]),
            "slope": 0.0,
            "touches": int(lv.get("touches", 0)),
        })
    # A completed rolling range edge is allowed even when pivot clustering is thin.
    edge = (
        max(_f(row, HIGH) for row in base)
        if side == "long"
        else min(_f(row, LOW) for row in base)
    )
    out.append({"kind": "range_edge", "event_level": edge, "slope": 0.0, "touches": 1})
    sl = sloped_level(
        list(base), side=source_side, min_pivots=3, min_r2=cfg.min_sloped_r2,
        atr_value=a, require_unbroken=True,
    )
    if sl is not None:
        # Fit coordinates are relative to base.  Project one bar to the impulse.
        event_level = float(sl["slope"]) * len(base) + float(sl["intercept"])
        out.append({
            "kind": "sloped",
            "event_level": event_level,
            "slope": float(sl["slope"]),
            "touches": int(sl.get("pivots", 0)),
            "r2": float(sl.get("r2", float("nan"))),
        })
    # Closest meaningful level first; actual breakout checks decide direction.
    return out


def impulse_breakout_retest_v2(
    rows: Sequence[Sequence[float]],
    *,
    instrument: FxInstrumentSpec,
    side_mode: str,
    cfg: Optional[ImpulseBreakoutRetestConfig] = None,
    events: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[FxTradePlan]:
    cfg = cfg or ImpulseBreakoutRetestConfig()
    window = list(rows[-cfg.context_bars:])
    if len(window) < max(cfg.trend_slow + cfg.trend_slope_bars + 5, cfg.level_lookback + 20):
        return None
    now = _bar_shape(window[-1])
    signal_bar_ts = int(_f(window[-1], TS))
    decision_ts = signal_bar_ts + H1_SECONDS
    if not _liquid_and_news_ok(decision_ts, now["c"], sessions=cfg.allowed_sessions, events=events):
        return None
    a = atr(window, exclude_last=True)
    if not (a == a and a > 0):
        return None

    # Most recent valid impulse wins.  age>=1 guarantees a later retest bar.
    for age in range(1, cfg.retest_window_bars + 1):
        event_i = len(window) - 1 - age
        if event_i <= cfg.level_lookback:
            continue
        event = _bar_shape(window[event_i])
        base = window[event_i - cfg.level_lookback:event_i]
        trend = _trend_side(
            window[: event_i + 1], a,
            fast=cfg.trend_fast, slow=cfg.trend_slow, slope_bars=cfg.trend_slope_bars,
            min_sep_atr=cfg.min_trend_sep_atr, min_slope_atr=cfg.min_trend_slope_atr,
        )
        if trend not in {"long", "short"} or not _allowed_side(trend, side_mode):
            continue
        for level_info in _break_levels(base, trend, a, cfg):
            event_level = float(level_info["event_level"])
            slope = float(level_info.get("slope", 0.0))
            current_level = event_level + slope * age
            impulse_body = (event["c"] - event["o"]) if trend == "long" else (event["o"] - event["c"])
            beyond = (event["c"] - event_level) if trend == "long" else (event_level - event["c"])
            prior_level = event_level - slope
            prior_close = _f(base[-1], CLOSE)
            recent_unbroken = True
            for bars_back, row in enumerate(reversed(base[-cfg.level_unbroken_bars:]), 1):
                historical_level = event_level - slope * bars_back
                close = _f(row, CLOSE)
                if trend == "long" and close > historical_level + cfg.breakout_buffer_atr * a:
                    recent_unbroken = False
                    break
                if trend == "short" and close < historical_level - cfg.breakout_buffer_atr * a:
                    recent_unbroken = False
                    break
            crossed_from_source_side = (
                prior_close <= prior_level
                and event["o"] <= event_level + cfg.breakout_buffer_atr * a
                if trend == "long"
                else prior_close >= prior_level
                and event["o"] >= event_level - cfg.breakout_buffer_atr * a
            )
            if not (recent_unbroken and crossed_from_source_side):
                continue
            if beyond < cfg.breakout_buffer_atr * a:
                continue
            if not (cfg.min_impulse_body_atr * a <= impulse_body <= cfg.max_impulse_body_atr * a):
                continue
            # Only the first intact retest belongs to this event.  A close back
            # through the level invalidates it; an earlier touch consumes it.
            intervening = window[event_i + 1:-1]
            event_intact = True
            for offset, row in enumerate(intervening, 1):
                projected = event_level + slope * offset
                if trend == "long":
                    failed = _f(row, CLOSE) < projected - cfg.retest_hold_atr * a
                    already_retested = _f(row, LOW) <= projected + cfg.retest_touch_atr * a
                else:
                    failed = _f(row, CLOSE) > projected + cfg.retest_hold_atr * a
                    already_retested = _f(row, HIGH) >= projected - cfg.retest_touch_atr * a
                if failed or already_retested:
                    event_intact = False
                    break
            if not event_intact:
                continue
            if trend == "long":
                touched = now["l"] <= current_level + cfg.retest_touch_atr * a
                held = now["c"] >= current_level + cfg.retest_hold_atr * a
                rejected = now["lower_wick"] >= cfg.min_rejection_wick_atr * a and now["close_location"] >= 0.55
                extension = (now["c"] - current_level) / a
                stop = min(now["l"], current_level - cfg.stop_buffer_atr * a)
            else:
                touched = now["h"] >= current_level - cfg.retest_touch_atr * a
                held = now["c"] <= current_level - cfg.retest_hold_atr * a
                rejected = now["upper_wick"] >= cfg.min_rejection_wick_atr * a and now["close_location"] <= 0.45
                extension = (current_level - now["c"]) / a
                stop = max(now["h"], current_level + cfg.stop_buffer_atr * a)
            if not (touched and held and rejected and 0 <= extension <= cfg.max_entry_extension_atr):
                continue
            respect_ok, respect = (True, {"respect_rated": False})
            if level_info["kind"] in {"horizontal", "range_edge"}:
                respect_ok, respect = _respect_meta(
                    base, event_level, trend,
                    min_resolved=cfg.min_resolved_reactions,
                    min_score=cfg.min_respect_score,
                    approach="from_below" if trend == "long" else "from_above",
                )
            if not respect_ok:
                continue
            event_ts = int(_f(window[event_i], TS))
            event_obj = FxEvent(
                event_id=_event_id(
                    "impulse_breakout_retest_v2", instrument.symbol, trend,
                    event_ts, str(level_info["kind"]), event_level,
                ),
                family="impulse_breakout_retest_v2",
                side=trend,
                signal_ts=decision_ts,
                level=current_level,
                level_kind=str(level_info["kind"]),
                reason="impulse_then_later_retest",
                metadata={
                    "instrument": instrument.symbol,
                    "impulse_ts": event_ts,
                    "signal_bar_ts": signal_bar_ts,
                    "retest_age_bars": age,
                    "impulse_body_atr": impulse_body / a,
                    "break_distance_atr": beyond / a,
                    "touches": level_info.get("touches", 0),
                    "r2": level_info.get("r2"),
                    **respect,
                },
            )
            return FxTradePlan(
                event=event_obj,
                entry_type="market_next_open",
                reference_price=now["c"],
                stop_price=stop,
                target_rr=cfg.target_rr,
                max_hold_bars=cfg.max_hold_bars,
                validity_bars=1,
                allowed_fill_sessions=cfg.allowed_sessions,
                metadata={"atr": a, "sessions": session_labels(decision_ts)},
            )
    return None


@dataclass(frozen=True)
class SweepReclaimBounceConfig:
    context_bars: int = 260
    pool_lookback: int = 36
    min_penetration_atr: float = 0.10
    max_penetration_atr: float = 0.90
    min_wick_atr: float = 0.10
    min_close_location: float = 0.58
    failed_break_window: int = 5
    min_sloped_r2: float = 0.55
    min_respect_score: float = 0.35
    min_resolved_reactions: int = 2
    block_high_vol_confidence: float = 0.55
    stop_buffer_atr: float = 0.12
    target_rr: float = 1.8
    max_hold_bars: int = 60
    allowed_sessions: tuple[str, ...] = ("london", "london_ny_overlap", "newyork")


def sweep_reclaim_bounce_v2(
    rows: Sequence[Sequence[float]],
    *,
    instrument: FxInstrumentSpec,
    side_mode: str,
    cfg: Optional[SweepReclaimBounceConfig] = None,
    events: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[FxTradePlan]:
    cfg = cfg or SweepReclaimBounceConfig()
    window = list(rows[-cfg.context_bars:])
    if len(window) < max(120, cfg.pool_lookback + cfg.failed_break_window + 10):
        return None
    now = _bar_shape(window[-1])
    signal_bar_ts = int(_f(window[-1], TS))
    decision_ts = signal_bar_ts + H1_SECONDS
    if not _liquid_and_news_ok(decision_ts, now["c"], sessions=cfg.allowed_sessions, events=events):
        return None
    a = atr(window, exclude_last=True)
    if not (a == a and a > 0):
        return None
    base = window[:-1]
    candidates: list[Dict[str, Any]] = []

    sw = liquidity_sweep(
        window[-(cfg.pool_lookback + 2):],
        pool_lookback=cfg.pool_lookback,
        min_penetration_atr=cfg.min_penetration_atr,
        atr_value=a,
    )
    if sw.event == "sweep_reversal":
        candidates.append({
            "side": sw.side,
            "level": float(sw.pool_level),
            "kind": "liquidity",
            "penetration": float(sw.penetration_atr),
            "event_ts": signal_bar_ts,
        })

    fb = failed_breakout(
        window,
        level_lookback=cfg.pool_lookback,
        event_window=cfg.failed_break_window,
        buffer_atr=cfg.min_penetration_atr,
        atr_value=a,
    )
    if fb.failed:
        extreme = (
            min(_f(row, LOW) for row in window[-cfg.failed_break_window:])
            if fb.side == "long"
            else max(_f(row, HIGH) for row in window[-cfg.failed_break_window:])
        )
        penetration = abs(extreme - float(fb.level)) / a
        event_rows = window[-cfg.failed_break_window:]
        if fb.side == "long":
            break_rows = [
                row for row in event_rows
                if _f(row, CLOSE) < float(fb.level) - cfg.min_penetration_atr * a
            ]
        else:
            break_rows = [
                row for row in event_rows
                if _f(row, CLOSE) > float(fb.level) + cfg.min_penetration_atr * a
            ]
        # Anchor the lifecycle to the last actual break, not to each later
        # reclaim candle.  This keeps repeated detections of one failed break
        # on one stable event_id.
        break_ts = int(_f(break_rows[-1], TS)) if break_rows else signal_bar_ts
        candidates.append({
            "side": fb.side,
            "level": float(fb.level),
            "kind": "failed_break",
            "penetration": penetration,
            "event_ts": break_ts,
        })

    # Independent sloped-channel sweep/reclaim.
    for side, source_side in (("long", "support"), ("short", "resistance")):
        line = sloped_level(
            base[-120:], side=source_side, min_pivots=3,
            min_r2=cfg.min_sloped_r2, atr_value=a, require_unbroken=True,
        )
        if line is None:
            continue
        projected = float(line["level_now"]) + float(line["slope"])
        if side == "long":
            penetration = (projected - now["l"]) / a
            reclaimed = now["l"] < projected and now["c"] > projected
        else:
            penetration = (now["h"] - projected) / a
            reclaimed = now["h"] > projected and now["c"] < projected
        if reclaimed and penetration >= cfg.min_penetration_atr:
            candidates.append({
                "side": side,
                "level": projected,
                "kind": "sloped",
                "penetration": penetration,
                "r2": float(line.get("r2", float("nan"))),
                "event_ts": signal_bar_ts,
            })

    if not candidates:
        return None
    reg = regime_probs(base[-180:])
    if reg.ok and reg.dominant == "high_vol" and reg.confidence >= cfg.block_high_vol_confidence:
        return None
    tide = elder_bias(base[-220:], require_with_tide=False)
    sb = structure_break(window[-100:], buffer_atr=0.05, atr_value=a)

    for cand in sorted(candidates, key=lambda item: float(item["penetration"]), reverse=True):
        side = str(cand["side"])
        if not _allowed_side(side, side_mode):
            continue
        penetration = float(cand["penetration"])
        if not (cfg.min_penetration_atr <= penetration <= cfg.max_penetration_atr):
            continue
        if side == "long":
            shape_ok = now["lower_wick"] >= cfg.min_wick_atr * a and now["close_location"] >= cfg.min_close_location
            tide_ok = tide.allow_long or (sb.event == "choch" and sb.side == "long") or (reg.ok and reg.dominant == "range")
            stop = min(now["l"], float(cand["level"]) - cfg.stop_buffer_atr * a)
        else:
            shape_ok = now["upper_wick"] >= cfg.min_wick_atr * a and now["close_location"] <= 1.0 - cfg.min_close_location
            tide_ok = tide.allow_short or (sb.event == "choch" and sb.side == "short") or (reg.ok and reg.dominant == "range")
            stop = max(now["h"], float(cand["level"]) + cfg.stop_buffer_atr * a)
        if not (shape_ok and tide_ok):
            continue
        respect_ok, respect = (True, {"respect_rated": False})
        if cand["kind"] != "sloped":
            respect_ok, respect = _respect_meta(
                base, float(cand["level"]), side,
                min_resolved=cfg.min_resolved_reactions,
                min_score=cfg.min_respect_score,
            )
        if not respect_ok:
            continue
        event_obj = FxEvent(
            event_id=_event_id(
                "sweep_reclaim_bounce_v2", instrument.symbol, side,
                int(cand.get("event_ts", signal_bar_ts)), str(cand["kind"]),
                None if cand["kind"] == "failed_break" else float(cand["level"]),
            ),
            family="sweep_reclaim_bounce_v2",
            side=side,
            signal_ts=decision_ts,
            level=float(cand["level"]),
            level_kind=str(cand["kind"]),
            reason="bounded_sweep_reclaimed",
            metadata={
                "instrument": instrument.symbol,
                "penetration_atr": penetration,
                "source_event_ts": int(cand.get("event_ts", signal_bar_ts)),
                "signal_bar_ts": signal_bar_ts,
                "regime": reg.dominant if reg.ok else "unknown",
                "tide": tide.tide,
                "choch_override": sb.event == "choch" and sb.side == side,
                "r2": cand.get("r2"),
                **respect,
            },
        )
        return FxTradePlan(
            event=event_obj,
            entry_type="market_next_open",
            reference_price=now["c"],
            stop_price=stop,
            target_rr=cfg.target_rr,
            max_hold_bars=cfg.max_hold_bars,
            allowed_fill_sessions=cfg.allowed_sessions,
            metadata={"atr": a, "sessions": session_labels(decision_ts)},
        )
    return None


@dataclass(frozen=True)
class RegimeRangeReversionConfig:
    context_bars: int = 260
    range_lookback: int = 72
    min_width_atr: float = 2.0
    max_width_atr: float = 8.0
    lower_zone: float = 0.25
    upper_zone: float = 0.75
    edge_touch_atr: float = 0.18
    reclaim_atr: float = 0.03
    min_wick_atr: float = 0.05
    limit_offset_atr: float = 0.04
    stop_buffer_atr: float = 0.35
    validity_bars: int = 4
    min_target_rr: float = 1.15
    fallback_target_rr: float = 1.5
    max_hold_bars: int = 48
    min_respect_score: float = 0.35
    min_resolved_reactions: int = 2
    allowed_sessions: tuple[str, ...] = ("london", "london_ny_overlap", "newyork")


def _finite(values: Iterable[float]) -> list[float]:
    return [float(v) for v in values if float(v) == float(v) and math.isfinite(float(v))]


def regime_range_reversion_v2(
    rows: Sequence[Sequence[float]],
    *,
    instrument: FxInstrumentSpec,
    side_mode: str,
    cfg: Optional[RegimeRangeReversionConfig] = None,
    events: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[FxTradePlan]:
    cfg = cfg or RegimeRangeReversionConfig()
    window = list(rows[-cfg.context_bars:])
    if len(window) < max(140, cfg.range_lookback + 30):
        return None
    current = _bar_shape(window[-1])
    signal_bar_ts = int(_f(window[-1], TS))
    decision_ts = signal_bar_ts + H1_SECONDS
    if not _liquid_and_news_ok(decision_ts, current["c"], sessions=cfg.allowed_sessions, events=events):
        return None
    # Freeze the range before the signal candle; current price cannot redraw it.
    base = window[:-1]
    a = atr(base, exclude_last=False)
    if not (a == a and a > 0):
        return None
    rs = range_state(
        base,
        lookback=cfg.range_lookback,
        require_all=False,
        lower_zone=cfg.lower_zone,
        upper_zone=cfg.upper_zone,
        allow_sloped=True,
    )
    if not (rs.ok and rs.is_range and cfg.min_width_atr <= rs.width_atr <= cfg.max_width_atr):
        return None
    reg = regime_probs(base[-180:])
    if reg.ok and reg.dominant == "high_vol":
        return None

    lower_candidates = _finite((rs.lower_now, rs.nearest_support))
    upper_candidates = _finite((rs.upper_now, rs.nearest_resistance))
    if not lower_candidates or not upper_candidates:
        return None
    lower = min(lower_candidates, key=lambda value: abs(current["c"] - value))
    upper = min(upper_candidates, key=lambda value: abs(current["c"] - value))
    if upper <= lower:
        return None
    midpoint = (upper + lower) / 2.0

    sides: list[str] = []
    if rs.regime in {"flat", "ascending"} and _allowed_side("long", side_mode):
        sides.append("long")
    if rs.regime in {"flat", "descending"} and _allowed_side("short", side_mode):
        sides.append("short")

    for side in sides:
        level = lower if side == "long" else upper
        level_kind = "horizontal" if (
            (side == "long" and rs.nearest_support == rs.nearest_support and abs(level - rs.nearest_support) < 1e-12)
            or (side == "short" and rs.nearest_resistance == rs.nearest_resistance and abs(level - rs.nearest_resistance) < 1e-12)
        ) else "sloped"
        if side == "long":
            touched = current["l"] <= level + cfg.edge_touch_atr * a
            reclaimed = current["c"] >= level + cfg.reclaim_atr * a
            rejected = current["lower_wick"] >= cfg.min_wick_atr * a and current["close_location"] >= 0.52
            limit = level + cfg.limit_offset_atr * a
            stop = level - cfg.stop_buffer_atr * a
            target = midpoint
            risk = limit - stop
            structural_rr = (target - limit) / risk if risk > 0 else -1.0
        else:
            touched = current["h"] >= level - cfg.edge_touch_atr * a
            reclaimed = current["c"] <= level - cfg.reclaim_atr * a
            rejected = current["upper_wick"] >= cfg.min_wick_atr * a and current["close_location"] <= 0.48
            limit = level - cfg.limit_offset_atr * a
            stop = level + cfg.stop_buffer_atr * a
            target = midpoint
            risk = stop - limit
            structural_rr = (limit - target) / risk if risk > 0 else -1.0
        if not (touched and reclaimed and rejected and structural_rr >= cfg.min_target_rr):
            continue
        respect_ok, respect = (True, {"respect_rated": False})
        if level_kind == "horizontal":
            respect_ok, respect = _respect_meta(
                base, level, side,
                min_resolved=cfg.min_resolved_reactions,
                min_score=cfg.min_respect_score,
            )
        if not respect_ok:
            continue
        event_obj = FxEvent(
            event_id=_event_id(
                "regime_range_reversion_v2", instrument.symbol, side,
                signal_bar_ts, level_kind, level,
            ),
            family="regime_range_reversion_v2",
            side=side,
            signal_ts=decision_ts,
            level=level,
            level_kind=level_kind,
            reason="frozen_range_edge_reclaim",
            metadata={
                "instrument": instrument.symbol,
                "range_regime": rs.regime,
                "range_votes": rs.votes,
                "ci": rs.ci,
                "vp": rs.vp,
                "adx": rs.adx,
                "width_atr": rs.width_atr,
                "structural_rr": structural_rr,
                "signal_bar_ts": signal_bar_ts,
                **respect,
            },
        )
        return FxTradePlan(
            event=event_obj,
            entry_type="limit",
            reference_price=current["c"],
            limit_price=limit,
            stop_price=stop,
            target_price=target,
            target_rr=max(cfg.fallback_target_rr, structural_rr),
            max_hold_bars=cfg.max_hold_bars,
            validity_bars=cfg.validity_bars,
            max_entry_gap_atr=0.50,
            allowed_fill_sessions=cfg.allowed_sessions,
            metadata={"atr": a, "sessions": session_labels(decision_ts)},
        )
    return None


SETUPS_V2 = {
    "impulse_breakout_retest_v2": impulse_breakout_retest_v2,
    "sweep_reclaim_bounce_v2": sweep_reclaim_bounce_v2,
    "regime_range_reversion_v2": regime_range_reversion_v2,
}
