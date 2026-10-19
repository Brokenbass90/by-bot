"""Closed-day account charges -> existing Monthly finalizer, no network."""
import copy
import json
from datetime import datetime
from pathlib import Path
from decimal import Decimal

import pytest

from research_lab.alpaca_dynamic_v1 import digest
from research_lab.alpaca_fee_to_live_closure_v1 import collect_account_cost_source
from research_lab.alpaca_monthly_binding_v1 import CONTRACT, entry_cid
from research_lab import alpaca_monthly_cost_source_v1 as costs
from test_alpaca_monthly_native_binding_v1 import setup, ticket
from test_alpaca_monthly_account_transport_v1 import connect_wire


def ms(value):
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000)


@pytest.fixture
def case():
    anchor_ms = ms('2026-10-01T13:29:00Z')
    observed = ms('2026-10-03T12:00:00Z')
    entry = dict(id='buy-a', symbol='AAA', side='buy', filled_qty='1', filled_avg_price='10',
                 filled_at='2026-10-01T14:00:00Z', client_order_id=entry_cid({'selection_id': 'selection'}, 'AAA'))
    other = dict(id='buy-b', symbol='BBB', side='buy', filled_qty='2', filled_avg_price='20',
                 filled_at='2026-10-01T14:01:00Z', client_order_id=entry_cid({'selection_id': 'selection'}, 'BBB'))
    exit = dict(id='sell-a', symbol='AAA', side='sell', filled_qty='1', filled_avg_price='12',
                filled_at='2026-10-02T14:00:00Z', type='stop', status='filled')
    positions = [dict(symbol='BBB', entry_id='buy-b', selection_id='selection', raw_entry=other)]
    retired = dict(symbol='AAA', entry_id='buy-a', selection_id='selection', raw_entry=entry)
    exits = [dict(entry_id='buy-a', orders=[exit], retired_position=retired, reason='protective_stop_intraday')]
    fills = [dict(id='f1', activity_type='FILL', order_id='buy-a', symbol='AAA', side='buy', qty='.4', price='10', transaction_time='2026-10-01T13:59:00Z'),
             dict(id='f2', activity_type='FILL', order_id='buy-a', symbol='AAA', side='buy', qty='.6', price='10', transaction_time='2026-10-01T14:00:00Z'),
             dict(id='f3', activity_type='FILL', order_id='buy-b', symbol='BBB', side='buy', qty='2', price='20', transaction_time='2026-10-01T14:01:00Z'),
             dict(id='f4', activity_type='FILL', order_id='sell-a', symbol='AAA', side='sell', qty='1', price='12', transaction_time='2026-10-02T14:00:00Z')]
    fees = [dict(id='fee1', activity_type='FEE', activity_sub_type='CAT', date='2026-10-01', created_at='2026-10-02T00:16:00Z', status='executed', currency='USD', net_amount='-.01'),
            dict(id='fee2', activity_type='FEE', activity_sub_type='CAT', date='2026-10-02', created_at='2026-10-03T00:16:00Z', status='executed', currency='USD', net_amount='-.01'),
            dict(id='fee3', activity_type='FEE', activity_sub_type='REG', date='2026-10-02', created_at='2026-10-03T00:17:00Z', status='executed', currency='USD', net_amount='-.01')]
    protocol = dict(schema='ALPACA_PROTOCOL_SOURCE_CONTRACT_V1', account_id='fixture', commission_rate='0',
        owner_attestation={'api_commission_null_is_not_proof': True}, regulatory_model=dict(
            cat_nms_executed_share_rate='.000003', sec_sell_value_rate='.0000206', taf_per_share_rate='0',
            rounding='each fee type aggregated daily per account then ceiling to USD0.01; exact fractional executed quantities'))
    calendar = [dict(session=d, open_ms=ms(d+'T13:30:00Z'), close_ms=ms(d+'T20:00:00Z')) for d in ('2026-10-01', '2026-10-02')]
    assets = [dict(id=s, symbol=s, asset_class='us_equity', exchange='NASDAQ') for s in ('AAA', 'BBB')]
    anchor = dict(schema='ALPACA_MONTHLY_CASH_ANCHOR_V1', account_id='fixture',
        client_order_id=entry['client_order_id'], observed_ms=anchor_ms,
        account=dict(id='fixture', currency='USD', cash='100', accrued_fees='0', pending_reg_taf_fees='0'))
    return dict(fills=fills, fees=fees, protocol=protocol, calendar=calendar, assets=assets,
        anchor=anchor, positions=positions, exits=exits, observed=observed, cash='61.97')


