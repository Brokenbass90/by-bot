from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext

import pytest

from research_lab.att1_ets2s_lifecycle import (
    ExposureEvent,
    ExposurePlan,
    LifecycleViolation,
    apply_event,
    initial_state,
    replay,
    target_close_qty,
)


def _plan(**changes):
    values = {
        "book": "SYNTHETIC_BOOK",
        "sleeve": "ATT1",
        "symbol": "HFTUSDT",
        "decision_id": "decision-1",
        "order_id": "order-1",
        "profile_id": "SYNTHETIC_ATT1_V1",
        "qty_step": "0.1",
        "requested_qty": "0.3",
        "submit_ms": 100,
    }
    values.update(changes)
    return ExposurePlan(**values)


def _event(event_id, kind, *, qty=None, execution_id=None, exchange_ms=101, received_ms=102, **changes):
    values = {
        "event_id": event_id,
        "kind": kind,
        "order_id": "order-1",
        "exchange_ms": exchange_ms,
        "received_ms": received_ms,
        "execution_id": execution_id,
        "qty": qty,
    }
    values.update(changes)
    return ExposureEvent(**values)


def test_ack_then_partial_fill_keeps_pending_entry_and_unconfirmed_protection_visible():
    plan = _plan()
    state = replay(
        plan,
        (
            _event("ack", "ENTRY_ACK"),
            _event("fill-1", "ENTRY_FILL", qty="0.1", execution_id="entry-1", exchange_ms=103, received_ms=104),
        ),
    )

    assert state.held_qty == Decimal("0.1")
    assert state.pending_entry_qty == Decimal("0.2")
    assert state.protected_qty == Decimal("0")
    assert state.unprotected_qty == Decimal("0.1")
    assert state.terminal_eligible is False


def test_partial_entry_late_fill_cancel_final_and_emergency_exit_conserve_observed_quantity():
    plan = _plan()
    before_final = replay(
        plan,
        (
            _event("fill-1", "ENTRY_FILL", qty="0.1", execution_id="entry-1"),
            _event("protect", "PROTECTION_ACK", qty="0.1", exchange_ms=103, received_ms=104),
            _event("exit-1", "EXIT_FILL", qty="0.1", execution_id="exit-1", exchange_ms=105, received_ms=106),
            _event("late-fill", "ENTRY_FILL", qty="0.2", execution_id="entry-2", exchange_ms=107, received_ms=108),
        ),
    )
    assert before_final.held_qty == Decimal("0.2")
    assert before_final.pending_entry_qty == Decimal("0")
    assert before_final.terminal_eligible is False

    terminal = replay(
        plan,
        before_final.accepted_events
        + (
            _event("cancel-final", "ENTRY_FINAL", exchange_ms=109, received_ms=110),
            _event("exit-2", "EXIT_FILL", qty="0.2", execution_id="exit-2", exchange_ms=111, received_ms=112),
        ),
    )
    assert terminal.entry_filled_qty == Decimal("0.3")
    assert terminal.exit_filled_qty == Decimal("0.3")
    assert terminal.held_qty == Decimal("0")
    assert terminal.terminal_eligible is True


def test_cancel_request_alone_allows_late_fill_and_final_cancellation_only_ends_pending_entry():
    plan = _plan()
    state = replay(
        plan,
        (
            _event("cancel", "CANCEL_REQUEST"),
            _event("late-fill", "ENTRY_FILL", qty="0.1", execution_id="entry-1", exchange_ms=103, received_ms=104),
        ),
    )
    assert state.cancel_requested is True
    assert state.held_qty == Decimal("0.1")
    assert state.pending_entry_qty == Decimal("0.2")

    final = apply_event(state, _event("final", "ENTRY_FINAL", exchange_ms=105, received_ms=106))
    assert final.held_qty == Decimal("0.1")
    assert final.pending_entry_qty == Decimal("0")
    assert final.entry_final is True


