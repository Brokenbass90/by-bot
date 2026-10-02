"""Cash admission contract. All account/evidence values here are synthetic."""
from copy import deepcopy
import importlib
import importlib.util

import pytest

from bot.att1_coordinator_adapter import AdapterViolation

T = 500_000 * 3_600_000
DAY = T // 86_400_000 * 86_400_000
SHA = 'a' * 64
ACCOUNT_SHA = 'd' * 64


def api():
    # RED is an assertion about the missing component, rather than an import typo.
    assert importlib.util.find_spec('bot.att1_canary_preparation') is not None
    return importlib.import_module('bot.att1_canary_preparation')


def inputs():
    binding = {
        'base_profile_sha256': '79d23e38a6bb851fb7e300c2e0d0c22b48b671585d4c060eb5384c192b128050',
        'account_fingerprint_sha256': ACCOUNT_SHA, 'broker_truth_sha256': 'e' * 64,
        'account_mode': 'UNIFIED_ONE_WAY_USDT', 'observed_ms': T + 20,
        'absolute_risk_cap': '0.50', 'old_budget_ceiling': '0.50',
        'max_notional': '50', 'daily_loss_cap': '1.00',
        'max_concurrent_positions': 1, 'send_enabled': False,
    }
    old = {
        'schema_id': 'att1_canary_old_budget_v1',
        'account_fingerprint_sha256': ACCOUNT_SHA, 'broker_truth_sha256': 'e' * 64,
        'observed_ms': T + 20, 'sizing_source_sha256': SHA, 'config_sha256': 'b' * 64,
        'raw_source_sha256': 'c' * 64, 'effective_equity_usdt': '100',
        'risk_per_trade_pct': '1', 'att1_risk_mult': '0.5',
        'breaker_risk_mult': '1', 'voladj_mult': '1', 'breaker_blocked': False,
        'cap_notional_to_equity': True, 'leverage': '1',
        'reserve_equity_frac': '0', 'max_positions': 1,
        'taker_fee_rate': '0.001', 'fee_source_sha256': 'f' * 64,
        'funding_cost_reserve_rate': '0.002', 'funding_source_sha256': '1' * 64,
    }
    cash = {
        'schema_id': 'att1_canary_cash_coverage_v1', 'account_fingerprint_sha256': ACCOUNT_SHA,
        'observed_ms': T + 40, 'coverage_start_ms': DAY, 'coverage_end_ms': T + 40,
        'owners': ['OLD', 'NEW'], 'complete': True, 'unresolved_prior_day_costs': False,
        'source_sha256': '2' * 64, 'events': [],
    }
    return binding, old, cash


def validated(**cash_changes):
    b, o, c = inputs()
    c.update(cash_changes)
    return api().validate_canary_budget_inputs(b, o, c, now_ms=T + 40)


def cash_event(**changes):
    row = {
        'source_id': 'old-fill-1', 'source_sha256': '3' * 64,
        'account_fingerprint_sha256': ACCOUNT_SHA, 'owner': 'OLD',
        'economic_ms': T + 5, 'received_ms': T + 30,
        'gross_realized_usdt': '-0.20', 'execution_fee_usdt': '0.10',
        'funding_cash_usdt': '0',
    }
    row.update(changes)
    return row


def project(v, occupied=None, *, risk='0', costs='0'):
    return api().project_att1_daily_budget(
        v, occupied or [], proposed_risk_usdt=risk, proposed_cost_reserve_usdt=costs)


def test_missing_old_cash_coverage_blocks():
    b, o, c = inputs()
    c['owners'] = ['NEW']
    with pytest.raises(AdapterViolation, match='coverage'):
        api().validate_canary_budget_inputs(b, o, c, now_ms=T + 40)


def test_duplicate_or_net_plus_fee_cash_cannot_double_count():
    row = cash_event()
    result = project(validated(events=[row, deepcopy(row)]))
    assert result['spent_usdt'] == '0.3'
    conflict = {**row, 'execution_fee_usdt': '0.11'}
    with pytest.raises(AdapterViolation, match='conflicting'):
        validated(events=[row, conflict])
    with pytest.raises(AdapterViolation, match='cash event'):
        validated(events=[{**row, 'net_pnl_usdt': '-0.30'}])


def test_profit_does_not_refill_daily_budget():
    result = project(validated(events=[cash_event(), cash_event(
        source_id='new-profitable-exit', owner='NEW', gross_realized_usdt='10',
        execution_fee_usdt='0.05', funding_cash_usdt='2')]), risk='0.5', costs='0.2')
    assert result['spent_usdt'] == '0.35'
    assert result['admitted'] is False
    assert result['reason'] == 'DAILY_BUDGET_EXCEEDED'


def test_existing_risk_and_cost_reserve_consume_cash_budget():
    occupied = [{'risk_reserve_usdt': '0.55', 'cost_reserve_usdt': '0.05'}]
    result = project(validated(events=[cash_event()]), occupied, risk='0.20')
    assert result['spent_usdt'] == '0.3'
    assert result['reserved_usdt'] == '0.6'
    assert result['remaining_usdt'] == '0.1'
    assert result['admitted'] is False


def test_midnight_carries_occupied_risk():
    b, o, c = inputs()
    tomorrow = DAY + 86_400_000 + 40
    b['observed_ms'] = o['observed_ms'] = c['observed_ms'] = tomorrow
    c['coverage_start_ms'] = DAY + 86_400_000
    c['coverage_end_ms'] = tomorrow
    v = api().validate_canary_budget_inputs(b, o, c, now_ms=tomorrow)
    result = project(v, [{'risk_reserve_usdt': '0.5', 'cost_reserve_usdt': '0.1'}], risk='0.5')
    assert result['reserved_usdt'] == '0.6'
    assert result['admitted'] is False


def test_late_cost_invalidates_incomplete_coverage():
    with pytest.raises(AdapterViolation, match='coverage'):
        validated(events=[cash_event(received_ms=T + 41)])
    with pytest.raises(AdapterViolation, match='coverage'):
        validated(unresolved_prior_day_costs=True)


@pytest.mark.parametrize('section,field,value', [
    ('old', 'observed_ms', T - 60_001), ('old', 'account_fingerprint_sha256', '9' * 64),
    ('old', 'voladj_mult', None), ('old', 'breaker_blocked', True),
    ('binding', 'send_enabled', True), ('binding', 'old_budget_ceiling', '0.51'),
    ('cash', 'complete', False), ('cash', 'coverage_start_ms', DAY + 1),
])
def test_stale_or_changed_account_and_sizing_inputs_block(section, field, value):
    b, o, c = inputs()
    {'binding': b, 'old': o, 'cash': c}[section][field] = value
    with pytest.raises(AdapterViolation):
        api().validate_canary_budget_inputs(b, o, c, now_ms=T + 40)


def test_fixed_risk_does_not_grow_with_equity():
    b, o, c = inputs()
    o['effective_equity_usdt'] = '200'
    b['old_budget_ceiling'] = '1'
    v = api().validate_canary_budget_inputs(b, o, c, now_ms=T + 40)
    assert v['binding']['absolute_risk_cap'] == '0.50'
    assert project(v, risk='0.51')['reason'] == 'ABSOLUTE_RISK_CAP_EXCEEDED'


def test_unknown_occupied_reserve_blocks_instead_of_releasing_slot():
    r = project(validated(), [{'risk_reserve_usdt': None, 'cost_reserve_usdt': '0'}], risk='0.1')
    assert r['admitted'] is False
    assert r['reason'] == 'UNKNOWN_OCCUPIED_RISK'
