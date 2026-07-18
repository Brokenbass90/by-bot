from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from bot.sloped_level_snapshot_v1 import (
    SLOPED_LEVEL_SNAPSHOT_SCHEMA,
    SlopedLevelConfigV1,
    SlopedLevelSnapshotError,
    build_sloped_level_snapshot_v1,
)


M1 = 60_000


def _support_rows(count: int = 30, pivots=(5, 12, 19)) -> list[list[float]]:
    rows = []
    for index in range(count):
        line = 100.0 + 0.5 * index
        low = line if index in pivots else line + 2.0
        close = line + 3.0
        rows.append([index * M1, close - 0.2, close + 1.0, low, close, 100.0 + index])
    return rows


def _resistance_rows(count: int = 30, pivots=(5, 12, 19)) -> list[list[float]]:
    rows = []
    for index in range(count):
        line = 150.0 - 0.4 * index
        high = line if index in pivots else line - 2.0
        close = line - 3.0
        rows.append([index * M1, close + 0.2, high, close - 1.0, close, 100.0 + index])
    return rows


def _config() -> SlopedLevelConfigV1:
    return SlopedLevelConfigV1(
        lookback_bars=40,
        pivot_left=1,
        pivot_right=1,
        min_confirmed_pivots=3,
        min_r_squared=0.99,
    )


@pytest.mark.parametrize(
    ("side", "factory", "expected_slope"),
    [
        ("support", _support_rows, 0.5),
        ("resistance", _resistance_rows, -0.4),
    ],
)
def test_builds_separate_causal_support_and_resistance(
    side, factory, expected_slope
) -> None:
    rows = factory()
    result = build_sloped_level_snapshot_v1(
        "TESTUSDT", side, M1, rows, as_of_ms=len(rows) * M1, cfg=_config()
    )
    assert result.status == "accepted"
    assert result.reason == "accepted"
    assert result.snapshot is not None
    snapshot = result.snapshot
    assert snapshot.schema == SLOPED_LEVEL_SNAPSHOT_SCHEMA
    assert snapshot.side == side
    assert len(snapshot.confirmed_pivots) == 3
    assert snapshot.slope_per_interval == pytest.approx(expected_slope)
    assert snapshot.r_squared == pytest.approx(1.0)
    assert snapshot.projected_at_as_of == pytest.approx(
        snapshot.intercept_at_anchor
        + snapshot.slope_per_interval
        * ((snapshot.as_of_ms - snapshot.anchor_ts_ms) / M1)
    )
    assert snapshot.unbroken_through_ms == snapshot.source_end_close_ms
    assert len(snapshot.line_id) == len(snapshot.snapshot_id) == 32
    assert len(snapshot.input_sha256) == len(snapshot.payload_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        snapshot.side = "resistance"  # type: ignore[misc]


def test_two_points_are_never_treated_as_evidence() -> None:
    with pytest.raises(SlopedLevelSnapshotError, match="at least three"):
        SlopedLevelConfigV1(min_confirmed_pivots=2)

    rows = _support_rows(pivots=(5, 15))
    result = build_sloped_level_snapshot_v1(
        "TESTUSDT", "support", M1, rows, as_of_ms=len(rows) * M1, cfg=_config()
    )
    assert result.status == "rejected"
    assert result.reason == "insufficient_confirmed_pivots"
    assert result.confirmed_pivots == 2
    assert result.snapshot is None


def test_pivot_right_must_be_closed_before_pivot_is_evidence() -> None:
    # The last low looks like a third pivot but has no right-hand closed bar.
    rows = _support_rows(count=20, pivots=(5, 12, 19))
    result = build_sloped_level_snapshot_v1(
        "TESTUSDT", "support", M1, rows, as_of_ms=len(rows) * M1, cfg=_config()
    )
    assert result.status == "rejected"
    assert result.reason == "insufficient_confirmed_pivots"
    assert result.confirmed_pivots == 2
    assert result.snapshot is None


def test_future_or_forming_tail_cannot_change_fit_or_identity() -> None:
    rows = _support_rows()
    base = build_sloped_level_snapshot_v1(
        "TESTUSDT", "support", M1, rows, as_of_ms=len(rows) * M1, cfg=_config()
    )
    extreme_open_tail = rows + [[30 * M1, 9_000.0, 10_000.0, 1.0, 9_500.0, 9e9]]
    same = build_sloped_level_snapshot_v1(
        "TESTUSDT",
        "support",
        M1,
        extreme_open_tail,
        as_of_ms=len(rows) * M1,
        cfg=_config(),
    )
    assert base.status == same.status == "accepted"
    assert base.snapshot == same.snapshot
    assert base.input_sha256 == same.input_sha256


def test_line_identity_is_stable_but_snapshot_versions_new_closed_prefix() -> None:
    rows = _support_rows()
    first = build_sloped_level_snapshot_v1(
        "TESTUSDT", "support", M1, rows, as_of_ms=30 * M1, cfg=_config()
    )
    line = 100.0 + 0.5 * 30
    close = line + 3.0
    refreshed_rows = rows + [[30 * M1, close - 0.2, close + 1.0, line + 2.0, close, 130.0]]
    second = build_sloped_level_snapshot_v1(
        "TESTUSDT", "support", M1, refreshed_rows, as_of_ms=31 * M1, cfg=_config()
    )
    assert first.snapshot is not None and second.snapshot is not None
    assert first.snapshot.line_id == second.snapshot.line_id
    assert first.snapshot.snapshot_id != second.snapshot.snapshot_id
    assert first.snapshot.source_sha256 != second.snapshot.source_sha256


def test_closed_break_rejects_line_instead_of_resurrecting_it() -> None:
    rows = _support_rows()
    # The last bar cannot be a confirmed pivot, but its closed break must still
    # invalidate the previously known support line.
    rows[-1][1:5] = [90.0, 91.0, 88.0, 89.0]
    result = build_sloped_level_snapshot_v1(
        "TESTUSDT", "support", M1, rows, as_of_ms=len(rows) * M1, cfg=_config()
    )
    assert result.status == "rejected"
    assert result.reason == "line_broken"
    assert result.snapshot is None


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda rows: rows.__setitem__(10, [10 * M1 + 1, *rows[10][1:]]), "invalid_source"),
        (lambda rows: rows.__setitem__(10, [10 * M1, 1.0, 0.5, 2.0, 1.0, 1.0]), "invalid_source"),
    ],
)
def test_bad_closed_source_fails_closed_with_explicit_reason(mutation, reason) -> None:
    rows = _support_rows()
    mutation(rows)
    result = build_sloped_level_snapshot_v1(
        "TESTUSDT", "support", M1, rows, as_of_ms=len(rows) * M1, cfg=_config()
    )
    assert result.status == "rejected"
    assert result.reason == reason
    assert result.snapshot is None


def test_support_and_resistance_cannot_share_identity() -> None:
    support = build_sloped_level_snapshot_v1(
        "TESTUSDT", "support", M1, _support_rows(), as_of_ms=30 * M1, cfg=_config()
    )
    resistance = build_sloped_level_snapshot_v1(
        "TESTUSDT", "resistance", M1, _resistance_rows(), as_of_ms=30 * M1, cfg=_config()
    )
    assert support.snapshot is not None and resistance.snapshot is not None
    assert support.snapshot.line_id != resistance.snapshot.line_id
    assert support.snapshot.input_sha256 != resistance.snapshot.input_sha256
