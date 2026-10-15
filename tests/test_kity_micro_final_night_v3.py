import copy,json,hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_lab import kity_micro_bounded_owner_v2 as bo
from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError
from research_lab.kity_micro_physical_owner_v1 import publish
from test_kity_micro_transport_v1 import Wire,client
from test_kity_micro_account_bridge_v1 import journal
from test_kity_micro_runtime_v1 import enter,exit_leg,flat,event


def test_account_instrument_eligibility_is_an_authenticated_get_only_surface():
    w=Wire();cap=client(w).get('/v5/account/instruments-info',dict(category='linear',symbol='XAUUSDT'))
    assert cap['signed'] and w.calls[0][0]=='GET' and w.calls[0][3] is None


def prior(tmp_path):
    store=tmp_path/'old';store.mkdir();j=journal(store);symbol=j.plan['legs'][0]['symbol']
    enter(j,symbol);j.append(event('UNWIND',reason='partial basket'));exit_leg(j,symbol);flat(j)
    j.append(event('FINALITY',net_cash_usdt='-.02',funding_complete=True));plan=j.plan;j.close()
    (store/'j.sqlite').rename(store/'lifecycle.sqlite')
    publish(store/'active-plan.json',dict(plan=plan))
    publish(store/'owner-go.json',dict(exact_go='GO KITY_EXECUTION_MICRO_LIVE '+plan['plan_id']))
    publish(store/'receipt.json',dict(phase='TERMINAL',plan_id=plan['plan_id'],terminal_net_usdt='-.02',broker_flat_proven=True))
    pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in store.iterdir() if p.is_file()}
    return dict(runtime_root=str(tmp_path/'night-final-20261015'),predecessor_store=str(store),
        predecessor_kind='ACCOUNTED_MICRO_TERMINAL',predecessor_plan_id=plan['plan_id'],
        predecessor_receipt=str(store/'receipt.json'),predecessor_files=pins)


def test_filled_terminal_predecessor_is_pinned_and_never_mutated(tmp_path):
    config=prior(tmp_path);before={p:Path(p).read_bytes() for p in config['predecessor_files']}
    state=bo.read_predecessor(config)
    assert state['phase']=='TERMINAL' and state['terminal_net_usdt']=='-0.02'
    assert before=={p:Path(p).read_bytes() for p in before}
    Path(config['predecessor_receipt']).write_text('{}')
    with pytest.raises(SourceError,match='PREDECESSOR_SOURCE_DRIFT'):bo.read_predecessor(config)


def test_new_epoch_uses_original_custody_not_a_new_lock(tmp_path):
    function=getattr(bo,'runtime_roots',None);assert callable(function)
    original=tmp_path/'runtime';new=original/'night-final-20261015'
    config=dict(runtime_root=str(new),custody_runtime_root=str(original),operation_scope='ONE_FINAL_NIGHT_2026_10_15',
        predecessor_kind='ACCOUNTED_MICRO_TERMINAL')
    assert function(config)==(new,original)
    with pytest.raises(SourceError):function(dict(config,runtime_root=str(tmp_path/'elsewhere')))
    with pytest.raises(SourceError):function(dict(config,operation_scope='retry_forever'))


def test_terminal_orders_off_requires_real_terminal_flat_cost_completion(tmp_path):
    config=prior(tmp_path);state=bo.read_predecessor(config)
    function=getattr(bo,'terminal_orders_off',None);assert callable(function)
    assert function(state)
    for mutation in ({'phase':'UNWINDING'},{'broker_flat_proven':False},{'fee_unknown_execution_ids':['unknown']},
                     {'held':{'BTWUSDT':'1'}},{'ownership_conflict':True},{'terminal_net_usdt':None}):
        bad=copy.deepcopy(state);bad.update(mutation);assert not function(bad)


def test_successful_empty_error_list_is_not_owner_reported_error(tmp_path):
    supervisor=bo.BoundedSupervisor.__new__(bo.BoundedSupervisor)
    config=prior(tmp_path);state=bo.read_predecessor(config)
    supervisor.root=tmp_path/'new';supervisor.custody_root=tmp_path/'original';supervisor.config={}
    supervisor.journal=SimpleNamespace(snapshot=lambda:state);supervisor.owner=SimpleNamespace(_authorized=True)
    supervisor.lease=SimpleNamespace(inode=818853)
    supervisor.heartbeat([])
    h=json.loads((supervisor.custody_root/'heartbeat.json').read_bytes())
    assert h['mode']=='ORDERS_OFF' and h['error'] is None
    supervisor.heartbeat(['REAL_FAILURE'])
    assert json.loads((supervisor.custody_root/'heartbeat.json').read_bytes())['error']==['REAL_FAILURE']


