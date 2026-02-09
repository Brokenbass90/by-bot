#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Print a leaderboard across backtest_runs/*/summary.csv

Usage:
  python3 scripts/leaderboard.py backtest_runs --limit 30

Shows ALL row per run, with tag, netPnL, PF, trades, winrate, n_symbols.
"""
from __future__ import annotations
import os, sys, csv, json, glob, argparse
from typing import Dict, Any, List

def read_json(p: str) -> Dict[str, Any]:
    try:
        return json.load(open(p, "r", encoding="utf-8"))
    except Exception:
        return {}

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="backtest_runs")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--sort", choices=["net", "pf", "wr", "tr"], default="net")
    args = ap.parse_args()

    runs = [p for p in glob.glob(os.path.join(args.root, "*")) if os.path.isdir(p)]
    out: List[Dict[str, Any]] = []
    for run in runs:
        summ = os.path.join(run, "summary.csv")
        params = os.path.join(run, "params.json")
        if not os.path.exists(summ):
            continue
        rows = list(csv.DictReader(open(summ, "r", encoding="utf-8")))
        all_row = next((r for r in rows if r.get("symbol") == "ALL"), None)
        if not all_row:
            continue
        meta = read_json(params)
        tag = ((meta.get("args") or {}).get("tag")) or os.path.basename(run)
        n_symbols = sum(
            1 for r in rows
            if r.get("symbol") not in ("ALL",) and not str(r.get("symbol","")).startswith("PORTFOLIO")
        )
        try:
            net = float(all_row.get("net_pnl", "0") or 0.0)
        except Exception:
            net = 0.0
        pf_raw = str(all_row.get("profit_factor","") or "")
        try:
            pf = float("inf") if pf_raw.lower()=="inf" else float(pf_raw)
        except Exception:
            pf = 0.0
        try:
            tr = int(float(all_row.get("trades","0") or 0))
        except Exception:
            tr = 0
        try:
            wr = float(all_row.get("winrate_pct","0") or 0.0)
        except Exception:
            wr = 0.0

        out.append({
            "run": os.path.basename(run),
            "tag": tag,
            "net": net,
            "pf": pf,
            "tr": tr,
            "wr": wr,
            "n": n_symbols,
        })

    key = {"net":"net", "pf":"pf", "wr":"wr", "tr":"tr"}[args.sort]
    out.sort(key=lambda r: r[key], reverse=True)

    print(f"{'run':28s} {'tag':22s} {'net':>8s} {'PF':>6s} {'tr':>5s} {'wr%':>6s} {'n':>3s}")
    for r in out[:args.limit]:
        pf = r["pf"]
        pf_s = "inf" if pf==float("inf") else f"{pf:.2f}"
        print(f"{r['run'][:28]:28s} {r['tag'][:22]:22s} {r['net']:8.2f} {pf_s:>6s} {r['tr']:5d} {r['wr']:6.1f} {r['n']:3d}")

if __name__ == "__main__":
    main()
