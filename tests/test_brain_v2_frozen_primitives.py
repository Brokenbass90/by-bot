from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import math
from pathlib import Path

import pytest

from research_lab.brain_v2_frozen_primitives import (
    BrainBlocked, Opportunity, FrozenStats, CellStats, score, rank,
    RegimeBar, regime_context, vol_category, PortfolioLeg, assess_portfolio,
    primitive_receipt, verify_frozen_sources,
)

H = 3600000
PIN = 'a'*64
FROZEN = 1759276800000
NOW = FROZEN + 300*H


def op(symbol='BTCUSDT', sleeve='BOUNCE1', available=NOW):
    return Opportunity(sleeve, symbol, 'long', available-1, available,
                       'next_open', .02, 48, 'FROZEN_6_2_F1', PIN)


def stats():
    return FrozenStats('BOUNCE1', 300, .4, 2.,
                       tuple(CellStats(r,v,150 if (r,v)==('BULL','MID') else 0,.6 if (r,v)==('BULL','MID') else 0)
                             for r in ('BULL','BEAR','NEUTRAL') for v in ('LOW','MID','HIGH')),
                       FROZEN, FROZEN-1, PIN)


def test_opportunity_is_immutable_and_hashes_all_frozen_fields():
    x=op()
    with pytest.raises(FrozenInstanceError): x.symbol='ETHUSDT'
    assert x.id == op().id
    assert x.id != replace(x, max_hold_h=49).id
    assert x.id != replace(x, source_hash='b'*64).id
    assert x.batch_hour == NOW//H


@pytest.mark.parametrize('field,value', [('stop_distance_frac',0),('stop_distance_frac',float('nan')),
    ('t_available',NOW-2),('side','buy'),('source_hash','unknown'),('max_hold_h',-1)])
def test_invalid_opportunity_fails_before_assessment(field,value):
    with pytest.raises(BrainBlocked): replace(op(),**{field:value})


def test_exact_shrinkage_scoring_and_frozen_multiplier():
    s=score(op(),stats(),'BULL','MID')
    # mu_s=.2; mu_sc=(150*.6+150*.2)/300=.4; z=.2; 1+4*z=1.8 ->1.5
    assert s.mu_s == pytest.approx(.2)
    assert s.mu_context == pytest.approx(.4)
    assert s.z == pytest.approx(.2)
    assert s.multiplier == 1.5


@pytest.mark.parametrize('regime,vol', [('UNKNOWN','MID'),('BULL','UNKNOWN'),('UNKNOWN','UNKNOWN')])
def test_unknown_context_is_sleeve_fallback_not_zero_or_veto(regime,vol):
    s=score(op(),stats(),regime,vol)
    assert s.mu_context == pytest.approx(.2)
    assert s.z == pytest.approx(.1)
    assert s.multiplier == pytest.approx(1.4)
    assert s.context_status == 'UNKNOWN_SLEEVE_FALLBACK'


def test_unobserved_known_cell_shrinks_to_sleeve_and_negative_score_is_not_veto():
    assert score(op(),stats(),'BEAR','LOW').mu_context == pytest.approx(.2)
    negative=replace(stats(),mean_r=-.4,cells=tuple(replace(c,n=0,mean_r=0) for c in stats().cells))
    s=score(op(),negative,'BEAR','LOW')
    assert s.z < 0 and s.multiplier == pytest.approx(.6)
    assert rank([op('ETHUSDT'),op()],{'BOUNCE1':negative},'BEAR','LOW','BRAIN_DET')


@pytest.mark.parametrize('change', [{'sigma_r':0},{'sigma_r':float('nan')},{'last_outcome_available_ms':FROZEN+1},
                                 {'frozen_at_ms':NOW+1},{'source_hash':'UNKNOWN'}])
def test_unsafe_or_unfrozen_statistics_rejected(change):
    with pytest.raises(BrainBlocked): score(op(),replace(stats(),**change),'BULL','MID')


