from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from bot.closed_bar_aggregation_v1 import (
    SOURCE_INTERVAL_MS,
    ClosedBarAggregationConfigV1,
    ClosedBarAggregationError,
    aggregate_closed_m5_bars,
)


M5 = SOURCE_INTERVAL_MS
PROVIDER_SHA = "a" * 64


def _aggregate(rows, target="M15", *, as_of=None, identity="research"):
    return aggregate_closed_m5_bars(
        rows,
        as_of_ms=(rows[-1][0] + M5 if as_of is None else as_of),
        provider_identity=identity,
        provider_fingerprint=PROVIDER_SHA,
        config=ClosedBarAggregationConfigV1(target_timeframe=target),
    )


def _rows(count: int, *, start_ts: int = 0):
    rows = []
    for index in range(count):
        open_price = 100.0 + index
        close = open_price + (0.25 if index % 2 == 0 else -0.25)
        rows.append(
            [
                start_ts + index * M5,
                open_price,
                max(open_price, close) + 0.5,
                min(open_price, close) - 0.5,
                close,
                10.0 + index,
            ]
        )
    return rows


def test_exact_m15_ohlcv_and_immutable_provenance() -> None:
    rows = [
        [0, 10.0, 12.0, 9.0, 11.0, 1.0],
        [M5, 11.0, 13.0, 10.0, 12.0, 2.0],
        [2 * M5, 12.0, 14.0, 11.0, 13.0, 3.0],
        [3 * M5, 13.0, 15.0, 12.0, 14.0, 4.0],
        [4 * M5, 14.0, 16.0, 13.0, 15.0, 5.0],
        [5 * M5, 15.0, 17.0, 14.0, 16.0, 6.0],
    ]

    result = _aggregate(rows)

    assert result.output_bars == (
        (0, 10.0, 14.0, 9.0, 13.0, 6.0),
        (3 * M5, 13.0, 17.0, 12.0, 16.0, 15.0),
    )
    assert result.source_count == 6
    assert result.output_count == 2
    assert result.source_start_open_ts_ms == 0
    assert result.source_end_close_ts_ms == 6 * M5
    assert len(result.source_sha256) == len(result.output_sha256) == 64
    assert len(result.provider_fingerprint) == len(result.config_fingerprint) == 64
    with pytest.raises(FrozenInstanceError):
        result.output_count = 99  # type: ignore[misc]


def test_research_and_live_labels_have_byte_identical_bars_and_hashes() -> None:
    rows = _rows(12)
    research = _aggregate(rows, "H1", identity="research")
    live = _aggregate(rows, "H1", identity="live")

    assert research.provider_identity != live.provider_identity
    assert research.output_bars == live.output_bars
    assert research.output_bytes() == live.output_bytes()
    assert research.source_sha256 == live.source_sha256
    assert research.output_sha256 == live.output_sha256
    assert research.config_fingerprint == live.config_fingerprint


def test_partial_first_last_and_missing_child_fail_closed() -> None:
    with pytest.raises(ClosedBarAggregationError, match="starts with a partial"):
        _aggregate(_rows(3, start_ts=M5))
    with pytest.raises(ClosedBarAggregationError, match="ends with a partial"):
        _aggregate(_rows(4))

    missing = _rows(6)
    del missing[2]
    with pytest.raises(ClosedBarAggregationError, match="missing M5 child"):
        _aggregate(missing)


def test_open_tail_is_rejected_instead_of_silently_truncated() -> None:
    closed = _rows(3)
    open_tail = closed + _rows(1, start_ts=3 * M5)

    with pytest.raises(ClosedBarAggregationError, match="closes after as_of_ms"):
        _aggregate(open_tail, as_of=3 * M5)


def test_future_mutation_cannot_change_a_frozen_closed_prefix() -> None:
    closed = _rows(3)
    future = _rows(3, start_ts=3 * M5)
    before = _aggregate(list(closed), as_of=3 * M5)
    future[0][2] = 999_999.0
    after = _aggregate(list(closed), as_of=3 * M5)

    assert before == after
    with pytest.raises(ClosedBarAggregationError, match="closes after as_of_ms"):
        _aggregate(closed + future, as_of=3 * M5)


