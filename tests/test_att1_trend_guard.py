from __future__ import annotations

from strategies.alt_trendline_touch_v1 import (
    AltTrendlineTouchV1Strategy,
    _trend_guard_allows,
)


def test_trend_guard_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ATT1_TREND_GUARD_BARS", raising=False)

    strategy = AltTrendlineTouchV1Strategy()

    assert strategy.cfg.trend_guard_bars == 0
    assert _trend_guard_allows("short", [100.0, 101.0], 0) is True


def test_a3_guard_rejects_short_after_three_bar_rise() -> None:
    closes = [100.0, 101.0, 102.0, 103.0]

    assert _trend_guard_allows("short", closes, 3) is False
    assert _trend_guard_allows("long", closes, 3) is True


def test_a3_guard_rejects_long_after_three_bar_fall() -> None:
    closes = [103.0, 102.0, 101.0, 100.0]

    assert _trend_guard_allows("short", closes, 3) is True
    assert _trend_guard_allows("long", closes, 3) is False


def test_trend_guard_fails_closed_on_short_history() -> None:
    assert _trend_guard_allows("short", [100.0, 99.0], 3) is False
