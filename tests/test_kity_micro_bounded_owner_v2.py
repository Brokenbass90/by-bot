import copy,json,sqlite3
from pathlib import Path
from types import SimpleNamespace
import pytest

from bot.kity_m3_orders_off import digest
from research_lab.kity_execution_micro_runtime_v1 import MicroJournal,BASKET
from research_lab.kity_micro_physical_owner_v1 import AccountLease,PhysicalOwner,publish
from research_lab.kity_micro_bounded_owner_v2 import (
    JournalV2,BoundedOwner,BoundedSupervisor,read_predecessor,validate_control,selected_store,rollback_state,
)
from research_lab.kity_micro_pricing_intent_v2 import make_intent,materialize,consume_once
from test_kity_micro_pricing_intent_v2 import source,PIN
from test_kity_micro_runtime_v1 import event


def bound(tmp_path,monkeypatch):
    d,_=source();i=make_intent(d,at_ms=1000,collar_bps='50',ttl_ms=600000,predecessor_plan_id='a'*64)
    fresh,c=source(2000);d=materialize(i,fresh,c,now_ms=2001)
    # Binding replay is separately tested with real raw captures. Here replace
    # only that pure replay to exercise actual lease/POST barriers/GO/expiry.
    monkeypatch.setattr('research_lab.kity_micro_bounded_owner_v2.verify_materialization',lambda *a:None)
    store=tmp_path/'experiment';store.mkdir();clock=[2100];calls=[]
    publish(store/'intent-claim.json',dict(intent_id=i['intent_id'],
        owner_go_text='GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id'],at_ms=2000))
    j=JournalV2(store/'lifecycle.sqlite',d['plan']);lease=AccountLease(tmp_path/'account.lock')
    wire=tmp_path/'wire';wire.mkdir()
    o=BoundedOwner(j,None,lease,store,platform_check=lambda:None,
        post=lambda *args:calls.append(args),clock=lambda:clock[0],dossier=d,wire_root=wire)
    return o,j,i,clock,calls


def test_literal_intent_go_is_retained_and_old_exact_plan_go_cannot_authorize(tmp_path,monkeypatch):
    o,j,i,clock,calls=bound(tmp_path,monkeypatch)
    with pytest.raises(ValueError):o.accept_go('GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])
    with pytest.raises(ValueError):o.accept_intent_go('GO KITY_EXECUTION_MICRO_INTENT_V2 '+'b'*64)
    text='GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id'];o.accept_intent_go(text)
    raw=json.loads((o.store/'owner-go.json').read_bytes())
    assert raw['owner_go_text']==text and raw['plan_id']==j.plan['plan_id'] and o._authorized
    assert calls==[]


def test_expiry_after_durable_intent_before_post_is_known_no_wire_not_fake_broker_rejection(tmp_path,monkeypatch):
    o,j,i,clock,calls=bound(tmp_path,monkeypatch)
    o.accept_intent_go('GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id'])
    req=j.plan['legs'][0]['request'];s=req['symbol']
    j.append(event('ENTRY_INTENT',symbol=s));deadline=j.snapshot()['deadline_ms']
    o._ticket=(digest(req),'ENTRY',600999);clock[0]=601000
    with pytest.raises(ValueError,match='INTENT_CLOCK'):o.post_once('/v5/order/create',req)
    state=j.snapshot()
    assert not calls and state['entries'][s]['terminal']
    assert state['entries'][s]['order_id'] is None and state['entries'][s]['local_not_sent']
    assert state['deadline_ms']==deadline and state['entry_blocked']
    j.close();reopened=JournalV2(o.store/'lifecycle.sqlite',o.journal.plan)
    assert reopened.snapshot()['entries'][s]['local_not_sent']


def test_restart_proves_no_send_only_without_persisted_wire_barrier(tmp_path,monkeypatch):
    o,j,i,clock,calls=bound(tmp_path,monkeypatch);req=j.plan['legs'][0]['request'];s=req['symbol']
    j.append(event('ENTRY_INTENT',symbol=s))
    barrier=o.wire_root/('send-'+digest(dict(path='/v5/order/create',request=req))+'.json')
    publish(barrier,{'status':'INTENT_WIRE_MAY_HAVE_RUN'})
    o.recover_no_wire()
    assert not j.snapshot()['entries'][s]['terminal'] and not calls
    barrier.unlink() # synthetic fixture only: production never deletes barriers
    o.recover_no_wire()
    assert j.snapshot()['entries'][s]['local_not_sent'] and not calls


