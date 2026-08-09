#!/usr/bin/env python3
"""Render one actual FX smart-grid trade for visual strategy audit."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / "runtime" / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(PROJECT_ROOT / "runtime" / "cache"))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from research_lab.fx_smart_grid_v1 import ROOT, aggregate_h1, load_rows


def _ts_label(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%m-%d\n%H:%M")


def _find_rows(symbol: str, entry_ts: int, exit_ts: int) -> list[list[float]]:
    rows = aggregate_h1(load_rows(ROOT / "data_cache/forex" / f"{symbol}_M5.csv"))
    indexes = {int(row[0]): i for i, row in enumerate(rows)}
    start = max(0, indexes[entry_ts] - 84)
    end = min(len(rows), indexes[exit_ts] + 8)
    return rows[start:end]


def render(trade: dict[str, str], output: Path) -> None:
    symbol = trade["symbol"]
    entry_ts, exit_ts = int(trade["entry_ts"]), int(trade["exit_ts"])
    rows = _find_rows(symbol, entry_ts, exit_ts)
    entry_prices = [float(x) for x in json.loads(trade["entry_prices"])]
    entry_timestamps = [int(x) for x in json.loads(trade["entry_timestamps"])]
    side = trade["side"]
    colors = {"up": "#2F80ED", "down": "#D76A55"}

    fig, ax = plt.subplots(figsize=(15, 8), facecolor="#FAFAF8")
    ax.set_facecolor("#FAFAF8")
    for i, row in enumerate(rows):
        _, opn, high, low, close, _ = row
        color = colors["up" if close >= opn else "down"]
        ax.vlines(i, low, high, color=color, linewidth=1.0, alpha=0.9)
        body_low = min(opn, close)
        height = max(abs(close - opn), max(abs(close), 1.0) * 1e-6)
        ax.add_patch(Rectangle((i - 0.32, body_low), 0.64, height, facecolor=color, edgecolor=color))

    index = {int(row[0]): i for i, row in enumerate(rows)}
    entry_i, exit_i = index[entry_ts], index[exit_ts]
    low = float(trade["range_low"])
    center = float(trade["range_center"])
    high = float(trade["range_high"])
    kill = float(trade["kill_price"])
    exit_price = float(trade["exit_price"])
    range_start = max(0, entry_i - 72)

    ax.hlines([low, high], range_start, entry_i, colors="#9A6B12", linestyles="--", linewidth=1.5, label="Range boundaries")
    ax.hlines(center, range_start, exit_i, colors="#314A67", linewidth=1.7, label="Center take")
    ax.hlines(kill, entry_i, exit_i, colors="#B33A3A", linestyles=":", linewidth=1.8, label="Range-break kill")
    for layer, (layer_ts, price) in enumerate(zip(entry_timestamps, entry_prices), start=1):
        layer_i = index[layer_ts]
        ax.scatter(layer_i, price, s=80, marker="v" if side == "short" else "^", color="#D18B00", zorder=5)
        ax.annotate(f"L{layer} {price:g}", (layer_i, price), xytext=(8, 5), textcoords="offset points", fontsize=9)
    ax.scatter(exit_i, exit_price, s=90, marker="X", color="#222222", zorder=6)
    ax.annotate(f"Exit: {trade['reason']}\n{exit_price:g}", (exit_i, exit_price), xytext=(10, -28), textcoords="offset points", fontsize=9)

    step = max(1, len(rows) // 12)
    ticks = list(range(0, len(rows), step))
    ax.set_xticks(ticks, [_ts_label(rows[i][0]) for i in ticks])
    ax.set_title(f"FX smart-grid v1 — actual {symbol} {side} trade", loc="left", fontsize=16, weight="bold")
    ax.set_xlabel("UTC H1 bars")
    ax.set_ylabel("Price")
    ax.grid(axis="y", color="#D8D8D2", linewidth=0.7, alpha=0.7)
    ax.legend(loc="upper left", frameon=False, ncols=3)
    ax.text(
        0.01, -0.16,
        f"Stress costs: {float(trade['cost_bps']):.2f} bps | PnL: {float(trade['pnl_bps']):+.2f} bps | "
        f"Layers: {trade['layers']} | Source: public Dukascopy M5 aggregated to H1",
        transform=ax.transAxes, fontsize=10, color="#444444",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--row", type=int, default=0)
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    with (run_dir / "best_stress_trades.csv").open(newline="", encoding="utf-8") as handle:
        trades = list(csv.DictReader(handle))
    if not trades:
        raise SystemExit("No best-stress trades found")
    # Use a representative median trade rather than a cherry-picked winner.
    ordered = sorted(trades, key=lambda row: float(row["pnl_bps"]))
    row = ordered[len(ordered) // 2] if args.row == 0 else trades[args.row]
    output = Path(args.output) if args.output else run_dir / "representative_trade.png"
    render(row, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
