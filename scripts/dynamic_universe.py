#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build a dynamic symbol universe from a trades.csv file.

Example:
  python3 scripts/dynamic_universe.py \
    --trades backtest_runs/portfolio_20260209_170340_combo_inplay_first_180d/trades.csv \
    --lookback_days 60 --min_trades 8 --exclude_worst 5
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple


def _parse_ts_ms(v: str) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def _utc_from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", required=True, help="Path to trades.csv")
    ap.add_argument("--lookback_days", type=int, default=60, help="Lookback window by exit_ts (UTC)")
    ap.add_argument("--min_trades", type=int, default=5, help="Minimum trades per symbol to be considered")
    ap.add_argument("--exclude_worst", type=int, default=5, help="Exclude N worst symbols by PnL")
    ap.add_argument("--include_top", type=int, default=0, help="Optional: include only top N symbols by PnL")
    ap.add_argument("--out", default="", help="Optional output file for comma-separated symbols")
    args = ap.parse_args()

    cutoff = None
    if args.lookback_days and args.lookback_days > 0:
        cutoff = datetime.now(timezone.utc).timestamp() - args.lookback_days * 86400

    per: Dict[str, Dict[str, float]] = defaultdict(lambda: {"pnl": 0.0, "trades": 0})
    with open(args.trades, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            ts = _parse_ts_ms(row.get("exit_ts", "0"))
            if cutoff is not None and (ts / 1000.0) < cutoff:
                continue
            sym = row.get("symbol", "")
            if not sym:
                continue
            pnl = float(row.get("pnl", 0.0) or 0.0)
            per[sym]["pnl"] += pnl
            per[sym]["trades"] += 1

    rows: List[Tuple[str, float, int]] = []
    for sym, v in per.items():
        if v["trades"] >= args.min_trades:
            rows.append((sym, v["pnl"], int(v["trades"])))

    rows.sort(key=lambda x: x[1], reverse=True)

    if args.include_top and args.include_top > 0:
        selected = rows[: args.include_top]
    else:
        worst = set(sym for sym, _, _ in rows[-max(0, int(args.exclude_worst)) :])
        selected = [r for r in rows if r[0] not in worst]

    symbols = [sym for sym, _, _ in selected]

    print("Selected symbols:", ",".join(symbols))
    if args.exclude_worst > 0:
        print("Excluded worst:", ",".join(sym for sym, _, _ in rows[-args.exclude_worst :]))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(",".join(symbols))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