def test_expired_entry_permission_does_not_block_owned_exits(tmp_path,monkeypatch):
    o,j,i,clock,calls=bound(tmp_path,monkeypatch)
    o.accept_intent_go('GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id'])
    clock[0]=601000
    seen=[]
    monkeypatch.setattr(PhysicalOwner,'post_once',lambda self,path,req:seen.append(req))
    req={'reduceOnly':True,'symbol':'BTWUSDT'}
    o.post_once('/v5/order/create',req)
    assert seen==[req] and not calls


def test_validation_checks_expiry_again_after_the_slow_get_preflight(tmp_path,monkeypatch):
    o,j,i,clock,calls=bound(tmp_path,monkeypatch)
    def slow(*args):clock[0]=601000
    monkeypatch.setattr(PhysicalOwner,'validate_preflight',slow)
    with pytest.raises(ValueError,match='INTENT_CLOCK'):
        o.validate_preflight(j.plan,j.plan['legs'][0]['request'],'ENTRY')
    assert not j.snapshot()['entries'] and not calls


def test_expiry_during_final_custody_check_is_rechecked_at_transport_boundary(tmp_path,monkeypatch):
    o,j,i,clock,calls=bound(tmp_path,monkeypatch)
    o.accept_intent_go('GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id'])
    req=j.plan['legs'][0]['request'];j.append(event('ENTRY_INTENT',symbol=req['symbol']))
    clock[0]=600999;o._ticket=(digest(req),'ENTRY',600999)
    monkeypatch.setattr(o,'assert_exclusive',lambda *_:clock.__setitem__(0,601000))
    with pytest.raises(ValueError,match='INTENT_CLOCK'):o.post_once('/v5/order/create',req)
    assert calls==[] and j.snapshot()['entries'][req['symbol']]['local_not_sent']


def test_predecessor_is_hash_verified_and_replayed_readonly(tmp_path):
    d,_=source();p=d['plan'];publish(tmp_path/'active-plan.json',d)
    j=MicroJournal(tmp_path/'lifecycle.sqlite',p)
    j.append(event('UNWIND',reason='no send'))
    j.append(event('BROKER_SNAPSHOT',positions={s:'0' for s,_ in BASKET},open_order_links=[]))
    j.append(event('FINALITY_NO_SEND'));j.close()
    import hashlib
    pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir() if p.is_file()}
    c={'predecessor_files':pins,'predecessor_plan_id':p['plan_id'],'runtime_root':str(tmp_path)}
    s=read_predecessor(c)
    assert s['execution_verdict']=='NO_SEND_NOT_LIFECYCLE_PASS'
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in pins.items())
    with sqlite3.connect(tmp_path/'lifecycle.sqlite') as db:db.execute("UPDATE events SET hash='bad' WHERE seq=1")
    with pytest.raises(ValueError):read_predecessor(c)


def test_control_scope_and_selected_path_are_exact_not_caller_supplied(tmp_path):
    i='a'*64
    assert validate_control({'kind':'PREPARE_BOUNDED'})['kind']=='PREPARE_BOUNDED'
    assert validate_control({'kind':'GO_BOUNDED','intent_id':i,
        'exact_go':'GO KITY_EXECUTION_MICRO_INTENT_V2 '+i})['intent_id']==i
    for x in ({'kind':'GO','plan_id':i,'exact_go':'GO KITY_EXECUTION_MICRO_LIVE '+i},
              {'kind':'GO_BOUNDED','intent_id':i,'exact_go':'wrong'}):
        with pytest.raises(ValueError):validate_control(x)
    assert selected_store(tmp_path,{'intent_id':i})==tmp_path/'experiments-v2'/i
    with pytest.raises(ValueError):selected_store(tmp_path,{'intent_id':'../other'})


def test_rollback_uses_selected_journal_not_old_terminal(tmp_path):
    from test_kity_micro_pricing_intent_v2 import intent
    i=intent();d,c=source(2000);out=materialize(i,d,c,now_ms=2001)
    selected={'intent_id':i['intent_id']};store=selected_store(tmp_path,selected)
    publish(tmp_path/'selected-v2.json',selected);publish(store/'active-plan.json',out)
    j=JournalV2(store/'lifecycle.sqlite',out['plan'])
    j.append(event('ENTRY_INTENT',symbol='BTWUSDT'));j.close()
    with pytest.raises(ValueError,match='ROLLBACK_SELECTED_RISK'):
        rollback_state({'runtime_root':str(tmp_path)})


def test_rollback_never_treats_missing_selected_journal_as_flat(tmp_path):
    publish(tmp_path/'selected-v2.json',{'intent_id':'a'*64})
    store=tmp_path/'experiments-v2'/('a'*64)
    publish(store/'active-plan.json',{'plan':source()[0]['plan']})
    with pytest.raises(ValueError,match='JOURNAL_MISSING'):
        rollback_state({'runtime_root':str(tmp_path)})


