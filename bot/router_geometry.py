from __future__ import annotations

from typing import Any, Dict, List, Sequence

from bot.chart_geometry import analyze_geometry


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _rows_from_series(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
) -> List[List[float]]:
    rows: List[List[float]] = []
    if not closes or not highs or not lows:
        return rows
    prev_close = _safe_float(closes[0], 0.0)
    for idx, (close, high, low) in enumerate(zip(closes, highs, lows)):
        close_f = _safe_float(close, prev_close)
        high_f = _safe_float(high, close_f)
        low_f = _safe_float(low, close_f)
        open_f = prev_close if idx > 0 else close_f
        rows.append([float(idx * 3_600_000), open_f, high_f, low_f, close_f, 0.0])
        prev_close = close_f
    return rows


def _trend_label(snapshot: Dict[str, Any]) -> str:
    channel = dict(snapshot.get("channel") or {})
    slope_pct = _safe_float(channel.get("slope_pct_per_bar"), 0.0)
    r2 = _safe_float(channel.get("r2"), 0.0)
    if r2 >= 0.35 and slope_pct >= 0.02:
        return "trend_up"
    if r2 >= 0.35 and slope_pct <= -0.02:
        return "trend_down"
    return "range_or_transition"


def _level_context(snapshot: Dict[str, Any]) -> str:
    price = _safe_float(snapshot.get("current_price"), 0.0)
    atr = max(_safe_float(snapshot.get("atr"), 0.0), max(price * 0.0015, 1e-12))
    nearest = dict(snapshot.get("nearest_levels") or {})
    above = list(nearest.get("above") or [])
    below = list(nearest.get("below") or [])
    if above:
        dist_above_atr = (_safe_float(above[0].get("price"), price) - price) / atr
        if dist_above_atr <= 0.6:
            return "near_resistance"
    if below:
        dist_below_atr = (price - _safe_float(below[0].get("price"), price)) / atr
        if dist_below_atr <= 0.6:
            return "near_support"
    return "mid_range"


def geometry_flags_from_series(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
) -> Dict[str, Any]:
    rows = _rows_from_series(closes, highs, lows)
    snapshot = analyze_geometry(rows[-120:])
    if str(snapshot.get("status")) != "ok":
        return {
            "status": str(snapshot.get("status") or "unavailable"),
            "trend_label": "unknown",
            "level_context": "unknown",
            "is_compressed": False,
            "compression_ratio": 0.0,
            "channel_r2": 0.0,
            "channel_position": 0.5,
        }
    channel = dict(snapshot.get("channel") or {})
    compression = dict(snapshot.get("compression") or {})
    return {
        "status": "ok",
        "trend_label": _trend_label(snapshot),
        "level_context": _level_context(snapshot),
        "is_compressed": bool(compression.get("is_compressed")),
        "compression_ratio": _safe_float(compression.get("compression_ratio"), 0.0),
        "channel_r2": _safe_float(channel.get("r2"), 0.0),
        "channel_position": _safe_float(channel.get("position"), 0.5),
        "slope_pct_per_bar": _safe_float(channel.get("slope_pct_per_bar"), 0.0),
    }


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def geometry_score_for_env(env_key: str, flags: Dict[str, Any]) -> Dict[str, Any]:
    env = str(env_key or "").upper()
    trend = str(flags.get("trend_label") or "unknown")
    level = str(flags.get("level_context") or "unknown")
    compressed = bool(flags.get("is_compressed"))
    channel_r2 = _safe_float(flags.get("channel_r2"), 0.0)
    channel_pos = _safe_float(flags.get("channel_position"), 0.5)

    score = 0.50
    reasons: List[str] = []

    if env.startswith("BREAKOUT"):
        if trend == "trend_up":
            score += 0.18
            reasons.append("trend_up")
        if level == "near_resistance":
            score += 0.18
            reasons.append("near_resistance")
        if compressed:
            score += 0.16
            reasons.append("compressed")
        if trend == "trend_down":
            score -= 0.20
            reasons.append("trend_down_penalty")
    elif env.startswith("BREAKDOWN"):
        if trend == "trend_down":
            score += 0.18
            reasons.append("trend_down")
        if level == "near_support":
            score += 0.18
            reasons.append("near_support")
        if compressed:
            score += 0.16
            reasons.append("compressed")
        if trend == "trend_up":
            score -= 0.20
            reasons.append("trend_up_penalty")
    elif env.startswith(("ARF1", "ARS1", "AVW1")):
        if trend == "range_or_transition":
            score += 0.16
            reasons.append("range_or_transition")
        if level in {"near_support", "near_resistance"}:
            score += 0.18
            reasons.append(level)
        if compressed:
            score += 0.05
            reasons.append("compressed")
        if trend in {"trend_up", "trend_down"}:
            score -= 0.10
            reasons.append("trend_penalty")
    elif env.startswith("ASC1"):
        if channel_r2 >= 0.35:
            score += 0.20
            reasons.append("channel_quality")
        if trend in {"trend_up", "trend_down"}:
            score += 0.12
            reasons.append(trend)
        if level in {"near_support", "near_resistance"}:
            score += 0.08
            reasons.append(level)
    elif env.startswith("ASB1"):
        if trend == "trend_up":
            score += 0.16
            reasons.append("trend_up")
        if level == "near_support":
            score += 0.22
            reasons.append("near_support")
        if compressed:
            score += 0.08
            reasons.append("compressed")
        if trend == "trend_down":
            score -= 0.16
            reasons.append("trend_down_penalty")
    elif env.startswith("PF2"):
        if level == "near_resistance":
            score += 0.15
            reasons.append("near_resistance")
        if channel_pos >= 0.75:
            score += 0.15
            reasons.append("upper_channel")
        if compressed:
            score += 0.05
            reasons.append("compressed")
    elif env.startswith(("ETS2", "MIDTERM")):
        if trend in {"trend_up", "trend_down"}:
            score += 0.12
            reasons.append(trend)
        if level in {"near_support", "near_resistance"}:
            score += 0.08
            reasons.append(level)

    min_keep = 0.45
    if env.startswith(("BREAKOUT", "BREAKDOWN", "ASB1")):
        min_keep = 0.55
    elif env.startswith(("ARF1", "ARS1", "AVW1", "ASC1")):
        min_keep = 0.48

    score = _clamp_score(score)
    return {
        "score": score,
        "min_keep_score": float(min_keep),
        "keep": bool(score >= min_keep),
        "reasons": reasons,
        "flags": flags,
    }