def test_late_and_over_planned_entry_fills_remain_visible_and_make_terminal_ineligible():
    plan = _plan(requested_qty="0.1")
    state = replay(
        plan,
        (
            _event("final", "ENTRY_FINAL"),
            _event("late", "ENTRY_FILL", qty="0.1", execution_id="entry-1", exchange_ms=103, received_ms=104),
            _event("over", "ENTRY_FILL", qty="0.2", execution_id="entry-2", exchange_ms=105, received_ms=106),
            _event("exit", "EXIT_FILL", qty="0.3", execution_id="exit-1", exchange_ms=107, received_ms=108),
        ),
    )
    assert state.entry_filled_qty == Decimal("0.3")
    assert state.held_qty == Decimal("0")
    assert "INCIDENT_UNEXPECTED_ENTRY_FILL" in state.incidents
    assert state.terminal_eligible is False


def test_identical_events_and_executions_are_idempotent_but_conflicts_fail():
    plan = _plan()
    fill = _event("fill-1", "ENTRY_FILL", qty="0.1", execution_id="entry-1")
    state = apply_event(initial_state(plan), fill)
    assert apply_event(state, fill) == state

    duplicate_execution = _event("fill-copy", "ENTRY_FILL", qty="0.1", execution_id="entry-1")
    deduplicated = apply_event(state, duplicate_execution)
    assert deduplicated.held_qty == Decimal("0.1")
    assert len(deduplicated.accepted_event_fingerprints) == 2

    with pytest.raises(LifecycleViolation):
        apply_event(state, _event("fill-1", "ENTRY_FILL", qty="0.2", execution_id="entry-1"))
    with pytest.raises(LifecycleViolation):
        apply_event(state, _event("fill-other", "ENTRY_FILL", qty="0.2", execution_id="entry-1", exchange_ms=103, received_ms=104))


def test_exit_overfill_and_foreign_order_reject_without_mutating_input_state():
    state = apply_event(initial_state(_plan()), _event("fill", "ENTRY_FILL", qty="0.1", execution_id="entry-1"))
    with pytest.raises(LifecycleViolation):
        apply_event(state, _event("too-much", "EXIT_FILL", qty="0.2", execution_id="exit-1", exchange_ms=103, received_ms=104))
    with pytest.raises(LifecycleViolation):
        apply_event(state, _event("foreign", "ENTRY_FILL", qty="0.1", execution_id="entry-2", order_id="other", exchange_ms=103, received_ms=104))
    assert state.held_qty == Decimal("0.1")
    assert state.pending_entry_qty == Decimal("0.2")


def test_target_close_quantity_uses_step_counts_and_final_closes_exact_remainder_without_dust():
    first = target_close_qty("0.3", "0.3", "0.1", "0.55")
    remainder = Decimal("0.3") - first
    final = target_close_qty("0.3", str(remainder), "0.1", "0.55", final=True)
    assert first == Decimal("0.1")
    assert final == Decimal("0.2")
    assert remainder - final == Decimal("0")


def test_final_target_returns_exact_zero_when_no_quantity_remains():
    assert target_close_qty("0.3", "0", "0.1", "0.55", final=True) == Decimal("0")


def test_step_validation_and_target_floor_do_not_depend_on_caller_decimal_precision():
    with localcontext() as context:
        context.prec = 3
        with pytest.raises(LifecycleViolation):
            initial_state(_plan(qty_step="1", requested_qty="123456789012345678901234567890.1"))
        assert target_close_qty("0.3", "0.3", "0.1", "0.55") == Decimal("0.1")
        assert target_close_qty("999", "999", "1", "0.5555") == Decimal("554")


def test_exposed_quantities_do_not_round_under_a_low_caller_decimal_context():
    with localcontext() as context:
        context.prec = 3
        state = apply_event(
            initial_state(
                _plan(
                    qty_step="0.1111111111111111111111111111111111111111111111111111111111111111",
                    requested_qty="0.2222222222222222222222222222222222222222222222222222222222222222",
                )
            ),
            _event(
                "fill",
                "ENTRY_FILL",
                qty="0.2222222222222222222222222222222222222222222222222222222222222222",
                execution_id="entry-1",
            ),
        )
    assert state.held_qty == Decimal("0.2222222222222222222222222222222222222222222222222222222222222222")


def test_decimal_inputs_with_excessive_precision_are_rejected_before_replay():
    with pytest.raises(LifecycleViolation):
        initial_state(_plan(requested_qty="11111111111111111111111111111111111111111111111111111111111111111"))


