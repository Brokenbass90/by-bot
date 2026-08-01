from __future__ import annotations

from bot.chart_geometry import pivot_trendlines


def _rows_with_descending_swing_highs() -> list[list[float]]:
    rows: list[list[float]] = []
    highs_by_index = {5: 105.0, 12: 104.0, 19: 103.0}
    for index in range(24):
        base = 100.0 + (index % 3) * 0.05
        high = highs_by_index.get(index, base + 0.4)
        rows.append([index * 3_600_000, base, high, base - 0.4, base, 1.0])
    return rows


def test_pivot_trendline_uses_confirmed_swings_not_all_closes() -> None:
    lines = pivot_trendlines(_rows_with_descending_swing_highs())
    resistance = lines["resistance"]

    assert resistance["kind"] == "swing_pivot_trendline_candidate_v1"
    assert resistance["valid"] is True
    assert resistance["pivot_count"] == 3
    assert resistance["r2"] > 0.99
    assert resistance["slope_pct_per_day"] < 0
    assert resistance["projection_now"] < 103.0


def test_stale_pivot_trendline_is_visible_as_diagnostic_but_not_qualified() -> None:
    rows = _rows_with_descending_swing_highs()
    for index in range(24, 50):
        rows.append([index * 3_600_000, 100.0, 100.4, 99.6, 100.0, 1.0])
    resistance = pivot_trendlines(rows)["resistance"]

    assert resistance["valid"] is False
    assert "pivot_stale" in resistance["blockers"]
