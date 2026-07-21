from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from bot.event_universe_v1 import M5_INTERVAL_MS, EventUniverseConfigV1
from scripts.run_event_universe_v2 import (
    ImmutableBarConflict,
    _collector_contract,
    _load_v2_spec,
    _preflight,
    assert_no_immutable_bar_conflict,
    normalize_settled_m5,
)


BASE = 1_800_000_000_000 // M5_INTERVAL_MS * M5_INTERVAL_MS


def _small_config() -> EventUniverseConfigV1:
    return dataclasses.replace(EventUniverseConfigV1(), baseline_bars=13, recent_bars=3)


def _rows(count: int = 18) -> list[list[float]]:
    rows = []
    for index in range(count):
        start = BASE + index * M5_INTERVAL_MS
        rows.append([start, 100.0, 101.0, 99.0, 100.0 + index / 100.0, 1.0, 1000.0])
    return rows


def test_v2_excludes_forming_and_just_closed_bar():
    cfg = _small_config()
    rows = _rows()
    source_as_of = BASE + len(rows) * M5_INTERVAL_MS
    normalized = normalize_settled_m5(rows, source_as_of_ms=source_as_of, config=cfg)
    assert len(normalized) == cfg.required_closed_bars
    assert normalized[-1][0] == source_as_of - 2 * M5_INTERVAL_MS

    changed = _rows()
    changed[-1][1:7] = [1.0, 999.0, 0.1, 500.0, 1e12, 1e12]
    assert normalize_settled_m5(changed, source_as_of_ms=source_as_of, config=cfg) == normalized


def test_v2_cross_snapshot_immutability_conflict_is_terminal():
    old = {"BANKUSDT": {BASE: [BASE, 1.0, 1.1, 0.9, 1.0, 100.0, 100.0]}}
    same = {"BANKUSDT": [[BASE, 1.0, 1.1, 0.9, 1.0, 100.0, 100.0]]}
    changed = {"BANKUSDT": [[BASE, 1.0, 1.1, 0.9, 1.01, 101.0, 101.0]]}
    assert_no_immutable_bar_conflict(old, same)
    with pytest.raises(ImmutableBarConflict, match="BANKUSDT"):
        assert_no_immutable_bar_conflict(old, changed)


def test_v2_spec_and_preflight_are_frozen_public_research_only():
    root = Path(__file__).resolve().parents[1]
    path = root / "configs/preregistered/event_universe_v2_20260721.json"
    spec, config = _load_v2_spec(path)
    preflight = _preflight(path, spec, config)
    assert preflight["ok"] is True
    assert preflight["network_calls"] is False
    assert preflight["private_api_calls"] is False
    assert preflight["orders_transfers_withdrawals"] is False
    assert preflight["collector_contract"] == _collector_contract(spec)
    assert preflight["collector_contract"]["source_finality_policy"]["settlement_lag_bars"] == 1


def test_v2r2_corrected_spec_is_separately_hash_bound():
    root = Path(__file__).resolve().parents[1]
    path = root / "configs/preregistered/event_universe_v2r2_20260721.json"
    spec, config = _load_v2_spec(path)
    contract = _collector_contract(spec)
    assert spec["frozen_at_utc"] == "2026-07-21T18:18:02Z"
    assert spec["run_revision"] == "v2r2_timestamp_corrected"
    assert contract["run_revision"] == "v2r2_timestamp_corrected"
    assert contract["spec_sha256"] == _preflight(path, spec, config)["spec_sha256"]
