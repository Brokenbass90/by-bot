from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pytest

from research_lab.brain_v2_frozen_primitives import Opportunity, BrainBlocked, digest
from research_lab.brain_v2_a1 import (
    HOUR, CUTOFF_MS, COST_MODEL, empty_brain_state, assess_request, build_contexts,
    signal_available_ms, TABLE_PIN, A1_PIN, A2_PIN,
)

PIN='a'*64
NOW=1_791_763_200_000  # 2026-10-12 00:00 UTC


def op(i=0, sleeve='ATT1', side='long', hour=NOW):
    base=HOUR//4 if sleeve in ('ETS2','SF3') else HOUR
    return Opportunity(sleeve,f'COIN{i}USDT',side,hour-base,hour,'next_open',.02,48,COST_MODEL,PIN)


def initialized():
    request=dict(request_id='epoch1',kind='INIT',initial_equity_usd=1000,
                 epoch_start_ms=NOW,source_hash=PIN,capital_known=True,
                 positions_known=True,protection_known=True)
    return assess_request(request,empty_brain_state())['state_after']


def batch(xs, hour=NOW, exits=()):
    return dict(request_id=f'hour{hour}',kind='HOUR',hour_ms=hour,
                sealed_at_ms=hour+HOUR,coverage_end_ms=hour+HOUR,source_hash=PIN,
                positions_known=True,protection_known=True,costs_known=True,
                opportunities=[asdict(x) for x in xs],
                contexts=build_contexts(xs,hour_ms=hour,btc_h4=None,symbol_h1={}),
                terminals=list(exits))


def test_budget_denominator_accepts_first_position_and_arms_are_separate():
    state=initialized(); result=assess_request(batch([op()]),state)
    assert state['arms']['RAW_SAFE']['positions']=={}  # pure function
    assert result['status']=='HOUR_RECORDED_ORDERS_OFF'
    for arm in ('RAW_SAFE','FOUNDATION','BRAIN_DET'):
        a=result['state_after']['arms'][arm]
        assert len(a['positions'])==1
        assert a['realized_equity_usd']=='1000'
    assert result['decisions']['FOUNDATION'][0]['risk_usd']=='5.000'
    assert result['orders_allowed'] is result['money_authority'] is False
    assert result['pins']['table_sha256']==TABLE_PIN


def test_greedy_continue_after_sleeve_cap_without_rejecting_all_later_sleeves():
    xs=[op(i,sleeve='BOUNCE1',side='long' if i%2 else 'short') for i in range(5)]
    xs.append(op(9,sleeve='ASR1'))
    result=assess_request(batch(xs),initialized())
    decisions=result['decisions']['FOUNDATION']
    assert sum(d['accepted'] for d in decisions if d['sleeve']=='BOUNCE1')==4
    assert any(d['reason']=='sleeve_cap' for d in decisions)
    assert next(d for d in decisions if d['sleeve']=='ASR1')['accepted'] is True
    assert len(result['state_after']['arms']['RAW_SAFE']['positions'])==6


def test_direction_budget_cap_is_36_usd_not_60_percent_of_current_risk():
    xs=[op(i,sleeve=('ATT1','ASR1','SBR1')[i%3]) for i in range(8)]
    result=assess_request(batch(xs),initialized())
    assert sum(d['accepted'] for d in result['decisions']['FOUNDATION'])==7
    assert result['decisions']['FOUNDATION'][-1]['reason']=='direction_cap'


def test_exact_twelve_slots_limit_and_first_violation_priority():
    xs=[op(i,sleeve=('ATT1','ASR1','SBR1')[i%3],side='long' if i%2 else 'short') for i in range(12)]
    first=assess_request(batch(xs),initialized())
    assert len(first['state_after']['arms']['RAW_SAFE']['positions'])==12
    duplicate_symbol=op(0,hour=NOW+HOUR)
    second=assess_request(batch([duplicate_symbol],hour=NOW+HOUR),first['state_after'])
    assert second['decisions']['RAW_SAFE'][0]['reason']=='slots_full'


