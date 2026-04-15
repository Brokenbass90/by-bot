#!/usr/bin/env python3
"""Quick static walk-forward for ATT1 and ASM1.

22 rolling 45-day windows ending at 15-day steps from 2025-10-01 to 2026-04-01.
Runs all windows in parallel (cached data only).
Prints per-window PF and aggregate verdict.

Usage:
    python3 scripts/run_sloped_wf_quick.py --strategy att1
    python3 scripts/run_sloped_wf_quick.py --strategy asm1
    python3 scripts/run_sloped_wf_quick.py --strategy both
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
RUNS_DIR = ROOT / "backtest_runs"

SYMBOLS_ATT1 = "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT"
SYMBOLS_ASM1 = "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT,XRPUSDT"

STRATEGY_MAP = {
    "att1": ("alt_trendline_touch_v1", SYMBOLS_ATT1),
    "asm1": ("alt_sloped_momentum_v1", SYMBOLS_ASM1),
}

# Best params from sweep
ATT1_PARAMS = {
    "ATT1_PIVOT_LEFT": "2", "ATT1_PIVOT_RIGHT": "2", "ATT1_MIN_PIVOTS": "2",
    "ATT1_MAX_PIVOT_AGE": "12", "ATT1_MIN_R2": "0.80", "ATT1_TOUCH_ATR": "0.25",
    "ATT1_RSI_LONG_MAX": "52", "ATT1_RSI_SHORT_MIN": "40",
}
ASM1_PARAMS = {
    "ASM1_MIN_R2": "0.25", "ASM1_BREAKOUT_EXT_ATR": "0.15", "ASM1_MIN_BODY_FRAC": "0.35",
    "ASM1_VOL_MULT": "2.0", "ASM1_MIN_SLOPE_PCT": "0.10", "ASM1_USE_TREND_FILTER": "0",
}

PARAMS_MAP = {"att1": ATT1_PARAMS, "asm1": ASM1_PARAMS}


def _build_windows(end: dt.date, total: int, window: int, step: int) -> List[dt.date]:
    """Build list of window-end dates, stepping backwards by `step` days.

    Each window covers (end - window, end].
    We stop when the window START would go before (end - total_days).
    """
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
    strategy_key, end_date_str, window_days, tag_prefix = args
    strat_name, symbols = STRATEGY_MAP[strategy_key]
    params = PARAMS_MAP[strategy_key]

    tag = f"{tag_prefix}_{end_date_str.replace('-', '')}"
    env = os.environ.copy()
    env.update(params)
    env["BACKTEST_CACHE_ONLY"] = "1"  # force cache-only (matches run_portfolio.py env var)
    env["CACHE_ONLY"] = "1"           # legacy compat

    cmd = [
        PYTHON, "backtest/run_portfolio.py",
        "--symbols", symbols,
        "--strategies", strat_name,
        "--days", str(window_days),
        "--end", end_date_str,
        "--tag", tag,
        "--risk_pct", "0.01",
        "--leverage", "1",
        "--fee_bps", "6",
        "--slippage_bps", "2",
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        return {"end": end_date_str, "pf": None, "trades": 0, "net": None, "status": "TIMEOUT"}

    # Find the run dir
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
    return {"end": end_date_str, "pf": None, "trades": 0, "net": None, "status": f"NO_SUMMARY:{r.stdout[-200:]}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=["att1", "asm1", "both"], default="both")
    ap.add_argument("--end", default="2026-04-01")
    ap.add_argument("--total_days", type=int, default=360)
    ap.add_argument("--window_days", type=int, default=45)
    ap.add_argument("--step_days", type=int, default=15)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    end_date = dt.datetime.strptime(args.end, "%Y-%m-%d").date()
    windows = _build_windows(end_date, args.total_days, args.window_days, args.step_days)
    print(f"Running {len(windows)} windows × {'2 strategies' if args.strategy == 'both' else '1 strategy'}")

    strategies = ["att1", "asm1"] if args.strategy == "both" else [args.strategy]

    tasks = []
    for strat in strategies:
        for end in windows:
            tasks.append((strat, end.strftime("%Y-%m-%d"), args.window_days, f"sloped_wf_{strat}"))

    results: Dict[str, List[Dict]] = {s: [] for s in strategies}

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(_run_window, task): task for task in tasks}
        done = 0
        for fut in as_completed(futs):
            task = futs[fut]
            strat_key = task[0]
            r = fut.result()
            results[strat_key].append(r)
            done += 1
            pf_str = f"PF={r['pf']:.3f}" if r["pf"] else r["status"]
            print(f"  [{done}/{len(tasks)}] {strat_key.upper()} {r['end']}: {pf_str} trades={r['trades']}")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"Walk-Forward Results ({len(windows)} windows, {args.window_days}-day each)")
    print(f"{'='*60}")

    for strat in strategies:
        rows = sorted(results[strat], key=lambda x: x["end"])
        valid = [r for r in rows if r["pf"] is not None and r["trades"] >= 5]
        pass_pf = [r for r in valid if r["pf"] >= 1.0]
        pass_pf_115 = [r for r in valid if r["pf"] >= 1.15]

        if not valid:
            print(f"\n{strat.upper()}: No valid windows")
            continue

        avg_pf = sum(r["pf"] for r in valid) / len(valid)
        avg_trades = sum(r["trades"] for r in valid) / len(valid)
        total_net = sum(r["net"] for r in valid if r["net"])
        win_rate_wf = len(pass_pf) / len(valid)
        win_rate_pf115 = len(pass_pf_115) / len(valid)

        print(f"\n{strat.upper()} ({STRATEGY_MAP[strat][0]})")
        print(f"  Windows: {len(valid)}/{len(rows)} valid  |  avg PF: {avg_pf:.3f}  |  avg trades/window: {avg_trades:.1f}")
        print(f"  Windows PF>1.00: {len(pass_pf)}/{len(valid)} ({win_rate_wf*100:.0f}%)")
        print(f"  Windows PF>1.15: {len(pass_pf_115)}/{len(valid)} ({win_rate_pf115*100:.0f}%)")
        print(f"  Sum net PnL across windows: {total_net:.2f}%")
        print()
        print(f"  {'End':12s} {'PF':6s} {'Trades':7s} {'Net%':7s} {'Status'}")
        print(f"  {'-'*12} {'-'*6} {'-'*7} {'-'*7} {'-'*8}")
        for r in rows:
            pf_str = f"{r['pf']:.3f}" if r["pf"] else "N/A  "
            net_str = f"{r['net']:+.2f}" if r["net"] is not None else "N/A"
            flag = "✅" if r["pf"] and r["pf"] >= 1.15 else ("⚠️ " if r["pf"] and r["pf"] >= 1.0 else "❌")
            print(f"  {r['end']:12s} {pf_str:6s} {r['trades']:7d} {net_str:7s} {flag}")

        # Verdict
        if avg_pf >= 1.15 and win_rate_wf >= 0.65:
            verdict = "🟢🟢 STRONG — deploy at full risk"
        elif avg_pf >= 1.05 and win_rate_wf >= 0.55:
            verdict = "🟢 VIABLE — deploy at 0.5-0.8x risk"
        else:
            verdict = "🔴 WEAK — do not deploy"

        print(f"\n  VERDICT: {verdict}")
        print(f"  Elapsed: {elapsed:.0f}s")


if __name__ == "__main__":
    main()
