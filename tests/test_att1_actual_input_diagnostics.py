"""Source diagnostics and conservative scenarios; not broker/live evidence."""
from copy import deepcopy

import pytest

from bot import att1_coordinator_adapter as a
from bot import att1_canary_preparation as p
from test_att1_symbol_input_evidence import inputs, envelope, NOW


def test_duplicate_zero_template_retains_both_sources_and_never_certifies_mode():
    data = inputs()
    first = data['position_pages'][0]
    first['result']['list'][0].update(seq=123, createdTime='123', updatedTime='456')
    first['result']['nextPageCursor'] = 'next'
    template = {'symbol':'LINKUSDT','positionIdx':0,'side':'','size':'0',
                'seq':-1,'createdTime':'','updatedTime':'','positionStatus':'',
                'stopLoss':'','takeProfit':'','trailingStop':''}
    data['position_pages'].append(envelope([template]))
    out = a.diagnose_att1_symbol_position_sources(data['position_pages'], symbol='LINKUSDT', observed_ms=NOW)
    assert out['status'] == 'BLOCKED_DUPLICATE_POSITION_INDEX'
    assert out['raw_row_count'] == 2 and out['position_indices'] == [0,0]
    assert out['uninitialized_zero_template_rows'] == [1]
    assert len(out['row_sources']) == 2 and out['rows_discarded'] == 0
    assert out['orders_allowed'] is False
    with pytest.raises(a.AdapterViolation):a.validate_att1_symbol_input_evidence(**data)


def test_link_hedge_and_zero_source_conflict_stays_blocked():
    first=envelope([{'symbol':'LINKUSDT','positionIdx':i,'side':'','size':'0'} for i in (1,2)])
    first['result']['nextPageCursor']='next'
    out=a.diagnose_att1_symbol_position_sources([first,envelope([{'symbol':'LINKUSDT','positionIdx':0,'side':'','size':'0'}])],symbol='LINKUSDT',observed_ms=NOW)
    assert out['status']=='BLOCKED_MODE_CONFLICT' and out['position_indices']==[1,2,0]
    assert out['rows_discarded']==0


@pytest.mark.parametrize('change',['cursor','stale','foreign','bad_size','boolean_idx'])
def test_diagnostics_do_not_soften_invalid_sources(change):
    data=inputs();pages=data['position_pages'];row=pages[0]['result']['list'][0]
    if change=='cursor':pages[0]['result']['nextPageCursor']='incomplete'
    if change=='stale':pages[0]['time']=NOW-60001
    if change=='foreign':row['symbol']='ADAUSDT'
    if change=='bad_size':row['size']='NaN'
    if change=='boolean_idx':row['positionIdx']=False
    with pytest.raises(a.AdapterViolation):a.diagnose_att1_symbol_position_sources(pages,symbol='LINKUSDT',observed_ms=NOW)


def costs():
    data=inputs()
    data['instrument_page']['result']['list'][0].update(fundingInterval=480,lowerFundingRate='-0.0066',upperFundingRate='0.0066')
    data['instrument_page']['result']['list'][0]['lotSizeFilter']['maxMktOrderQty']='100'
    return dict(symbol='LINKUSDT',instrument_page=data['instrument_page'],fee_page=data['fee_page'],
        now_ms=NOW,requested_qty='0.5',entry_price='10',original_stop='11',
        absolute_risk_usdt='0.60',daily_remaining_usdt='1.20',max_notional_usdt='100')


def test_14day_full_risk_quantity_rejected_without_resizing_or_shortening_hold():
    out=p.assess_att1_14day_quantity(**costs())
    # 43 * .0066 * (.5*11) + two .00055 fees = 1.56695 through stop-price scenario.
    assert out['funding_settlements']==43 and out['hold_minutes']==20160
    assert out['required_risk_usdt']=='0.55'
    assert out['required_cost_reserve_usdt']=='1.56695'
    assert out['status']=='BLOCKED_COST_INFEASIBLE' and out['requested_qty']=='0.5'
    assert out['quantity_changed'] is False and out['orders_allowed'] is False


def test_feasible_snapshot_scenario_is_not_a_future_guarantee_or_money_pass():
    values=costs();values.update(daily_remaining_usdt='3')
    out=p.assess_att1_14day_quantity(**values)
    assert out['status']=='CONDITIONAL_SCENARIO_ONLY'
    assert out['future_ceiling_proven'] is False and out['money_ready'] is False
    altered=deepcopy(values);altered['instrument_page']['result']['list'][0]['lowerFundingRate']='-0.01'
    assert p.assess_att1_14day_quantity(**altered)['source_sha256']!=out['source_sha256']


@pytest.mark.parametrize('change',['minimum','step','stale','foreign_fee','missing_interval','risk_cap'])
def test_quantity_policy_denies_missing_costs_bad_lots_or_oversized_risk(change):
    values=costs()
    if change=='minimum':values['requested_qty']='0.1'
    if change=='step':values['requested_qty']='0.55'
    if change=='stale':values['instrument_page']['time']=NOW-60001
    if change=='foreign_fee':values['fee_page']['result']['list'][0]['symbol']='BTCUSDT'
    if change=='missing_interval':del values['instrument_page']['result']['list'][0]['fundingInterval']
    if change=='risk_cap':values['absolute_risk_usdt']='0.50'
    out=p.assess_att1_14day_quantity(**values)
    assert out['status'].startswith('BLOCKED_') and out['money_ready'] is False


def test_stop_notional_not_entry_notional_enforces_frozen_cap():
    values=costs();values.update(max_notional_usdt='5',daily_remaining_usdt='3')
    assert p.assess_att1_14day_quantity(**values)['status']=='BLOCKED_RISK_OR_NOTIONAL_CAP'

def test_market_quantity_limit_is_not_ignored_by_cost_assessment():
    values=costs();values.update(daily_remaining_usdt='3')
    values['instrument_page']['result']['list'][0]['lotSizeFilter']['maxMktOrderQty']='0.4'
    assert p.assess_att1_14day_quantity(**values)['status']=='BLOCKED_VENUE_MINIMUM_OR_STEP'
