from datetime import date

import pytest

from backtest.alpaca_exact_parity_contract import DailyBar
from backtest.alpaca_honest_portfolio import (
    Candidate,
    MonthlyDecision,
    capped_normalized_weights,
    quantize_sell_stop,
    simulate_live_protection_daily_proxy,
)
from scripts.equities_alpaca_paper_bridge import _hard_capped_normalized_weights


def _bar(day: int, open_: float, high: float, low: float, close: float) -> DailyBar:
    return DailyBar(date(2026, 1, day), open_, high, low, close)


def test_hard_weight_cap_cannot_be_rebreached_by_renormalization() -> None:
    assert capped_normalized_weights({"AAA": 10.0}, maximum_weight=0.60) == {"AAA": 0.60}
    weights = capped_normalized_weights({"AAA": 10.0, "BBB": 2.0, "CCC": 1.0}, maximum_weight=0.60)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert max(weights.values()) <= 0.60
    assert weights["AAA"] == pytest.approx(0.60)


def test_backtest_and_live_bridge_share_the_same_hard_cap_sizing() -> None:
    fixture = {"NVDA": 10.0, "KO": 1.0, "JPM": 1.0}

    research = capped_normalized_weights(fixture, maximum_weight=0.60)
    live = _hard_capped_normalized_weights(fixture, maximum_weight=0.60)

    assert live == pytest.approx(research)


def test_sell_stop_quantization_never_rounds_up() -> None:
    assert quantize_sell_stop(105.039) == 105.03
    assert quantize_sell_stop(0.456789) == 0.4567


def test_daily_ratchet_is_next_session_effective_and_cash_is_not_upscaled() -> None:
    data = {
        "AAA": [
            _bar(2, 100.0, 104.5, 99.0, 104.0),
            _bar(3, 100.2, 101.0, 99.5, 100.0),
        ]
    }
    decision = MonthlyDecision(
        signal_session=date(2025, 12, 31),
        entry_session=date(2026, 1, 2),
        picks=(Candidate("AAA", 1.0, 1.0, 1.0, 100.0, 0.60),),
        reason="test",
    )
    result = simulate_live_protection_daily_proxy(
        data,
        [date(2026, 1, 2), date(2026, 1, 3)],
        [decision],
        initial_capital=1_000.0,
        target_gross_exposure=0.70,
        cost_bps_per_side=0.0,
    )

    # One capped name receives only 60% of the 70% sleeve: 42% gross, with
    # the remaining capital explicitly left in cash.
    first = result["daily_equity"][0]
    assert first["cash"] == pytest.approx(580.0)
    assert first["gross_exposure"] < 0.45
    trade = result["trades"][0]
    assert trade["exit_session"] == "2026-01-03"
    assert trade["reason"] == "protective_stop_gap_open"
    assert trade["exit_fill"] == pytest.approx(100.2)


def test_daily_drawdown_includes_initial_capital() -> None:
    data = {"AAA": [_bar(2, 100.0, 100.0, 90.0, 92.0)]}
    decision = MonthlyDecision(
        signal_session=date(2025, 12, 31),
        entry_session=date(2026, 1, 2),
        picks=(Candidate("AAA", 1.0, 10.0, 10.0, 100.0, 1.0),),
        reason="test",
    )
    result = simulate_live_protection_daily_proxy(
        data,
        [date(2026, 1, 2)],
        [decision],
        initial_capital=1_000.0,
        target_gross_exposure=0.70,
        cost_bps_per_side=0.0,
    )
    assert result["daily_max_drawdown_pct"] == pytest.approx(5.6)
