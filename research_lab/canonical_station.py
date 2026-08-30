from __future__ import annotations

import hashlib
import json
import os
import re
import fcntl
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


MANIFEST_SCHEMA_ID = "canonical_research_station_v1"
AUTHORITY = "research_only_no_live_or_promotion"
REQUIRED_FALSE_AUTHORITY = (
    "promotion_authority",
    "network_authority",
    "private_api_authority",
    "order_authority",
    "live_write_authority",
)
_PATH_FIELDS = (
    "evidence_paths",
    "canonical_evidence_files",
    "source_paths",
    "config_paths",
    "input_paths",
    "runtime_requirements",
)
_GLOB_CHARS = frozenset("*?[")
_FORBIDDEN_LAUNCH_ARGUMENTS = ("--live", "--place-order", "--private-api")
_CREDENTIAL_FRAGMENT = re.compile(r"(?:^|[_-])(?:api[_-]?key|secret|token|credential)(?:$|[_=:.-])", re.IGNORECASE)
_SCREEN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}")
_JOB_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,63}")


class MigrationError(RuntimeError):
    pass


class ProcessKind(str, Enum):
    DETERMINISTIC = "deterministic_decision_loop"
    MARKET_SNAPSHOT = "market_snapshot_loop"
    COLLECTOR = "collector_supervisor"


class ParityState(str, Enum):
    PASS = "PASS"
    FAIL_CLOSED = "FAIL_CLOSED"
    NOT_CONFIRMED = "NOT_CONFIRMED"


@dataclass(frozen=True)
class CanonicalJob:
    name: str
    process_kind: ProcessKind
    screen_session: str
    launcher: Sequence[str]
    evidence_paths: Sequence[str]
    canonical_evidence_files: Sequence[str] = ()
    source_paths: Sequence[str] = ()
    config_paths: Sequence[str] = ()
    input_paths: Sequence[str] = ()
    evidence_epoch_env: str = "RESEARCH_STATION_EVIDENCE_EPOCH"


@dataclass(frozen=True)
class ProcessReceipt:
    job_name: str
    screen_name: str
    pid: int | None
    cwd: str | None
    command: str
    process_kind: ProcessKind
    identity: dict[str, str | None]
    counters: dict[str, int]
    timestamps: dict[str, str]
    evidence_paths: Sequence[str]
    evidence_epoch: str | None
    authority: dict[str, Any]
    status: ParityState
    eligible_for_parity: bool = False


@dataclass(frozen=True)
class ParityReceipt:
    state: ParityState
    reason: str
    stop_allowed: bool
    compared_fields: Sequence[str] = ()
    observed_at_utc: str | None = None


def _validate_receipt_authority(receipt: ProcessReceipt) -> None:
    """Reject receipts that do not carry the exact research-only contract."""
    _validate_receipt_shape(receipt)
    expected = {
        "authority": AUTHORITY,
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        # Public reads are the only allowed external-data capability in the
        # current truthful manifest contract.
        "public_data_read_authority": True,
    }
    if (
        receipt.authority.get("authority") != AUTHORITY
        or any(
            receipt.authority.get(key) is not value
            for key, value in expected.items()
            if key != "authority"
        )
    ):
        raise MigrationError("receipt authority drift")
    factual = {
        "public_data_read_authority",
        "research_only",
        "live_order_authority",
        "orders_sent",
        "private_api_calls",
    }
    if any(not isinstance(key, str) for key in receipt.authority):
        raise MigrationError("malformed receipt authority mapping")
    unknown = sorted(set(receipt.authority) - set(expected) - factual)
    if unknown:
        raise MigrationError("unknown authority claim: " + ",".join(unknown))
    if receipt.authority.get("research_only", True) is not True:
        raise MigrationError("receipt research_only authority drift")
    for key in ("live_order_authority", "orders_sent", "private_api_calls"):
        if key in receipt.authority and receipt.authority[key] is not False:
            raise MigrationError(f"receipt {key} authority drift")


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_HASH_KEYS = frozenset({
    "source_sha256", "config_sha256", "input_sha256", "code_sha256", "content_sha256",
    "source_hash", "config_hash", "input_hash", "code_hash", "content_hash",
})
_IDENTITY_ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    "source_hash": ("source_sha256", "source_hash", "source_hashes"),
    "config_hash": ("config_sha256", "config_hash", "config_hashes"),
    "input_hash": ("input_sha256", "input_hash", "input_hashes"),
    "code_hash": ("code_sha256", "code_hash", "code_hashes"),
    "content_hash": ("content_sha256", "content_hash", "content_hashes"),
    "exit": ("exit", "exit_price"),
    "cost": ("cost", "costs"),
}
_COUNT_ALIASES = ("count", "records", "items")
_SIZE_ALIASES = ("size_bytes", "size")


