from scripts.xsec_shadow_cycle import _markout, _order_plan


def test_order_plan_estimates_fee_and_half_spread_without_sending_orders():
    orders, cost = _order_plan(
        {"BTCUSDT": -50.0},
        {"BTCUSDT": 100.0},
        {"BTCUSDT": {"bid": 99.0, "ask": 101.0, "last": 100.0}},
        taker_fee_bps=5.5,
    )

    assert len(orders) == 1
    assert orders[0]["side"] == "Buy"
    assert orders[0]["delta_notional_usd"] == 150.0
    assert orders[0]["half_spread_bps"] == 100.0
    assert cost == 150.0 * 105.5 / 10_000.0


def test_phase_markout_handles_long_and_short_notional():
    result = _markout(
        {
            "phase_capital_usd": 100.0,
            "target_usd": {"LONG": 50.0, "SHORT": -50.0},
            "entry_prices": {"LONG": 100.0, "SHORT": 100.0},
            "estimated_entry_cost_usd": 0.1,
        },
        {
            "LONG": {"bid": 109.0, "ask": 111.0, "last": 110.0},
            "SHORT": {"bid": 89.0, "ask": 91.0, "last": 90.0},
        },
    )

    assert result["gross_pnl_usd"] == 10.0
    assert result["gross_return"] == 0.1
    assert result["covered_symbols"] == 2
