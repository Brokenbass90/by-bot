import datetime as dt

from scripts.materialize_alpaca_pit_daily import select_universe


def test_pit_candidate_universe_keeps_recent_delisted_and_ranks_active_by_liquidity():
    reference = [
        {"ticker": "AAA", "type": "CS", "primary_exchange": "XNYS", "active": True},
        {"ticker": "BBB", "type": "CS", "primary_exchange": "XNAS", "active": True},
        {"ticker": "OLD", "type": "CS", "primary_exchange": "XNYS", "active": False, "delisted_utc": "2025-01-02T00:00:00Z"},
        {"ticker": "ANCIENT", "type": "CS", "primary_exchange": "XNYS", "active": False, "delisted_utc": "2020-01-02T00:00:00Z"},
    ]
    assets = [
        {"symbol": "AAA", "status": "active", "tradable": True},
        {"symbol": "BBB", "status": "active", "tradable": True},
    ]
    result = select_universe(
        reference, assets, {"AAA": 10.0, "BBB": 100.0},
        start=dt.date(2024, 8, 12), target_size=2, inactive_cap=1, force_symbols=[],
    )
    assert result["symbols"] == ["BBB", "OLD"]
    assert result["inactive_selected"] == 1
    assert result["pit_candidate_pool"] is True
    assert result["point_in_time_membership"] is False


def test_forced_symbol_is_retained_beyond_nominal_target():
    reference = [
        {"ticker": "AAA", "type": "CS", "primary_exchange": "XNYS", "active": True},
        {"ticker": "SPY", "type": "CS", "primary_exchange": "ARCX", "active": True},
    ]
    assets = [
        {"symbol": "AAA", "status": "active", "tradable": True},
        {"symbol": "SPY", "status": "active", "tradable": True},
    ]
    result = select_universe(
        reference, assets, {"AAA": 100.0, "SPY": 1.0},
        start=dt.date(2024, 8, 12), target_size=1, inactive_cap=0, force_symbols=["SPY"],
    )
    assert result["symbols"] == ["AAA", "SPY"]
