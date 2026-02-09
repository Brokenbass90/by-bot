#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract a comma-separated symbol list from a portfolio summary.csv.

Usage:
  python3 scripts/symbols_from_summary.py backtest_runs/portfolio_*/summary.csv

Prints:
  BTCUSDT,ETHUSDT,...
"""

import csv
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/symbols_from_summary.py <summary_csv_path>", file=sys.stderr)
        return 2

    p = Path(sys.argv[1])
    if not p.exists():
        print(f"File not found: {p}", file=sys.stderr)
        return 2

    with p.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        rows = list(r)

    if not rows:
        print("Empty summary.csv (no rows)", file=sys.stderr)
        return 2

    row = rows[0]
    for key in ("symbols", "Symbols", "SYMBOLS"):
        if key in row and row[key]:
            s = str(row[key]).strip()
            s = s.replace(";", ",")
            s = ",".join([x.strip().upper() for x in s.split(",") if x.strip()])
            print(s)
            return 0

    print("No 'symbols' column found in summary.csv", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
