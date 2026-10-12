from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from research_lab.brain_v2_frozen_primitives import ARMS, BrainBlocked
from research_lab.brain_v2_develop import START, TICK, DATES, FOLDS
from research_lab.brain_v2_v1_1_a7 import (
    A7Table, DevelopEngineV11, feasibility, run_once_authorized, OWNER_GO,
)
from tests.test_brain_v2_develop import entry, outcome

BASE=Path('reports/evidence/brain_v2_v1_1_20261012')


def tables():
    pub=json.loads((BASE/'TABLE_HASH_PUBLICATION.json').read_bytes())
    rows={Path(r['path']).name:r for r in pub['files']}
    return tuple(A7Table(Path(rows['MU_SIGMA_V1_A7_fold_'+d+'.json']['path']).read_bytes(),
        expected_pin=rows['MU_SIGMA_V1_A7_fold_'+d+'.json']['sha256'],cutoff=d) for d in DATES)


@pytest.mark.parametrize('lev,expected',[(100.,None),(100.01,'infeasible_stop_lev'),(165060,'infeasible_stop_lev')])
def test_frozen_boundary_and_grass(lev,expected):
    assert feasibility(replace(entry(sleeve='SF3'),lev=lev))==expected


def test_grass_is_rejected_all_arms_before_context_outcome_or_allocator():
    e=replace(entry(sleeve='SF3'),lev=165060)
    engine=DevelopEngineV11(tables())
    result=engine.step(START,[e],{}, {})
    for arm in ARMS:
        assert result['decisions'][e.opportunity.id][arm]['reason']=='infeasible_stop_lev'
        assert not engine.arms[arm]['positions'] and engine.arms[arm]['accepted']==0
    assert engine.report()['infeasible_stop_lev_by_sleeve_fold']=={'0|SF3':1}
    with pytest.raises(BrainBlocked,match='duplicate'):
        engine.step(START+TICK,[e],{}, {})


