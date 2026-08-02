from __future__ import annotations

from bot.att1_geometry_v2 import (
    enforced_geometry_v2_blockers,
    evaluate_att1_short_geometry_v2,
)


def _rows_with_descending_resistance_and_room() -> list[list[float]]:
    rows: list[list[float]] = []
    pivot_highs = {8: 105.0, 16: 104.0, 24: 103.0}
    pivot_lows = {5: 96.0, 18: 95.0}
    for index in range(29):
        base = 100.0 - index * 0.03
        high = pivot_highs.get(index, base + 0.25)
        low = pivot_lows.get(index, base - 0.25)
        rows.append([index * 3_600_000, base + 0.10, high, low, base, 1.0])
    # Fourth touch/rejection at the projected descending resistance.
    rows.append([29 * 3_600_000, 102.45, 102.55, 101.95, 102.05, 1.0])
    return rows


def _current_ltc_like_rows() -> list[list[float]]:
    rows: list[list[float]] = []
    pivot_highs = {9: 44.75, 31: 44.77, 36: 44.79}
    pivot_lows = {14: 44.40, 34: 44.40}
    for index in range(39):
        base = 44.60
        high = pivot_highs.get(index, 44.70)
        low = pivot_lows.get(index, 44.50)
        rows.append([index * 3_600_000, 44.62, high, low, base, 1.0])
    rows.append([39 * 3_600_000, 44.81, 44.81, 44.65, 44.66, 1.0])
    return rows


def test_geometry_v2_accepts_descending_line_with_room() -> None:
    decision = evaluate_att1_short_geometry_v2(
        _rows_with_descending_resistance_and_room(),
        entry=102.05,
        sl=103.10,
        min_r2=0.50,
        max_entry_distance_atr=1.0,
        min_room_to_support_r=0.50,
    )

    assert decision.classification == "descending_trendline_rejection"
    assert "resistance_not_descending" not in decision.blockers
    assert "opposing_support_too_close" not in decision.blockers


def test_geometry_v2_blocks_rising_line_and_near_support() -> None:
    decision = evaluate_att1_short_geometry_v2(
        _current_ltc_like_rows(),
        entry=44.65,
        sl=45.04,
        min_r2=0.55,
    )

    assert decision.allowed is False
    assert "resistance_not_descending" in decision.blockers
    assert "opposing_support_too_close" in decision.blockers
    assert decision.nearest_support is not None
    assert decision.nearest_support_source in {"horizontal_pivots", "equal_low_liquidity"}


def test_geometry_v2_reports_horizontal_origin_separately() -> None:
    decision = evaluate_att1_short_geometry_v2(
        _current_ltc_like_rows(),
        entry=44.65,
        sl=45.04,
        min_r2=0.55,
    )

    assert decision.classification == "horizontal_resistance_rejection"
    assert decision.horizontal_origin is not None
    assert decision.horizontal_origin_source in {"horizontal_pivots", "equal_high_liquidity"}
    assert "setup_belongs_to_horizontal_family" in decision.blockers


def test_geometry_v2_profiles_decompose_independent_failure_families() -> None:
    decision = evaluate_att1_short_geometry_v2(
        _current_ltc_like_rows(),
        entry=44.65,
        sl=45.04,
        min_r2=0.55,
    )

    assert enforced_geometry_v2_blockers(decision, "line_quality")
    assert enforced_geometry_v2_blockers(decision, "room") == ("opposing_support_too_close",)
    assert enforced_geometry_v2_blockers(decision, "attribution") == (
        "setup_belongs_to_horizontal_family",
    )
    assert set(enforced_geometry_v2_blockers(decision, "line_quality+room")) == {
        blocker
        for blocker in decision.blockers
        if blocker
        in {
            "no_resistance_trendline",
            "insufficient_confirmed_pivots",
            "resistance_not_descending",
            "pivot_fit_too_weak",
            "opposing_support_too_close",
        }
    }
