#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ACTIVE = {
    "inplay_breakout.py",
    "btc_eth_midterm_pullback.py",
    "signals.py",
    "__init__.py",
}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    strategies = sorted((root / "strategies").glob("*.py"))
    out = root / "docs" / "rd_cleanup_candidates.csv"

    rows = []
    for p in strategies:
        status = "keep_active" if p.name in ACTIVE else "archive_candidate"
        rows.append((p.name, status))

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "status"])
        w.writerows(rows)

    keep_n = sum(1 for _, s in rows if s == "keep_active")
    arc_n = len(rows) - keep_n
    print(f"saved={out}")
    print(f"keep_active={keep_n} archive_candidate={arc_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

