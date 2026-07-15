#!/usr/bin/env python3
"""Validate the human-reviewed project capability registry.

The registry is an information/authority map, not a launcher.  This validator
has no network, broker, env or order capability.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "configs" / "project_capability_registry_v1.json"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{2,79}$")
EXECUTION_AUTHORITIES = {
    "none",
    "read_only",
    "tiny_money",
    "protect_existing_only",
    "paper_orders",
    "shadow_no_orders",
    "observer_proposal_only",
    "proposal_only",
    "report_only",
}
LIVE_STAGES = {"live_tiny_canary", "live_safe_hold"}
MONEY_AUTHORITIES = {"tiny_money", "protect_existing_only"}
REQUIRED_COMPONENT_FIELDS = {
    "component_id",
    "kind",
    "market",
    "physical_side",
    "stage",
    "execution_authority",
    "promotion_authorized",
    "runtime_entrypoints",
    "data_contract",
    "level_contract",
    "cost_contract",
    "evidence",
    "known_gaps",
    "next_gate",
}


def validate_registry(payload: Any, *, root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["registry must be a JSON object"], "warnings": []}
    if payload.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if payload.get("authority") != "human_reviewed_capability_map":
        errors.append("authority must equal human_reviewed_capability_map")
    allowed_stages = payload.get("allowed_stages")
    if not isinstance(allowed_stages, list) or not allowed_stages:
        errors.append("allowed_stages must be a non-empty list")
        allowed_stage_set: set[str] = set()
    else:
        allowed_stage_set = {str(value) for value in allowed_stages}
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        errors.append("components must be a non-empty list")
        components = []

    ids: list[str] = []
    stage_counts: Counter[str] = Counter()
    authority_counts: Counter[str] = Counter()
    for index, row in enumerate(components):
        prefix = f"components[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = sorted(REQUIRED_COMPONENT_FIELDS - set(row))
        if missing:
            errors.append(f"{prefix} missing fields: {','.join(missing)}")
        component_id = str(row.get("component_id") or "")
        ids.append(component_id)
        if not ID_RE.fullmatch(component_id):
            errors.append(f"{prefix}.component_id is not canonical: {component_id!r}")
        stage = str(row.get("stage") or "")
        authority = str(row.get("execution_authority") or "")
        stage_counts[stage] += 1
        authority_counts[authority] += 1
        if stage not in allowed_stage_set:
            errors.append(f"{component_id}: stage {stage!r} is not allowed")
        if authority not in EXECUTION_AUTHORITIES:
            errors.append(f"{component_id}: execution_authority {authority!r} is not allowed")
        if stage in LIVE_STAGES and authority not in MONEY_AUTHORITIES:
            errors.append(f"{component_id}: live stage requires explicit money/protection authority")
        if authority in MONEY_AUTHORITIES and stage not in LIVE_STAGES:
            errors.append(f"{component_id}: money/protection authority requires a live stage")
        if not isinstance(row.get("promotion_authorized"), bool):
            errors.append(f"{component_id}: promotion_authorized must be boolean")
        if row.get("promotion_authorized") is True and stage not in LIVE_STAGES:
            errors.append(f"{component_id}: promotion authorization is inconsistent with stage {stage}")

        for field in ("runtime_entrypoints", "evidence", "known_gaps"):
            if not isinstance(row.get(field), list):
                errors.append(f"{component_id}: {field} must be a list")
        for rel in row.get("runtime_entrypoints") or []:
            rel_text = str(rel)
            path = root / rel_text
            try:
                path.resolve().relative_to(root.resolve())
            except (OSError, ValueError):
                errors.append(f"{component_id}: unsafe runtime path {rel_text!r}")
                continue
            if not path.is_file():
                errors.append(f"{component_id}: runtime entrypoint missing: {rel_text}")
        for rel in row.get("evidence") or []:
            rel_text = str(rel)
            path = root / rel_text
            try:
                path.resolve().relative_to(root.resolve())
            except (OSError, ValueError):
                errors.append(f"{component_id}: unsafe evidence path {rel_text!r}")
                continue
            if not path.exists():
                # Runtime receipts may be intentionally absent on a clean clone;
                # the capability map remains valid but must expose the gap.
                warnings.append(f"{component_id}: evidence currently unavailable: {rel_text}")
        for field in ("kind", "market", "physical_side", "data_contract", "level_contract", "cost_contract", "next_gate"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append(f"{component_id}: {field} must be a non-empty string")

    duplicates = sorted(key for key, count in Counter(ids).items() if key and count > 1)
    if duplicates:
        errors.append(f"duplicate component_id values: {','.join(duplicates)}")
    return {
        "ok": not errors,
        "schema_version": payload.get("schema_version"),
        "as_of_utc": payload.get("as_of_utc"),
        "component_count": len(components),
        "stage_counts": dict(sorted(stage_counts.items())),
        "authority_counts": dict(sorted(authority_counts.items())),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    path = Path(args.registry).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = validate_registry(payload)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
