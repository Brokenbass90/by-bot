#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _read_summary(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            return {k: (v or "") for k, v in row.items()}
    return {}


def _iter_run_dirs(root: Path):
    if not root.exists():
        return
    for p in sorted(root.iterdir()):
        if p.is_dir():
            yield p


def main() -> int:
    ap = argparse.ArgumentParser(description="Build one CSV catalog from run folders")
    ap.add_argument("--root", default="backtest_runs/old", help="Folder containing run directories")
    ap.add_argument("--out", default="docs/backtest_runs_catalog.csv", help="Output CSV file")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    for run_dir in _iter_run_dirs(root) or []:
        row = {
            "run_dir": str(run_dir.relative_to(Path.cwd())),
            "kind": run_dir.name.split("_", 1)[0],
            "summary_exists": "0",
            "tag": "",
            "strategies": "",
            "symbols": "",
            "days": "",
            "end_date_utc": "",
            "starting_equity": "",
            "ending_equity": "",
            "trades": "",
            "net_pnl": "",
            "profit_factor": "",
            "winrate": "",
            "max_drawdown": "",
        }
        sm = _read_summary(run_dir / "summary.csv")
        if sm:
            row["summary_exists"] = "1"
            for k in (
                "tag",
                "strategies",
                "symbols",
                "days",
                "end_date_utc",
                "starting_equity",
                "ending_equity",
                "trades",
                "net_pnl",
                "profit_factor",
                "winrate",
                "max_drawdown",
            ):
                row[k] = sm.get(k, "")
        rows.append(row)

    fields = [
        "run_dir",
        "kind",
        "summary_exists",
        "tag",
        "strategies",
        "symbols",
        "days",
        "end_date_utc",
        "starting_equity",
        "ending_equity",
        "trades",
        "net_pnl",
        "profit_factor",
        "winrate",
        "max_drawdown",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"saved={out}")
    print(f"root={root}")
    print(f"rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
