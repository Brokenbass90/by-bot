"""Source capture only: late fee creation, completeness and no financial authority."""
import copy
import json
import time

import pytest

from research_lab import alpaca_fee_to_live_closure_v1 as source


def feed(pages, *, fault=None):
    calls = []
    account = dict(id='fixture-account', cash='100.00', currency='USD', accrued_fees='0', pending_reg_taf_fees='0')
    pages = iter(pages)
    account_reads = 0

    def get(route, params):
        nonlocal account_reads
        calls.append((route, copy.deepcopy(params)))
        if route == '/v2/account':
            account_reads += 1
            row = copy.deepcopy(account)
            if fault == 'cash_changed' and account_reads == 2:
                row['cash'] = '99.99'
            if fault == 'wrong_account':
                row['id'] = 'foreign-account'
            if fault == 'missing_liability':
                row.pop('pending_reg_taf_fees')
            if fault == 'nonfinite':
                row['accrued_fees'] = 'NaN'
        else:
            assert route == '/v2/account/activities'
            row = next(pages)
            if fault == 'lost_response':
                raise TimeoutError('fixture lost GET response')
        stamp = 1790985600100 + (len(calls) - 1) * 20
        return dict(http_status=500 if fault == 'http_error' else 200,
                    started_ms=stamp, received_ms=stamp + 10,
                    raw=json.dumps(row))
    return get, calls


def collect(get, **overrides):
    args = dict(account_id='fixture-account', after='2026-10-01T00:00:00Z',
                until='2026-10-03T00:00:00Z', now_ms=1790985601000,
                page_size=1, max_pages=4)
    return source.collect_account_cost_source(get, **{**args, **overrides})


def test_creation_time_query_keeps_fee_with_earlier_trade_date():
    fill = dict(id='fill-1', activity_type='FILL', transaction_time='2026-10-01T14:00:00Z')
    fee = dict(id='fee-1', activity_type='FEE', date='2026-10-01',
               created_at='2026-10-02T00:16:00Z', net_amount='-0.01')
    get, calls = feed([[fill], [fee], []])
    result = collect(get)
    assert result['activities'] == [fill, fee]
    assert result['coverage']['pagination_exhausted'] is True
    assert result['coverage']['page_count'] == 3
    activity_calls = [params for route, params in calls if route.endswith('/activities')]
    assert all('date' not in params for params in activity_calls)
    assert activity_calls[1]['page_token'] == 'fill-1'
    assert activity_calls[2]['page_token'] == 'fee-1'
    assert result['terminal_cost_finality_proven'] is False
    assert result['orders_allowed'] is result['money_authority'] is False
    assert len(result['captures']) == 5


def test_empty_activities_and_zero_pending_never_prove_zero_cost():
    get, _ = feed([[]])
    result = collect(get)
    assert result['activities'] == []
    assert result['terminal_cost_finality_proven'] is False
    assert 'commission_usd' not in result and 'regulatory_fees_usd' not in result


@pytest.mark.parametrize('fault,reason', [
    ('wrong_account', 'COST_SOURCE_ACCOUNT_CONFLICT'),
    ('cash_changed', 'COST_SOURCE_ACCOUNT_MOVED'),
    ('missing_liability', 'COST_SOURCE_ACCOUNT_FIELDS_REQUIRED'),
    ('nonfinite', 'COST_SOURCE_ACCOUNT_NUMBER'),
    ('http_error', 'COST_SOURCE_GET_FAILED'),
])
def test_uncertain_account_or_transport_cannot_return_complete_source(fault, reason):
    get, _ = feed([[]], fault=fault)
    with pytest.raises(ValueError, match=reason):
        collect(get)


def test_full_page_at_bound_is_not_exhausted_coverage():
    get, _ = feed([[dict(id='a', activity_type='FILL')]])
    with pytest.raises(ValueError, match='COST_SOURCE_PAGE_BOUND'):
        collect(get, max_pages=1)


def test_repeated_activity_id_cannot_double_count_a_fee():
    row = dict(id='a', activity_type='FEE', net_amount='-0.01')
    get, _ = feed([[row], [row]])
    with pytest.raises(ValueError, match='COST_SOURCE_DUPLICATE_ACTIVITY'):
        collect(get)


def test_lost_get_response_has_no_partial_success_and_replay_is_deterministic():
    get, _ = feed([[]], fault='lost_response')
    with pytest.raises(ValueError, match='COST_SOURCE_GET_EXCEPTION') as failure:
        collect(get)
    assert len(failure.value.captures) == 1
    assert failure.value.request['route'] == '/v2/account/activities'
    first, _ = feed([[]]); second, _ = feed([[]])
    assert collect(first) == collect(second)


@pytest.mark.parametrize('change', [dict(page_size=101), dict(max_pages=0),
                                   dict(until='2026-09-01T00:00:00Z'),
                                   dict(until='2026-10-04T00:00:00Z'),
                                   dict(after='2026-10-01T00:00:00')])
def test_bad_coverage_or_bounds_fail_before_get(change):
    get, calls = feed([[]])
    with pytest.raises(ValueError, match='COST_SOURCE_'):
        collect(get, **change)
    assert calls == []


