#!/usr/bin/env python3
"""Regime-gated FX range grid v2 (research-only).

V2 rebuilds range detection instead of tuning the failed v1.  A grid may arm
only after alternating boundary touches, low directional efficiency, bounded
regression drift, no fresh close breakout, and a liquid-session entry.  Layers
are equal-budget; there is no martingale, live authority, or overnight hold.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_lab.fx_smart_grid_v1 import (
    ROOT,
    aggregate_h1,
    atr,
    efficiency,
    load_rows,
    roundtrip_cost_bps,
    summarize,
    write_csv,
)


@dataclass(frozen=True)
class ParamsV2:
    lookback: int
    entry_band_atr: float
    er_max: float
    slope_span_atr_max: float
    max_layers: int
    min_alternating_touches: int = 3
    touch_band_atr: float = 0.25
    breakout_cooldown_bars: int = 5
    breakout_close_atr: float = 0.10
    spacing_atr: float = 0.35
    kill_buffer_atr: float = 0.30
    max_hold_h1: int = 12
    volume_spike_mult: float = 2.0


def regression_slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_x = (len(values) - 1) / 2.0
    mean_y = statistics.fmean(values)
    denom = sum((i - mean_x) ** 2 for i in range(len(values)))
    if denom <= 0:
        return 0.0
    return sum((i - mean_x) * (value - mean_y) for i, value in enumerate(values)) / denom


def alternating_boundary_touches(
    rows: Sequence[Sequence[float]],
    low: float,
    high: float,
    atr_value: float,
    band_atr: float,
    *,
    min_separation: int = 3,
) -> list[str]:
    """Compress separated boundary contacts into an alternating L/H sequence."""
    band = max(0.0, float(band_atr)) * float(atr_value)
    touches: list[tuple[int, str]] = []
    for index, row in enumerate(rows):
        hit_low = float(row[3]) <= low + band
        hit_high = float(row[2]) >= high - band
        if hit_low == hit_high:
            continue
        side = "L" if hit_low else "H"
        if touches and touches[-1][1] == side:
            touches[-1] = (index, side)
        elif not touches or index - touches[-1][0] >= min_separation:
            touches.append((index, side))
    return [side for _, side in touches]


def qualifies_range(
    rows: Sequence[Sequence[float]], index: int, params: ParamsV2
) -> tuple[dict[str, float] | None, str]:
    anchor_end = index - params.breakout_cooldown_bars
    anchor_start = anchor_end - params.lookback
    if anchor_start < 2:
        return None, "warmup"
    history = rows[anchor_start:anchor_end]
    recent = rows[anchor_end:index]
    a = atr(rows, anchor_end - 1)
    if not math.isfinite(a) or a <= 0:
        return None, "atr_invalid"
    closes = [float(row[4]) for row in history]
    low = min(float(row[3]) for row in history)
    high = max(float(row[2]) for row in history)
    width_atr = (high - low) / a
    if not 2.5 <= width_atr <= 6.0:
        return None, "range_width"
    er = efficiency(closes)
    if er > params.er_max:
        return None, "directional_efficiency"
    slope_span_atr = abs(regression_slope(closes)) * (len(closes) - 1) / a
    if slope_span_atr > params.slope_span_atr_max:
        return None, "regression_drift"
    touch_sequence = alternating_boundary_touches(
        history, low, high, a, params.touch_band_atr
    )
    if len(touch_sequence) < params.min_alternating_touches:
        return None, "insufficient_touches"
    recent_closes = [float(row[4]) for row in recent]
    breakout_pad = params.breakout_close_atr * a
    if any(value > high + breakout_pad or value < low - breakout_pad for value in recent_closes):
        return None, "fresh_breakout"
    historical_volumes = [float(row[5]) for row in history if float(row[5]) > 0]
    recent_volumes = [float(row[5]) for row in recent if float(row[5]) > 0]
    if historical_volumes and recent_volumes:
        base_volume = statistics.median(historical_volumes)
        if (
            base_volume > 0
            and statistics.fmean(recent_volumes) > params.volume_spike_mult * base_volume
            and efficiency(recent_closes) > 0.50
        ):
            return None, "directional_volume_spike"
    return {
        "atr": a,
        "low": low,
        "high": high,
        "center": (low + high) / 2.0,
        "width_atr": width_atr,
        "efficiency": er,
        "slope_span_atr": slope_span_atr,
        "touches": float(len(touch_sequence)),
    }, "qualified"


def run_symbol_v2(
    symbol: str,
    rows: Sequence[Sequence[float]],
    params: ParamsV2,
    cost: dict[str, Any],
    arm: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    trades: list[dict[str, Any]] = []
    rejects: dict[str, int] = {}
    i = params.lookback + params.breakout_cooldown_bars + 2
    while i < len(rows) - 2:
        range_info, reason = qualifies_range(rows, i, params)
        if range_info is None:
            rejects[reason] = rejects.get(reason, 0) + 1
            i += 1
            continue
        a = range_info["atr"]
        low, high, center = range_info["low"], range_info["high"], range_info["center"]
        signal_close = float(rows[i - 1][4])
        if signal_close <= low + params.entry_band_atr * a:
            side = 1
        elif signal_close >= high - params.entry_band_atr * a:
            side = -1
        else:
            rejects["not_at_boundary"] = rejects.get("not_at_boundary", 0) + 1
            i += 1
            continue
        entry_hour = datetime.fromtimestamp(float(rows[i][0]), tz=timezone.utc).hour
        if not 6 <= entry_hour <= 16:
            rejects["session_gate"] = rejects.get("session_gate", 0) + 1
            i += 1
            continue
        entries = [float(rows[i][1])]
        entry_times = [int(rows[i][0])]
        next_layer = entries[0] - side * params.spacing_atr * a
        kill = low - params.kill_buffer_atr * a if side > 0 else high + params.kill_buffer_atr * a
        exit_index = min(len(rows) - 1, i + params.max_hold_h1)
        exit_price, exit_reason = float(rows[exit_index][4]), "time"
        for j in range(i + 1, exit_index + 1):
            bar_high, bar_low, close = float(rows[j][2]), float(rows[j][3]), float(rows[j][4])
            hour = datetime.fromtimestamp(float(rows[j][0]), tz=timezone.utc).hour
            if (side > 0 and bar_low <= kill) or (side < 0 and bar_high >= kill):
                exit_price, exit_index, exit_reason = kill, j, "emergency_range_break"
                break
            if (side > 0 and bar_high >= center) or (side < 0 and bar_low <= center):
                exit_price, exit_index, exit_reason = center, j, "center_take"
                break
            if hour >= 20:
                exit_price, exit_index, exit_reason = close, j, "session_flatten"
                break
            if len(entries) < params.max_layers:
                crossed = close <= next_layer if side > 0 else close >= next_layer
                if crossed:
                    entries.append(close)
                    entry_times.append(int(rows[j][0]))
                    next_layer = close - side * params.spacing_atr * a
        average = statistics.fmean(entries)
        costs = roundtrip_cost_bps(symbol, average, cost, arm)
        gross = side * (exit_price / average - 1.0) * 10_000.0
        trades.append({
            "symbol": symbol,
            "entry_ts": int(rows[i][0]),
            "exit_ts": int(rows[exit_index][0]),
            "side": "long" if side > 0 else "short",
            "layers": len(entries),
            "entry_prices": json.dumps([round(x, 8) for x in entries]),
            "entry_timestamps": json.dumps(entry_times),
            "average_entry": round(average, 8),
            "exit_price": round(exit_price, 8),
            "range_low": round(low, 8),
            "range_center": round(center, 8),
            "range_high": round(high, 8),
            "range_atr": round(a, 8),
            "range_efficiency": round(range_info["efficiency"], 6),
            "slope_span_atr": round(range_info["slope_span_atr"], 6),
            "alternating_touches": int(range_info["touches"]),
            "kill_price": round(kill, 8),
            "cost_bps": round(costs, 6),
            "pnl_bps": gross - costs,
            "reason": exit_reason,
        })
        i = exit_index + 1
    return trades, rejects


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", default="EURUSD,GBPUSD,USDJPY,EURJPY,GBPJPY,XAUUSD")
    parser.add_argument("--outdir", default="")
    args = parser.parse_args()
    cost_path = ROOT / "configs/research/fx_oanda_public_cost_contract_20260729.json"
    cost = json.loads(cost_path.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir) if args.outdir else ROOT / "reports/research" / f"fx_smart_grid_v2_{stamp}"
    pairs = [item.strip().upper() for item in args.pairs.split(",") if item.strip()]
    data = {
        symbol: aggregate_h1(load_rows(ROOT / "data_cache/forex" / f"{symbol}_M5.csv"))
        for symbol in pairs
    }
    search = list(itertools.product((48, 72), (0.20, 0.35), (0.12, 0.20), (0.75, 1.25), (1, 3)))
    rows: list[dict[str, Any]] = []
    trade_cache: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    reject_cache: dict[tuple[Any, ...], dict[str, int]] = {}
    for lookback, entry_band, er_max, slope_max, layers in search:
        params = ParamsV2(lookback, entry_band, er_max, slope_max, layers)
        for arm in ("base", "stress"):
            trades: list[dict[str, Any]] = []
            rejects: dict[str, int] = {}
            for symbol in pairs:
                symbol_trades, symbol_rejects = run_symbol_v2(symbol, data[symbol], params, cost, arm)
                trades.extend(symbol_trades)
                for reason, count in symbol_rejects.items():
                    rejects[reason] = rejects.get(reason, 0) + count
            key = (lookback, entry_band, er_max, slope_max, layers, arm)
            trade_cache[key], reject_cache[key] = trades, rejects
            rows.append({**asdict(params), "arm": arm, **summarize(trades)})
    outdir.mkdir(parents=True, exist_ok=True)
    write_csv(outdir / "summary.csv", rows)
    stress = [row for row in rows if row["arm"] == "stress"]
    best = max(stress, key=lambda row: (row["positive_folds"], row["pf"], row["net_bps"]))
    best_key = (
        best["lookback"], best["entry_band_atr"], best["er_max"],
        best["slope_span_atr_max"], best["max_layers"], "stress",
    )
    best_trades = trade_cache[best_key]
    write_csv(outdir / "best_stress_trades.csv", best_trades)
    rejects = reject_cache[best_key]
    verdict = {
        "schema": "fx_smart_grid_v2_bounded_diagnostic",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_authorized": False,
        "search_trials": len(search),
        "data": "public Dukascopy M5 aggregated to complete H1",
        "cost_contract": str(cost_path.relative_to(ROOT)),
        "cost_contract_expired_for_promotion": True,
        "best_stress": best,
        "best_rejection_counts": rejects,
        "decision": (
            "PASS_TO_UNTOUCHED_OOS"
            if best["trades"] >= 100 and best["pf"] >= 1.10 and best["positive_folds"] >= 3
            else "FAIL_OR_REBUILD"
        ),
        "limitations": [
            "32 configurations are diagnostic selection, not OOS evidence",
            "H1 OHLC cannot model limit queue priority or intrabar layer ordering",
            "public cost contract is expired for promotion",
            "news blackout is not yet available in the public dataset",
        ],
    }
    (outdir / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest = ROOT / "runtime/fx_smart_grid_v2_latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({**verdict, "outdir": str(outdir)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"outdir": str(outdir), **verdict}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
