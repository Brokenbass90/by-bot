"""Owner-bounded first-entry authority only; broker calls are simulated."""
import copy
import importlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from research_lab.alpaca_dynamic_v1 import canonical,digest
from tests.test_alpaca_dynamic_live_runtime_v1 import setup,case,NOW,run


def api():return importlib.import_module('research_lab.alpaca_dynamic_first_intent_v1')


@pytest.fixture
def approved(setup,tmp_path):
    _,_,intake,policy,binding,_=setup
    intent=api().prepare_first_intent(policy=policy,binding=binding,
        ticker='NET',session='2026-10-14',ranking_sha256=intake['plan']['ranking_sha256'],
        slot_entry_order_id=intake['plan']['slot_entry_order_id'],risk_distance='4',
        max_qty='.5',max_notional_usd='50',max_risk_usd='2',max_limit_price='100',
        price_source_sha256='a'*64,quote_cts_ms=NOW-86400000,
        prepared_ms=NOW-86400000)
    ip=tmp_path/'first-intent.json';ip.write_bytes(canonical(intent))
    # Fixture represents later separate direct owner GO, not today's choice.
    permit=dict(schema='ALPACA_DYNAMIC_FIRST_INTENT_OWNER_GO_V1',account_id=policy['account_id'],
        endpoint=binding['endpoint'],intent_sha256=intent['intent_sha256'],
        static_binding_sha256=intent['static_binding_sha256'],session=intent['session'],
        owner_go_text='GO ALPACA_DYNAMIC_FIRST_INTENT_V1 '+intent['intent_sha256'])
    gp=tmp_path/'first-go.json';gp.write_bytes(canonical(permit))
    return setup,ip,gp,intent


def test_preparation_has_no_order_or_owner_authority(approved):
    s,_,_,i=approved
    assert i['orders_allowed'] is False and i['money_authority'] is False
    assert i['attempts_allowed']==1 and i['symbol']=='NET'
    assert s[1].writes==[] and not Path(s[4]['runtime']).exists()


def test_separate_go_still_required(approved):
    s,ip,gp,i=approved;gp.write_text('{}')
    r=s[0].run_once(intake=s[2],policy=s[3],binding=s[4],client=s[1],now_ms=NOW,
        apply=True,owner_go_path=gp,first_intent_path=ip)
    assert r['status']=='BLOCKED_DATA' and s[1].writes==[]


def test_first_intent_accepts_exact_fresh_plan_and_restart_no_second_buy(approved):
    s,ip,gp,i=approved
    def invoke():return s[0].run_once(intake=s[2],policy=s[3],binding=s[4],client=s[1],
        now_ms=NOW+3000,apply=True,owner_go_path=gp,first_intent_path=ip)
    assert invoke()['status']=='LIVE_PROTECTED'
    assert invoke()['status']=='LIVE_PROTECTED'
    assert len(s[1].writes)==2


@pytest.mark.parametrize('change',[
    {'symbol':'XOM'},{'session':'2026-10-15'},{'qty':'.51'},
    {'ranking_sha256':'9'*64},{'risk_distance':'4.01'},
    {'reference_ask':'100.01'},{'slot_entry_order_id':'foreign'}])
def test_intent_cannot_expand_or_change_fresh_plan(approved,change):
    s,ip,gp,i=approved
    mutated=copy.deepcopy(s[2]);mutated['plan'].update(change)
    with pytest.raises(ValueError):
        api().check_first_intent(i,s[4],mutated,s[3])
    assert s[1].writes==[]


def test_no_go_transfer_to_different_binding(approved):
    s,ip,gp,i=approved;b=copy.deepcopy(s[4]);b['lock_path']+='-other'
    with pytest.raises(ValueError,match='FIRST_INTENT'):
        api().check_first_intent(i,b,s[2],s[3])


def test_intent_pins_native_manager_before_future_plan(approved):
    s,_,_,intent=approved
    changed=copy.deepcopy(s[2]);changed['scope']['native_manager_source_sha256']='0'*64
    with pytest.raises(ValueError,match='FIRST_INTENT_NATIVE_MANAGER'):
        api().check_first_intent(intent,s[4],changed,s[3])
    assert s[1].writes==[]


