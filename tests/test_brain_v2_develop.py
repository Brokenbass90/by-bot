from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from research_lab.brain_v2_frozen_primitives import BrainBlocked, Opportunity, canonical
from research_lab.brain_v2_sources import EntryProjection
from research_lab.brain_v2_a3 import COST_MODEL, HOUR, TICK
from research_lab.brain_v2_develop import (
    FoldTable, FundingA6, DevelopEngine, START, END, FOLDS, Outcome,
)

BASE=Path('reports/evidence/brain_v2_develop_20261012')
PIN='a'*64


def tables():
    pub=json.loads((BASE/'TABLE_HASH_PUBLICATION.json').read_bytes())
    return tuple(FoldTable(Path(r['path']).read_bytes(),expected_pin=r['sha256'],
                           cutoff=r['cutoff']) for r in pub['tables'])


def entry(i=0,at=START,sleeve='ATT1',side='short'):
    bar=TICK if sleeve in ('ETS2','SF3') else HOUR
    return EntryProjection(Opportunity(sleeve,f'COIN{i}USDT',side,at-bar,at,
        'next_open',.02,336,COST_MODEL,PIN),50)


def known(rate='.001'):
    return dict(status='KNOWN',rate_sum=rate,reason='A6_COVERED',source_hash=PIN)


def outcome(hours=1,R=1,funding=None):
    return Outcome(hours,R,known('0') if funding is None else funding)


def fund(rows=None):
    ts=[START+(i-12)*HOUR for i in range(30)]
    raw=canonical(dict(symbol='COIN0USDT',funding=[[t,.001] for t in ts] if rows is None else rows))
    return FundingA6(raw,source_hash=hashlib.sha256(raw).hexdigest(),symbol='COIN0USDT')


def test_fold_tables_exact_pins_and_missing_sigma_is_A6_cold_start():
    t=tables()
    for i in [0,1]:
        s=t[i].score('ETS2','BEAR','HIGH',at_ms=FOLDS[i][0])
        assert s['z']==0 and s['multiplier']==1 and s['cold_start'] is True
    assert t[2].score('ETS2','UNKNOWN','UNKNOWN',at_ms=FOLDS[2][0])['cold_start'] is False
    with pytest.raises(BrainBlocked,match='table_cutoff'):
        t[2].score('ETS2','UNKNOWN','UNKNOWN',at_ms=START)
    with pytest.raises(BrainBlocked,match='table_pin'):
        FoldTable(t[0].raw+b' ',expected_pin=t[0].source_hash,cutoff='2023-07-01')


def test_calendar_exact_entry_exclusion_release_inclusion_and_past_ten_intervals():
    x=fund().summary(start_ms=START,end_ms=START+2*HOUR)
    assert x['status']=='KNOWN' and Decimal(x['rate_sum'])==Decimal('.002')
    assert x['baseline_gap_ms']==HOUR and x['settlement_count']==2
    # An empty held interval between covered calculations is genuinely zero.
    x=fund().summary(start_ms=START+1,end_ms=START+HOUR-1)
    assert x['status']=='KNOWN' and Decimal(x['rate_sum'])==0


@pytest.mark.parametrize('mutation,reason',[
    ('missing','missing_file'),('few','insufficient_history'),
    ('left','outside_archive'),('right','outside_archive'),
    ('gap','calendar_gap'),('boundary_gap','calendar_gap'),('nonfinite','nonfinite_rate')])
def test_A6_unknown_is_whole_trade_with_exact_reason(mutation,reason):
    rows=[[START+(i-12)*HOUR,.001] for i in range(30)]
    if mutation=='missing':archive=FundingA6(None,source_hash=None,symbol='COIN0USDT')
    else:
        if mutation=='few':rows=rows[4:]
        elif mutation=='left':rows=rows[13:]
        elif mutation=='right':rows=rows[:14]
        elif mutation=='gap':rows=[r for r in rows if r[0]!=START+HOUR]
        elif mutation=='boundary_gap':rows=[r for r in rows if r[0]!=START+3*HOUR]
        elif mutation=='nonfinite':rows[13][1]=None
        archive=fund(rows)
    end=START+2*HOUR+TICK if mutation=='boundary_gap' else START+2*HOUR
    x=archive.summary(start_ms=START,end_ms=end)
    assert x['status']=='FUNDING_UNKNOWN' and x['rate_sum'] is None and x['reason']==reason


