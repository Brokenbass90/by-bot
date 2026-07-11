from datetime import datetime, timedelta, timezone

from bot.fx_calendar import assess_schedule_coverage, market_is_open, session_labels


UTC = timezone.utc


def _ts(year, month, day, hour):
    return int(datetime(year, month, day, hour, tzinfo=UTC).timestamp())


def _market_rows(start, hours, schedule):
    rows = []
    for i in range(hours):
        ts = start + i * 3600
        if market_is_open(ts, schedule):
            px = 100 + i * 0.001
            rows.append([ts, px, px + 0.2, px - 0.2, px + 0.05, 1.0])
    return rows


def test_dst_aware_overlap_and_weekend():
    labels = session_labels(_ts(2026, 7, 1, 13))
    assert "london_ny_overlap" in labels
    assert not market_is_open(_ts(2026, 7, 4, 12), "fx_24x5")
    assert market_is_open(_ts(2026, 7, 5, 22), "fx_24x5")


def test_expected_weekend_gap_is_not_a_data_hole():
    rows = _market_rows(_ts(2026, 1, 1, 0), 24 * 240, "fx_24x5")
    report = assess_schedule_coverage(
        rows, symbol="EURUSD", schedule="fx_24x5", min_bars=1000, min_span_days=180
    )
    assert report.ok
    assert report.coverage == 1.0
    assert report.max_missing_run == 0


def test_midweek_hole_fails_even_when_weekends_exist():
    rows = _market_rows(_ts(2026, 1, 1, 0), 24 * 240, "fx_24x5")
    # Remove five consecutive expected Wednesday bars.
    target = _ts(2026, 3, 4, 10)
    rows = [r for r in rows if not (target <= r[0] < target + 5 * 3600)]
    report = assess_schedule_coverage(
        rows, symbol="EURUSD", schedule="fx_24x5", min_bars=1000,
        min_span_days=180, max_missing_run=3,
    )
    assert not report.ok
    assert report.max_missing_run == 5
    assert any("missing_run" in reason for reason in report.reasons)


def test_xau_daily_maintenance_is_schedule_not_missingness():
    rows = _market_rows(_ts(2026, 1, 1, 0), 24 * 240, "xau_23x5")
    report = assess_schedule_coverage(
        rows, symbol="XAUUSD", schedule="xau_23x5", min_bars=1000, min_span_days=180
    )
    assert report.ok and report.max_missing_run == 0


def test_off_schedule_source_bar_is_not_silently_accepted():
    start = _ts(2026, 1, 1, 0)
    rows = _market_rows(start, 24 * 240, "fx_24x5")
    rows.append([_ts(2026, 1, 3, 12), 100.0, 100.2, 99.8, 100.0, 1.0])
    report = assess_schedule_coverage(
        rows, symbol="EURUSD", schedule="fx_24x5", min_bars=1000,
        min_span_days=180,
    )
    assert not report.ok
    assert report.off_schedule_bars == 1
    assert any("off_schedule" in reason for reason in report.reasons)


def test_frozen_window_exposes_trailing_missing_bars():
    start = _ts(2026, 3, 2, 0)
    end = start + 14 * 24 * 3600
    rows = _market_rows(start, 14 * 24, "fx_24x5")
    rows = rows[:-3]
    report = assess_schedule_coverage(
        rows, symbol="EURUSD", schedule="fx_24x5", min_bars=1,
        min_span_days=1, max_missing_run=1,
        window_start_ts=start, window_end_ts_exclusive=end,
    )
    assert not report.ok
    assert report.max_missing_run >= 3


def test_non_finite_or_non_positive_ohlc_is_invalid():
    start = _ts(2026, 3, 2, 8)
    rows = _market_rows(start, 24 * 60, "fx_24x5")
    rows[10][2] = float("inf")
    rows[11][3] = -1.0
    report = assess_schedule_coverage(
        rows, symbol="EURUSD", schedule="fx_24x5",
        min_bars=1, min_span_days=1,
    )
    assert not report.ok
    assert report.invalid_ohlc_bars == 2
