#!/usr/bin/env python3
"""Metadata-only preflight for the contaminated ATT1/SBR1 reserved window.

This command deliberately cannot load, hash, inspect, or score market files.
It freezes the exact live-native major-8 candidate and reports all remaining
blockers before a separately authorized one-shot diagnostic is possible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json"
DEFAULT_RECEIPT = ROOT / "reports/receipts/ATT1_SBR1_RESERVED_OOS_PREFLIGHT_2026_08_27.json"
EXPECTED_START_UTC = "2025-10-01T00:00:00Z"
EXPECTED_END_UTC_EXCLUSIVE = "2026-07-01T00:00:00Z"
EXPECTED_SCHEMA = "att1_sbr1_reserved_oos_diagnostic_preflight_config_v1"
EXPECTED_CLASSIFICATION = "RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION"
EXPECTED_SOURCE_PIN_PATHS = {
    "live_native_candidate": "configs/research/att1_sbr1_live_native_parity_v1.json",
    "fixed51_evidence_contract": "configs/research/att1_sbr1_fixed51_evidence_parity_v1.json",
    "presealed_thresholds": (
        "research_lab/results/att1_sbr1_presealed_economics_diagnostic_20260823/receipt.json"
    ),
    "live_caller_parity_receipt": (
        "reports/receipts/LIVE_CALLER_PARITY_FINAL_VERIFICATION_2026_08_26.json"
    ),
    "legacy_att1_prereg": "research_lab/prereg/PREREG_FLAT_DOWN_2026_08_18.md",
    "legacy_sbr1_prereg": "research_lab/prereg/PREREG_FLAT_UP_2026_08_19.md",
}
EXPECTED_CANDIDATE_PATH = "configs/research/att1_sbr1_live_native_parity_v1.json"
EXPECTED_THRESHOLD_PATH = (
    "research_lab/results/att1_sbr1_presealed_economics_diagnostic_20260823/receipt.json"
)
EXPECTED_RESERVED_M5_MANIFEST_PATH = (
    "configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json"
)
EXPECTED_RUNNER_PATH = "scripts/run_att1_sbr1_reserved_oos_v1.py"
EXPECTED_AUDIT_PATH = "scripts/audit_att1_sbr1_reserved_oos_v1.py"


class PreflightViolation(ValueError):
    """A metadata or source invariant changed before any market read."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def calendar_days(start_utc: str, end_utc_exclusive: str) -> int:
    start = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_utc_exclusive.replace("Z", "+00:00"))
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise PreflightViolation("invalid reserved window")
    seconds = (end - start).total_seconds()
    if seconds % 86_400:
        raise PreflightViolation("reserved window is not whole UTC days")
    return int(seconds // 86_400)


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PreflightViolation(f"required regular JSON missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightViolation(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PreflightViolation(f"JSON root must be an object: {path}")
    return value


def _repo_file(root: Path, raw: object) -> Path:
    text = str(raw or "")
    relative = Path(text)
    if (
        not text
        or relative.is_absolute()
        or "\\" in text
        or any(part in {"", ".", ".."} for part in relative.parts)
        or ".git" in relative.parts
    ):
        raise PreflightViolation(f"unsafe repo-relative path: {text!r}")
    cursor = root.resolve()
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PreflightViolation(f"source path contains symlink: {text!r}")
    if not cursor.is_file():
        raise PreflightViolation(f"required source missing: {text}")
    return cursor


def _verify_pin(root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    path = _repo_file(root, row.get("path"))
    expected = str(row.get("sha256") or "")
    actual = sha256_file(path)
    if len(expected) != 64 or actual != expected:
        raise PreflightViolation(f"source pin drift: {row.get('path')}")
    return {
        "path": str(row.get("path")),
        "sha256": actual,
        "bytes": path.stat().st_size,
    }


def _validate_config(config: dict[str, Any]) -> None:
    fingerprint = str(config.get("config_fingerprint_sha256") or "")
    frozen = dict(config)
    frozen.pop("config_fingerprint_sha256", None)
    if fingerprint != canonical_sha256(frozen):
        raise PreflightViolation("config fingerprint mismatch")
    exact = {
        "schema_id": EXPECTED_SCHEMA,
        "authority": "metadata_only_no_reserved_market_decode_no_live_no_broker_no_money_no_promotion",
        "default_off": True,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
        "performance_allowed": False,
        "classification": EXPECTED_CLASSIFICATION,
        "purity": "KNOWN_CONTAMINATED",
    }
    if any(config.get(key) != value for key, value in exact.items()):
        raise PreflightViolation("authority or classification changed")
    window = config.get("reserved_window")
    if not isinstance(window, dict):
        raise PreflightViolation("reserved_window missing")
    days = calendar_days(
        str(window.get("start_utc") or ""),
        str(window.get("end_utc_exclusive") or ""),
    )
    if window != {
        "start_utc": EXPECTED_START_UTC,
        "end_utc_exclusive": EXPECTED_END_UTC_EXCLUSIVE,
        "calendar_days": 273,
    } or days != 273:
        raise PreflightViolation("reserved window changed")

    source_pins = config.get("source_pins")
    if not isinstance(source_pins, list):
        raise PreflightViolation("source pin inventory changed")
    actual_source_paths = {
        str(row.get("role") or ""): str(row.get("path") or "")
        for row in source_pins
        if isinstance(row, Mapping)
    }
    if (
        len(source_pins) != len(EXPECTED_SOURCE_PIN_PATHS)
        or actual_source_paths != EXPECTED_SOURCE_PIN_PATHS
    ):
        raise PreflightViolation("source pin inventory changed")

    candidate = config.get("candidate_manifest")
    threshold = config.get("threshold_source")
    if not isinstance(candidate, Mapping) or candidate.get("path") != EXPECTED_CANDIDATE_PATH:
        raise PreflightViolation("candidate manifest path changed")
    if not isinstance(threshold, Mapping) or threshold.get("path") != EXPECTED_THRESHOLD_PATH:
        raise PreflightViolation("threshold source path changed")

    future = config.get("future_one_shot")
    if not isinstance(future, Mapping):
        raise PreflightViolation("future_one_shot missing")
    if any(
        future.get(key) is not True
        for key in (
            "atomic_claim_before_market_decode",
            "refuse_second_attempt",
            "owner_authorization_required",
        )
    ):
        raise PreflightViolation("one-shot safety contract changed")
    if future.get("runner_path") != EXPECTED_RUNNER_PATH:
        raise PreflightViolation("one-shot runner path changed")
    if future.get("audit_path") != EXPECTED_AUDIT_PATH:
        raise PreflightViolation("one-shot audit path changed")

    data_contract = config.get("reserved_data_contract")
    if not isinstance(data_contract, Mapping):
        raise PreflightViolation("reserved data contract missing")
    manifest_row = data_contract.get("reserved_m5_input_manifest")
    if manifest_row is not None:
        if not isinstance(manifest_row, Mapping):
            raise PreflightViolation("reserved M5 manifest row invalid")
        if manifest_row.get("path") != EXPECTED_RESERVED_M5_MANIFEST_PATH:
            raise PreflightViolation("reserved M5 manifest path changed")


def _validate_reserved_m5_manifest(
    root: Path,
    row: Mapping[str, Any],
    *,
    expected_universe: list[str],
) -> dict[str, Any]:
    """Validate metadata identity without opening any referenced market file."""

    verified = _verify_pin(root, row)
    manifest = _read_json(_repo_file(root, row.get("path")))
    exact = {
        "schema_id": "att1_sbr1_reserved_m5_input_manifest_v1",
        "authority": "identity_only_materialized_without_scoring_no_live_no_broker",
        "market_rows_decoded_by_preflight": 0,
        "performance_computed": False,
        "money_authority": False,
    }
    if any(manifest.get(key) != value for key, value in exact.items()):
        raise PreflightViolation("reserved M5 manifest authority changed")
    if manifest.get("window") != {
        "start_utc": EXPECTED_START_UTC,
        "end_utc_exclusive": EXPECTED_END_UTC_EXCLUSIVE,
    }:
        raise PreflightViolation("reserved M5 manifest window changed")
    if manifest.get("timeframe_minutes") != 5:
        raise PreflightViolation("reserved M5 manifest timeframe changed")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != len(expected_universe):
        raise PreflightViolation("reserved M5 manifest input inventory changed")
    seen: list[str] = []
    for item in inputs:
        if not isinstance(item, Mapping):
            raise PreflightViolation("reserved M5 manifest input row invalid")
        if set(item) != {
            "symbol",
            "source_path",
            "sha256",
            "bytes",
            "rows",
            "first_ts_ms",
            "last_ts_ms",
        }:
            raise PreflightViolation("reserved M5 manifest input schema changed")
        symbol = str(item.get("symbol") or "")
        source_path = Path(str(item.get("source_path") or ""))
        digest = str(item.get("sha256") or "")
        if (
            not symbol
            or source_path.is_absolute()
            or ".." in source_path.parts
            or ".git" in source_path.parts
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or int(item.get("bytes") or 0) <= 0
            or int(item.get("rows") or 0) <= 0
        ):
            raise PreflightViolation("reserved M5 manifest input identity invalid")
        seen.append(symbol)
    if seen != expected_universe:
        raise PreflightViolation("reserved M5 manifest universe changed")
    return {**verified, "schema_id": manifest["schema_id"], "inputs": len(inputs)}


def _thresholds(receipt: Mapping[str, Any]) -> dict[str, Any]:
    sleeves = receipt.get("sleeves")
    if not isinstance(sleeves, Mapping):
        raise PreflightViolation("threshold receipt sleeves missing")
    out: dict[str, Any] = {}
    for leg in ("ATT1", "SBR1"):
        sleeve = sleeves.get(leg)
        if not isinstance(sleeve, Mapping):
            raise PreflightViolation(f"threshold receipt missing {leg}")
        gate = sleeve.get("zero_risk_shadow_gate")
        if not isinstance(gate, Mapping) or not isinstance(gate.get("thresholds"), Mapping):
            raise PreflightViolation(f"threshold gate missing {leg}")
        out[leg] = dict(gate["thresholds"])
    return out


def build_preflight(root: Path, config_path: Path) -> dict[str, Any]:
    """Build a receipt without touching any reserved market-data path."""

    root = root.resolve()
    config = _read_json(config_path)
    _validate_config(config)

    verified_sources = []
    pins_by_role: dict[str, Mapping[str, Any]] = {}
    source_pins = config.get("source_pins")
    if not isinstance(source_pins, list) or not source_pins:
        raise PreflightViolation("source_pins missing")
    for raw in source_pins:
        if not isinstance(raw, Mapping):
            raise PreflightViolation("invalid source pin")
        role = str(raw.get("role") or "")
        if not role or role in pins_by_role:
            raise PreflightViolation("missing or duplicate source pin role")
        pins_by_role[role] = raw
        verified_sources.append({"role": role, **_verify_pin(root, raw)})

    known_accesses = config.get("known_accesses")
    if not isinstance(known_accesses, list) or len(known_accesses) < 2:
        raise PreflightViolation("known access ledger is incomplete")
    verified_accesses = []
    for access in known_accesses:
        if not isinstance(access, Mapping) or not access.get("id"):
            raise PreflightViolation("invalid known access row")
        evidence = access.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise PreflightViolation("known access evidence missing")
        verified_accesses.append(
            {
                "id": str(access["id"]),
                "window_intersection": str(access.get("window_intersection") or ""),
                "effect": str(access.get("effect") or ""),
                "evidence": [_verify_pin(root, row) for row in evidence],
            }
        )

    candidate_row = config.get("candidate_manifest")
    if not isinstance(candidate_row, Mapping):
        raise PreflightViolation("candidate manifest missing")
    _verify_pin(root, candidate_row)
    candidate = _read_json(_repo_file(root, candidate_row.get("path")))
    if candidate.get("default_off") is not True or candidate.get("money_authority") is not False:
        raise PreflightViolation("candidate authority widened")
    if candidate.get("sealed_holdout_guard") != {
        "start_utc": EXPECTED_START_UTC,
        "end_utc_exclusive": EXPECTED_END_UTC_EXCLUSIVE,
        "must_not_read": True,
    }:
        raise PreflightViolation("candidate reserved guard changed")

    threshold_row = config.get("threshold_source")
    if not isinstance(threshold_row, Mapping):
        raise PreflightViolation("threshold source missing")
    _verify_pin(root, threshold_row)
    threshold_receipt = _read_json(_repo_file(root, threshold_row.get("path")))

    data_contract = config.get("reserved_data_contract")
    future = config.get("future_one_shot")
    if not isinstance(data_contract, Mapping) or not isinstance(future, Mapping):
        raise PreflightViolation("data or one-shot contract missing")
    if data_contract.get("preflight_may_open_or_hash_market_files") is not False:
        raise PreflightViolation("preflight market access must remain forbidden")

    blockers: list[str] = []
    reserved_manifest_row = data_contract.get("reserved_m5_input_manifest")
    verified_reserved_manifest = None
    if reserved_manifest_row is None:
        blockers.append("RESERVED_M5_INPUT_MANIFEST_MISSING")
    elif not isinstance(reserved_manifest_row, Mapping):
        raise PreflightViolation("reserved M5 manifest row invalid")
    else:
        verified_reserved_manifest = _validate_reserved_m5_manifest(
            root,
            reserved_manifest_row,
            expected_universe=list(candidate.get("universe") or []),
        )
    for path_key, hash_key, code in (
        ("runner_path", "runner_sha256", "ONE_SHOT_RUNNER_NOT_FROZEN"),
        ("audit_path", "audit_sha256", "INDEPENDENT_AUDIT_NOT_FROZEN"),
    ):
        raw_path = str(future.get(path_key) or "")
        expected_hash = str(future.get(hash_key) or "")
        if not raw_path or len(expected_hash) != 64:
            blockers.append(code)
        else:
            _verify_pin(root, {"path": raw_path, "sha256": expected_hash})

    legacy = config.get("legacy_contracts")
    if not isinstance(legacy, list) or len(legacy) != 2:
        raise PreflightViolation("legacy contract inventory missing")
    for row in legacy:
        if not isinstance(row, Mapping) or row.get("release_authority_for_this_candidate") is not False:
            raise PreflightViolation("legacy contract authority changed")
        _verify_pin(root, row)

    receipt = {
        "schema_id": "att1_sbr1_reserved_oos_preflight_receipt_v1",
        "generated_at_utc": _utc_now(),
        "decision": "READY_FOR_OWNER_AUTHORIZATION" if not blockers else "BLOCKED_FAIL_CLOSED",
        "classification": EXPECTED_CLASSIFICATION,
        "purity": "KNOWN_CONTAMINATED",
        "authority": config["authority"],
        "preflight_implementation": {
            "path": "scripts/preflight_att1_sbr1_reserved_oos_v1.py",
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "reserved_window": dict(config["reserved_window"]),
        "known_accesses": verified_accesses,
        "frozen_candidate": {
            "contract_label": candidate_row.get("contract_label"),
            "manifest_path": candidate_row.get("path"),
            "manifest_sha256": candidate_row.get("sha256"),
            "universe": list(candidate.get("universe") or []),
            "profiles": dict(candidate.get("profiles") or {}),
            "regime_contract": dict(candidate.get("regime_contract") or {}),
            "execution_contract": dict(candidate.get("execution_contract") or {}),
            "cost_contracts": dict(candidate.get("cost_contracts") or {}),
            "decision_thresholds": _thresholds(threshold_receipt),
            "decision_contract": dict(config.get("decision_contract") or {}),
        },
        "legacy_contracts": legacy,
        "legacy_contracts_are_not_release_authority": True,
        "reserved_data_contract": dict(data_contract),
        "verified_reserved_m5_manifest": verified_reserved_manifest,
        "verified_source_pins": verified_sources,
        "blockers": blockers,
        "one_shot_command_ready": not blockers,
        "reserved_market_files_opened": 0,
        "reserved_market_rows_decoded": 0,
        "performance_computed": False,
        "live_or_broker_calls": False,
        "orders_created_or_changed": 0,
        "money_authority": False,
        "promotion_authority": False,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    receipt = build_preflight(ROOT, args.config)
    _atomic_write_json(args.output, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if receipt["decision"] == "READY_FOR_OWNER_AUTHORIZATION" else 2


if __name__ == "__main__":
    sys.exit(main())