def test_funding_step_increase_unknown_step_decrease_covered():
    earlier=[[START+(i-12)*HOUR,.001] for i in range(13)]
    slow=earlier+[[START+2*HOUR,.001],[START+4*HOUR,.001]]
    fast=earlier+[[START+TICK*i,.001] for i in range(1,9)]
    assert fund(slow).summary(start_ms=START,end_ms=START+2*HOUR)['status']=='FUNDING_UNKNOWN'
    assert fund(fast).summary(start_ms=START,end_ms=START+2*HOUR)['status']=='KNOWN'


def test_future_intervals_cannot_change_past_median():
    rows=[[START+(i-12)*HOUR,.001] for i in range(13)]
    rows+=[[START+2*HOUR,.001],[START+4*HOUR,.001],[START+6*HOUR,.001]]
    x=fund(rows).summary(start_ms=START,end_ms=START+HOUR)
    assert x['baseline_gap_ms']==HOUR and x['status']=='FUNDING_UNKNOWN'


def test_dd_env_before_packet_uses_future_R_only_as_diagnostic():
    def run(R):
        engine=DevelopEngine(tables());x=entry()
        engine.step(START,[x],{x.opportunity.id:('UNKNOWN','UNKNOWN')},
                    {x.opportunity.id:outcome(R=R)})
        y=entry(1,at=START+TICK,sleeve='ETS2')
        result=engine.step(START+TICK,[y],{y.opportunity.id:('UNKNOWN','UNKNOWN')},
                          {y.opportunity.id:outcome(R=2)})
        return engine,result
    positive,a=run(2);negative,b=run(-3)
    assert a['decisions']==b['decisions']
    assert a['ticks']['RAW_SAFE']['env_usd']=='99500'
    assert b['ticks']['RAW_SAFE']['env_usd']=='98500'
    assert positive.arms['RAW_SAFE']['equity']==negative.arms['RAW_SAFE']['equity']==Decimal(100000)


def test_unknown_cash_frees_risk_and_is_excluded_from_dd_env():
    engine=DevelopEngine(tables());x=entry()
    unknown=dict(status='FUNDING_UNKNOWN',rate_sum=None,reason='missing_file',source_hash=None)
    engine.step(START,[x],{x.opportunity.id:('UNKNOWN','UNKNOWN')},
                {x.opportunity.id:outcome(R=-20,funding=unknown)})
    result=engine.step(START+TICK,[],{}, {})
    assert result['ticks']['RAW_SAFE']['env_usd']=='100000'
    for at in range(START+2*TICK,START+HOUR+1,TICK):result=engine.step(at,[],{},{})
    raw=engine.arms['RAW_SAFE']
    assert not raw['positions'] and raw['equity']==Decimal(100000)
    closed,=result['closed']['RAW_SAFE']
    assert closed['net_usd'] is None and closed['status']=='FUNDING_UNKNOWN'
    assert raw['unknown_by_reason']=={'missing_file':1}


def test_release_precedes_entry_and_cost_does_not_double_subtract_commission():
    engine=DevelopEngine(tables());x=entry(side='long')
    engine.step(START,[x],{x.opportunity.id:('UNKNOWN','UNKNOWN')},
                {x.opportunity.id:outcome(R=1,funding=known('.001'))})
    for at in range(START+TICK,START+HOUR,TICK):engine.step(at,[],{},{})
    y=entry(at=START+HOUR)
    result=engine.step(START+HOUR,[y],{y.opportunity.id:('UNKNOWN','UNKNOWN')},
                       {y.opportunity.id:outcome(R=1)})
    assert engine.arms['RAW_SAFE']['equity']==Decimal('100465') #500R -10 slip -25 funding
    assert result['decisions'][y.opportunity.id]['RAW_SAFE']['risk_usd']=='502.325'


