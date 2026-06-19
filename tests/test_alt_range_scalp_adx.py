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


def test_adx_matches_wilder_reference_fixture() -> None:
    closes = [
        100.0, 101.4, 100.7, 102.2, 101.1, 100.2, 99.8, 100.9, 102.0, 101.6,
        103.1, 102.5, 101.7, 100.8, 101.9, 103.0, 104.2, 103.7, 102.9, 104.4,
        105.2, 104.1, 103.3, 102.6, 103.8, 105.0, 106.3, 105.5, 104.6, 105.9,
        107.1, 106.4, 105.2, 104.7, 105.8, 107.4, 108.1, 107.2, 106.0, 107.3,
        108.8, 109.4, 108.2, 107.5, 108.9, 110.1, 109.0, 108.4, 109.8, 111.0,
    ]

    assert math.isclose(_adx_from_rows(_rows(closes), 14), 20.13801282827233, rel_tol=1e-12)
