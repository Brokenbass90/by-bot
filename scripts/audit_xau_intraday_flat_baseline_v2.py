#!/usr/bin/env python3
"""Independent arithmetic and contract audit for XAU flat baseline V2."""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "research_lab/results/xau_intraday_flat_baseline_v2_20260813"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    errors: list[str] = []
    audited: dict[str, object] = {}
    for cost_case in ("base", "stress"):
        summaries = _rows(RESULT / cost_case / "summary.csv")
        trades = _rows(RESULT / cost_case / "trades.csv")
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for trade in trades:
            grouped[trade["setup"]].append(trade)
            entry = datetime.fromtimestamp(float(trade["entry_ts"]), timezone.utc)
            exit_ = datetime.fromtimestamp(float(trade["exit_ts"]), timezone.utc)
            if exit_ < entry:
                errors.append(f"{cost_case}:{trade['setup']}:exit_before_entry")
            if trade.get("exit_reason") == "forced_flat" and exit_.hour != 21:
                errors.append(f"{cost_case}:{trade['setup']}:bad_forced_flat_hour")
        case_rows: dict[str, object] = {}
        for summary in summaries:
            setup = summary["setup"]
            own = grouped.get(setup, [])
            count = len(own)
            net_r = sum(float(row["r"]) for row in own)
            if count != int(summary["trades"]):
                errors.append(f"{cost_case}:{setup}:trade_count")
            if not math.isclose(net_r, float(summary["net_r"]), abs_tol=5e-4):
                errors.append(f"{cost_case}:{setup}:net_r")
            if summary["preflight_go"] != "False":
                errors.append(f"{cost_case}:{setup}:unexpected_preflight_pass")
            case_rows[setup] = {"trades": count, "net_r": round(net_r, 4)}
        audited[cost_case] = case_rows

    payload = {
        "schema_id": "xau_intraday_flat_baseline_v2_independent_audit_v1",
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "audited": audited,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
