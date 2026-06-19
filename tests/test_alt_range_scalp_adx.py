from __future__ import annotations

import math

from strategies.alt_range_scalp_v1 import _adx_from_rows


def _rows(closes: list[float]) -> list[list[float]]:
    rows: list[list[float]] = []
    for i, close in enumerate(closes):
        rows.append([i * 900_000, close, close + 0.6, close - 0.6, close, 100.0])
    return rows


def test_adx_distinguishes_trend_from_balanced_range() -> None:
    trending = _rows([100.0 + i * 0.8 for i in range(50)])
    ranging = _rows([100.0 + (1.0 if i % 2 else -1.0) for i in range(50)])

    trend_adx = _adx_from_rows(trending, 14)
    range_adx = _adx_from_rows(ranging, 14)

    assert math.isfinite(trend_adx)
    assert math.isfinite(range_adx)
    assert trend_adx > 80.0
    assert range_adx < 15.0
    assert trend_adx > range_adx


def test_adx_requires_a_positive_period_and_enough_history() -> None:
    rows = _rows([100.0 + i for i in range(10)])

    assert math.isnan(_adx_from_rows(rows, 0))
    assert math.isnan(_adx_from_rows(rows, 14))
