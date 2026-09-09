from copy import deepcopy
from fractions import Fraction

import pytest

from research_lab.att1_ets2s_accounting import (
    AccountingPlan, AccountingViolation, EntryFinal, Execution, FundingCashSettlement,
    FundingSchedule, FundingSettlement, replay_accounting,
)
from research_lab.att1_lifecycle_coordinator import replay_lifecycle
from research_lab.att1_lifecycle_profile import bind_broker_replay_profile
from test_att1_broker_replay_binding import bound, execution, mapped
from test_att1_lifecycle_coordinator import ev


SHA = 'a' * 64


def broker_plan():
    return AccountingPlan('BROKER_REPLAY_ATT1_V1', '110', '1', 'USDT', SHA)


def cash(amount, *, qty='0.05', settlement_ms=20_000, received_ms=50_000, event_id='cash'):
    return FundingCashSettlement(event_id, 'funding-1', settlement_ms, settlement_ms, received_ms,
                                 qty, amount, 'USDT', SHA)


def replay(amount='-0.00049999', *, settlement_ms=20_000, schedule=True, qty='0.05'):
    events = [
        Execution('entry', 'fill-1', 'ENTRY', '0.05', '100', '0', 'USDT', SHA, 'TAKER', 10_000, 10_000, SHA),
        EntryFinal('entry-final', 11_000, 11_000, SHA),
        Execution('exit', 'fill-2', 'EXIT', '0.05', '112', '0', 'USDT', SHA, 'TAKER', 30_000, 30_000, SHA),
        cash(amount, qty=qty, settlement_ms=settlement_ms),
    ]
    coverage = FundingSchedule((settlement_ms,), 10_000, 30_000, SHA, True) if schedule else None
    return replay_accounting(broker_plan(), events, coverage, reconcile_delayed_funding=True)


def test_signed_broker_cash_debit_and_credit_are_exact():
    debit = replay()
    credit = replay('0.00049999')
    assert debit.settled_funding == Fraction('-0.00049999')
    assert credit.settled_funding == Fraction('0.00049999')
    assert debit.closed_net_r == (Fraction('-0.6') + Fraction('-0.00049999')) / Fraction('0.5')


def test_broker_cash_rejects_zero_quantity_with_nonzero_cash_and_wrong_delayed_qty():
    with pytest.raises(AccountingViolation, match='zero funding quantity'):
        replay('0.1', qty='0')
    with pytest.raises(AccountingViolation, match='historical held qty'):
        replay(qty='0.04')


def test_broker_cash_missing_coverage_or_boundary_ambiguity_keeps_net_r_null():
    assert replay(schedule=False).closed_net_r is None
    boundary = replay(settlement_ms=12_000)
    assert 'FUNDING_BOUNDARY_AMBIGUOUS' in boundary.issues
    assert boundary.closed_net_r is None


def test_broker_cash_duplicate_changed_amount_and_profile_mixes_reject():
    initial = cash('0.1')
    changed = FundingCashSettlement('cash-redelivery', initial.settlement_id, initial.settlement_ms,
                                    initial.exchange_ms, initial.received_ms + 1, initial.qty_at_settlement,
                                    '0.2', initial.currency, initial.source_sha256)
    with pytest.raises(AccountingViolation, match='conflicting settlement_id'):
        replay_accounting(broker_plan(), [initial, changed], FundingSchedule((20_000,), 0, 20_000, SHA, True),
                          reconcile_delayed_funding=True)
    synthetic = AccountingPlan('SYNTHETIC_TEST', '110', '1', 'USDT', SHA)
    with pytest.raises(AccountingViolation, match='broker funding cash'):
        replay_accounting(synthetic, [cash('0')], FundingSchedule((20_000,), 0, 20_000, SHA, True))
    with pytest.raises(AccountingViolation, match='synthetic funding'):
        replay_accounting(broker_plan(), [FundingSettlement('funding', 'f', 20_000, 20_000, 20_000, '0', '100', '0', SHA)],
                          FundingSchedule((20_000,), 0, 20_000, SHA, True))


def test_broker_entry_fill_records_absolute_risk_and_notional_cap_incidents():
    _, profile, intent = bound()
    over_risk = replay_lifecycle(profile, intent, [ev('ENTRY_ACK', 31), mapped(execution(execPrice='88'))])
    assert 'ABSOLUTE_RISK_CAP_EXCEEDED' in over_risk['incidents']

    base, profile, intent = bound()
    binding = deepcopy(profile['broker_binding'])
    binding['max_notional'] = '5.1'
    constrained = bind_broker_replay_profile(base, binding)
    over_notional = replay_lifecycle(constrained, intent, [ev('ENTRY_ACK', 31), mapped(execution(execQty='0.04', execPrice='200'))])
    assert 'NOTIONAL_CAP_EXCEEDED' in over_notional['incidents']
