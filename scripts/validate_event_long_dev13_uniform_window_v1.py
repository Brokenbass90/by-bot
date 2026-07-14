#!/usr/bin/env python3
"""Validate and load a hash-pinned virtual uniform closed-M5 window.

This module is deliberately data-only.  It verifies immutable source lineage,
closed-bar boundaries, exact M5 contiguity, and deterministic timestamp crops.
It never imports a strategy, computes outcomes, contacts a network, or writes
market data.  A later research runner may use :func:`load_uniform_symbol_rows`
only after the manifest has been frozen and hash-pinned.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
OHLCV_KEYS = ("ts", "o", "h", "l", "c", "v")
EXPECTED_KIND = "uniform_closed_m5_virtual_window_manifest_v1"
EXPECTED_INTERVAL_MS = 300_000
EXPECTED_MANIFEST_KEYS = {
    "schema_version", "kind", "name", "frozen_at_utc", "research_only",
    "closed_bars_only", "no_parameter_scan", "performance_computed",
    "live_or_broker_calls", "physical_data_mutated", "materialization",
    "source_manifest", "loader_contract", "window", "symbols", "snapshots",
    "manifest_fingerprint_sha256",
}
EXPECTED_WINDOW_KEYS = {
    "start_ts", "start_utc", "end_ts_exclusive", "end_utc_exclusive",
    "interval_ms", "expected_rows_per_symbol", "bar_timestamp_semantics",
    "end_semantics",
}
EXPECTED_LOADER_KEYS = {
    "path", "sha256", "selection", "requires_exact_contiguous_grid",
    "forming_or_future_tail_allowed",
}
EXPECTED_SOURCE_REF_KEYS = {"path", "sha256", "kind", "schema_version"}
EXPECTED_SNAPSHOT_KEYS = {
    "source_path", "source_sha256", "source_manifest_record_sha256",
    "slice_first_ts", "slice_last_ts", "slice_rows", "virtual_slice_sha256",
}


class UniformWindowError(ValueError):
    """The uniform-window manifest or one of its immutable inputs is invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _require_exact_keys(value: object, expected: set[str], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise UniformWindowError(f"{name} schema keys changed")
    return value


def _repo_file(root: Path, raw: object) -> Path:
    text = str(raw or "")
    relative = Path(text)
    if not text or relative.is_absolute() or "\\" in text:
        raise UniformWindowError(f"path must be non-empty and repo-relative: {text!r}")
    if any(part in {"", ".", ".."} for part in relative.parts) or ".git" in relative.parts:
        raise UniformWindowError(f"unsafe repo-relative path: {text!r}")
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise UniformWindowError(f"path contains a symlink: {text!r}")
    return cursor


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise UniformWindowError(f"input is not a regular file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UniformWindowError(f"invalid JSON input {path}: {exc}") from exc


def _utc_ms(text: object) -> int:
    raw = str(text or "")
    if not raw.endswith("Z"):
        raise UniformWindowError(f"UTC timestamp must end in Z: {raw!r}")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError as exc:
        raise UniformWindowError(f"invalid UTC timestamp: {raw!r}") from exc
    if parsed.tzinfo != timezone.utc:
        raise UniformWindowError(f"timestamp is not UTC: {raw!r}")
    return int(parsed.timestamp() * 1000)


def _number(value: object, *, field: str, symbol: str, index: int) -> float:
    if isinstance(value, bool):
        raise UniformWindowError(f"boolean {field} at {symbol}:{index}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise UniformWindowError(f"non-numeric {field} at {symbol}:{index}") from exc
    if not math.isfinite(result):
        raise UniformWindowError(f"non-finite {field} at {symbol}:{index}")
    return result


def _manifest_fingerprint(manifest: Mapping[str, Any]) -> str:
    frozen = dict(manifest)
    frozen.pop("manifest_fingerprint_sha256", None)
    return canonical_sha256(frozen)


def _validate_manifest_header(manifest: Mapping[str, Any]) -> tuple[tuple[str, ...], int, int, int]:
    _require_exact_keys(manifest, EXPECTED_MANIFEST_KEYS, "uniform-window manifest")
    if manifest.get("schema_version") != 1 or manifest.get("kind") != EXPECTED_KIND:
        raise UniformWindowError("uniform-window schema/kind mismatch")
    if not all(manifest.get(key) is True for key in (
        "research_only", "closed_bars_only", "no_parameter_scan",
    )):
        raise UniformWindowError("research-only closed-bar flags are mandatory")
    if any(manifest.get(key) is not False for key in (
        "performance_computed", "live_or_broker_calls", "physical_data_mutated",
    )):
        raise UniformWindowError("outcome/live/data-mutation flags must remain false")
    if manifest.get("materialization") != "virtual_timestamp_crop_of_hash_pinned_sources":
        raise UniformWindowError("only the frozen virtual timestamp crop is accepted")
    if manifest.get("manifest_fingerprint_sha256") != _manifest_fingerprint(manifest):
        raise UniformWindowError("uniform-window manifest fingerprint mismatch")

    symbols_raw = manifest.get("symbols")
    if not isinstance(symbols_raw, list) or not symbols_raw:
        raise UniformWindowError("symbols must be a non-empty list")
    symbols = tuple(str(item) for item in symbols_raw)
    if len(symbols) != len(set(symbols)) or any(not symbol.endswith("USDT") for symbol in symbols):
        raise UniformWindowError("symbols must be unique canonical USDT names")

    window = _require_exact_keys(manifest.get("window"), EXPECTED_WINDOW_KEYS, "window")
    try:
        start = int(window["start_ts"])
        end = int(window["end_ts_exclusive"])
        interval = int(window["interval_ms"])
        expected_rows = int(window["expected_rows_per_symbol"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UniformWindowError("window contract is malformed") from exc
    if interval != EXPECTED_INTERVAL_MS or start <= 0 or end <= start:
        raise UniformWindowError("window must be positive closed M5 boundaries")
    if start % interval or end % interval or (end - start) % interval:
        raise UniformWindowError("window is not aligned to exact M5 boundaries")
    if expected_rows != (end - start) // interval:
        raise UniformWindowError("expected row count does not match the M5 grid")
    if _utc_ms(window.get("start_utc")) != start or _utc_ms(window.get("end_utc_exclusive")) != end:
        raise UniformWindowError("UTC labels do not match epoch boundaries")
    frozen_at = _utc_ms(manifest.get("frozen_at_utc"))
    if end > frozen_at:
        raise UniformWindowError("uniform window ends after the manifest freeze timestamp")
    if window.get("bar_timestamp_semantics") != "open_time_ms":
        raise UniformWindowError("bar timestamps must be M5 open times")
    if window.get("end_semantics") != "exact_close_of_final_included_M5_bar":
        raise UniformWindowError("end-exclusive must be the exact final M5 close")
    return symbols, start, end, expected_rows


def validate_uniform_window_manifest(
    root: Path,
    manifest_path: Path,
    *,
    verify_rows: bool,
) -> dict[str, Any]:
    """Validate immutable lineage; optionally parse every selected M5 row."""
    root = root.resolve()
    if manifest_path.is_absolute():
        try:
            manifest_relative = manifest_path.relative_to(root).as_posix()
        except ValueError as exc:
            raise UniformWindowError("manifest must remain inside the repository") from exc
    else:
        manifest_relative = manifest_path.as_posix()
    manifest_path = _repo_file(root, manifest_relative)
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, Mapping):
        raise UniformWindowError("uniform-window manifest root must be an object")
    symbols, start, end, expected_rows = _validate_manifest_header(manifest)

    loader = _require_exact_keys(
        manifest.get("loader_contract"), EXPECTED_LOADER_KEYS, "loader contract"
    )
    loader_path = _repo_file(root, loader.get("path"))
    if sha256_file(loader_path) != loader.get("sha256"):
        raise UniformWindowError("pinned uniform-window loader changed")
    if loader.get("selection") != "start_ts_lte_row_ts_lt_end_ts_exclusive":
        raise UniformWindowError("virtual crop selection changed")
    if loader.get("requires_exact_contiguous_grid") is not True:
        raise UniformWindowError("exact contiguous grid is mandatory")
    if loader.get("forming_or_future_tail_allowed") is not False:
        raise UniformWindowError("forming/future tails are forbidden")

    source_ref = _require_exact_keys(
        manifest.get("source_manifest"), EXPECTED_SOURCE_REF_KEYS, "source-manifest reference"
    )
    source_path = _repo_file(root, source_ref.get("path"))
    if sha256_file(source_path) != source_ref.get("sha256"):
        raise UniformWindowError("source manifest hash mismatch")
    source = _read_json(source_path)
    if not isinstance(source, Mapping):
        raise UniformWindowError("source manifest root must be an object")
    if source.get("kind") != source_ref.get("kind") or source.get("schema_version") != source_ref.get("schema_version"):
        raise UniformWindowError("source manifest identity changed")
    source_pins = source.get("input_snapshots")
    source_records = source.get("snapshots")
    if not isinstance(source_pins, Mapping) or not isinstance(source_records, Mapping):
        raise UniformWindowError("source snapshot maps are missing")
    if set(source_pins) != set(symbols) or set(source_records) != set(symbols):
        raise UniformWindowError("source manifest symbol set differs from uniform cohort")

    rows_contract = manifest.get("snapshots")
    if not isinstance(rows_contract, Mapping) or set(rows_contract) != set(symbols):
        raise UniformWindowError("uniform snapshot contract is incomplete")

    checked: list[dict[str, Any]] = []
    for symbol in symbols:
        row_contract = rows_contract[symbol]
        source_pin = source_pins[symbol]
        source_record = source_records[symbol]
        if not all(isinstance(item, Mapping) for item in (row_contract, source_pin, source_record)):
            raise UniformWindowError(f"malformed source contract for {symbol}")
        _require_exact_keys(row_contract, EXPECTED_SNAPSHOT_KEYS, f"snapshot contract for {symbol}")
        if row_contract.get("source_path") != source_pin.get("path") or row_contract.get("source_sha256") != source_pin.get("sha256"):
            raise UniformWindowError(f"source pin mismatch for {symbol}")
        if row_contract.get("source_path") != source_record.get("path") or row_contract.get("source_sha256") != source_record.get("sha256"):
            raise UniformWindowError(f"source snapshot record mismatch for {symbol}")
        if row_contract.get("source_manifest_record_sha256") != canonical_sha256(source_record):
            raise UniformWindowError(f"source lineage fingerprint mismatch for {symbol}")
        if source_record.get("quality_pass") is not True or int(source_record.get("max_internal_gap_bars", -1)) != 0:
            raise UniformWindowError(f"source is not contiguous/quality-passed for {symbol}")
        if int(source_record.get("first_ts", -1)) != start or int(source_record.get("last_ts", -1)) < end - EXPECTED_INTERVAL_MS:
            raise UniformWindowError(f"source does not cover the uniform window for {symbol}")
        if int(row_contract.get("slice_first_ts", -1)) != start or int(row_contract.get("slice_last_ts", -1)) != end - EXPECTED_INTERVAL_MS:
            raise UniformWindowError(f"slice boundaries changed for {symbol}")
        if int(row_contract.get("slice_rows", -1)) != expected_rows:
            raise UniformWindowError(f"slice row count changed for {symbol}")
        if not _is_sha256(row_contract.get("virtual_slice_sha256")):
            raise UniformWindowError(f"virtual slice hash is missing for {symbol}")

        snapshot_path = _repo_file(root, row_contract.get("source_path"))
        actual_source_sha = sha256_file(snapshot_path)
        if actual_source_sha != row_contract.get("source_sha256"):
            raise UniformWindowError(f"immutable source snapshot changed for {symbol}")

        item = {
            "symbol": symbol,
            "source_sha256": actual_source_sha,
            "slice_rows": expected_rows,
            "virtual_slice_sha256": row_contract["virtual_slice_sha256"],
        }
        if verify_rows:
            selected = _load_and_validate_rows(
                snapshot_path,
                symbol=symbol,
                start=start,
                end=end,
                expected_rows=expected_rows,
            )
            actual_virtual_sha = canonical_sha256(selected)
            if actual_virtual_sha != row_contract.get("virtual_slice_sha256"):
                raise UniformWindowError(f"virtual slice content hash mismatch for {symbol}")
            item["rows_verified"] = True
        checked.append(item)

    return {
        "schema": "uniform_closed_m5_virtual_window_validation_v1",
        "manifest": manifest_path.relative_to(root).as_posix(),
        "manifest_sha256": sha256_file(manifest_path),
        "manifest_fingerprint_sha256": manifest["manifest_fingerprint_sha256"],
        "source_manifest_sha256": source_ref["sha256"],
        "window_start_ts": start,
        "window_end_ts_exclusive": end,
        "symbols": list(symbols),
        "rows_per_symbol": expected_rows,
        "source_hashes_verified": True,
        "rows_verified": verify_rows,
        "performance_computed": False,
        "live_or_broker_calls": False,
        "integrity_pass": True,
        "snapshots": checked,
    }


def _load_and_validate_rows(
    path: Path,
    *,
    symbol: str,
    start: int,
    end: int,
    expected_rows: int,
) -> list[dict[str, object]]:
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise UniformWindowError(f"snapshot is not an array for {symbol}")
    selected: list[dict[str, object]] = []
    expected_ts = start
    for index, raw in enumerate(payload):
        if not isinstance(raw, Mapping) or set(raw) != set(OHLCV_KEYS):
            raise UniformWindowError(f"non-canonical OHLCV row at {symbol}:{index}")
        raw_ts = raw["ts"]
        if isinstance(raw_ts, bool):
            raise UniformWindowError(f"boolean timestamp at {symbol}:{index}")
        try:
            ts_float = float(raw_ts)
            ts = int(raw_ts)
        except (TypeError, ValueError, OverflowError) as exc:
            raise UniformWindowError(f"invalid timestamp at {symbol}:{index}") from exc
        if not math.isfinite(ts_float) or ts_float != ts:
            raise UniformWindowError(f"inexact timestamp at {symbol}:{index}")
        if ts < start or ts >= end:
            continue
        if ts != expected_ts:
            raise UniformWindowError(
                f"non-contiguous M5 grid for {symbol}: expected {expected_ts}, got {ts}"
            )
        o, h, l, c, v = (
            _number(raw[key], field=key, symbol=symbol, index=index)
            for key in OHLCV_KEYS[1:]
        )
        if not (o > 0 and h > 0 and l > 0 and c > 0 and v >= 0):
            raise UniformWindowError(f"invalid OHLCV sign at {symbol}:{index}")
        if h < max(o, l, c) or l > min(o, h, c):
            raise UniformWindowError(f"OHLC invariant failed at {symbol}:{index}")
        selected.append({key: raw[key] for key in OHLCV_KEYS})
        expected_ts += EXPECTED_INTERVAL_MS
    if len(selected) != expected_rows or expected_ts != end:
        raise UniformWindowError(
            f"uniform crop incomplete for {symbol}: rows={len(selected)} expected={expected_rows}"
        )
    return selected


def load_uniform_symbol_rows(
    root: Path,
    manifest_path: Path,
    symbol: str,
) -> list[dict[str, object]]:
    """Return one exact virtual crop after full manifest/source validation."""
    receipt = validate_uniform_window_manifest(root, manifest_path, verify_rows=False)
    if symbol not in receipt["symbols"]:
        raise UniformWindowError(f"symbol is outside the frozen cohort: {symbol}")
    manifest = _read_json(manifest_path)
    row_contract = manifest["snapshots"][symbol]
    window = manifest["window"]
    rows = _load_and_validate_rows(
        _repo_file(root.resolve(), row_contract["source_path"]),
        symbol=symbol,
        start=int(window["start_ts"]),
        end=int(window["end_ts_exclusive"]),
        expected_rows=int(window["expected_rows_per_symbol"]),
    )
    if canonical_sha256(rows) != row_contract["virtual_slice_sha256"]:
        raise UniformWindowError(f"virtual slice content hash mismatch for {symbol}")
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = validate_uniform_window_manifest(
            args.root,
            args.manifest,
            verify_rows=not args.metadata_only,
        )
        exit_code = 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError, UniformWindowError) as exc:
        payload = {
            "schema": "uniform_closed_m5_virtual_window_validation_v1",
            "integrity_pass": False,
            "performance_computed": False,
            "live_or_broker_calls": False,
            "error": str(exc),
        }
        exit_code = 2
    print(json.dumps(payload, indent=None if args.compact else 2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
