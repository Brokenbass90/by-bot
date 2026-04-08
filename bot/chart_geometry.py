from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / float(len(values)))


def _std(values: Sequence[float], mean_value: float | None = None) -> float:
    if not values:
        return 0.0
    mu = float(mean_value if mean_value is not None else _mean(values))
    var = sum((float(v) - mu) ** 2 for v in values) / float(len(values))
    return float(var ** 0.5)


def _atr_from_rows(rows: Sequence[Sequence[Any]], period: int = 14) -> float:
    if len(rows) < max(3, period + 1):
        return 0.0
    trs: List[float] = []
    prev_close = _safe_float(rows[0][4], 0.0)
    for row in rows[1:]:
        high = _safe_float(row[2], prev_close)
        low = _safe_float(row[3], prev_close)
        close = _safe_float(row[4], prev_close)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(float(tr))
        prev_close = close
    window = trs[-max(1, int(period)) :]
    return _mean(window)


@dataclass
class PivotPoint:
    index: int
    ts_ms: int
    price: float
    side: str


@dataclass
class HorizontalLevel:
    price: float
    touches: int
    side_bias: str
    last_touch_ts_ms: int
    score: float


def find_pivots(
    rows: Sequence[Sequence[Any]],
    *,
    left: int = 2,
    right: int = 2,
) -> List[PivotPoint]:
    out: List[PivotPoint] = []
    if len(rows) < left + right + 3:
        return out
    for idx in range(left, len(rows) - right):
        high = _safe_float(rows[idx][2], 0.0)
        low = _safe_float(rows[idx][3], 0.0)
        prev_highs = [_safe_float(rows[j][2], high) for j in range(idx - left, idx)]
        next_highs = [_safe_float(rows[j][2], high) for j in range(idx + 1, idx + right + 1)]
        prev_lows = [_safe_float(rows[j][3], low) for j in range(idx - left, idx)]
        next_lows = [_safe_float(rows[j][3], low) for j in range(idx + 1, idx + right + 1)]
        ts_ms = int(_safe_float(rows[idx][0], 0.0))
        if prev_highs and next_highs and high >= max(prev_highs) and high > max(next_highs):
            out.append(PivotPoint(index=idx, ts_ms=ts_ms, price=high, side="resistance"))
        if prev_lows and next_lows and low <= min(prev_lows) and low < min(next_lows):
            out.append(PivotPoint(index=idx, ts_ms=ts_ms, price=low, side="support"))
    return out


def cluster_horizontal_levels(
    rows: Sequence[Sequence[Any]],
    pivots: Sequence[PivotPoint],
    *,
    atr: float,
    tolerance_atr: float = 0.35,
    min_touches: int = 2,
    max_levels: int = 8,
) -> List[HorizontalLevel]:
    if not rows or not pivots:
        return []
    tol = max(atr * float(tolerance_atr), max(_safe_float(rows[-1][4], 1.0), 1.0) * 0.0015)
    clusters: List[Dict[str, Any]] = []
    for pivot in sorted(pivots, key=lambda p: p.ts_ms):
        matched = None
        for cluster in clusters:
            if abs(float(cluster["price"]) - float(pivot.price)) <= tol:
                matched = cluster
                break
        if matched is None:
            matched = {
                "price": float(pivot.price),
                "prices": [float(pivot.price)],
                "side_counts": {pivot.side: 1},
                "last_touch_ts_ms": int(pivot.ts_ms),
            }
            clusters.append(matched)
        else:
            matched["prices"].append(float(pivot.price))
            matched["price"] = _mean(matched["prices"])
            matched["side_counts"][pivot.side] = int(matched["side_counts"].get(pivot.side, 0)) + 1
            matched["last_touch_ts_ms"] = max(int(matched["last_touch_ts_ms"]), int(pivot.ts_ms))

    levels: List[HorizontalLevel] = []
    last_ts = int(_safe_float(rows[-1][0], 0.0))
    for cluster in clusters:
        touches = len(cluster["prices"])
        if touches < int(min_touches):
            continue
        price = _mean(cluster["prices"])
        side_counts = dict(cluster["side_counts"])
        support_count = int(side_counts.get("support", 0))
        resistance_count = int(side_counts.get("resistance", 0))
        side_bias = "mixed"
        if support_count > resistance_count:
            side_bias = "support"
        elif resistance_count > support_count:
            side_bias = "resistance"
        age_bars = max(1.0, (last_ts - int(cluster["last_touch_ts_ms"])) / 3_600_000.0)
        recency_mult = max(0.35, min(1.0, 24.0 / age_bars))
        score = float(touches) * recency_mult
        levels.append(
            HorizontalLevel(
                price=float(price),
                touches=touches,
                side_bias=side_bias,
                last_touch_ts_ms=int(cluster["last_touch_ts_ms"]),
                score=float(score),
            )
        )
    levels.sort(key=lambda level: (-level.score, level.price))
    return levels[: max(1, int(max_levels))]


