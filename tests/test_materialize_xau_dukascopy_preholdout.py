import argparse
import datetime as dt
from pathlib import Path

import pytest

import scripts.materialize_xau_dukascopy_preholdout as materializer
from scripts.materialize_xau_dukascopy_preholdout import SEALED_START, materialize, month_windows


def test_month_windows_are_contiguous_and_end_exclusive():
    start = dt.datetime(2024, 11, 15, tzinfo=dt.UTC)
    end = dt.datetime(2025, 2, 2, tzinfo=dt.UTC)
    windows = list(month_windows(start, end))
    assert windows[0][0] == start
    assert windows[-1][1] == end
    assert all(left[1] == right[0] for left, right in zip(windows, windows[1:]))


def test_materializer_refuses_sealed_holdout_before_network(tmp_path):
    args = argparse.Namespace(
        from_utc="2025-09-01",
        to_utc="2025-10-02",
        out_dir=str(tmp_path),
        sleep_sec=0.0,
        timeout_sec=0.1,
        hour_retries=0,
        month_attempts=1,
        retry_delay_sec=0.0,
        min_free_gb=0.0,
    )
    with pytest.raises(ValueError, match="sealed holdout"):
        materialize(args)
    assert SEALED_START == dt.datetime(2025, 10, 1, tzinfo=dt.UTC)


def test_source_writes_current_month_status_before_slow_download() -> None:
    source = Path(materializer.__file__).read_text(encoding="utf-8")

    status_write = source.index('"current_month": name')
    download_call = source.index("_build_rows_for_pair(")

    assert status_write < download_call
