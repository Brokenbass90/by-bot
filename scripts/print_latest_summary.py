#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print aggregate backtest results for the latest run (no pandas required).

Usage:
  python3 scripts/print_latest_summary.py backtest_runs
"""

import csv
import glob
import os
import sys

def _latest_run_dir(base: str) -> str:
    runs = sorted(glob.glob(os.path.join(base, "*")), key=os.path.getmtime)
    if not runs:
        raise SystemExit(f"No runs found in: {base}")
    return runs[-1]

def _pick(d: dict, *keys: str) -> str:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return ""

def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "backtest_runs"
    run_dir = _latest_run_dir(base)
    path = os.path.join(run_dir, "summary.csv")
    print("LATEST RUN:", run_dir)
    print("SUMMARY:", path)

    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("symbol") == "ALL":
                rows.append(r)

    # sort by pnl
    def fnum(x: str) -> float:
        try:
            return float(x)
        except Exception:
            return float("-inf")

    rows.sort(key=lambda r: fnum(_pick(r, "total_pnl", "net_pnl", "netPnL")), reverse=True)

    for r in rows:
        strategy = r.get("strategy", "")
        pnl = _pick(r, "total_pnl", "net_pnl", "netPnL")
        pf = _pick(r, "pf", "profit_factor", "PF")
        wr = _pick(r, "winrate", "winrate_pct", "winratePct")
        dd = _pick(r, "max_dd", "max_drawdown_pct", "maxDD")
        print(f"{strategy:10s}  PnL={pnl}  PF={pf}  WR={wr}  MaxDD={dd}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