def _validate_hash_value(value: Any, field: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise MigrationError(f"{field} must be a non-empty 64-hex SHA-256")


def _validate_receipt_shape(receipt: ProcessReceipt) -> None:
    if not isinstance(receipt, ProcessReceipt):
        raise MigrationError("malformed receipt mapping")
    if not isinstance(receipt.authority, Mapping) or not isinstance(receipt.identity, Mapping):
        raise MigrationError("malformed receipt mapping")
    if not isinstance(receipt.counters, Mapping) or not isinstance(receipt.timestamps, Mapping):
        raise MigrationError("malformed receipt mapping")
    if not isinstance(receipt.job_name, str) or not _JOB_NAME.fullmatch(receipt.job_name):
        raise MigrationError("malformed receipt job scope")
    if not isinstance(receipt.screen_name, str) or not _SCREEN_NAME.fullmatch(receipt.screen_name):
        raise MigrationError("malformed receipt screen scope")
    if not isinstance(receipt.command, str) or not receipt.command.strip():
        raise MigrationError("malformed receipt command scope")
    if not isinstance(receipt.process_kind, ProcessKind):
        raise MigrationError("malformed receipt process kind")
    if not isinstance(receipt.status, ParityState):
        raise MigrationError("malformed receipt parity status")
    if not isinstance(receipt.eligible_for_parity, bool):
        raise MigrationError("malformed receipt parity eligibility")
    if (
        isinstance(receipt.evidence_paths, (str, bytes))
        or not isinstance(receipt.evidence_paths, Sequence)
        or not receipt.evidence_paths
        or not all(isinstance(path, str) and path.strip() for path in receipt.evidence_paths)
    ):
        raise MigrationError("malformed receipt evidence paths")
    if receipt.pid is not None and (
        not isinstance(receipt.pid, int) or isinstance(receipt.pid, bool) or receipt.pid <= 0
    ):
        raise MigrationError("malformed receipt pid")
    if receipt.cwd is not None and (not isinstance(receipt.cwd, str) or not receipt.cwd):
        raise MigrationError("malformed receipt cwd")
    if receipt.evidence_epoch is not None and (
        not isinstance(receipt.evidence_epoch, str) or not receipt.evidence_epoch
    ):
        raise MigrationError("malformed receipt evidence epoch")
    for field, value in receipt.identity.items():
        if not isinstance(field, str):
            raise MigrationError("malformed receipt identity mapping")
        if field in _HASH_KEYS or field.endswith("_sha256") or field.endswith("_hash"):
            _validate_hash_value(value, f"identity.{field}")
        elif field.endswith("_hashes"):
            if not isinstance(value, Mapping) or not value:
                raise MigrationError(f"identity.{field} must be a non-empty SHA-256 map")
            for key, item in value.items():
                _validate_hash_value(item, f"identity.{field}.{key}")
        if field in {"count", "records", "items", "size", "size_bytes"} and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            raise MigrationError(f"identity.{field} counter must be an integer")
        if field in {"count", "records", "items", "size", "size_bytes"} and value < 0:
            raise MigrationError(f"identity.{field} counter must be non-negative")
    for field, value in receipt.counters.items():
        if not isinstance(field, str):
            raise MigrationError("malformed receipt counter mapping")
        if not isinstance(value, int) or isinstance(value, bool):
            raise MigrationError(f"counter {field} must be an integer")
        if value < 0:
            raise MigrationError(f"counter {field} must be non-negative")


def _parity_gate(receipt: ProcessReceipt) -> ParityReceipt | None:
    _validate_receipt_authority(receipt)
    status = receipt.status.value if isinstance(receipt.status, ParityState) else receipt.status
    if receipt.eligible_for_parity is not True or status != ParityState.PASS.value:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="receipt_not_parity_eligible",
            stop_allowed=False,
        )
    return None


