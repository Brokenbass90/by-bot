"""Budget impossibility checks catch optimistic sizing and invented admission."""
from copy import deepcopy
from fractions import Fraction as F

import pytest
from research_lab import att1_feasibility as f

N = 1791105600000


def sources(price='100', lower='-0.0033', step='0.01', maximum='1000'):
    instrument = {'retCode':0,'time':N-100,'result':{'category':'linear','list':[{
        'symbol':'DOTUSDT','status':'Trading','contractType':'LinearPerpetual',
        'quoteCoin':'USDT','settleCoin':'USDT','fundingInterval':480,
        'lowerFundingRate':lower,'upperFundingRate':'0.01',
        'priceFilter':{'tickSize':'0.01'},'lotSizeFilter':{
            'qtyStep':step,'minOrderQty':step,'minNotionalValue':'5',
            'maxMktOrderQty':maximum}}]}}
    fee = {'retCode':0,'time':N-100,'result':{'list':[{'symbol':'DOTUSDT',
        'takerFeeRate':'0.00055','makerFeeRate':'0.0002'}]}}
    ticker = {'retCode':0,'time':N-100,'result':{'category':'linear',
        'list':[{'symbol':'DOTUSDT','bid1Price':price,'ask1Price':price}]}}
    return instrument, fee, ticker


def row(parts, remaining='0.8'):
    return f.assess_symbol_feasibility(symbol='DOTUSDT',instrument_page=parts[0],
        fee_page=parts[1],ticker_page=parts[2],now_ms=N,absolute_risk_usdt='0.4',
        daily_remaining_usdt=remaining,max_notional_usdt='100')


def test_minimum_lot_can_fit_while_every_frozen_sizing_branch_cannot():
    parts=sources();original=deepcopy(parts);out=row(parts)
    assert out['minimum_venue_quantity']=='0.05'
    assert out['minimum_scenario']['required_risk_usdt']=='0.00055'
    assert out['minimum_scenario']['required_cost_reserve_usdt']=='0.7150715'
    assert out['minimum_scenario']['status']=='CONDITIONAL_SCENARIO_ONLY'
    # Independent branch lower bound: risk .4/2 + minimum notional5*.143.
    assert out['sizing_lower_bounds_usdt']['risk_limited']=='0.915'
    assert out['status']=='REJECT_FROZEN_SIZING_BUDGET'
    assert out['orders_allowed'] is False and out['money_ready'] is False
    assert out['actual_signal_available'] is False and parts==original


def test_less_adverse_funding_does_not_produce_false_impossibility():
    out=row(sources(lower='0'))
    assert out['status']=='NOT_PROVEN_FEASIBLE'
    assert out['minimum_scenario']['required_cost_reserve_usdt']=='0.00550055'
    assert out['orders_allowed'] is False


def test_market_maximum_branch_prevents_risk_bound_overclaim():
    out=row(sources(maximum='0.05'))
    assert out['sizing_lower_bounds_usdt']['market_max_limited']=='0.715'
    assert out['status']=='NOT_PROVEN_FEASIBLE'


def test_quantity_and_notional_minimum_round_up_on_captured_step():
    out=row(sources(price='3',step='0.1'))
    assert out['minimum_venue_quantity']=='1.7'
    assert out['minimum_scenario']['required_risk_usdt']=='0.0187'
    assert out['minimum_scenario']['required_cost_reserve_usdt']=='0.731731'


@pytest.mark.parametrize('change',['stale_ticker','wrong_symbol','ambiguous_ticker','bad_instrument','fee_stale','zero_price'])
def test_bad_source_cannot_be_reported_as_budget_rejection(change):
    parts=sources()
    if change=='stale_ticker':parts[2]['time']=N-60001
    if change=='wrong_symbol':parts[2]['result']['list'][0]['symbol']='ETHUSDT'
    if change=='ambiguous_ticker':parts[2]['result']['list']*=2
    if change=='bad_instrument':parts[0]['result']['list'][0]['status']='Closed'
    if change=='fee_stale':parts[1]['time']=N-60001
    if change=='zero_price':parts[2]['result']['list'][0]['bid1Price']='0'
    assert row(parts)['status']=='BLOCKED_SOURCE_INPUTS'


def test_proven_rejection_contains_no_feasible_frozen_size_in_tick_grid():
    out=row(sources());assert out['status']=='REJECT_FROZEN_SIZING_BUDGET'
    # Exercise all three branches and one-unit flooring with independent math.
    for cents in [1,10,100,1000,2000,3600,4000,10000,20000,100000]:
        stop=F(100)+F(cents,100)
        q=(min(F('.4')/((stop-100)*F('1.1')),100/stop,F(1000))//F('.01'))*F('.01')
        if q<F('.01') or q*100<5:continue
        assert q*(stop-100)*F('1.1')+q*stop*F('.143')>F('.8')
