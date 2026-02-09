#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Print comma-separated symbol list from a backtest summary.

Usage:
  python3 backtest/symbols_from_summary.py backtest_runs/portfolio_*/summary.csv
  python3 backtest/symbols_from_summary.py backtest_runs/portfolio_*/   # folder ok

Output:
  BTCUSDT,ETHUSDT,...
"""

from __future__ import annotations

import os
import sys
import csv
from pathlib import Path
from typing import List


def _load_csv_rows(p: Path) -> List[dict]:
    with p.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 backtest/symbols_from_summary.py <summary.csv or run folder>", file=sys.stderr)
        return 2

    inp = Path(sys.argv[1]).expanduser()
    if inp.is_dir():
        inp = inp / "summary.csv"
    if not inp.exists():
        print(f"File not found: {inp}", file=sys.stderr)
        return 2

    rows = _load_csv_rows(inp)
    if not rows:
        print("", end="")
        return 0

    cols = set(rows[0].keys())

    # Portfolio summary format: first row has "symbols" with ';' separators
    if "symbols" in cols and rows[0].get("symbols"):
        syms = [s.strip() for s in str(rows[0]["symbols"]).replace(";", ",").split(",") if s.strip()]
        print(",".join(syms))
        return 0

    # Monthly summary format: one row per symbol + a final ALL/PORTFOLIO row
    if "symbol" in cols:
        syms = []
        for it in rows:
            sym = (it.get("symbol") or "").strip().upper()
            if not sym:
                continue
            if sym == "ALL" or "PORTFOLIO" in sym:
                continue
            syms.append(sym)
        # Preserve order but unique
        seen = set()
        out = []
        for s in syms:
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        print(",".join(out))
        return 0

    print(f"Unrecognized summary format. Columns: {sorted(cols)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
