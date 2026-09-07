from dataclasses import FrozenInstanceError
from decimal import localcontext
from fractions import Fraction

import pytest

from research_lab.att1_ets2s_accounting import (
    AccountingPlan,
    AccountingViolation,
    EntryFinal,
    Execution,
    FundingSchedule,
    FundingSettlement,
    replay_accounting,
)


SHA = "a" * 64
FEE_SHA = "b" * 64
FUNDING_SHA = "c" * 64


def _plan(**changes):
    values = {
        "profile_id": "SYNTHETIC_ATT1_ACCOUNTING_V1",
        "accepted_stop": "110",
        "planned_risk_amount": "10",
        "currency": "USDT",
        "source_sha256": SHA,
    }
    values.update(changes)
    return AccountingPlan(**values)


def _fill(event_id, execution_id, kind, qty, price, *, fee_amount="0", exchange_ms=100, received_ms=101, **changes):
    values = {
        "event_id": event_id,
        "execution_id": execution_id,
        "kind": kind,
        "qty": qty,
        "price": price,
        "fee_amount": fee_amount,
        "fee_currency": "USDT",
        "fee_source_sha256": FEE_SHA,
        "liquidity": "TAKER",
        "exchange_ms": exchange_ms,
        "received_ms": received_ms,
        "source_sha256": SHA,
    }
    values.update(changes)
    return Execution(**values)


def _final(event_id="final", *, exchange_ms=102, received_ms=103, **changes):
    values = {
        "event_id": event_id,
        "exchange_ms": exchange_ms,
        "received_ms": received_ms,
        "source_sha256": SHA,
    }
    values.update(changes)
    return EntryFinal(**values)


def _funding(event_id, settlement_id, settlement_ms, qty, mark, rate, *, received_ms=None, **changes):
    values = {
        "event_id": event_id,
        "settlement_id": settlement_id,
        "settlement_ms": settlement_ms,
        "exchange_ms": settlement_ms,
        "received_ms": settlement_ms + 1 if received_ms is None else received_ms,
        "qty_at_settlement": qty,
        "mark_price": mark,
        "rate": rate,
        "source_sha256": FUNDING_SHA,
    }
    values.update(changes)
    return FundingSettlement(**values)


def _schedule(times=(), *, start_ms=0, end_ms=1_000, complete=True, **changes):
    values = {
        "settlement_ms": tuple(times),
        "start_ms": start_ms,
        "end_ms": end_ms,
        "source_sha256": FUNDING_SHA,
        "complete": complete,
    }
    values.update(changes)
    return FundingSchedule(**values)


def test_closed_short_costs_and_fixed_r0_are_hand_calculated_exactly():
    result = replay_accounting(
        _plan(),
        (
            _fill("entry", "e-1", "ENTRY", "1", "100", fee_amount=".10"),
            _final(),
            _fill("exit", "x-1", "EXIT", "1", "90", fee_amount=".09", exchange_ms=104, received_ms=105),
        ),
        _schedule(),
    )

    assert result.gross_realized == Fraction(10)
    assert result.known_fee_total == Fraction(19, 100)
    assert result.net_realized == Fraction(981, 100)
    assert result.fixed_r0 == Fraction(10)
    assert result.closed_net_r == Fraction(981, 1000)
    assert result.held_qty == Fraction(0)
    assert result.remaining_basis is None


def test_entry_rebate_increases_net_without_changing_gross_or_r0():
    result = replay_accounting(
        _plan(),
        (
            _fill("entry", "e-1", "ENTRY", "1", "100", fee_amount="-.02"),
            _final(),
            _fill("exit", "x-1", "EXIT", "1", "90", exchange_ms=104, received_ms=105),
        ),
        _schedule(),
    )
    assert result.gross_realized == Fraction(10)
    assert result.net_realized == Fraction(501, 50)
    assert result.closed_net_r == Fraction(501, 500)


def test_interleaved_late_entry_never_reprices_prior_realized_cash_and_final_uses_aggregate_vwap():
    result = replay_accounting(
        _plan(accepted_stop="120"),
        (
            _fill("entry-1", "e-1", "ENTRY", "1", "100"),
            _fill("exit-1", "x-1", "EXIT", "1", "90", exchange_ms=102, received_ms=103),
            _fill("entry-2", "e-2", "ENTRY", "1", "110", exchange_ms=104, received_ms=105),
            _final(exchange_ms=106, received_ms=107),
            _fill("exit-2", "x-2", "EXIT", "1", "100", exchange_ms=108, received_ms=109),
        ),
        _schedule(),
    )
    assert result.gross_realized == Fraction(20)
    assert result.aggregate_entry_qty == Fraction(2)
    assert result.aggregate_entry_notional == Fraction(210)
    assert result.fixed_r0 == Fraction(30)
    assert result.closed_net_r == Fraction(2, 3)


