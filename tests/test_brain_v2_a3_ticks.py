from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal, localcontext

import pytest

from research_lab.brain_v2_frozen_primitives import Opportunity, BrainBlocked
from research_lab.brain_v2_a1 import build_contexts, BrainJournal as A1Journal
from research_lab.brain_v2_a3 import (
    TICK, HOUR, COST_MODEL, A3_PIN, A4_PIN, BrainJournal, empty_brain_state,
    assess_request, funding_summary, terminal_cash, funding_population_status,
)

NOW=1_791_763_200_000
PIN='a'*64


def op(i=0, sleeve='ATT1', tick=NOW, side='long'):
    base=TICK if sleeve in ('ETS2','SF3') else HOUR
    return Opportunity(sleeve,f'COIN{i}USDT',side,tick-base,tick,
                       'next_open',.020003,48,COST_MODEL,PIN)


def init():
    return dict(request_id='a3_epoch',kind='INIT',initial_equity_usd=1000,
                epoch_start_ms=NOW,source_hash=PIN,capital_known=True,
                positions_known=True,protection_known=True)


def initialized():
    return assess_request(init(),empty_brain_state())['state_after']


def tick(xs=(), at=NOW, terminals=()):
    return dict(request_id=f'tick{at}',kind='TICK',tick_ms=at,known_at_ms=at,
                coverage_end_ms=at,batch_complete=True,terminals_complete=True,source_hash=PIN,
                positions_known=True,protection_known=True,
                opportunities=[asdict(x) for x in xs],
                entries={x.id:dict(lev='49.99',source_hash=x.source_hash,
                                  t_available=x.t_available,entry_rule='next_open') for x in xs},
                contexts=build_contexts(xs,hour_ms=at//HOUR*HOUR,btc_h4=None,symbol_h1={}),
                terminals=list(terminals))


def funding(x, end, expected=(), rates=()):
    return dict(schema='BRAIN_V2_A3_FUNDING',venue='bybit',symbol=x.symbol,
                source_hash=PIN,calendar_sha256='b'*64,calendar_complete=True,
                start_ms=x.t_available,end_ms=end,known_at_ms=end,
                expected_settlements=list(expected),
                rates=[dict(settlement_ms=t,rate=r,available_ms=t) for t,r in rates])


def terminal(x, hours=1, R='.98', expected=(), rates=()):
    end=x.t_available+hours*HOUR
    return dict(opportunity_id=x.id,hours=hours,R=R,available_ms=end,
                source_hash=x.source_hash,cost_model_id=COST_MODEL,
                funding=funding(x,end,expected,rates))


def advance(state, to, terminals=(), xs=()):
    start=state['epoch_start_ms'] if state['last_tick_ms'] is None else state['last_tick_ms']+TICK
    for at in range(start,to+1,TICK):
        result=assess_request(tick(xs if at==to else (),at,terminals if at==to else ()),state)
        state=result['state_after']
    return result


def test_exact_quarter_hour_batch_context_and_source_lev():
    x=op(sleeve='ETS2',tick=NOW+TICK)
    result=advance(initialized(),NOW+TICK,xs=[x])
    for arm in result['state_after']['arms'].values():
        p=arm['positions'][x.id]
        assert p['entry_ms']==NOW+TICK
        assert p['context_hour_ms']==NOW
        assert p['lev']=='49.99'
        assert Decimal(p['notional_usd'])==Decimal(p['risk_usd'])*Decimal('49.99')
        assert 'R' not in p and 'hours' not in p and 'release_time' not in p
    assert result['pins']['addendum_a3_sha256']==A3_PIN
    assert result['pins']['addendum_a4_sha256']==A4_PIN
    assert result['orders_allowed'] is result['money_authority'] is False


def test_future_opportunity_cannot_enter_earlier_package():
    state=initialized();future=op(sleeve='ETS2',tick=NOW+TICK)
    with pytest.raises(BrainBlocked,match='opportunity_not_exact_tick'):
        assess_request(tick([op(),future]),state)
    assert not any(a['positions'] for a in state['arms'].values())


def test_off_grid_is_explicit_per_arm_rejection_not_rounded():
    x=replace(op(sleeve='ETS2'),t_available=NOW+1,t_signal=NOW-TICK+1)
    result=assess_request(tick([x]),initialized())
    for arm in result['decisions'].values():
        assert len(arm)==1 and arm[0]['reason']=='off_grid' and arm[0]['accepted'] is False
    assert not any(a['positions'] for a in result['state_after']['arms'].values())


def test_h1_symbol_cannot_be_time_shifted_to_intrahour():
    x=op(tick=NOW+TICK)
    with pytest.raises(BrainBlocked,match='opportunity_frozen_time_cost|signal_bar_identity'):
        advance(initialized(),NOW+TICK,xs=[x])


def test_release_before_new_batch_credits_exact_a3_net_without_double_commission():
    x=op();s=assess_request(tick([x]),initialized())['state_after']
    result=advance(s,NOW+HOUR,terminals=[terminal(x)],xs=[op(tick=NOW+HOUR)])
    a=result['state_after']['arms']['RAW_SAFE'];closed=a['closed'][x.id]
    # risk5, rounded stream lev49.99 => notional249.95. R already net of6bps/side.
    assert Decimal(closed['r_pnl_usd'])==Decimal('4.9')
    assert Decimal(closed['slippage_usd'])==Decimal('.09998')
    assert Decimal(closed['net_usd'])==Decimal('4.80002')
    assert Decimal(a['realized_equity_usd'])==Decimal('1004.80002')
    assert Decimal(result['decisions']['RAW_SAFE'][0]['risk_usd'])==Decimal('5.0240001')
    assert x.id not in a['positions']


def test_quarter_hour_release_keeps_capital_causal_inside_same_hour():
    x=op(sleeve='ETS2',tick=NOW+TICK)
    first=advance(initialized(),NOW+TICK,xs=[x])
    before=advance(first['state_after'],NOW+HOUR)
    assert x.id in before['state_after']['arms']['RAW_SAFE']['positions']
    result=advance(before['state_after'],NOW+HOUR+TICK,terminals=[terminal(x)],
                   xs=[op(sleeve='ETS2',tick=NOW+HOUR+TICK)])
    assert x.id in result['state_after']['arms']['RAW_SAFE']['closed']
    assert result['decisions']['RAW_SAFE'][0]['accepted'] is True


@pytest.mark.parametrize('mutation', ['R','hours','release_time','lev_missing','future_entry'])
def test_entry_metadata_cannot_import_outcome_or_guess_lev(mutation):
    x=op();req=tick([x]);entry=req['entries'][x.id]
    if mutation in ('R','hours','release_time'):entry[mutation]=1
    elif mutation=='lev_missing':entry.pop('lev')
    else:entry['t_available']+=TICK
    with pytest.raises(BrainBlocked,match='entry'):
        assess_request(req,initialized())


@pytest.mark.parametrize('mutation', ['hours_zero','hours_fractional','R_nan','source','early','late','future'])
def test_terminal_never_frees_on_entry_or_backdates_future_unknown_outcomes(mutation):
    x=op();s=assess_request(tick([x]),initialized())['state_after'];event=terminal(x)
    if mutation=='hours_zero':event['hours']=0
    elif mutation=='hours_fractional':event['hours']=.25
    elif mutation=='R_nan':event['R']='NaN'
    elif mutation=='source':event['source_hash']='c'*64
    elif mutation=='future':event['available_ms']+=1
    at=NOW+HOUR-TICK if mutation=='early' else NOW+HOUR+TICK if mutation=='late' else NOW+HOUR
    with pytest.raises(BrainBlocked):advance(s,at,terminals=[event])
    assert x.id in s['arms']['RAW_SAFE']['positions']


def test_funding_signed_exact_bounds_and_no_duplicate_commission():
    x=op();end=NOW+HOUR
    f=funding(x,end,[NOW+TICK,end],[(NOW+TICK,'.001'),(end,'-.0002')])
    result=funding_summary(f,x,end,end)
    assert result['status']=='KNOWN' and Decimal(result['rate_sum'])==Decimal('.0008')
    long=terminal_cash('5','49.99','.98','long',result)
    short=terminal_cash('5','49.99','.98','short',result)
    assert Decimal(long['funding_usd'])==Decimal('.19996')
    assert Decimal(short['funding_usd'])==Decimal('-.19996')
    assert Decimal(long['net_usd'])==Decimal('4.60006')
    assert Decimal(short['net_usd'])==Decimal('4.99998')


def test_a4_missing_funding_frees_risk_excludes_whole_pnl_and_preserves_equity():
    x=op();end=NOW+HOUR;f=funding(x,end,[end],[])
    summary=funding_summary(f,x,end,end)
    assert summary['status']=='FUNDING_UNKNOWN' and summary['rate_sum'] is None
    cash=terminal_cash('5','49.99','1','long',summary)
    assert cash['net_usd'] is cash['r_pnl_usd'] is cash['slippage_usd'] is cash['funding_usd'] is None
    s=assess_request(tick([x]),initialized())['state_after'];event=terminal(x,expected=[end])
    new=op(tick=end)
    result=advance(s,end,terminals=[event],xs=[new])
    a=result['state_after']['arms']['RAW_SAFE']
    assert a['closed'][x.id]['status']=='FUNDING_UNKNOWN'
    assert a['closed'][x.id]['net_usd'] is None
    assert x.id not in a['positions'] and new.id in a['positions']
    assert a['realized_equity_usd']=='1000'
    assert result['funding_coverage']['status']=='BLOCKED_DATA'
    assert result['funding_coverage']['arms']['RAW_SAFE']['unknown_slot_hours']=='1'
    assert Decimal(result['funding_coverage']['arms']['RAW_SAFE']['unknown_risk_usd'])==5
    assert x.id in s['arms']['RAW_SAFE']['positions']


@pytest.mark.parametrize('mutation', ['no_calendar','no_source','at_entry','beyond_release','duplicate','unknown_rate','future_rate'])
def test_incomplete_or_conflicting_funding_cannot_assert_empty_known_cost(mutation):
    x=op();end=NOW+HOUR;f=funding(x,end,[end],[(end,'.001')])
    if mutation=='no_calendar':f.pop('calendar_complete')
    elif mutation=='no_source':f['source_hash']=None
    elif mutation=='at_entry':f['expected_settlements']=[NOW]
    elif mutation=='beyond_release':f['expected_settlements']=[end+1]
    elif mutation=='duplicate':f['rates']*=2
    elif mutation=='unknown_rate':f['rates'][0]['rate']=None
    else:f['rates'][0]['available_ms']=end+1
    if mutation in ('unknown_rate','future_rate'):
        assert funding_summary(f,x,end,end)['status']=='FUNDING_UNKNOWN'
    else:
        with pytest.raises(BrainBlocked):funding_summary(f,x,end,end)


def test_known_no_settlement_requires_explicit_calendar_and_proves_zero_sum():
    x=op();end=NOW+HOUR
    assert funding_summary(funding(x,end),x,end,end)['rate_sum']=='0'


def test_a4_late_funding_cannot_retroactively_credit_equity():
    x=op();end=NOW+HOUR;s=assess_request(tick([x]),initialized())['state_after']
    result=advance(s,end,terminals=[terminal(x,expected=[end])])
    late=terminal(x,expected=[end],rates=[(end,'.001')])
    with pytest.raises(BrainBlocked,match='duplicate_terminal'):
        assess_request(tick(at=end+TICK,terminals=[late]),result['state_after'])
    assert result['state_after']['arms']['RAW_SAFE']['realized_equity_usd']=='1000'


def test_exact_five_percent_is_allowed_over_five_blocks_any_arm_empty_is_pending():
    counts={arm:{'evaluated':20,'funding_unknown':1} for arm in ('RAW_SAFE','FOUNDATION','BRAIN_DET')}
    assert funding_population_status(counts)['status']=='FUNDING_COVERAGE_PASS'
    counts['BRAIN_DET']['evaluated']=19
    result=funding_population_status(counts)
    assert result['status']=='BLOCKED_DATA' and result['blocked_arms']==['BRAIN_DET']
    counts['BRAIN_DET']={'evaluated':0,'funding_unknown':0}
    assert funding_population_status(counts)['status']=='PENDING_POPULATION'


def test_known_context_cannot_use_next_hour_in_15m_batch():
    x=op(sleeve='ETS2',tick=NOW+TICK);req=tick([x],NOW+TICK)
    req['contexts']=build_contexts([x],hour_ms=NOW+HOUR,btc_h4=None,symbol_h1={})
    s=advance(initialized(),NOW)['state_after']
    with pytest.raises(BrainBlocked,match='context'):assess_request(req,s)


def test_caps_order_and_negative_scoring_remain_frozen():
    xs=[op(i,sleeve='BOUNCE1',side='short' if i%2 else 'long') for i in range(5)]+[op(9,sleeve='ASR1')]
    result=assess_request(tick(xs),initialized())
    assert len(result['state_after']['arms']['RAW_SAFE']['positions'])==6
    assert sum(d['accepted'] for d in result['decisions']['FOUNDATION'])==5
    assert any(d['reason']=='sleeve_cap' for d in result['decisions']['FOUNDATION'])
    assert all(.5<=d['multiplier']<=1.5 for d in result['decisions']['BRAIN_DET'])


def test_global_decimal_settings_cannot_change_receipts():
    req=tick([op()]);state=initialized()
    a=assess_request(req,state)
    with localcontext() as c:
        c.prec=8;b=assess_request(req,state)
    assert a==b


def test_a3_atomic_restart_duplicate_and_cross_version_rejection(tmp_path):
    root=tmp_path/'a3';x=op()
    with BrainJournal(root) as j:
        j.process(init());first=j.process(tick([x]))
        for at in range(NOW+TICK,NOW+HOUR,TICK):j.process(tick(at=at))
        last=j.process(tick(at=NOW+HOUR,terminals=[terminal(x)]))
    with BrainJournal(root) as j:
        assert j.process(tick([x]))==first
        assert j.process(tick(at=NOW+HOUR,terminals=[terminal(x)]))==last
        assert j.state==last['state_after']
    from research_lab.os2_shadow_bridge import BridgeBlocked
    with pytest.raises(BridgeBlocked):A1Journal(root)


def test_tick_gap_and_unknown_authority_block_without_mutation():
    s=initialized();req=tick([op()]);req['batch_complete']=False
    with pytest.raises(BrainBlocked):assess_request(req,s)
    req=tick(at=NOW+TICK)
    with pytest.raises(BrainBlocked,match='tick_sequence'):assess_request(req,s)
    assert not any(a['positions'] for a in s['arms'].values())