def _process_kind_value(value: ProcessKind | str) -> str:
    return value.value if isinstance(value, ProcessKind) else str(value)


def _identity_has(identity: Mapping[str, Any], candidates: Sequence[str]) -> bool:
    """Return true only for a present, non-blank immutable identity value."""
    return any(
        candidate in identity
        and identity[candidate] is not None
        and identity[candidate] != ""
        and identity[candidate] != {}
        and identity[candidate] != []
        for candidate in candidates
    )


def _normalize_identity_aliases(identity: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(identity)
    for canonical, aliases in _IDENTITY_ALIAS_GROUPS.items():
        present = [(alias, identity[alias]) for alias in aliases if alias in identity]
        if not present:
            continue
        first = present[0][1]
        if any(value != first for _, value in present[1:]):
            raise MigrationError(f"conflicting identity aliases for {canonical}")
        for alias, _ in present:
            normalized.pop(alias, None)
        normalized[canonical] = first
    return normalized


def _numeric_alias_value(receipt: ProcessReceipt, aliases: Sequence[str], field: str) -> int:
    values = [
        mapping[alias]
        for mapping in (receipt.identity, receipt.counters)
        for alias in aliases
        if alias in mapping
    ]
    if not values:
        raise MigrationError(f"mandatory collector {field} is missing")
    first = values[0]
    if any(value != first for value in values[1:]):
        raise MigrationError(f"conflicting collector aliases for {field}")
    if not isinstance(first, int) or isinstance(first, bool) or first < 0:
        raise MigrationError(f"collector {field} must be a non-negative integer")
    return first


def _compare_identity_and_economics(
    old: ProcessReceipt, new: ProcessReceipt
) -> ParityReceipt:
    """Compare all immutable identity, counter, and economic fields."""
    old_identity = _normalize_identity_aliases(old.identity)
    new_identity = _normalize_identity_aliases(new.identity)
    fields = tuple(sorted(set(old_identity) | set(new_identity)))
    counter_fields = tuple(sorted(set(old.counters) | set(new.counters)))
    compared = fields + tuple(f"counter:{field}" for field in counter_fields)
    if not old.identity or not new.identity:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="mandatory_identity_fields_unavailable",
            stop_allowed=False,
            compared_fields=compared,
        )
    if _process_kind_value(old.process_kind) != _process_kind_value(new.process_kind):
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="process_kind_mismatch",
            stop_allowed=False,
            compared_fields=compared,
        )
    if old.job_name != new.job_name:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="job_scope_mismatch",
            stop_allowed=False,
            compared_fields=compared,
        )
    if any(old_identity.get(key) != new_identity.get(key) for key in fields):
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="identity_or_economic_field_mismatch",
            stop_allowed=False,
            compared_fields=compared,
        )
    if any(old.counters.get(key) != new.counters.get(key) for key in counter_fields):
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="counter_or_economic_field_mismatch",
            stop_allowed=False,
            compared_fields=compared,
        )
    return ParityReceipt(
        state=ParityState.PASS,
        reason="identity_and_economics_match",
        stop_allowed=True,
        compared_fields=compared,
    )