def test_fold_switch_preserves_capital_positions_and_entry_attribution():
    engine=DevelopEngine(tables());boundary=FOLDS[1][0]
    for at in range(START,boundary-HOUR,TICK):engine.step(at,[],{},{})
    x=entry(at=boundary-HOUR)
    engine.step(boundary-HOUR,[x],{x.opportunity.id:('UNKNOWN','UNKNOWN')},
                {x.opportunity.id:outcome(hours=2,R=1)})
    for at in range(boundary-HOUR+TICK,boundary+HOUR+1,TICK):result=engine.step(at,[],{},{})
    raw=engine.arms['RAW_SAFE']
    assert raw['equity']==Decimal('100490')
    assert raw['fold_net'][0]==Decimal(490) and raw['fold_net'][1]==0
    closed,=result['closed']['RAW_SAFE'];assert closed['entry_fold']==0


def test_closed_only_tail_can_drain_without_new_entries_and_end_fold_changes():
    engine=DevelopEngine(tables())
    for at in range(START,END-HOUR,TICK):engine.step(at,[],{},{})
    x=entry(at=END-HOUR)
    engine.step(END-HOUR,[x],{x.opportunity.id:('UNKNOWN','UNKNOWN')},
                {x.opportunity.id:outcome(hours=2,R=1)})
    for at in range(END-HOUR+TICK,END+HOUR+1,TICK):result=engine.step(at,[],{},{})
    assert result['closed']['RAW_SAFE'][0]['entry_fold']==3
    with pytest.raises(BrainBlocked,match='new_entry_after_end'):
        y=entry(at=END+HOUR+TICK,sleeve='ETS2')
        engine.step(END+HOUR+TICK,[y],{y.opportunity.id:('UNKNOWN','UNKNOWN')},
                    {y.opportunity.id:outcome()})


def test_cold_start_leg_is_admitted_to_all_arms_with_unit_multiplier():
    engine=DevelopEngine(tables());x=entry(sleeve='ETS2')
    result=engine.step(START,[x],{x.opportunity.id:('BULL','HIGH')},
                       {x.opportunity.id:outcome()})
    for arm,d in result['decisions'][x.opportunity.id].items():
        assert d['accepted'] is True and Decimal(d['risk_usd'])==500
    assert result['decisions'][x.opportunity.id]['BRAIN_DET']['multiplier']==1


def test_unknown_exactly_five_percent_is_allowed_strictly_greater_blocked():
    engine=DevelopEngine(tables())
    for a in engine.arms.values():a['closed_count']=20;a['unknown_count']=1
    assert engine.report()['status']!='BLOCKED_DATA'
    engine.arms['RAW_SAFE']['unknown_count']=2
    assert engine.report()['status']=='BLOCKED_DATA'


def test_duplicate_tick_or_missing_quarter_cannot_advance_state():
    engine=DevelopEngine(tables());engine.step(START,[],{},{})
    with pytest.raises(BrainBlocked,match='tick_continuity'):engine.step(START,[],{},{})
    with pytest.raises(BrainBlocked,match='tick_continuity'):engine.step(START+2*TICK,[],{},{})


def test_shared_source_input_cannot_mutate_the_three_accepted_ledgers():
    engine=DevelopEngine(tables());x=entry();f=known('0')
    engine.step(START,[x],{x.opportunity.id:('UNKNOWN','UNKNOWN')},
                {x.opportunity.id:outcome(funding=f)})
    f.update(status='FUNDING_UNKNOWN',rate_sum=None,reason='missing_file')
    result=engine.step(START+TICK,[],{},{})
    assert result['ticks']['RAW_SAFE']['env_usd']=='99500'
    funds=[a['positions'][x.opportunity.id]['funding'] for a in engine.arms.values()]
    assert len({id(d) for d in funds})==3
    assert all(d['status']=='KNOWN' for d in funds)
