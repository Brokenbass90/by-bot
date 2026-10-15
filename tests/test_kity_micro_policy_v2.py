import copy
import json
from pathlib import Path

import pytest

from bot.kity_m3_orders_off import digest
from research_lab.kity_execution_micro_runtime_v1 import prepare_micro_plan, assess_micro_readiness, MicroJournal
from test_kity_micro_runtime_v1 import dossier, event, send, fill, terminal, protect, exit_leg, flat, BASKET

ROOT=Path(__file__).resolve().parents[1]
V2=json.loads((ROOT/'configs/research/kity_execution_micro_owner_bounds_v2_20261015.json').read_text())


def test_direct_owner_policy_v2_removes_only_the_guarantee_blocker():
    p=prepare_micro_plan(dossier(),V2)
    r=assess_micro_readiness(p,dict(marginMode='REGULAR_MARGIN'))
    assert 'HARD_FINAL_LOSS_CAP_NOT_ENFORCEABLE_ON_PERPETUALS' not in r['reasons']
    assert r['loss_policy']=='IMMEDIATE_ALL_IN_EXIT_THRESHOLD'
    assert r['loss_threshold_usdt']=='15' and r['execution_overshoot_accepted'] is True
    assert r['guaranteed_final_loss_cap'] is False and r['orders_allowed'] is False
    assert 'REAL_TRANSPORT_AND_EXCLUSIVE_WRITER_BINDING_REQUIRED' in r['reasons']


@pytest.mark.parametrize('key,value',[('source_reply_id','unknown'),('allow_execution_overshoot',False),
    ('loss_policy','IGNORE_LOSS'),('max_all_in_loss_usdt','16'),('duration_ms',1800001),
    ('max_gross_usdt','211'),('max_rounding_shortfall_fraction','.204')])
def test_v2_policy_cannot_be_relaxed_or_self_authorized(key,value):
    b=copy.deepcopy(V2);b[key]=value
    with pytest.raises(ValueError,match='OWNER_BOUND'):prepare_micro_plan(dossier(),b)


def test_old_guarantee_policy_still_replays_without_being_silently_softened():
    from test_kity_micro_runtime_v1 import BOUNDS
    p=prepare_micro_plan(dossier(),BOUNDS)
    assert 'HARD_FINAL_LOSS_CAP_NOT_ENFORCEABLE_ON_PERPETUALS' in assess_micro_readiness(p,{})['reasons']


def test_v2_acceptance_does_not_waive_saved_210_dollar_gross_cap():
    d=dossier();d['profiles'][0]['observed_depth_gross']='210.266660'
    p=prepare_micro_plan(d,V2)
    assert 'GROSS_CAP_EXCEEDED' in assess_micro_readiness(p,{})['reasons']


def test_v2_final_overshoot_is_reported_not_claimed_as_a_guarantee(tmp_path):
    p=prepare_micro_plan(dossier(),V2);j=MicroJournal(tmp_path/'j.sqlite',p)
    s=BASKET[0][0];send(j,s);fill(j,s,price='20',fee='0');terminal(j,s);protect(j,s)
    j.append(event('UNWIND',reason='loss'));exit_leg(j,s,price='1',fee='0');flat(j)
    j.append(event('FINALITY',funding_complete=True,net_cash_usdt='-19'))
    assert j.snapshot()['terminal_verdict']=='EXIT_THRESHOLD_OVERSHOOT'
    assert j.snapshot()['execution_overshoot_accepted'] is True
    assert j.snapshot()['orders_allowed'] is False and j.snapshot()['research_evidence_eligible'] is False
