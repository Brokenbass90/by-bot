from __future__ import annotations

import hashlib
import json
import os
import re
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
_PATH_FIELDS = ("evidence_paths", "source_paths", "config_paths", "input_paths")
_GLOB_CHARS = frozenset("*?[")
_FORBIDDEN_LAUNCH_ARGUMENTS = ("--live", "--place-order", "--private-api")
_CREDENTIAL_FRAGMENT = re.compile(r"(?:^|[_-])(?:api[_-]?key|secret|token|credential)(?:$|[_=:.-])", re.IGNORECASE)
_SCREEN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}")


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


@dataclass(frozen=True)
class ParityReceipt:
    state: ParityState
    reason: str
    stop_allowed: bool
    compared_fields: Sequence[str] = ()
    observed_at_utc: str | None = None


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
        if not isinstance(name, str) or not name:
            raise MigrationError(f"jobs[{index}].name is required")
        if name in names:
            raise MigrationError(f"duplicate job name: {name}")
        names.add(name)
        session = job.get("screen_session")
        if not isinstance(session, str) or not _SCREEN_NAME.fullmatch(session):
            raise MigrationError(f"jobs[{index}].screen_session is invalid")
        if session in sessions:
            raise MigrationError(f"duplicate screen session: {session}")
        sessions.add(session)
        if job.get("process_kind") not in supported_kinds:
            raise MigrationError(f"jobs[{index}].process_kind is unsupported")
        _validate_launcher(job, index=index)
        for field in _PATH_FIELDS:
            values = job.get(field, [])
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                raise MigrationError(f"jobs[{index}].{field} must be explicit relative paths")
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
