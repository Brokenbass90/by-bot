from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "position_geometry_v1"
_NUMBER = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))"
_FIELD_PATTERNS = {
    "trendline": re.compile(rf"\btl={_NUMBER}", re.IGNORECASE),
    "level": re.compile(rf"\b(?:lvl|level)={_NUMBER}", re.IGNORECASE),
    "upper": re.compile(rf"\bupper={_NUMBER}", re.IGNORECASE),
    "lower": re.compile(rf"\blower={_NUMBER}", re.IGNORECASE),
    "resistance": re.compile(rf"\b(?:res|resistance)={_NUMBER}", re.IGNORECASE),
    "support": re.compile(rf"\b(?:sup|support)={_NUMBER}", re.IGNORECASE),
    "reaction_origin": re.compile(rf"\bg2origin={_NUMBER}", re.IGNORECASE),
    "opposing_support": re.compile(rf"\bg2support={_NUMBER}", re.IGNORECASE),
}
_METRIC_PATTERNS = {
    "rsi": re.compile(rf"\brsi={_NUMBER}", re.IGNORECASE),
    "r2": re.compile(rf"\br2={_NUMBER}", re.IGNORECASE),
    "pivots": re.compile(r"\bpivots=(\d+)", re.IGNORECASE),
    "age_bars": re.compile(rf"\bage={_NUMBER}", re.IGNORECASE),
    "entry_distance_atr": re.compile(rf"\bentrydist={_NUMBER}", re.IGNORECASE),
    "touch_distance_atr": re.compile(rf"\btouchdist={_NUMBER}", re.IGNORECASE),
    "reject_depth_atr": re.compile(rf"\breject={_NUMBER}", re.IGNORECASE),
    "body_atr": re.compile(rf"\bbody={_NUMBER}", re.IGNORECASE),
    "atr_pct": re.compile(rf"\batrpct={_NUMBER}", re.IGNORECASE),
    "quality": re.compile(rf"\bquality={_NUMBER}", re.IGNORECASE),
    "room_r": re.compile(rf"\broomr={_NUMBER}", re.IGNORECASE),
}
_SLOPE = re.compile(rf"\bslope={_NUMBER}%/d", re.IGNORECASE)
_ANCHORS = re.compile(r"\banchors=([0-9eE+.:|\-]+)", re.IGNORECASE)


def _finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def parse_signal_geometry(reason: str) -> dict[str, Any]:
    """Parse the level actually recorded by the strategy at signal time."""
    text = str(reason or "").strip()
    horizontal_levels: list[dict[str, Any]] = []
    trendline = None
    for role, pattern in _FIELD_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        price = _finite_float(match.group(1))
        if price is None or price <= 0:
            continue
        if role == "trendline":
            trendline = price
        else:
            horizontal_levels.append(
                {
                    "role": role,
                    "price": price,
                    "provenance": "signal_reason",
                }
            )

    slope_match = _SLOPE.search(text)
    slope = _finite_float(slope_match.group(1)) if slope_match else None
    anchor_match = _ANCHORS.search(text)
    pivot_points: list[dict[str, Any]] = []
    if anchor_match:
        for raw_point in anchor_match.group(1).split("|"):
            if ":" not in raw_point:
                continue
            raw_ts, raw_price = raw_point.split(":", 1)
            ts_value = _finite_float(raw_ts)
            price_value = _finite_float(raw_price)
            if ts_value is None or price_value is None or price_value <= 0:
                continue
            ts_ms = int(ts_value if ts_value > 10**11 else ts_value * 1000)
            pivot_points.append({"ts_ms": ts_ms, "price": float(price_value)})
    sloped_lines: list[dict[str, Any]] = []
    if trendline is not None:
        sloped_lines.append(
            {
                "role": "signal_trendline",
                "projection_at_signal": trendline,
                "slope_pct_per_day": slope,
                "points_ts_px": pivot_points,
                "provenance": "signal_reason",
                "exact_projection": True,
                "exact_pivots": bool(pivot_points),
            }
        )

    metrics: dict[str, Any] = {}
    for name, pattern in _METRIC_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        parsed = _finite_float(match.group(1))
        if parsed is not None:
            metrics[name] = int(parsed) if name == "pivots" else parsed

    primary_level = trendline
    primary_role = "trendline" if trendline is not None else None
    if primary_level is None and horizontal_levels:
        primary_level = horizontal_levels[0]["price"]
        primary_role = horizontal_levels[0]["role"]

    return {
        "available": primary_level is not None,
        "primary_level": primary_level,
        "primary_role": primary_role,
        "horizontal_levels": horizontal_levels,
        "sloped_lines": sloped_lines,
        "metrics": metrics,
        "source_reason": text,
        "limitations": (
            []
            if not sloped_lines or pivot_points
            else ["pivot_points_not_serialized_by_strategy"]
        ),
    }


def build_position_geometry(
    *,
    symbol: str,
    strategy: str,
    side: str,
    entry_ts: int,
    entry_price: float | None,
    sl_price: float | None,
    tp_prices: list[float] | None,
    signal_reason: str,
    order_id: str = "",
    order_link_id: str = "",
) -> dict[str, Any]:
    parsed = parse_signal_geometry(signal_reason)
    return {
        "schema_version": SCHEMA_VERSION,
        "symbol": str(symbol or "").upper(),
        "strategy": str(strategy or ""),
        "side": str(side or ""),
        "entry_ts": int(entry_ts or 0),
        "entry_price": _finite_float(entry_price),
        "sl_price": _finite_float(sl_price),
        "tp_prices": [
            value for value in (_finite_float(item) for item in (tp_prices or []))
            if value is not None
        ],
        "order_id": str(order_id or ""),
        "order_link_id": str(order_link_id or ""),
        **parsed,
    }


def _safe_key(value: str) -> str:
    key = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return key[:180] or "unknown_order"


def write_position_geometry(
    directory: str | Path,
    key: str,
    payload: dict[str, Any],
) -> Path:
    """Atomically persist the immutable entry snapshot."""
    root = Path(directory).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_safe_key(key)}.json"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path
