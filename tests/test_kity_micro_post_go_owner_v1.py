import json
from pathlib import Path
import pytest

from bot.kity_m3_orders_off import digest
from research_lab import kity_micro_post_go_owner_v1 as po
from research_lab.kity_micro_bounded_owner_v2 import JournalV2, read_state
from research_lab.kity_micro_physical_owner_v1 import AccountLease, PhysicalOwner, publish
from research_lab.kity_micro_post_go_pricing_v1 import compile_after_go, GO_PREFIX
from test_kity_micro_post_go_pricing_v1 import policy, fresh
from test_kity_micro_runtime_v1 import event


def owned(tmp_path,monkeypatch):
    p=policy();d,c=fresh();out=compile_after_go(p,d,c,go_ms=4999800,now_ms=5000001)
    # Raw-source replay has a separate exact-saved-capture test; only substitute
    # that offline parser boundary to exercise real journal/lease/GO behavior.
    monkeypatch.setattr(po,'verify_compilation',lambda d:None)
    store=tmp_path/'experiment';store.mkdir();clock=[5000010];calls=[]
    publish(store/'policy-claim.json',dict(policy_id=p['policy_id'],
        owner_go_text=GO_PREFIX+p['policy_id'],go_ms=4999800,accepted_ms=4999900))
    j=JournalV2(store/'lifecycle.sqlite',out['plan']);lease=AccountLease(tmp_path/'account.lock')
    wire=tmp_path/'wire';wire.mkdir()
    o=po.PostGoOwner(j,None,lease,store,platform_check=lambda:None,
        post=lambda *args:calls.append(args),clock=lambda:clock[0],dossier=out,wire_root=wire)
    return o,j,p,clock,calls