def test_weighted_remaining_basis_is_used_only_for_subsequent_exits():
    partial = replay_accounting(
        _plan(),
        (
            _fill("entry-1", "e-1", "ENTRY", "1", "100"),
            _fill("exit-1", "x-1", "EXIT", ".5", "90", exchange_ms=102, received_ms=103),
            _fill("entry-2", "e-2", "ENTRY", "1", "110", exchange_ms=104, received_ms=105),
        ),
        _schedule(),
    )
    assert partial.gross_realized == Fraction(5)
    assert partial.held_qty == Fraction(3, 2)
    assert partial.remaining_basis == Fraction(320, 3)

    result = replay_accounting(
        _plan(),
        (
            _fill("entry-1", "e-1", "ENTRY", "1", "100"),
            _fill("exit-1", "x-1", "EXIT", ".5", "90", exchange_ms=102, received_ms=103),
            _fill("entry-2", "e-2", "ENTRY", "1", "110", exchange_ms=104, received_ms=105),
            _fill("exit-2", "x-2", "EXIT", "1.5", "100", exchange_ms=106, received_ms=107),
        ),
        _schedule(),
    )
    assert result.gross_realized == Fraction(15)
    assert result.held_qty == Fraction(0)
    assert result.remaining_basis is None


def test_finality_then_late_entry_preserves_exposure_freezes_r0_and_blocks_closed_r():
    result = replay_accounting(
        _plan(),
        (
            _fill("entry-1", "e-1", "ENTRY", "1", "100"),
            _final(),
            _fill("late", "e-2", "ENTRY", "1", "110", exchange_ms=104, received_ms=105),
        ),
        _schedule(),
    )
    assert result.held_qty == Fraction(2)
    assert result.remaining_basis == Fraction(105)
    assert result.fixed_r0 == Fraction(10)
    assert "FINAL_ENTRY_DRIFT" in result.issues
    assert result.closed_net_r is None


def test_signed_settled_funding_and_flat_observation_are_exact():
    result = replay_accounting(
        _plan(),
        (
            _fill("entry", "e-1", "ENTRY", "1", "100", exchange_ms=100, received_ms=101),
            _funding("fund-plus", "f-1", 110, "1", "100", ".001"),
            _funding("fund-minus", "f-2", 120, "1", "100", "-.001"),
            _fill("exit", "x-1", "EXIT", "1", "90", exchange_ms=130, received_ms=131),
            _funding("flat", "f-3", 140, "0", "100", ".001"),
        ),
        _schedule((110, 120, 140), start_ms=100, end_ms=140),
    )
    assert result.settled_funding == Fraction(0)
    assert result.net_realized == Fraction(10)
    with pytest.raises(AccountingViolation):
        replay_accounting(_plan(), (_fill("entry", "e-1", "ENTRY", "1", "100"), _funding("bad", "f", 110, "2", "100", ".001")), _schedule((110,)))


def test_distinct_funding_settlements_cannot_double_count_one_scheduled_timestamp():
    with pytest.raises(AccountingViolation):
        replay_accounting(
            _plan(),
            (
                _fill("entry", "e-1", "ENTRY", "1", "100", exchange_ms=100, received_ms=101),
                _final(exchange_ms=102, received_ms=103),
                _funding("fund-1", "s-1", 110, "1", "100", ".001"),
                _funding("fund-2", "s-2", 110, "1", "100", ".001"),
                _fill("exit", "x-1", "EXIT", "1", "90", exchange_ms=120, received_ms=121),
            ),
            _schedule((110,), start_ms=100, end_ms=120),
        )


def test_exact_funding_redelivery_is_a_no_op():
    settlement = _funding("fund-1", "s-1", 110, "1", "100", ".001")
    result = replay_accounting(
        _plan(),
        (
            _fill("entry", "e-1", "ENTRY", "1", "100", exchange_ms=100, received_ms=101),
            settlement,
            settlement,
        ),
        _schedule((110,), start_ms=100, end_ms=110),
    )
    assert result.settled_funding == Fraction(1, 10)


