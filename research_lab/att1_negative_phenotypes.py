"""Exploratory ATT1 loss decomposition with fixed, causal feature buckets.

This tool diagnoses a frozen replay.  It does not select a filter, tune a
threshold, or grant promotion/live authority.  Any candidate suggested by the
output needs a new preregistered experiment on a disjoint window.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FEATURE_RE = re.compile(r"(?:^|\s)([a-z0-9_]+)=([^\s]+)", re.IGNORECASE)


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _feature_float(value: Any) -> float | None:
    if isinstance(value, str):
        match = re.match(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", value)
        value = match.group(0) if match else value
    return _float(value)


def parse_features(reason: str) -> dict[str, str]:
    return {match.group(1).lower(): match.group(2) for match in FEATURE_RE.finditer(reason or "")}


def _bucket(value: float | None, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    if value is None:
        return "missing"
    for cut, label in zip(cuts, labels):
        if value < cut:
            return label
    return labels[-1]


def _exit_path(reason: str) -> str:
    suffix = reason.rsplit("+", 1)[-1] if "+" in reason else "unknown"
    if "+TP2" in reason:
        return "tp2_or_runner"
    if "+TP1" in reason:
        return "tp1_then_runner"
    if suffix == "SL" or reason.endswith("+SL"):
        return "initial_stop"
    if "TRAIL_SL" in reason:
        return "trail_without_tp1"
    if "TIME" in suffix:
        return "time_stop"
    return suffix.lower()


def load_btc_regime(path: Path) -> tuple[list[int], list[float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("records", payload)
    times = [int(row["ts_ms"]) for row in rows]
    closes = [float(row["close"]) for row in rows]
    return times, closes


def btc_30d_regime(ts_ms: int, times: list[int], closes: list[float]) -> tuple[str, float | None]:
    if not times:
        return "missing", None
    now_idx = bisect.bisect_right(times, ts_ms) - 1
    old_idx = bisect.bisect_right(times, ts_ms - 30 * 86_400_000) - 1
    if old_idx < 0 or now_idx <= old_idx or closes[old_idx] <= 0:
        return "missing", None
    ret = closes[now_idx] / closes[old_idx] - 1.0
    if ret > 0.10:
        return "bull_gt_10pct", ret
    if ret < -0.10:
        return "bear_lt_minus_10pct", ret
    return "neutral", ret


def _group_stats(rows: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(float(row["r_multiple"]))
    result = []
    for name, values in grouped.items():
        gross_win = sum(value for value in values if value > 0)
        gross_loss = -sum(value for value in values if value < 0)
        result.append(
            {
                "value": name,
                "trades": len(values),
                "net_r": sum(values),
                "mean_r": sum(values) / len(values),
                "profit_factor_r": gross_win / gross_loss if gross_loss else None,
                "win_rate": sum(value > 0 for value in values) / len(values),
            }
        )
    return sorted(result, key=lambda item: (item["net_r"], item["value"]))


def analyze(trades_path: Path, btc_path: Path) -> dict[str, Any]:
    times, closes = load_btc_regime(btc_path)
    rows: list[dict[str, Any]] = []
    with trades_path.open(newline="", encoding="utf-8") as handle:
        for trade in csv.DictReader(handle):
            risk = _float(trade.get("initial_risk_usd"))
            pnl = _float(trade.get("pnl"))
            if not risk or risk <= 0 or pnl is None:
                continue
            reason = trade.get("signal_reason") or trade.get("reason") or ""
            features = parse_features(reason)
            ts_ms = int(trade["entry_ts"])
            regime, regime_ret = btc_30d_regime(ts_ms, times, closes)
            entry_dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            slope = _feature_float(features.get("slope"))
            rows.append(
                {
                    "r_multiple": pnl / risk,
                    "symbol": trade.get("symbol", "missing"),
                    "calendar_quarter": f"{entry_dt.year}-Q{(entry_dt.month - 1) // 3 + 1}",
                    "exit_path": _exit_path(trade.get("reason", "")),
                    "geometry": features.get("g2", "missing"),
                    "origin_source": features.get("g2originsrc", "missing"),
                    "support_source": features.get("g2supportsrc", "missing"),
                    "btc_30d_regime": regime,
                    "btc_30d_return": regime_ret,
                    "abs_slope_pct_day_bin": _bucket(abs(slope) if slope is not None else None, (1.0, 2.0, 4.0), ("lt_1", "1_to_2", "2_to_4", "gte_4")),
                    "rsi_bin": _bucket(_feature_float(features.get("rsi")), (45.0, 55.0), ("lt_45", "45_to_55", "gte_55")),
                    "r2_bin": _bucket(_feature_float(features.get("r2")), (0.90, 0.97), ("lt_0_90", "0_90_to_0_97", "gte_0_97")),
                    "age_bin": _bucket(_feature_float(features.get("age")), (4.0, 7.0), ("le_3", "4_to_6", "gte_7")),
                    "entry_distance_atr_bin": _bucket(_feature_float(features.get("entrydist")), (0.50, 1.00), ("lt_0_50", "0_50_to_1_00", "gte_1_00")),
                    "touch_distance_atr_bin": _bucket(_feature_float(features.get("touchdist")), (0.0, 0.50), ("lt_0", "0_to_0_50", "gte_0_50")),
                    "atr_pct_bin": _bucket(_feature_float(features.get("atrpct")), (1.0, 2.0), ("lt_1", "1_to_2", "gte_2")),
                }
            )
    values = [float(row["r_multiple"]) for row in rows]
    gross_win = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    dimensions = [
        "symbol", "calendar_quarter", "exit_path", "geometry", "origin_source",
        "support_source", "btc_30d_regime", "abs_slope_pct_day_bin", "rsi_bin",
        "r2_bin", "age_bin", "entry_distance_atr_bin", "touch_distance_atr_bin",
        "atr_pct_bin",
    ]
    groups = {dimension: _group_stats(rows, dimension) for dimension in dimensions}
    candidates = []
    for dimension, buckets in groups.items():
        for bucket in buckets:
            if bucket["trades"] >= 15:
                candidates.append({"dimension": dimension, **bucket})
    candidates.sort(key=lambda item: item["net_r"])
    return {
        "schema_id": "att1_negative_phenotypes_v1",
        "authority": "exploratory_diagnosis_only_no_filter_selection_no_live_authority",
        "source": str(trades_path),
        "btc_regime_source": str(btc_path),
        "trades": len(values),
        "net_r": sum(values),
        "mean_r": sum(values) / len(values) if values else None,
        "profit_factor_r": gross_win / gross_loss if gross_loss else None,
        "groups": groups,
        "most_negative_buckets_min_n15": candidates[:12],
        "interpretation_rule": "Buckets are exploratory explanations, not tradable filters. A next experiment must freeze one causal mechanism and use a disjoint window.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", required=True, type=Path)
    parser.add_argument("--btc-bars", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = analyze(args.trades, args.btc_bars)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("trades", "net_r", "mean_r", "profit_factor_r")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
