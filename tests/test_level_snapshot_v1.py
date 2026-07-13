from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from bot.level_snapshot_v1 import (
    LevelSnapshotConfigV1,
    LevelSnapshotError,
    build_resistance_snapshot_v1,
    flip_level_snapshot_v1,
    invalidate_level_snapshot_v1,
    level_snapshot_from_dict,
    level_snapshot_to_dict,
)


H1 = 3_600_000
PROVIDER_SHA = "a" * 64


def h1_rows(count: int = 60):
    rows = []
    pivot_indices = {10, 25, 40}
    for index in range(count):
        close = 107.0 + 0.05 * (index % 3)
        high = 110.0 if index in pivot_indices else close + 0.55
        rows.append([index * H1, close - 0.1, high, close - 0.65, close, 1_000.0 + index])
    return rows


def build(rows=None, *, as_of=None):
    source = list(rows or h1_rows())
    return build_resistance_snapshot_v1(
        "TESTUSDT", "H1", source,
        as_of_ms=len(source) * H1 if as_of is None else as_of,
        provider_fingerprint=PROVIDER_SHA,
        cfg=LevelSnapshotConfigV1(lookback_bars=60, max_distance_atr=5.0),
    )


def test_build_is_closed_causal_immutable_and_versioned() -> None:
    source = h1_rows()
    snapshot = build(source)
    assert snapshot is not None
    assert snapshot.lifecycle == "resistance"
    assert len(snapshot.confirmed_pivots) == len(snapshot.respect_history) >= 2
    assert snapshot.valid_at_ms <= snapshot.source_end_close_ms <= snapshot.created_at_ms
    assert len(snapshot.level_id) == len(snapshot.snapshot_id) == 32
    assert len(snapshot.source_bars_sha256) == len(snapshot.payload_sha256) == 64

    # An extreme still-open H1 tail is excluded from both source hash and ID.
    open_tail = source + [[60 * H1, 107.0, 999.0, 1.0, 900.0, 99_000.0]]
    same = build_resistance_snapshot_v1(
        "TESTUSDT", "H1", open_tail, as_of_ms=60 * H1,
        provider_fingerprint=PROVIDER_SHA,
        cfg=LevelSnapshotConfigV1(lookback_bars=60, max_distance_atr=5.0),
    )
    assert same == snapshot
    with pytest.raises(FrozenInstanceError):
        snapshot.level = 1.0  # type: ignore[misc]


def test_level_id_survives_refresh_but_snapshot_id_versions_evidence() -> None:
    source = h1_rows()
    first = build(source)
    refreshed_rows = source + [[60 * H1, 107.0, 107.6, 106.4, 107.1, 1_100.0]]
    second = build_resistance_snapshot_v1(
        "TESTUSDT", "H1", refreshed_rows, as_of_ms=61 * H1,
        provider_fingerprint=PROVIDER_SHA,
        cfg=LevelSnapshotConfigV1(lookback_bars=61, max_distance_atr=5.0),
    )
    assert first is not None and second is not None
    assert first.level_id == second.level_id
    assert first.snapshot_id != second.snapshot_id
    assert first.source_bars_sha256 != second.source_bars_sha256


def test_flip_and_invalidation_keep_frozen_identity() -> None:
    base = build()
    assert base is not None
    flipped = flip_level_snapshot_v1(
        base, breakout_ts_ms=base.created_at_ms + H1,
        breakout_close=base.zone_high + 1.0,
    )
    invalid = invalidate_level_snapshot_v1(
        flipped, invalidated_at_ms=base.created_at_ms + 2 * H1,
        close=base.zone_low - 0.1, reason="closed_below_flip",
    )
    assert invalid.lifecycle == "invalidated"
    assert invalid.level_id == base.level_id
    assert invalid.snapshot_id == base.snapshot_id
    assert invalid.payload_sha256 == base.payload_sha256


@pytest.mark.parametrize(
    "field,value",
    [
        ("zone_high", 999.0),
        ("source_end_close_ms", 1),
        ("config_sha256", "b" * 64),
        ("level_id", "0" * 32),
    ],
)
def test_serialized_evidence_tampering_fails_closed(field, value) -> None:
    snapshot = build()
    assert snapshot is not None
    payload = level_snapshot_to_dict(snapshot)
    payload[field] = value
    with pytest.raises(LevelSnapshotError):
        level_snapshot_from_dict(payload)


def test_grid_gap_and_config_fail_closed() -> None:
    rows = h1_rows()
    rows[20][0] += 1
    with pytest.raises(LevelSnapshotError, match="grid"):
        build(rows)
    with pytest.raises(LevelSnapshotError):
        LevelSnapshotConfigV1(lookback_bars=2)
    with pytest.raises(LevelSnapshotError, match="provider"):
        build_resistance_snapshot_v1(
            "TESTUSDT", "H1", h1_rows(), as_of_ms=60 * H1,
            provider_fingerprint="not-a-sha",
        )