def test_supervisor_claims_selection_before_capture_and_never_retries_failed_intent(tmp_path,monkeypatch):
    from test_kity_micro_pricing_intent_v2 import intent
    i=intent();publish(tmp_path/'bounded-intents'/(i['intent_id']+'.json'),i)
    s=BoundedSupervisor.__new__(BoundedSupervisor);s.root=tmp_path;s.config={'_config_sha256':PIN}
    s.check=lambda:None;s.journal=None;s.owner=None
    s.before_selection=lambda: (_ for _ in ()).throw(ValueError('already selected')) if (tmp_path/'selected-v2.json').exists() else None
    calls=[]
    def failed(store):calls.append(store);assert (tmp_path/'selected-v2.json').exists();raise ValueError('source unavailable')
    s.fresh=failed;monkeypatch.setattr('research_lab.kity_micro_bounded_owner_v2.now_ms',lambda:2000)
    x={'kind':'GO_BOUNDED','intent_id':i['intent_id'],'exact_go':'GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id']}
    with pytest.raises(ValueError,match='source unavailable'):s.control(x)
    with pytest.raises(ValueError,match='already selected'):s.control(x)
    assert len(calls)==1 and (selected_store(tmp_path,i)/'no-send.json').exists()
    assert not (tmp_path/'lifecycle.sqlite').exists()


def test_new_plan_cannot_bind_into_the_original_or_another_experiment_store(tmp_path):
    from test_kity_micro_pricing_intent_v2 import intent
    i=intent();d,c=source(2000);out=materialize(i,d,c,now_ms=2001)
    s=BoundedSupervisor.__new__(BoundedSupervisor);s.root=tmp_path
    s.config={'_config_sha256':PIN,'predecessor_plan_id':i['predecessor_plan_id']}
    for wrong in (tmp_path,tmp_path/'experiments-v2'/('b'*64)):
        s.experiment_root=wrong
        with pytest.raises(ValueError,match='SELECTED_BINDING_CONFLICT'):s.bind(out,create=True)
        assert not (wrong/'lifecycle.sqlite').exists()


def test_v2_full_concrete_venue_ten_native_stops_and_exit_after_intent_expiry(tmp_path,monkeypatch):
    """Run the existing signed transport/venue/restart/unwind fixture via V2.

    Only raw-source parser replay is replaced by a synthetic fixture; the
    concrete owner, journal, POST barriers, readback and 30min exit are real code.
    """
    import test_kity_micro_physical_e2e_v1 as venue
    import research_lab.kity_micro_bounded_owner_v2 as v2
    at=1792050000000;ref,c=source(at)
    p=copy.deepcopy(ref['plan'])
    for leg in p['legs']:
        leg['quantity']=leg['request']['qty']='1'
    p.update(reference_gross_usdt='10',planned_limit_gross_usdt='10')
    p['plan_id']=digest({k:v for k,v in p.items() if k!='plan_id'})
    ref['plan']=p
    # High synthetic fee reserve makes a native fallback feasible even at the
    # legacy fixture's $10 total size. No live costs or bounds are modified.
    for ins in ref['instruments']:ins['taker_fee']='.6'
    i=make_intent(ref,at_ms=at,collar_bps='50',ttl_ms=600000,predecessor_plan_id='a'*64)
    d=materialize(i,ref,c,now_ms=at)
    monkeypatch.setattr(venue,'prepare_micro_plan',lambda *_:copy.deepcopy(d['plan']))
    monkeypatch.setattr(v2,'verify_materialization',lambda *_:None)
    class HarnessOwner(BoundedOwner):
        def accept_go(self,text):
            assert text=='GO KITY_EXECUTION_MICRO_LIVE '+self.journal.plan['plan_id']
            self.accept_intent_go('GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id'])
    def factory(*args,**kwargs):
        store=Path(args[3]);publish(store/'intent-claim.json',dict(intent_id=i['intent_id'],
            owner_go_text='GO KITY_EXECUTION_MICRO_INTENT_V2 '+i['intent_id'],at_ms=at))
        return HarnessOwner(*args,**kwargs,dossier=d,wire_root=tmp_path/'wire')
    monkeypatch.setattr(venue,'PhysicalOwner',factory)
    # Base fixture uses MicroJournal; use the compatible extended reducer.
    monkeypatch.setattr(venue,'MicroJournal',JournalV2)
    venue.test_concrete_owner_all_ten_native_restart_deadline_and_actual_cash_path(tmp_path,monkeypatch)
