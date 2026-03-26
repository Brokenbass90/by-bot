#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


def _load_candidates(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            file = (row.get("file") or "").strip()
            status = (row.get("status") or "").strip()
            if file and status:
                rows.append({"file": file, "status": status})
    return rows


def _parse_strategy_imports(run_portfolio_path: Path) -> set[str]:
    text = run_portfolio_path.read_text(encoding="utf-8")
    mods = set(re.findall(r"from\s+strategies\.([a-zA-Z0-9_]+)\s+import\s+", text))
    return mods


def main() -> int:
    ap = argparse.ArgumentParser(description="Report cleanup blockers for strategy archiving")
    ap.add_argument("--candidates", default="docs/rd_cleanup_candidates.csv")
    ap.add_argument("--run-portfolio", default="backtest/run_portfolio.py")
    ap.add_argument("--out", default="docs/cleanup_gap_report.csv")
    args = ap.parse_args()

    root = Path.cwd()
    c_path = (root / args.candidates).resolve()
    rp_path = (root / args.run_portfolio).resolve()
    out_path = (root / args.out).resolve()

    if not c_path.exists():
        raise SystemExit(f"Missing candidates csv: {c_path}")
    if not rp_path.exists():
        raise SystemExit(f"Missing run_portfolio file: {rp_path}")

    imports = _parse_strategy_imports(rp_path)
    rows = _load_candidates(c_path)

    out_rows: list[dict[str, str]] = []
    for row in rows:
        file = row["file"]
        status = row["status"]
        module = file[:-3] if file.endswith(".py") else file
        exists_file = "1" if (root / "strategies" / file).exists() else "0"
        in_imports = "1" if module in imports else "0"

        if status == "archive_candidate" and in_imports == "1":
            hint = "prune_import_before_archive"
        elif status == "archive_candidate":
            hint = "archive_ready"
        elif status == "keep_active" and in_imports == "1":
            hint = "ok_active"
        else:
            hint = "check_active_missing_import"

        out_rows.append(
            {
                "file": file,
                "module": module,
                "status": status,
                "exists_file": exists_file,
                "in_run_portfolio_imports": in_imports,
                "action_hint": hint,
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "file",
                "module",
                "status",
                "exists_file",
                "in_run_portfolio_imports",
                "action_hint",
            ],
        )
        w.writeheader()
        w.writerows(out_rows)

    prune_needed = sum(1 for x in out_rows if x["action_hint"] == "prune_import_before_archive")
    archive_ready = sum(1 for x in out_rows if x["action_hint"] == "archive_ready")
    print(f"saved={out_path}")
    print(f"rows={len(out_rows)} prune_import_before_archive={prune_needed} archive_ready={archive_ready}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