def derive(case):
    account = dict(id='fixture', currency='USD', cash=case['cash'], accrued_fees=case.get('pending', '0'), pending_reg_taf_fees='0')
    def get(route, params):
        body = account if route == '/v2/account' else case['fills'] + case['fees']
        return dict(http_status=200, started_ms=case['observed']-100, received_ms=case['observed']-100,
                    raw=json.dumps(body))
    source = collect_account_cost_source(get, account_id='fixture', after='2026-10-01T00:00:00Z',
        until='2026-10-03T06:00:00Z', now_ms=case['observed'])
    return costs.derive_owned_exit_cost(source=source, protocol=case['protocol'], calendar=case['calendar'],
        assets=case['assets'], anchor=case['anchor'], positions=case['positions'], exits=case['exits'], entry_id='buy-a')


def test_account_day_costs_allocate_once_without_claiming_broker_per_order_fees(case):
    result = derive(case)
    assert result['closure_status'] == 'ACCOUNT_DAY_FEES_RECONCILED'
    assert result['gross_before_fees'] == '2'
    # Buy-day penny goes to the two-share open entry. All posted pennies remain accounted.
    assert result['regulatory_fees_usd'] == '0.02'
    assert result['other_cash_net_usd'] == '-40.01'
    assert result['cash_after_exit'] == '61.97'
    assert result['allocation_policy'] == costs.ALLOCATION_POLICY
    assert result['broker_per_order_fee_attribution'] is False
    assert result['money_authority'] is False


def test_repeated_source_and_reordered_activity_rows_do_not_change_allocation(case):
    first = derive(case)
    assert derive(case) == first
    case['fills'].reverse(); case['fees'].reverse()
    second = derive(case)
    assert second['regulatory_fees_usd'] == first['regulatory_fees_usd']
    assert second['account_day_allocations'] == first['account_day_allocations']


@pytest.mark.parametrize('fault', ['missing_fee', 'foreign_fill', 'quantity', 'price', 'cash', 'anchor', 'owner', 'liability'])
def test_uncertainty_cannot_produce_terminal_source(case, fault):
    if fault == 'missing_fee': case['fees'].pop()
    if fault == 'foreign_fill': case['fills'][2]['order_id'] = 'foreign'
    if fault == 'quantity': case['fills'][0]['qty'] = '.5'
    if fault == 'price': case['fills'][0]['price'] = '11'
    if fault == 'cash': case['cash'] = '62.97'
    if fault == 'anchor': case['anchor']['observed_ms'] = case['observed']
    if fault == 'owner': case['exits'][0]['retired_position']['raw_entry']['client_order_id'] = 'legacy-NET'
    if fault == 'liability': case['pending'] = '.01'
    with pytest.raises(ValueError): derive(case)


def test_broker_cent_rounding_is_explicit_and_never_hidden_as_other_cash(case):
    for f in case['fills'][:2]: f['price'] = '10.006'
    case['exits'][0]['retired_position']['raw_entry']['filled_avg_price'] = '10.006'
    case['cash'] = '61.97'  # .4 and .6 share fills each settle to exact cents here.
    result = derive(case)
    assert result['gross_before_fees'] == '1.994'
    assert Decimal(result['broker_cash_rounding_usd']) == Decimal('0.006')
    assert result['other_cash_net_usd'] == '-40.01'


