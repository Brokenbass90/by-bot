#!/usr/bin/env python3
"""Independent arithmetic and lifecycle receipt for bounded research outputs.

This validator deliberately does not decide whether a trading idea is good.
It checks that a report agrees with its trade ledger and that basic position
lifecycle invariants were not violated by the research harness.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def _float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def _selected_summary(verdict: dict[str, Any]) -> dict[str, Any]:
    for key in ("best_stress", "best"):
        value = verdict.get(key)
        if isinstance(value, dict):
            return value
    return {}


def validate_receipt(
    verdict: dict[str, Any], trades: Sequence[dict[str, str]]
) -> dict[str, Any]:
    summary = _selected_summary(verdict)
    failures: list[str] = []
    lifecycle_failures = 0
    arithmetic_failures = 0
    pnl_values: list[float] = []

    for index, row in enumerate(trades):
        try:
            pnl = _float(row, "pnl_bps")
            cost = _float(row, "cost_bps")
            if "gross_bps" in row and row.get("gross_bps") not in (None, ""):
                gross = _float(row, "gross_bps")
            else:
                side = 1.0 if str(row.get("side") or "").lower() in {"long", "buy"} else -1.0
                gross = side * (_float(row, "exit_price") / _float(row, "average_entry") - 1.0) * 10_000.0
            # Ledgers round price fields to eight decimals, so allow the tiny
            # reconstruction error introduced by their serialized precision.
            if not math.isclose(pnl, gross - cost, rel_tol=0.0, abs_tol=1e-4):
                arithmetic_failures += 1
            if cost < 0:
                arithmetic_failures += 1
            pnl_values.append(pnl)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            arithmetic_failures += 1
            continue

        try:
            if "entry_ts" in row and "exit_ts" in row:
                lifecycle_failures += int(int(row["exit_ts"]) < int(row["entry_ts"]))
            if "entry_day" in row and "exit_day" in row:
                lifecycle_failures += int(int(row["exit_day"]) < int(row["entry_day"]))
            if "held_days" in row and summary.get("max_hold_days") is not None:
                lifecycle_failures += int(int(row["held_days"]) > int(summary["max_hold_days"]))
        except (KeyError, TypeError, ValueError):
            lifecycle_failures += 1

    if arithmetic_failures:
        failures.append(f"trade_arithmetic_failures={arithmetic_failures}")
    if lifecycle_failures:
        failures.append(f"lifecycle_failures={lifecycle_failures}")

    expected_count = int(summary.get("trades") or 0)
    if expected_count != len(trades):
        failures.append(f"trade_count verdict={expected_count} csv={len(trades)}")
    expected_net = float(summary.get("net_bps") or 0.0)
    csv_net = sum(pnl_values)
    if not math.isclose(expected_net, csv_net, rel_tol=0.0, abs_tol=1e-3):
        failures.append(f"net_bps verdict={expected_net:.6f} csv={csv_net:.6f}")

    fold_key = "entry_ts" if trades and "entry_ts" in trades[0] else "entry_day"
    if trades and fold_key in trades[0] and isinstance(summary.get("fold_net_bps"), list):
        secondary = "symbol" if "symbol" in trades[0] else "pair"
        ordered = sorted(trades, key=lambda row: (int(row[fold_key]), str(row.get(secondary) or "")))
        folds = [
            sum(float(row["pnl_bps"]) for row in ordered[i * len(ordered) // 4:(i + 1) * len(ordered) // 4])
            for i in range(4)
        ]
        expected_folds = [float(value) for value in summary["fold_net_bps"]]
        if any(not math.isclose(a, b, rel_tol=0.0, abs_tol=1e-3) for a, b in zip(folds, expected_folds)):
            failures.append("fold_net_bps_mismatch")

    return {
        "schema": "research_result_validation_receipt_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": not failures,
        "trade_count": len(trades),
        "recomputed_net_bps": round(csv_net, 6),
        "arithmetic_failures": arithmetic_failures,
        "lifecycle_failures": lifecycle_failures,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--trades", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    verdict_path = Path(args.verdict)
    trades_path = Path(args.trades)
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    with trades_path.open(newline="", encoding="utf-8") as handle:
        trades = list(csv.DictReader(handle))
    receipt = validate_receipt(verdict, trades)
    output = Path(args.output) if args.output else verdict_path.with_name("validation_receipt.json")
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