def test_raw_hash_conflict_and_future_capture_are_rejected():
    get, _ = feed([[]])
    def corrupt(route, params):
        row = get(route, params); row['sha256'] = '0' * 64
        return row
    with pytest.raises(ValueError, match='COST_SOURCE_RAW_PIN'):
        collect(corrupt)
    def future(route, params):
        row = get(route, params); row['received_ms'] = 1790985601001
        return row
    with pytest.raises(ValueError, match='COST_SOURCE_CAPTURE_TIME'):
        collect(future)


def test_live_get_latency_uses_completion_clock_instead_of_frozen_start(monkeypatch):
    current = [1790985600000]
    monkeypatch.setattr(time, 'time_ns', lambda: current[0] * 1_000_000)
    reader, _ = feed([[]])
    def delayed(route, params):
        row = reader(route, params); row['started_ms'] = current[0]
        current[0] += 5; row['received_ms'] = current[0]
        return row
    result = collect(delayed, now_ms=None)
    assert result['observed_ms'] == 1790985600015
    assert result['captures'][-1]['received_ms'] == result['observed_ms']


@pytest.mark.parametrize('fault,reason', [('stale', 'COST_SOURCE_CAPTURE_TIME'),
                                        ('out_of_order', 'COST_SOURCE_CAPTURE_ORDER')])
def test_capture_must_cover_cutoff_in_sequential_request_order(fault, reason):
    get, _ = feed([[]]); calls = []
    def broken(route, params):
        row = get(route, params); calls.append(row)
        if fault == 'stale':
            row['started_ms'] = 100; row['received_ms'] = 110
        elif len(calls) == 2:
            row['started_ms'] = 1790985600105
        return row
    with pytest.raises(ValueError, match=reason) as failure:
        collect(broken)
    assert failure.value.captures[-1]['raw'] == calls[-1]['raw']


def test_failed_http_body_and_prior_capture_are_preserved_for_recovery():
    reader, _ = feed([[]])
    def failed(route, params):
        row = reader(route, params)
        if route.endswith('/activities'):
            row['http_status'] = 503; row['raw'] = '{"message":"fixture unavailable"}'
        return row
    with pytest.raises(ValueError, match='COST_SOURCE_GET_FAILED') as failure:
        collect(failed)
    captures = failure.value.captures
    assert len(captures) == 2
    assert captures[0]['route'] == '/v2/account'
    assert captures[1]['http_status'] == 503
    assert captures[1]['raw'] == '{"message":"fixture unavailable"}'


@pytest.fixture
def fee_day():
    from datetime import datetime
    ms = lambda s: int(datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() * 1000)
    trades = [dict(id='f1', activity_type='FILL', order_id='buy', symbol='AAA', side='buy', qty='.5', price='10', transaction_time='2026-10-01T14:00:00Z'),
              dict(id='f2', activity_type='FILL', order_id='buy', symbol='AAA', side='buy', qty='1', price='10', transaction_time='2026-10-01T14:01:00Z'),
              dict(id='f3', activity_type='FILL', order_id='sell', symbol='BBB', side='sell', qty='.5', price='20', transaction_time='2026-10-01T14:02:00Z')]
    fees = [dict(id='c', activity_type='FEE', activity_sub_type='CAT', date='2026-10-01', created_at='2026-10-02T00:16:00Z', status='executed', currency='USD', net_amount='-0.01'),
            dict(id='r', activity_type='FEE', activity_sub_type='REG', date='2026-10-01', created_at='2026-10-02T00:23:00Z', status='executed', currency='USD', net_amount='-0.01')]
    protocol = dict(schema='ALPACA_PROTOCOL_SOURCE_CONTRACT_V1', account_id='fixture-account', commission_rate='0', owner_attestation={'api_commission_null_is_not_proof': True},
                    regulatory_model=dict(cat_nms_executed_share_rate='0.000003', sec_sell_value_rate='0.0000206', taf_per_share_rate='0',
                                          rounding='each fee type aggregated daily per account then ceiling to USD0.01; exact fractional executed quantities'))
    calendar = [dict(session='2026-10-01', open_ms=ms('2026-10-01T13:30:00Z'), close_ms=ms('2026-10-01T20:00:00Z'))]
    return trades, fees, protocol, calendar


def day_check(fee_day, *, rows=None, source_change=None, protocol_change=None, calendar_change=None,
              assets_change=None, collect_change=None):
    trades, fees, protocol, calendar = copy.deepcopy(fee_day)
    if protocol_change: protocol_change(protocol)
    if calendar_change: calendar_change(calendar)
    get, _ = feed([trades + fees if rows is None else rows])
    captured = collect(get, page_size=100, **(collect_change or {}))
    if source_change: source_change(captured)
    assets = [dict(id=s, symbol=s, asset_class='us_equity', exchange='NASDAQ') for s in ('AAA', 'BBB')]
    if assets_change: assets_change(assets)
    return source.reconcile_account_day_fees(captured, protocol=protocol,
        protocol_sha256=source.digest(protocol), calendar=calendar, calendar_sha256=source.digest(calendar),
        assets=assets, assets_sha256=source.digest(assets))