def compare_deterministic_receipts(
    old: ProcessReceipt, new: ProcessReceipt
) -> ParityReceipt:
    if (gate := _parity_gate(old)) is not None:
        return gate
    if (gate := _parity_gate(new)) is not None:
        return gate
    if _process_kind_value(old.process_kind) != ProcessKind.DETERMINISTIC.value:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="unexpected_process_kind",
            stop_allowed=False,
        )
    # Evidence files are deliberately relocated from the legacy root into the
    # epoch-specific canonical root.  Their paths and epoch labels are not
    # identity; immutable source/config/input/code hashes and economics are.
    old_source_ts = _source_timestamp(old.timestamps)
    new_source_ts = _source_timestamp(new.timestamps)
    if old_source_ts != new_source_ts:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="source_or_evidence_mismatch",
            stop_allowed=False,
        )
    if old_source_ts is None or new_source_ts is None:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="source_timestamp_unavailable",
            stop_allowed=False,
        )
    required = {
        "decision_id": ("decision_id",),
        "source_hash": ("source_sha256", "source_hash", "source_hashes"),
        "config_hash": ("config_sha256", "config_hash", "config_hashes"),
        "input_hash": ("input_sha256", "input_hash", "input_hashes"),
        "code_hash": ("code_sha256", "code_hash", "code_hashes"),
        "intended_fill": ("intended_fill",),
        "exit": ("exit", "exit_price"),
        "cost": ("cost", "costs"),
        "funding": ("funding",),
    }
    missing = [
        name
        for name, candidates in required.items()
        if not (_identity_has(old.identity, candidates) and _identity_has(new.identity, candidates))
    ]
    if missing:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="mandatory_identity_or_economic_field_missing",
            stop_allowed=False,
            compared_fields=tuple(sorted(missing)),
        )
    return _compare_identity_and_economics(old, new)


def _source_timestamp(timestamps: Mapping[str, str]) -> int | None:
    values: list[int] = []
    for key in ("closed_source_ts", "source_ts", "source_timestamp"):
        if key not in timestamps:
            continue
        values.append(_validate_utc_timestamp(timestamps[key], field=key))
    if len(set(values)) > 1:
        raise MigrationError("conflicting source timestamp aliases")
    return values[0] if values else None


def _validate_utc_timestamp(value: Any, *, field: str) -> int:
    if not isinstance(value, str):
        raise MigrationError(f"{field} must be a valid UTC timestamp")
    try:
        parsed = dt.datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as exc:
        raise MigrationError(f"{field} must be a valid UTC timestamp") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != dt.timedelta(0)
        or parsed.microsecond != 0
    ):
        raise MigrationError(f"{field} must be a valid whole-second UTC timestamp")
    return int(parsed.timestamp())


def compare_market_snapshot_receipts(
    old: ProcessReceipt, new: ProcessReceipt
) -> ParityReceipt:
    if (gate := _parity_gate(old)) is not None:
        return gate
    if (gate := _parity_gate(new)) is not None:
        return gate
    if _process_kind_value(old.process_kind) != ProcessKind.MARKET_SNAPSHOT.value:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="unexpected_process_kind",
            stop_allowed=False,
        )
    left_raw = old.timestamps.get("closed_source_ts")
    right_raw = new.timestamps.get("closed_source_ts")
    _source_timestamp(old.timestamps)
    _source_timestamp(new.timestamps)
    left = (
        _validate_utc_timestamp(left_raw, field="closed_source_ts")
        if left_raw is not None
        else None
    )
    right = (
        _validate_utc_timestamp(right_raw, field="closed_source_ts")
        if right_raw is not None
        else None
    )
    if left is None or right is None or left != right:
        return ParityReceipt(
            state=ParityState.NOT_CONFIRMED,
            reason="shared_closed_source_timestamp_unavailable",
            stop_allowed=False,
        )
    required = {
        "source_hash": ("source_sha256", "source_hash", "source_hashes"),
        "config_hash": ("config_sha256", "config_hash", "config_hashes"),
        "input_hash": ("input_sha256", "input_hash", "input_hashes"),
        "content_hash": ("content_sha256", "content_hash", "content_hashes"),
        "decision_id": ("decision_id",),
    }
    missing = [
        name
        for name, candidates in required.items()
        if not _identity_has(old.identity, candidates)
        or not _identity_has(new.identity, candidates)
    ]
    if missing:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="mandatory_snapshot_identity_or_economic_field_missing",
            stop_allowed=False,
            compared_fields=tuple(sorted(missing)),
        )
    return _compare_identity_and_economics(old, new)


_FRESHNESS_FIELDS = frozenset(
    {"freshness", "updated_at_utc", "observed_at_utc", "collected_at_utc"}
)
_FRESHNESS_TIMESTAMP_FIELDS = _FRESHNESS_FIELDS | frozenset(
    {"fresh", "heartbeat_at_utc", "generated_at_utc"}
)


