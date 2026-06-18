#!/usr/bin/env python3
"""Run adaptive_v1 as the single Alpaca monthly paper order driver."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.alpaca_adaptive_shadow import run_shadow, write_bridge_picks_csv
from scripts.alpaca_v3_event_backtest import DEFAULT_UNIVERSE


def build_bridge_env(
    report: dict[str, Any],
    *,
    picks_csv: Path,
    capital: float,
    target_alloc_pct: float,
    send_orders: bool,
) -> dict[str, str]:
    env = os.environ.copy()
    exposure = max(0.0, min(1.0, float(report.get("exposure") or 0.0)))
    env.update(
        {
            "ALPACA_PICKS_CSV": str(picks_csv),
            "ALPACA_CURRENT_CYCLE_PICKS_CSV": str(picks_csv),
            "ALPACA_SEND_ORDERS": "1" if send_orders else "0",
            "ALPACA_CLOSE_STALE_POSITIONS": "1",
            "ALPACA_CAPITAL_OVERRIDE_USD": str(max(0.0, capital)),
            "ALPACA_TARGET_ALLOC_PCT": f"{max(0.0, min(1.0, target_alloc_pct / 100.0)) * exposure:.8f}",
            "ALPACA_MAX_POSITIONS": str(max(1, int(report.get("max_positions") or 1))),
            "ALPACA_MIN_DOLLAR_ORDER": "10",
            "ALPACA_ALLOW_STALE_PICKS": "0",
            "ALPACA_REFRESH_UTC": str(report.get("generated_at_utc") or ""),
            "MONTHLY_WEIGHTED_SIZING": "1",
            "MONTHLY_ATR_SIZING": "0",
            "MONTHLY_TRAIL_ENABLE": "1",
            "ALPACA_BROKER_PROTECTION_ENABLE": "1",
            "ALPACA_BROKER_PROTECTION_REQUIRED": "1",
            "ALPACA_BROKER_PROTECTION_ORDER_CLASS": "simple_stop",
            "ALPACA_NATIVE_TRAIL_ENABLE": "0",
            "ALPACA_ALLOW_EMPTY_PICKS_FOR_CASH": (
                "1" if report.get("reason") == "market_below_regime_sma_cash" else "0"
            ),
        }
    )
    return env


def main() -> int:
    ap = argparse.ArgumentParser(description="adaptive_v1 Alpaca paper driver")
    ap.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--target-alloc-pct", type=float, default=70.0)
    ap.add_argument("--max-positions", type=int, default=4)
    ap.add_argument("--preset", choices=("baseline", "lively"), default="baseline")
    ap.add_argument("--cache-dir", default="runtime/equities_yf_cache")
    ap.add_argument("--runtime-dir", default="runtime/equities_alpaca_adaptive_v1")
    ap.add_argument("--send-orders", action="store_true")
    ap.add_argument(
        "--reuse-selection",
        action="store_true",
        help="manage the last daily selection without recalculating or rotating it",
    )
    args = ap.parse_args()

    end = args.end or (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    cache_dir = Path(args.cache_dir)
    runtime_dir = Path(args.runtime_dir)
    if not cache_dir.is_absolute():
        cache_dir = ROOT / cache_dir
    if not runtime_dir.is_absolute():
        runtime_dir = ROOT / runtime_dir
    report_path = runtime_dir / "latest_selection.json"
    picks_csv = runtime_dir / "current_cycle_picks.csv"
    if args.reuse_selection:
        if not report_path.exists() or not picks_csv.exists():
            print(json.dumps({"error": "adaptive_selection_missing", "runtime_dir": str(runtime_dir)}))
            return 2
        report = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        report = run_shadow(
            symbols=symbols,
            start=args.start,
            end=end,
            capital=float(args.capital),
            max_positions=int(args.max_positions),
            cache_dir=cache_dir,
            target_alloc_pct=float(args.target_alloc_pct),
            preset=args.preset,
        )

    if not report.get("picks") and report.get("reason") != "market_below_regime_sma_cash":
        print(json.dumps({"error": "adaptive_selector_empty", "reason": report.get("reason")}, ensure_ascii=True))
        return 3

    runtime_dir.mkdir(parents=True, exist_ok=True)
    if not args.reuse_selection:
        report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        write_bridge_picks_csv(report, picks_csv)
    env = build_bridge_env(
        report,
        picks_csv=picks_csv,
        capital=float(args.capital),
        target_alloc_pct=float(args.target_alloc_pct),
        send_orders=bool(args.send_orders),
    )
    command = [sys.executable, str(ROOT / "scripts" / "equities_alpaca_paper_bridge.py"), "--picks-csv", str(picks_csv)]
    print(
        f"preset={report.get('preset', args.preset)} refresh={not args.reuse_selection} "
        f"mode={'send_orders' if args.send_orders else 'dry_run'} "
        f"picks={','.join(p['symbol'] for p in report.get('picks') or []) or 'cash'}"
    )
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
