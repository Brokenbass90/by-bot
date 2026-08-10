from scripts.alpaca_protective_exit_manager import build_ratchet_plan, build_stop_replace_payload


def _position(price=105.0, entry=100.0, qty=0.5):
    return {"symbol": "SCHW", "current_price": str(price), "avg_entry_price": str(entry), "qty": str(qty)}


def _stop(price=95.0, qty=0.5):
    return {
        "id": "stop-1", "symbol": "SCHW", "side": "sell", "type": "stop",
        "status": "new", "stop_price": str(price), "qty": str(qty), "filled_qty": "0",
        "time_in_force": "gtc",
    }


def test_arms_and_only_raises_existing_broker_stop():
    plan, state = build_ratchet_plan(
        [_position()], [_stop()], {}, activate_gain_pct=3.5, trail_pct=3.5,
        min_lock_gain_pct=0.5, min_raise_bps=10, market_gap_bps=10,
    )
    row = plan[0]
    assert row["action"] == "replace_stop"
    assert row["target_stop"] == 101.32
    assert state["SCHW"]["hwm"] == 105.0


def test_high_water_mark_ratchets_but_never_lowers_stop():
    plan, _ = build_ratchet_plan(
        [_position(price=106.0)], [_stop(price=102.0)], {"SCHW": {"hwm": 110.0}},
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert plan[0]["action"] == "replace_stop"
    assert plan[0]["target_stop"] == 105.89


def test_unarmed_position_and_missing_coverage_fail_closed():
    plan, _ = build_ratchet_plan(
        [_position(price=102.0)], [_stop()], {}, activate_gain_pct=3.5, trail_pct=3.5,
        min_lock_gain_pct=0.5, min_raise_bps=10, market_gap_bps=10,
    )
    assert plan[0]["reason"] == "trail_not_armed"

    plan, _ = build_ratchet_plan(
        [_position()], [], {}, activate_gain_pct=3.5, trail_pct=3.5,
        min_lock_gain_pct=0.5, min_raise_bps=10, market_gap_bps=10,
    )
    assert plan[0]["action"] == "blocked"
    assert plan[0]["reason"] == "expected_one_stop_found_0"


def test_excluded_symbols_are_not_managed():
    plan, state = build_ratchet_plan(
        [_position()], [_stop()], {}, activate_gain_pct=3.5, trail_pct=3.5,
        min_lock_gain_pct=0.5, min_raise_bps=10, market_gap_bps=10,
        excluded_symbols={"SCHW"},
    )
    assert plan == []
    assert state == {}


def test_fractional_stop_replace_preserves_existing_qty():
    payload = build_stop_replace_payload(105.0306)
    assert payload == {"stop_price": "105.03"}
    assert "qty" not in payload
    assert "time_in_force" not in payload


def test_stop_price_uses_four_decimals_below_one_dollar():
    assert build_stop_replace_payload(0.456789) == {"stop_price": "0.4567"}