def instrument_cap(symbol='XAUUSDT'):
    return dict(http_status=200,body=dict(retCode=0,result=dict(category='linear',list=[dict(
        symbol=symbol,status='Trading',contractType='LinearPerpetual',quoteCoin='USDT',settleCoin='USDT',
        unifiedMarginTrade=True,isPreListing=False,priceFilter=dict(tickSize='.01'),
        lotSizeFilter=dict(minOrderQty='.001',maxOrderQty='100',maxMktOrderQty='100',qtyStep='.001',minNotionalValue='5'))])))


def test_account_available_is_not_claimed_to_be_a_successful_create():
    function=getattr(bo,'account_instrument_available',None);assert callable(function)
    result=function(instrument_cap(),'XAUUSDT')
    assert result['account_instrument_available'] is True
    assert result['create_acceptance_proven'] is False and result['terms_acceptance_proven'] is False
    for key,value in [('symbol','WRONGUSDT'),('status','PendingOpen'),('unifiedMarginTrade',1),('isPreListing',True)]:
        cap=instrument_cap();cap['body']['result']['list'][0][key]=value
        with pytest.raises(SourceError):function(cap,'XAUUSDT')


def test_missing_selection_with_new_wire_or_experiment_history_cannot_prepare(tmp_path):
    function=getattr(bo,'check_unselected_history',None);assert callable(function)
    root=tmp_path/'epoch';custody=tmp_path/'custody';(custody/'wire').mkdir(parents=True)
    config=dict(operation_scope='ONE_FINAL_NIGHT_2026_10_15',wire_baseline_files={})
    function(root,custody,config)
    (custody/'wire/send-new.json').write_text('{}')
    with pytest.raises(SourceError,match='MISSING_SELECTED_STATE'):function(root,custody,config)
    (custody/'wire/send-new.json').unlink()
    actual=root/'experiments-v2'/('a'*64);actual.mkdir(parents=True);(actual/'intent-claim.json').write_text('{}')
    with pytest.raises(SourceError,match='MISSING_SELECTED_STATE'):function(root,custody,config)


def test_final_namespace_constructor_keeps_original_lock_wire_and_health(tmp_path,monkeypatch):
    config=prior(tmp_path);custody=tmp_path/'custody';custody.mkdir();(custody/'account.lock').touch()
    config.update(runtime_root=str(custody/'night-final-20261015'),custody_runtime_root=str(custody),
        operation_scope='ONE_FINAL_NIGHT_2026_10_15',wire_baseline_files={},
        account_lock_inode=(custody/'account.lock').stat().st_ino)
    monkeypatch.setattr(bo,'load_bound_credentials',lambda c:('test-key','test-secret'))
    monkeypatch.setattr(bo,'platform_verifier',lambda c:lambda:None)
    s=bo.BoundedSupervisor(config)
    try:
        assert s.lease.path==custody/'account.lock' and s.writer.store==custody/'wire'
        assert not (s.root/'account.lock').exists() and s.previous['phase']=='TERMINAL'
        s.heartbeat();h=json.loads((custody/'heartbeat.json').read_bytes())
        assert h['mode']=='ORDERS_OFF' and h['phase']=='NO_ACTIVE_PLAN' and h['error'] is None
    finally:s.lease.close()


def test_all_ten_signed_native_lifecycle_with_account_instrument_reads(tmp_path,monkeypatch):
    import urllib.parse
    import test_kity_micro_physical_e2e_v1 as venue
    import test_kity_micro_bounded_owner_v2 as bounded
    checked=[];original=venue.BybitReadTransport
    class AccountAwareTransport(original):
        def __init__(self,key,secret,*,wire,clock):
            def extra(method,url,headers,data,timeout):
                parsed=urllib.parse.urlparse(url)
                if parsed.path=='/v5/account/instruments-info':
                    p=dict(urllib.parse.parse_qsl(parsed.query));checked.append(p['symbol'])
                    body=instrument_cap(p['symbol'])['body'];body['time']=clock()
                    return 200,json.dumps(body).encode()
                return wire(method,url,headers,data,timeout)
            super().__init__(key,secret,wire=extra,clock=clock)
    class AccountAwareOwner(bo.BoundedOwner):require_account_instruments=True
    monkeypatch.setattr(venue,'BybitReadTransport',AccountAwareTransport)
    monkeypatch.setattr(bounded,'BoundedOwner',AccountAwareOwner)
    bounded.test_v2_full_concrete_venue_ten_native_stops_and_exit_after_intent_expiry(tmp_path,monkeypatch)
    assert checked==[s for s,_ in bo.rt.BASKET]