def regression_channel(
    rows: Sequence[Sequence[Any]],
    *,
    lookback: int = 72,
    width_std_mult: float = 2.0,
) -> Dict[str, float]:
    sample = list(rows[-max(3, int(lookback)) :])
    if len(sample) < 3:
        return {}
    closes = [_safe_float(row[4], 0.0) for row in sample]
    xs = list(range(len(closes)))
    x_mean = _mean(xs)
    y_mean = _mean(closes)
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom <= 0:
        return {}
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, closes)) / denom
    intercept = y_mean - slope * x_mean
    fitted = [intercept + slope * x for x in xs]
    residuals = [y - y_hat for y, y_hat in zip(closes, fitted)]
    resid_std = _std(residuals, 0.0)
    cur_mid = float(fitted[-1])
    upper = cur_mid + float(width_std_mult) * resid_std
    lower = cur_mid - float(width_std_mult) * resid_std
    width_abs = max(0.0, upper - lower)
    cur_price = float(closes[-1])
    ss_tot = sum((y - y_mean) ** 2 for y in closes)
    ss_res = sum((y - y_hat) ** 2 for y, y_hat in zip(closes, fitted))
    r2 = 0.0 if ss_tot <= 0 else max(0.0, 1.0 - ss_res / ss_tot)
    pos = 0.5 if width_abs <= 1e-12 else (cur_price - lower) / width_abs
    return {
        "slope_per_bar": float(slope),
        "slope_pct_per_bar": 0.0 if abs(cur_price) <= 1e-12 else float(slope / cur_price * 100.0),
        "intercept": float(intercept),
        "mid": float(cur_mid),
        "upper": float(upper),
        "lower": float(lower),
        "width_abs": float(width_abs),
        "width_pct": 0.0 if abs(cur_price) <= 1e-12 else float(width_abs / cur_price * 100.0),
        "r2": float(r2),
        "position": float(max(0.0, min(1.0, pos))),
    }


def compression_state(
    rows: Sequence[Sequence[Any]],
    *,
    short_window: int = 12,
    long_window: int = 48,
) -> Dict[str, float | bool]:
    if len(rows) < max(4, long_window):
        return {}
    short_rows = rows[-int(short_window) :]
    long_rows = rows[-int(long_window) :]
    short_range = _mean([_safe_float(r[2], 0.0) - _safe_float(r[3], 0.0) for r in short_rows])
    long_range = _mean([_safe_float(r[2], 0.0) - _safe_float(r[3], 0.0) for r in long_rows])
    cur_price = max(abs(_safe_float(rows[-1][4], 0.0)), 1e-12)
    ratio = float(short_range / max(long_range, 1e-12))
    return {
        "short_range_pct": float(short_range / cur_price * 100.0),
        "long_range_pct": float(long_range / cur_price * 100.0),
        "compression_ratio": ratio,
        "is_compressed": bool(ratio <= 0.68),
    }


def nearest_levels(
    levels: Sequence[HorizontalLevel],
    *,
    price: float,
    count: int = 3,
) -> Dict[str, List[Dict[str, float | int | str]]]:
    below = [lvl for lvl in levels if lvl.price <= price]
    above = [lvl for lvl in levels if lvl.price > price]
    below.sort(key=lambda lvl: price - lvl.price)
    above.sort(key=lambda lvl: lvl.price - price)

    def _pack(items: Sequence[HorizontalLevel]) -> List[Dict[str, float | int | str]]:
        out: List[Dict[str, float | int | str]] = []
        for item in items[: max(1, int(count))]:
            out.append(
                {
                    "price": float(item.price),
                    "touches": int(item.touches),
                    "side_bias": str(item.side_bias),
                    "score": float(item.score),
                }
            )
        return out

    return {"below": _pack(below), "above": _pack(above)}


def analyze_geometry(
    rows: Sequence[Sequence[Any]],
    *,
    pivot_left: int = 2,
    pivot_right: int = 2,
    level_tolerance_atr: float = 0.35,
    channel_lookback: int = 72,
    compression_short: int = 12,
    compression_long: int = 48,
) -> Dict[str, Any]:
    if len(rows) < 20:
        return {"status": "insufficient_rows", "rows": len(rows)}
    cur_price = _safe_float(rows[-1][4], 0.0)
    atr = _atr_from_rows(rows, 14)
    pivots = find_pivots(rows, left=pivot_left, right=pivot_right)
    levels = cluster_horizontal_levels(
        rows,
        pivots,
        atr=atr,
        tolerance_atr=level_tolerance_atr,
        min_touches=2,
        max_levels=8,
    )
    channel = regression_channel(rows, lookback=channel_lookback)
    compression = compression_state(rows, short_window=compression_short, long_window=compression_long)
    nearest = nearest_levels(levels, price=cur_price, count=3)
    return {
        "status": "ok",
        "rows": len(rows),
        "current_price": float(cur_price),
        "atr": float(atr),
        "pivot_count": len(pivots),
        "levels": [
            {
                "price": float(level.price),
                "touches": int(level.touches),
                "side_bias": str(level.side_bias),
                "score": float(level.score),
                "last_touch_ts_ms": int(level.last_touch_ts_ms),
            }
            for level in levels
        ],
        "nearest_levels": nearest,
        "channel": channel,
        "compression": compression,
    }