@pytest.mark.parametrize(
    "events,schedule",
    (
        ((_fill("entry", "e", "ENTRY", "1", "100", fee_amount=None),), _schedule()),
        ((_fill("entry", "e", "ENTRY", "1", "100", fee_currency="BTC"),), _schedule()),
        ((_fill("entry", "e", "ENTRY", "1", "100"),), None),
        ((_fill("entry", "e", "ENTRY", "1", "100"),), _schedule(complete=False)),
        ((_fill("entry", "e", "ENTRY", "1", "100"), _funding("extra", "f", 110, "1", "100", ".001")), _schedule(())),
        ((_fill("entry", "e", "ENTRY", "1", "100"), _fill("exit", "x", "EXIT", "1", "90", exchange_ms=120, received_ms=121)), _schedule((110,), end_ms=200)),
        ((_fill("entry", "e", "ENTRY", "1", "100"),), _schedule((), start_ms=101)),
    ),
)
def test_unknown_costs_or_incomplete_funding_never_fabricate_net_values(events, schedule):
    if events[0].fee_currency == "BTC":
        with pytest.raises(AccountingViolation):
            replay_accounting(_plan(), events, schedule)
        return
    result = replay_accounting(_plan(), events, schedule)
    assert result.net_realized is None
    assert result.closed_net_r is None


def test_costs_can_turn_positive_gross_negative_and_open_position_has_no_closed_r():
    closed = replay_accounting(
        _plan(),
        (_fill("entry", "e", "ENTRY", "1", "100", fee_amount="11"), _final(), _fill("exit", "x", "EXIT", "1", "90", exchange_ms=104, received_ms=105)),
        _schedule(),
    )
    assert closed.gross_realized == Fraction(10)
    assert closed.net_realized == Fraction(-1)
    assert closed.closed_net_r == Fraction(-1, 10)

    open_result = replay_accounting(_plan(), (_fill("entry", "e", "ENTRY", "1", "100"),), _schedule(), mark_price="90")
    assert open_result.gross_realized == Fraction(0)
    assert open_result.unrealized == Fraction(10)
    assert open_result.net_equity_change == Fraction(10)
    assert open_result.closed_net_r is None


def test_duplicate_delivery_is_idempotent_conflicts_and_unseen_time_reversal_fail_and_result_is_immutable():
    entry = _fill("entry", "e", "ENTRY", "1", "100")
    result = replay_accounting(_plan(), (entry, entry, _fill("entry-copy", "e", "ENTRY", "1", "100")), _schedule())
    assert result.held_qty == Fraction(1)
    with pytest.raises(AccountingViolation):
        replay_accounting(_plan(), (entry, _fill("entry", "e", "ENTRY", "2", "100", exchange_ms=102, received_ms=103)), _schedule())
    with pytest.raises(AccountingViolation):
        replay_accounting(_plan(), (entry, _fill("later", "x", "EXIT", "1", "90", exchange_ms=110, received_ms=111), _fill("old", "e-2", "ENTRY", "1", "100", exchange_ms=105, received_ms=106)), _schedule())
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.held_qty = Fraction(2)


def test_decimal_boundaries_bool_timestamps_and_low_decimal_context_do_not_change_exact_cash():
    with localcontext() as context:
        context.prec = 1
        result = replay_accounting(_plan(), (_fill("entry", "e", "ENTRY", "1", "100"), _fill("exit", "x", "EXIT", "1", "90", exchange_ms=102, received_ms=103)), _schedule())
    assert result.gross_realized == Fraction(10)
    with pytest.raises(AccountingViolation):
        replay_accounting(_plan(), (_fill("entry", "e", "ENTRY", "1", "NaN"),), _schedule())
    with pytest.raises(AccountingViolation):
        replay_accounting(_plan(), (_fill("entry", "e", "ENTRY", "1", "100", exchange_ms=True),), _schedule())
    with pytest.raises(AccountingViolation):
        replay_accounting(_plan(), (_fill("entry", "e", "ENTRY", "1" * 65, "100"),), _schedule())


def test_no_fill_finalization_has_no_r_and_invalid_hash_or_final_conflict_rejects():
    result = replay_accounting(_plan(), (_final(),), _schedule())
    assert result.fixed_r0 is None
    assert result.closed_net_r is None
    with pytest.raises(AccountingViolation):
        replay_accounting(_plan(source_sha256="A" * 64), (), _schedule())
    with pytest.raises(AccountingViolation):
        replay_accounting(_plan(profile_id="ATT1_REAL_V1"), (), _schedule())
    with pytest.raises(AccountingViolation):
        replay_accounting(_plan(), (_final(), _final("another", exchange_ms=104, received_ms=105)), _schedule())
