from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.materialize_pump_exhaustion_snapshots import (
    MaterializationError,
    materialize_snapshots,
)


START = 1_800_000_000_000
INTERVAL = 300_000
END = START + 4 * INTERVAL
SYMBOLS = ("AAAUSDT", "BBBUSDT", "CCCUSDT")


def _row(ts: int, close: float = 10.5) -> dict:
    return {"ts": ts, "o": 10.0, "h": 11.0, "l": 9.5, "c": close, "v": 100.0}


def _seq(ts: int, close: float = 10.5) -> list[float]:
    return [ts, 10.0, 11.0, 9.5, close, 100.0]


def _prepare(tmp_path: Path, *, min_coverage: float = 1.0, max_gap: int = 0) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    cache = root / "data_cache"
    config_dir = root / "configs" / "preregistered"
    cache.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    config = {
        "name": "pump_exhaustion_test",
        "research_only": True,
        "frozen_before_results": True,
        "no_parameter_scan": True,
        "live_or_broker_calls": False,
        "strategy": {
            "id": "pump_exhaustion_unwind_short_v1",
            "physical_side_identity": "short_only",
            "signal_side": "short",
            "live_ready": False,
        },
        "data": {
            "cache_source": "data_cache",
            "symbols": list(SYMBOLS),
            "window_start_ts": START,
            "window_end_ts_exclusive": END,
            "interval_ms": INTERVAL,
            "min_coverage": min_coverage,
            "max_internal_gap_bars": max_gap,
            "input_snapshots": {},
        },
    }
    config_path = config_dir / "pump.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return root, config_path


def _exact(root: Path, symbol: str, rows: list) -> Path:
    path = root / "data_cache" / f"{symbol}_5_{START}_{END}.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def _full_rows(kind: str = "mapping") -> list:
    factory = _row if kind == "mapping" else _seq
    return [factory(START + index * INTERVAL) for index in range(4)]


def _materialize(root: Path, config: Path, name: str = "run", source_map=None):
    return materialize_snapshots(
        root,
        config_path=config,
        output_dir=root / "data_cache" / "immutable" / name,
        source_map=source_map,
    )


def test_mixed_segments_become_deterministic_canonical_snapshots(tmp_path: Path) -> None:
    root, config = _prepare(tmp_path)
    first = root / "data_cache" / "AAAUSDT_5_part_a.json"
    second = root / "data_cache" / "AAAUSDT_5_part_b.json"
    first.write_text(json.dumps([_seq(START + INTERVAL), _seq(START)]), encoding="utf-8")
    second.write_text(
        json.dumps([_row(START + INTERVAL), _row(START + 2 * INTERVAL), _row(START + 3 * INTERVAL)]),
        encoding="utf-8",
    )
    _exact(root, "BBBUSDT", _full_rows("sequence"))
    _exact(root, "CCCUSDT", _full_rows("mapping"))

    manifest = _materialize(
        root,
        config,
        source_map={"AAAUSDT": [second, first]},
    )

    output = root / manifest["snapshots"]["AAAUSDT"]["path"]
    rows = json.loads(output.read_text(encoding="utf-8"))
    assert [row["ts"] for row in rows] == [START + i * INTERVAL for i in range(4)]
    assert list(rows[0]) == ["ts", "o", "h", "l", "c", "v"]
    assert manifest["snapshots"]["AAAUSDT"]["coverage"] == 1.0
    assert manifest["snapshots"]["AAAUSDT"]["max_internal_gap_bars"] == 0
    assert len(manifest["snapshots"]["AAAUSDT"]["provenance"]) == 2
    assert hashlib.sha256(output.read_bytes()).hexdigest() == manifest["snapshots"]["AAAUSDT"]["sha256"]
    assert manifest["input_snapshots"]["AAAUSDT"] == {
        "path": manifest["snapshots"]["AAAUSDT"]["path"],
        "sha256": manifest["snapshots"]["AAAUSDT"]["sha256"],
    }
    assert manifest["performance_computed"] is False
    assert manifest["network_calls"] is False
    assert manifest["live_state_changed"] is False


def test_conflicting_duplicate_timestamp_fails_without_partial_output(tmp_path: Path) -> None:
    root, config = _prepare(tmp_path)
    left = root / "data_cache" / "AAAUSDT_5_left.json"
    right = root / "data_cache" / "AAAUSDT_5_right.json"
    left.write_text(json.dumps(_full_rows()), encoding="utf-8")
    changed = _full_rows()
    changed[1] = _row(START + INTERVAL, close=10.7)
    right.write_text(json.dumps(changed), encoding="utf-8")
    _exact(root, "BBBUSDT", _full_rows())
    _exact(root, "CCCUSDT", _full_rows())
    output = root / "data_cache" / "immutable" / "conflict"

    with pytest.raises(MaterializationError, match="conflicting duplicate timestamp"):
        materialize_snapshots(
            root,
            config_path=config,
            output_dir=output,
            source_map={"AAAUSDT": [left, right]},
        )

    assert not output.exists()


