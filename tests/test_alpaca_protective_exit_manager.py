from scripts.alpaca_protective_exit_manager import (
    _confirmed_fixed_stop,
    build_ratchet_plan,
    build_stop_replace_payload,
)


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
        [_position(price=106.0)],
        [_stop(price=102.0)],
        {"SCHW": {"entry_price": 100.0, "hwm": 110.0}},
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


def test_state_advances_accepted_floor_only_from_broker_observed_stop():
    plan, state = build_ratchet_plan(
        [_position(price=110.0)],
        [_stop(price=102.0)],
        {"SCHW": {"entry_price": 100.0, "hwm": 109.0, "accepted_stop_floor": 101.0,
                  "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z"}},
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert plan[0]["target_stop"] > 102.0
    assert state["SCHW"]["accepted_stop_floor"] == 102.0


def test_hwm_only_or_rejected_theoretical_raise_does_not_advance_accepted_floor():
    _, state = build_ratchet_plan(
        [_position(price=110.0)],
        [],
        {"SCHW": {"entry_price": 100.0, "hwm": 120.0, "accepted_stop_floor": 103.0,
                  "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z"}},
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert state["SCHW"]["hwm"] == 120.0
    assert state["SCHW"]["accepted_stop_floor"] == 103.0


def test_market_below_accepted_floor_escalates_instead_of_lowering_stop():
    plan, state = build_ratchet_plan(
        [_position(price=105.0)],
        [_stop(price=96.0)],
        {
            "SCHW": {
                "entry_price": 100.0,
                "hwm": 112.0,
                "accepted_stop_floor": 108.0,
                "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z",
            }
        },
        activate_gain_pct=3.5,
        trail_pct=3.5,
        min_lock_gain_pct=0.5,
        min_raise_bps=10,
        market_gap_bps=10,
    )
    assert plan[0]["action"] == "escalate_below_accepted_floor"
    assert plan[0]["reason"] == "market_below_broker_accepted_floor"
    assert state["SCHW"]["accepted_stop_floor"] == 108.0


def test_partial_qty_change_preserves_lifecycle_floor_but_new_entry_resets_it():
    previous = {"SCHW": {"entry_price": 100.0, "hwm": 110.0,
                         "accepted_stop_floor": 104.0,
                         "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z"}}
    _, same = build_ratchet_plan(
        [_position(price=106.0, entry=100.0, qty=0.25)], [], previous,
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert same["SCHW"]["accepted_stop_floor"] == 104.0
    assert same["SCHW"]["lifecycle_first_seen_at_utc"] == "2026-08-10T13:30:00Z"

    _, changed = build_ratchet_plan(
        [_position(price=106.0, entry=101.0, qty=0.25)], [], previous,
        activate_gain_pct=3.5, trail_pct=3.5, min_lock_gain_pct=0.5,
        min_raise_bps=10, market_gap_bps=10,
    )
    assert changed["SCHW"]["accepted_stop_floor"] == 0.0
    assert changed["SCHW"]["hwm"] == 106.0


def test_confirmed_stop_requires_fixed_sell_and_full_coverage():
    assert _confirmed_fixed_stop(_stop(price=104.0), symbol="SCHW", position_qty=0.5)
    assert not _confirmed_fixed_stop(
        {**_stop(price=104.0), "type": "trailing_stop"},
        symbol="SCHW",
        position_qty=0.5,
    )
    assert not _confirmed_fixed_stop(
        {**_stop(price=104.0), "qty": "0.25"},
        symbol="SCHW",
        position_qty=0.5,
    )
    assert not _confirmed_fixed_stop(
        {**_stop(price=104.0), "qty": "0.75"},
        symbol="SCHW",
        position_qty=0.5,
    )
