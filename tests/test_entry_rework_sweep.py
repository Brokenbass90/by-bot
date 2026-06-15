"""Tests for the ASB1/ATT1 entry-rework sweep summarizer."""

from backtest.entry_rework_sweep import _score_combo, combo_label, summarize_result


def test_summarize_result_weights_expectancy_by_trades():
    result = {
        "symbol": "SOLUSDT",
        "windows_with_trades": 2,
        "positive_windows": 1,
        "details": [
            {"metrics": {"trades": 2, "expectancy_R": 1.0, "profit_factor": 2.0}},
            {"metrics": {"trades": 6, "expectancy_R": -0.5, "profit_factor": 0.8}},
        ],
    }
    out = summarize_result(result)
    assert out["total_trades"] == 8
    assert out["weighted_expectancy_R"] == -0.125
    assert out["mean_window_pf"] == 1.4


def test_score_combo_counts_candidate_like_symbols():
    rows = [
        {
            "symbol": "A",
            "windows_with_trades": 4,
            "positive_windows": 3,
            "positive_frac": 0.75,
            "total_trades": 22,
            "weighted_expectancy_R": 0.1,
        },
        {
            "symbol": "B",
            "windows_with_trades": 4,
            "positive_windows": 2,
            "positive_frac": 0.5,
            "total_trades": 30,
            "weighted_expectancy_R": 0.2,
        },
    ]
    score = _score_combo(rows)
    assert score["candidate_like_symbols"] == 1
    assert score["symbols_with_trades"] == 2
    assert score["total_trades"] == 52


def test_combo_label_is_stable():
    assert combo_label({"B": "2", "A": "1"}) == "A=1, B=2"
