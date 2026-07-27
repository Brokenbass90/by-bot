from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backtest.portfolio_diversification_gate import evaluate_portfolio


def _trade(
    strategy: str,
    month: int,
    result_r: float,
    *,
    segment: str = "oos",
    day: int = 1,
    close_day: int = 2,
) -> dict:
    return {
        "strategy": strategy,
        "opened_at_utc": datetime(
            2025, month, day, tzinfo=timezone.utc
        ).isoformat(),
        "closed_at_utc": datetime(
            2025, month, close_day, tzinfo=timezone.utc
        ).isoformat(),
        "net_return_r": result_r,
        "segment": segment,
    }


def test_three_slot_cap_rejects_fourth_simultaneous_trade() -> None:
    rows = [
        _trade(f"s{i}", 1, 1.0, day=1, close_day=10)
        for i in range(4)
    ]

    result = evaluate_portfolio(
        rows,
        min_oos_months=1,
        min_oos_strategies=2,
    )

    assert result["occupancy"]["accepted_trades"] == 3
    assert result["occupancy"]["rejected_by_three_slot_cap"] == 1
    assert result["occupancy"]["peak_simultaneous_positions"] == 3


def test_calendar_months_include_idle_zero_months() -> None:
    rows = [
        _trade("a", 1, 1.0),
        _trade("b", 3, 1.0),
    ]

    result = evaluate_portfolio(
        rows,
        min_oos_months=3,
        min_oos_strategies=2,
        min_oos_annualized_return_pct=0.0,
        max_top_strategy_profit_share=1.0,
    )

    assert result["oos"]["months"] == 3
    assert result["oos"]["zero_months"] == 1
    assert result["oos"]["negative_months"] == 0
    assert result["aspirational_zero_red_oos_months"] is True


def test_diversification_can_offset_red_legs_without_weight_search() -> None:
    rows = []
    for month in range(1, 13):
        rows.append(_trade("trend", month, 1.0, day=1, close_day=2))
        rows.append(_trade("reversion", month, -0.4, day=3, close_day=4))

    result = evaluate_portfolio(
        rows,
        min_oos_months=12,
        min_oos_annualized_return_pct=3.0,
        max_top_strategy_profit_share=1.0,
    )

    assert result["aspirational_zero_red_oos_months"] is True
    assert result["oos"]["negative_months"] == 0
    assert result["oos"]["annualized_return_pct_simple"] == 3.6
    assert result["verdict"] == "PASS_NEXT_NON_MONEY_GATE"
    assert result["weights_optimized"] is False
    assert result["capital_authorized"] is False


def test_train_months_cannot_hide_oos_red_months() -> None:
    rows = [
        _trade("trend", month, 2.0, segment="train")
        for month in range(1, 7)
    ]
    rows.extend(
        _trade("trend", month, -1.0, segment="oos")
        for month in range(7, 13)
    )
    rows.extend(
        _trade("carry", month, 0.1, segment="oos", day=3, close_day=4)
        for month in range(7, 13)
    )

    result = evaluate_portfolio(
        rows,
        min_oos_months=6,
        max_negative_oos_months_per_year=0,
        min_oos_annualized_return_pct=0.0,
        max_top_strategy_profit_share=1.0,
    )

    assert result["train"]["total_return_pct_simple"] > 0
    assert result["oos"]["negative_months"] == 6
    assert result["aspirational_zero_red_oos_months"] is False
    assert result["verdict"] == "NO_PROMOTION"


def test_invalid_segment_fails_closed() -> None:
    row = _trade("trend", 1, 1.0)
    row["segment"] = "in_sample"

    with pytest.raises(ValueError, match="segment"):
        evaluate_portfolio([row])