def test_closed_source_change_updates_source_and_output_hashes() -> None:
    rows = _rows(3)
    original = _aggregate(rows)
    changed_rows = [list(row) for row in rows]
    changed_rows[2][2] += 0.125
    changed = _aggregate(changed_rows)

    assert original.source_sha256 != changed.source_sha256
    assert original.output_sha256 != changed.output_sha256
    with pytest.raises(ClosedBarAggregationError, match="output_sha256"):
        replace(original, output_sha256="b" * 64)


def test_h1_and_h4_use_exact_child_counts() -> None:
    rows = _rows(48)
    h1 = _aggregate(rows, "H1")
    h4 = _aggregate(rows, "H4")

    assert h1.output_count == 4
    assert h4.output_count == 1
    assert h1.source_count == h4.source_count == 48
    assert h1.output_bars[0][0] == h4.output_bars[0][0] == 0
    assert h4.output_bars[0][5] == pytest.approx(sum(row[5] for row in rows))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_timeframe": "h1"},
        {"target_timeframe": "60"},
        {"target_timeframe": "M5"},
        {"target_timeframe": "H1", "source_timeframe": "M1"},
        {"target_timeframe": "H1", "source_interval_ms": 60_000},
        {"target_timeframe": "H1", "require_utc_grid": False},
        {"target_timeframe": "H1", "require_contiguous_source": False},
        {"target_timeframe": "H1", "require_full_target_buckets": False},
        {"target_timeframe": "H1", "require_closed_source": False},
    ],
)
def test_config_is_strict_and_cannot_disable_safety(kwargs) -> None:
    with pytest.raises(ClosedBarAggregationError):
        ClosedBarAggregationConfigV1(**kwargs)


def test_provider_contract_and_config_type_fail_closed() -> None:
    rows = _rows(3)
    cfg = ClosedBarAggregationConfigV1(target_timeframe="M15")
    with pytest.raises(ClosedBarAggregationError, match="provider_identity"):
        aggregate_closed_m5_bars(
            rows, as_of_ms=3 * M5, provider_identity=" live ",
            provider_fingerprint=PROVIDER_SHA, config=cfg,
        )
    with pytest.raises(ClosedBarAggregationError, match="provider_fingerprint"):
        aggregate_closed_m5_bars(
            rows, as_of_ms=3 * M5, provider_identity="live",
            provider_fingerprint="not-a-sha", config=cfg,
        )
    with pytest.raises(ClosedBarAggregationError, match="config"):
        aggregate_closed_m5_bars(
            rows, as_of_ms=3 * M5, provider_identity="live",
            provider_fingerprint=PROVIDER_SHA, config=None,  # type: ignore[arg-type]
        )


def test_off_grid_duplicate_disorder_and_gap_fail_closed() -> None:
    off_grid = _rows(3)
    off_grid[1][0] += 1
    with pytest.raises(ClosedBarAggregationError, match="off the M5"):
        _aggregate(off_grid)

    duplicate = _rows(3)
    duplicate[1][0] = duplicate[0][0]
    with pytest.raises(ClosedBarAggregationError, match="duplicates"):
        _aggregate(duplicate)

    disorder = _rows(3)
    disorder[1], disorder[2] = disorder[2], disorder[1]
    with pytest.raises(ClosedBarAggregationError, match="out of timestamp order"):
        _aggregate(disorder, as_of=3 * M5)


@pytest.mark.parametrize(
    "field,value,match",
    [
        (1, float("nan"), "finite"),
        (2, float("inf"), "finite"),
        (4, 0.0, "positive"),
        (5, -1.0, "non-negative"),
        (2, 99.0, "OHLC geometry"),
        (3, 101.0, "OHLC geometry"),
    ],
)
def test_invalid_ohlcv_fails_closed(field, value, match) -> None:
    rows = _rows(3)
    rows[1][field] = value
    with pytest.raises(ClosedBarAggregationError, match=match):
        _aggregate(rows)


def test_malformed_rows_and_noncanonical_timestamps_fail_closed() -> None:
    rows = _rows(3)
    rows[1] = rows[1][:-1]
    with pytest.raises(ClosedBarAggregationError, match="six fields"):
        _aggregate(rows)

    rows = _rows(3)
    rows[1][0] = float(M5)
    with pytest.raises(ClosedBarAggregationError, match="must be an integer"):
        _aggregate(rows)