def test_ranking_uses_earliest_available_then_id_not_existing_router_recent_first():
    xs=[op('ETHUSDT',available=NOW+1),op(),op('SOLUSDT')]
    out=rank(xs,{'BOUNCE1':stats()},'UNKNOWN','UNKNOWN','BRAIN_DET')
    assert out[0].t_available==NOW and out[-1].t_available==NOW+1
    assert [x.id for x in out[:2]] == sorted(x.id for x in xs if x.t_available==NOW)
    assert rank(xs,{},'UNKNOWN','UNKNOWN','RAW_SAFE') == rank(xs,{},'UNKNOWN','UNKNOWN','FOUNDATION')
    with pytest.raises(BrainBlocked): rank([op(),op()],{},'UNKNOWN','UNKNOWN','RAW_SAFE')


def bars(n=60):
    end=NOW//(4*H)*(4*H)
    return [RegimeBar(end-(n-i)*4*H,100+i,102+i,99+i,101+i,5,
                      end-(n-i-1)*4*H) for i in range(n)]


def test_regime_matches_pinned_existing_math_only_on_closed_causal_source():
    from bot.regime_orchestrator import compute_regime
    xs=bars()
    result=regime_context(xs,NOW,PIN)
    expected=compute_regime([[x.open_ms,x.o,x.h,x.l,x.c,x.v] for x in xs])['regime']
    assert result['regime']=={'BULL_TREND':'BULL','BEAR_TREND':'BEAR','NEUTRAL':'NEUTRAL'}[expected]
    assert result['orders_allowed'] is False


@pytest.mark.parametrize('fault', ['short','gap','future','unavailable','duplicate','missing_latest','pin','nan'])
def test_bad_regime_source_is_explicit_unknown(fault):
    xs=bars(); pin=PIN
    if fault=='short':xs=xs[:-1]
    if fault=='gap':xs=xs[:10]+xs[11:]
    if fault=='future':xs[-1]=replace(xs[-1],open_ms=NOW)
    if fault=='unavailable':xs[-1]=replace(xs[-1],available_ms=NOW+1)
    if fault=='duplicate':xs[-1]=xs[-2]
    if fault=='missing_latest':xs=[replace(x,open_ms=x.open_ms-4*H,available_ms=x.available_ms-4*H) for x in xs]
    if fault=='pin':pin=None
    if fault=='nan':xs[-1]=replace(xs[-1],c=float('nan'))
    result=regime_context(xs,NOW,pin)
    assert result['regime']=='UNKNOWN' and result['reason']


@pytest.mark.parametrize('pct,expected', [(0,'LOW'),(32.99,'LOW'),(33,'MID'),(67,'MID'),(67.01,'HIGH'),(100,'HIGH')])
def test_vol_frozen_category_boundaries(pct,expected):
    assert vol_category(pct,observed_ms=NOW,as_of_ms=NOW,method_pin=PIN)['vol']==expected


@pytest.mark.parametrize('pct,stamp,pin', [(None,NOW,PIN),(-1,NOW,PIN),(101,NOW,PIN),(float('nan'),NOW,PIN),
                                         (20,NOW+1,PIN),(20,NOW,None)])
def test_missing_or_future_vol_estimator_remains_unknown(pct,stamp,pin):
    assert vol_category(pct,observed_ms=stamp,as_of_ms=NOW,method_pin=pin)['vol']=='UNKNOWN'


def leg(symbol,sleeve,side,risk=5):
    return PortfolioLeg(symbol,sleeve,side,risk,PIN)


def test_literal_caps_expose_cold_start_and_single_sleeve_conflict():
    single=[leg('BTCUSDT','BOUNCE1','long')]
    assert assess_portfolio(single,1000,'RAW_SAFE',protection_known=True)['status']=='PROPOSED_PORTFOLIO_FEASIBLE'
    for arm in ('FOUNDATION','BRAIN_DET'):
        r=assess_portfolio(single,1000,arm,protection_known=True)
        assert {'sleeve_share_cap','net_direction_cap'}<=set(r['violations'])
    balanced=[leg('BTCUSDT','A','long'),leg('ETHUSDT','B','short'),leg('SOLUSDT','C','long')]
    assert assess_portfolio(balanced,1000,'FOUNDATION',protection_known=True)['status']=='PROPOSED_PORTFOLIO_FEASIBLE'
    only_bounce=[leg(x,'BOUNCE1','long') for x in ('BTCUSDT','ETHUSDT')]
    assert assess_portfolio(only_bounce,1000,'FOUNDATION',protection_known=True)['status']=='PROPOSED_PORTFOLIO_REJECT'


