#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append a one-line record for the latest backtest run to a CSV log.

Usage:
  python3 scripts/log_latest_run.py backtest_runs experiments.csv "optional note"

- Finds the most recently modified run dir inside backtest_runs/
- Reads params.json and summary.csv
- Writes/append a row into experiments.csv

This is intentionally "safe": it only logs env vars that were snapshotted by run_month.py
(only INPLAY_/RANGE_/BOUNCE_/MIN_NOTIONAL_/FEE_/SLIPPAGE_ prefixes).
"""
from __future__ import annotations
import os, sys, csv, json, glob
from datetime import datetime

def _latest_run_dir(root: str) -> str:
    runs = [p for p in glob.glob(os.path.join(root, "*")) if os.path.isdir(p)]
    if not runs:
        raise SystemExit(f"No run dirs found under: {root}")
    runs.sort(key=os.path.getmtime, reverse=True)
    return runs[0]

def main() -> None:
    root = sys.argv[1] if len(sys.argv) >= 2 else "backtest_runs"
    out_csv = sys.argv[2] if len(sys.argv) >= 3 else "experiments.csv"
    note = sys.argv[3] if len(sys.argv) >= 4 else ""

    run_dir = _latest_run_dir(root)
    params_path = os.path.join(run_dir, "params.json")
    summary_path = os.path.join(run_dir, "summary.csv")

    if not os.path.exists(params_path) or not os.path.exists(summary_path):
        raise SystemExit(f"Missing params.json or summary.csv in: {run_dir}")

    meta = json.load(open(params_path, "r", encoding="utf-8"))
    rows = list(csv.DictReader(open(summary_path, "r", encoding="utf-8")))
    all_row = next((r for r in rows if r.get("symbol") == "ALL"), None)
    if not all_row:
        raise SystemExit("summary.csv has no ALL row")

    # count symbols (exclude ALL and PORTFOLIO*)
    n_symbols = sum(
        1 for r in rows
        if r.get("symbol") not in ("ALL",) and not str(r.get("symbol","")).startswith("PORTFOLIO")
    )

    tag = ((meta.get("args") or {}).get("tag")) or os.path.basename(run_dir)
    start_utc = meta.get("start_utc", "")
    end_utc = meta.get("end_utc", "")
    strategies = meta.get("strategies", "")

    net = float(all_row.get("net_pnl", "0") or 0.0)
    pf_raw = str(all_row.get("profit_factor", "") or "")
    pf = pf_raw
    trades = int(float(all_row.get("trades", "0") or 0))
    winrate = float(all_row.get("winrate_pct", "0") or 0.0)
    maxdd = float(all_row.get("max_drawdown_pct", "0") or 0.0)

    env = meta.get("env") or {}
    # Compact env snapshot (only what usually matters)
    env_keep = {k: env.get(k) for k in sorted(env.keys()) if k.startswith(("INPLAY_", "MIN_NOTIONAL_", "FEE_", "SLIPPAGE_"))}

    row_out = {
        "ts_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_dir": os.path.basename(run_dir),
        "tag": tag,
        "strategies": strategies,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "n_symbols": n_symbols,
        "trades": trades,
        "winrate_pct": f"{winrate:.2f}",
        "profit_factor": pf,
        "net_pnl": f"{net:.4f}",
        "maxdd_pct": f"{maxdd:.4f}",
        "env": json.dumps(env_keep, ensure_ascii=False, sort_keys=True),
        "note": note,
    }

    header = list(row_out.keys())
    exists = os.path.exists(out_csv)

    with open(out_csv, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if not exists:
            w.writeheader()
        w.writerow(row_out)

    print(f"Logged: {os.path.basename(run_dir)} -> {out_csv}")

if __name__ == "__main__":
    main()
