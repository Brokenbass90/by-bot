"""Inert ATT1 cash/command preparation. No broker sender or money authority.

Hashes and pure validation establish consistency of declared evidence only.
The trusted GET collector and independent acceptance receipts establish its
provenance; neither this module nor a binding can authorize an order.
"""
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import re

from bot.att1_coordinator_adapter import AdapterViolation, _number
from research_lab.att1_lifecycle_coordinator import digest
from research_lab.att1_lifecycle_profile import _decimal_text

DAY_MS = 86_400_000
MAX_EVIDENCE_AGE_MS = 60_000
BASE_PROFILE_SHA = '79d23e38a6bb851fb7e300c2e0d0c22b48b671585d4c060eb5384c192b128050'
_SHA = re.compile(r'[0-9a-f]{64}\Z')


def _mapping(value, fields, name):
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise AdapterViolation('invalid ' + name + ' fields')
    return dict(value)


def _sha(value, name):
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise AdapterViolation('invalid ' + name + ' hash')
    return value


def _clock(value, now, name):
    if type(value) is not int or not 0 < value <= now or now - value > MAX_EVIDENCE_AGE_MS:
        raise AdapterViolation('stale/invalid ' + name + ' clock')


def _day(now):
    try:
        return datetime.fromtimestamp(now // 1000, timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError) as exc:
        raise AdapterViolation('invalid UTC clock') from exc


def validate_canary_budget_inputs(binding: Mapping, old_budget_evidence: Mapping,
                                 cash_evidence: Mapping, *, now_ms: int) -> dict:
    """Validate declared source-bound inputs; no claim of authentication."""
    if type(now_ms) is not int or now_ms <= 0:
        raise AdapterViolation('invalid budget clock')
    b = _mapping(binding, {
        'base_profile_sha256', 'account_fingerprint_sha256', 'broker_truth_sha256',
        'account_mode', 'observed_ms', 'absolute_risk_cap', 'old_budget_ceiling',
        'max_notional', 'daily_loss_cap', 'max_concurrent_positions', 'send_enabled',
    }, 'binding')
    for key in ('base_profile_sha256', 'account_fingerprint_sha256', 'broker_truth_sha256'):
        _sha(b[key], key)
    _clock(b['observed_ms'], now_ms, 'binding')
    r = _number(b['absolute_risk_cap'], 'risk', positive=True)
    old_cap = _number(b['old_budget_ceiling'], 'OLD ceiling', positive=True)
    n = _number(b['max_notional'], 'notional', positive=True)
    daily = _number(b['daily_loss_cap'], 'daily cap', positive=True)
    if (b['base_profile_sha256'] != BASE_PROFILE_SHA or r > old_cap or n > 100
            or daily != 2 * r or b['account_mode'] != 'UNIFIED_ONE_WAY_USDT'
            or type(b['max_concurrent_positions']) is not int or b['max_concurrent_positions'] != 1
            or b['send_enabled'] is not False):
        raise AdapterViolation('unsafe inert binding')
    o = _mapping(old_budget_evidence, {
        'schema_id', 'account_fingerprint_sha256', 'broker_truth_sha256', 'observed_ms',
        'sizing_source_sha256', 'config_sha256', 'raw_source_sha256',
        'effective_equity_usdt', 'risk_per_trade_pct', 'att1_risk_mult',
        'breaker_risk_mult', 'voladj_mult', 'breaker_blocked',
        'cap_notional_to_equity', 'leverage', 'reserve_equity_frac', 'max_positions',
        'taker_fee_rate', 'fee_source_sha256', 'funding_cost_reserve_rate', 'funding_source_sha256',
    }, 'OLD budget')
    if (o['schema_id'] != 'att1_canary_old_budget_v1'
            or o['account_fingerprint_sha256'] != b['account_fingerprint_sha256']
            or o['broker_truth_sha256'] != b['broker_truth_sha256']
            or o['observed_ms'] != b['observed_ms'] or o['breaker_blocked'] is not False):
        raise AdapterViolation('OLD risk input identity/availability mismatch')
    _clock(o['observed_ms'], now_ms, 'OLD')
    for key in ('sizing_source_sha256', 'config_sha256', 'raw_source_sha256', 'fee_source_sha256', 'funding_source_sha256'):
        _sha(o[key], key)
    eq = _number(o['effective_equity_usdt'], 'equity', positive=True)
    pct = _number(o['risk_per_trade_pct'], 'risk pct', positive=True)
    mult = _number(o['att1_risk_mult'], 'ATT1 multiplier', positive=True)
    breaker = _number(o['breaker_risk_mult'], 'breaker', positive=True)
    vol = _number(o['voladj_mult'], 'volatility', positive=True)
    # Matches the deployed legacy cash-risk calculation. The .1 clamp is not
    # permission to bypass a blocked breaker or non-positive strategy size.
    computed_cap = eq * pct / 100 * max(Fraction('0.1'), mult * breaker) * vol
    leverage = _number(o['leverage'], 'leverage', positive=True)
    reserve = _number(o['reserve_equity_frac'], 'equity reserve', nonnegative=True)
    slots = o['max_positions']
    if (type(o['cap_notional_to_equity']) is not bool or type(slots) is not int
            or slots < 0 or reserve >= 1 or pct > 100 or computed_cap != old_cap):
        raise AdapterViolation('OLD risk input calculation mismatch')
    notional_cap = eq * (1 if o['cap_notional_to_equity'] else leverage) * (1 - reserve)
    if slots > 1:
        notional_cap /= slots
    if n > notional_cap:
        raise AdapterViolation('OLD notional ceiling exceeded')
    for key in ('taker_fee_rate', 'funding_cost_reserve_rate'):
        rate = _number(o[key], key, nonnegative=True)
        if rate >= 1:
            raise AdapterViolation('invalid cost reserve rate')
    c = _mapping(cash_evidence, {
        'schema_id', 'account_fingerprint_sha256', 'observed_ms', 'coverage_start_ms',
        'coverage_end_ms', 'owners', 'complete', 'unresolved_prior_day_costs', 'source_sha256', 'events',
    }, 'cash coverage')
    _clock(c['observed_ms'], now_ms, 'cash')
    _sha(c['source_sha256'], 'cash source')
    start = now_ms // DAY_MS * DAY_MS
    if (c['schema_id'] != 'att1_canary_cash_coverage_v1'
            or c['account_fingerprint_sha256'] != b['account_fingerprint_sha256']
            or c['complete'] is not True or c['unresolved_prior_day_costs'] is not False
            or not isinstance(c['owners'], list) or sorted(c['owners']) != ['NEW', 'OLD']
            or type(c['coverage_start_ms']) is not int or c['coverage_start_ms'] != start
            or type(c['coverage_end_ms']) is not int or c['coverage_end_ms'] != c['observed_ms']
            or not start <= c['coverage_end_ms'] <= now_ms or not isinstance(c['events'], list)):
        raise AdapterViolation('cash coverage incomplete')
    seen, spent, normalized = {}, Fraction(0), []
    for value in c['events']:
        row = _mapping(value, {
            'source_id', 'source_sha256', 'account_fingerprint_sha256', 'owner',
            'economic_ms', 'received_ms', 'gross_realized_usdt', 'execution_fee_usdt', 'funding_cash_usdt',
        }, 'cash event')
        sid = row['source_id']
        if not isinstance(sid, str) or not 1 <= len(sid) <= 256:
            raise AdapterViolation('cash event identity missing')
        _sha(row['source_sha256'], 'cash event')
        ex, rx = row['economic_ms'], row['received_ms']
        if (row['owner'] not in {'OLD', 'NEW'} or row['account_fingerprint_sha256'] != b['account_fingerprint_sha256']
                or type(ex) is not int or type(rx) is not int or not start <= ex <= rx <= c['observed_ms']):
            raise AdapterViolation('cash event outside complete coverage')
        economic = {k: v for k, v in row.items() if k != 'received_ms'}
        if sid in seen:
            if seen[sid] != economic:
                raise AdapterViolation('conflicting cash event identity')
            continue
        seen[sid] = economic
        gross = _number(row['gross_realized_usdt'], 'gross realized')
        fee = _number(row['execution_fee_usdt'], 'execution fee', nonnegative=True)
        funding = _number(row['funding_cash_usdt'], 'funding cash')
        spent += max(-gross, 0) + fee + max(-funding, 0)
        normalized.append(row)
    c['events'] = normalized
    out = {'schema_id': 'att1_canary_validated_budget_v1', 'binding': deepcopy(b),
           'old_budget_evidence': deepcopy(o), 'cash_evidence': deepcopy(c),
           'now_ms': now_ms, 'day_utc': _day(now_ms), 'spent_usdt': _decimal_text(spent),
           'binding_sha256': digest(b), 'cash_coverage_sha256': digest(c),
           'source_ids': sorted(seen), 'orders_allowed': False}
    out['validation_sha256'] = digest(out)
    return out


def _revalidate(validated):
    if not isinstance(validated, Mapping):
        raise AdapterViolation('validated budget required')
    try:
        value = validate_canary_budget_inputs(validated['binding'], validated['old_budget_evidence'],
                                              validated['cash_evidence'], now_ms=validated['now_ms'])
    except KeyError as exc:
        raise AdapterViolation('validated budget malformed') from exc
    if value != validated:
        raise AdapterViolation('validated budget projection/provenance changed')
    return value


def project_att1_daily_budget(validated: Mapping, occupied: list[Mapping], *,
                             proposed_risk_usdt: str, proposed_cost_reserve_usdt: str) -> dict:
    v = _revalidate(validated)
    if not isinstance(occupied, list):
        raise AdapterViolation('occupied reservation inventory required')
    risk = _number(proposed_risk_usdt, 'proposed risk', nonnegative=True)
    costs = _number(proposed_cost_reserve_usdt, 'proposed costs', nonnegative=True)
    spent = _number(v['spent_usdt'], 'spent', nonnegative=True)
    reserved, unknown = Fraction(0), False
    for row in occupied:
        if not isinstance(row, Mapping):
            raise AdapterViolation('invalid occupied reservation')
        if row.get('risk_reserve_usdt') is None or row.get('cost_reserve_usdt') is None:
            unknown = True
            continue
        reserved += _number(row['risk_reserve_usdt'], 'occupied risk', nonnegative=True)
        reserved += _number(row['cost_reserve_usdt'], 'occupied costs', nonnegative=True)
    remaining = _number(v['binding']['daily_loss_cap'], 'daily cap') - spent - reserved
    reason = ('UNKNOWN_OCCUPIED_RISK' if unknown else
              'ABSOLUTE_RISK_CAP_EXCEEDED' if risk > _number(v['binding']['absolute_risk_cap'], 'risk cap') else
              'DAILY_BUDGET_EXCEEDED' if risk + costs > remaining else 'ADMITTED_ORDERS_OFF')
    out = {'admitted': reason == 'ADMITTED_ORDERS_OFF', 'reason': reason,
           'day_utc': v['day_utc'], 'spent_usdt': _decimal_text(spent),
           'reserved_usdt': _decimal_text(reserved), 'remaining_usdt': _decimal_text(remaining),
           'binding_sha256': v['binding_sha256'], 'budget_evidence_sha256': v['validation_sha256'],
           'orders_allowed': False}
    out['projection_sha256'] = digest(out)
    return out
