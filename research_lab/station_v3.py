#!/usr/bin/env python3
"""Research Station v3: immutable, resumable, research-only orchestration.

This module deliberately does *not* know how to trade, promote a strategy, call an
exchange, or choose a data cache.  It executes an explicitly hashed local runner
against explicitly named and validated local CSV inputs.  Every trial is journaled
with an idempotency key and an atomic receipt.

The runner protocol is intentionally small.  Station v3 invokes the configured
runner as::

    python runner.py [configured args...] --request REQUEST.json --result RESULT.json

The runner must exit zero and write a JSON object containing both
``{"status": "ok"}`` and the exact ``idempotency_key`` from REQUEST.json.  Its
result is advisory research evidence only; Station v3 has no promotion authority.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


SCHEMA_VERSION = 3
AUTHORITY = "research_only_no_live_or_promotion"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}")
FORBIDDEN_CONFIG_KEYS = {
    "api_key",
    "api_secret",
    "secret",
    "token",
    "password",
    "private_key",
    "credentials",
    "credential",
}
FORBIDDEN_ARG_FRAGMENTS = (
    "http://",
    "https://",
    "api-key",
    "api_key",
    "api-secret",
    "api_secret",
    "access-token",
    "access_token",
    "password",
    "private-key",
    "private_key",
    "credential",
    "--live",
    "--trade-on",
    "--private-api",
    "--place-order",
)


class StationV3Error(RuntimeError):
    """Base class for fail-closed Station v3 errors."""


class ConfigError(StationV3Error):
    pass


class LockHeldError(StationV3Error):
    pass


class HashDriftError(StationV3Error):
    pass


class InputValidationError(StationV3Error):
    pass


class IntegrityError(StationV3Error):
    pass


class TrialFailedError(StationV3Error):
    pass


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _decode_json(value: str, *, source: str) -> Any:
    def object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, child in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = child
        return result

    def reject_non_finite(constant: str) -> Any:
        raise ValueError(f"non-finite JSON number {constant!r}")

    try:
        return json.loads(
            value,
            object_pairs_hook=object_without_duplicates,
            parse_constant=reject_non_finite,
        )
    except Exception as exc:  # noqa: BLE001 - normalize every provenance parse error
        raise IntegrityError(f"invalid JSON at {source}: {exc}") from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def _atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write_bytes(path, _canonical_json(value))


def _load_json(path: Path) -> Any:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - provenance failures must be explicit
        raise IntegrityError(f"invalid JSON at {path}: {exc}") from exc
    return _decode_json(raw, source=str(path))


def _resolve_explicit_file(project_root: Path, value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} must be a non-empty file path")
    if any(char in value for char in "*?["):
        raise ConfigError(f"{field} must be explicit; globs are forbidden: {value!r}")
    raw = Path(value).expanduser()
    path = (raw if raw.is_absolute() else project_root / raw).resolve()
    if not path.is_file():
        raise ConfigError(f"{field} does not exist or is not a regular file: {path}")
    return path


def _walk_forbidden_keys(value: Any, prefix: str = "config") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            credential_suffixes = tuple(f"_{item}" for item in FORBIDDEN_CONFIG_KEYS)
            if normalized in FORBIDDEN_CONFIG_KEYS or normalized.endswith(credential_suffixes):
                raise ConfigError(f"private credential field is forbidden in Station v3 config: {prefix}.{key}")
            _walk_forbidden_keys(child, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden_keys(child, f"{prefix}[{index}]")


def _validate_config_shape(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ConfigError("config must be a JSON object")
    _walk_forbidden_keys(config)
    if config.get("schema_version") != SCHEMA_VERSION or isinstance(config.get("schema_version"), bool):
        raise ConfigError(f"schema_version must equal {SCHEMA_VERSION}")
    if config.get("authority") != AUTHORITY:
        raise ConfigError(f"authority must be exactly {AUTHORITY!r}")
    if config.get("promotion_authority", False) is not False:
        raise ConfigError("promotion_authority must be false")

    runner = config.get("runner")
    if not isinstance(runner, dict):
        raise ConfigError("runner must be an object")
    args = runner.get("args", [])
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise ConfigError("runner.args must be a list of strings")
    for arg in args:
        lowered = arg.lower()
        if PLACEHOLDER_RE.search(arg):
            raise ConfigError("runner.args are static; Station v3 supplies --request/--result itself")
        if any(fragment in lowered for fragment in FORBIDDEN_ARG_FRAGMENTS):
            raise ConfigError(f"unsafe runner argument is forbidden: {arg!r}")

    if not isinstance(config.get("code_paths", []), list):
        raise ConfigError("code_paths must be a list of explicit file paths")
    inputs = config.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ConfigError("inputs must be a non-empty list")
    trials = config.get("trials")
    if not isinstance(trials, list) or not trials:
        raise ConfigError("trials must be a non-empty list")
    seen_trial_ids: set[str] = set()
    for index, trial in enumerate(trials):
        if not isinstance(trial, dict):
            raise ConfigError(f"trials[{index}] must be an object")
        trial_id = trial.get("id")
        if not isinstance(trial_id, str) or not trial_id.strip():
            raise ConfigError(f"trials[{index}].id must be a non-empty string")
        if trial_id in seen_trial_ids:
            raise ConfigError(f"duplicate trial id: {trial_id!r}")
        seen_trial_ids.add(trial_id)
        try:
            _canonical_json(trial.get("params", {}))
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"trials[{index}].params is not JSON-serializable: {exc}") from exc

    timeout = config.get("trial_timeout_seconds", 3600)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not (1 <= timeout <= 14 * 24 * 3600):
        raise ConfigError("trial_timeout_seconds must be an integer between 1 and 1209600")
    return config


def _parse_iso8601(value: str, *, field: str) -> int:
    if not isinstance(value, str):
        raise InputValidationError(f"{field} must be an ISO-8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise InputValidationError(f"invalid ISO-8601 timestamp for {field}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise InputValidationError(f"{field} must include an explicit timezone: {value!r}")
    if parsed.microsecond:
        raise InputValidationError(f"{field} must resolve to an exact whole second: {value!r}")
    utc = parsed.astimezone(dt.timezone.utc)
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    delta = utc - epoch
    return delta.days * 86_400 + delta.seconds


def _parse_csv_timestamp(raw: str, fmt: str, *, row_number: int, field: str) -> int:
    value = raw.strip()
    try:
        if fmt == "epoch_s":
            if not re.fullmatch(r"[+-]?\d+", value):
                raise ValueError("epoch seconds must be an exact integer")
            return int(value)
        if fmt == "epoch_ms":
            if not re.fullmatch(r"[+-]?\d+", value):
                raise ValueError("epoch milliseconds must be an exact integer")
            number = int(value)
            if number % 1000:
                raise ValueError("epoch milliseconds must be an exact whole second")
            return number // 1000
        if fmt == "iso8601":
            return _parse_iso8601(value, field=f"{field} row {row_number}")
    except (ValueError, OverflowError) as exc:
        raise InputValidationError(
            f"invalid {fmt} timestamp in {field} at CSV row {row_number}: {raw!r} ({exc})"
        ) from exc
    raise InputValidationError(f"unsupported timestamp_format {fmt!r} for {field}")


def _parse_config_timestamp(value: Any, *, field: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _parse_iso8601(value, field=field)
    raise InputValidationError(f"{field} must be integer epoch seconds or an ISO-8601 timestamp")


def _parse_hhmm(value: str, *, field: str) -> int:
    if value == "24:00":
        return 24 * 60
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", str(value))
    if not match:
        raise InputValidationError(f"{field} must be HH:MM (24:00 is allowed as an end): {value!r}")
    return int(match.group(1)) * 60 + int(match.group(2))


@dataclass(frozen=True)
class _CalendarPolicy:
    kind: str
    timezone: dt.tzinfo
    open_windows: dict[int, tuple[tuple[int, int], ...]]
    closures: tuple[tuple[int, int], ...]

    def expected(self, timestamp_s: int) -> bool:
        if any(start <= timestamp_s < end for start, end in self.closures):
            return False
        if self.kind == "continuous":
            return True
        local = dt.datetime.fromtimestamp(timestamp_s, tz=dt.timezone.utc).astimezone(self.timezone)
        minute = local.hour * 60 + local.minute
        return any(start <= minute < end for start, end in self.open_windows.get(local.weekday(), ()))


def _calendar_policy(value: Any, *, field: str) -> _CalendarPolicy:
    if not isinstance(value, dict):
        raise InputValidationError(f"{field} must be an object")
    kind = value.get("kind")
    if kind not in {"continuous", "weekly_schedule"}:
        raise InputValidationError(f"{field}.kind must be continuous or weekly_schedule")
    timezone_name = value.get("timezone", "UTC")
    try:
        timezone = ZoneInfo(str(timezone_name))
    except Exception as exc:  # noqa: BLE001
        raise InputValidationError(f"unknown timezone in {field}: {timezone_name!r}") from exc

    windows: dict[int, tuple[tuple[int, int], ...]] = {}
    if kind == "weekly_schedule":
        raw_windows = value.get("open_windows")
        if not isinstance(raw_windows, dict):
            raise InputValidationError(f"{field}.open_windows must map weekdays 0..6 to time windows")
        for raw_day, raw_ranges in raw_windows.items():
            try:
                day = int(raw_day)
            except (TypeError, ValueError) as exc:
                raise InputValidationError(f"invalid weekday {raw_day!r} in {field}.open_windows") from exc
            if day not in range(7) or not isinstance(raw_ranges, list):
                raise InputValidationError(f"weekday {raw_day!r} in {field}.open_windows is invalid")
            parsed_ranges: list[tuple[int, int]] = []
            for range_index, raw_range in enumerate(raw_ranges):
                if not isinstance(raw_range, list) or len(raw_range) != 2:
                    raise InputValidationError(
                        f"{field}.open_windows[{raw_day}][{range_index}] must be [start,end]"
                    )
                start = _parse_hhmm(raw_range[0], field=f"{field}.open_windows[{raw_day}][{range_index}].start")
                end = _parse_hhmm(raw_range[1], field=f"{field}.open_windows[{raw_day}][{range_index}].end")
                if not 0 <= start < end <= 24 * 60:
                    raise InputValidationError(f"invalid/overnight window in {field}: {raw_range!r}; split at midnight")
                parsed_ranges.append((start, end))
            windows[day] = tuple(sorted(parsed_ranges))

    closures: list[tuple[int, int]] = []
    raw_closures = value.get("closures", [])
    if not isinstance(raw_closures, list):
        raise InputValidationError(f"{field}.closures must be a list")
    for index, closure in enumerate(raw_closures):
        if not isinstance(closure, dict):
            raise InputValidationError(f"{field}.closures[{index}] must be an object")
        start = _parse_iso8601(closure.get("start"), field=f"{field}.closures[{index}].start")
        end = _parse_iso8601(closure.get("end"), field=f"{field}.closures[{index}].end")
        if start >= end:
            raise InputValidationError(f"closure start must precede end in {field}.closures[{index}]")
        closures.append((start, end))
    return _CalendarPolicy(kind, timezone, windows, tuple(sorted(closures)))


def validate_csv_input(path: Path, config: Mapping[str, Any], *, name: str) -> dict[str, Any]:
    """Validate one explicit bar CSV and return an auditable summary.

    Missing intervals are accepted only when *every* missing timestamp is closed by
    the supplied calendar policy.  No calendar is inferred from the filename or
    symbol.
    """

    timestamp_column = config.get("timestamp_column")
    if not isinstance(timestamp_column, str) or not timestamp_column:
        raise InputValidationError(f"input {name}: timestamp_column is required")
    timestamp_format = config.get("timestamp_format")
    if timestamp_format not in {"epoch_s", "epoch_ms", "iso8601"}:
        raise InputValidationError(f"input {name}: timestamp_format must be epoch_s, epoch_ms, or iso8601")
    interval = config.get("interval_seconds")
    if not isinstance(interval, int) or isinstance(interval, bool) or interval <= 0:
        raise InputValidationError(f"input {name}: interval_seconds must be a positive integer")
    alignment = config.get("alignment_epoch_seconds", 0)
    if not isinstance(alignment, int) or isinstance(alignment, bool):
        raise InputValidationError(f"input {name}: alignment_epoch_seconds must be an integer")
    coverage_start = _parse_config_timestamp(
        config.get("coverage_start"), field=f"input {name}.coverage_start"
    )
    coverage_end = _parse_config_timestamp(
        config.get("coverage_end_exclusive"), field=f"input {name}.coverage_end_exclusive"
    )
    source_as_of = _parse_config_timestamp(
        config.get("source_as_of"), field=f"input {name}.source_as_of"
    )
    finality_lag = config.get("finality_lag_seconds")
    if not isinstance(finality_lag, int) or isinstance(finality_lag, bool) or finality_lag < 0:
        raise InputValidationError(f"input {name}: finality_lag_seconds must be a non-negative integer")
    if coverage_start >= coverage_end:
        raise InputValidationError(f"input {name}: coverage_start must precede coverage_end_exclusive")
    if (coverage_start - alignment) % interval or (coverage_end - alignment) % interval:
        raise InputValidationError(f"input {name}: coverage bounds are off the {interval}s alignment")
    if source_as_of < coverage_end + finality_lag:
        raise InputValidationError(
            f"input {name}: source_as_of does not finalize coverage_end_exclusive plus "
            f"finality_lag_seconds ({source_as_of} < {coverage_end + finality_lag})"
        )
    min_rows = config.get("min_rows", 2)
    if not isinstance(min_rows, int) or isinstance(min_rows, bool) or min_rows < 2:
        raise InputValidationError(f"input {name}: min_rows must be an integer >= 2")
    max_missing = config.get("max_missing_slots_to_check", 1_000_000)
    if not isinstance(max_missing, int) or isinstance(max_missing, bool) or max_missing < 0:
        raise InputValidationError(f"input {name}: max_missing_slots_to_check must be a non-negative integer")
    delimiter = config.get("delimiter", ",")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise InputValidationError(f"input {name}: delimiter must be one character")
    calendar = _calendar_policy(config.get("calendar"), field=f"input {name}.calendar")

    timestamps: list[int] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames:
                raise InputValidationError(f"input {name}: CSV header is missing")
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise InputValidationError(f"input {name}: duplicate CSV column names")
            if timestamp_column not in reader.fieldnames:
                raise InputValidationError(
                    f"input {name}: timestamp column {timestamp_column!r} not found in {reader.fieldnames!r}"
                )
            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    raise InputValidationError(f"input {name}: malformed extra fields at CSV row {row_number}")
                raw = row.get(timestamp_column)
                if raw is None or not raw.strip():
                    raise InputValidationError(f"input {name}: empty timestamp at CSV row {row_number}")
                timestamps.append(
                    _parse_csv_timestamp(raw, timestamp_format, row_number=row_number, field=f"input {name}")
                )
    except UnicodeDecodeError as exc:
        raise InputValidationError(f"input {name}: CSV is not valid UTF-8: {exc}") from exc

    if len(timestamps) < min_rows:
        raise InputValidationError(f"input {name}: expected at least {min_rows} rows, found {len(timestamps)}")

    # Establish ordering/uniqueness before inspecting gaps so a later backwards
    # row cannot be obscured by an earlier apparent gap.
    for index in range(1, len(timestamps)):
        previous = timestamps[index - 1]
        timestamp_s = timestamps[index]
        if timestamp_s == previous:
            raise InputValidationError(f"input {name}: duplicate timestamp {timestamp_s}")
        if timestamp_s < previous:
            raise InputValidationError(
                f"input {name}: timestamps are not strictly sorted at {previous} -> {timestamp_s}"
            )

    if timestamps[0] < coverage_start or timestamps[-1] >= coverage_end:
        raise InputValidationError(
            f"input {name}: rows fall outside configured half-open coverage "
            f"[{coverage_start},{coverage_end})"
        )
    for index, timestamp_s in enumerate(timestamps):
        if (timestamp_s - alignment) % interval:
            raise InputValidationError(
                f"input {name}: timestamp {timestamp_s} at data row {index + 1} is off the {interval}s alignment"
            )
        if not calendar.expected(timestamp_s):
            raise InputValidationError(
                f"input {name}: bar at {timestamp_s} falls in a configured market closure"
            )

    gaps = 0
    missing_closed_slots = 0
    checked_missing_slots = 0

    def validate_missing_slots(start: int, end: int, *, context: str) -> None:
        nonlocal gaps, missing_closed_slots, checked_missing_slots
        missing_count = max(0, (end - start) // interval)
        if missing_count <= 0:
            return
        if checked_missing_slots + missing_count > max_missing:
            raise InputValidationError(
                f"input {name}: cumulative gap check would exceed "
                f"max_missing_slots_to_check={max_missing}"
            )
        checked_missing_slots += missing_count
        gaps += 1
        for missing_ts in range(start, end, interval):
            if calendar.expected(missing_ts):
                raise InputValidationError(
                    f"input {name}: unexpected open-market gap at {missing_ts} ({context})"
                )
            missing_closed_slots += 1

    validate_missing_slots(
        coverage_start,
        timestamps[0],
        context=f"before first row {timestamps[0]}",
    )
    for index, timestamp_s in enumerate(timestamps):
        if index == 0:
            continue
        previous = timestamps[index - 1]
        delta = timestamp_s - previous
        if delta % interval:
            raise InputValidationError(
                f"input {name}: interval {delta}s at {previous} -> {timestamp_s} is not a multiple of {interval}s"
            )
        missing_count = delta // interval - 1
        if missing_count <= 0:
            continue
        validate_missing_slots(
            previous + interval,
            timestamp_s,
            context=f"between {previous} and {timestamp_s}",
        )

    validate_missing_slots(
        timestamps[-1] + interval,
        coverage_end,
        context=f"after last row {timestamps[-1]}",
    )

    return {
        "rows": len(timestamps),
        "first_timestamp_s": timestamps[0],
        "last_timestamp_s": timestamps[-1],
        "interval_seconds": interval,
        "alignment_epoch_seconds": alignment,
        "coverage_start_timestamp_s": coverage_start,
        "coverage_end_exclusive_timestamp_s": coverage_end,
        "source_as_of_timestamp_s": source_as_of,
        "finality_lag_seconds": finality_lag,
        "calendar_kind": calendar.kind,
        "calendar_timezone": str(getattr(calendar.timezone, "key", calendar.timezone)),
        "closure_gaps": gaps,
        "missing_closed_slots": missing_closed_slots,
    }


class ExclusiveRunLock:
    """Non-blocking, process-wide exclusive lock for one run directory."""

    def __init__(self, run_dir: Path):
        self.path = run_dir / ".station_v3.lock"
        self._handle: Any = None

    def __enter__(self) -> "ExclusiveRunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise LockHeldError(f"run is already locked: {self.path.parent}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid(), "acquired_at": _utc_now()}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        self._handle = handle
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


def _file_record(path: Path, *, role: str, logical_name: str) -> dict[str, Any]:
    before = path.stat()
    digest = sha256_file(path)
    after = path.stat()
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise HashDriftError(f"file changed while it was being hashed: {path}")
    return {
        "role": role,
        "logical_name": logical_name,
        "path": str(path),
        "size": after.st_size,
        "sha256": digest,
    }


def _runtime_contract() -> dict[str, Any]:
    return {
        "python_executable": str(Path(sys.executable).resolve()),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_cache_tag": sys.implementation.cache_tag,
        "platform": sys.platform,
    }


def _prepare_manifest(
    *,
    config_path: Path,
    config: dict[str, Any],
    project_root: Path,
    run_id: str,
) -> dict[str, Any]:
    runner_path = _resolve_explicit_file(project_root, config["runner"].get("path"), field="runner.path")
    spec_path = _resolve_explicit_file(project_root, config.get("spec_path"), field="spec_path")
    code_paths = [
        _resolve_explicit_file(project_root, value, field=f"code_paths[{index}]")
        for index, value in enumerate(config.get("code_paths", []))
    ]
    worker_path = Path(__file__).with_name("station_v3_worker.py").resolve()
    if not worker_path.is_file():
        raise ConfigError(f"Station v3 worker is missing: {worker_path}")

    files: list[dict[str, Any]] = [
        _file_record(config_path, role="config", logical_name="config"),
        _file_record(Path(__file__).resolve(), role="orchestrator", logical_name="station_v3"),
        _file_record(worker_path, role="orchestrator", logical_name="station_v3_worker"),
        _file_record(Path(sys.executable).resolve(), role="runtime", logical_name="python_executable"),
        _file_record(runner_path, role="runner", logical_name="runner"),
        _file_record(spec_path, role="spec", logical_name="spec"),
    ]
    files.extend(
        _file_record(path, role="code", logical_name=f"code_{index}") for index, path in enumerate(code_paths)
    )

    input_records: list[dict[str, Any]] = []
    seen_input_names: set[str] = set()
    seen_input_paths: set[Path] = set()
    for index, input_config in enumerate(config["inputs"]):
        if not isinstance(input_config, dict):
            raise ConfigError(f"inputs[{index}] must be an object")
        name = input_config.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"inputs[{index}].name must be a non-empty string")
        if name in seen_input_names:
            raise ConfigError(f"duplicate input name: {name!r}")
        seen_input_names.add(name)
        path = _resolve_explicit_file(project_root, input_config.get("path"), field=f"inputs[{index}].path")
        if path in seen_input_paths:
            raise ConfigError(f"input file is listed more than once: {path}")
        seen_input_paths.add(path)
        validated_hash = sha256_file(path)
        validation = validate_csv_input(path, input_config, name=name)
        record = _file_record(path, role="input_csv", logical_name=name)
        if record["sha256"] != validated_hash:
            raise HashDriftError(f"input changed while it was being validated: {path}")
        record["validation"] = validation
        record["input_config"] = input_config
        input_records.append(record)
        files.append(record)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": _utc_now(),
        "authority": AUTHORITY,
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "runtime": _runtime_contract(),
        "project_root": str(project_root),
        "runner_path": str(runner_path),
        "runner_args": list(config["runner"].get("args", [])),
        "spec_path": str(spec_path),
        "trial_timeout_seconds": int(config.get("trial_timeout_seconds", 3600)),
        "trials": config["trials"],
        "inputs": input_records,
        "files": files,
    }


def _verify_file_records(manifest: Mapping[str, Any]) -> None:
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise IntegrityError("manifest files list is empty")
    for record in files:
        if not isinstance(record, dict):
            raise IntegrityError("malformed file record in manifest")
        path = Path(str(record.get("path", "")))
        if not path.is_file():
            raise HashDriftError(f"immutable file disappeared: {path}")
        actual = _file_record(
            path,
            role=str(record.get("role", "")),
            logical_name=str(record.get("logical_name", "")),
        )
        if actual["size"] != record.get("size") or actual["sha256"] != record.get("sha256"):
            raise HashDriftError(
                f"immutable file drift for {record.get('role')}:{record.get('logical_name')} at {path}; "
                f"expected sha256={record.get('sha256')} size={record.get('size')}, "
                f"got sha256={actual['sha256']} size={actual['size']}"
            )


def _validate_manifest_contract(
    manifest: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    config_path: Path,
    project_root: Path,
) -> None:
    expected_keys = {
        "schema_version",
        "run_id",
        "created_at",
        "authority",
        "promotion_authority",
        "network_authority",
        "private_api_authority",
        "order_authority",
        "live_write_authority",
        "runtime",
        "project_root",
        "runner_path",
        "runner_args",
        "spec_path",
        "trial_timeout_seconds",
        "trials",
        "inputs",
        "files",
    }
    if set(manifest) != expected_keys:
        raise IntegrityError("manifest field set does not match the Station v3 contract")
    if manifest.get("authority") != AUTHORITY or any(
        manifest.get(field) is not False
        for field in (
            "promotion_authority",
            "network_authority",
            "private_api_authority",
            "order_authority",
            "live_write_authority",
        )
    ):
        raise IntegrityError("manifest research-only authority contract is invalid")
    if manifest.get("runtime") != _runtime_contract():
        raise HashDriftError("Python runtime drift from the immutable manifest")
    _parse_iso8601(manifest.get("created_at"), field="manifest.created_at")

    runner_path = _resolve_explicit_file(project_root, config["runner"].get("path"), field="runner.path")
    spec_path = _resolve_explicit_file(project_root, config.get("spec_path"), field="spec_path")
    code_paths = [
        _resolve_explicit_file(project_root, value, field=f"code_paths[{index}]")
        for index, value in enumerate(config.get("code_paths", []))
    ]
    worker_path = Path(__file__).with_name("station_v3_worker.py").resolve()
    input_configs = config.get("inputs", [])
    manifest_inputs = manifest.get("inputs")
    if not isinstance(manifest_inputs, list) or len(manifest_inputs) != len(input_configs):
        raise IntegrityError("manifest input list differs from config")

    input_paths: list[Path] = []
    for index, (input_config, record) in enumerate(zip(input_configs, manifest_inputs)):
        if not isinstance(input_config, dict) or not isinstance(record, dict):
            raise IntegrityError(f"manifest/config input {index} is malformed")
        path = _resolve_explicit_file(project_root, input_config.get("path"), field=f"inputs[{index}].path")
        input_paths.append(path)
        if (
            record.get("role") != "input_csv"
            or record.get("logical_name") != input_config.get("name")
            or record.get("path") != str(path)
            or record.get("input_config") != input_config
        ):
            raise HashDriftError(f"manifest input contract drift at inputs[{index}]")

    expected_scalar_fields = {
        "project_root": str(project_root),
        "runner_path": str(runner_path),
        "runner_args": list(config["runner"].get("args", [])),
        "spec_path": str(spec_path),
        "trial_timeout_seconds": int(config.get("trial_timeout_seconds", 3600)),
        "trials": config["trials"],
    }
    for field, expected in expected_scalar_fields.items():
        if manifest.get(field) != expected:
            raise HashDriftError(f"manifest/config drift at {field}")

    expected_descriptors = [
        ("config", "config", config_path),
        ("orchestrator", "station_v3", Path(__file__).resolve()),
        ("orchestrator", "station_v3_worker", worker_path),
        ("runtime", "python_executable", Path(sys.executable).resolve()),
        ("runner", "runner", runner_path),
        ("spec", "spec", spec_path),
        *[("code", f"code_{index}", path) for index, path in enumerate(code_paths)],
        *[
            ("input_csv", str(input_config["name"]), path)
            for input_config, path in zip(input_configs, input_paths)
        ],
    ]
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != len(expected_descriptors):
        raise IntegrityError("manifest file set differs from config")
    actual_descriptors = [
        (record.get("role"), record.get("logical_name"), Path(str(record.get("path", ""))))
        if isinstance(record, dict)
        else None
        for record in files
    ]
    if actual_descriptors != expected_descriptors:
        raise HashDriftError("manifest file descriptors differ from config")
    if files[-len(manifest_inputs) :] != manifest_inputs:
        raise IntegrityError("manifest input records are not identical to their file records")


def _verify_manifest(
    manifest_path: Path,
    *,
    config: Mapping[str, Any],
    config_path: Path,
    project_root: Path,
    run_id: str,
) -> tuple[dict[str, Any], str]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise IntegrityError(f"invalid Station v3 manifest: {manifest_path}")
    if manifest.get("run_id") != run_id:
        raise IntegrityError(f"manifest run_id mismatch: expected {run_id!r}, got {manifest.get('run_id')!r}")
    if manifest.get("project_root") != str(project_root):
        raise HashDriftError(
            f"project_root drift: manifest={manifest.get('project_root')!r}, current={str(project_root)!r}"
        )
    _validate_manifest_contract(
        manifest,
        config=config,
        config_path=config_path,
        project_root=project_root,
    )
    _verify_file_records(manifest)
    manifest_sha = sha256_file(manifest_path)
    return manifest, manifest_sha


def _trial_key(manifest_sha: str, trial_index: int, trial: Mapping[str, Any]) -> str:
    intent = {
        "manifest_sha256": manifest_sha,
        "trial_index": trial_index,
        "trial_id": trial["id"],
        "params": trial.get("params", {}),
    }
    return _sha256_bytes(_canonical_json(intent))


def _record_hash(record: Mapping[str, Any]) -> str:
    return _sha256_bytes(_canonical_json({k: v for k, v in record.items() if k != "record_sha256"}))


def _load_ledger(path: Path, *, manifest_sha: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    previous_hash = "0" * 64
    seen_keys: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise IntegrityError(f"ledger is not UTF-8: {path}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise IntegrityError(f"blank/corrupt ledger line {line_number}: {path}")
        try:
            record = _decode_json(line, source=f"{path} line {line_number}")
        except IntegrityError as exc:
            raise IntegrityError(f"corrupt ledger line {line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise IntegrityError(f"ledger line {line_number} is not an object")
        if record.get("sequence") != line_number:
            raise IntegrityError(f"ledger sequence mismatch at line {line_number}")
        if record.get("manifest_sha256") != manifest_sha:
            raise IntegrityError(f"ledger manifest hash mismatch at line {line_number}")
        if record.get("prev_record_sha256") != previous_hash:
            raise IntegrityError(f"ledger hash chain mismatch at line {line_number}")
        actual_hash = _record_hash(record)
        if record.get("record_sha256") != actual_hash:
            raise IntegrityError(f"ledger record hash mismatch at line {line_number}")
        key = record.get("idempotency_key")
        if not isinstance(key, str) or key in seen_keys:
            raise IntegrityError(f"duplicate/invalid idempotency key at ledger line {line_number}")
        seen_keys.add(key)
        records.append(record)
        previous_hash = actual_hash
    return records


def _append_ledger_atomic(path: Path, records: Sequence[dict[str, Any]], new_record: dict[str, Any]) -> dict[str, Any]:
    """Logically append one record while replacing the file atomically.

    Existing records are copied byte-for-byte in canonical form and are never
    removed or edited.  Atomic replacement avoids an unresumable partial JSONL tail
    if power is lost during append.
    """

    if any(r["idempotency_key"] == new_record["idempotency_key"] for r in records):
        raise IntegrityError(f"idempotency key already exists in ledger: {new_record['idempotency_key']}")
    record = dict(new_record)
    record["sequence"] = len(records) + 1
    record["prev_record_sha256"] = records[-1]["record_sha256"] if records else "0" * 64
    record["record_sha256"] = _record_hash(record)
    payload = b"".join(_canonical_json(item) for item in [*records, record])
    _atomic_write_bytes(path, payload)
    return record


def _expected_trials(manifest: Mapping[str, Any], manifest_sha: str) -> list[dict[str, Any]]:
    expected: list[dict[str, Any]] = []
    for index, trial in enumerate(manifest["trials"]):
        expected.append(
            {
                "index": index,
                "id": trial["id"],
                "params": trial.get("params", {}),
                "key": _trial_key(manifest_sha, index, trial),
            }
        )
    return expected


def _receipt_artifact(run_dir: Path, receipt: Mapping[str, Any], path_field: str, hash_field: str) -> None:
    raw_path = receipt.get(path_field)
    expected_hash = receipt.get(hash_field)
    if not isinstance(raw_path, str) or not isinstance(expected_hash, str):
        raise IntegrityError(f"receipt has invalid {path_field}/{hash_field}")
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise IntegrityError(f"receipt artifact path escapes run directory: {raw_path!r}")
    artifact = (run_dir / relative).resolve()
    try:
        artifact.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise IntegrityError(f"receipt artifact path escapes run directory: {raw_path!r}") from exc
    if not artifact.is_file():
        raise IntegrityError(f"receipt artifact disappeared: {artifact}")
    if sha256_file(artifact) != expected_hash:
        raise IntegrityError(f"receipt artifact hash drift: {artifact}")


def _validate_receipt(
    path: Path,
    expected: Mapping[str, Any],
    *,
    run_dir: Path,
    run_id: str,
    manifest_sha: str,
) -> dict[str, Any]:
    receipt = _load_json(path)
    if not isinstance(receipt, dict):
        raise IntegrityError(f"receipt is not an object: {path}")
    if receipt.get("schema_version") != SCHEMA_VERSION or receipt.get("authority") != AUTHORITY:
        raise IntegrityError(f"receipt has invalid schema/authority: {path}")
    checks = {
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
        "trial_index": expected["index"],
        "trial_id": expected["id"],
        "idempotency_key": expected["key"],
    }
    for field, value in checks.items():
        if receipt.get(field) != value:
            raise IntegrityError(f"receipt {path} has wrong {field}: {receipt.get(field)!r} != {value!r}")
    if receipt.get("status") not in {"succeeded", "failed"}:
        raise IntegrityError(f"receipt {path} has invalid status")
    started_at = _parse_iso8601(receipt.get("started_at"), field=f"receipt {path}.started_at")
    finished_at = _parse_iso8601(receipt.get("finished_at"), field=f"receipt {path}.finished_at")
    if finished_at < started_at:
        raise IntegrityError(f"receipt {path} finished before it started")
    for path_field, hash_field in (
        ("request_path", "request_sha256"),
        ("stdout_path", "stdout_sha256"),
        ("stderr_path", "stderr_sha256"),
    ):
        _receipt_artifact(run_dir, receipt, path_field, hash_field)
    if receipt["status"] == "succeeded":
        _receipt_artifact(run_dir, receipt, "result_path", "result_sha256")
    elif receipt.get("result_path") is not None or receipt.get("result_sha256") is not None:
        raise IntegrityError(f"failed receipt unexpectedly references a result: {path}")
    return receipt


def _ledger_entry_from_receipt(
    receipt_path: Path,
    receipt: Mapping[str, Any],
    *,
    run_dir: Path,
    manifest_sha: str,
) -> dict[str, Any]:
    return {
        "manifest_sha256": manifest_sha,
        "idempotency_key": receipt["idempotency_key"],
        "trial_index": receipt["trial_index"],
        "trial_id": receipt["trial_id"],
        "status": receipt["status"],
        "receipt_path": str(receipt_path.relative_to(run_dir)),
        "receipt_sha256": sha256_file(receipt_path),
        # Derive the ledger timestamp from immutable receipt content so a ledger
        # lost after checkpointing can be reconstructed byte-for-byte.
        "recorded_at": receipt["finished_at"],
    }


def _reconcile_receipts(
    run_dir: Path,
    expected_trials: Sequence[dict[str, Any]],
    records: list[dict[str, Any]],
    *,
    run_id: str,
    manifest_sha: str,
) -> list[dict[str, Any]]:
    ledger_path = run_dir / "trials.jsonl"
    expected_by_key = {item["key"]: item for item in expected_trials}
    records_by_key = {item["idempotency_key"]: item for item in records}
    receipts_dir = run_dir / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    receipt_paths = {path.stem: path for path in receipts_dir.glob("*.json")}
    unexpected_keys = sorted(set(receipt_paths) - set(expected_by_key))
    if unexpected_keys:
        raise IntegrityError(
            f"unexpected receipt not in manifest trial set: {receipt_paths[unexpected_keys[0]]}"
        )
    for expected in expected_trials:
        key = expected["key"]
        receipt_path = receipt_paths.get(key)
        if receipt_path is None:
            continue
        receipt = _validate_receipt(
            receipt_path,
            expected,
            run_dir=run_dir,
            run_id=run_id,
            manifest_sha=manifest_sha,
        )
        ledger_record = records_by_key.get(key)
        if ledger_record is None:
            appended = _append_ledger_atomic(
                ledger_path,
                records,
                _ledger_entry_from_receipt(
                    receipt_path, receipt, run_dir=run_dir, manifest_sha=manifest_sha
                ),
            )
            records.append(appended)
            records_by_key[key] = appended
        else:
            expected_ledger_fields = {
                "trial_index": expected["index"],
                "trial_id": expected["id"],
                "status": receipt["status"],
                "receipt_path": str(receipt_path.relative_to(run_dir)),
                "receipt_sha256": sha256_file(receipt_path),
            }
            for field, value in expected_ledger_fields.items():
                if ledger_record.get(field) != value:
                    raise IntegrityError(
                        f"ledger/receipt mismatch for {key} at {field}: {ledger_record.get(field)!r} != {value!r}"
                    )

    for record in records:
        key = record["idempotency_key"]
        expected = expected_by_key.get(key)
        if expected is None:
            raise IntegrityError(f"ledger contains a trial outside the manifest: {key}")
        receipt_path = receipts_dir / f"{key}.json"
        expected_ledger_fields = {
            "trial_index": expected["index"],
            "trial_id": expected["id"],
            "receipt_path": str(receipt_path.relative_to(run_dir)),
        }
        for field, value in expected_ledger_fields.items():
            if record.get(field) != value:
                raise IntegrityError(
                    f"ledger trial mismatch for {key} at {field}: {record.get(field)!r} != {value!r}"
                )
        if not receipt_path.is_file():
            raise IntegrityError(f"ledger receipt disappeared: {receipt_path}")
        receipt = _validate_receipt(
            receipt_path,
            expected,
            run_dir=run_dir,
            run_id=run_id,
            manifest_sha=manifest_sha,
        )
        if record.get("status") != receipt.get("status"):
            raise IntegrityError(f"ledger/receipt status mismatch for {key}")
        if sha256_file(receipt_path) != record["receipt_sha256"]:
            raise IntegrityError(f"ledger receipt hash mismatch: {receipt_path}")
    return records


def _checkpoint(
    run_dir: Path,
    *,
    state: str,
    run_id: str,
    manifest_sha: str,
    records: Sequence[Mapping[str, Any]],
    total_trials: int,
    detail: str | None = None,
) -> dict[str, Any]:
    value = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
        "state": state,
        "completed_trials": len(records),
        "successful_trials": sum(item.get("status") == "succeeded" for item in records),
        "failed_trials": sum(item.get("status") == "failed" for item in records),
        "total_trials": total_trials,
        "ledger_tail_sha256": records[-1]["record_sha256"] if records else "0" * 64,
        "updated_at": _utc_now(),
    }
    if detail:
        value["detail"] = detail
    _atomic_write_json(run_dir / "checkpoint.json", value)
    return value


def _validate_checkpoint(
    path: Path,
    *,
    run_id: str,
    manifest_sha: str,
    records: Sequence[Mapping[str, Any]],
    total_trials: int,
) -> dict[str, Any]:
    checkpoint = _load_json(path)
    if not isinstance(checkpoint, dict):
        raise IntegrityError(f"checkpoint is not an object: {path}")
    allowed_fields = {
        "schema_version",
        "run_id",
        "manifest_sha256",
        "state",
        "completed_trials",
        "successful_trials",
        "failed_trials",
        "total_trials",
        "ledger_tail_sha256",
        "updated_at",
        "detail",
    }
    required_fields = allowed_fields - {"detail"}
    if not required_fields.issubset(checkpoint) or set(checkpoint) - allowed_fields:
        raise IntegrityError(f"checkpoint field set is invalid: {path}")
    expected_identity = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
        "total_trials": total_trials,
    }
    for field, value in expected_identity.items():
        if checkpoint.get(field) != value:
            raise IntegrityError(
                f"checkpoint mismatch at {field}: {checkpoint.get(field)!r} != {value!r}"
            )
    state = checkpoint.get("state")
    if state not in {"RUNNING", "PAUSED", "INTERRUPTED", "FAILED", "COMPLETED"}:
        raise IntegrityError(f"checkpoint has invalid state: {state!r}")
    completed = checkpoint.get("completed_trials")
    if not isinstance(completed, int) or isinstance(completed, bool) or not (0 <= completed <= total_trials):
        raise IntegrityError("checkpoint completed_trials is invalid")
    if completed > len(records):
        raise IntegrityError(
            f"checkpoint references {completed} completed trials but only {len(records)} "
            "ledger/receipt records remain"
        )
    prefix = list(records[:completed])
    expected_progress = {
        "successful_trials": sum(record.get("status") == "succeeded" for record in prefix),
        "failed_trials": sum(record.get("status") == "failed" for record in prefix),
        "ledger_tail_sha256": prefix[-1]["record_sha256"] if prefix else "0" * 64,
    }
    for field, value in expected_progress.items():
        if checkpoint.get(field) != value:
            raise IntegrityError(
                f"checkpoint/ledger prefix mismatch at {field}: {checkpoint.get(field)!r} != {value!r}"
            )
    if state == "COMPLETED" and (
        completed != total_trials or expected_progress["successful_trials"] != total_trials
    ):
        raise IntegrityError("COMPLETED checkpoint does not describe an all-success ledger")
    if state == "FAILED" and expected_progress["failed_trials"] < 1:
        raise IntegrityError("FAILED checkpoint has no failed trial")
    _parse_iso8601(checkpoint.get("updated_at"), field=f"checkpoint {path}.updated_at")
    return checkpoint


def _sanitized_worker_env(project_root: Path, trial_dir: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    tmp_dir = trial_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "PATH": os.defpath,
            "LANG": "C",
            "LC_ALL": "C",
            "TZ": "UTC",
            "HOME": str(trial_dir),
            "TMPDIR": str(tmp_dir),
            "PYTHONPATH": str(project_root),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONUTF8": "1",
            "STATION_V3_RESEARCH_ONLY": "1",
            "STATION_V3_NO_NETWORK": "1",
            "STATION_V3_NO_PRIVATE_API": "1",
            "STATION_V3_NO_ORDERS": "1",
            "STATION_V3_NO_LIVE_WRITES": "1",
            "STATION_V3_NO_PROMOTION": "1",
            "DRY_RUN": "1",
            "TRADE_ON": "0",
            "LIVE_TRADING": "0",
        }
    )
    return env


def _run_trial(
    *,
    run_dir: Path,
    manifest: Mapping[str, Any],
    manifest_sha: str,
    expected: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    def captured_bytes(value: bytes | str | None) -> bytes:
        if isinstance(value, str):
            return value.encode("utf-8", errors="replace")
        return value or b""

    key = expected["key"]
    trial_dir = run_dir / "trial_work" / f"{expected['index']:06d}_{key[:16]}"
    trial_dir.mkdir(parents=True, exist_ok=True)
    request_path = trial_dir / "request.json"
    pending_result_path = trial_dir / "result.pending.json"
    result_path = trial_dir / "result.json"
    stdout_path = trial_dir / "stdout.txt"
    stderr_path = trial_dir / "stderr.txt"
    for stale in (pending_result_path, result_path):
        if stale.exists():
            stale.unlink()

    request = {
        "schema_version": SCHEMA_VERSION,
        "authority": AUTHORITY,
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "run_id": manifest["run_id"],
        "manifest_sha256": manifest_sha,
        "trial_index": expected["index"],
        "trial_id": expected["id"],
        "idempotency_key": key,
        "params": expected["params"],
        "spec_path": manifest["spec_path"],
        "inputs": [
            {
                "name": item["logical_name"],
                "path": item["path"],
                "sha256": item["sha256"],
                "validation": item["validation"],
            }
            for item in manifest["inputs"]
        ],
    }
    _atomic_write_json(request_path, request)
    request_sha = sha256_file(request_path)
    started_at = _utc_now()
    worker = Path(__file__).with_name("station_v3_worker.py").resolve()
    command = [
        sys.executable,
        str(worker),
        "--allowed-write-root",
        str(trial_dir),
        "--runner",
        str(manifest["runner_path"]),
        "--",
        *manifest.get("runner_args", []),
        "--request",
        str(request_path),
        "--result",
        str(pending_result_path),
    ]
    status = "failed"
    failure_reason: str | None = None
    return_code: int | None = None
    result: dict[str, Any] | None = None
    _atomic_write_bytes(stdout_path, b"")
    _atomic_write_bytes(stderr_path, b"")
    try:
        completed = subprocess.run(
            command,
            cwd=str(trial_dir),
            env=_sanitized_worker_env(Path(manifest["project_root"]), trial_dir),
            capture_output=True,
            timeout=int(manifest["trial_timeout_seconds"]),
            check=False,
        )
        return_code = completed.returncode
        _atomic_write_bytes(stdout_path, captured_bytes(completed.stdout))
        _atomic_write_bytes(stderr_path, captured_bytes(completed.stderr))
        if return_code != 0:
            failure_reason = f"runner exited non-zero: {return_code}"
        elif not pending_result_path.is_file():
            failure_reason = "runner exited zero but did not write result JSON"
        else:
            try:
                parsed = _decode_json(
                    pending_result_path.read_text(encoding="utf-8"),
                    source=str(pending_result_path),
                )
            except Exception as exc:  # noqa: BLE001
                failure_reason = f"runner result is invalid JSON: {exc}"
            else:
                if not isinstance(parsed, dict):
                    failure_reason = "runner result must be a JSON object"
                elif parsed.get("status") != "ok":
                    failure_reason = f"runner result status is not 'ok': {parsed.get('status')!r}"
                elif parsed.get("idempotency_key") != key:
                    failure_reason = "runner result idempotency_key does not match request"
                else:
                    result = parsed
                    _atomic_write_json(result_path, result)
                    status = "succeeded"
    except subprocess.TimeoutExpired as exc:
        _atomic_write_bytes(stdout_path, captured_bytes(exc.stdout))
        _atomic_write_bytes(stderr_path, captured_bytes(exc.stderr))
        failure_reason = f"runner timed out after {manifest['trial_timeout_seconds']} seconds"
    except Exception as exc:  # noqa: BLE001 - recorded in the immutable receipt
        failure_reason = f"runner orchestration exception: {type(exc).__name__}: {exc}"

    if pending_result_path.exists():
        pending_result_path.unlink()
    # Do not mint a receipt from a trial observed under drifting immutable inputs.
    # The caller repeats this check after the atomic receipt to close the remaining
    # receipt/ledger window as tightly as a path-based source can permit.
    _verify_file_records(manifest)
    finished_at = _utc_now()
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "authority": AUTHORITY,
        "run_id": manifest["run_id"],
        "manifest_sha256": manifest_sha,
        "trial_index": expected["index"],
        "trial_id": expected["id"],
        "idempotency_key": key,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "runner_exit_code": return_code,
        "request_path": str(request_path.relative_to(run_dir)),
        "request_sha256": request_sha,
        "result_path": str(result_path.relative_to(run_dir)) if status == "succeeded" else None,
        "result_sha256": sha256_file(result_path) if status == "succeeded" else None,
        "stdout_path": str(stdout_path.relative_to(run_dir)),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_path": str(stderr_path.relative_to(run_dir)),
        "stderr_sha256": sha256_file(stderr_path),
        "failure_reason": failure_reason,
    }
    receipt_path = run_dir / "receipts" / f"{key}.json"
    _atomic_write_json(receipt_path, receipt)
    return receipt_path, receipt


def _validate_completion(
    path: Path,
    *,
    run_id: str,
    manifest_sha: str,
    records: Sequence[Mapping[str, Any]],
    total_trials: int,
) -> dict[str, Any]:
    if len(records) != total_trials or any(record.get("status") != "succeeded" for record in records):
        raise IntegrityError("completion receipt exists without a complete all-success ledger")
    completion = _load_json(path)
    expected = {
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
        "completed_trials": total_trials,
        "successful_trials": total_trials,
        "failed_trials": 0,
        "ledger_tail_sha256": records[-1]["record_sha256"] if records else "0" * 64,
    }
    if not isinstance(completion, dict):
        raise IntegrityError(f"completion receipt is not an object: {path}")
    for field, value in expected.items():
        if completion.get(field) != value:
            raise IntegrityError(
                f"completion receipt is stale or mismatched at {field}: {completion.get(field)!r} != {value!r}"
            )
    if completion.get("state") != "COMPLETED":
        raise IntegrityError("completion receipt state is not COMPLETED")
    if completion.get("authority") != AUTHORITY or completion.get("promotion_authority") is not False:
        raise IntegrityError("completion receipt has invalid research-only authority")
    return completion


def _write_failure_artifact(run_dir: Path, name: str, exc: BaseException) -> None:
    _atomic_write_json(
        run_dir / name,
        {
            "schema_version": SCHEMA_VERSION,
            "state": "FAILED_CLOSED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            "recorded_at": _utc_now(),
        },
    )


def run_station(
    *,
    config_path: Path | str,
    runs_root: Path | str,
    run_id: str,
    project_root: Path | str,
    max_trials: int | None = None,
) -> dict[str, Any]:
    """Create or resume one immutable Station v3 run.

    ``max_trials`` is an operational slice only; it is not part of research intent.
    A sliced invocation ends in PAUSED and resumes idempotently on the next call.
    """

    if not RUN_ID_RE.fullmatch(str(run_id)) or ".." in str(run_id):
        raise ConfigError("run_id must be 3-128 safe characters and may not contain '..'")
    if max_trials is not None and (not isinstance(max_trials, int) or isinstance(max_trials, bool) or max_trials <= 0):
        raise ConfigError("max_trials must be a positive integer")
    root = Path(project_root).expanduser().resolve()
    config_file = Path(config_path).expanduser()
    config_file = (config_file if config_file.is_absolute() else root / config_file).resolve()
    if not config_file.is_file():
        raise ConfigError(f"config file not found: {config_file}")
    runs_dir = Path(runs_root).expanduser()
    runs_dir = (runs_dir if runs_dir.is_absolute() else root / runs_dir).resolve()
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    with ExclusiveRunLock(run_dir):
        manifest: dict[str, Any] | None = None
        manifest_sha = ""
        records: list[dict[str, Any]] = []
        try:
            integrity_refusal_path = run_dir / "integrity_refusal.json"
            if integrity_refusal_path.exists():
                raise IntegrityError(
                    "run previously recorded an integrity refusal and is permanently failed closed; "
                    "use a new run_id"
                )
            config = _validate_config_shape(_load_json(config_file))
            manifest_path = run_dir / "manifest.json"
            existing_manifest = manifest_path.exists()
            checkpoint_path = run_dir / "checkpoint.json"
            if existing_manifest and not checkpoint_path.exists():
                receipts_dir = run_dir / "receipts"
                trial_work_dir = run_dir / "trial_work"
                has_uncheckpointed_state = (
                    (run_dir / "trials.jsonl").exists()
                    or (run_dir / "completion.json").exists()
                    or (receipts_dir.is_dir() and any(receipts_dir.glob("*.json")))
                    or (trial_work_dir.is_dir() and any(trial_work_dir.iterdir()))
                )
                if has_uncheckpointed_state:
                    raise IntegrityError("run has state-bearing artifacts but checkpoint.json is missing")
            if existing_manifest:
                manifest, manifest_sha = _verify_manifest(
                    manifest_path,
                    config=config,
                    config_path=config_file,
                    project_root=root,
                    run_id=run_id,
                )
            else:
                # Old text logs are deliberately ignored.  State-bearing artifacts
                # without a manifest are not trusted.
                unsafe_existing = [
                    path
                    for path in run_dir.iterdir()
                    if path.name != ".station_v3.lock" and path.suffix.lower() != ".log"
                ]
                if unsafe_existing:
                    raise IntegrityError(
                        "run directory has state-bearing files but no manifest: "
                        + ", ".join(str(path.name) for path in unsafe_existing)
                    )
                manifest = _prepare_manifest(
                    config_path=config_file,
                    config=config,
                    project_root=root,
                    run_id=run_id,
                )
                _atomic_write_json(manifest_path, manifest)
                manifest_sha = sha256_file(manifest_path)

            expected = _expected_trials(manifest, manifest_sha)
            ledger_path = run_dir / "trials.jsonl"
            records = _load_ledger(ledger_path, manifest_sha=manifest_sha)
            records = _reconcile_receipts(
                run_dir,
                expected,
                records,
                run_id=run_id,
                manifest_sha=manifest_sha,
            )
            total = len(expected)
            if checkpoint_path.exists():
                _validate_checkpoint(
                    checkpoint_path,
                    run_id=run_id,
                    manifest_sha=manifest_sha,
                    records=records,
                    total_trials=total,
                )
            failed = [record for record in records if record["status"] == "failed"]
            if failed:
                _checkpoint(
                    run_dir,
                    state="FAILED",
                    run_id=run_id,
                    manifest_sha=manifest_sha,
                    records=records,
                    total_trials=total,
                    detail=f"failed trial is immutable: {failed[0]['trial_id']}",
                )
                raise TrialFailedError(
                    f"run contains failed trial {failed[0]['trial_id']!r}; use a new run_id after fixing immutable inputs"
                )

            completion_path = run_dir / "completion.json"
            if completion_path.exists():
                completion = _validate_completion(
                    completion_path,
                    run_id=run_id,
                    manifest_sha=manifest_sha,
                    records=records,
                    total_trials=total,
                )
                _checkpoint(
                    run_dir,
                    state="COMPLETED",
                    run_id=run_id,
                    manifest_sha=manifest_sha,
                    records=records,
                    total_trials=total,
                )
                return completion

            _checkpoint(
                run_dir,
                state="RUNNING",
                run_id=run_id,
                manifest_sha=manifest_sha,
                records=records,
                total_trials=total,
            )

            records_by_key = {record["idempotency_key"]: record for record in records}
            executed = 0
            for trial in expected:
                if trial["key"] in records_by_key:
                    continue
                _verify_file_records(manifest)
                receipt_path, receipt = _run_trial(
                    run_dir=run_dir,
                    manifest=manifest,
                    manifest_sha=manifest_sha,
                    expected=trial,
                )
                # Inputs and code must remain byte-identical for the whole trial,
                # not merely at process start.
                _verify_file_records(manifest)
                appended = _append_ledger_atomic(
                    ledger_path,
                    records,
                    _ledger_entry_from_receipt(
                        receipt_path,
                        receipt,
                        run_dir=run_dir,
                        manifest_sha=manifest_sha,
                    ),
                )
                records.append(appended)
                records_by_key[trial["key"]] = appended
                executed += 1
                state = "RUNNING" if receipt["status"] == "succeeded" else "FAILED"
                _checkpoint(
                    run_dir,
                    state=state,
                    run_id=run_id,
                    manifest_sha=manifest_sha,
                    records=records,
                    total_trials=total,
                    detail=receipt.get("failure_reason"),
                )
                if receipt["status"] != "succeeded":
                    failure = TrialFailedError(
                        f"trial {trial['id']!r} failed closed: {receipt.get('failure_reason')}"
                    )
                    _write_failure_artifact(run_dir, "run_failure.json", failure)
                    raise failure
                if max_trials is not None and executed >= max_trials and len(records) < total:
                    checkpoint = _checkpoint(
                        run_dir,
                        state="PAUSED",
                        run_id=run_id,
                        manifest_sha=manifest_sha,
                        records=records,
                        total_trials=total,
                        detail=f"operational max_trials slice reached: {max_trials}",
                    )
                    return checkpoint

            if len(records) != total or any(record["status"] != "succeeded" for record in records):
                raise IntegrityError("all manifest trials were visited but the successful ledger is incomplete")
            completion = {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "manifest_sha256": manifest_sha,
                "state": "COMPLETED",
                "completed_trials": total,
                "successful_trials": total,
                "failed_trials": 0,
                "ledger_tail_sha256": records[-1]["record_sha256"] if records else "0" * 64,
                "completed_at": _utc_now(),
                "authority": AUTHORITY,
                "promotion_authority": False,
            }
            _atomic_write_json(completion_path, completion)
            _checkpoint(
                run_dir,
                state="COMPLETED",
                run_id=run_id,
                manifest_sha=manifest_sha,
                records=records,
                total_trials=total,
            )
            return completion
        except KeyboardInterrupt as exc:
            if manifest is not None and manifest_sha:
                _checkpoint(
                    run_dir,
                    state="INTERRUPTED",
                    run_id=run_id,
                    manifest_sha=manifest_sha,
                    records=records,
                    total_trials=len(manifest.get("trials", [])),
                    detail="operator interruption; safe to resume with identical immutable files",
                )
            raise exc
        except HashDriftError as exc:
            _write_failure_artifact(run_dir, "integrity_refusal.json", exc)
            raise
        except StationV3Error as exc:
            _write_failure_artifact(run_dir, "orchestrator_failure.json", exc)
            raise
        except Exception as exc:  # noqa: BLE001 - never hide orchestration defects
            _write_failure_artifact(run_dir, "orchestrator_failure.json", exc)
            raise StationV3Error(f"unexpected Station v3 exception: {type(exc).__name__}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Explicit Station v3 JSON config")
    parser.add_argument("--runs-root", required=True, help="Directory containing unique run_id directories")
    parser.add_argument("--run-id", required=True, help="Unique run id; use the same id only to resume")
    parser.add_argument("--project-root", default=".", help="Base for every relative config path (default: cwd)")
    parser.add_argument("--max-trials", type=int, help="Optional operational slice; leaves run PAUSED, not complete")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_station(
            config_path=args.config,
            runs_root=args.runs_root,
            run_id=args.run_id,
            project_root=args.project_root,
            max_trials=args.max_trials,
        )
    except StationV3Error as exc:
        print(f"STATION_V3_FAIL_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