def test_non_string_fill_quantity_fails_as_a_lifecycle_violation():
    with pytest.raises(LifecycleViolation):
        apply_event(initial_state(_plan()), _event("fill", "ENTRY_FILL", qty=Decimal("0.1"), execution_id="entry-1"))


def test_identical_old_execution_redelivery_is_accepted_without_rewinding_watermarks():
    plan = _plan()
    state = replay(
        plan,
        (
            _event("fill", "ENTRY_FILL", qty="0.1", execution_id="entry-1", exchange_ms=101, received_ms=102),
            _event("ack", "ENTRY_ACK", exchange_ms=105, received_ms=106),
        ),
    )
    redelivery = apply_event(
        state,
        _event("fill-redelivery", "ENTRY_FILL", qty="0.1", execution_id="entry-1", exchange_ms=101, received_ms=102),
    )
    assert redelivery.held_qty == Decimal("0.1")
    assert redelivery.last_exchange_ms == 105
    assert redelivery.last_received_ms == 106
    assert "fill-redelivery" in redelivery.accepted_event_fingerprints


def test_unseen_old_execution_remains_a_causal_order_violation():
    state = replay(
        _plan(),
        (
            _event("fill", "ENTRY_FILL", qty="0.1", execution_id="entry-1", exchange_ms=101, received_ms=102),
            _event("ack", "ENTRY_ACK", exchange_ms=105, received_ms=106),
        ),
    )
    with pytest.raises(LifecycleViolation):
        apply_event(
            state,
            _event("unseen-old", "ENTRY_FILL", qty="0.1", execution_id="entry-2", exchange_ms=103, received_ms=104),
        )
    assert state.held_qty == Decimal("0.1")


def test_unknown_and_partial_protection_remain_explicit_and_do_not_block_exit():
    plan = _plan()
    partial = replay(
        plan,
        (
            _event("fill", "ENTRY_FILL", qty="0.2", execution_id="entry-1"),
            _event("protect", "PROTECTION_ACK", qty="0.1", exchange_ms=103, received_ms=104),
        ),
    )
    assert partial.protected_qty == Decimal("0.1")
    assert partial.unprotected_qty == Decimal("0.1")
    unknown = apply_event(partial, _event("unknown", "UNKNOWN_PROTECTION", exchange_ms=105, received_ms=106))
    assert unknown.protected_qty == Decimal("0")
    assert unknown.unprotected_qty == Decimal("0.2")
    exited = apply_event(unknown, _event("exit", "EXIT_FILL", qty="0.2", execution_id="exit-1", exchange_ms=107, received_ms=108))
    assert exited.held_qty == Decimal("0")


@pytest.mark.parametrize(
    ("plan_changes", "event", "target_args"),
    (
        ({"qty_step": 0.1}, None, None),
        ({"requested_qty": "NaN"}, None, None),
        ({"requested_qty": "0.25"}, None, None),
        ({"profile_id": "ATT1_V1"}, None, None),
        ({}, _event("bad-time", "ENTRY_ACK", exchange_ms=99, received_ms=100), None),
        ({}, _event("bool-time", "ENTRY_ACK", exchange_ms=True, received_ms=102), None),
        ({}, None, ("0.3", "0.3", "0.1", "1.1")),
    ),
)
def test_invalid_decimal_profile_and_causal_inputs_fail(plan_changes, event, target_args):
    if target_args is not None:
        with pytest.raises(LifecycleViolation):
            target_close_qty(*target_args)
    elif event is not None:
        with pytest.raises(LifecycleViolation):
            apply_event(initial_state(_plan(**plan_changes)), event)
    else:
        with pytest.raises(LifecycleViolation):
            initial_state(_plan(**plan_changes))


def test_replay_is_deterministic_and_exposes_no_mutable_state_collections():
    plan = _plan()
    events = (
        _event("fill", "ENTRY_FILL", qty="0.1", execution_id="entry-1"),
        _event("final", "ENTRY_FINAL", exchange_ms=103, received_ms=104),
    )
    first = replay(plan, events)
    second = replay(plan, events)
    assert first == second
    with pytest.raises((TypeError, FrozenInstanceError)):
        first.accepted_event_fingerprints["other"] = "mutated"
    with pytest.raises((TypeError, FrozenInstanceError)):
        first.accepted_events += (events[0],)
    assert first.held_qty == Decimal("0.1")
