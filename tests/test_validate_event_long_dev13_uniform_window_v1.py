from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.validate_event_long_dev13_uniform_window_v1 import (
    UniformWindowError,
    canonical_sha256,
    load_uniform_symbol_rows,
    sha256_file,
    validate_uniform_window_manifest,
)


START = 1_800_000_000_000
INTERVAL = 300_000
END = START + 3 * INTERVAL
SYMBOLS = ("AAAUSDT", "BBBUSDT")


def _row(ts: int, close: float = 10.0) -> dict[str, float | int]:
    return {"ts": ts, "o": 10.0, "h": 11.0, "l": 9.0, "c": close, "v": 100.0}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    loader_source = Path(__file__).resolve().parents[1] / "scripts" / "validate_event_long_dev13_uniform_window_v1.py"
    loader_path = root / "scripts" / loader_source.name
    loader_path.parent.mkdir(parents=True)
    loader_path.write_bytes(loader_source.read_bytes())

    snapshots: dict[str, dict] = {}
    pins: dict[str, dict] = {}
    manifest_rows: dict[str, dict] = {}
    for offset, symbol in enumerate(SYMBOLS):
        rows = [_row(START + index * INTERVAL, close=10.0 + offset) for index in range(4)]
        path = root / "data_cache" / "immutable" / f"{symbol}.json"
        _write_json(path, rows)
        relative = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        source_record = {
            "path": relative,
            "sha256": digest,
            "rows": 4,
            "first_ts": START,
            "last_ts": END,
            "max_internal_gap_bars": 0,
            "quality_pass": True,
            "provenance": [{"path": f"legacy/{symbol}.json", "sha256": hashlib.sha256(symbol.encode()).hexdigest()}],
        }
        snapshots[symbol] = source_record
        pins[symbol] = {"path": relative, "sha256": digest}
        crop = rows[:3]
        manifest_rows[symbol] = {
            "source_path": relative,
            "source_sha256": digest,
            "source_manifest_record_sha256": canonical_sha256(source_record),
            "slice_first_ts": START,
            "slice_last_ts": END - INTERVAL,
            "slice_rows": 3,
            "virtual_slice_sha256": canonical_sha256(crop),
        }

    source_manifest = {
        "schema_version": 1,
        "kind": "test_source_manifest",
        "input_snapshots": pins,
        "snapshots": snapshots,
    }
    source_path = root / "data_cache" / "immutable" / "source_manifest.json"
    _write_json(source_path, source_manifest)
    manifest = {
        "schema_version": 1,
        "kind": "uniform_closed_m5_virtual_window_manifest_v1",
        "name": "unit_uniform_window",
        "frozen_at_utc": "2027-01-15T09:00:00Z",
        "research_only": True,
        "closed_bars_only": True,
        "no_parameter_scan": True,
        "performance_computed": False,
        "live_or_broker_calls": False,
        "physical_data_mutated": False,
        "materialization": "virtual_timestamp_crop_of_hash_pinned_sources",
        "source_manifest": {
            "path": source_path.relative_to(root).as_posix(),
            "sha256": sha256_file(source_path),
            "kind": "test_source_manifest",
            "schema_version": 1,
        },
        "loader_contract": {
            "path": loader_path.relative_to(root).as_posix(),
            "sha256": sha256_file(loader_path),
            "selection": "start_ts_lte_row_ts_lt_end_ts_exclusive",
            "requires_exact_contiguous_grid": True,
            "forming_or_future_tail_allowed": False,
        },
        "window": {
            "start_ts": START,
            "start_utc": "2027-01-15T08:00:00Z",
            "end_ts_exclusive": END,
            "end_utc_exclusive": "2027-01-15T08:15:00Z",
            "interval_ms": INTERVAL,
            "expected_rows_per_symbol": 3,
            "bar_timestamp_semantics": "open_time_ms",
            "end_semantics": "exact_close_of_final_included_M5_bar",
        },
        "symbols": list(SYMBOLS),
        "snapshots": manifest_rows,
    }
    manifest["manifest_fingerprint_sha256"] = canonical_sha256(manifest)
    manifest_path = root / "configs" / "preregistered" / "uniform.json"
    _write_json(manifest_path, manifest)
    return root, manifest_path


