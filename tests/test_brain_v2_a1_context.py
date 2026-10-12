from dataclasses import replace
import hashlib
from pathlib import Path

import pytest

from research_lab.brain_v2_frozen_primitives import BrainBlocked, Opportunity, RegimeBar
from research_lab.brain_v2_a1 import HOUR, TABLE_PIN, load_table, score_a1, vol_context

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT/'reports/evidence/brain_v2_a2_20261012/frozen/research_lab/brain_v2/MU_SIGMA_V1.json'
NOW = 1_790_000*HOUR
PIN = 'a'*64


def bars(n=2173):
    # First TR=2 then TR=2: exact constant Wilder NATR, ties -> p=50.
    return tuple(RegimeBar(NOW-(n-i)*HOUR, 100., 101., 99., 100., 1.,
                          NOW-(n-i-1)*HOUR) for i in range(n))


def opportunity(sleeve='BOUNCE1'):
    return Opportunity(sleeve,'BTCUSDT','long',NOW-1,NOW,'next_open',.02,48,'FROZEN_6_2_F1',PIN)


def test_pinned_table_load_and_exact_shrinkage_with_explicit_empty_cell():
    table=load_table(TABLE.read_bytes())
    s=score_a1(opportunity(),table,'BULL','MID')
    mu_s=151*.07065714569536427/(151+300)
    assert s.mu_s==pytest.approx(mu_s)
    row=__import__('json').loads(TABLE.read_bytes())['nogi']['BOUNCE1']['cells']['BULL_TREND|MID']
    assert s.mu_context==pytest.approx((row['n']*row['mean']+150*mu_s)/(row['n']+150))
    assert s.multiplier==pytest.approx(1+4*s.z)
    # This frozen exhaustive table omits BULL|LOW: n=0 is justified by n accounting.
    assert score_a1(opportunity(),table,'BULL','LOW').mu_context==pytest.approx(mu_s)
    assert score_a1(opportunity(),table,'UNKNOWN','HIGH').mu_context==pytest.approx(mu_s)


def test_table_hash_conflict_missing_sleeve_and_pre_cutoff_decision_block():
    with pytest.raises(BrainBlocked,match='table_pin'): load_table(TABLE.read_bytes()+b' ')
    table=load_table(TABLE.read_bytes())
    with pytest.raises(BrainBlocked,match='statistics_sleeve'): score_a1(opportunity('UNAPPROVED'),table,'BULL','MID')
    with pytest.raises(BrainBlocked,match='cutoff'):
        score_a1(replace(opportunity(),t_signal=1,t_available=1),table,'BULL','MID')
    assert hashlib.sha256(TABLE.read_bytes()).hexdigest()==TABLE_PIN


def test_wilder_seed_full_window_and_midrank_ties():
    result=vol_context(bars(),hour_ms=NOW,source_hash=PIN)
    assert result['vol']=='MID'
    assert result['percentile']==50.
    assert result['natr']==pytest.approx(.02)
    assert result['window_count']==2160
    assert result['source_hash']==PIN
    assert result['orders_allowed'] is False


@pytest.mark.parametrize('fault',['short','missing_last','gap','future_receive','nan','duplicate','geometry','bad_pin'])
def test_unknown_vol_never_becomes_neutral_or_zero(fault):
    xs=list(bars()); pin=PIN
    if fault=='short': xs=xs[1:]
    if fault=='missing_last': xs=xs[:-1]
    if fault=='gap': del xs[-100]
    if fault=='future_receive': xs[-1]=replace(xs[-1],available_ms=NOW+1)
    if fault=='nan': xs[-1]=replace(xs[-1],c=float('nan'))
    if fault=='duplicate': xs[-100]=xs[-101]
    if fault=='geometry': xs[-1]=replace(xs[-1],h=90)
    if fault=='bad_pin': pin='unknown'
    result=vol_context(xs,hour_ms=NOW,source_hash=pin)
    assert result['vol']=='UNKNOWN'
    assert 'percentile' not in result


def test_wilder_recursive_value_differs_from_simple_rolling_mean():
    xs=list(bars()); xs[-1]=replace(xs[-1],h=102.,l=98.)
    result=vol_context(xs,hour_ms=NOW,source_hash=PIN)
    assert result['natr']==pytest.approx(((13*2+4)/14)/100)
    assert result['vol']=='HIGH'
    assert result['percentile']==pytest.approx(100*(2159+.5)/2160)
