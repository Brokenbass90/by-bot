"""New explicit owner scope; original V3 and spent artifacts are not amended."""
import copy
import json
from pathlib import Path
from decimal import Decimal as D

import pytest

from bot.kity_m3_orders_off import digest
from research_lab.kity_execution_micro_runtime_v1 import _owner_bounds, prepare_micro_plan
from research_lab.kity_micro_post_go_pricing_v1 import make_policy, compile_after_go
from research_lab.kity_micro_pricing_intent_v2 import materialize
from research_lab.kity_batch_ws_v1 import make_batch_policy, payload, BatchJournal, commit_intent, consume_batch_policy_once, GO_PREFIX
from research_lab.kity_micro_preflight_v1 import attach_native_guards
from test_kity_micro_post_go_pricing_v1 import fresh
from test_kity_micro_runtime_v1 import dossier
from test_kity_micro_integration_v3 import V3
from test_kity_micro_pricing_intent_v2 import PIN, PREVIOUS

ROOT=Path(__file__).resolve().parents[1]
V4=json.loads((ROOT/'configs/research/kity_execution_micro_owner_bounds_v4_20261017.json').read_bytes())


def bound_policy(**changes):
    return make_policy(created_ms=1000,valid_until_ms=80000000,physical_config_sha256=PIN,
                       predecessor_plan_id=PREVIOUS,bounds=V4,**changes)


def cap300_fresh(price='1.2'):
    d,c=fresh(price=price)
    # Use the REAL unchanged preparer, not a hand-written accepted plan.
    src=dossier()
    for leg,source_leg in zip(src['profiles'][0]['legs'],d['plan']['legs']):
        leg['draft_entry']=copy.deepcopy(source_leg['request'])
        leg['entry_reference_notional']=str(D(source_leg['quantity'])*D(price))
        leg['quantity']=source_leg['quantity']
        leg['rounding_shortfall_fraction']='0'
    src['profiles'][0]['common_reference_target']=str(D('20')*D(price))
    src['profiles'][0]['observed_depth_gross']=str(D('200')*D(price))
    src['profiles'][0]['constant_price_roundtrip_fees']=str(D('200')*D(price)*D('.0011'))
    d['instruments']=[dict(i,tick_size='.0001') for i in d['instruments']]
    attach_native_guards(src['profiles'][0],d['instruments'],D('15'),D('0'))
    src['observed_end_ms']=d['observed_end_ms']
    d['plan']=prepare_micro_plan(src,V4)
    return d,c


def test_new_explicit_v4_scope_compiles_real_240_gross_and_ten_native_guards(tmp_path):
    p=bound_policy();d,c=cap300_fresh();out=compile_after_go(p,d,c,go_ms=4999800,now_ms=5000001)
    assert out['plan']['bounds']['max_gross_usdt']=='300'
    assert out['plan']['bounds']['max_all_in_loss_usdt']=='15'
    assert D(out['plan']['reference_gross_usdt'])==240
    assert len(payload(out['plan'])['request'])==10
    assert all(l['request']['stopLoss'] for l in out['plan']['legs'])
    assert not out['orders_allowed']
    j=BatchJournal(tmp_path/'v4.sqlite',out['plan']);commit_intent(j,at_ms=5000002)
    assert len(j.snapshot()['entries'])==10
    j.close()


@pytest.mark.parametrize('field,value',[
    ('owner_approval_text_sha256','0'*64),('owner_review_packet_id','0'*64),
    ('supersedes_spent_policy_sha256','0'*64),('source_owner_message','GO'),
    ('max_gross_usdt','301'),('max_all_in_loss_usdt','16'),
    ('allow_reentry',True),('owner_money_go',True),('duration_ms',1800001)])
def test_rehash_or_copied_scope_cannot_widen_owner_go(field,value):
    with pytest.raises(ValueError):_owner_bounds(dict(V4,**{field:value}))


def test_v3_cannot_gain_300_and_v4_cannot_gain_70s():
    with pytest.raises(ValueError):_owner_bounds(dict(V3,max_gross_usdt='300'))
    with pytest.raises(ValueError):bound_policy(dispatch_window_ms=70000)


def test_personal_handoff_accepts_only_the_separately_validated_v4_60s_scope():
    from scripts.kity_batch_owner_handoff_v1 import approved_bounds
    approved_bounds(bound_policy())
    with pytest.raises(ValueError):approved_bounds(dict(bound_policy(),dispatch_window_ms=70000))
    with pytest.raises(ValueError):approved_bounds(dict(bound_policy(),bounds=dict(V4,max_all_in_loss_usdt='16')))


def test_v4_materialization_refuses_collar_over_300():
    p=bound_policy();d,c=cap300_fresh('1.50')
    with pytest.raises(ValueError,match='300'):
        compile_after_go(p,d,c,go_ms=4999800,now_ms=5000001)


def test_cap300_batch_claim_still_consumed_before_capture_and_not_reused(tmp_path):
    p=make_batch_policy(bound_policy());calls=[]
    def capture():
        assert (tmp_path/'batch-policy-claim.json').is_file()
        calls.append(1);raise ValueError('FRESH_SOURCE_FAILED')
    with pytest.raises(ValueError,match='FRESH_SOURCE_FAILED'):
        consume_batch_policy_once(tmp_path,p,GO_PREFIX+p['batch_policy_id'],4999800,capture,clock=lambda:5000001)
    with pytest.raises(FileExistsError):
        consume_batch_policy_once(tmp_path,p,GO_PREFIX+p['batch_policy_id'],4999800,capture,clock=lambda:5000002)
    assert calls==[1]