@pytest.mark.parametrize(
    "bad_row,reason",
    [
        ({"ts": START, "o": 10, "h": 9, "l": 8, "c": 10, "v": 1}, "OHLC invariant"),
        ([START + 1, 10, 11, 9, 10, 1], "off the frozen interval grid"),
        ({"ts": START, "o": 10, "h": 11, "l": 9, "c": 10}, "missing OHLCV keys"),
    ],
)
def test_malformed_invariant_or_alignment_fails_closed(
    tmp_path: Path, bad_row: object, reason: str
) -> None:
    root, config = _prepare(tmp_path)
    rows = _full_rows()
    rows[0] = bad_row
    _exact(root, "AAAUSDT", rows)
    _exact(root, "BBBUSDT", _full_rows())
    _exact(root, "CCCUSDT", _full_rows())

    with pytest.raises(MaterializationError, match=reason):
        _materialize(root, config, name="bad")

    assert not (root / "data_cache" / "immutable" / "bad").exists()


def test_inadequate_coverage_or_gap_fails_closed(tmp_path: Path) -> None:
    root, config = _prepare(tmp_path, min_coverage=0.75, max_gap=0)
    _exact(root, "AAAUSDT", [_row(START), _row(START + 2 * INTERVAL), _row(START + 3 * INTERVAL)])
    _exact(root, "BBBUSDT", _full_rows())
    _exact(root, "CCCUSDT", _full_rows())

    with pytest.raises(MaterializationError, match="max_gap=1 allowed=0"):
        _materialize(root, config, name="gap")


def test_unsafe_source_and_existing_output_are_refused(tmp_path: Path) -> None:
    root, config = _prepare(tmp_path)
    for symbol in SYMBOLS:
        _exact(root, symbol, _full_rows())
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(_full_rows()), encoding="utf-8")

    with pytest.raises(MaterializationError, match="source escapes repo"):
        _materialize(root, config, name="unsafe", source_map={"AAAUSDT": [outside]})

    linked = root / "data_cache" / "AAAUSDT_5_linked.json"
    linked.symlink_to(outside)
    with pytest.raises(MaterializationError, match="path contains a symlink"):
        _materialize(root, config, name="linked", source_map={"AAAUSDT": [linked]})

    _materialize(root, config, name="once")
    with pytest.raises(MaterializationError, match="refusing to overwrite immutable output"):
        _materialize(root, config, name="once")


def test_exact_numeric_window_wins_over_unselected_legacy_noise(tmp_path: Path) -> None:
    root, config = _prepare(tmp_path)
    for symbol in SYMBOLS:
        _exact(root, symbol, _full_rows("sequence"))
    distractor = root / "data_cache" / "AAAUSDT_5_older_segment.json"
    distractor.write_text(json.dumps([_row(START, close=10.8)]), encoding="utf-8")

    manifest = _materialize(root, config, name="exact")

    provenance = manifest["snapshots"]["AAAUSDT"]["provenance"]
    assert len(provenance) == 1
    assert provenance[0]["path"].endswith(f"AAAUSDT_5_{START}_{END}.json")


def test_fallback_merges_every_segment_that_adds_coverage(tmp_path: Path) -> None:
    root, config = _prepare(tmp_path)
    base = root / "data_cache" / "AAAUSDT_5_long_history.json"
    tail = root / "data_cache" / "AAAUSDT_5_recent_tail.json"
    redundant = root / "data_cache" / "AAAUSDT_5_redundant.json"
    base.write_text(json.dumps([_row(START + i * INTERVAL) for i in range(3)]), encoding="utf-8")
    tail.write_text(
        json.dumps([_seq(START + 2 * INTERVAL), _seq(START + 3 * INTERVAL)]),
        encoding="utf-8",
    )
    redundant.write_text(json.dumps([_row(START)]), encoding="utf-8")
    _exact(root, "BBBUSDT", _full_rows())
    _exact(root, "CCCUSDT", _full_rows())

    manifest = _materialize(root, config, name="segments")

    snapshot = manifest["snapshots"]["AAAUSDT"]
    assert snapshot["rows"] == 4
    assert snapshot["coverage"] == 1.0
    assert len(snapshot["provenance"]) == 2
    assert sum(row["rows_contributed"] for row in snapshot["provenance"]) == 4


def test_redundant_discovered_segment_cannot_hide_conflicting_duplicate(tmp_path: Path) -> None:
    root, config = _prepare(tmp_path)
    base = root / "data_cache" / "AAAUSDT_5_long_history.json"
    conflicting = root / "data_cache" / "AAAUSDT_5_redundant_conflict.json"
    base.write_text(json.dumps(_full_rows()), encoding="utf-8")
    conflicting.write_text(json.dumps([_row(START, close=10.8)]), encoding="utf-8")
    _exact(root, "BBBUSDT", _full_rows())
    _exact(root, "CCCUSDT", _full_rows())

    with pytest.raises(MaterializationError, match="conflicting duplicate timestamp"):
        _materialize(root, config, name="redundant-conflict")

    assert not (root / "data_cache" / "immutable" / "redundant-conflict").exists()


def test_snapshot_bytes_are_reproducible(tmp_path: Path) -> None:
    root, config = _prepare(tmp_path)
    for symbol in SYMBOLS:
        _exact(root, symbol, list(reversed(_full_rows("sequence"))))

    first = _materialize(root, config, name="first")
    second = _materialize(root, config, name="second")
    first_path = root / first["snapshots"]["AAAUSDT"]["path"]
    second_path = root / second["snapshots"]["AAAUSDT"]["path"]
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first["snapshots"]["AAAUSDT"]["sha256"] == second["snapshots"]["AAAUSDT"]["sha256"]
