#!/usr/bin/env python3
"""Walk-forward crypto pairs stat-arb diagnostic.

Replaces the old hard-coded-path script.  Hedge parameters and residual
statistics are fitted only on the trailing train window.  Trades from all
pairs are folded chronologically, costs are charged on both legs, and pair
concentration is reported.  The AR(1) residual gate is a stationarity proxy,
not a formal cointegration proof, so this script has no live authority.
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
from typing import Any, Sequence

from research_lab.result_receipt_validator import validate_receipt

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Params:
    train_days: int
    z_entry: float
    z_exit: float
    max_hold_days: int
    ar1_phi_max: float = 0.98
    cost_bps_per_leg_side: float = 8.0


def fit_ols(y: Sequence[float], x: Sequence[float]) -> tuple[float, float]:
    mean_x, mean_y = statistics.fmean(x), statistics.fmean(y)
    denom = sum((value - mean_x) ** 2 for value in x)
    beta = sum((xv - mean_x) * (yv - mean_y) for xv, yv in zip(x, y)) / denom if denom else 0.0
    return mean_y - beta * mean_x, beta


def ar1_phi(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 1.0
    lag, now = values[:-1], values[1:]
    _, phi = fit_ols(now, lag)
    return phi


def load_daily(path: Path) -> dict[str, dict[int, float]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(symbol): {int(day): float(price) for day, price in values.items() if float(price) > 0}
        for symbol, values in raw.items()
        if isinstance(values, dict)
    }


def pair_series(data: dict[str, dict[int, float]], a: str, b: str) -> list[tuple[int, float, float]]:
    days = sorted(set(data[a]).intersection(data[b]))
    return [(day, math.log(data[a][day]), math.log(data[b][day])) for day in days]


def run_pair(series: Sequence[tuple[int, float, float]], a: str, b: str, params: Params) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    position: dict[str, Any] | None = None
    for index in range(params.train_days, len(series)):
        day, log_a, log_b = series[index]

        # Manage an existing spread with the model frozen at entry.  The
        # previous implementation refit first and skipped the whole bar when
        # the new AR(1) estimate failed its gate.  That allowed a configured
        # 20-day position to remain open for more than 200 days.
        if position is not None:
            entry_model_z = (
                log_a
                - float(position["alpha"])
                - float(position["beta"]) * log_b
                - float(position["residual_mean"])
            ) / float(position["residual_std"])
            held = index - int(position["entry_index"])
            if abs(entry_model_z) > params.z_exit and held < params.max_hold_days:
                continue
            beta_entry = float(position["beta"])
            weight_a = 1.0 / (1.0 + abs(beta_entry))
            weight_b = abs(beta_entry) / (1.0 + abs(beta_entry))
            leg_return = (
                weight_a * (log_a - float(position["entry_log_a"]))
                - weight_b * (log_b - float(position["entry_log_b"]))
            )
            gross_bps = int(position["side"]) * leg_return * 10_000.0
            # Two legs, each opened and closed: four charged leg-sides.
            costs = 4.0 * params.cost_bps_per_leg_side
            trades.append({
                "pair": f"{a}/{b}",
                "entry_day": int(position["entry_day"]),
                "exit_day": day,
                "held_days": held,
                "side": "long_spread" if int(position["side"]) > 0 else "short_spread",
                "entry_z": round(float(position["entry_z"]), 6),
                "exit_z": round(entry_model_z, 6),
                "beta": round(beta_entry, 6),
                "ar1_phi": round(float(position["phi"]), 6),
                "gross_bps": round(gross_bps, 6),
                "cost_bps": costs,
                "pnl_bps": gross_bps - costs,
                "reason": "z_exit" if abs(entry_model_z) <= params.z_exit else "max_hold",
            })
            position = None
            continue

        train = series[index - params.train_days:index]
        ys, xs = [row[1] for row in train], [row[2] for row in train]
        alpha, beta = fit_ols(ys, xs)
        residuals = [yv - alpha - beta * xv for yv, xv in zip(ys, xs)]
        mean, std = statistics.fmean(residuals), statistics.stdev(residuals)
        phi = ar1_phi(residuals)
        if std <= 0 or not -0.50 < phi < params.ar1_phi_max:
            continue
        z = (log_a - alpha - beta * log_b - mean) / std
        if abs(z) < params.z_entry or beta <= 0:
            continue
        position = {
            "entry_index": index,
            "entry_day": day,
            "entry_log_a": log_a,
            "entry_log_b": log_b,
            "entry_z": z,
            "side": -1 if z > 0 else 1,
            "alpha": alpha,
            "beta": beta,
            "residual_mean": mean,
            "residual_std": std,
            "phi": phi,
        }
    return trades


def summarize(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(trades, key=lambda row: (int(row["entry_day"]), row["pair"]))
    values = [float(row["pnl_bps"]) for row in ordered]
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    folds = [
        sum(float(row["pnl_bps"]) for row in ordered[i * len(ordered) // 4:(i + 1) * len(ordered) // 4])
        for i in range(4)
    ]
    by_pair: dict[str, float] = {}
    for row in ordered:
        by_pair[row["pair"]] = by_pair.get(row["pair"], 0.0) + float(row["pnl_bps"])
    positive_total = sum(max(0.0, value) for value in by_pair.values())
    top_share = max((max(0.0, value) for value in by_pair.values()), default=0.0) / positive_total if positive_total else 1.0
    return {
        "trades": len(values),
        "net_bps": round(sum(values), 4),
        "mean_bps": round(statistics.fmean(values), 4) if values else 0.0,
        "pf": round(gains / losses, 4) if losses else (999.0 if gains else 0.0),
        "win_rate": round(sum(value > 0 for value in values) / len(values), 4) if values else 0.0,
        "positive_folds": sum(value > 0 for value in folds),
        "fold_net_bps": [round(value, 4) for value in folds],
        "positive_pairs": sum(value > 0 for value in by_pair.values()),
        "pairs_traded": len(by_pair),
        "top_positive_pair_share": round(top_share, 4),
    }


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="research_lab/data/daily_closes.json")
    parser.add_argument("--outdir", default="")
    args = parser.parse_args()
    data_path = ROOT / args.data
    data = load_daily(data_path)
    symbols = sorted(data)
    search = list(itertools.product((120, 180), (1.5, 2.0), (0.25, 0.50), (10, 20)))
    summaries: list[dict[str, Any]] = []
    trade_cache: dict[tuple[int, float, float, int], list[dict[str, Any]]] = {}
    for train_days, z_entry, z_exit, max_hold in search:
        params = Params(train_days, z_entry, z_exit, max_hold)
        trades: list[dict[str, Any]] = []
        for a, b in itertools.combinations(symbols, 2):
            series = pair_series(data, a, b)
            if len(series) < train_days + 90:
                continue
            trades.extend(run_pair(series, a, b, params))
        key = (train_days, z_entry, z_exit, max_hold)
        trade_cache[key] = trades
        summaries.append({**asdict(params), **summarize(trades)})
    best = max(summaries, key=lambda row: (row["positive_folds"], row["pf"], row["net_bps"]))
    best_key = (best["train_days"], best["z_entry"], best["z_exit"], best["max_hold_days"])
    best_trades = sorted(trade_cache[best_key], key=lambda row: (row["entry_day"], row["pair"]))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.outdir) if args.outdir else ROOT / "reports/research" / f"pairs_statarb_v2_{stamp}"
    outdir.mkdir(parents=True, exist_ok=True)
    write_csv(outdir / "summary.csv", summaries)
    write_csv(outdir / "best_trades.csv", best_trades)
    passes = (
        best["trades"] >= 100 and best["pf"] >= 1.10 and best["positive_folds"] >= 3
        and best["positive_pairs"] >= 5 and best["top_positive_pair_share"] <= 0.35
    )
    verdict = {
        "schema": "pairs_statarb_v2_walk_forward_diagnostic",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_authorized": False,
        "data": str(data_path.relative_to(ROOT)),
        "symbols": len(symbols),
        "candidate_pairs": len(list(itertools.combinations(symbols, 2))),
        "search_trials": len(search),
        "best": best,
        "decision": "PASS_TO_FORMAL_COINTEGRATION_OOS" if passes else "FAIL_OR_REBUILD",
        "limitations": [
            "AR1 residual gate is a stationarity proxy, not an ADF cointegration test",
            "16 configurations are selected on the diagnostic sample",
            "overlapping pair positions are not portfolio-capacity simulated",
            "daily closes cannot model intraday legging and execution",
        ],
    }
    receipt = validate_receipt(verdict, best_trades)
    (outdir / "validation_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verdict["measurement_validation_passed"] = bool(receipt["passed"])
    verdict["measurement_validation_receipt"] = "validation_receipt.json"
    if not receipt["passed"]:
        verdict["decision"] = "MEASUREMENT_INVALID"
    (outdir / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest = ROOT / "runtime/pairs_statarb_v2_latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({**verdict, "outdir": str(outdir)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"outdir": str(outdir), **verdict}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