def test_only_actual_policy_go_can_enable_owner_not_internal_derived_intent(tmp_path,monkeypatch):
    o,j,p,clock,calls=owned(tmp_path,monkeypatch)
    with pytest.raises(ValueError):o.accept_go('GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])
    with pytest.raises(ValueError):o.accept_intent_go('GO KITY_EXECUTION_MICRO_INTENT_V2 '+o.intent['intent_id'])
    assert not o._authorized and not calls
    o.accept_policy_go(GO_PREFIX+p['policy_id'])
    r=json.loads((o.store/'owner-go.json').read_text())
    assert r['owner_go_text']==GO_PREFIX+p['policy_id'] and r['go_ms']==4999800
    assert o._authorized and not calls


def test_dispatch_deadline_rechecked_after_final_custody_without_wire(tmp_path,monkeypatch):
    o,j,p,clock,calls=owned(tmp_path,monkeypatch);o.accept_policy_go(GO_PREFIX+p['policy_id'])
    req=j.plan['legs'][0]['request'];j.append(event('ENTRY_INTENT',symbol=req['symbol']))
    clock[0]=5059799;o._ticket=(digest(req),'ENTRY',clock[0])
    monkeypatch.setattr(o,'assert_exclusive',lambda *_:clock.__setitem__(0,5059800))
    with pytest.raises(ValueError,match='DISPATCH_DEADLINE'):o.post_once('/v5/order/create',req)
    assert not calls and j.snapshot()['entries'][req['symbol']]['local_not_sent']


def test_recovery_after_entry_deadline_retains_exit_authority_but_never_reenters(tmp_path,monkeypatch):
    o,j,p,clock,calls=owned(tmp_path,monkeypatch);o.accept_policy_go(GO_PREFIX+p['policy_id'])
    clock[0]=9999999;o._authorized=False;o.recover_go()
    assert o._authorized
    with pytest.raises(ValueError):o.entry_fence()
    seen=[];monkeypatch.setattr(PhysicalOwner,'post_once',lambda self,path,req:seen.append(req))
    req=dict(symbol='BTWUSDT',reduceOnly=True)
    o.post_once('/v5/order/create',req)
    assert seen==[req] and not calls


def test_policy_claim_tampering_blocks_binding(tmp_path,monkeypatch):
    o,j,p,clock,calls=owned(tmp_path,monkeypatch)
    claim=o.store/'policy-claim.json';data=json.loads(claim.read_text());data['go_ms']-=1
    claim.write_text(json.dumps(data)) # deliberate corruption of synthetic fixture
    with pytest.raises(ValueError,match='CLAIM'):
        po.PostGoOwner(j,None,o.lease,o.store,platform_check=lambda:None,post=lambda *_:None,
            clock=lambda:clock[0],dossier=o.dossier,wire_root=o.wire_root)


def test_failed_post_go_capture_consumes_new_selection_and_preserves_old_history(tmp_path,monkeypatch):
    p=policy();publish(tmp_path/'policies'/(p['policy_id']+'.json'),p)
    old=tmp_path/'old-selected-v2.json';old.write_text('immutable old NO_SEND')
    s=po.PostGoSupervisor.__new__(po.PostGoSupervisor);s.root=tmp_path;s.config={'_config_sha256':p['physical_config_sha256']}
    s.journal=None;s.owner=None;s.before_selection=lambda: (_ for _ in ()).throw(ValueError('selected')) if (tmp_path/'selected-v2.json').exists() else None
    calls=[]
    def unavailable(store):
        assert (tmp_path/'selected-v2.json').exists();calls.append(1);raise ValueError('SOURCE_UNKNOWN')
    s.fresh=unavailable;monkeypatch.setattr(po,'now_ms',lambda:5000001)
    cmd=dict(kind='GO_POST_GO',policy_id=p['policy_id'],exact_go=GO_PREFIX+p['policy_id'],issued_ms=4999800)
    with pytest.raises(ValueError,match='SOURCE_UNKNOWN'):s.control(cmd)
    with pytest.raises(ValueError,match='selected'):s.control(cmd)
    assert calls==[1] and old.read_text()=='immutable old NO_SEND'
    assert not s.journal and not s.owner
    assert (tmp_path/'experiments-v2'/p['policy_id']/'no-send.json').exists()


def test_post_go_control_rejects_legacy_or_caller_price_and_quantity():
    p=policy();cmd=dict(kind='GO_POST_GO',policy_id=p['policy_id'],exact_go=GO_PREFIX+p['policy_id'],issued_ms=4999800)
    assert po.validate_control(cmd)==cmd
    for change in ({'price':'2'},{'qty':'10'},{'issued_ms':True},{'exact_go':'GO KITY_EXECUTION_MICRO_INTENT_V2 '+p['policy_id']}):
        with pytest.raises(ValueError):po.validate_control(dict(cmd,**change))


def test_missing_selection_with_any_new_experiment_history_blocks_startup(tmp_path):
    custody=tmp_path/'runtime';root=custody/'post-go-20261016';store=root/'experiments-v2'/'a';store.mkdir(parents=True)
    (store/'policy-claim.json').write_text('{}')
    with pytest.raises(ValueError,match='MISSING_SELECTED'):
        po.check_history(root,custody,{'wire_baseline_files':{}})


def test_owner_cli_default_only_reports_no_network_without_starting_service(capsys):
    assert po.main([])==0
    assert 'OWNER_PREPARATION_ONLY_NO_NETWORK' in capsys.readouterr().out


def test_post_go_owner_all_ten_native_restart_deadline_and_final_cash(tmp_path,monkeypatch):
    """Real journal/lease/dispatch/readback/exit against the deterministic venue.

    Synthetic source replay is the only replaced parser boundary. No actual
    credential, HTTP request, money authority or broker order is involved.
    """
    import copy
    import test_kity_micro_physical_e2e_v1 as venue
    from research_lab.kity_micro_post_go_pricing_v1 import make_policy
    from test_kity_micro_pricing_intent_v2 import source, PIN
    from test_kity_micro_integration_v3 import V3
    at=1792050000000;d,c=source(at);plan=copy.deepcopy(d['plan'])
    for leg in plan['legs']:leg['quantity']=leg['request']['qty']='1'
    plan.update(reference_gross_usdt='10',planned_limit_gross_usdt='10')
    plan['plan_id']=digest({k:v for k,v in plan.items() if k!='plan_id'})
    d['plan']=plan;d['observed_start_ms']=at
    for row in d['instruments']:row['taker_fee']='.6'
    p=make_policy(created_ms=at-1000,valid_until_ms=at+86400000-1000,
        physical_config_sha256=PIN,predecessor_plan_id='a'*64,bounds=V3)
    out=compile_after_go(p,d,c,go_ms=at,now_ms=at)
    monkeypatch.setattr(venue,'prepare_micro_plan',lambda *_:copy.deepcopy(out['plan']))
    monkeypatch.setattr(po,'verify_compilation',lambda *_:None)
    class HarnessOwner(po.PostGoOwner):
        def accept_go(self,text):
            assert text=='GO KITY_EXECUTION_MICRO_LIVE '+self.journal.plan['plan_id']
            self.accept_policy_go(GO_PREFIX+p['policy_id'])
    def factory(*args,**kwargs):
        store=Path(args[3])
        publish(store/'policy-claim.json',dict(policy_id=p['policy_id'],
            owner_go_text=GO_PREFIX+p['policy_id'],go_ms=at,accepted_ms=at))
        return HarnessOwner(*args,**kwargs,dossier=out,wire_root=tmp_path/'wire')
    monkeypatch.setattr(venue,'PhysicalOwner',factory);monkeypatch.setattr(venue,'MicroJournal',JournalV2)
    venue.test_concrete_owner_all_ten_native_restart_deadline_and_actual_cash_path(tmp_path,monkeypatch)
