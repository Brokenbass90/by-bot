#!/usr/bin/env python3
"""Verify the passport-bound Inplay causal replay and issue a shadow-only verdict."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.run_passport import sha256_file, validate_passport


def audit(passport_path: Path, result_path: Path) -> dict:
    errors: list[str] = []
    passport = validate_passport(json.loads(passport_path.read_text(encoding="utf-8")))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    for row in passport["code"]:
        if sha256_file(Path(row["path"])) != row["sha256"]:
            errors.append(f"code_hash:{Path(row['path']).name}")
    for row in passport["inputs"]:
        if sha256_file(Path(row["path"])) != row["sha256"]:
            errors.append(f"input_hash:{Path(row['path']).name}")
    meta = result.get("_meta") or {}
    if meta.get("passport_sha256") != passport.get("passport_sha256"):
        errors.append("passport_binding")
    if meta.get("schema_id") != "path_sim_fail_closed_v4_next_open":
        errors.append("engine_schema")
    if meta.get("same_close_entry") is not False or meta.get("reserved_holdout_used") is not False:
        errors.append("causal_or_holdout_contract")
    selected = []
    for index in range(4):
        window = result.get(str(index)) or {}
        grid = list(window.get("grid") or [])
        if len(grid) != 30:
            errors.append(f"grid:{index}")
            continue
        matches = [row for row in grid if row.get("mult") == 0.75 and row.get("hours") == 24]
        if len(matches) != 1:
            errors.append(f"fixed_contract:{index}")
        else:
            selected.append(matches[0])
    means = [float(row["R_per_trade"]) for row in selected]
    positive_folds = sum(value > 0 for value in means)
    median_r = statistics.median(means) if means else None
    viable = not errors and len(means) == 4 and positive_folds >= 3 and median_r > 0
    return {
        "schema_id": "inplay_causal_receipt_audit_v1",
        "authority": "research_only_shadow_zero_risk_at_most",
        "capital_authorized": False,
        "passport_sha256": sha256_file(passport_path),
        "result_sha256": sha256_file(result_path),
        "fixed_contract": {"stop_typical_move_multiplier": 0.75, "hours": 24},
        "fold_mean_r": means,
        "positive_folds": positive_folds,
        "median_fold_r": median_r,
        "errors": sorted(set(errors)),
        "verdict": "CAUSAL_VIABLE_SHADOW_ONLY" if viable else "REJECT",
        "limitations": [
            "preholdout period was used during discovery and is not independent confirmation",
            "one of four fixed folds is materially negative",
            "portfolio overlap, slot use, prospective fills and drawdown are not measured",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passport", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.passport, args.result)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 2 if result["verdict"] == "REJECT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
