import json
from datetime import date, datetime, timezone

from scripts.xsec_shadow_cycle import (
    _markout,
    _maturity_audit,
    _order_plan,
    _sanitize_returns,
)


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
    assert result["eligible_for_leverage_history"] is True
    assert len(result["contributions"]) == 2


def test_phase_markout_flags_portfolio_outlier_from_leverage_history():
    result = _markout(
        {
            "phase_capital_usd": 100.0,
            "target_usd": {"MOON": 100.0},
            "entry_prices": {"MOON": 100.0},
        },
        {"MOON": {"bid": 199.0, "ask": 201.0, "last": 200.0}},
    )

    assert result["gross_return"] == 1.0
    assert result["portfolio_anomaly"] is True
    assert result["anomaly_symbols"] == ["MOON"]
    assert result["eligible_for_leverage_history"] is False


def test_phase_markout_rejects_incomplete_attribution():
    result = _markout(
        {
            "phase_capital_usd": 100.0,
            "target_usd": {"KNOWN": 50.0, "MISSING": -50.0},
            "entry_prices": {"KNOWN": 100.0},
        },
        {"KNOWN": {"bid": 109.0, "ask": 111.0, "last": 110.0}},
    )

    assert result["coverage_complete"] is False
    assert result["missing_symbols"] == ["MISSING"]
    assert result["gross_return"] is None
    assert result["eligible_for_leverage_history"] is False


def test_sanitize_returns_drops_legacy_outliers_and_malformed_values():
    accepted, dropped = _sanitize_returns([0.1, "-0.2", 0.61, "bad", None])

    assert accepted == [0.1, -0.2]
    assert dropped == [0.61, "bad", None]


def test_maturity_audit_uses_exchange_launch_time(tmp_path):
    as_of = date(2026, 8, 11)
    mature_launch = int(
        datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
    )
    young_launch = int(
        datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp() * 1000
    )
    path = tmp_path / "instruments.json"
    path.write_text(
        json.dumps({"records": [
            {"symbol": "OLDUSDT", "launchTime": str(mature_launch)},
            {"symbol": "NEWUSDT", "launchTime": str(young_launch)},
        ]}),
        encoding="utf-8",
    )

    result = _maturity_audit(["OLDUSDT", "NEWUSDT"], path, as_of)

    assert result["eligible_symbols"] == ["OLDUSDT"]
    assert result["excluded_launch_time"] == {"NEWUSDT": young_launch}
