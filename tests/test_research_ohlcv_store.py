from __future__ import annotations

import pytest

from research_lab.research_ohlcv_store import (
    ResearchKlineStore,
    ResearchKlineStoreError,
    timeframe_minutes,
)
from strategies.live_kline_utils import closed_kline_rows


HOUR_MS = 3_600_000


def _hour(ts_hour: int, price: float) -> list[float]:
    return [
        ts_hour * HOUR_MS,
        price,
        price + 2.0,
        price - 1.0,
        price + 1.0,
        10.0,
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("60", 60), (60, 60), ("H1", 60), ("1h", 60), ("4H", 240), ("D1", 1440)],
)
def test_timeframe_minutes_accepts_canonical_aliases(raw: object, expected: int) -> None:
    assert timeframe_minutes(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "banana", "0", 0, "1M"])
def test_timeframe_minutes_rejects_ambiguous_or_invalid_values(raw: object) -> None:
    with pytest.raises(ResearchKlineStoreError):
        timeframe_minutes(raw)


def test_same_timeframe_returns_only_requested_closed_prefix() -> None:
    store = ResearchKlineStore("ETHUSDT", base_interval_minutes=60)
    store.rows = [_hour(i, 100.0 + i) for i in range(6)]

    assert store.fetch_klines("ETHUSDT", "60", 2) == store.rows[-2:]


def test_h4_aggregation_uses_complete_utc_children_and_excludes_open_tail() -> None:
    store = ResearchKlineStore("ETHUSDT", base_interval_minutes=60)
    # Bars 00:00..04:00 are closed prefixes at 05:00.  The 04:00 child starts
    # the next H4 bucket, which is still open and must not leak into evidence.
    store.rows = [_hour(i, 100.0 + i) for i in range(5)]

    assert store.fetch_klines("ETHUSDT", "240", 5) == [
        [0, 100.0, 105.0, 99.0, 104.0, 40.0]
    ]


def test_h4_aggregation_returns_multiple_complete_buckets_oldest_first() -> None:
    store = ResearchKlineStore("ETHUSDT", base_interval_minutes=60)
    store.rows = [_hour(i, 100.0 + i) for i in range(8)]

    rows = store.fetch_klines("ETHUSDT", "4h", 2)

    assert [row[0] for row in rows] == [0, 4 * HOUR_MS]
    assert rows[1] == [4 * HOUR_MS, 104.0, 109.0, 103.0, 108.0, 40.0]


def test_store_fails_closed_for_wrong_symbol_lower_tf_and_gapped_bucket() -> None:
    store = ResearchKlineStore("ETHUSDT", base_interval_minutes=60)
    store.rows = [_hour(i, 100.0 + i) for i in (0, 1, 3)]

    with pytest.raises(ResearchKlineStoreError, match="per-symbol"):
        store.fetch_klines("BTCUSDT", "60", 2)
    with pytest.raises(ResearchKlineStoreError, match="finer than source"):
        store.fetch_klines("ETHUSDT", "15", 2)
    with pytest.raises(ResearchKlineStoreError, match="missing source child"):
        store.fetch_klines("ETHUSDT", "240", 2)


def test_store_infers_h1_source_from_timestamp_spacing() -> None:
    store = ResearchKlineStore("ETHUSDT")
    store.rows = [_hour(i, 100.0 + i) for i in range(8)]

    assert store.base_interval_minutes == 60
    assert len(store.fetch_klines("ETHUSDT", "240", 2)) == 2


def test_closed_store_matches_live_closed_bar_filter_at_h4_boundary() -> None:
    store = ResearchKlineStore("ETHUSDT", base_interval_minutes=60)
    store.rows = [_hour(i, 100.0 + i) for i in range(5)]

    # A raw exchange H4 response at 05:00 contains the current 04:00 H4
    # bucket.  The live helper must remove it; the canonical research Store
    # must never construct it in the first place.
    raw_h4 = [
        [0, 100.0, 105.0, 99.0, 104.0, 40.0],
        [4 * HOUR_MS, 104.0, 106.0, 103.0, 105.0, 10.0],
    ]
    live_closed = closed_kline_rows(raw_h4, "240", now_ms=5 * HOUR_MS)

    assert live_closed == store.fetch_klines("ETHUSDT", "240", 10)