def _immutable_timestamps(receipt: ProcessReceipt) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, value in receipt.timestamps.items():
        if not isinstance(key, str):
            raise MigrationError("malformed receipt timestamp mapping")
        if key in _FRESHNESS_TIMESTAMP_FIELDS:
            continue
        result[key] = _validate_utc_timestamp(value, field=f"timestamps.{key}")
    return result


def compare_collector_snapshots(
    old: ProcessReceipt, new: ProcessReceipt
) -> ParityReceipt:
    if (gate := _parity_gate(old)) is not None:
        return gate
    if (gate := _parity_gate(new)) is not None:
        return gate
    if _process_kind_value(old.process_kind) != ProcessKind.COLLECTOR.value:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="unexpected_process_kind",
            stop_allowed=False,
        )
    ignored_identity = _FRESHNESS_FIELDS | frozenset(_COUNT_ALIASES) | frozenset(_SIZE_ALIASES)
    ignored_counters = frozenset(_COUNT_ALIASES) | frozenset(_SIZE_ALIASES)
    left = _normalize_identity_aliases(
        {key: value for key, value in old.identity.items() if key not in ignored_identity}
    )
    right = _normalize_identity_aliases(
        {key: value for key, value in new.identity.items() if key not in ignored_identity}
    )
    try:
        left_count = _numeric_alias_value(old, _COUNT_ALIASES, "count")
        right_count = _numeric_alias_value(new, _COUNT_ALIASES, "count")
        left_size = _numeric_alias_value(old, _SIZE_ALIASES, "size_bytes")
        right_size = _numeric_alias_value(new, _SIZE_ALIASES, "size_bytes")
    except MigrationError as exc:
        if " is missing" not in str(exc):
            raise
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="mandatory_collector_identity_or_count_fields_missing",
            stop_allowed=False,
        )
    left_counters = {
        key: value for key, value in old.counters.items() if key not in ignored_counters
    }
    right_counters = {
        key: value for key, value in new.counters.items() if key not in ignored_counters
    }
    left_timestamps = _immutable_timestamps(old)
    right_timestamps = _immutable_timestamps(new)
    compared = tuple(sorted(set(left) | set(right))) + (
        "count",
        "size_bytes",
    ) + tuple(
        f"counter:{field}" for field in sorted(set(left_counters) | set(right_counters))
    ) + tuple(
        f"timestamp:{field}"
        for field in sorted(set(left_timestamps) | set(right_timestamps))
    )
    missing = [
        name for name in ("source_hash", "content_hash")
        if name not in left or name not in right
    ]
    if not old.identity or not new.identity or missing:
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="mandatory_collector_identity_or_count_fields_missing",
            stop_allowed=False,
            compared_fields=compared,
        )
    if (
        left != right
        or left_count != right_count
        or left_size != right_size
        or left_counters != right_counters
        or left_timestamps != right_timestamps
    ):
        return ParityReceipt(
            state=ParityState.FAIL_CLOSED,
            reason="immutable_snapshot_mismatch",
            stop_allowed=False,
            compared_fields=compared,
        )
    return ParityReceipt(
        state=ParityState.PASS,
        reason="immutable_snapshot_match",
        stop_allowed=True,
        compared_fields=compared,
    )