@pytest.mark.parametrize('precision', ['pinned', 'unknown', 'unproven'])
def test_unequal_price_partial_fills_need_explicit_source_pinned_average_precision(case, precision):
    case['fills'][1]['price']='11.111111115'
    case['exits'][0]['retired_position']['raw_entry']['filled_avg_price']='10.666667'
    case['cash']='61.30'
    if precision != 'unknown':
        case['protocol']['execution_average_precision']=dict(decimal_places=6,rounding='ROUND_HALF_UP',source_sha256='a'*64)
        case['protocol']['sources']={'fixture_precision': {'sha256': 'a'*64 if precision=='pinned' else 'b'*64}}
    if precision != 'pinned':
        with pytest.raises(ValueError, match='ORDER_AVERAGE_PRECISION_UNKNOWN'): derive(case)
    else:
        result=derive(case)
        assert result['activity_gross_before_fees']=='1.3333333310'
        assert result['gross_before_fees']=='1.333333'
        assert result['broker_cash_rounding_usd']=='-0.0033333310'


def test_delayed_fees_restart_producer_and_existing_finalizer_complete_one_cycle(setup, case, tmp_path, monkeypatch):
    book, selection, adapter, io, now = setup
    original_account = io.get_account
    io.get_account = lambda: dict(original_account(), currency='USD', accrued_fees='0', pending_reg_taf_fees='0')
    client, writes, lose = connect_wire(setup, monkeypatch)
    adapter.enter(ticket(setup), now_ms=now, apply=True)
    io.orders['stop'].update(status='filled', filled_qty='.3', filled_avg_price='277', filled_at='2026-11-02T14:30:59Z')
    io.positions=[]; io.get_clock=lambda: dict(is_open=True, timestamp='2026-11-02T14:31:00Z')
    adapter.maintain(now_ms=now+60000, apply=True)
    observed=ms('2026-11-03T22:00:00Z')
    account=dict(original_account(), cash='477.13', currency='USD', accrued_fees='0', pending_reg_taf_fees='0')
    io.get_account=lambda: copy.deepcopy(account)
    fills=[dict(id='f-buy', activity_type='FILL', order_id='entry', symbol='NET', side='buy', qty='.3', price='311.222', transaction_time='2026-11-02T14:30:01Z'),
           dict(id='f-sell', activity_type='FILL', order_id='stop', symbol='NET', side='sell', qty='.3', price='277', transaction_time='2026-11-02T14:30:59Z')]
    fees=[dict(id='f-cat', activity_type='FEE', activity_sub_type='CAT', date='2026-11-02', created_at='2026-11-03T00:16:00Z', status='executed', currency='USD', net_amount='-.01'),
          dict(id='f-sec', activity_type='FEE', activity_sub_type='REG', date='2026-11-02', created_at='2026-11-03T00:17:00Z', status='executed', currency='USD', net_amount='-.01')]
    def capture(rows):
        def get(route, params):
            return dict(http_status=200, started_ms=observed-100, received_ms=observed-100,
                raw=json.dumps(account if route=='/v2/account' else rows))
        return collect_account_cost_source(get, account_id='fixture', after='2026-11-02T00:00:00Z',
            until='2026-11-03T21:59:00Z', now_ms=observed)
    values=dict(protocol=case['protocol'], calendar=selection['calendar'],
                assets=[dict(id='NET', symbol='NET', asset_class='us_equity', exchange='NYSE')])
    paths={}
    for name,value in values.items():
        p=tmp_path/(name+'.json');p.write_text(json.dumps(value)); paths[name+'_path']=p
    early=tmp_path/'early.json';early.write_text(json.dumps(capture(fills)))
    with pytest.raises(ValueError, match='COST_FEE_POSTING_PENDING_OR_CONFLICT'):
        costs.produce_cost_sources(adapter, source_path=early, now_ms=observed, **paths)
    with pytest.raises(ValueError, match='MONTHLY_ACCOUNTING_PENDING'): adapter._require_exit_accounting()
    late=tmp_path/'late.json';late.write_text(json.dumps(capture(fills+fees)))
    def raw_get(route, params):
        if route=='/v2/clock': body=dict(timestamp='2026-11-03T21:59:00Z')
        elif route=='/v2/account': body=account
        else: assert route=='/v2/account/activities';body=fills+fees
        return dict(http_status=200,started_ms=observed-100,received_ms=observed-100,raw=json.dumps(body))
    client.cost_get=raw_get
    results=costs.capture_and_produce_cost_sources(adapter, after='2026-11-02T00:00:00Z', now_ms=observed, **paths)
    automatic_source=next((adapter.runtime/'cost-captures').glob('*/source.json'))
    source_path=results['entry']; before=Path(source_path).read_bytes(); stamp=Path(source_path).stat().st_mtime_ns
    # Lost caller response/restart: the producer reuses the same immutable source.
    assert costs.produce_cost_sources(adapter, source_path=automatic_source, now_ms=observed, **paths)==results
    assert Path(source_path).read_bytes()==before and Path(source_path).stat().st_mtime_ns==stamp
    # Liabilities may accrue between the captured source and independent readback.
    for fault in ('nonzero','missing','nonfinite','currency'):
        saved=copy.deepcopy(account)
        if fault=='nonzero':account['pending_reg_taf_fees']='.50'
        if fault=='missing':account.pop('pending_reg_taf_fees')
        if fault=='nonfinite':account['accrued_fees']='NaN'
        if fault=='currency':account['currency']='EUR'
        with pytest.raises(ValueError, match='TERMINAL_LIABILITY_PENDING'):
            adapter.finalize_exit('entry',source_path,now_ms=observed)
        with pytest.raises(ValueError, match='MONTHLY_ACCOUNTING_PENDING'): adapter._require_exit_accounting()
        account.clear();account.update(saved)
    result=adapter.finalize_exit('entry',source_path,now_ms=observed)
    assert result['status']=='LIVE_TERMINAL_COST_FINALITY'
    assert result['net_usd_exact']=='-10.2866' and result['broker_cash_after']=='477.13'
    assert adapter.finalize_exit('entry',source_path,now_ms=observed)==result
    assert costs.produce_cost_sources(adapter, source_path=automatic_source, now_ms=observed, **paths)=={}
    assert adapter._require_exit_accounting() is None
    assert len(writes)==2  # only the simulated initial entry and protection


