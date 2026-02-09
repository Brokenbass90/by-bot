#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Find PnL killers inside a run folder.

Auto-detects:
- trades_inplay.csv
- trades_bounce.csv
- trades.csv (portfolio/core-suite)

Usage:
  python3 scripts/find_killers.py path/to/run_folder --top 15
"""

import argparse
import os
import csv
import math
from collections import defaultdict


def _to_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def profit_factor(gp, gl):
    if gl == 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def fmt_pf(x):
    if math.isinf(x):
        return "inf"
    return f"{x:.2f}"


def analyze_csv(path, strategy_hint=""):
    by = defaultdict(lambda: {"n": 0, "gp": 0.0, "gl": 0.0})

    with open(path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            sym = (row.get("symbol") or "").strip()
            if not sym:
                continue
            pnl = _to_float(row.get("pnl"))
            by[sym]["n"] += 1
            if pnl > 0:
                by[sym]["gp"] += pnl
            elif pnl < 0:
                by[sym]["gl"] += -pnl

    out = []
    for sym, d in by.items():
        net = d["gp"] - d["gl"]
        pf = profit_factor(d["gp"], d["gl"])
        out.append((net, sym, d["n"], pf))

    out.sort()  # worst first
    return out


def print_top(title, rows, top):
    print("\n" + title)
    print("symbol\ttrades\tPF\tnetPnL")
    for net, sym, n, pf in rows[:top]:
        print(f"{sym}\t{n}\t{fmt_pf(pf)}\t{net:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_folder")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    folder = args.run_folder
    folder = os.path.expanduser(folder)
    if "path/to" in folder:
        print("You passed a placeholder folder. Replace path/to/run_folder with the real run folder path (e.g., backtest_runs/<run_id>/).")
        return
    if not os.path.isdir(folder):
        print("Folder not found:", folder)
        print("Tip: pass full path to your run folder that contains trades*.csv")
        return
    candidates = [
        ("inplay", os.path.join(folder, "trades_inplay.csv")),
        ("bounce", os.path.join(folder, "trades_bounce.csv")),
        ("portfolio", os.path.join(folder, "trades.csv")),
    ]

    found = False
    for name, path in candidates:
        if os.path.exists(path):
            found = True
            rows = analyze_csv(path, strategy_hint=name)
            print_top(f"[{name}] Top {args.top} PnL killers", rows, args.top)

    if not found:
        print("No trade CSVs found in folder:", folder)
        print("Expected one of: trades_inplay.csv, trades_bounce.csv, trades.csv")


if __name__ == "__main__":
    main()