def test_exact_already_sealed_grass_source_row_is_rejected():
    # Read only the already-consumed V1 incident receipt, not any new outcomes.
    raw=Path('reports/evidence/brain_v2_develop_20261012/run_a5_a6/'
        'PARTIAL_CAPITAL_RECONCILIATION.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='71c86059b4b9f1024e6443d3c68f1793767129942622d2b88306856c11350481'
    released=json.loads(raw)['first_unsaved_release_arithmetic']['BRAIN_DET']['due_releases']
    case=next(r for r in released if r['source_row']['sym']=='GRASSUSDT')
    row=case['source_row'];at=case['entry_ms']
    assert row['leg']=='SF3' and row['lev']==165060.0 and row['ts']==1744033500000
    e=replace(entry(at=at,sleeve=row['leg'],side=row['side']),lev=row['lev'])
    e=replace(e,opportunity=replace(e.opportunity,symbol=row['sym'],t_signal=row['ts']))
    engine=DevelopEngineV11(tables())
    engine.last_tick=at-TICK  # Empty synthetic preceding tick; not a historical replay.
    result=engine.step(at,[e],{}, {})
    assert all(result['decisions'][e.opportunity.id][arm]['reason']=='infeasible_stop_lev' for arm in ARMS)


def test_exact100_allocates_and_10001_never_reaches_scoring():
    good=replace(entry(),lev=100.)
    bad=replace(entry(1,sleeve='SF3'),lev=100.01)
    engine=DevelopEngineV11(tables())
    result=engine.step(START,[bad,good],{good.opportunity.id:('UNKNOWN','UNKNOWN')},
                       {good.opportunity.id:outcome()})
    for arm in ARMS:
        assert result['decisions'][good.opportunity.id][arm]['accepted']
        assert not result['decisions'][bad.opportunity.id][arm]['accepted']
        assert engine.arms[arm]['accepted']==1
    assert all(float(x)<=6 for x in engine.report()['max_open_notional_over_equity'].values())


def test_cold_start_and_exact_table_pins_preserved():
    all_tables=tables()
    for i in (0,1):
        for sleeve in ('ETS2','SF3'):
            score=all_tables[i].score(sleeve,'UNKNOWN','UNKNOWN',at_ms=FOLDS[i][0])
            assert score['cold_start'] and score['z']==0 and score['multiplier']==1.
    with pytest.raises(BrainBlocked,match='table_pin'):
        A7Table(all_tables[0].raw+b' ',expected_pin=all_tables[0].source_hash,cutoff=DATES[0])
    tampered=json.loads(all_tables[0].raw);tampered['exec_feasibility']['max_lev']=101
    raw=json.dumps(tampered).encode()
    with pytest.raises(BrainBlocked,match='A7'):
        A7Table(raw,expected_pin=hashlib.sha256(raw).hexdigest(),cutoff=DATES[0])


@pytest.mark.parametrize('lev',[True,0,float('nan'),float('inf')])
def test_unknown_or_invalid_lev_never_becomes_zero_or_clamped(lev):
    with pytest.raises(BrainBlocked,match='lev_unknown'):
        feasibility(replace(entry(),lev=lev))


def test_infeasible_population_preserves_causal_source_timing_checks():
    x=replace(entry(sleeve='SF3'),lev=165060)
    x=replace(x,opportunity=replace(x.opportunity,t_signal=x.opportunity.t_signal-TICK))
    with pytest.raises(BrainBlocked,match='opportunity_tick'):
        DevelopEngineV11(tables()).step(START,[x],{}, {})


def test_release_cash_and_sf3_diagnostics_use_unchanged_A3_costs():
    x=replace(entry(sleeve='SF3'),lev=100.)
    engine=DevelopEngineV11(tables())
    engine.step(START,[x],{x.opportunity.id:('UNKNOWN','UNKNOWN')},{x.opportunity.id:outcome()})
    for i in range(1,5):engine.step(START+i*TICK,[],{}, {})
    report=engine.report()
    for arm in ARMS:
        assert report['arms'][arm]['final_realized_usd']=='100480'
        assert report['sf3_contribution'][arm]['net_usd']=='480'
        assert report['sf3_contribution'][arm]['fraction_of_arm_net']=='1'
        assert not engine.arms[arm]['positions']


def test_no_go_creates_no_run_and_no_driver(tmp_path):
    output=tmp_path/'run_v1_1';calls=[]
    with pytest.raises(BrainBlocked,match='owner_go'):
        run_once_authorized(output,'a'*64,None,lambda p:calls.append(p))
    assert not output.exists() and not calls


def test_runner_without_go_never_even_opens_manifest(monkeypatch):
    from research_lab.brain_v2_v1_1_run import main
    monkeypatch.setattr('sys.argv',['v11','--manifest','missing.json','--expected-pin','a'*64])
    with pytest.raises(BrainBlocked,match='owner_go'):main()


def test_verify_only_cannot_construct_outcome_inputs(monkeypatch,capsys):
    import research_lab.brain_v2_v1_1_run as runner
    manifest=BASE/'PREPARATION_MANIFEST.json'
    def forbidden(*args):raise AssertionError('outcome inputs must not be constructed')
    monkeypatch.setattr(runner,'RealInputs',forbidden)
    monkeypatch.setattr('sys.argv',['v11','--manifest',str(manifest),'--expected-pin',
        json.loads(manifest.read_bytes())['sha256'],'--verify-only'])
    runner.main()
    assert json.loads(capsys.readouterr().out)['filter_runs']==0
    assert not (BASE/'run_v1_1').exists()


def test_separate_version_one_shot_and_early_failure_spent(tmp_path):
    with pytest.raises(BrainBlocked,match='version'):
        run_once_authorized(tmp_path/'run_a5_a6','a'*64,OWNER_GO,lambda _:None)
    def fail(_):raise BrainBlocked('synthetic_early_failure')
    output=tmp_path/'run_v1_1'
    report=run_once_authorized(output,'a'*64,OWNER_GO,fail)
    assert report['run_permission_consumed'] and report['status']=='BLOCKED_DATA'
    assert json.loads((output/'OWNER_GO.json').read_bytes())['owner_go']==OWNER_GO
    with pytest.raises(BrainBlocked,match='single_run'):
        run_once_authorized(output,'a'*64,OWNER_GO,fail)
