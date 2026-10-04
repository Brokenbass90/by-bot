"""Exact frozen admission priced from captured sources; all inputs synthetic."""
from copy import deepcopy
from fractions import Fraction

import pytest

from bot import att1_canary_preparation as p
from bot import att1_coordinator_adapter as a
from research_lab.att1_lifecycle_coordinator import digest
from research_lab.att1_lifecycle_profile import _decimal_text
from test_att1_canary_preparation import entry_inputs, handoff_inputs, N
from test_att1_exclusive_reservation import ledger, ready_for_canary, ACCOUNT


def data(lower='-0.002'):
    profile, intent, budget = entry_inputs()
    i = intent['instrument']
    instrument = {'retCode':0,'time':N-20,'result':{'category':'linear','nextPageCursor':'',
        'list':[{'symbol':i['symbol'],'status':'Trading','contractType':'LinearPerpetual',
        'quoteCoin':'USDT','settleCoin':'USDT','fundingInterval':480,
        'lowerFundingRate':lower,'upperFundingRate':'0.01',
        'priceFilter':{'tickSize':i['tick_size']},'lotSizeFilter':{
            'qtyStep':i['qty_step'],'minOrderQty':i['min_order_qty'],
            'minNotionalValue':i['min_notional'],'maxMktOrderQty':i['max_market_qty']}}]}}
    fee = {'retCode':0,'time':N-20,'result':{'list':[{'symbol':i['symbol'],
        'takerFeeRate':'0.001','makerFeeRate':'0.0002'}]}}
    i['source_sha256']=digest(instrument)
    old=budget['old_budget_evidence']
    old['fee_source_sha256']=digest(fee);old['funding_source_sha256']=digest(instrument)
    old['funding_cost_reserve_rate']=_decimal_text(43*max(-Fraction(lower),Fraction(0)))
    budget=p.validate_canary_budget_inputs(budget['binding'],old,budget['cash_evidence'],now_ms=N)
    sources={'account_fingerprint_sha256':budget['binding']['account_fingerprint_sha256'],
             'observed_ms':N,'instrument_page':instrument,'fee_page':fee}
    return profile,intent,budget,sources


def bind(values):
    profile,intent,budget,sources=values
    return p.bind_canary_command_budget(budget,profile,intent,order_link_id='exact-cost',cost_sources=sources)


def test_exact_admitted_quantity_reserves_source_bound_fourteen_day_cost():
    values=data();original=deepcopy(values);out=bind(values)
    command=out['command_binding']
    assert command['command']['qty']=='0.04'
    assert command['required_risk_usdt']=='0.44'
    assert command['required_cost_reserve_usdt']=='0.3872'
    assert command['cost_assessment']['funding_settlements']==43
    assert command['cost_assessment']['status']=='CONDITIONAL_SCENARIO_ONLY'
    assert out['orders_allowed'] is False and command['command']['orders_allowed'] is False
    assert values==original and p._revalidate(out)==out


def test_infeasible_actual_quantity_rejects_instead_of_resizing():
    values=data('-0.01');original=deepcopy(values)
    with pytest.raises(a.AdapterViolation,match='BLOCKED_COST_INFEASIBLE'):
        bind(values)
    assert values==original


@pytest.mark.parametrize('change',['account','clock','instrument_hash','step','fee_rate','fee_hash','funding_hash','funding_rate'])
def test_cost_attachment_rejects_source_or_old_provenance_mismatch(change):
    profile,intent,budget,sources=data()
    if change=='account':sources['account_fingerprint_sha256']='f'*64
    if change=='clock':sources['observed_ms']=N-60001
    if change=='instrument_hash':intent['instrument']['source_sha256']='f'*64
    if change=='step':intent['instrument']['qty_step']='0.02'
    key={'fee_rate':'taker_fee_rate','fee_hash':'fee_source_sha256','funding_hash':'funding_source_sha256','funding_rate':'funding_cost_reserve_rate'}.get(change)
    if key:
        old=deepcopy(budget['old_budget_evidence']);old[key]='0' if change.endswith('rate') else 'f'*64
        budget=p.validate_canary_budget_inputs(budget['binding'],old,budget['cash_evidence'],now_ms=N)
    with pytest.raises(a.AdapterViolation):bind((profile,intent,budget,sources))


def test_attached_assessment_cannot_be_repriced_after_validation():
    out=bind(data());out['command_binding']['required_cost_reserve_usdt']='0'
    out['validation_sha256']=digest({k:v for k,v in out.items() if k!='validation_sha256'})
    with pytest.raises(a.AdapterViolation,match='projection/provenance'):
        p._revalidate(out)


def test_daily_spend_is_debited_before_exact_cost_assessment():
    from test_att1_canary_budget import cash_event
    profile,intent,budget,sources=data()
    cash=deepcopy(budget['cash_evidence'])
    cash['events']=[cash_event(account_fingerprint_sha256=budget['binding']['account_fingerprint_sha256'],
        economic_ms=N-10,received_ms=N,gross_realized_usdt='-0.3',execution_fee_usdt='0',funding_cash_usdt='0')]
    budget=p.validate_canary_budget_inputs(budget['binding'],budget['old_budget_evidence'],cash,now_ms=N)
    with pytest.raises(a.AdapterViolation,match='BLOCKED_COST_INFEASIBLE'):
        bind((profile,intent,budget,sources))


def test_prepare_entry_persists_actual_source_reserve_and_restart_never_reprices(ledger):
    con,_=ledger;ready_for_canary(con)
    profile,intent,budget,sources=data()
    budget=p.bind_canary_handoff(budget,**handoff_inputs())
    result=p.prepare_new_att1_entry(con,ACCOUNT,profile=profile,intent=intent,
        validated_budget=budget,now_ms=N,cost_sources=sources)
    assert result['orders_allowed'] is False and result['commands'][0]['qty']=='0.04'
    assert con.execute('SELECT risk_reserve_usdt,cost_reserve_usdt FROM att1_decisions').fetchone()==('0.44','0.3872')
    changed=deepcopy(sources);changed['fee_page']['result']['list'][0]['takerFeeRate']='0.01'
    restarted=p.prepare_new_att1_entry(con,ACCOUNT,profile=profile,intent=intent,
        validated_budget=budget,now_ms=N,cost_sources=changed)
    assert restarted['status']=='RECOVERY_REQUIRED_LOOKUP_ONLY' and restarted['commands']==[]
    assert con.execute('SELECT cost_reserve_usdt FROM att1_decisions').fetchone()==('0.3872',)


def test_prepare_entry_cost_rejection_leaves_no_reservation(ledger):
    con,_=ledger;ready_for_canary(con)
    profile,intent,budget,sources=data('-0.01')
    budget=p.bind_canary_handoff(budget,**handoff_inputs())
    with pytest.raises(a.AdapterViolation,match='BLOCKED_COST_INFEASIBLE'):
        p.prepare_new_att1_entry(con,ACCOUNT,profile=profile,intent=intent,
            validated_budget=budget,now_ms=N,cost_sources=sources)
    assert con.execute('SELECT COUNT(*) FROM att1_decisions').fetchone()[0]==0
