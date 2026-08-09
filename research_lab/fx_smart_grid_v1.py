#!/usr/bin/env python3
"""Bounded FX smart-grid diagnostic on public M5 data.

This is deliberately not a martingale and not a live executor.  It compares a
single range-fade entry with a fixed-budget, equal-weight 3-layer grid.  Every
position has a range-break kill, a time/session exit, conservative same-bar
resolution, base and stress costs, and four chronological folds.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Params:
    lookback: int
    entry_atr: float
    er_max: float
    max_layers: int
    spacing_atr: float = 0.45
    kill_buffer_atr: float = 0.35
    max_hold_h1: int = 12


def load_rows(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append([float(row[k]) for k in ("ts", "o", "h", "l", "c", "v")])
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def aggregate_h1(rows: Sequence[Sequence[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    bucket: list[Sequence[float]] = []
    bucket_ts: int | None = None
    for row in rows:
        ts = int(float(row[0]))
        current = ts // 3600 * 3600
        if bucket_ts is None:
            bucket_ts = current
        if current != bucket_ts:
            if len(bucket) == 12:
                out.append([
                    float(bucket_ts), float(bucket[0][1]),
                    max(float(x[2]) for x in bucket), min(float(x[3]) for x in bucket),
                    float(bucket[-1][4]), sum(float(x[5]) for x in bucket),
                ])
            bucket, bucket_ts = [], current
        bucket.append(row)
    if bucket_ts is not None and len(bucket) == 12:
        out.append([
            float(bucket_ts), float(bucket[0][1]),
            max(float(x[2]) for x in bucket), min(float(x[3]) for x in bucket),
            float(bucket[-1][4]), sum(float(x[5]) for x in bucket),
        ])
    return out


def atr(rows: Sequence[Sequence[float]], end: int, period: int = 14) -> float:
    start = max(1, end - period + 1)
    values = []
    for i in range(start, end + 1):
        h, low, prev = float(rows[i][2]), float(rows[i][3]), float(rows[i - 1][4])
        values.append(max(h - low, abs(h - prev), abs(low - prev)))
    return statistics.fmean(values) if values else float("nan")


def efficiency(closes: Sequence[float]) -> float:
    travel = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return abs(closes[-1] - closes[0]) / travel if travel > 0 else 0.0


def pip_size(symbol: str) -> float:
    return 0.01 if symbol.endswith("JPY") or symbol == "XAUUSD" else 0.0001


def roundtrip_cost_bps(symbol: str, price: float, cost: dict[str, Any], arm: str) -> float:
    instrument = cost["instruments"][symbol]
    spread = float(instrument["spread_pips_base"]) * float(instrument.get("pip_size", pip_size(symbol)))
    if arm == "stress":
        spread *= 2.0
        commission = 2.0 * float(cost["research_arms"]["stress"]["commission_bps_per_side"])
        slippage = 0.8
    else:
        commission = 0.0
        slippage = 0.3
    return spread / price * 10_000.0 + commission + slippage


def _finish(side: int, entries: list[float], exit_price: float, cost_bps: float) -> float:
    average = statistics.fmean(entries)
    gross = side * (exit_price / average - 1.0) * 10_000.0
    return gross - cost_bps


def run_symbol(
    symbol: str,
    rows: Sequence[Sequence[float]],
    params: Params,
    cost: dict[str, Any],
    arm: str,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    warmup = max(params.lookback + 2, 80)
    i = warmup
    while i < len(rows) - 2:
        history = rows[i - params.lookback:i]
        closes = [float(x[4]) for x in history]
        a = atr(rows, i - 1)
        if not math.isfinite(a) or a <= 0 or efficiency(closes) > params.er_max:
            i += 1
            continue
        high = max(float(x[2]) for x in history)
        low = min(float(x[3]) for x in history)
        center = (high + low) / 2.0
        width_atr = (high - low) / a
        # Too narrow cannot pay costs; too wide is usually a trend disguised as range.
        if not (2.5 <= width_atr <= 8.0):
            i += 1
            continue
        signal_close = float(rows[i - 1][4])
        if signal_close <= center - params.entry_atr * a:
            side = 1
        elif signal_close >= center + params.entry_atr * a:
            side = -1
        else:
            i += 1
            continue
        entry_index = i
        entry = float(rows[entry_index][1])
        # Never arm a fresh grid after the liquid sessions are mostly over.
        entry_hour = datetime.fromtimestamp(float(rows[entry_index][0]), tz=timezone.utc).hour
        if entry_hour < 6 or entry_hour > 16:
            i += 1
            continue
        entries = [entry]
        entry_timestamps = [int(rows[entry_index][0])]
        next_layer = entry - side * params.spacing_atr * a
        stop = (low - params.kill_buffer_atr * a) if side > 0 else (high + params.kill_buffer_atr * a)
        exit_index = min(len(rows) - 1, entry_index + params.max_hold_h1)
        reason = "time"
        exit_price = float(rows[exit_index][4])
        for j in range(entry_index + 1, exit_index + 1):
            h, lo, close = float(rows[j][2]), float(rows[j][3]), float(rows[j][4])
            hour = datetime.fromtimestamp(float(rows[j][0]), tz=timezone.utc).hour
            # Worst case when kill and profit are both touched in one H1 bar.
            if (side > 0 and lo <= stop) or (side < 0 and h >= stop):
                exit_price, exit_index, reason = stop, j, "range_break_kill"
                break
            if (side > 0 and h >= center) or (side < 0 and lo <= center):
                exit_price, exit_index, reason = center, j, "center_take"
                break
            if hour >= 20:
                exit_price, exit_index, reason = close, j, "session_flatten"
                break
            if len(entries) < params.max_layers:
                crossed = close <= next_layer if side > 0 else close >= next_layer
                if crossed:
                    entries.append(close)
                    entry_timestamps.append(int(rows[j][0]))
                    next_layer = close - side * params.spacing_atr * a
        cost_bps = roundtrip_cost_bps(symbol, statistics.fmean(entries), cost, arm)
        pnl_bps = _finish(side, entries, exit_price, cost_bps)
        trades.append({
            "symbol": symbol,
            "signal_ts": int(rows[i - 1][0]),
            "entry_ts": int(rows[entry_index][0]),
            "exit_ts": int(rows[exit_index][0]),
            "side": "long" if side > 0 else "short",
            "layers": len(entries),
            "entry_prices": json.dumps([round(x, 8) for x in entries]),
            "entry_timestamps": json.dumps(entry_timestamps),
            "average_entry": round(statistics.fmean(entries), 8),
            "exit_price": round(exit_price, 8),
            "range_low": round(low, 8),
            "range_center": round(center, 8),
            "range_high": round(high, 8),
            "range_atr": round(a, 8),
            "kill_price": round(stop, 8),
            "cost_bps": round(cost_bps, 6),
            "pnl_bps": pnl_bps,
            "reason": reason,
        })
        i = exit_index + 1
    return trades


def summarize(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    values = [float(x["pnl_bps"]) for x in trades]
    gains = sum(x for x in values if x > 0)
    losses = -sum(x for x in values if x < 0)
    ordered = sorted(trades, key=lambda x: int(x["entry_ts"]))
    folds = []
    for fold in range(4):
        part = ordered[fold * len(ordered) // 4:(fold + 1) * len(ordered) // 4]
        folds.append(sum(float(x["pnl_bps"]) for x in part))
    return {
        "trades": len(values),
        "net_bps": round(sum(values), 4),
        "mean_bps": round(statistics.fmean(values), 4) if values else 0.0,
        "pf": round(gains / losses, 4) if losses > 0 else (999.0 if gains > 0 else 0.0),
        "win_rate": round(sum(x > 0 for x in values) / len(values), 4) if values else 0.0,
        "positive_folds": sum(x > 0 for x in folds),
        "fold_net_bps": [round(x, 4) for x in folds],
    }


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", default="EURUSD,GBPUSD,USDJPY,EURJPY,GBPJPY,XAUUSD")
    parser.add_argument("--outdir", default="")
    args = parser.parse_args()
    cost_path = ROOT / "configs/research/fx_oanda_public_cost_contract_20260729.json"
    cost = json.loads(cost_path.read_text(encoding="utf-8"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir) if args.outdir else ROOT / "reports/research" / f"fx_smart_grid_v1_{stamp}"
    pairs = [x.strip().upper() for x in args.pairs.split(",") if x.strip()]
    data = {symbol: aggregate_h1(load_rows(ROOT / "data_cache/forex" / f"{symbol}_M5.csv")) for symbol in pairs}
    results: list[dict[str, Any]] = []
    grid = itertools.product((48, 72), (0.8, 1.2), (0.20, 0.30), (1, 3))
    for lookback, entry_atr, er_max, layers in grid:
        params = Params(lookback, entry_atr, er_max, layers)
        for arm in ("base", "stress"):
            trades = [trade for symbol in pairs for trade in run_symbol(symbol, data[symbol], params, cost, arm)]
            results.append({**asdict(params), "arm": arm, **summarize(trades)})
    outdir.mkdir(parents=True, exist_ok=True)
    write_csv(outdir / "summary.csv", results)
    stress = [row for row in results if row["arm"] == "stress"]
    best = max(stress, key=lambda row: (row["positive_folds"], row["pf"], row["net_bps"]))
    baseline_key = (best["lookback"], best["entry_atr"], best["er_max"])
    baseline = next(
        row for row in stress
        if (row["lookback"], row["entry_atr"], row["er_max"]) == baseline_key and row["max_layers"] == 1
    )
    best_params = Params(
        lookback=int(best["lookback"]),
        entry_atr=float(best["entry_atr"]),
        er_max=float(best["er_max"]),
        max_layers=int(best["max_layers"]),
        spacing_atr=float(best["spacing_atr"]),
        kill_buffer_atr=float(best["kill_buffer_atr"]),
        max_hold_h1=int(best["max_hold_h1"]),
    )
    best_trades = [
        trade
        for symbol in pairs
        for trade in run_symbol(symbol, data[symbol], best_params, cost, "stress")
    ]
    write_csv(outdir / "best_stress_trades.csv", best_trades)
    passes = (
        best["max_layers"] == 3 and best["trades"] >= 100 and best["pf"] >= 1.05
        and best["positive_folds"] >= 3 and best["net_bps"] > baseline["net_bps"]
    )
    verdict = {
        "schema": "fx_smart_grid_v1_bounded_diagnostic",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_authorized": False,
        "data": "public Dukascopy M5 aggregated to complete H1",
        "cost_contract": str(cost_path.relative_to(ROOT)),
        "cost_contract_expired_for_promotion": True,
        "overnight_financing_avoided": "new entries 06-16 UTC; force-flat by 20 UTC",
        "best_stress": best,
        "matching_single_entry_stress": baseline,
        "decision": "PASS_TO_WALK_FORWARD" if passes else "FAIL_REBUILD_OR_CLOSE",
        "limitations": [
            "H1 OHLC cannot reproduce real multi-order queue/fill priority",
            "public cost contract is a research proxy and expired for promotion",
            "selection among 16 configurations is diagnostic, not OOS evidence",
        ],
    }
    (outdir / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest = ROOT / "runtime/fx_smart_grid_v1_latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({**verdict, "outdir": str(outdir)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"outdir": str(outdir), **verdict}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
