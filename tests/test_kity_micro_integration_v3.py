import copy
import json
from pathlib import Path

import pytest

from research_lab.kity_execution_micro_runtime_v1 import prepare_micro_plan,assess_micro_readiness
from research_lab.kity_execution_micro_runtime_v1 import validate_plan
from bot.kity_m3_orders_off import digest
from test_kity_micro_runtime_v1 import dossier,BOUNDS
from test_kity_micro_policy_v2 import V2

ROOT=Path(__file__).resolve().parents[1]
V3=dict(V2,schema='kity_execution_micro_owner_bounds_v3',max_gross_usdt='215',
 source_owner_message='2026-10-15 GO KITY MICRO-LIVE EXECUTION INTEGRATION — ORDERS OFF',
 supersedes_policy_sha256='49bf03e4733711d3c97c684ec2436fff988817e8fb6d9cef351b71708a882bb3')


def test_owner_215_amendment_accepts_saved_basket_without_any_other_change():
    d=dossier();d['profiles'][0]['observed_depth_gross']='210.266660'
    p=prepare_micro_plan(d,V3)
    assert p['bounds']['max_gross_usdt']=='215' and p['blocked_reasons']==[]
    assert p['bounds']['max_all_in_loss_usdt']=='15' and p['bounds']['duration_ms']==1800000
    assert not assess_micro_readiness(p,{})['orders_allowed']
    assert len(p['legs'])==10 and p['bounds']['max_rounding_shortfall_fraction']=='0.203'


def test_215_ceiling_is_exact_and_previous_policies_keep_210():
    d=dossier();d['profiles'][0]['observed_depth_gross']='215.000001'
    assert prepare_micro_plan(d,V3)['blocked_reasons']==['GROSS_CAP_EXCEEDED']
    for b in (BOUNDS,V2):
        d['profiles'][0]['observed_depth_gross']='210.000001'
        assert prepare_micro_plan(d,b)['blocked_reasons']==['GROSS_CAP_EXCEEDED']


@pytest.mark.parametrize('key,value',[('max_gross_usdt','216'),('source_owner_message','unknown'),
 ('supersedes_policy_sha256','a'*64),('duration_ms',1800001),('allow_reentry',True)])
def test_amendment_cannot_extend_money_authority_or_other_bounds(key,value):
    b=dict(V3);b[key]=value
    with pytest.raises(ValueError,match='OWNER_BOUND'):prepare_micro_plan(dossier(),b)


def test_rehashing_a_plan_cannot_hide_an_order_quantity_over_the_gross_cap():
    p=prepare_micro_plan(dossier(),V3)
    p['legs'][0]['quantity']='999';p['legs'][0]['request']['qty']='999'
    p['plan_id']=digest({k:v for k,v in p.items() if k!='plan_id'})
    with pytest.raises(ValueError,match='PLAN_BOUND'):validate_plan(p)