def validate_completion_proof(run_dir: Path) -> None:
    """Validate a Station V3 completion proof and its complete ledger.

    Station V3 owns the detailed manifest/receipt/ledger invariants.  Reuse its
    validators here so migration cannot accidentally accept a looser completion
    interpretation than the station itself.
    """
    run_dir = Path(run_dir).resolve()
    completion_path = run_dir / "completion.json"
    manifest_path = run_dir / "manifest.json"
    checkpoint_path = run_dir / "checkpoint.json"
    ledger_path = run_dir / "trials.jsonl"
    required = (completion_path, manifest_path, checkpoint_path, ledger_path)
    if not all(path.is_file() for path in required):
        raise MigrationError("Station V3 completion proof is incomplete")
    try:
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationError("Station V3 completion proof is malformed") from exc
    if not isinstance(completion, dict) or not isinstance(manifest, dict):
        raise MigrationError("Station V3 completion proof is malformed")
    if manifest.get("authority") != AUTHORITY or manifest.get("promotion_authority") is not False:
        raise MigrationError("invalid Station V3 manifest authority")
    if not isinstance(manifest.get("trials"), list) or not manifest["trials"]:
        raise MigrationError("Station V3 completion proof has no manifest trials")
    if completion.get("authority") != AUTHORITY or completion.get("promotion_authority") is not False:
        raise MigrationError("invalid Station V3 completion authority")
    try:
        from research_lab.station_v3 import (
            _load_ledger,
            _load_json,
            _validate_config_shape,
            _validate_manifest_contract,
            _expected_trials,
            _validate_receipt,
            _verify_file_records,
            _validate_checkpoint,
            _validate_completion,
            sha256_file,
        )

        # Re-read with Station V3's duplicate-key/non-finite rejecting decoder.
        manifest = _load_json(manifest_path)
        completion = _load_json(completion_path)
        if not isinstance(manifest, Mapping) or not isinstance(completion, Mapping):
            raise MigrationError("Station V3 completion proof is malformed")
        expected_completion_fields = {
            "schema_version",
            "run_id",
            "manifest_sha256",
            "state",
            "completed_trials",
            "successful_trials",
            "failed_trials",
            "ledger_tail_sha256",
            "completed_at",
            "authority",
            "promotion_authority",
        }
        if set(completion) != expected_completion_fields:
            raise MigrationError("Station V3 completion field set is invalid")
        if completion.get("schema_version") != 3 or isinstance(
            completion.get("schema_version"), bool
        ):
            raise MigrationError("Station V3 completion schema version is invalid")
        for field in ("completed_trials", "successful_trials", "failed_trials"):
            value = completion.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise MigrationError(f"Station V3 completion {field} is invalid")
        _validate_utc_timestamp(
            completion.get("completed_at"), field="completion.completed_at"
        )
        manifest_sha = sha256_file(manifest_path)
        if manifest.get("schema_version") != 3 or not isinstance(manifest.get("run_id"), str):
            raise MigrationError("invalid Station V3 manifest identity")
        files = manifest.get("files")
        config_records = [
            record for record in files or []
            if isinstance(record, Mapping) and record.get("role") == "config"
        ]
        if len(config_records) != 1:
            raise MigrationError("invalid Station V3 manifest config descriptor")
        config_path = Path(str(config_records[0].get("path", ""))).resolve()
        config = _load_json(config_path)
        if not isinstance(config, Mapping):
            raise MigrationError("invalid Station V3 config contract")
        _validate_config_shape(config)
        project_root = Path(str(manifest.get("project_root", ""))).resolve()
        _validate_manifest_contract(
            manifest,
            config=config,
            config_path=config_path,
            project_root=project_root,
        )
        # This verifies every immutable file descriptor (runner, spec, code,
        # input, orchestrator, and runtime) against the current bytes.
        _verify_file_records(manifest)
        records = _load_ledger(ledger_path, manifest_sha=manifest_sha)
        total_trials = len(manifest.get("trials", []))
        expected_trials = _expected_trials(manifest, manifest_sha)
        if len(records) != total_trials:
            raise MigrationError("complete successful ledger is missing manifest trials")
        records_by_key = {record.get("idempotency_key"): record for record in records}
        receipts_dir = run_dir / "receipts"
        for expected in expected_trials:
            key = expected["key"]
            receipt_path = receipts_dir / f"{key}.json"
            if not receipt_path.is_file():
                raise MigrationError(f"complete successful ledger is missing receipt: {key}")
            receipt = _validate_receipt(
                receipt_path,
                expected,
                run_dir=run_dir,
                run_id=manifest["run_id"],
                manifest_sha=manifest_sha,
            )
            record = records_by_key.get(key)
            if record is None:
                raise MigrationError(f"ledger is missing manifest trial idempotency key: {key}")
            expected_record = {
                "trial_index": expected["index"],
                "trial_id": expected["id"],
                "status": receipt["status"],
                "receipt_path": str(receipt_path.relative_to(run_dir)),
                "receipt_sha256": sha256_file(receipt_path),
            }
            if any(record.get(field) != value for field, value in expected_record.items()):
                raise MigrationError(f"ledger/receipt mismatch for manifest trial: {key}")
        if any(record.get("status") != "succeeded" for record in records):
            raise MigrationError("complete successful ledger contains failed trial")
        _validate_checkpoint(
            checkpoint_path,
            run_id=str(manifest.get("run_id")),
            manifest_sha=manifest_sha,
            records=records,
            total_trials=total_trials,
        )
        _validate_completion(
            completion_path,
            run_id=str(manifest.get("run_id")),
            manifest_sha=manifest_sha,
            records=records,
            total_trials=total_trials,
        )
    except Exception as exc:  # StationV3Error plus malformed data
        if isinstance(exc, MigrationError):
            raise
        raise MigrationError(f"invalid Station V3 completion proof: {exc}") from exc


