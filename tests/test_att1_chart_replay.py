from scripts.audit_att1_chart_replay import (
    _forward_path,
    _grid_quality,
    _research_class,
)


def _m5_path() -> list[list[float]]:
    rows = []
    for index in range(12):
        close = 100.0 - index * 0.1
        rows.append([index * 300_000, close + 0.05, close + 0.10, close - 0.10, close, 1.0])
    return rows


def test_short_path_labels_one_r_before_stop() -> None:
    result = _forward_path(
        _m5_path(),
        entry_ts=0,
        entry=100.0,
        sl=101.0,
        side="short",
        forward_hours=1,
    )
    assert result["first_hit"] == "+1R"
    assert result["mfe_r"] >= 1.0
    assert result["coverage"] == 1.0


def test_grid_quality_rejects_a_missing_bar() -> None:
    rows = _m5_path()
    rows.pop(4)
    result = _grid_quality(rows, 300_000)
    assert result["contiguous"] is False
    assert result["gap_count"] == 1


def test_rising_resistance_is_not_relabelled_as_att1() -> None:
    parsed = {"sloped_lines": [{"slope_pct_per_day": 0.2}]}
    g2 = {"allowed": False, "classification": "horizontal_resistance_rejection"}
    assert _research_class(parsed, g2) == "rising_resistance_separate_family"


def test_good_line_with_late_entry_is_separate_from_bad_line() -> None:
    parsed = {"sloped_lines": [{"slope_pct_per_day": -0.5}]}
    g2 = {
        "allowed": False,
        "classification": "descending_trendline_rejection",
        "blockers": ["entry_too_far_after_rejection"],
    }
    assert _research_class(parsed, g2) == "descending_line_pass_execution_or_room_fail"
