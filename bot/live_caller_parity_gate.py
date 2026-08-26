"""Fail-closed validators for LIVE_CALLER_PARITY evidence and config gates.

This module is deliberately a pure file/config boundary.  It never imports a
broker client, reads secrets, decodes sealed rows, or grants execution
authority.  P4 binds the two zero-risk fixed-51 shadows to one immutable
evidence contract.  P5 compares a caller-shaped effective configuration with
that contract and returns machine-readable drift codes.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path
from typing import Mapping, Sequence

from bot.att1_fixed51_shadow import ATT1_FIXED51_UNIVERSE
from bot.sbr1_universe import FIXED51_UNIVERSE, MAJOR8_MONEY_UNIVERSE


P4_SCHEMA_ID = "att1_sbr1_fixed51_evidence_parity_manifest_v1"
P5_SCHEMA_ID = "live_caller_effective_config_contract_v1"
P4_AUTHORITY = "research_only_fixed51_evidence_no_orders_no_private_api_no_money_no_promotion"
UNAVAILABLE = {"HFTUSDT": "bybit_linear_status_closed_observed_2026-08-24"}
FIXED51 = tuple(FIXED51_UNIVERSE)
MAJOR8 = tuple(MAJOR8_MONEY_UNIVERSE)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class ParityGateViolation(ValueError):
    """Stable validation code; callers must fail closed on this exception."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ParityGateViolation("noncanonical_manifest") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise ParityGateViolation(f"artifact_unreadable:{path.as_posix()}") from exc


def _sha_field(value: object, field: str) -> str:
    text = str(value or "").strip()
    if SHA_RE.fullmatch(text) is None:
        raise ParityGateViolation(f"invalid_sha256:{field}")
    return text