def register_run_identity(
    path: Path, run_id: str, fingerprint: str, receipt: Mapping[str, Any]
) -> None:
    """Append an fsync'd run identity, rejecting conflicting fingerprints."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Serialize the read/check/append transaction so two workers cannot
        # race past one another with incompatible identities.
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            lines = handle.read().splitlines()
            existing = [json.loads(line) for line in lines if line.strip()]
            if any(not isinstance(row, dict) for row in existing):
                raise MigrationError("run identity registry is malformed")
            matching_identity = False
            for row in existing:
                if row.get("run_id") == run_id and row.get("fingerprint") != fingerprint:
                    raise MigrationError("incompatible identity for run ID")
                if row.get("run_id") == run_id and row.get("fingerprint") == fingerprint:
                    matching_identity = True
            if matching_identity:
                return
            handle.seek(0, os.SEEK_END)
            handle.write(
                json.dumps(
                    {"run_id": run_id, "fingerprint": fingerprint, "receipt": dict(receipt)},
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except (OSError, TypeError, ValueError) as exc:
        raise MigrationError("could not append run identity registry") from exc


def canonical_screen_name(base: str, epoch: str) -> str:
    if not _SCREEN_NAME.fullmatch(base):
        raise MigrationError("canonical screen base is invalid")
    suffix = hashlib.sha256(epoch.encode("utf-8")).hexdigest()[:10]
    return f"{base}_{suffix}"


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MigrationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _explicit_relative_path(value: str, *, field: str) -> None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or any(char in value for char in _GLOB_CHARS):
        raise MigrationError(f"{field} must contain explicit relative paths")


def _resolve_within(root: Path, value: str, *, field: str) -> Path:
    _explicit_relative_path(value, field=field)
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise MigrationError(f"{field} escapes project root") from exc
    return resolved


def _validate_launcher(job: Mapping[str, Any], *, index: int) -> None:
    launcher = job.get("launcher")
    if not isinstance(launcher, list) or not launcher or not all(
        isinstance(value, str) and value for value in launcher
    ):
        raise MigrationError(f"jobs[{index}].launcher must be a non-empty string list")
    _explicit_relative_path(launcher[0], field=f"jobs[{index}].launcher")
    for argument in launcher[1:]:
        normalized = argument.strip().lower()
        if any(fragment in normalized for fragment in _FORBIDDEN_LAUNCH_ARGUMENTS) or _CREDENTIAL_FRAGMENT.search(argument):
            raise MigrationError(f"forbidden launcher argument: {argument}")


def validate_authority_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_id") != MANIFEST_SCHEMA_ID:
        raise MigrationError("canonical station schema mismatch")
    if manifest.get("authority") != AUTHORITY:
        raise MigrationError("canonical station authority mismatch")
    for key in REQUIRED_FALSE_AUTHORITY:
        if manifest.get(key) is not False:
            raise MigrationError(f"{key} must be false")
    if manifest.get("public_data_read_authority") is not True:
        raise MigrationError("public_data_read_authority must be true")
    runtime_root = manifest.get("canonical_runtime_root")
    if not isinstance(runtime_root, str) or not runtime_root:
        raise MigrationError("canonical_runtime_root is required")
    _explicit_relative_path(runtime_root, field="canonical_runtime_root")

    jobs = manifest.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise MigrationError("jobs must be a non-empty list")
    names: set[str] = set()
    sessions: set[str] = set()
    supported_kinds = {kind.value for kind in ProcessKind}
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            raise MigrationError(f"jobs[{index}] must be an object")
        name = job.get("name")
        if not isinstance(name, str) or not _JOB_NAME.fullmatch(name):
            raise MigrationError(f"jobs[{index}].name is invalid")
        if name in names:
            raise MigrationError(f"duplicate job name: {name}")
        names.add(name)
        session = job.get("screen_session")
        if not isinstance(session, str) or not _SCREEN_NAME.fullmatch(session):
            raise MigrationError(f"jobs[{index}].screen_session is invalid")
        if session in sessions:
            raise MigrationError(f"duplicate screen session: {session}")
        sessions.add(session)
        legacy_markers = job.get("legacy_session_markers")
        if not isinstance(legacy_markers, list) or not legacy_markers or not all(
            isinstance(marker, str) and _SCREEN_NAME.fullmatch(marker)
            for marker in legacy_markers
        ):
            raise MigrationError(
                f"jobs[{index}].legacy_session_markers must be explicit safe session prefixes"
            )
        command_markers = job.get("legacy_command_markers")
        if not isinstance(command_markers, list) or not command_markers or not all(
            isinstance(marker, str) and _SCREEN_NAME.fullmatch(marker)
            for marker in command_markers
        ):
            raise MigrationError(
                f"jobs[{index}].legacy_command_markers must be explicit safe basenames"
            )
        if job.get("process_kind") not in supported_kinds:
            raise MigrationError(f"jobs[{index}].process_kind is unsupported")
        migration_mode = job.get("migration_mode", "canonical")
        if migration_mode not in {"canonical", "manual_hold"}:
            raise MigrationError(f"jobs[{index}].migration_mode is unsupported")
        if migration_mode == "manual_hold" and not job.get("migration_blocked_reason"):
            raise MigrationError(
                f"jobs[{index}].migration_blocked_reason is required for manual_hold"
            )
        max_age_seconds = job.get("max_age_seconds")
        if (
            not isinstance(max_age_seconds, int)
            or isinstance(max_age_seconds, bool)
            or max_age_seconds <= 0
        ):
            raise MigrationError(f"jobs[{index}].max_age_seconds must be positive")
        _validate_launcher(job, index=index)
        for field in _PATH_FIELDS:
            values = job.get(field, [])
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                raise MigrationError(f"jobs[{index}].{field} must be explicit relative paths")
            if field in {"evidence_paths", "canonical_evidence_files"} and not values:
                raise MigrationError(f"jobs[{index}].{field} must not be empty")
            for value in values:
                _explicit_relative_path(value, field=f"jobs[{index}].{field}")


def load_manifest(path: Path, project_root: Path) -> dict[str, Any]:
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except MigrationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MigrationError(f"manifest is unreadable or malformed: {path}") from exc
    if not isinstance(raw, dict):
        raise MigrationError("manifest must be a JSON object")
    validate_authority_manifest(raw)
    root = project_root.resolve()
    _resolve_within(root, str(raw["canonical_runtime_root"]), field="canonical_runtime_root")
    for index, job in enumerate(raw["jobs"]):
        launcher = _resolve_within(root, job["launcher"][0], field=f"jobs[{index}].launcher")
        if not launcher.is_file():
            raise MigrationError(f"launcher does not exist: {launcher}")
    return raw


def identity_fingerprint(receipt: ProcessReceipt) -> str:
    process_kind = (
        receipt.process_kind.value
        if isinstance(receipt.process_kind, ProcessKind)
        else str(receipt.process_kind)
    )
    return hashlib.sha256(
        _canonical_json(
            {
                "job_name": receipt.job_name,
                "screen_name": receipt.screen_name,
                "process_kind": process_kind,
                "identity": receipt.identity,
                "evidence_paths": list(receipt.evidence_paths),
                "evidence_epoch": receipt.evidence_epoch,
            }
        )
    ).hexdigest()


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(_canonical_json(dict(payload)))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
