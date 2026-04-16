#!/usr/bin/env python3
"""Full-year portfolio backtest + monthly/per-strategy analysis.

Runs the current live portfolio (ATT1 + Elder v2 + ASB1 + HZBO1 + IVB1)
for Apr 2025 → Mar 2026 (all 4 symbols fully cached) and produces:

  - Month-by-month P&L table with equity curve
  - Per-strategy monthly breakdown
  - Red month deep-dive (which strategies caused losses)
  - WinRate and PF by month
  - Recommendations for weak strategies

Usage:
    cd /path/to/bybit-bot-clean-v28
    python3 scripts/run_annual_analysis.py [--skip-backtest] [--tag my_tag]

Options:
    --skip-backtest   Use existing trades.csv (pass with --trades-csv path)
    --trades-csv PATH Path to trades CSV (with --skip-backtest)
    --tag TAG         Run tag prefix (default: annual_live_portfolio)
    --days N          Number of days (default: 365)
    --end YYYY-MM-DD  End date (default: 2026-03-31)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# ─── Configuration ────────────────────────────────────────────────────────────

STRATEGIES = [
    "elder_triple_screen_v2",
    "alt_trendline_touch_v1",
    "alt_slope_break_v1",
    "alt_horizontal_break_v1",
    "impulse_volume_breakout_v1",
]
STRATEGY_LABELS = {
    "elder_triple_screen_v2": "Elder v2",
    "alt_trendline_touch_v1": "ATT1",
    "alt_slope_break_v1": "ASB1",
    "alt_horizontal_break_v1": "HZBO1",
    "impulse_volume_breakout_v1": "IVB1",
}
SYMBOLS = "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT"
STARTING_EQUITY = 1000.0

# Production risk multipliers (match live bot settings)
RISK_ENV = {
    # Elder v2: shorts-only, macro-filtered
    "ETS2_TREND_REQUIRE_HIST_SIGN": "1",
    "ETS2_ALLOW_LONGS": "0",
    "ETS2_ALLOW_SHORTS": "1",
    "ELDER_RISK_MULT": "0.60",           # backtest uses ELDER_RISK_MULT

    # ATT1: both sides, no macro filter (trendline touch)
    "ATT1_RISK_MULT": "0.70",

    # ASB1: both sides, bearish macro filter for shorts
    "ASB1_RISK_MULT": "0.50",
    # default macro_require_bearish=True already in code

    # HZBO1: shorts-only, macro filter
    "HZBO1_RISK_MULT": "0.40",
    # default macro_require_bearish=True already in code

    # IVB1: longs-only, bull macro filter (4h hist > 0 required)
    # default macro_require_bull=True already in code (from our recent fix)
}


# ─── Backtest runner ──────────────────────────────────────────────────────────

def run_backtest(tag: str, days: int, end_date: str) -> Optional[Path]:
    """Run run_portfolio.py and return path to trades.csv, or None on failure."""
    env = os.environ.copy()
    env.update(RISK_ENV)
    env["BACKTEST_CACHE_ONLY"] = "1"
    env["CACHE_ONLY"] = "1"
    env["MIN_NOTIONAL_FILL_FRAC"] = "0"

    cmd = [
        PYTHON, str(ROOT / "backtest" / "run_portfolio.py"),
        "--symbols", SYMBOLS,
        "--strategies", ",".join(STRATEGIES),
        "--days", str(days),
        "--end", end_date,
        "--starting_equity", str(STARTING_EQUITY),
        "--risk_pct", "0.01",
        "--leverage", "1",
        "--fee_bps", "6",
        "--slippage_bps", "2",
        "--max_positions", "8",          # allow up to 8 simultaneous positions
        "--tag", tag,
        "--cache", str(ROOT / ".cache" / "klines"),
    ]

    print(f"\n{'='*70}")
    print(f"RUNNING BACKTEST: {' '.join(cmd[-10:])}")
    print(f"Env overrides: {RISK_ENV}")
    print(f"{'='*70}\n")

    t0 = time.time()
    result = subprocess.run(
        cmd, cwd=str(ROOT), env=env,
        capture_output=False,    # show live output
        text=True,
    )
    elapsed = time.time() - t0
    print(f"\n[DONE] backtest finished in {elapsed:.0f}s (exit={result.returncode})")

    if result.returncode != 0:
        print("[ERROR] backtest failed")
        return None

    # Find the output directory
    runs = sorted((ROOT / "backtest_runs").glob(f"*{tag}*"), key=lambda p: p.stat().st_mtime)
    if not runs:
        print("[ERROR] no backtest_runs directory found")
        return None

    trades_csv = runs[-1] / "trades.csv"
    if not trades_csv.exists():
        print(f"[ERROR] trades.csv not found in {runs[-1]}")
        return None

    print(f"\nOutput: {trades_csv}")
    return trades_csv


# ─── Analysis ─────────────────────────────────────────────────────────────────

def load_trades(trades_csv: Path) -> List[dict]:
    trades = []
    with open(trades_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric fields
            row["pnl"] = float(row.get("pnl", 0))
            row["pnl_pct_equity"] = float(row.get("pnl_pct_equity", 0))
            row["entry_ts"] = int(row.get("entry_ts", 0))
            row["exit_ts"] = int(row.get("exit_ts", 0))
            row["fees"] = float(row.get("fees", 0))
            trades.append(row)
    # Sort by exit time
    trades.sort(key=lambda r: r["exit_ts"])
    return trades


def month_key(ts_ms: int) -> str:
    """Convert timestamp ms → 'YYYY-MM'."""
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m")


def month_label(ym: str) -> str:
    """Convert 'YYYY-MM' → 'Jan 2025' etc."""
    dt = datetime.strptime(ym + "-01", "%Y-%m-%d")
    return dt.strftime("%b %Y")


def analyze(trades: List[dict]) -> dict:
    """Full portfolio analysis: monthly + per-strategy."""

    # ── Equity curve ──────────────────────────────────────────────────────────
    equity = STARTING_EQUITY
    equity_by_ts: List[Tuple[int, float]] = [(0, equity)]
    for t in trades:
        equity += t["pnl"]
        equity_by_ts.append((t["exit_ts"], equity))

    final_equity = equity
    total_return_pct = (final_equity - STARTING_EQUITY) / STARTING_EQUITY * 100

    # ── Monthly equity buckets ─────────────────────────────────────────────────
    # Track equity at start of each month
    months_seen = sorted({month_key(t["exit_ts"]) for t in trades})
    month_start_equity: Dict[str, float] = {}
    month_end_equity: Dict[str, float] = {}

    # Walk through trades in order to build equity curve
    equity = STARTING_EQUITY
    prev_month = None
    month_running: Dict[str, float] = defaultdict(float)
    month_trades: Dict[str, List[dict]] = defaultdict(list)
    month_wins: Dict[str, int] = defaultdict(int)
    month_total: Dict[str, int] = defaultdict(int)
    month_fees: Dict[str, float] = defaultdict(float)

    for t in trades:
        mk = month_key(t["exit_ts"])
        if mk not in month_start_equity:
            month_start_equity[mk] = equity
        month_running[mk] += t["pnl"]
        month_trades[mk].append(t)
        if t["pnl"] > 0:
            month_wins[mk] += 1
        month_total[mk] += 1
        month_fees[mk] += t["fees"]
        equity += t["pnl"]
        month_end_equity[mk] = equity

    # ── Per-strategy monthly breakdown ─────────────────────────────────────────
    strat_monthly: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    strat_monthly_trades: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for t in trades:
        mk = month_key(t["exit_ts"])
        strat = t.get("strategy", "unknown")
        strat_monthly[strat][mk] += t["pnl"]
        strat_monthly_trades[strat][mk].append(t)

    # ── Per-strategy annual totals ─────────────────────────────────────────────
    strat_totals: Dict[str, dict] = {}
    for strat in STRATEGIES:
        strat_trades = [t for t in trades if t.get("strategy") == strat]
        total_pnl = sum(t["pnl"] for t in strat_trades)
        wins = sum(1 for t in strat_trades if t["pnl"] > 0)
        n = len(strat_trades)
        gross_win = sum(t["pnl"] for t in strat_trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in strat_trades if t["pnl"] < 0))
        pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
        strat_totals[strat] = {
            "trades": n,
            "pnl": total_pnl,
            "pnl_pct": total_pnl / STARTING_EQUITY * 100,
            "winrate": wins / n if n > 0 else 0,
            "pf": pf,
            "fees": sum(t["fees"] for t in strat_trades),
        }

    # ── Max drawdown from equity curve ─────────────────────────────────────────
    equity = STARTING_EQUITY
    peak = STARTING_EQUITY
    max_dd = 0.0
    for t in trades:
        equity += t["pnl"]
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd

    return {
        "starting_equity": STARTING_EQUITY,
        "final_equity": final_equity,
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_dd,
        "months": months_seen,
        "month_start_equity": month_start_equity,
        "month_end_equity": month_end_equity,
        "month_running": month_running,
        "month_trades": month_trades,
        "month_wins": month_wins,
        "month_total": month_total,
        "month_fees": month_fees,
        "strat_monthly": strat_monthly,
        "strat_monthly_trades": strat_monthly_trades,
        "strat_totals": strat_totals,
        "total_trades": len(trades),
        "total_wins": sum(1 for t in trades if t["pnl"] > 0),
        "total_fees": sum(t["fees"] for t in trades),
    }


# ─── Report rendering ─────────────────────────────────────────────────────────

def render_report(a: dict) -> str:
    lines = []
    W = 80

    def hdr(s: str):
        lines.append("")
        lines.append("=" * W)
        lines.append(f"  {s}")
        lines.append("=" * W)

    def sub(s: str):
        lines.append("")
        lines.append(f"── {s} " + "─" * max(0, W - 4 - len(s)))

    # ── Header ────────────────────────────────────────────────────────────────
    hdr("FULL-YEAR PORTFOLIO BACKTEST — LIVE PORTFOLIO (Apr 2025 → Mar 2026)")
    lines.append(f"  Strategies : {', '.join(STRATEGY_LABELS.values())}")
    lines.append(f"  Symbols    : {SYMBOLS}")
    lines.append(f"  Risk       : 1% per trade | Leverage: 1× | Fees: 6+2 bps")
    lines.append(f"  Multipliers: Elder 0.60× | ATT1 0.70× | ASB1 0.50× | HZBO1 0.40× | IVB1 1.00×")
    lines.append(f"  Macro ftrs : Elder shorts-only, ASB1/HZBO1 bearish, IVB1 bullish")

    # ── Summary ────────────────────────────────────────────────────────────────
    sub("ANNUAL SUMMARY")
    s_eq = a["starting_equity"]
    f_eq = a["final_equity"]
    total_ret = a["total_return_pct"]
    max_dd = a["max_drawdown_pct"]
    wr = a["total_wins"] / a["total_trades"] * 100 if a["total_trades"] else 0
    months = a["months"]
    red_months = [m for m in months if a["month_running"][m] < 0]

    lines.append(f"  Starting equity  : ${s_eq:,.0f}")
    lines.append(f"  Final equity     : ${f_eq:,.2f}")
    lines.append(f"  Total return     : {total_ret:+.2f}%  (${f_eq - s_eq:+.2f})")
    lines.append(f"  Max drawdown     : {max_dd:.2f}%")
    lines.append(f"  Total trades     : {a['total_trades']} (WR {wr:.1f}%)")
    lines.append(f"  Total fees paid  : ${a['total_fees']:.2f}")
    lines.append(f"  Months tested    : {len(months)}")
    lines.append(f"  Red months       : {len(red_months)} ({', '.join(month_label(m) for m in red_months) or 'NONE'})")

    # Extrapolation
    if len(months) > 0:
        monthly_avg = total_ret / len(months)
        annual_proj = monthly_avg * 12
        lines.append("")
        lines.append(f"  Monthly avg      : {monthly_avg:+.2f}%")
        lines.append(f"  Annualized (12m) : {annual_proj:+.2f}%  (at 1× leverage)")
        lines.append(f"  At 2× leverage   : {annual_proj*2:+.2f}%")
        lines.append(f"  At 3× leverage   : {annual_proj*3:+.2f}%")

    # ── Monthly breakdown ──────────────────────────────────────────────────────
    sub("MONTH-BY-MONTH BREAKDOWN")
    header = f"{'Month':<12} {'P&L':>8} {'%':>7} {'Trades':>7} {'WR':>7} {'PF':>6} {'Equity':>10} {'Signal'}"
    lines.append(header)
    lines.append("-" * W)

    equity = a["starting_equity"]
    for m in months:
        pnl = a["month_running"][m]
        n = a["month_total"][m]
        wins = a["month_wins"][m]
        wr_m = wins / n * 100 if n > 0 else 0
        eq_end = a["month_end_equity"][m]
        eq_start = a["month_start_equity"][m]
        ret_m = (eq_end - eq_start) / eq_start * 100

        # PF for this month
        month_trd = a["month_trades"][m]
        gross_w = sum(t["pnl"] for t in month_trd if t["pnl"] > 0)
        gross_l = abs(sum(t["pnl"] for t in month_trd if t["pnl"] < 0))
        pf_m = gross_w / gross_l if gross_l > 0 else (99.9 if gross_w > 0 else 0)

        flag = "🔴" if pnl < 0 else ("🟡" if pnl < 2 else "🟢")
        lines.append(
            f"{month_label(m):<12} {pnl:>+8.2f} {ret_m:>+6.2f}% {n:>7} {wr_m:>6.1f}% "
            f"{pf_m:>6.2f} ${eq_end:>9.2f}  {flag}"
        )

    # ── Per-strategy breakdown ─────────────────────────────────────────────────
    sub("PER-STRATEGY ANNUAL TOTALS")
    header2 = f"{'Strategy':<14} {'Trades':>7} {'P&L':>9} {'%/yr':>7} {'WR':>7} {'PF':>6} {'Fees':>7}"
    lines.append(header2)
    lines.append("-" * W)

    for strat in STRATEGIES:
        st = a["strat_totals"].get(strat, {})
        if not st:
            continue
        label = STRATEGY_LABELS.get(strat, strat)
        n = st["trades"]
        pnl = st["pnl"]
        pct = st["pnl_pct"]
        wr = st["winrate"] * 100
        pf = st["pf"]
        fees = st["fees"]
        flag = "✅" if pnl > 0 else "❌"
        lines.append(
            f"{label:<14} {n:>7} {pnl:>+9.2f} {pct:>+6.2f}% {wr:>6.1f}% "
            f"{pf:>6.2f} ${fees:>6.2f}  {flag}"
        )

    # ── Per-strategy monthly matrix ────────────────────────────────────────────
    sub("STRATEGY × MONTH MATRIX (P&L %)")
    month_abbr = [month_label(m)[:6] for m in months]
    hdr_row = f"{'':14}" + "".join(f"{ma:>8}" for ma in month_abbr)
    lines.append(hdr_row)
    lines.append("-" * min(W + 20, 120))

    for strat in STRATEGIES:
        label = STRATEGY_LABELS.get(strat, strat)
        row = f"{label:<14}"
        for m in months:
            pnl_m = a["strat_monthly"][strat].get(m, 0)
            pct_m = pnl_m / STARTING_EQUITY * 100
            cell = f"{pct_m:>+7.2f}%"
            row += cell
        lines.append(row)

    # ── Red month analysis ─────────────────────────────────────────────────────
    if red_months:
        sub("RED MONTH DEEP-DIVE")
        for m in red_months:
            month_trd = a["month_trades"][m]
            pnl_total = sum(t["pnl"] for t in month_trd)
            lines.append(f"\n  {month_label(m)} — total P&L: ${pnl_total:+.2f}")

            # Per-strategy breakdown for this month
            by_strat: Dict[str, List] = defaultdict(list)
            for t in month_trd:
                by_strat[t.get("strategy", "?")].append(t)
            for strat in STRATEGIES:
                if strat not in by_strat:
                    continue
                ts = by_strat[strat]
                sp = sum(t["pnl"] for t in ts)
                sw = sum(1 for t in ts if t["pnl"] > 0)
                label = STRATEGY_LABELS.get(strat, strat)
                flag = "💸" if sp < 0 else "✅"
                lines.append(
                    f"    {label:<14} {len(ts):>3} trades  "
                    f"P&L: ${sp:>+8.2f}  WR: {sw/len(ts)*100:>4.1f}%  {flag}"
                )

    # ── Weak strategy analysis ─────────────────────────────────────────────────
    sub("STRATEGY HEALTH ASSESSMENT")
    for strat in STRATEGIES:
        st = a["strat_totals"].get(strat, {})
        if not st:
            continue
        label = STRATEGY_LABELS.get(strat, strat)
        pnl = st["pnl"]
        n = st["trades"]
        wr = st["winrate"]
        pf = st["pf"]

        # Count profitable months
        strat_months = a["strat_monthly"][strat]
        prof_months = sum(1 for m in months if strat_months.get(m, 0) > 0)
        loss_months = sum(1 for m in months if strat_months.get(m, 0) < 0)

        status = "STRONG" if (pf >= 1.2 and wr >= 0.48 and pnl > 0) else \
                 "OK" if (pf >= 1.05 and pnl > 0) else \
                 "WEAK" if pf < 1.0 else "MARGINAL"

        lines.append(f"\n  {label} [{status}]")
        lines.append(f"    Trades: {n} | WR: {wr*100:.1f}% | PF: {pf:.3f} | Annual P&L: ${pnl:+.2f}")
        lines.append(f"    Green months: {prof_months}/{len(months)} | Red months: {loss_months}/{len(months)}")

        if pf < 1.0:
            lines.append(f"    ⚠️  PROFIT FACTOR < 1.0 — NET LOSER — requires investigation")
        elif pf < 1.1:
            lines.append(f"    ⚠️  Low profit factor — marginal profitability")
        if wr < 0.40:
            lines.append(f"    ⚠️  Win rate below 40% — check TP/SL ratio")
        if n < 20:
            lines.append(f"    ⚠️  Very few trades ({n}) — low statistical significance")

    # ── Scaling projection ─────────────────────────────────────────────────────
    sub("SCALING PROJECTIONS")
    ret = a["total_return_pct"]
    months_count = len(months)
    ann = ret * 12 / months_count if months_count else ret
    lines.append(f"  Base (1% risk, 1× leverage): {ann:+.1f}%/year")
    lines.append(f"  At 1× leverage, 2% risk    : {ann*2:+.1f}%/year")
    lines.append(f"  At 2× leverage, 1% risk    : {ann*2:+.1f}%/year")
    lines.append(f"  At 3× leverage, 1% risk    : {ann*3:+.1f}%/year  (current live target)")
    lines.append(f"  At 2× leverage, 2% risk    : {ann*4:+.1f}%/year")
    lines.append("")
    lines.append(f"  Note: These are linear extrapolations. Compounding, drawdown,")
    lines.append(f"  and regime changes will affect actual live returns.")

    return "\n".join(lines)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-backtest", action="store_true",
                    help="Skip running backtest, use existing trades.csv")
    ap.add_argument("--trades-csv", default="",
                    help="Path to existing trades.csv (with --skip-backtest)")
    ap.add_argument("--tag", default="annual_live_portfolio",
                    help="Run tag prefix")
    ap.add_argument("--days", type=int, default=365,
                    help="Number of days to backtest")
    ap.add_argument("--end", default="2026-03-31",
                    help="End date YYYY-MM-DD (latest data in cache: 2026-03-31)")
    args = ap.parse_args()

    os.chdir(str(ROOT))

    # ── Run backtest ──────────────────────────────────────────────────────────
    if args.skip_backtest:
        if not args.trades_csv:
            print("[ERROR] --skip-backtest requires --trades-csv")
            sys.exit(1)
        trades_csv = Path(args.trades_csv)
    else:
        print(f"Starting full-year backtest...")
        print(f"  Period: {args.days} days ending {args.end}")
        print(f"  Strategies: {', '.join(STRATEGIES)}")
        print(f"  Symbols: {SYMBOLS}")
        print(f"  This may take 10-30 minutes...")

        ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = f"{args.tag}_{ts_tag}"

        trades_csv = run_backtest(tag, args.days, args.end)
        if trades_csv is None:
            print("[FATAL] Backtest failed. Aborting analysis.")
            sys.exit(1)

    # ── Load and analyze ──────────────────────────────────────────────────────
    print(f"\nLoading trades from: {trades_csv}")
    trades = load_trades(trades_csv)
    print(f"Loaded {len(trades)} trades")

    if not trades:
        print("[ERROR] No trades found in trades.csv")
        sys.exit(1)

    print("Running analysis...")
    analysis = analyze(trades)

    # ── Render report ─────────────────────────────────────────────────────────
    report = render_report(analysis)
    print("\n" + report)

    # Save to file
    out_path = trades_csv.parent / "annual_analysis_report.txt"
    out_path.write_text(report)
    print(f"\n[SAVED] Report → {out_path}")

    # Save JSON for further processing
    json_data = {
        "starting_equity": analysis["starting_equity"],
        "final_equity": analysis["final_equity"],
        "total_return_pct": analysis["total_return_pct"],
        "max_drawdown_pct": analysis["max_drawdown_pct"],
        "total_trades": analysis["total_trades"],
        "months": analysis["months"],
        "monthly_pnl": {m: analysis["month_running"][m] for m in analysis["months"]},
        "monthly_pct": {
            m: (analysis["month_end_equity"][m] - analysis["month_start_equity"][m])
               / analysis["month_start_equity"][m] * 100
            for m in analysis["months"]
        },
        "strat_totals": {
            strat: {
                **analysis["strat_totals"][strat],
                "monthly_pnl": dict(analysis["strat_monthly"][strat]),
            }
            for strat in STRATEGIES if strat in analysis["strat_totals"]
        },
    }
    json_out = trades_csv.parent / "annual_analysis_data.json"
    json_out.write_text(json.dumps(json_data, indent=2))
    print(f"[SAVED] Data  → {json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
