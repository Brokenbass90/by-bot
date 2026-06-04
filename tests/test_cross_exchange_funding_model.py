from scripts.cross_exchange_funding_shadow import (
    MODEL_VERSION,
    _aligned_next_epoch,
    _pair_price_pnl_pct,
    _settle_funding,
)


def test_delta_neutral_price_pnl_uses_executable_prices():
    pos = {
        "long_entry_exec": 100.0,
        "short_entry_exec": 100.0,
    }
    assert abs(_pair_price_pnl_pct(pos, 101.0, 101.0)) < 1e-9


def test_funding_is_not_accrued_before_settlement():
    pos = {
        "opened_at_epoch": 1000.0,
        "short_funding_interval_h": 8.0,
        "long_funding_interval_h": 8.0,
        "short_next_funding_epoch": 2000.0,
        "long_next_funding_epoch": 2000.0,
        "short_pending_funding_event_pct": 0.1,
        "long_pending_funding_event_pct": -0.1,
        "funding_settled_pct_per_leg": 0.0,
    }
    current = {
        "short_funding_event_pct": 0.1,
        "long_funding_event_pct": -0.1,
    }
    assert _settle_funding(pos, current, 1999.0) == 0.0


def test_funding_is_credited_only_after_settlement():
    pos = {
        "opened_at_epoch": 1000.0,
        "short_funding_interval_h": 8.0,
        "long_funding_interval_h": 8.0,
        "short_next_funding_epoch": 2000.0,
        "long_next_funding_epoch": 2000.0,
        "short_pending_funding_event_pct": 0.1,
        "long_pending_funding_event_pct": -0.1,
        "funding_settled_pct_per_leg": 0.0,
    }
    current = {
        "short_funding_event_pct": 0.1,
        "long_funding_event_pct": -0.1,
    }
    assert round(_settle_funding(pos, current, 2001.0), 6) == 0.2
    assert len(pos["funding_events"]) == 2


def test_missing_current_snapshot_uses_last_pre_settlement_rate_then_clears_it():
    pos = {
        "opened_at_epoch": 1000.0,
        "short_funding_interval_h": 8.0,
        "long_funding_interval_h": 8.0,
        "short_next_funding_epoch": 2000.0,
        "long_next_funding_epoch": 2000.0,
        "short_pending_funding_event_pct": 0.1,
        "long_pending_funding_event_pct": -0.1,
        "funding_settled_pct_per_leg": 0.0,
    }
    assert round(_settle_funding(pos, None, 2001.0), 6) == 0.2
    assert pos["short_pending_funding_event_pct"] == 0.0
    assert pos["long_pending_funding_event_pct"] == 0.0


def test_model_version_is_explicit():
    assert MODEL_VERSION == "settlement_execution_v2"
    assert _aligned_next_epoch(0.0, 8.0) == 8.0 * 3600.0
