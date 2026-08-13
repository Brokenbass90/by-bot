#!/usr/bin/env python3
"""Independent arithmetic/contract audit of Alpaca protection challenger V2."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.run_passport import sha256_file, validate_passport


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return -worst * 100.0


def _recompute(row: dict[str, Any]) -> dict[str, Any]:
    equity = list(row["daily_equity"])
    trades = list(row["trades"])
    initial = float(row["initial_capital"])
    values = [initial, *[float(item["equity"]) for item in equity]]
    gains = sum(max(0.0, float(item["pnl"])) for item in trades)
    losses = -sum(min(0.0, float(item["pnl"])) for item in trades)
    month_end: dict[str, float] = {}
    for item in equity:
        month_end[str(item["session"])[:7]] = float(item["equity"])
    previous = initial
    monthly = []
    for value in month_end.values():
        monthly.append((value / previous - 1.0) * 100.0)
        previous = value
    lifecycle_errors = sum(
        date.fromisoformat(str(item["exit_session"])) < date.fromisoformat(str(item["entry_session"]))
        or float(item["entry_fill"]) <= 0
        or float(item["exit_fill"]) <= 0
        or float(item["qty"]) <= 0
        for item in trades
    )
    return {
        "return_pct": (values[-1] / initial - 1.0) * 100.0,
        "daily_max_drawdown_pct": _max_drawdown(values),
        "profit_factor_realized": gains / losses if losses else (math.inf if gains else 0.0),
        "realized_trades": len(trades),
        "red_months": sum(value < 0 for value in monthly),
        "months": len(monthly),
        "worst_month_pct": min(monthly, default=0.0),
        "average_gross_exposure_pct": sum(float(item["gross_exposure"]) for item in equity) / len(equity) * 100.0,
        "lifecycle_errors": lifecycle_errors,
        "gap_blocks": sum(len(item.get("gap_blocked") or []) for item in row["decisions"]),
    }


def audit(root: Path) -> dict[str, Any]:
    failures: list[str] = []
    passport_path = root / "run_passport.json"
    result_path = root / "result.json"
    passport = validate_passport(json.loads(passport_path.read_text(encoding="utf-8")))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    v1 = json.loads((ROOT / "research_lab/results/alpaca_clean_v38_proxy_v1_20260813/result.json").read_text(encoding="utf-8"))
    for item in [*passport["code"], *passport["inputs"]]:
        if sha256_file(Path(item["path"])) != item["sha256"]:
            failures.append(f"hash:{Path(item['path']).name}")
    if result.get("capital_authorized") is not False or result.get("exact_live_contract") is not False:
        failures.append("authority")

    computed: dict[str, Any] = {}
    metric_fields = (
        "return_pct", "daily_max_drawdown_pct", "profit_factor_realized",
        "realized_trades", "red_months", "months", "worst_month_pct",
        "average_gross_exposure_pct",
    )
    for arm, cases in result["results"].items():
        computed[arm] = {}
        for case, row in cases.items():
            own = _recompute(row)
            computed[arm][case] = own
            for field in metric_fields:
                if field in {"realized_trades", "red_months", "months"}:
                    equal = own[field] == row[field]
                else:
                    equal = math.isclose(float(own[field]), float(row[field]), abs_tol=1e-9)
                if not equal:
                    failures.append(f"{arm}:{case}:{field}")
            if own["lifecycle_errors"]:
                failures.append(f"{arm}:{case}:lifecycle")

    for case, v1_name in (("base", "base_5bps_side"), ("stress", "stress_10bps_side")):
        for field in metric_fields:
            left = result["results"]["current_contract"][case][field]
            right = v1["results"][v1_name][field]
            if field in {"realized_trades", "red_months", "months"}:
                equal = left == right
            else:
                equal = math.isclose(float(left), float(right), abs_tol=1e-9)
            if not equal:
                failures.append(f"baseline_parity:{case}:{field}")
    for case in ("base", "stress"):
        if computed["current_contract"][case]["gap_blocks"] != 0:
            failures.append(f"current_contract:{case}:unexpected_gap_blocks")
        if computed["entry_relative_stop"][case]["gap_blocks"] != 0:
            failures.append(f"entry_relative_stop:{case}:unexpected_gap_blocks")
        if computed["entry_stop_gap2"][case]["gap_blocks"] <= 0:
            failures.append(f"entry_stop_gap2:{case}:missing_gap_blocks")

    gates = {}
    baseline = result["results"]["current_contract"]
    for arm in ("entry_relative_stop", "entry_stop_gap2"):
        gates[arm] = all(
            result["results"][arm][case]["daily_max_drawdown_pct"] < baseline[case]["daily_max_drawdown_pct"]
            and result["results"][arm][case]["annualized_return_pct"] >= baseline[case]["annualized_return_pct"]
            and result["results"][arm][case]["profit_factor_realized"] >= baseline[case]["profit_factor_realized"]
            and result["results"][arm][case]["realized_trades"] >= 30
            for case in ("base", "stress")
        )
    if gates != result["diagnostic_gates"]:
        failures.append("gate_recompute")
    return {
        "schema_id": "alpaca_protection_challenger_v2_independent_audit",
        "passed": not failures,
        "failures": sorted(set(failures)),
        "authority": "research_only_no_live_or_promotion",
        "capital_authorized": False,
        "passport_sha256": sha256_file(passport_path),
        "result_sha256": sha256_file(result_path),
        "computed": computed,
        "recomputed_gates": gates,
        "interpretation": "arithmetic and V1 baseline parity only; PIT and 15-minute live parity blockers remain",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = audit(args.root.resolve())
    if args.out.exists():
        raise RuntimeError(f"write-once output exists: {args.out}")
    args.out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
