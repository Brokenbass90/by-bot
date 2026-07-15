from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_multicoin_pattern_atlas_v1 import (
    DEFAULT_CONFIG,
    H1_MS,
    PatternAtlasError,
    analyze_h1_symbol,
    detect_pattern_ids,
    discovery_end_exclusive,
    forward_path,
    load_discovery_m5_rows,
    load_preregistration,
    summarize_observations,
)


ROOT = Path(__file__).resolve().parents[1]


def _bar(index: int, o: float, h: float, low: float, c: float) -> tuple[int, float, float, float, float, float]:
    return (index * H1_MS, o, h, low, c, 100.0)


def _config() -> dict:
    return {
        "event_contract": {
            "prior_range_lookback_h1": 20,
            "touch_tolerance_bps": 10.0,
            "minimum_wick_to_body_ratio": 1.5,
            "same_pattern_cooldown_h1": 168,
            "forward_horizons_h1": [6, 24, 72, 168],
        }
    }


def test_frozen_preregistration_and_pins_validate() -> None:
    config = load_preregistration(ROOT, DEFAULT_CONFIG)

    assert config["discovery_only"] is True
    assert config["promotion_eligible"] is False
    assert [item["side"] for item in config["patterns"]].count("long") == 3
    assert [item["side"] for item in config["patterns"]].count("short") == 3


def test_discovery_cutoff_reserves_at_least_120_days_and_is_complete_h1() -> None:
    full_end = 1_783_173_900_000
    cutoff = discovery_end_exclusive(full_end)

    assert cutoff % H1_MS == 0
    assert full_end - cutoff >= 120 * 86_400_000
    assert full_end - cutoff < 120 * 86_400_000 + H1_MS


def test_prefix_loader_stops_before_malformed_sealed_tail(tmp_path: Path) -> None:
    start = 1_800_000_000_000
    rows = []
    for index in range(12):
        ts = start + index * 300_000
        rows.append({"ts": ts, "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 1})
    # Deliberately malformed sealed JSON: success proves the decoder never asks
    # for the first holdout object after consuming the exact discovery prefix.
    path = tmp_path / "source.json"
    path.write_text(json.dumps(rows)[:-1] + ',{"ts":BROKEN}]', encoding="utf-8")

    loaded = load_discovery_m5_rows(
        path,
        start_ts=start,
        discovery_end_ts_exclusive=start + H1_MS,
    )

    assert len(loaded) == 12
    assert loaded[-1][0] < start + H1_MS


def test_patterns_use_only_prior_range_and_keep_physical_sides_separate() -> None:
    prior = [_bar(index, 100, 110, 90, 100) for index in range(20)]
    breakout_long = prior + [_bar(20, 105, 115, 104, 112)]
    failed_short = prior + [_bar(20, 105, 115, 100, 99)]
    rejection_long = prior + [_bar(20, 100, 103, 89.95, 101)]

    assert detect_pattern_ids(breakout_long, 20) == ("horizontal_breakout_long",)
    assert "failed_break_reversal_short" in detect_pattern_ids(failed_short, 20)
    assert "horizontal_rejection_short" in detect_pattern_ids(failed_short, 20)
    assert "horizontal_rejection_long" in detect_pattern_ids(rejection_long, 20)


def test_forward_path_enters_next_h1_open_and_has_side_correct_mfe_mae() -> None:
    bars = [
        _bar(0, 100, 101, 99, 100),
        _bar(1, 110, 121, 99, 120),
        _bar(2, 120, 132, 108, 110),
    ]

    long = forward_path(bars, signal_index=0, horizon_h1=2, side="long")
    short = forward_path(bars, signal_index=0, horizon_h1=2, side="short")

    assert long["entry_ts"] == H1_MS
    assert long["return_bps"] == pytest.approx(0.0)
    assert long["mfe_bps"] == pytest.approx(2000.0)
    assert long["mae_bps"] == pytest.approx(-1000.0)
    assert short["return_bps"] == pytest.approx(0.0)
    assert short["mfe_bps"] == pytest.approx(1000.0)
    assert short["mae_bps"] == pytest.approx(-2000.0)


def test_analysis_never_crosses_discovery_end_and_summary_keeps_empty_cells() -> None:
    bars = [_bar(index, 100, 101, 99, 100) for index in range(210)]
    bars[20] = _bar(20, 100, 112, 100, 111)
    observations, controls = analyze_h1_symbol("TESTUSDT", bars, _config())

    assert observations
    assert all(row["exit_ts"] <= len(bars) * H1_MS for row in observations)
    assert all(row["entry_ts"] > row["signal_close_ts"] - 1 for row in observations)
    summaries = summarize_observations(observations, controls)
    assert len(summaries) == 24
    assert any(row["n"] == 0 and row["mean_return_bps"] is None for row in summaries)
    breakout_168 = next(
        row for row in summaries
        if row["pattern_id"] == "horizontal_breakout_long" and row["horizon_h1"] == 168
    )
    assert breakout_168["n"] == 1


def test_forward_path_fails_closed_if_horizon_enters_sealed_space() -> None:
    bars = [_bar(index, 100, 101, 99, 100) for index in range(10)]
    with pytest.raises(PatternAtlasError, match="crosses"):
        forward_path(bars, signal_index=5, horizon_h1=6, side="long")
