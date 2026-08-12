#!/usr/bin/env python3
"""Validate a bounded candidate prefilter without broker or promotion authority."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.run_passport import validate_passport


def validate(passport_path: Path, result_paths: list[Path]) -> dict[str, Any]:
    errors: list[str] = []
    passport = validate_passport(json.loads(passport_path.read_text(encoding="utf-8")))
    contract = passport["measurement_contract"]
    expected_inputs = {Path(row["path"]).resolve() for row in passport["inputs"] if row.get("temporal_data")}
    holdout_start_ms = int(
        datetime.fromisoformat(passport["sealed_holdouts"][0]["start_utc"].replace("Z", "+00:00")).timestamp()
        * 1000
    )
    rows = []
    for path in result_paths:
        result = json.loads(path.read_text(encoding="utf-8"))
        aggregate = result.get("aggregate") or {}
        if result.get("authority") != "research_only_no_live_or_promotion":
            errors.append(f"{path}: authority drift")
        if result.get("sealed_holdout_rows_decoded") != 0:
            errors.append(f"{path}: sealed_holdout_rows_decoded must be zero")
        actual_inputs = {
            Path(str(value)).resolve() for value in (result.get("input_files") or {}).values()
        }
        if not actual_inputs and result.get("input_json"):
            actual_inputs = {Path(str(result["input_json"])).resolve()}
        if actual_inputs != expected_inputs:
            errors.append(f"{path}: inputs differ from passport")
        declared_costs = contract["costs"].get("round_trip_bps")
        if declared_costs is None:
            declared_costs = contract["costs"].get("round_trip_bps_scenarios") or []
        accepted_costs = [float(declared_costs)] if isinstance(declared_costs, (int, float)) else [float(x) for x in declared_costs]
        if float(result.get("fee_round_trip_bps") or -1) not in accepted_costs:
            errors.append(f"{path}: cost contract drift")
        if result.get("symbols") != contract["universe"]:
            errors.append(f"{path}: universe contract drift")
        for symbol, boundary in (result.get("bar_ranges") or {}).items():
            if int(boundary.get("last_ts_ms") or holdout_start_ms) >= holdout_start_ms:
                errors.append(f"{path}: {symbol} reaches sealed holdout")
        if int(aggregate.get("trades") or 0) <= 0:
            errors.append(f"{path}: no trades")
        if int(aggregate.get("months_positive") or 0) > int(aggregate.get("months_total") or 0):
            errors.append(f"{path}: invalid monthly counts")
        rows.append({
            "path": str(path),
            "strategy": result.get("strategy"),
            "trades": aggregate.get("trades"),
            "expectancy_R": aggregate.get("expectancy_R"),
            "profit_factor": aggregate.get("profit_factor"),
            "months_positive": aggregate.get("months_positive"),
            "months_total": aggregate.get("months_total"),
        })
    return {
        "schema_id": "candidate_prefilter_validation_receipt_v1",
        "authority": "research_only_no_live_or_promotion",
        "passport_sha256": passport["passport_sha256"],
        "validated_results": rows,
        "errors": errors,
        "status": "pass" if not errors else "fail_closed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passport", required=True, type=Path)
    parser.add_argument("--result", required=True, action="append", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = validate(args.passport, args.result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
