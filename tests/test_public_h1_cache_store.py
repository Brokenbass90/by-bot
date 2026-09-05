from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bot.public_h1_cache_store import (
    CanonicalCachedFeed,
    CanonicalH1Cache,
    PublicCacheViolation,
    classify_stream,
    validate_closed_h1_rows,
)


H1 = 3_600_000


def _bar(hour: int, price: float = 100.0) -> list[object]:
    return [hour * H1, str(price), str(price + 3), str(price - 2), str(price + 1), "10"]


def _bars(start: int, count: int) -> list[list[object]]:
    return [_bar(start + i, 100.0 + i) for i in range(count)]


def test_validate_removes_forming_h1_tail_and_normalizes_bybit_descending_rows() -> None:
    rows = [[3 * H1, "103", "106", "101", "105", "12", "turnover"]] + list(reversed(_bars(0, 3)))

    assert validate_closed_h1_rows(rows, observed_at_ms=3 * H1) == [
        [0, 100.0, 103.0, 98.0, 101.0, 10.0],
        [H1, 101.0, 104.0, 99.0, 102.0, 10.0],
        [2 * H1, 102.0, 105.0, 100.0, 103.0, 10.0],
    ]


@pytest.mark.parametrize(
    "rows",
    [
        _bars(0, 1) + _bars(2, 1),
        [_bar(0), _bar(0)],
        [_bar(0), _bar(2), _bar(1)],
        [[1, "1", "2", "0.5", "1.5", "1"]],
        [[0, "1", "0.5", "0.9", "0.8", "1"]],
        [[0, "1", "2", "0", "1.5", "1"]],
    ],
)
def test_validate_rejects_gap_duplicate_order_off_grid_and_invalid_ohlcv(rows: list[list[object]]) -> None:
    with pytest.raises(PublicCacheViolation):
        validate_closed_h1_rows(rows, observed_at_ms=10 * H1)


def test_validate_rejects_future_and_stale_latest_close() -> None:
    with pytest.raises(PublicCacheViolation, match="future"):
        validate_closed_h1_rows(_bars(0, 2) + [_bar(4)], observed_at_ms=3 * H1)
    with pytest.raises(PublicCacheViolation, match="stale"):
        validate_closed_h1_rows(_bars(0, 2), observed_at_ms=10 * H1, max_age_ms=H1)


def test_validate_rejects_insufficient_history() -> None:
    with pytest.raises(PublicCacheViolation, match="minimum"):
        validate_closed_h1_rows(_bars(0, 1), observed_at_ms=H1, min_bars=2)


def test_stream_classification_has_exact_forward_and_backfill_boundaries() -> None:
    close = 10 * H1
    lag = 300_000

    assert classify_stream(bar_close_ts_ms=close, observed_at_ms=close, max_forward_lag_ms=lag) == "EXECUTION_FORWARD"
    assert classify_stream(bar_close_ts_ms=close, observed_at_ms=close + lag, max_forward_lag_ms=lag) == "EXECUTION_FORWARD"
    assert classify_stream(bar_close_ts_ms=close, observed_at_ms=close + lag + 1, max_forward_lag_ms=lag) == "ALPHA_FORWARD_BACKFILL"
    with pytest.raises(PublicCacheViolation, match="before"):
        classify_stream(bar_close_ts_ms=close, observed_at_ms=close - 1, max_forward_lag_ms=lag)


def test_cache_bootstrap_retry_append_restart_and_retention(tmp_path: Path) -> None:
    cache = CanonicalH1Cache(tmp_path, max_bars=1920)
    initial = _bars(0, 2)
    metadata = cache.merge("ethusdt", initial, observed_at_ms=2 * H1)
    assert metadata.row_count == 2
    assert metadata.first_start_ms == 0
    assert metadata.last_start_ms == H1
    assert metadata.latest_close_ms == 2 * H1
    assert metadata.changed is True
    assert (tmp_path / "ETHUSDT.json").stat().st_mode & 0o777 == 0o600

    retry = cache.merge("ETHUSDT", initial, observed_at_ms=2 * H1)
    assert retry.changed is False
    assert retry.rows_hash == metadata.rows_hash

    appended = cache.merge("ETHUSDT", initial + [_bar(2, 102.0)], observed_at_ms=3 * H1)
    assert appended.changed is True
    rows, restored = CanonicalH1Cache(tmp_path, max_bars=1920).load("ethusdt")
    assert rows == tuple([
        [0, 100.0, 103.0, 98.0, 101.0, 10.0],
        [H1, 101.0, 104.0, 99.0, 102.0, 10.0],
        [2 * H1, 102.0, 105.0, 100.0, 103.0, 10.0],
    ])
    assert restored.rows_hash == appended.rows_hash

    retained = CanonicalH1Cache(tmp_path / "retained", max_bars=1920)
    retained.merge("BTCUSDT", _bars(0, 1922), observed_at_ms=1922 * H1)
    retained_rows, retained_meta = retained.load("BTCUSDT")
    assert len(retained_rows) == 1920
    assert retained_rows[0][0] == 2 * H1
    assert retained_meta.last_start_ms == 1921 * H1

    evicted_mutation = _bars(0, 1923)
    evicted_mutation[0] = _bar(0, 999.0)
    with pytest.raises(PublicCacheViolation, match="retained boundary"):
        retained.merge("BTCUSDT", evicted_mutation, observed_at_ms=1923 * H1)