def test_stale_preparation_quote_is_refused(setup):
    _,_,r,p,b,_=setup
    with pytest.raises(ValueError,match='PREPARATION_QUOTE'):
        api().prepare_first_intent(policy=p,binding=b,ticker='NET',session='2026-10-14',
            ranking_sha256=r['plan']['ranking_sha256'],slot_entry_order_id=r['plan']['slot_entry_order_id'],
            risk_distance='4',max_qty='.5',max_notional_usd='50',max_risk_usd='2',max_limit_price='100',
            price_source_sha256='a'*64,quote_cts_ms=NOW-600001,prepared_ms=NOW-10000)


def test_intent_cannot_relax_original_entry_window(approved):
    s,ip,gp,i=approved
    r=s[0].run_once(intake=s[2],policy=s[3],binding=s[4],client=s[1],now_ms=NOW+300001,
        apply=True,owner_go_path=gp,first_intent_path=ip)
    assert r['status']=='BLOCKED_DATA' and s[1].writes==[]


def test_bounded_intent_never_clears_halt(approved):
    s,ip,gp,i=approved;Path(s[4]['halt_path']).write_text('{"halted":true}')
    r=s[0].run_once(intake=s[2],policy=s[3],binding=s[4],client=s[1],now_ms=NOW,
        apply=True,owner_go_path=gp,first_intent_path=ip)
    assert r['reason']=='ENTRY_HALTED' and s[1].writes==[]


def test_first_intent_is_not_a_second_entry_permission(approved):
    import sqlite3
    s,ip,gp,i=approved
    runtime=Path(s[4]['runtime']);runtime.mkdir()
    with sqlite3.connect(runtime/'live.sqlite') as db:
        db.execute('CREATE TABLE intents(id TEXT PRIMARY KEY,account TEXT,slot TEXT,session TEXT,payload TEXT)')
        db.execute('INSERT INTO intents VALUES(?,?,?,?,?)',('old',s[4]['account_id'],'old-slot','old-session','{}'))
    r=s[0].run_once(intake=s[2],policy=s[3],binding=s[4],client=s[1],now_ms=NOW,
        apply=True,owner_go_path=gp,first_intent_path=ip)
    assert r['reason']=='FIRST_DYNAMIC_ENTRY_ALREADY_CONSUMED' and s[1].writes==[]


def test_pre_entry_dossier_never_promotes_missing_actual_paper():
    r=importlib.import_module('research_lab.alpaca_live_readiness_v1').pre_entry_dossier(
        paper=dict(status='PAPER_PENDING'),deployment={},binding={},intent={},policy={},preparation={},now_ms=NOW)
    assert r['status']=='BLOCKED_DATA' and r['ready_for_live_go'] is False


@pytest.mark.parametrize('ask,allowed',[('363.20',True),('363.2001',False)])
def test_net_cent_rounded_stop_uses_actual_plan_risk_cap(ask,allowed):
    """Oct12 NET quantity fits rounded stop; raw ranking distance must not veto it.

    A 0.0001 wider actual distance still exceeds the SAME original risk cap and
    must be rejected. This is a transport-free counterexample, not a LIVE source.
    """
    policy=json.loads((Path(__file__).resolve().parents[1]/
        'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json').read_bytes())
    slot=next(s for s in policy['inherited_slots'] if s['entry_order_id'].startswith('2b559bee'))
    binding=dict(account_id=policy['account_id'],endpoint='https://api.alpaca.markets',policy_sha256=digest(policy))
    intent=api().prepare_first_intent(policy=policy,binding=binding,ticker='NET',session='2026-10-14',
        ranking_sha256='a'*64,slot_entry_order_id=slot['entry_order_id'],risk_distance='33.54241333009',
        max_qty='0.325167779',max_notional_usd=str(slot['notional_cap']),max_risk_usd=str(slot['risk_cap']),
        max_limit_price='363.20',price_source_sha256='b'*64,quote_cts_ms=NOW-86400000,prepared_ms=NOW-86400000)
    intake=dict(plan=dict(symbol='NET',session='2026-10-14',ranking_sha256=intent['ranking_sha256'],
        slot_entry_order_id=slot['entry_order_id'],qty='0.325167779',reference_ask=ask,stop_price='329.66',
        risk_distance=str(Decimal(ask)-Decimal('329.66'))),scope=dict(native_manager_source_sha256=intent['native_manager_source_sha256']),
        entry_payload=dict(symbol='NET',qty='0.325167779',limit_price='363.20'))
    if allowed:assert api().check_first_intent(intent,binding,intake,policy)==intent['intent_sha256']
    else:
        with pytest.raises(ValueError,match='FIRST_INTENT_CAP_EXCEEDED'):
            api().check_first_intent(intent,binding,intake,policy)
