#!/usr/bin/env python3
"""Independent, fail-closed audit for the ATT1/SBR1 reserved OOS diagnostic.

The pre-execution path is metadata-only: it deliberately does not resolve or
open any ``source_path`` named by the reserved M5 manifest.  The post-execution
path is a separate evidence reader; it never imports the one-shot runner or
uses a runner-computed decision as its own verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
CONFIG_REL = Path("configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json")
MANIFEST_REL = Path("configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json")
RUNNER_REL = Path("scripts/run_att1_sbr1_reserved_oos_v1.py")
AUDIT_REL = Path("scripts/audit_att1_sbr1_reserved_oos_v1.py")
AUTHORIZATION_REL = Path("configs/research/att1_sbr1_reserved_oos_owner_authorization_v1.json")
OUTPUT_REL = Path("research_lab/results/att1_sbr1_reserved_oos_v1")
CLAIM_REL = OUTPUT_REL / "one_shot_claim.json"
RECEIPT_REL = OUTPUT_REL / "receipt.json"
START_UTC = "2025-10-01T00:00:00Z"
END_UTC = "2026-07-01T00:00:00Z"
MAJOR8 = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT")
EXPECTED_SOURCE_PINS = {
    "live_native_candidate": "configs/research/att1_sbr1_live_native_parity_v1.json",
    "fixed51_evidence_contract": "configs/research/att1_sbr1_fixed51_evidence_parity_v1.json",
    "presealed_thresholds": "research_lab/results/att1_sbr1_presealed_economics_diagnostic_20260823/receipt.json",
    "live_caller_parity_receipt": "reports/receipts/LIVE_CALLER_PARITY_FINAL_VERIFICATION_2026_08_26.json",
    "legacy_att1_prereg": "research_lab/prereg/PREREG_FLAT_DOWN_2026_08_18.md",
    "legacy_sbr1_prereg": "research_lab/prereg/PREREG_FLAT_UP_2026_08_19.md",
}
AUTHORITY = "metadata_only_no_reserved_market_decode_no_live_no_broker_no_money_no_promotion"
RESULT_AUTHORITY = "research_only_reserved_diagnostic_no_live_no_broker_no_money_no_promotion"


class AuditViolation(RuntimeError):
    """Independent evidence validation failed closed."""


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def verify_audit_receipt(receipt: Mapping[str, Any]) -> None:
    """Verify the auditor's canonical receipt without trusting its decision."""
    unsigned = dict(receipt)
    actual = str(unsigned.pop("audit_receipt_sha256", ""))
    if actual != canonical_sha256(unsigned):
        raise AuditViolation("audit receipt self hash drift")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_file(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", "..", ".git"} for part in relative.parts):
        raise AuditViolation(f"unsafe path:{relative}")
    current = root.resolve()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise AuditViolation(f"symlink path:{relative}")
    if not current.is_file():
        raise AuditViolation(f"missing regular file:{relative}")
    return current


def _read_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise AuditViolation(f"{label} missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditViolation(f"{label} malformed") from exc
    if not isinstance(value, dict):
        raise AuditViolation(f"{label} must be an object")
    return value


def _pin(root: Path, row: Mapping[str, object], expected: Path) -> tuple[Path, str]:
    if Path(str(row.get("path") or "")) != expected:
        raise AuditViolation(f"pinned path drift:{expected}")
    path = _safe_file(root, expected)
    actual, wanted = sha256_file(path), str(row.get("sha256") or "")
    if len(wanted) != 64 or actual != wanted:
        raise AuditViolation(f"pinned SHA drift:{expected}")
    return path, actual


def _validate_manifest_metadata(manifest: Mapping[str, Any]) -> None:
    exact = {
        "schema_id": "att1_sbr1_reserved_m5_input_manifest_v1",
        "authority": "identity_only_materialized_without_scoring_no_live_no_broker",
        "market_rows_decoded_by_preflight": 0,
        "performance_computed": False,
        "money_authority": False,
        "window": {"start_utc": START_UTC, "end_utc_exclusive": END_UTC},
        "timeframe_minutes": 5,
    }
    if any(manifest.get(key) != value for key, value in exact.items()):
        raise AuditViolation("reserved manifest metadata drift")
    inputs = manifest.get("inputs")
    required = {"symbol", "source_path", "sha256", "bytes", "rows", "first_ts_ms", "last_ts_ms"}
    if not isinstance(inputs, list) or len(inputs) != len(MAJOR8):
        raise AuditViolation("reserved manifest inventory drift")
    if any(not isinstance(row, Mapping) or set(row) != required for row in inputs):
        raise AuditViolation("reserved manifest schema drift")
    if [str(row["symbol"]) for row in inputs] != list(MAJOR8):
        raise AuditViolation("reserved manifest universe drift")
    for row in inputs:
        source = Path(str(row["source_path"]))
        digest = str(row["sha256"])
        if source.is_absolute() or any(part in {"", ".", "..", ".git"} for part in source.parts) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise AuditViolation("reserved manifest input identity drift")
        if int(row["bytes"]) <= 0 or int(row["rows"]) != 273 * 288 or int(row["first_ts_ms"]) != 1_759_276_800_000 or int(row["last_ts_ms"]) != 1_782_864_000_000 - 300_000:
            raise AuditViolation("reserved manifest input counts drift")


def _validate_config(root: Path, config: Mapping[str, Any]) -> tuple[Path, Path, Path, Path]:
    frozen = dict(config)
    fingerprint = str(frozen.pop("config_fingerprint_sha256", ""))
    if fingerprint != canonical_sha256(frozen):
        raise AuditViolation("config fingerprint drift")
    if config.get("authority") != AUTHORITY or config.get("classification") != "RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION":
        raise AuditViolation("diagnostic authority or classification drift")
    if any(config.get(key) is not value for key, value in {"default_off": True, "money_authority": False, "orders_allowed": False, "private_api_allowed": False, "performance_allowed": False}.items()):
        raise AuditViolation("diagnostic authority widened")
    if config.get("reserved_window") != {"start_utc": START_UTC, "end_utc_exclusive": END_UTC, "calendar_days": 273}:
        raise AuditViolation("reserved window drift")
    candidate = config.get("candidate_manifest")
    if not isinstance(candidate, Mapping):
        raise AuditViolation("candidate pin missing")
    _pin(root, candidate, Path("configs/research/att1_sbr1_live_native_parity_v1.json"))
    source_pins = config.get("source_pins")
    if not isinstance(source_pins, list) or not source_pins:
        raise AuditViolation("source pins missing")
    actual_source_pins = {str(row.get("role") or ""): str(row.get("path") or "") for row in source_pins if isinstance(row, Mapping)}
    if actual_source_pins != EXPECTED_SOURCE_PINS or len(source_pins) != len(EXPECTED_SOURCE_PINS):
        raise AuditViolation("source pin inventory drift")
    for row in source_pins:
        if not isinstance(row, Mapping):
            raise AuditViolation("source pin malformed")
        path = Path(str(row.get("path") or ""))
        _pin(root, row, path)
    data = config.get("reserved_data_contract")
    if not isinstance(data, Mapping) or data.get("preflight_may_open_or_hash_market_files") is not False:
        raise AuditViolation("reserved data contract drift")
    manifest_row = data.get("reserved_m5_input_manifest")
    if not isinstance(manifest_row, Mapping):
        raise AuditViolation("reserved manifest pin missing")
    manifest_path, _ = _pin(root, manifest_row, MANIFEST_REL)
    _validate_manifest_metadata(_read_object(manifest_path, "reserved manifest"))
    future = config.get("future_one_shot")
    if not isinstance(future, Mapping) or any(future.get(key) is not True for key in ("atomic_claim_before_market_decode", "refuse_second_attempt", "owner_authorization_required")):
        raise AuditViolation("one-shot contract drift")
    runner_path, _ = _pin(root, future, RUNNER_REL) if False else _pin(root, {"path": future.get("runner_path"), "sha256": future.get("runner_sha256")}, RUNNER_REL)
    audit_path, _ = _pin(root, {"path": future.get("audit_path"), "sha256": future.get("audit_sha256")}, AUDIT_REL)
    config_path = _safe_file(root, CONFIG_REL)
    return config_path, manifest_path, runner_path, audit_path


def _preexisting(root: Path, relative: Path) -> bool:
    path = root / relative
    return path.exists() or path.is_symlink()


def build_preexecution_audit(root: Path = ROOT, *, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Freeze all metadata before authorization without opening market inputs."""
    root = root.resolve()
    if _preexisting(root, AUTHORIZATION_REL):
        raise AuditViolation("owner authorization already present")
    if _preexisting(root, CLAIM_REL):
        raise AuditViolation("one-shot claim already present")
    if _preexisting(root, RECEIPT_REL) or _preexisting(root, OUTPUT_REL):
        raise AuditViolation("one-shot result already present")
    config_value = dict(config) if config is not None else _read_object(_safe_file(root, CONFIG_REL), "diagnostic config")
    config_path, manifest_path, runner_path, audit_path = _validate_config(root, config_value)
    receipt: dict[str, Any] = {
        "schema_id": "att1_sbr1_reserved_oos_independent_audit_preexecution_v1",
        "generated_at_utc": _utc_now(), "decision": "READY_FOR_OWNER_AUTHORIZATION",
        "authority": AUTHORITY, "classification": config_value["classification"],
        "config_sha256": sha256_file(config_path), "config_fingerprint_sha256": config_value["config_fingerprint_sha256"],
        "input_manifest_sha256": sha256_file(manifest_path), "runner_sha256": sha256_file(runner_path), "audit_sha256": sha256_file(audit_path),
        "owner_authorization_present": False, "claim_present": False, "result_present": False,
        "reserved_market_files_opened": 0, "reserved_market_rows_decoded": 0,
        "performance_computed": False, "live_or_broker_calls": False,
        "orders_created_or_changed": 0, "money_authority": False, "promotion_authority": False,
    }
    receipt["audit_receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def _parse_utc(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditViolation(f"invalid timestamp:{field}") from exc
    if parsed.tzinfo is None:
        raise AuditViolation(f"invalid timestamp:{field}")
    return parsed


def _expected_artifacts() -> set[str]:
    names: set[str] = set()
    for sleeve in ("att1", "sbr1"):
        names.update({f"{sleeve}_evaluation_research.jsonl", f"{sleeve}_evaluation_live.jsonl"})
        for mode in ("base", "stress"):
            names.update({f"{sleeve}_{mode}_research.jsonl", f"{sleeve}_{mode}_live.jsonl", f"{sleeve}_{mode}_parity_report.json"})
    return names


def verify_output_inventory(output: Path, inventory: Mapping[str, object]) -> None:
    """Check the runner's exact immutable artifact inventory and hashes."""
    if set(inventory) != _expected_artifacts():
        raise AuditViolation("output hash inventory drift")
    for name, expected_hash in inventory.items():
        path = output / str(name)
        if path.is_symlink() or not path.is_file() or sha256_file(path) != expected_hash:
            raise AuditViolation(f"output hash drift:{name}")


def verify_claim_timing(claim_created_at_utc: object, market_decode_started_at_utc: object, market_decode_finished_at_utc: object) -> None:
    claim_time = _parse_utc(claim_created_at_utc, "claim_created")
    decode_start = _parse_utc(market_decode_started_at_utc, "decode_start")
    decode_end = _parse_utc(market_decode_finished_at_utc, "decode_end")
    if not claim_time <= decode_start <= decode_end:
        raise AuditViolation("claim receipt timing inversion")


def verify_ledger_parity(research: Mapping[Any, Any], live: Mapping[Any, Any], sleeve: str, mode: str) -> dict[str, Any]:
    """Run the stable comparator; never accept runner-provided parity labels."""
    from research_lab.adapter_parity import compare_ledgers

    parity = compare_ledgers(research, live)
    if parity["decision"] != "PASS":
        raise AuditViolation(f"research/live ledger mismatch:{sleeve}:{mode}")
    return parity


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AuditViolation(f"invalid decimal:{field}") from exc
    if not result.is_finite():
        raise AuditViolation(f"invalid decimal:{field}")
    return result


def threshold_checks(metrics: Mapping[str, object], thresholds: Mapping[str, object]) -> dict[str, bool]:
    return {
        "n_gte": int(metrics["n"]) >= int(thresholds["n_gte"]),
        "mean_r_gt": _decimal(metrics["mean_r"], "mean_r") > _decimal(thresholds["mean_r_gt"], "mean_r_gt"),
        "profit_factor_gte": metrics.get("profit_factor") is not None and _decimal(metrics["profit_factor"], "profit_factor") >= _decimal(thresholds["profit_factor_gte"], "profit_factor_gte"),
        "both_halves_r_gt": all(_decimal(value, "half") > _decimal(thresholds["both_halves_r_gt"], "both_halves_r_gt") for value in metrics["chronological_halves_r"]),
        "max_sequential_drawdown_r_lte": _decimal(metrics["max_sequential_drawdown_r"], "drawdown") <= _decimal(thresholds["max_sequential_drawdown_r_lte"], "drawdown_limit"),
        "positive_month_fraction_gte": _decimal(metrics["positive_month_fraction"], "months") >= _decimal(thresholds["positive_month_fraction_gte"], "month_limit"),
        "positive_symbol_concentration_lte": _decimal(metrics["positive_symbol_concentration"], "concentration") <= _decimal(thresholds["positive_symbol_concentration_lte"], "concentration_limit"),
        "minimum_leave_one_symbol_out_r_gt": _decimal(metrics["minimum_leave_one_symbol_out_r"], "loso") > _decimal(thresholds["minimum_leave_one_symbol_out_r_gt"], "loso_limit"),
    }


def three_way_decision(base: Mapping[str, object], stress: Mapping[str, object], thresholds: Mapping[str, object], *, negative_stress_n: int) -> str:
    if all(threshold_checks(base, thresholds).values()) and all(threshold_checks(stress, thresholds).values()):
        return "PASS_ZERO_RISK_INTEGRATION_ONLY"
    minimum = int(thresholds["n_gte"])
    if (int(base["n"]) >= minimum and int(stress["n"]) >= minimum) or (int(stress["n"]) >= negative_stress_n and _decimal(stress["sum_r"], "sum_r") < 0):
        return "FAIL_CLOSED"
    return "INCONCLUSIVE_LOW_N"


def verify_reported_sleeves(reported: Mapping[str, Any], independent: Mapping[str, Any]) -> None:
    """Require the runner evidence to agree with independently derived facts."""
    for sleeve in ("ATT1", "SBR1"):
        runner_sleeve, audit_sleeve = reported.get(sleeve), independent.get(sleeve)
        if not isinstance(runner_sleeve, Mapping) or not isinstance(audit_sleeve, Mapping):
            raise AuditViolation(f"runner sleeve missing:{sleeve}")
        if runner_sleeve.get("decision") != audit_sleeve.get("decision"):
            raise AuditViolation(f"runner sleeve decision drift:{sleeve}")
        if runner_sleeve.get("checks") != audit_sleeve.get("checks"):
            raise AuditViolation(f"runner sleeve checks drift:{sleeve}")
        runner_modes, audit_modes = runner_sleeve.get("modes"), audit_sleeve.get("modes")
        if not isinstance(runner_modes, Mapping) or not isinstance(audit_modes, Mapping):
            raise AuditViolation(f"runner sleeve modes missing:{sleeve}")
        for mode in ("base", "stress"):
            if not isinstance(runner_modes.get(mode), Mapping) or runner_modes[mode].get("metrics") != audit_modes[mode]["metrics"]:
                raise AuditViolation(f"runner sleeve metrics drift:{sleeve}:{mode}")


def audit_postexecution(root: Path = ROOT) -> dict[str, Any]:
    """Independently audit a completed one-shot receipt and immutable outputs."""
    root = root.resolve()
    config = _read_object(_safe_file(root, CONFIG_REL), "diagnostic config")
    config_path, manifest_path, runner_path, audit_path = _validate_config(root, config)
    authorization_path = _safe_file(root, AUTHORIZATION_REL)
    authorization = _read_object(authorization_path, "owner authorization")
    claim_path = _safe_file(root, CLAIM_REL)
    receipt_path = _safe_file(root, RECEIPT_REL)
    claim, result = _read_object(claim_path, "one-shot claim"), _read_object(receipt_path, "one-shot receipt")
    if claim.get("schema_id") != "att1_sbr1_reserved_oos_one_shot_claim_v1" or claim.get("state") != "CLAIMED_BEFORE_MARKET_DECODE":
        raise AuditViolation("claim schema or state drift")
    if result.get("schema_id") != "att1_sbr1_reserved_oos_one_shot_receipt_v1" or result.get("authority") != RESULT_AUTHORITY:
        raise AuditViolation("receipt schema or authority drift")
    unsigned = dict(result); actual_receipt_sha = str(unsigned.pop("receipt_sha256", ""))
    if actual_receipt_sha != canonical_sha256(unsigned):
        raise AuditViolation("receipt self hash drift")
    identities = {"config_sha256": sha256_file(config_path), "input_manifest_sha256": sha256_file(manifest_path), "runner_sha256": sha256_file(runner_path), "audit_sha256": sha256_file(audit_path), "authorization_sha256": sha256_file(authorization_path)}
    if any(claim.get(key) != value or result.get(key) != value for key, value in identities.items()):
        raise AuditViolation("claim or receipt identity drift")
    if authorization.get("config_sha256") != identities["config_sha256"] or authorization.get("input_manifest_sha256") != identities["input_manifest_sha256"] or authorization.get("runner_sha256") != identities["runner_sha256"] or authorization.get("audit_sha256") != identities["audit_sha256"]:
        raise AuditViolation("authorization identity drift")
    if result.get("claim_sha256") != sha256_file(claim_path):
        raise AuditViolation("receipt claim hash drift")
    verify_claim_timing(claim.get("claim_created_at_utc"), result.get("market_decode_started_at_utc"), result.get("market_decode_finished_at_utc"))
    if result.get("reserved_window") != {"start_utc": START_UTC, "end_utc_exclusive": END_UTC} or result.get("classification") != config["classification"]:
        raise AuditViolation("receipt window or classification drift")
    if any(result.get(key) != value for key, value in {"private_api_calls": 0, "live_or_broker_calls": False, "orders_created_or_changed": 0, "money_authority": False, "promotion_authority": False}.items()):
        raise AuditViolation("receipt authority widened")
    output = root / OUTPUT_REL
    inventory = result.get("output_file_sha256")
    if not isinstance(inventory, Mapping):
        raise AuditViolation("output hash inventory drift")
    verify_output_inventory(output, inventory)
    from research_lab.adapter_parity import read_jsonl
    from research_lab.summarize_att1_sbr1_presealed_economics import chronological_symbol_occupancy, metrics
    threshold_receipt = _read_object(_safe_file(root, Path(str(config["threshold_source"]["path"]))), "threshold receipt")
    thresholds_by_sleeve = {sleeve: threshold_receipt["sleeves"][sleeve]["zero_risk_shadow_gate"]["thresholds"] for sleeve in ("ATT1", "SBR1")}
    independent_sleeves: dict[str, Any] = {}
    for sleeve in ("ATT1", "SBR1"):
        modes: dict[str, Any] = {}
        for mode in ("base", "stress"):
            research = read_jsonl(output / f"{sleeve.lower()}_{mode}_research.jsonl")
            live = read_jsonl(output / f"{sleeve.lower()}_{mode}_live.jsonl")
            parity = verify_ledger_parity(research, live, sleeve, mode)
            accepted = chronological_symbol_occupancy(tuple(live.values()), sleeve)
            modes[mode] = {"raw_signals": len(live), "accepted_signals": len(accepted.rows), "same_symbol_occupancy_drops": accepted.overlap_drops, "metrics": metrics(accepted.rows), "parity": parity}
        thresholds = thresholds_by_sleeve[sleeve]
        decision = three_way_decision(modes["base"]["metrics"], modes["stress"]["metrics"], thresholds, negative_stress_n=int(config["decision_contract"]["negative_stress_sum_r_is_fail_when_n_gte"]))
        independent_sleeves[sleeve] = {"modes": modes, "thresholds": thresholds, "checks": {mode: threshold_checks(modes[mode]["metrics"], thresholds) for mode in ("base", "stress")}, "decision": decision}
    reported_sleeves = result.get("sleeves")
    if not isinstance(reported_sleeves, Mapping):
        raise AuditViolation("runner sleeves missing")
    verify_reported_sleeves(reported_sleeves, independent_sleeves)
    audit: dict[str, Any] = {"schema_id": "att1_sbr1_reserved_oos_independent_audit_receipt_v1", "generated_at_utc": _utc_now(), "decision": "AUDIT_PASS_RESEARCH_ONLY", "authority": RESULT_AUTHORITY, "identities": identities, "claim_sha256": sha256_file(claim_path), "one_shot_receipt_sha256": sha256_file(receipt_path), "sleeves": independent_sleeves, "money_authority": False, "promotion_authority": False}
    audit["audit_receipt_sha256"] = canonical_sha256(audit)
    verify_audit_receipt(audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--post-execution", action="store_true")
    args = parser.parse_args()
    try:
        receipt = audit_postexecution(ROOT) if args.post_execution else build_preexecution_audit(ROOT)
    except AuditViolation as exc:
        print(json.dumps({"decision": "BLOCKED_FAIL_CLOSED", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