@pytest.mark.parametrize('failure', ['clock_http', 'clock_json', 'later_http'])
def test_failed_automatic_capture_always_preserves_initial_clock(tmp_path, failure):
    from types import SimpleNamespace
    class Book:
        def rows(self, table):return [{}]
    def get(route, params):
        if route=='/v2/clock':
            raw='bad json' if failure=='clock_json' else '{"timestamp":"2026-10-03T00:00:00Z"}'
            status=503 if failure=='clock_http' else 200
        else:raw='{"message":"later failure"}';status=503
        return dict(http_status=status,raw=raw,started_ms=1790985600000,received_ms=1790985600000)
    native=SimpleNamespace(book=Book(),runtime=tmp_path,account='fixture',client=SimpleNamespace(cost_get=get))
    with pytest.raises(ValueError):
        costs.capture_and_produce_cost_sources(native,after='2026-10-01T00:00:00Z',protocol_path='unused',
            calendar_path='unused',assets_path='unused',now_ms=1790985601000)
    saved=json.loads(next((tmp_path/'cost-captures').glob('failed-*.json')).read_bytes())
    assert saved['clock_capture']['raw']==('bad json' if failure=='clock_json' else '{"timestamp":"2026-10-03T00:00:00Z"}')
    assert saved['clock_capture']['http_status']==(503 if failure=='clock_http' else 200)
    if failure=='later_http':assert saved['captures'][0]['raw']=='{"message":"later failure"}'
