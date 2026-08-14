import argparse
import datetime as dt
from pathlib import Path

import pytest

import scripts.materialize_xau_dukascopy_preholdout as materializer
from scripts.materialize_xau_dukascopy_preholdout import SEALED_START, day_windows, materialize, month_windows


def test_month_windows_are_contiguous_and_end_exclusive():
    start = dt.datetime(2024, 11, 15, tzinfo=dt.UTC)
    end = dt.datetime(2025, 2, 2, tzinfo=dt.UTC)
    windows = list(month_windows(start, end))
    assert windows[0][0] == start
    assert windows[-1][1] == end
    assert all(left[1] == right[0] for left, right in zip(windows, windows[1:]))


def test_day_windows_are_contiguous_and_end_exclusive():
    start = dt.datetime(2025, 1, 1, 5, tzinfo=dt.UTC)
    end = dt.datetime(2025, 1, 3, 7, tzinfo=dt.UTC)
    windows = list(day_windows(start, end))
    assert windows == [
        (start, dt.datetime(2025, 1, 2, tzinfo=dt.UTC)),
        (dt.datetime(2025, 1, 2, tzinfo=dt.UTC), dt.datetime(2025, 1, 3, tzinfo=dt.UTC)),
        (dt.datetime(2025, 1, 3, tzinfo=dt.UTC), end),
    ]


def test_materializer_refuses_sealed_holdout_before_network(tmp_path):
    args = argparse.Namespace(
        from_utc="2025-09-01",
        to_utc="2025-10-02",
        out_dir=str(tmp_path),
        sleep_sec=0.0,
        timeout_sec=0.1,
        hour_retries=0,
        window_attempts=1,
        max_quarantined_days=0,
        retry_delay_sec=0.0,
        min_free_gb=0.0,
    )
    with pytest.raises(ValueError, match="sealed holdout"):
        materialize(args)
    assert SEALED_START == dt.datetime(2025, 10, 1, tzinfo=dt.UTC)


def test_source_writes_current_day_status_before_slow_download() -> None:
    source = Path(materializer.__file__).read_text(encoding="utf-8")

    status_write = source.index('"current_day": name')
    download_call = source.index("_build_rows_for_pair(")

    assert status_write < download_call


def test_materializer_quarantines_failed_day_and_continues(tmp_path, monkeypatch):
    calls = []

    def fake_build(**kwargs):
        day = kwargs["start_utc"].strftime("%Y-%m-%d")
        calls.append(day)
        if day == "2025-01-01":
            return [], {"hours_fail": 1}, "HTTP 503"
        if day == "2025-01-02":
            return [], {"hours_fail": 0}, ""
        ts = int(kwargs["start_utc"].timestamp())
        return [(ts, 1.0, 1.1, 0.9, 1.0, 2.0)], {"hours_fail": 0}, ""

    monkeypatch.setattr(materializer, "_build_rows_for_pair", fake_build)
    args = argparse.Namespace(
        from_utc="2025-01-01",
        to_utc="2025-01-04",
        out_dir=str(tmp_path),
        sleep_sec=0.0,
        timeout_sec=0.1,
        hour_retries=0,
        window_attempts=1,
        retry_delay_sec=0.0,
        min_free_gb=0.0,
        max_quarantined_days=2,
    )
    assert materialize(args) == 4
    status = __import__("json").loads((tmp_path / "status.json").read_text())
    assert status["state"] == "complete_with_quarantine"
    assert status["promotion_eligible"] is False
    assert status["quarantined_days"][0]["day"] == "2025-01-01"
    assert status["empty_market_days"] == ["2025-01-02"]
    assert calls == ["2025-01-01", "2025-01-02", "2025-01-03"]


def test_materializer_stops_when_quarantine_guard_is_exceeded(tmp_path, monkeypatch):
    def fake_build(**_kwargs):
        return [], {"hours_fail": 1}, "HTTP 503"

    monkeypatch.setattr(materializer, "_build_rows_for_pair", fake_build)
    args = argparse.Namespace(
        from_utc="2025-01-01",
        to_utc="2025-01-03",
        out_dir=str(tmp_path),
        sleep_sec=0.0,
        timeout_sec=0.1,
        hour_retries=0,
        window_attempts=1,
        retry_delay_sec=0.0,
        min_free_gb=0.0,
        max_quarantined_days=0,
    )
    assert materialize(args) == 2
    status = __import__("json").loads((tmp_path / "status.json").read_text())
    assert status["state"] == "quarantine_guard"
    assert status["promotion_eligible"] is False


def test_materializer_resumes_empty_and_quarantined_days_without_refetch(tmp_path, monkeypatch):
    (tmp_path / "status.json").write_text(
        '{"empty_market_days":["2025-01-01"],"quarantined_days":'
        '[{"day":"2025-01-02","last_error":"HTTP 503"}]}',
        encoding="utf-8",
    )
    calls = []

    def fake_build(**kwargs):
        calls.append(kwargs["start_utc"].strftime("%Y-%m-%d"))
        ts = int(kwargs["start_utc"].timestamp())
        return [(ts, 1.0, 1.1, 0.9, 1.0, 2.0)], {"hours_fail": 0}, ""

    monkeypatch.setattr(materializer, "_build_rows_for_pair", fake_build)
    args = argparse.Namespace(
        from_utc="2025-01-01", to_utc="2025-01-04", out_dir=str(tmp_path),
        sleep_sec=0.0, timeout_sec=0.1, hour_retries=0, window_attempts=1,
        retry_delay_sec=0.0, min_free_gb=0.0, max_quarantined_days=2,
        retry_quarantined=False,
    )
    assert materialize(args) == 4
    assert calls == ["2025-01-03"]


def test_materializer_skips_weekends_without_network(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(materializer, "_build_rows_for_pair", lambda **kwargs: calls.append(kwargs) or ([], {"hours_fail": 0}, ""))
    args = argparse.Namespace(
        from_utc="2025-01-04", to_utc="2025-01-06", out_dir=str(tmp_path),
        sleep_sec=0.0, timeout_sec=0.1, hour_retries=0, window_attempts=1,
        retry_delay_sec=0.0, min_free_gb=0.0, max_quarantined_days=2,
        retry_quarantined=False,
    )
    assert materialize(args) == 2
    assert calls == []
    status = __import__("json").loads((tmp_path / "status.json").read_text())
    assert status["empty_market_days"] == ["2025-01-04", "2025-01-05"]