def test_deep_validation_and_loader_return_exact_closed_m5_crop(tmp_path: Path) -> None:
    root, manifest_path = _fixture(tmp_path)

    receipt = validate_uniform_window_manifest(root, manifest_path, verify_rows=True)
    rows = load_uniform_symbol_rows(root, manifest_path, "AAAUSDT")

    assert receipt["integrity_pass"] is True
    assert receipt["rows_verified"] is True
    assert receipt["performance_computed"] is False
    assert len(rows) == 3
    assert [row["ts"] for row in rows] == [START, START + INTERVAL, START + 2 * INTERVAL]
    assert all(int(row["ts"]) < END for row in rows)


def test_metadata_validation_still_hash_checks_every_source(tmp_path: Path) -> None:
    root, manifest_path = _fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = root / manifest["snapshots"]["AAAUSDT"]["source_path"]
    source.write_text(source.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(UniformWindowError, match="source snapshot changed"):
        validate_uniform_window_manifest(root, manifest_path, verify_rows=False)


def test_gap_or_forming_tail_cannot_be_hidden_by_manifest_hash(tmp_path: Path) -> None:
    root, manifest_path = _fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    symbol = "AAAUSDT"
    source_path = root / manifest["snapshots"][symbol]["source_path"]
    rows = json.loads(source_path.read_text(encoding="utf-8"))
    rows.pop(1)
    _write_json(source_path, rows)

    source_manifest_path = root / manifest["source_manifest"]["path"]
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    changed = source_manifest["snapshots"][symbol]
    changed["sha256"] = sha256_file(source_path)
    source_manifest["input_snapshots"][symbol]["sha256"] = changed["sha256"]
    changed["rows"] = 3
    _write_json(source_manifest_path, source_manifest)
    manifest["source_manifest"]["sha256"] = sha256_file(source_manifest_path)
    manifest["snapshots"][symbol]["source_sha256"] = changed["sha256"]
    manifest["snapshots"][symbol]["source_manifest_record_sha256"] = canonical_sha256(changed)
    manifest["manifest_fingerprint_sha256"] = canonical_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_fingerprint_sha256"}
    )
    _write_json(manifest_path, manifest)

    with pytest.raises(UniformWindowError, match="non-contiguous M5 grid"):
        validate_uniform_window_manifest(root, manifest_path, verify_rows=True)


def test_manifest_fingerprint_and_frozen_cohort_fail_closed(tmp_path: Path) -> None:
    root, manifest_path = _fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed = copy.deepcopy(manifest)
    changed["window"]["end_ts_exclusive"] += INTERVAL
    _write_json(manifest_path, changed)

    with pytest.raises(UniformWindowError, match="fingerprint"):
        validate_uniform_window_manifest(root, manifest_path, verify_rows=False)

    _write_json(manifest_path, manifest)
    with pytest.raises(UniformWindowError, match="outside the frozen cohort"):
        load_uniform_symbol_rows(root, manifest_path, "CCCUSDT")


def test_window_must_be_closed_at_or_before_manifest_freeze(tmp_path: Path) -> None:
    root, manifest_path = _fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frozen_at_utc"] = "2027-01-15T08:10:00Z"
    manifest["manifest_fingerprint_sha256"] = canonical_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_fingerprint_sha256"}
    )
    _write_json(manifest_path, manifest)

    with pytest.raises(UniformWindowError, match="ends after.*freeze"):
        validate_uniform_window_manifest(root, manifest_path, verify_rows=False)


def test_manifest_schema_and_freeze_timestamp_fail_closed(tmp_path: Path) -> None:
    root, manifest_path = _fixture(tmp_path)
    original = json.loads(manifest_path.read_text(encoding="utf-8"))

    unknown = copy.deepcopy(original)
    unknown["monthly_returns"] = [1.0]
    unknown["manifest_fingerprint_sha256"] = canonical_sha256(
        {key: value for key, value in unknown.items() if key != "manifest_fingerprint_sha256"}
    )
    _write_json(manifest_path, unknown)
    with pytest.raises(UniformWindowError, match="schema keys"):
        validate_uniform_window_manifest(root, manifest_path, verify_rows=False)

    malformed = copy.deepcopy(original)
    malformed["frozen_at_utc"] = "2027-01-15T09:00:00+01:00"
    malformed["manifest_fingerprint_sha256"] = canonical_sha256(
        {key: value for key, value in malformed.items() if key != "manifest_fingerprint_sha256"}
    )
    _write_json(manifest_path, malformed)
    with pytest.raises(UniformWindowError, match="must end in Z"):
        validate_uniform_window_manifest(root, manifest_path, verify_rows=False)