def _relative(value: object, field: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("../") or "/../" in text:
        raise ParityGateViolation(f"unsafe_path:{field}")
    return text


def _load_json(root: Path, path_value: object, field: str) -> tuple[Path, dict[str, object]]:
    rel = _relative(path_value, field)
    path = root / rel
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParityGateViolation(f"artifact_json_unreadable:{field}") from exc
    if not isinstance(value, dict):
        raise ParityGateViolation(f"artifact_json_not_object:{field}")
    return path, value


def _exact_universe(value: object, expected: tuple[str, ...], field: str) -> None:
    if not isinstance(value, list) or tuple(str(item).strip().upper() for item in value) != expected:
        raise ParityGateViolation(f"{field}_identity_mismatch")


def _authority_flags(raw: Mapping[str, object], *, prefix: str) -> None:
    if raw.get("authority") != P4_AUTHORITY:
        raise ParityGateViolation(f"{prefix}_authority_mismatch")
    required_false = ("money_authority", "orders_allowed", "private_api_allowed", "release_or_promotion_authority", "sealed_data_allowed")
    for field in required_false:
        if raw.get(field) is not False:
            raise ParityGateViolation(f"{prefix}_unsafe_authority:{field}")


def _verify_attached_shadow(root: Path, row: Mapping[str, object], sleeve: str) -> dict[str, object]:
    if not isinstance(row, Mapping):
        raise ParityGateViolation(f"{sleeve}_shadow_artifact_invalid")
    manifest_path, shadow = _load_json(root, row.get("manifest_path"), f"{sleeve}_manifest_path")
    config_path, config = _load_json(root, row.get("config_path"), f"{sleeve}_config_path")
    expected_manifest_sha = _sha_field(row.get("manifest_sha256"), f"{sleeve}_manifest_sha256")
    expected_config_sha = _sha_field(row.get("config_sha256"), f"{sleeve}_config_sha256")
    if sha256_file(manifest_path) != expected_manifest_sha:
        raise ParityGateViolation(f"{sleeve}_manifest_file_hash_mismatch")
    if sha256_file(config_path) != expected_config_sha:
        raise ParityGateViolation(f"{sleeve}_config_file_hash_mismatch")
    if sleeve == "ATT1":
        if shadow.get("schema_id") != "att1_fixed51_public_shadow_manifest_v1":
            raise ParityGateViolation("ATT1_shadow_schema_mismatch")
        if shadow.get("authority") != "zero_risk_public_att1_fixed51_evidence_no_orders_no_money_no_promotion":
            raise ParityGateViolation("ATT1_shadow_authority_mismatch")
        if shadow.get("evidence_universe") != list(FIXED51):
            raise ParityGateViolation("ATT1_shadow_universe_mismatch")
        if config.get("schema_id") != "att1_fixed51_zero_risk_shadow_config_v1":
            raise ParityGateViolation("ATT1_config_schema_mismatch")
        if config.get("evidence_universe") != list(FIXED51) or config.get("money_universe") != list(MAJOR8):
            raise ParityGateViolation("ATT1_config_universe_mismatch")
    else:
        if shadow.get("schema_id") != "sbr1_fixed51_evidence_manifest_v1":
            raise ParityGateViolation("SBR1_shadow_schema_mismatch")
        if shadow.get("authority") != "research_only_no_orders_no_private_api_no_money_no_promotion":
            raise ParityGateViolation("SBR1_shadow_authority_mismatch")
        if shadow.get("universe") != list(FIXED51) or shadow.get("money_universe") != list(MAJOR8):
            raise ParityGateViolation("SBR1_shadow_universe_mismatch")
        if config.get("schema_id") != "sbr1_zero_risk_shadow_config_v1":
            raise ParityGateViolation("SBR1_config_schema_mismatch")
        if config.get("evidence_universe") != list(FIXED51) or config.get("money_universe") != list(MAJOR8):
            raise ParityGateViolation("SBR1_config_universe_mismatch")
    return {"manifest_sha256": expected_manifest_sha, "config_sha256": expected_config_sha}


def verify_fixed51_evidence_manifest(root: Path, manifest_path: Path, *, verify_attached: bool = True) -> dict[str, object]:
    """Validate P4's separate evidence universe and shadow artifact bindings."""
    root = root.resolve()
    path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParityGateViolation("p4_manifest_unreadable") from exc
    if not isinstance(raw, dict) or raw.get("schema_id") != P4_SCHEMA_ID:
        raise ParityGateViolation("p4_manifest_schema_mismatch")
    _authority_flags(raw, prefix="p4")
    if raw.get("default_off") is not True or raw.get("enabled") is not False:
        raise ParityGateViolation("p4_manifest_not_default_off")
    _exact_universe(raw.get("evidence_universe"), FIXED51, "p4_evidence_universe")
    _exact_universe(raw.get("money_universe"), MAJOR8, "p4_money_universe")
    if raw.get("evidence_universe_sha256") != sha256_bytes(_canonical(list(FIXED51))):
        raise ParityGateViolation("p4_evidence_universe_hash_mismatch")
    if raw.get("money_universe_sha256") != sha256_bytes(_canonical(list(MAJOR8))):
        raise ParityGateViolation("p4_money_universe_hash_mismatch")
    if raw.get("expected_structurally_unavailable") != UNAVAILABLE:
        raise ParityGateViolation("p4_unavailable_symbol_contract_mismatch")
    coverage = raw.get("coverage_contract")
    if not isinstance(coverage, dict):
        raise ParityGateViolation("p4_coverage_contract_missing")
    if coverage.get("expected_symbol_count") != 51 or coverage.get("expected_available_symbol_count") != 50:
        raise ParityGateViolation("p4_coverage_count_mismatch")
    if coverage.get("substitution_allowed") is not False or coverage.get("private_api_allowed") is not False or coverage.get("orders_allowed") is not False:
        raise ParityGateViolation("p4_coverage_authority_mismatch")
    if coverage.get("structurally_unavailable") != UNAVAILABLE:
        raise ParityGateViolation("p4_coverage_unavailable_mismatch")
    attached = raw.get("shadows")
    if not isinstance(attached, dict) or set(attached) != {"ATT1", "SBR1"}:
        raise ParityGateViolation("p4_shadow_bindings_missing")
    if verify_attached:
        details = {sleeve: _verify_attached_shadow(root, attached[sleeve], sleeve) for sleeve in ("ATT1", "SBR1")}
    else:
        details = {}
    if attached["ATT1"].get("journal_path") == attached["SBR1"].get("journal_path"):
        raise ParityGateViolation("p4_shadow_journals_not_separate")
    return {
        "schema_id": P4_SCHEMA_ID,
        "decision": "PASS",
        "authority": P4_AUTHORITY,
        "evidence_universe": list(FIXED51),
        "money_universe": list(MAJOR8),
        "expected_structurally_unavailable": dict(UNAVAILABLE),
        "attached": details,
        "manifest_sha256": sha256_file(path),
        "sealed_holdout_rows_decoded": 0,
    }


def _latest_runtime_cycle(
    events: Sequence[Mapping[str, object]], *, sleeve: str
) -> tuple[int, list[Mapping[str, object]]]:
    if isinstance(events, (str, bytes)) or not events:
        raise ParityGateViolation(f"{sleeve}_runtime_journal_empty")
    normalized: list[tuple[int, Mapping[str, object]]] = []
    eligible_types = (
        {"raw_decision", "expected_symbol_unavailable"}
        if sleeve == "ATT1"
        else {"evaluation", "evaluation_unavailable"}
    )
    for event in events:
        if not isinstance(event, Mapping):
            raise ParityGateViolation(f"{sleeve}_runtime_event_invalid")
        if str(event.get("event_type") or "") not in eligible_types:
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            raise ParityGateViolation(f"{sleeve}_runtime_payload_invalid")
        close_raw = payload.get("closed_h1_ts_ms")
        if isinstance(close_raw, bool):
            raise ParityGateViolation(f"{sleeve}_runtime_close_invalid")
        try:
            close_ts = int(str(close_raw))
        except (TypeError, ValueError) as exc:
            raise ParityGateViolation(f"{sleeve}_runtime_close_invalid") from exc
        if close_ts <= 0 or close_ts % 3_600_000 != 0:
            raise ParityGateViolation(f"{sleeve}_runtime_close_invalid")
        normalized.append((close_ts, event))
    if not normalized:
        raise ParityGateViolation(f"{sleeve}_runtime_journal_no_evaluations")
    latest = max(close for close, _event in normalized)
    return latest, [event for close, event in normalized if close == latest]


def _runtime_payload(event: Mapping[str, object], *, sleeve: str) -> Mapping[str, object]:
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        raise ParityGateViolation(f"{sleeve}_runtime_payload_invalid")
    for field in ("money_authority", "orders_allowed"):
        if payload.get(field) is not False:
            raise ParityGateViolation(f"{sleeve}_runtime_unsafe_authority:{field}")
    for optional in (
        "private_api_allowed",
        "release_or_promotion_authority",
        "sealed_data_allowed",
    ):
        if optional in payload and payload.get(optional) is not False:
            raise ParityGateViolation(
                f"{sleeve}_runtime_unsafe_authority:{optional}"
            )
    return payload


def load_verified_runtime_journal(
    path: Path, *, sleeve: str
) -> list[dict[str, object]]:
    """Read and independently verify one deployed shadow hash chain."""

    sleeve = str(sleeve or "").strip().upper()
    if sleeve not in {"ATT1", "SBR1"}:
        raise ParityGateViolation("runtime_journal_sleeve_invalid")
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise ParityGateViolation(f"{sleeve}_runtime_journal_not_regular")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise ParityGateViolation(f"{sleeve}_runtime_journal_mode_unsafe")
        lines = path.read_text(encoding="ascii").splitlines()
    except ParityGateViolation:
        raise
    except (OSError, UnicodeError) as exc:
        raise ParityGateViolation(f"{sleeve}_runtime_journal_unreadable") from exc
    if not lines:
        raise ParityGateViolation(f"{sleeve}_runtime_journal_empty")
    expected_schema = (
        "att1_fixed51_raw_shadow_event_v2"
        if sleeve == "ATT1"
        else "sbr1_zero_risk_shadow_event_v1"
    )
    previous = "0" * 64
    claims: set[str] = set()
    events: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ParityGateViolation(
                f"{sleeve}_runtime_journal_invalid_json:{line_number}"
            ) from exc
        if not isinstance(event, dict) or event.get("schema_id") != expected_schema:
            raise ParityGateViolation(
                f"{sleeve}_runtime_journal_schema_mismatch:{line_number}"
            )
        common = {
            "schema_id",
            "event_type",
            "claim_key",
            "payload",
            "previous_event_hash",
            "event_id",
            "event_hash",
        }
        required = common | ({"identity_sha256"} if sleeve == "ATT1" else set())
        if set(event) != required or not isinstance(event.get("payload"), dict):
            raise ParityGateViolation(
                f"{sleeve}_runtime_journal_fields_mismatch:{line_number}"
            )
        claim = str(event.get("claim_key") or "").strip()
        event_type = str(event.get("event_type") or "").strip()
        previous_hash = _sha_field(
            event.get("previous_event_hash"), "previous_event_hash"
        )
        event_id = _sha_field(event.get("event_id"), "event_id")
        event_hash = _sha_field(event.get("event_hash"), "event_hash")
        if not claim or not event_type or claim in claims or previous_hash != previous:
            raise ParityGateViolation(
                f"{sleeve}_runtime_journal_chain_broken:{line_number}"
            )
        if sleeve == "ATT1":
            identity = _sha_field(event.get("identity_sha256"), "identity_sha256")
            body = {
                "schema_id": expected_schema,
                "event_type": event_type,
                "claim_key": claim,
                "identity_sha256": identity,
                "payload": event["payload"],
                "previous_event_hash": previous,
            }
        else:
            body = {
                "claim_key": claim,
                "event_type": event_type,
                "payload": event["payload"],
            }
        if event_id != sha256_bytes(_canonical(body)):
            raise ParityGateViolation(
                f"{sleeve}_runtime_journal_event_id_mismatch:{line_number}"
            )
        expected_hash = sha256_bytes(
            _canonical({"event_id": event_id, "previous_event_hash": previous})
        )
        if event_hash != expected_hash:
            raise ParityGateViolation(
                f"{sleeve}_runtime_journal_event_hash_mismatch:{line_number}"
            )
        claims.add(claim)
        previous = event_hash
        events.append(event)
    return events


def verify_fixed51_runtime_cycles(
    att1_events: Sequence[Mapping[str, object]],
    sbr1_events: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Validate latest hash-chain-decoded zero-risk cycles for P4.

    The journal-specific readers remain responsible for verifying each chain.
    This pure boundary then proves exact causal-cycle coverage and authority.
    SBR1 may contain the three major-8 money-only symbols that are outside the
    immutable fixed-51 evidence universe; they are reported separately and do
    not enlarge evidence N.
    """

    att1_close, att1_cycle = _latest_runtime_cycle(att1_events, sleeve="ATT1")
    sbr1_close, sbr1_cycle = _latest_runtime_cycle(sbr1_events, sleeve="SBR1")
    if att1_close != sbr1_close:
        raise ParityGateViolation("runtime_cycle_clock_mismatch")

    expected_sbr_cycle = tuple(dict.fromkeys((*FIXED51, *MAJOR8)))
    summaries: dict[str, dict[str, object]] = {}
    for sleeve, cycle, expected in (
        ("ATT1", att1_cycle, FIXED51),
        ("SBR1", sbr1_cycle, expected_sbr_cycle),
    ):
        seen: dict[str, Mapping[str, object]] = {}
        for event in cycle:
            payload = _runtime_payload(event, sleeve=sleeve)
            symbol = str(payload.get("symbol") or "").strip().upper()
            if not symbol or symbol in seen:
                raise ParityGateViolation(f"{sleeve}_runtime_symbol_invalid")
            seen[symbol] = payload
        if set(seen) != set(expected):
            raise ParityGateViolation(f"{sleeve}_latest_cycle_universe_mismatch")
        hft = seen.get("HFTUSDT")
        if hft is None or hft.get("status") not in {
            "RAW_DECISION_SHADOW_EXPECTED_UNAVAILABLE",
            "expected_structural_gap",
        }:
            raise ParityGateViolation(f"{sleeve}_HFT_structural_gap_missing")
        summaries[sleeve] = {
            "cycle_symbol_count": len(seen),
            "fixed51_evidence_symbol_count": len(set(seen) & set(FIXED51)),
            "money_only_extra_symbols": sorted(set(seen) - set(FIXED51)),
            "expected_structurally_unavailable": ["HFTUSDT"],
        }
    receipt: dict[str, object] = {
        "schema_id": "att1_sbr1_fixed51_runtime_coverage_receipt_v1",
        "decision": "PASS",
        "authority": P4_AUTHORITY,
        "closed_h1_ts_ms": att1_close,
        "ATT1": summaries["ATT1"],
        "SBR1": summaries["SBR1"],
        "money_authority": False,
        "orders_created_or_changed": 0,
        "private_api_calls": False,
        "sealed_holdout_rows_decoded": 0,
    }
    receipt["receipt_sha256"] = sha256_bytes(_canonical(receipt))
    return receipt


def _env_mapping(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ParityGateViolation("effective_config_unreadable") from exc
    result: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and re.fullmatch(r"[A-Z][A-Z0-9_]+", key):
            result[key] = value.strip().strip("\"'")
    return result


def verify_live_config(root: Path, manifest_path: Path, actual: Mapping[str, object], *, verify_attached: bool = True) -> dict[str, object]:
    """Compare an effective, secret-free caller config with the P5 contract.

    The function returns a receipt even on mismatch so a CLI can persist it;
    no mismatch is silently coerced into a pass.  It intentionally does not
    read process environment variables or any broker credentials.
    """
    root = root.resolve()
    try:
        p4 = verify_fixed51_evidence_manifest(root, manifest_path, verify_attached=verify_attached)
    except ParityGateViolation as exc:
        return {"schema_id": P5_SCHEMA_ID, "decision": "BLOCKED", "fail_codes": [str(exc)], "p4": {"decision": "BLOCKED"}, "sealed_holdout_rows_decoded": 0}
    p4_raw_path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    try:
        raw = json.loads(p4_raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_id": P5_SCHEMA_ID, "decision": "BLOCKED", "fail_codes": ["p4_manifest_unreadable"], "sealed_holdout_rows_decoded": 0}
    contract = raw.get("effective_config_contract")
    if not isinstance(contract, dict):
        return {"schema_id": P5_SCHEMA_ID, "decision": "FAIL", "fail_codes": ["effective_config_contract_missing"], "p4": p4, "sealed_holdout_rows_decoded": 0}
    failures: list[str] = []
    for key, expected in contract.items():
        if key.startswith("__"):
            continue
        if key not in actual:
            failures.append(f"effective_config_missing:{key}")
        elif str(actual[key]).strip() != str(expected).strip():
            failures.append(f"effective_config_mismatch:{key}:expected={expected}:actual={actual[key]}")
    return {
        "schema_id": P5_SCHEMA_ID,
        "decision": "PASS" if not failures else "FAIL",
        "fail_codes": failures,
        "p4": p4,
        "effective_config_contract_sha256": sha256_bytes(_canonical(contract)),
        "sealed_holdout_rows_decoded": 0,
        "authority": P4_AUTHORITY,
    }


def load_env_mapping(path: Path) -> dict[str, str]:
    """Public secret-free env parser for the verify CLI and tests."""
    return _env_mapping(path)


__all__ = [
    "FIXED51", "MAJOR8", "P4_AUTHORITY", "P4_SCHEMA_ID", "P5_SCHEMA_ID",
    "ParityGateViolation", "load_env_mapping", "load_verified_runtime_journal", "sha256_file", "verify_fixed51_evidence_manifest", "verify_fixed51_runtime_cycles", "verify_live_config",
]