def test_both_orders_are_exact_deterministic_and_negative_scores_still_admit():
    xs=[op(i,sleeve=s) for i,s in enumerate(('SF3','ATT1','BOUNCE1','ASR1'))]
    a=assess_request(batch(xs),initialized())
    b=assess_request(batch(list(reversed(xs))),initialized())
    assert a['decisions']==b['decisions']
    brain=a['decisions']['BRAIN_DET']
    assert [d['z'] for d in brain]==sorted((d['z'] for d in brain),reverse=True)
    assert any(d['z']<0 and d['accepted'] for d in brain)
    assert all(.5<=d['multiplier']<=1.5 for d in brain)


def terminal(x, hour=NOW+HOUR, gross=.02):
    return dict(opportunity_id=x.id,actual_exit_ms=hour+100,available_ms=hour+101,
                gross_return_frac=gross,exit_notional_ratio=1.02,
                funding_cost_frac=.001,source_hash=PIN,finality='FINAL',cost_model_id=COST_MODEL)


def test_realized_equity_full_costs_and_release_before_same_hour_batch():
    x=op(); first=assess_request(batch([x]),initialized())
    new=op(hour=NOW+HOUR)
    second=assess_request(batch([new],hour=NOW+HOUR,exits=[terminal(x)]),first['state_after'])
    a=second['state_after']['arms']['RAW_SAFE']
    # notional250; gross5, fees.303, slippage.101, funding.25 -> net4.346.
    assert float(a['realized_equity_usd'])==pytest.approx(1004.346)
    assert second['decisions']['RAW_SAFE'][0]['accepted'] is True
    assert float(second['decisions']['RAW_SAFE'][0]['risk_usd'])==pytest.approx(5.02173)
    assert x.id in a['closed'] and x.id not in a['positions']
    assert second['state_after']['arms']['BRAIN_DET']['realized_equity_usd']!=a['realized_equity_usd']


@pytest.mark.parametrize('field,value', [('positions_known',False),('protection_known',False),('costs_known',False),
    ('coverage_end_ms',NOW),('sealed_at_ms',NOW+HOUR-1),('source_hash','unknown')])
def test_unknown_incomplete_authority_blocks_without_state_mutation(field,value):
    state=initialized(); req=batch([op()]);req[field]=value
    with pytest.raises(BrainBlocked): assess_request(req,state)
    assert not any(a['positions'] for a in state['arms'].values())


@pytest.mark.parametrize('field,value', [('finality','UNKNOWN'),('funding_cost_frac',None),
    ('available_ms',NOW+3*HOUR),('source_hash','unknown'),('cost_model_id','TABLE_R_ALREADY_NET')])
def test_unresolved_terminal_cannot_free_risk_or_create_zero_cost(field,value):
    x=op();state=assess_request(batch([x]),initialized())['state_after']; event=terminal(x);event[field]=value
    with pytest.raises(BrainBlocked): assess_request(batch([],hour=NOW+HOUR,exits=[event]),state)
    assert x.id in state['arms']['RAW_SAFE']['positions']


def test_duplicate_opportunity_out_of_order_hour_and_terminal_are_explicit_blocked():
    x=op();state=assess_request(batch([x]),initialized())['state_after']
    with pytest.raises(BrainBlocked,match='hour_sequence'): assess_request(batch([],hour=NOW+2*HOUR),state)
    with pytest.raises(BrainBlocked,match='duplicate_opportunity'): assess_request(batch([x,x]),initialized())
    with pytest.raises(BrainBlocked,match='duplicate_terminal'):
        assess_request(batch([],hour=NOW+HOUR,exits=[terminal(x),terminal(x)]),state)


def test_a2_available_mapping_for_both_timeframes_without_reading_outcomes():
    assert signal_available_ms('ATT1',NOW)==NOW+HOUR
    assert signal_available_ms('ETS2',NOW)==NOW+HOUR//4
    assert signal_available_ms('SF3',NOW+HOUR//4)==NOW+HOUR//2
    with pytest.raises(BrainBlocked): signal_available_ms('UNKNOWN',NOW)
    with pytest.raises(BrainBlocked): signal_available_ms('ETS2',NOW+1)


def test_context_future_or_different_hour_cannot_be_silently_adopted():
    req=batch([op()]); req['contexts'][op().id]['hour_ms']+=HOUR
    with pytest.raises(BrainBlocked,match='context'): assess_request(req,initialized())


def test_state_tamper_cannot_rebase_cap_or_adopt_unknown_positions():
    state=initialized(); state['arms']['RAW_SAFE']['realized_equity_usd']='1001'
    with pytest.raises(BrainBlocked,match='state'): assess_request(batch([]),state)