def test_cache_rejects_mutation_gap_unsafe_symbol_and_corrupt_or_symlink_file(tmp_path: Path) -> None:
    cache = CanonicalH1Cache(tmp_path, max_bars=1920)
    cache.merge("ETHUSDT", _bars(0, 2), observed_at_ms=2 * H1)

    changed = _bars(0, 2)
    changed[1][1] = "101.5"
    with pytest.raises(PublicCacheViolation, match="mutation"):
        cache.merge("ETHUSDT", changed, observed_at_ms=2 * H1)
    with pytest.raises(PublicCacheViolation, match="contiguous"):
        cache.merge("ETHUSDT", [_bar(3)], observed_at_ms=4 * H1)
    with pytest.raises(PublicCacheViolation, match="symbol"):
        cache.merge("../escape", _bars(0, 1), observed_at_ms=H1)

    path = tmp_path / "ETHUSDT.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(PublicCacheViolation, match="corrupt"):
        cache.load("ETHUSDT")

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(PublicCacheViolation, match="symlink"):
        cache.load("ETHUSDT")


def test_cache_rejects_non_regular_cache_file(tmp_path: Path) -> None:
    cache = CanonicalH1Cache(tmp_path, max_bars=1920)
    (tmp_path / "ETHUSDT.json").mkdir()
    with pytest.raises(PublicCacheViolation, match="not regular"):
        cache.load("ETHUSDT")


def test_cache_write_enforces_0600_under_hostile_umask(tmp_path: Path) -> None:
    cache = CanonicalH1Cache(tmp_path, max_bars=1920)
    previous = os.umask(0o200)
    try:
        cache.merge("ETHUSDT", _bars(0, 2), observed_at_ms=2 * H1)
    finally:
        os.umask(previous)

    assert (tmp_path / "ETHUSDT.json").stat().st_mode & 0o777 == 0o600
    assert CanonicalH1Cache(tmp_path, max_bars=1920).load("ETHUSDT")[1].row_count == 2


def test_cache_load_missing_is_empty_and_metadata_is_immutable(tmp_path: Path) -> None:
    metadata = CanonicalH1Cache(tmp_path, max_bars=1920).merge("EMPTY", [], observed_at_ms=0)
    assert metadata.row_count == 0
    rows, loaded = CanonicalH1Cache(tmp_path, max_bars=1920).load("MISSING")
    assert rows == ()
    assert loaded.changed is False
    with pytest.raises(Exception):
        metadata.row_count = 3  # type: ignore[misc]


def test_cache_accepts_fixed_universe_symbols_with_numeric_prefix(tmp_path: Path) -> None:
    metadata = CanonicalH1Cache(tmp_path, max_bars=1920).merge(
        "1000BONKUSDT", _bars(0, 2), observed_at_ms=2 * H1
    )
    assert metadata.row_count == 2


def test_cached_feed_uses_canonical_store_for_exact_h1_h4_d1_and_rejects_invalid_requests() -> None:
    rows = _bars(0, 48)
    feed = CanonicalCachedFeed("ethusdt", rows)

    assert feed("ETHUSDT", "60", 2) == [
        [46 * H1, 146.0, 149.0, 144.0, 147.0, 10.0],
        [47 * H1, 147.0, 150.0, 145.0, 148.0, 10.0],
    ]
    assert feed("ETHUSDT", "4h", 2)[-1] == [44 * H1, 144.0, 150.0, 142.0, 148.0, 40.0]
    assert feed("ETHUSDT", "D1", 1)[0] == [24 * H1, 124.0, 150.0, 122.0, 148.0, 240.0]

    with pytest.raises(PublicCacheViolation, match="symbol"):
        feed("BTCUSDT", "60", 1)
    with pytest.raises(PublicCacheViolation, match="timeframe"):
        feed("ETHUSDT", "15", 1)
    with pytest.raises(PublicCacheViolation, match="gap"):
        CanonicalCachedFeed("ETHUSDT", [_bar(0), _bar(2)])


def test_cached_feed_excludes_incomplete_h4_and_d1_tails() -> None:
    feed = CanonicalCachedFeed("ETHUSDT", _bars(0, 29))

    h4 = feed("ETHUSDT", "4h", 20)
    d1 = feed("ETHUSDT", "D1", 20)

    assert [row[0] for row in h4] == [hour * H1 for hour in range(0, 25, 4)]
    assert [row[0] for row in d1] == [0]
