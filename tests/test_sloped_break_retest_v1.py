from strategies.sloped_break_retest_v1 import _retest_expiry_ms


def test_retest_expiry_preserves_millisecond_timestamp_unit() -> None:
    start_ms = 1_786_000_000_000

    expiry_ms = _retest_expiry_ms(start_ms, retest_window_bars=8, tf_seconds=3600)

    assert expiry_ms - start_ms == 8 * 60 * 60 * 1000


def test_retest_expiry_enforces_two_bar_minimum() -> None:
    start_ms = 1_786_000_000_000

    expiry_ms = _retest_expiry_ms(start_ms, retest_window_bars=1, tf_seconds=900)

    assert expiry_ms - start_ms == 2 * 15 * 60 * 1000
