#!/usr/bin/env python3
"""Sequential timeout-safe crypto candidate matrix runner.

Runs one strategy/symbol portfolio backtest per subprocess and writes a compact
CSV. It is intentionally boring: no multiprocessing, no live state, no env
mutation. Use it when larger portfolio research hangs before producing
summary.csv.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _csv_items(raw: str) -> list[str]:
    return [x.strip() for x in str(raw or "").replace(";", ",").split(",") if x.strip()]


def _latest_run_dir(tag: str) -> Path | None:
    matches = sorted(
        (ROOT / "backtest_runs").glob(f"portfolio_*_{tag}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def _summary_row(run_dir: Path) -> dict[str, str]:
    path = run_dir / "summary.csv"
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return rows[0] if rows else {}


def _negative_months(run_dir: Path) -> int:
    path = run_dir / "trades.csv"
    if not path.exists():
        return 0
    months: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts = str(row.get("exit_ts") or row.get("entry_ts") or "")
            month = ""
            try:
                raw_ts = float(ts)
                if raw_ts > 10_000_000_000:
                    raw_ts /= 1000.0
                month = datetime.fromtimestamp(raw_ts, tz=timezone.utc).strftime("%Y-%m")
            except Exception:
                month = ts[:7]
            if not month:
                continue
            try:
                pnl = float(row.get("pnl") or 0.0)
            except Exception:
                pnl = 0.0
            months[month] = months.get(month, 0.0) + pnl
    return sum(1 for v in months.values() if v < 0)


def run_one(args: argparse.Namespace, strategy: str, symbol: str) -> dict[str, str]:
    tag = f"{args.tag}_{strategy}_{symbol}_{args.days}d"
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if args.cache_only:
        env["BACKTEST_CACHE_ONLY"] = "1"
        env["CACHE_ONLY"] = "1"
    env["MIN_NOTIONAL_FILL_FRAC"] = str(args.min_notional_fill_frac)

    cmd = [
        PYTHON,
        "backtest/run_portfolio.py",
        "--symbols",
        symbol,
        "--strategies",
        strategy,
        "--days",
        str(args.days),
        "--end",
        args.end,
        "--tag",
        tag,
        "--starting_equity",
        str(args.starting_equity),
        "--risk_pct",
        str(args.risk_pct),
        "--leverage",
        str(args.leverage),
        "--max_positions",
        str(args.max_positions),
        "--fee_bps",
        str(args.fee_bps),
        "--slippage_bps",
        str(args.slippage_bps),
    ]
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=float(args.timeout_sec),
        )
        status = "OK" if proc.returncode == 0 else f"EXIT{proc.returncode}"
        tail = (proc.stderr or proc.stdout or "")[-500:].replace("\n", " ")
    except subprocess.TimeoutExpired as exc:
        status = f"TIMEOUT>{args.timeout_sec}s"
        tail = ((exc.stderr or exc.stdout or "") if isinstance(exc.stderr or exc.stdout, str) else "")[-500:].replace("\n", " ")

    elapsed = time.time() - t0
    run_dir = _latest_run_dir(tag)
    summary = _summary_row(run_dir) if run_dir else {}
    return {
        "strategy": strategy,
        "symbol": symbol,
        "status": status,
        "elapsed_sec": f"{elapsed:.1f}",
        "trades": str(summary.get("trades", "")),
        "net_pnl": str(summary.get("net_pnl", "")),
        "profit_factor": str(summary.get("profit_factor", "")),
        "winrate": str(summary.get("winrate", "")),
        "max_drawdown": str(summary.get("max_drawdown", "")),
        "negative_months": str(_negative_months(run_dir) if run_dir else ""),
        "run_dir": str(run_dir.relative_to(ROOT)) if run_dir else "",
        "tail": tail,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategies", required=True)
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--end", default="2026-04-30")
    ap.add_argument("--tag", default="candidate_matrix_seq")
    ap.add_argument("--timeout-sec", type=int, default=480)
    ap.add_argument("--starting-equity", type=float, default=100.0)
    ap.add_argument("--risk-pct", type=float, default=0.0075)
    ap.add_argument("--leverage", type=float, default=1.0)
    ap.add_argument("--max-positions", type=int, default=1)
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--slippage-bps", type=float, default=2.0)
    ap.add_argument("--min-notional-fill-frac", default="0")
    ap.add_argument("--cache-only", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    strategies = _csv_items(args.strategies)
    symbols = _csv_items(args.symbols)
    out_path = Path(args.out) if args.out else ROOT / "reports" / "research" / f"{args.tag}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "strategy",
        "symbol",
        "status",
        "elapsed_sec",
        "trades",
        "net_pnl",
        "profit_factor",
        "winrate",
        "max_drawdown",
        "negative_months",
        "run_dir",
        "tail",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for strategy in strategies:
            for symbol in symbols:
                row = run_one(args, strategy, symbol)
                writer.writerow(row)
                fh.flush()
                print(
                    f"{strategy:34s} {symbol:12s} {row['status']:14s} "
                    f"trades={row['trades'] or '-':>4s} pf={row['profit_factor'] or '-':>6s} "
                    f"net={row['net_pnl'] or '-':>7s} dd={row['max_drawdown'] or '-':>6s}",
                    flush=True,
                )
    print(f"summary_csv={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
