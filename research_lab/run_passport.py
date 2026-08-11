#!/usr/bin/env python3
"""Fail-closed passport for ad-hoc research runs.

The passport binds a result to explicit code, inputs, universe, timeframe,
window, costs, labels, split design, search budget, and sealed-holdout policy.
It has no broker or promotion authority.  A temporal input that overlaps a
declared sealed holdout is rejected *before the input file is opened*.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


SCHEMA_ID = "research_run_passport_v1"
REQUEST_SCHEMA_ID = "research_run_passport_request_v1"
AUTHORITY = "research_only_no_live_or_promotion"


class PassportError(RuntimeError):
    """The run cannot produce admissible research evidence."""


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


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: Any, *, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise PassportError(f"{field} must be an ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise PassportError(f"{field} is not valid ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise PassportError(f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _window(value: Any, *, field: str) -> tuple[dt.datetime, dt.datetime]:
    if not isinstance(value, Mapping):
        raise PassportError(f"{field} must be an object")
    start = _parse_utc(value.get("start_utc"), field=f"{field}.start_utc")
    end = _parse_utc(value.get("end_utc_exclusive"), field=f"{field}.end_utc_exclusive")
    if start >= end:
        raise PassportError(f"{field} must be a non-empty [start,end) window")
    return start, end


def _overlaps(left: tuple[dt.datetime, dt.datetime], right: tuple[dt.datetime, dt.datetime]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _explicit_file(project_root: Path, raw: Any, *, field: str) -> Path:
    if not isinstance(raw, str) or not raw.strip() or any(char in raw for char in "*?["):
        raise PassportError(f"{field} must be an explicit file path")
    unresolved = Path(raw).expanduser()
    path = (unresolved if unresolved.is_absolute() else project_root / unresolved).resolve()
    if not path.is_file():
        raise PassportError(f"{field} is not a file: {path}")
    return path


def _validate_request(spec: Any) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise PassportError("passport request must be an object")
    if spec.get("schema_id") != REQUEST_SCHEMA_ID:
        raise PassportError(f"schema_id must equal {REQUEST_SCHEMA_ID!r}")
    if spec.get("authority") != AUTHORITY:
        raise PassportError(f"authority must equal {AUTHORITY!r}")
    if spec.get("promotion_authority") is not False:
        raise PassportError("promotion_authority must be false")
    if spec.get("live_or_broker_calls") is not False:
        raise PassportError("live_or_broker_calls must be false")
    experiment_id = spec.get("experiment_id")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise PassportError("experiment_id is required")

    code_paths = spec.get("code_paths")
    inputs = spec.get("inputs")
    if not isinstance(code_paths, list) or not code_paths:
        raise PassportError("code_paths must be a non-empty list")
    if not isinstance(inputs, list) or not inputs:
        raise PassportError("inputs must be a non-empty list")

    measurement = spec.get("measurement_contract")
    if not isinstance(measurement, dict):
        raise PassportError("measurement_contract must be an object")
    for field in ("engine", "timeframe", "costs", "label_contract", "split_contract"):
        if field not in measurement:
            raise PassportError(f"measurement_contract.{field} is required")
    universe = measurement.get("universe")
    if not isinstance(universe, list) or not universe or not all(isinstance(x, str) and x for x in universe):
        raise PassportError("measurement_contract.universe must be a non-empty symbol list")
    analysis_window = _window(measurement.get("window"), field="measurement_contract.window")

    search = spec.get("search_contract")
    if not isinstance(search, dict):
        raise PassportError("search_contract must be an object")
    variant_count = search.get("variant_count")
    if not isinstance(variant_count, int) or isinstance(variant_count, bool) or variant_count < 1:
        raise PassportError("search_contract.variant_count must be a positive integer")
    if not isinstance(search.get("random_seed"), int) or isinstance(search.get("random_seed"), bool):
        raise PassportError("search_contract.random_seed must be an integer")
    if search.get("pre_registered") is not True:
        raise PassportError("search_contract.pre_registered must be true")

    sealed: list[tuple[str, tuple[dt.datetime, dt.datetime]]] = []
    for index, raw in enumerate(spec.get("sealed_holdouts") or []):
        if not isinstance(raw, dict) or raw.get("must_not_be_read") is not True:
            raise PassportError(f"sealed_holdouts[{index}] must declare must_not_be_read=true")
        holdout_id = raw.get("id")
        if not isinstance(holdout_id, str) or not holdout_id:
            raise PassportError(f"sealed_holdouts[{index}].id is required")
        sealed.append((holdout_id, _window(raw, field=f"sealed_holdouts[{index}]")))

    for holdout_id, holdout_window in sealed:
        if _overlaps(analysis_window, holdout_window):
            raise PassportError(f"analysis window overlaps sealed holdout {holdout_id}")

    # Validate every declared data boundary before any input file is opened.
    for index, raw in enumerate(inputs):
        if not isinstance(raw, dict):
            raise PassportError(f"inputs[{index}] must be an object")
        if not isinstance(raw.get("contains_sealed_holdout"), bool):
            raise PassportError(f"inputs[{index}].contains_sealed_holdout must be explicit")
        if raw["contains_sealed_holdout"]:
            raise PassportError(f"inputs[{index}] contains a sealed holdout and must not be opened")
        if raw.get("temporal_data") is True:
            input_window = _window(raw.get("data_window"), field=f"inputs[{index}].data_window")
            for holdout_id, holdout_window in sealed:
                if _overlaps(input_window, holdout_window):
                    raise PassportError(
                        f"inputs[{index}] declared data window overlaps sealed holdout {holdout_id}"
                    )
        elif raw.get("temporal_data") is not False:
            raise PassportError(f"inputs[{index}].temporal_data must be explicit")
    return spec


def build_passport(spec: Any, *, project_root: Path) -> dict[str, Any]:
    request = _validate_request(spec)
    root = project_root.resolve()

    code = []
    for index, raw in enumerate(request["code_paths"]):
        path = _explicit_file(root, raw, field=f"code_paths[{index}]")
        code.append({"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size})

    inputs = []
    for index, raw in enumerate(request["inputs"]):
        path = _explicit_file(root, raw.get("path"), field=f"inputs[{index}].path")
        inputs.append(
            {
                "path": str(path),
                "role": raw.get("role"),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "temporal_data": raw["temporal_data"],
                "data_window": raw.get("data_window"),
                "contains_sealed_holdout": False,
            }
        )

    comparison_contract = {
        "code": code,
        "inputs": inputs,
        "measurement_contract": request["measurement_contract"],
        "search_contract": request["search_contract"],
    }
    passport = {
        "schema_id": SCHEMA_ID,
        "authority": AUTHORITY,
        "promotion_authority": False,
        "live_or_broker_calls": False,
        "experiment_id": request["experiment_id"],
        "created_at_utc": _utc_now(),
        "code": code,
        "inputs": inputs,
        "measurement_contract": request["measurement_contract"],
        "search_contract": request["search_contract"],
        "sealed_holdouts": request.get("sealed_holdouts") or [],
        "sealed_holdout_rows_decoded": 0,
        "comparison_contract_sha256": _sha256_bytes(_canonical_json(comparison_contract)),
        "request_sha256": _sha256_bytes(_canonical_json(request)),
    }
    passport["passport_sha256"] = _sha256_bytes(_canonical_json(passport))
    return passport


def validate_passport(passport: Any) -> dict[str, Any]:
    if not isinstance(passport, dict) or passport.get("schema_id") != SCHEMA_ID:
        raise PassportError("invalid passport schema")
    expected = passport.get("passport_sha256")
    unsigned = dict(passport)
    unsigned.pop("passport_sha256", None)
    actual = _sha256_bytes(_canonical_json(unsigned))
    if expected != actual:
        raise PassportError("passport hash mismatch")
    if passport.get("authority") != AUTHORITY or passport.get("promotion_authority") is not False:
        raise PassportError("passport authority drift")
    return passport


def assert_comparable(left: Mapping[str, Any], right: Mapping[str, Any]) -> None:
    validate_passport(dict(left))
    validate_passport(dict(right))
    if left.get("comparison_contract_sha256") != right.get("comparison_contract_sha256"):
        raise PassportError("run passports have different measurement conditions")


def write_passport(path: Path, passport: Mapping[str, Any]) -> None:
    validate_passport(dict(passport))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json(passport)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise PassportError(f"passport is write-once and already exists: {path}") from exc
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    passport = build_passport(spec, project_root=args.project_root)
    write_passport(args.output, passport)
    print(json.dumps(passport, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
