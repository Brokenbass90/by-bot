"""Post-GO prices must come from one new source, never a human-delay anchor."""
import copy
import json

import pytest

from bot.kity_m3_orders_off import digest
from research_lab import kity_micro_post_go_pricing_v1 as pg
from research_lab.kity_micro_pricing_intent_v2 import materialize
from test_kity_micro_pricing_intent_v2 import source, PIN, PREVIOUS, intent
from test_kity_micro_integration_v3 import V3


def policy():
    return pg.make_policy(created_ms=1000, valid_until_ms=80000000,
        physical_config_sha256=PIN, predecessor_plan_id=PREVIOUS, bounds=V3)


def fresh(at=5000000, price='.95'):
    d,c=source(at,price)
    d['observed_start_ms']=at-100
    return d,c


def test_long_human_delay_uses_only_post_go_prices_and_quantities():
    p=policy();d,c=fresh();before=copy.deepcopy((p,d,c))
    # The old approval would fail on this price change even inside its TTL.
    old,c_old=source(2000,'.95')
    with pytest.raises(ValueError,match='PRICE_ENVELOPE'):
        materialize(intent(),old,c_old,now_ms=2001)
    out=pg.compile_after_go(p,d,c,go_ms=4999800,now_ms=5000001)
    assert out['plan']['legs'][0]['request']['price']=='0.9547'
    assert out['plan']['legs'][5]['request']['price']=='0.9453'
    assert out['plan']['pricing_intent']['expires_ms']==5059800
    assert out['post_go_policy']['policy_id']==p['policy_id']
    assert out['post_go_go_ms']==4999800
    assert (p,d,c)==before
    assert not out['orders_allowed'] and not out['counts_toward_C1_C2_C3']


def test_policy_has_no_preapproved_absolute_prices_or_quantities():
    p=policy()
    assert 'reference_plan' not in p and 'price_bands' not in p
    assert [(r['symbol'],r['side']) for r in p['basket']]==list(pg.BASKET)
    d,c=fresh();d['plan']['legs'][0]['quantity']='19'
    d['plan']['legs'][0]['request']['qty']='19'
    d['plan']['planned_limit_gross_usdt']='189.05'
    d['plan']['reference_gross_usdt']='189.05'
    d['plan']['plan_id']=digest({k:v for k,v in d['plan'].items() if k!='plan_id'})
    assert pg.compile_after_go(p,d,c,go_ms=4999800,now_ms=5000001)['plan']['legs'][0]['quantity']=='19'


@pytest.mark.parametrize('change',[
    {'collar_bps':'51'}, {'dispatch_window_ms':60001}, {'quantity_rule':'CUSTOM'},
    {'bounds':dict(V3,max_gross_usdt='216')}, {'research_evidence_eligible':True},
    {'valid_until_ms':True}, {'created_ms':True}, {'basket':[]},
])
def test_rehash_does_not_authorize_changed_policy_rules(change):
    p=policy();p.update(change);p['policy_id']=digest({k:v for k,v in p.items() if k!='policy_id'})
    with pytest.raises(ValueError):pg.validate_policy(p)


@pytest.mark.parametrize('go,now',[(999,5000001),(80000000,80000001),(4999800,5059800),(5000002,5000001)])
def test_go_session_and_post_go_dispatch_deadline_fail_closed(go,now):
    d,c=fresh()
    with pytest.raises(ValueError):pg.compile_after_go(policy(),d,c,go_ms=go,now_ms=now)


def test_pre_go_capture_and_stale_cts_are_never_reused():
    d,c=fresh()
    with pytest.raises(ValueError,match='CAPTURE_PRECEDES_GO'):
        pg.compile_after_go(policy(),d,c,go_ms=5000000,now_ms=5000001)
    c['book:BTWUSDT']['body']['result']['cts']=1
    with pytest.raises(ValueError,match='COMMON_2S'):
        pg.compile_after_go(policy(),d,c,go_ms=4999800,now_ms=5000001)


def test_one_durable_claim_before_one_capture_no_retry_after_failure(tmp_path):
    p=policy();calls=[]
    def capture():
        assert (tmp_path/'policy-claim.json').is_file()
        calls.append(1)
        raise ValueError('SOURCE_UNKNOWN')
    text='GO KITY_EXECUTION_MICRO_POLICY_V1 '+p['policy_id']
    with pytest.raises(ValueError,match='SOURCE_UNKNOWN'):
        pg.consume_policy_once(tmp_path,p,text,4999800,capture,clock=lambda:5000001)
    with pytest.raises(FileExistsError):
        pg.consume_policy_once(tmp_path,p,text,4999800,capture,clock=lambda:5000002)
    assert calls==[1] and not (tmp_path/'materialized.json').exists()
    assert json.loads((tmp_path/'no-send.json').read_text())['broker_writes']==0


def test_capture_that_finishes_after_deadline_is_not_retried(tmp_path):
    p=policy();at=[5000000];calls=[]
    def capture():
        calls.append(1);at[0]=5060000
        return fresh(5060000)
    with pytest.raises(ValueError,match='DISPATCH_DEADLINE'):
        pg.consume_policy_once(tmp_path,p,'GO KITY_EXECUTION_MICRO_POLICY_V1 '+p['policy_id'],
            5000000,capture,clock=lambda:at[0])
    assert calls==[1] and (tmp_path/'no-send.json').exists()
    assert not (tmp_path/'materialized.json').exists()


def test_old_money_go_or_expired_policy_never_takes_a_capture(tmp_path):
    calls=[];p=policy()
    with pytest.raises(ValueError,match='EXACT_POLICY_GO'):
        pg.consume_policy_once(tmp_path,p,'GO KITY_EXECUTION_MICRO_INTENT_V2 '+p['policy_id'],
            4999800,lambda:calls.append(1),clock=lambda:5000001)
    with pytest.raises(ValueError):
        pg.consume_policy_once(tmp_path,p,'GO KITY_EXECUTION_MICRO_POLICY_V1 '+p['policy_id'],
            80000000,lambda:calls.append(1),clock=lambda:80000000)
    assert not calls and not list(tmp_path.iterdir())


def test_fresh_caps_cannot_be_bypassed_by_dynamic_pricing():
    d,c=fresh(price='1.074')
    with pytest.raises(ValueError,match='215'):
        pg.compile_after_go(policy(),d,c,go_ms=4999800,now_ms=5000001)
