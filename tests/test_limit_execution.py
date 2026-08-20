import pytest

from bot.limit_execution import TradePrint, simulate_limit_then_market


def test_sell_rests_at_ask_and_requires_queue_consumption():
    result = simulate_limit_then_market(
        side="Sell",
        signal_ts_ms=1_000,
        best_bid=99.0,
        best_ask=100.0,
        queue_ahead_qty=2.0,
        order_qty=1.0,
        trades=[
            TradePrint(2_000, 100.0, 1.5, "Buy"),
            TradePrint(3_000, 100.1, 1.5, "Buy"),
        ],
        fallback_bid=98.5,
        fallback_ask=99.5,
    )
    assert result.mode == "maker"
    assert result.limit_price == 100.0
    assert result.fill_ts_ms == 3_000
    assert result.savings_bps_vs_market > 0


def test_buy_does_not_treat_quote_disappearance_or_wrong_aggressor_as_fill():
    result = simulate_limit_then_market(
        side="Buy",
        signal_ts_ms=10_000,
        best_bid=99.0,
        best_ask=100.0,
        queue_ahead_qty=1.0,
        order_qty=1.0,
        trades=[TradePrint(20_000, 98.9, 10.0, "Buy")],
        fallback_bid=100.5,
        fallback_ask=101.0,
    )
    assert result.mode == "market_fallback"
    assert result.execution_price == 101.0
    assert result.fill_ts_ms is None


def test_fallback_at_better_price_can_still_save_without_fake_maker_fee():
    result = simulate_limit_then_market(
        side="Sell",
        signal_ts_ms=1_000,
        best_bid=99.0,
        best_ask=100.0,
        queue_ahead_qty=5.0,
        order_qty=1.0,
        trades=[],
        fallback_bid=99.5,
        fallback_ask=100.5,
    )
    assert result.mode == "market_fallback"
    assert result.fee_bps == pytest.approx(5.5)
    assert result.savings_bps_vs_market > 0


def test_crossed_book_is_rejected():
    with pytest.raises(ValueError, match="crossed book"):
        simulate_limit_then_market(
            side="buy", signal_ts_ms=1, best_bid=101, best_ask=100,
            queue_ahead_qty=0, order_qty=1, trades=[],
            fallback_bid=100, fallback_ask=101,
        )
