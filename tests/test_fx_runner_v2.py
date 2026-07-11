from datetime import datetime, timezone

import pytest

from scripts.run_fx_v2_preregistered_gate_20260711 import (
    _aggregate_h1_complete,
    _contiguous_market_segments,
    _load_m5,
)


UTC = timezone.utc


def _ts(year, month, day, hour, minute=0):
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp())


def _m5_hour(start, count=12):
    return [
        [start + i * 300, 100.0, 100.2, 99.8, 100.0, 1.0]
        for i in range(count)
    ]


def test_h1_aggregation_rejects_partial_source_hour():
    start = _ts(2026, 7, 6, 8)
    complete, missing = _aggregate_h1_complete(
        _m5_hour(start), schedule="fx_24x5", source_interval_sec=300
    )
    assert len(complete) == 1 and missing == []

    partial, missing = _aggregate_h1_complete(
        _m5_hour(start, 11), schedule="fx_24x5", source_interval_sec=300
    )
    assert partial == []
    assert missing[0]["missing_subbars"] == 1


def test_market_segments_reset_on_unknown_midweek_gap_not_weekend():
    monday = _ts(2026, 7, 6, 8)
    rows = [
        [monday, 1, 2, 0.5, 1, 1],
        [monday + 2 * 3600, 1, 2, 0.5, 1, 1],
    ]
    assert len(_contiguous_market_segments(rows, schedule="fx_24x5")) == 2

    friday = _ts(2026, 7, 10, 20)
    sunday = _ts(2026, 7, 12, 21)
    weekend_rows = [
        [friday, 1, 2, 0.5, 1, 1],
        [sunday, 1, 2, 0.5, 1, 1],
    ]
    assert len(_contiguous_market_segments(weekend_rows, schedule="fx_24x5")) == 1


def test_loader_fails_closed_on_non_finite_ohlc(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("ts,o,h,l,c,v\n1,1,inf,0.9,1,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid OHLCV"):
        _load_m5(path)