def test_account_day_fees_aggregate_partial_fills_and_multiple_symbols(fee_day):
    result = day_check(fee_day)
    assert result['status'] == 'ACCOUNT_DAY_FEE_SOURCE_PASS'
    assert result['regulatory_fees_usd'] == '0.02'
    assert result['days'][0]['fill_count'] == 3
    assert result['days'][0]['fee_activity_count'] == 2
    assert result['days'][0]['posted'] == {'CAT': '0.01', 'SEC': '0.01'}
    assert result['cash_reconciled'] is result['position_cost_allocation_produced'] is False
    assert result['capital_released'] is result['money_authority'] is False


def test_missing_posted_fee_remains_pending_despite_zero_account_liabilities(fee_day):
    trades, fees, _, _ = fee_day
    with pytest.raises(ValueError, match='COST_FEE_POSTING_PENDING_OR_CONFLICT'):
        day_check(fee_day, rows=trades + fees[:1])
    assert day_check(fee_day)['status'] == 'ACCOUNT_DAY_FEE_SOURCE_PASS'


@pytest.mark.parametrize('fault', ['too_much', 'unexecuted', 'wrong_currency', 'intraday', 'unknown_type'])
def test_unresolved_fee_semantics_fail_closed(fee_day, fault):
    trades, fees, _, _ = copy.deepcopy(fee_day)
    if fault == 'too_much': fees[0]['net_amount'] = '-0.02'
    if fault == 'unexecuted': fees[0]['status'] = 'pending'
    if fault == 'wrong_currency': fees[0]['currency'] = 'EUR'
    if fault == 'intraday': fees[0]['created_at'] = '2026-10-01T15:00:00Z'
    if fault == 'unknown_type': fees[0]['activity_sub_type'] = 'UNKNOWN'
    with pytest.raises(ValueError, match='COST_FEE_'):
        day_check(fee_day, rows=trades + fees)


def test_detached_activity_mutation_cannot_attest_fees(fee_day):
    with pytest.raises(ValueError, match='COST_FEE_SOURCE_DRIFT'):
        day_check(fee_day, source_change=lambda s: s['activities'][0].update(qty='2'))


@pytest.mark.parametrize('fault', ['account', 'commission', 'taf', 'calendar'])
def test_unsupported_protocol_or_uncovered_session_cannot_close(fee_day, fault):
    protocol_change = None; calendar_change = None
    if fault == 'account': protocol_change = lambda p: p.update(account_id='foreign')
    if fault == 'commission': protocol_change = lambda p: p.update(commission_rate='.01')
    if fault == 'taf': protocol_change = lambda p: p['regulatory_model'].update(taf_per_share_rate='.001')
    if fault == 'calendar': calendar_change = lambda c: c.clear()
    with pytest.raises(ValueError, match='COST_FEE_'):
        day_check(fee_day, protocol_change=protocol_change, calendar_change=calendar_change)


def test_day_finality_does_not_require_one_fee_row_per_fill(fee_day):
    trades, fees, _, _ = copy.deepcopy(fee_day)
    fees[0]['net_amount'] = '-0.005'
    fees.append({**fees[0], 'id': 'c2'})
    assert day_check(fee_day, rows=trades + fees)['regulatory_fees_usd'] == '0.020'


def test_post_close_query_cannot_attest_whole_account_day(fee_day):
    trades, fees, _, _ = copy.deepcopy(fee_day)
    for row in fees:
        row['created_at'] = '2026-10-01T20:05:00Z'
    with pytest.raises(ValueError, match='COST_FEE_DAY_COVERAGE_OR_SESSION_NOT_CLOSED'):
        day_check(fee_day, rows=trades + fees, collect_change={'until': '2026-10-01T20:10:00Z'})


@pytest.mark.parametrize('fault', ['crypto', 'currency', 'unknown_symbol', 'asset_class', 'exchange', 'missing_asset', 'conflicting_class', 'asset_id'])
def test_equity_fee_model_rejects_unsupported_or_unproven_instruments(fee_day, fault):
    trades, fees, _, _ = copy.deepcopy(fee_day)
    assets_change = None
    if fault == 'crypto': trades[0].update(asset_class='crypto', symbol='BTC/USD')
    if fault == 'currency': trades[0]['currency'] = 'EUR'
    if fault == 'unknown_symbol': trades[0]['symbol'] = 'UNPROVEN'
    if fault == 'asset_class': assets_change = lambda a: a[0].update(asset_class='crypto')
    if fault == 'exchange': assets_change = lambda a: a[0].update(exchange='OTC')
    if fault == 'missing_asset': assets_change = lambda a: a.clear()
    if fault == 'conflicting_class': assets_change = lambda a: a[0].update(**{'class':'crypto'})
    if fault == 'asset_id': trades[0]['asset_id'] = 'different-security'
    with pytest.raises(ValueError, match='COST_FEE_INSTRUMENT_SCOPE'):
        day_check(fee_day, rows=trades + fees, assets_change=assets_change)
