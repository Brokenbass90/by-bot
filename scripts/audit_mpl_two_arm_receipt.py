#!/usr/bin/env python3
"""Independently validate the frozen MPL two-arm receipt without rerunning it."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_AUTHORITY = "research_only_no_live_or_promotion"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def expected_arm_verdict(arm: dict[str, Any]) -> str:
    death = arm.get("death_gates") or {}
    acceptance = arm.get("acceptance_gates") or {}
    if not death or not all(value is True for value in death.values()):
        return "REJECT"
    if acceptance and all(value is True for value in acceptance.values()):
        return "SHADOW_CANDIDATE_ONLY"
    return "NO_PROMOTION"


def expected_choice(arms: dict[str, dict[str, Any]]) -> str | None:
    if (arms.get("V4_stop_x2.0") or {}).get("verdict") == "SHADOW_CANDIDATE_ONLY":
        return "V4"
    if (arms.get("V3_stop_x1.0") or {}).get("verdict") == "SHADOW_CANDIDATE_ONLY":
        return "V3"
    return None


def audit(root: Path, manifest_path: Path, result_path: Path, source: Path) -> dict[str, Any]:
    errors: list[str] = []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if manifest.get("schema_id") != "mpl_two_arm_holdout_unseal_manifest_v2":
        errors.append("manifest_schema")
    if result.get("schema_id") != "mpl_two_arm_holdout_result_v1":
        errors.append("result_schema")
    if manifest.get("authority") != EXPECTED_AUTHORITY or result.get("authority") != EXPECTED_AUTHORITY:
        errors.append("authority")
    if result.get("capital_authorized") is not False:
        errors.append("capital_authority")
    if result.get("manifest_sha256") != sha256_file(manifest_path):
        errors.append("manifest_hash")

    code_hashes = dict(manifest.get("code_sha256") or {})
    for raw, expected in code_hashes.items():
        path = Path(raw)
        if not path.is_file() or sha256_file(path) != expected:
            errors.append(f"code_hash:{path.name}")

    input_hashes = dict(manifest.get("input_sha256") or {})
    if manifest.get("input_set_sha256") != canonical_sha256(input_hashes):
        errors.append("input_set_hash")
    allowlist = json.loads((root / "research_lab/allowlist_v3.json").read_text(encoding="utf-8"))
    expected_files = {f"{symbol}.npz" for symbol in allowlist}
    if set(input_hashes) != expected_files:
        errors.append("input_file_set")
    for name, expected in input_hashes.items():
        path = source / name
        if not path.is_file() or sha256_file(path) != expected:
            errors.append(f"input_hash:{name}")
    build_status = source / "build_status.json"
    if (
        not build_status.is_file()
        or (manifest.get("preflight") or {}).get("build_status_sha256") != sha256_file(build_status)
    ):
        errors.append("build_status_hash")

    arms = dict(result.get("arms") or {})
    expected_arms = {"V4_stop_x2.0": 2.0, "V3_stop_x1.0": 1.0}
    if set(arms) != set(expected_arms):
        errors.append("arm_set")
    for name, multiplier in expected_arms.items():
        arm = dict(arms.get(name) or {})
        if float(arm.get("arm_stop_multiplier") or 0) != multiplier:
            errors.append(f"stop_multiplier:{name}")
        if float(arm.get("bootstrap_lower_quantile") or 0) != 0.0125:
            errors.append(f"bootstrap_quantile:{name}")
        if arm.get("verdict") != expected_arm_verdict(arm):
            errors.append(f"verdict:{name}")
        n = int(arm.get("n") or 0)
        if n != int(arm.get("control_n") or -1):
            errors.append(f"control_n:{name}")
        if n != sum(int(value) for value in (arm.get("signal_counts") or {}).values()):
            errors.append(f"signal_count_sum:{name}")
        if n != sum(int(row.get("n") or 0) for row in (arm.get("quarters") or {}).values()):
            errors.append(f"quarter_count_sum:{name}")
        if n != sum(int(row.get("n") or 0) for row in (arm.get("halves") or [])):
            errors.append(f"half_count_sum:{name}")
    if result.get("chosen_arm") != expected_choice(arms):
        errors.append("chosen_arm")

    return {
        "schema_id": "mpl_two_arm_independent_audit_v1",
        "authority": "research_only_no_live_or_promotion",
        "capital_authorized": False,
        "manifest_sha256": sha256_file(manifest_path),
        "result_sha256": sha256_file(result_path),
        "code_file_count": len(code_hashes),
        "input_file_count": len(input_hashes),
        "errors": sorted(set(errors)),
        "verdict": "PASS" if not errors else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", type=Path, default=Path("reports/research/mpl_two_arm_holdout_20260812/unseal_manifest.json"))
    parser.add_argument("--result", type=Path, default=Path("reports/research/mpl_two_arm_holdout_20260812/result.json"))
    parser.add_argument("--source", type=Path, default=Path("research_lab/data/m15_exec_v3"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.root.resolve(), args.manifest, args.result, args.source)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