def test_caps_reject_unknown_and_never_change_caps_or_sizing():
    for equity,protected in [(None,True),(1000,None),(0,True)]:
        assert assess_portfolio([],equity,'RAW_SAFE',protection_known=protected)['status']=='BLOCKED_DATA'
    assert assess_portfolio(None,1000,'RAW_SAFE',protection_known=True)['status']=='BLOCKED_DATA'
    assert 'total_open_risk_cap' in assess_portfolio([leg('BTCUSDT','A','long',61)],1000,'RAW_SAFE',protection_known=True)['violations']
    assert 'symbol_cap' in assess_portfolio([leg('BTCUSDT','A','long'),leg('BTCUSDT','B','short')],1000,'RAW_SAFE',protection_known=True)['violations']
    assert 'position_cap' in assess_portfolio([leg(str(i),'A','long',1) for i in range(13)],1000,'RAW_SAFE',protection_known=True)['violations']


def test_receipt_is_identical_and_explicitly_has_no_integrated_allocator_authority():
    r=primitive_receipt(op(),stats(),'BULL','MID',1000)
    assert r==primitive_receipt(op(),stats(),'BULL','MID',1000)
    assert set(r['arms'])=={'RAW_SAFE','FOUNDATION','BRAIN_DET'}
    assert r['orders_allowed'] is False and r['status']=='BLOCKED_DATA'
    assert r['arms']['RAW_SAFE']['risk_usd']==5
    assert r['arms']['BRAIN_DET']['risk_usd']==7.5
    assert r['arms']['BRAIN_DET']['notional_usd']==375
    assert r['sha256']==hashlib.sha256(json.dumps({k:v for k,v in r.items() if k!='sha256'},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def test_snapshot_source_pins_are_exact_and_tamper_fails(tmp_path):
    manifest=Path('reports/evidence/brain_bounce_intake_20261011/source_manifest.json')
    assert verify_frozen_sources(manifest)['verified_files']==5
    d=json.loads(manifest.read_text()); d['files'][0]['sha256']='b'*64
    p=tmp_path/'manifest.json';p.write_text(json.dumps(d))
    with pytest.raises(BrainBlocked): verify_frozen_sources(p,root=Path.cwd())


def test_missing_statistics_cell_is_not_inferred_as_zero_observations():
    with pytest.raises(BrainBlocked): score(op(),replace(stats(),cells=()),'BULL','MID')
    assert score(op(),replace(stats(),cells=()),'UNKNOWN','UNKNOWN').context_status=='UNKNOWN_SLEEVE_FALLBACK'


def test_statistics_cannot_consume_post_develop_outcomes_even_if_frozen_later():
    with pytest.raises(BrainBlocked):
        score(op(),replace(stats(),frozen_at_ms=NOW-1,last_outcome_available_ms=FROZEN+H),'BULL','MID')


def test_exact_sleeve_and_direction_boundary_has_no_float_epsilon():
    xs=[leg('A','A','long',4),leg('B','B','long',4),leg('C','C','short',2)]
    r=assess_portfolio(xs,1000,'FOUNDATION',protection_known=True)
    assert r['status']=='PROPOSED_PORTFOLIO_FEASIBLE'
    r=assess_portfolio([replace(xs[0],risk_usd=4.000001),*xs[1:]],1000,'FOUNDATION',protection_known=True)
    assert 'sleeve_share_cap' in r['violations'] and 'net_direction_cap' in r['violations']


@pytest.mark.parametrize('data',[None,[None],{}])
def test_missing_or_malformed_regime_collection_is_explicit_unknown(data):
    assert regime_context(data,NOW,PIN)['regime']=='UNKNOWN'


def test_malformed_position_collection_is_explicit_blocked_not_zero_exposure():
    assert assess_portfolio([None],1000,'RAW_SAFE',protection_known=True)['status']=='BLOCKED_DATA'


def test_opportunity_symbol_is_not_silently_restricted_to_ascii_universe():
    x=op(symbol='币安人生USDT')
    assert x.symbol=='币安人生USDT' and x.id!=op().id
    assert assess_portfolio([leg(x.symbol,'A','long')],1000,'RAW_SAFE',protection_known=True)['status']=='PROPOSED_PORTFOLIO_FEASIBLE'
