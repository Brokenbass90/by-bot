#!/usr/bin/env python3
"""Independent arithmetic/authority audit for mapped funding V2."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _annualized(values: list[float]) -> float | None:
    return (sum(values) / len(values) * 365.0 / 30.0 * 100.0) if values else None


def audit(result_path: Path, passport_path: Path) -> dict[str, Any]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    passport = json.loads(passport_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if result.get("authority") != "research_only_no_live_or_promotion":
        errors.append("authority_drift")
    if result.get("capital_authorized") is not False or result.get("promotion_authorized") is not False:
        errors.append("capital_or_promotion_authorized")
    if result.get("sealed_holdout_rows_decoded") != 0:
        errors.append("sealed_holdout_was_read")
    if result.get("passport_sha256") != passport.get("passport_sha256"):
        errors.append("passport_mismatch")
    if result.get("survivorship_resolved") is not False:
        errors.append("survivorship_claim_drift")
    periods = list(result.get("periods") or [])
    if any(int(row["exit_ts_ms"]) >= 1759276800000 for row in periods):
        errors.append("period_crosses_sealed_boundary")

    expected_costs = {"base_31bps": 31.0, "stress_51bps": 51.0}
    recomputed = {}
    for name, cost_bps in expected_costs.items():
        selected = [float(row["selected_gross_return"]) - cost_bps / 10_000.0 for row in periods]
        basket = [float(row["basket_gross_return"]) - cost_bps / 10_000.0 for row in periods]
        edge = [a - b for a, b in zip(selected, basket)]
        half = len(edge) // 2
        values = {
            "periods": len(periods),
            "selected_annualized_pair_notional_pct": _annualized(selected),
            "basket_annualized_pair_notional_pct": _annualized(basket),
            "selection_edge_annualized_pct": _annualized(edge),
            "selection_edge_halves_annualized_pct": [
                _annualized(edge[:half]), _annualized(edge[half:])
            ],
            "positive_periods": sum(x > 0 for x in selected),
            "red_periods": sum(x < 0 for x in selected),
        }
        reported = (result.get("scenarios") or {}).get(name) or {}
        for key, expected in values.items():
            actual = reported.get(key)
            if isinstance(expected, list):
                if not isinstance(actual, list) or len(actual) != len(expected) or any(
                    not math.isclose(float(a), float(e), abs_tol=1e-10, rel_tol=0.0)
                    for a, e in zip(actual, expected)
                ):
                    errors.append(f"{name}:{key}_mismatch")
            elif isinstance(expected, float):
                if actual is None or not math.isclose(float(actual), expected, abs_tol=1e-10, rel_tol=0.0):
                    errors.append(f"{name}:{key}_mismatch")
            elif actual != expected:
                errors.append(f"{name}:{key}_mismatch")
        recomputed[name] = values

    quarantine = result.get("quarantined_symbol_periods") or {}
    if int(quarantine.get("ZECUSDT") or 0) <= 0:
        errors.append("known_zec_corruption_not_quarantined")
    receipt = {
        "schema_id": "funding_spot_perp_mapped_v2_independent_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "authority": "research_only_no_live_or_promotion",
        "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "passport_sha256": passport.get("passport_sha256"),
        "recomputed": recomputed,
        "errors": errors,
        "verdict": "PASS" if not errors else "FAIL_CLOSED",
    }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--passport", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = audit(args.result, args.passport)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
