#!/usr/bin/env python3
"""Generic walk-forward runner for any strategy registered in run_portfolio.py.

22 rolling 45-day windows, parallel execution.

Usage:
    python3 scripts/run_generic_wf.py \
        --strategy alt_horizontal_break_v1 \
        --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
        --tag hzbo1_shorts_no_macro \
        [--extra_env KEY=VALUE KEY2=VALUE2 ...]

Extra env vars are passed to each subprocess (on top of current os.environ).

Examples:
    # No macro filter (baseline)
    python3 scripts/run_generic_wf.py \
        --strategy alt_horizontal_break_v1 \
        --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
        --tag hzbo1_no_macro \
        --extra_env HZBO1_MACRO_REQUIRE_BEARISH=0

    # With macro filter
    python3 scripts/run_generic_wf.py \
        --strategy alt_horizontal_break_v1 \
        --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
        --tag hzbo1_macro \
        --extra_env HZBO1_MACRO_REQUIRE_BEARISH=1
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple, Optional

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def _build_windows(end: dt.date, total: int, window: int, step: int) -> List[dt.date]:
    earliest_start = end - dt.timedelta(days=total)
    ends = []
    d = end
    while True:
        win_start = d - dt.timedelta(days=window)
        if win_start < earliest_start:
            break
        ends.append(d)
        d -= dt.timedelta(days=step)
    return list(reversed(ends))


def _run_window(args: Tuple) -> Optional[Dict]:
    strategy_name, symbols, end_date_str, window_days, tag_prefix, extra_env = args

    tag = f"{tag_prefix}_{end_date_str.replace('-', '')}"
    env = os.environ.copy()
    env.update(extra_env)
    env["BACKTEST_CACHE_ONLY"] = "1"
    env["CACHE_ONLY"] = "1"
    env["MIN_NOTIONAL_FILL_FRAC"] = "0"  # critical for tight-SL strategies

    cmd = [
        PYTHON, "backtest/run_portfolio.py",
        "--symbols", symbols,
        "--strategies", strategy_name,
        "--days", str(window_days),
        "--end", end_date_str,
        "--tag", tag,
        "--risk_pct", "0.01",
        "--leverage", "1",
        "--fee_bps", "6",
        "--slippage_bps", "2",
    ]

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, env=env, cwd=str(ROOT)
        )
    except subprocess.TimeoutExpired:
        return {"end": end_date_str, "pf": None, "trades": 0, "net": None, "status": "TIMEOUT"}

    for line in r.stdout.splitlines():
        if "summary:" in line:
            summary_path = line.split("summary:")[-1].strip()
            try:
                with open(summary_path) as f:
                    rows = list(csv.DictReader(f))
                if rows:
                    row = rows[0]
                    pf = float(row.get("profit_factor") or 0)
                    trades = int(row.get("trades") or 0)
                    net = float(row.get("net_pnl") or 0)
                    return {"end": end_date_str, "pf": pf, "trades": trades, "net": net, "status": "OK"}
            except Exception as e:
                return {"end": end_date_str, "pf": None, "trades": 0, "net": None, "status": f"ERR:{e}"}

    return {"end": end_date_str, "pf": None, "trades": 0, "net": None, "status": f"NO_SUMMARY:{r.stdout[-300:]}"}


def print_wf_summary(strategy: str, rows: List[Dict], window_days: int) -> None:
    rows_sorted = sorted(rows, key=lambda x: x["end"])

    pfs = [r["pf"] for r in rows_sorted if r["pf"] is not None]
    trades_list = [r["trades"] for r in rows_sorted]

    print(f"\n{'='*65}")
    print(f"Walk-Forward Results: {strategy}")
    print(f"{'='*65}")
    print(f"{'Window End':<14} {'PF':>7} {'Trades':>8} {'Net%':>8} Status")
    print("-" * 65)
    for r in rows_sorted:
        pf_str = f"{r['pf']:.3f}" if r["pf"] is not None else "  N/A"
        net_str = f"{r['net']:.2f}%" if r["net"] is not None else "   N/A"
        print(f"{r['end']:<14} {pf_str:>7} {r['trades']:>8} {net_str:>8} {r.get('status','')}")

    print("-" * 65)
    n = len(rows_sorted)
    if pfs:
        avg_pf = sum(pfs) / len(pfs)
        n_above_1 = sum(1 for p in pfs if p > 1.0)
        n_above_115 = sum(1 for p in pfs if p > 1.15)
        avg_trades = sum(trades_list) / n
        print(f"\nSUMMARY ({n} windows, {window_days}-day each):")
        print(f"  AvgPF:    {avg_pf:.3f}")
        print(f"  PF>1.00:  {n_above_1}/{n} ({100*n_above_1//n}%)")
        print(f"  PF>1.15:  {n_above_115}/{n} ({100*n_above_115//n}%)")
        print(f"  AvgTrades:{avg_trades:.0f}/window")
        print()
        if avg_pf >= 1.15 and n_above_1 >= n * 0.65:
            verdict = "🟢 STRONG — deploy at full canary risk"
        elif avg_pf >= 1.05 and n_above_1 >= n * 0.55:
            verdict = "🟢 VIABLE — deploy at reduced canary risk (0.50×)"
        elif avg_pf >= 1.00 and n_above_1 >= n * 0.50:
            verdict = "🟡 MARGINAL — more WF validation needed"
        else:
            verdict = "🔴 WEAK — do not deploy"
        print(f"  VERDICT:  {verdict}")
    else:
        print("\n  No valid windows — check strategy/data setup")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, help="Strategy name (e.g. alt_horizontal_break_v1)")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--end", default="2026-04-01")
    ap.add_argument("--total_days", type=int, default=360)
    ap.add_argument("--window_days", type=int, default=45)
    ap.add_argument("--step_days", type=int, default=15)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument(
        "--extra_env",
        nargs="*",
        default=[],
        help="Extra env vars as KEY=VALUE pairs",
    )
    args = ap.parse_args()

    extra_env: Dict[str, str] = {}
    for kv in (args.extra_env or []):
        if "=" in kv:
            k, v = kv.split("=", 1)
            extra_env[k.strip()] = v.strip()

    end_date = dt.datetime.strptime(args.end, "%Y-%m-%d").date()
    windows = _build_windows(end_date, args.total_days, args.window_days, args.step_days)
    print(f"Strategy: {args.strategy}")
    print(f"Symbols:  {args.symbols}")
    print(f"Running {len(windows)} windows × {args.window_days}-day")
    if extra_env:
        print(f"Extra env: {extra_env}")

    tasks = [
        (args.strategy, args.symbols, w.strftime("%Y-%m-%d"), args.window_days, args.tag, extra_env)
        for w in windows
    ]

    results: List[Dict] = []
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(_run_window, task): task for task in tasks}
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            pf_str = f"PF={r['pf']:.3f}" if r["pf"] is not None else r["status"]
            print(f"  [{done:>2}/{len(tasks)}] {r['end']}: {pf_str} T={r['trades']}")

    elapsed = time.time() - t0
    print_wf_summary(args.strategy, results, args.window_days)
    print(f"\nCompleted in {elapsed:.0f}s")


if __name__ == "__main__":
    main()
