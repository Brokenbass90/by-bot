import copy
import json
from decimal import Decimal

import pytest

from bot.kity_m3_orders_off import digest
from research_lab import kity_batch_ws_v1 as batch
from research_lab.kity_execution_micro_runtime_v1 import prepare_micro_plan,MicroJournal
from test_kity_micro_runtime_v1 import dossier,event
from test_kity_micro_integration_v3 import V3


def plan():
    d=dossier()
    for leg in d['profiles'][0]['legs']:
        leg['draft_entry'].update(stopLoss='.9' if leg['side']=='Buy' else '1.1',
            slTriggerBy='LastPrice',slOrderType='Market',tpslMode='Full')
    return prepare_micro_plan(d,V3)


def journal(tmp_path):return batch.BatchJournal(tmp_path/'batch.sqlite',plan())


def test_all_ten_intents_are_one_durable_event_before_wire(tmp_path):
    j=journal(tmp_path);p=j.plan;body=batch.payload(p)
    assert len(body['request'])==10 and body['category']=='linear'
    assert all('category' not in r for r in body['request'])
    assert batch.commit_intent(j,at_ms=2100)
    s=j.snapshot();assert len(s['entries'])==10
    assert s['first_send_ms']==2100 and s['deadline_ms']==1802100
    assert j.db.execute('SELECT count(*) FROM events').fetchone()[0]==1
    j.close();j=batch.BatchJournal(tmp_path/'batch.sqlite',p)
    assert len(j.snapshot()['entries'])==10
    with pytest.raises(ValueError):batch.commit_intent(j,at_ms=2101)


def test_old_journal_is_not_changed_to_allow_unprotected_sequential_entries(tmp_path):
    p=plan();j=MicroJournal(tmp_path/'old.sqlite',p)
    for n in range(2):
        e=event('ENTRY_INTENT',symbol=p['legs'][n]['symbol']);e['event_id']='entry'+str(n)
        if n==0:j.append(e)
        else:
            with pytest.raises(ValueError,match='RECONCILIATION'):j.append(e)


def ack(p,code_index=None):
    return dict(retCode=0,result=dict(list=[dict(symbol=l['symbol'],orderLinkId=l['request']['orderLinkId'],
        orderId='' if i==code_index else 'order-'+str(i)) for i,l in enumerate(p['legs'])]),
        retExtInfo=dict(list=[dict(code=10001 if i==code_index else 0,msg='') for i in range(10)]))


def test_batch_ack_is_not_ten_fills_or_protection(tmp_path):
    j=journal(tmp_path);batch.commit_intent(j,at_ms=2000)
    r=batch.apply_ack(j,ack(j.plan),at_ms=2100)
    s=j.snapshot()
    assert r['status']=='BATCH_ACK_RECONCILE_REQUIRED' and len(s['fills'])==0
    assert all(v=='0' for v in s['held'].values()) and all(o['protected']=='0' for o in s['entries'].values())


def test_partial_rejection_blocks_entries_and_keeps_all_owned_ids(tmp_path):
    j=journal(tmp_path);batch.commit_intent(j,at_ms=2000)
    batch.apply_ack(j,ack(j.plan,3),at_ms=2100)
    s=j.snapshot()
    assert s['entry_blocked'] and s['phase']=='UNWINDING'
    assert s['entries'][j.plan['legs'][3]['symbol']]['definite_rejection']==10001
    assert sum(o['order_id'] is not None for o in s['entries'].values())==9


def test_lost_batch_response_is_one_send_and_never_retried(tmp_path):
    calls=[]
    def wire(*args):calls.append(args);raise TimeoutError()
    w=batch.BatchSignedPostOnce('fixture-key','fixture-secret',tmp_path,wire=wire,clock=lambda:2000)
    with pytest.raises(TimeoutError):w.post('/v5/order/create-batch',batch.payload(plan()))
    with pytest.raises(ValueError):w.post('/v5/order/create-batch',batch.payload(plan()))
    assert len(calls)==1
    assert 'fixture-secret' not in ''.join(p.read_text() for p in tmp_path.iterdir())


def test_default_orders_off_does_not_call_owner_or_create_an_intent(tmp_path):
    j=journal(tmp_path);calls=[]
    class Owner:
        def assert_exclusive(self,*a):calls.append(1)
    out=batch.dispatch_batch(j,Owner(),now_ms=2100)
    assert out['status']=='BATCH_ORDERS_OFF' and not calls and not j.snapshot()['entries']


@pytest.mark.parametrize('change',[{'qty':'999'},{'stopLoss':None},{'reduceOnly':True}])
def test_rehashed_batch_cannot_escape_caps_or_native_guard(change):
    p=plan();p['legs'][0]['request'].update(change)
    p['plan_id']=digest({k:v for k,v in p.items() if k!='plan_id'})
    with pytest.raises(ValueError):batch.payload(p)


def test_rest_barrier_required_after_every_private_ws_disconnect(tmp_path):
    inbox=batch.PrivateInbox(tmp_path)
    inbox.connected('connection1');inbox.authenticated();inbox.subscribed()
    assert not inbox.ready
    inbox.rest_reconciled();assert inbox.ready
    inbox.disconnected('socket_lost');assert not inbox.ready
    inbox.connected('connection2');inbox.authenticated();inbox.subscribed();assert not inbox.ready


def test_private_sender_never_accepts_trade_ops_or_trade_url():
    s=batch.PrivateSession('fixture-key','fixture-secret',clock=lambda:2000)
    for frame in ({'op':'order.create'},{'op':'subscribe','args':['order','order.linear']},{'op':'subscribe','args':['execution.fast']}):
        with pytest.raises(ValueError):s.validate_outbound(frame)
    with pytest.raises(ValueError):batch.PrivateSession('k','s',url='wss://stream.bybit.com/v5/trade')
    assert s.auth_frame()['op']=='auth'


def test_ws_execution_before_ack_and_duplicate_message_do_not_duplicate_cash(tmp_path):
    j=journal(tmp_path);batch.commit_intent(j,at_ms=2000);leg=j.plan['legs'][0]
    inbox=batch.PrivateInbox(tmp_path/'inbox');inbox.connected('a');inbox.authenticated();inbox.subscribed();inbox.rest_reconciled()
    row=dict(category='linear',symbol=leg['symbol'],orderId='order-0',orderLinkId=leg['request']['orderLinkId'],
        side=leg['side'],execType='Trade',execId='exec-1',execQty='1',execPrice='1.02',execFee='.001',execTime='2000')
    msg=dict(topic='execution.linear',creationTime=2100,data=[row])
    inbox.ingest(msg,observed_ms=2100);inbox.ingest(dict(msg,id='duplicate-envelope'),observed_ms=2101)
    inbox.project(j)
    assert j.snapshot()['held'][leg['symbol']]=='1' and len(j.snapshot()['fills'])==1
    assert Decimal(j.snapshot()['fees_usdt'])==Decimal('.001')


def test_foreign_ws_order_is_retained_but_never_adopted(tmp_path):
    j=journal(tmp_path);batch.commit_intent(j,at_ms=2000)
    inbox=batch.PrivateInbox(tmp_path/'inbox');inbox.connected('a')
    inbox.ingest(dict(topic='order.linear',creationTime=2100,data=[dict(orderId='foreign',orderLinkId='ATT1-foreign',symbol='BTWUSDT')]),observed_ms=2100)
    inbox.project(j)
    assert len(j.snapshot()['fills'])==0 and all(v['order_id'] is None for v in j.snapshot()['entries'].values())


def test_seq_is_not_assumed_globally_unique_or_contiguous(tmp_path):
    j=journal(tmp_path);batch.commit_intent(j,at_ms=2000)
    inbox=batch.PrivateInbox(tmp_path/'inbox');inbox.connected('a')
    rows=[]
    for i in range(2):
        l=j.plan['legs'][i]
        rows.append(dict(category='linear',symbol=l['symbol'],orderId='id'+str(i),orderLinkId=l['request']['orderLinkId'],side=l['side'],
            execType='Trade',execId='e'+str(i),execQty='1',execPrice='1',execFee='0',execTime='2000',seq=900))
    inbox.ingest(dict(topic='execution.linear',creationTime=2100,data=rows),observed_ms=2100);inbox.project(j)
    assert len(j.snapshot()['fills'])==2


@pytest.mark.parametrize('change', ['missing', 'duplicate_link', 'duplicate_id', 'top_timeout', 'bool_code'])
def test_ambiguous_ack_never_becomes_fill_or_retry(tmp_path,change):
    j=journal(tmp_path);batch.commit_intent(j,at_ms=2000);response=ack(j.plan)
    if change=='missing':response['result']['list'].pop()
    elif change=='duplicate_link':response['result']['list'][1]['orderLinkId']=response['result']['list'][0]['orderLinkId']
    elif change=='duplicate_id':response['result']['list'][1]['orderId']=response['result']['list'][0]['orderId']
    elif change=='top_timeout':response['retCode']=10000
    else:response['retExtInfo']['list'][2]['code']=False
    batch.apply_ack(j,response,at_ms=2100)
    assert j.snapshot()['entry_blocked'] and not j.snapshot()['fills']
    assert all(a['kind']!='ENTRY' for a in j.actions(2200))


def test_batch_cannot_convert_or_modify_a_legacy_journal(tmp_path):
    p=plan();path=tmp_path/'old.sqlite';j=MicroJournal(path,p);j.close()
    raw=path.read_bytes()
    with pytest.raises(ValueError,match='LEGACY'):batch.BatchJournal(path,p)
    assert path.read_bytes()==raw


def test_restart_and_partial_basket_keep_existing_scoped_unwind(tmp_path):
    from research_lab.kity_micro_supervisor_v1 import recover_without_reentry
    from test_kity_micro_runtime_v1 import fill,terminal,exit_leg,flat
    j=journal(tmp_path);batch.commit_intent(j,at_ms=2000)
    for i,l in enumerate(j.plan['legs']):
        if i==3:
            j.append(event('DISPATCH_REJECTED',symbol=l['symbol'],order_link_id=l['request']['orderLinkId'],ret_code=10001))
        else:
            fill(j,l['symbol']);terminal(j,l['symbol'])
    p=j.plan;j.close();j=batch.BatchJournal(tmp_path/'batch.sqlite',p)
    recover_without_reentry(j,2100)
    actions=j.actions(2200)
    assert len(actions)==9 and all(a['kind']=='EXIT' and a['request']['reduceOnly'] is True for a in actions)
    for a in actions:exit_leg(j,a['symbol'])
    flat(j)
    assert j.snapshot()['broker_flat_proven'] and all(a['kind']!='ENTRY' for a in j.actions(2300))


def test_atomic_ten_lifecycle_retains_accounting_finality_and_rounding(tmp_path):
    from test_kity_micro_runtime_v1 import fill,terminal,protect,exit_leg,flat
    j=journal(tmp_path);batch.commit_intent(j,at_ms=2000)
    for l in j.plan['legs']:
        s=l['symbol'];fill(j,s);terminal(j,s);protect(j,s)
    assert j.actions(2100)[0]['kind']=='MONITOR'
    j.append(event('UNWIND',reason='30_MIN_TEST'))
    for l in j.plan['legs']:exit_leg(j,l['symbol'])
    flat(j);j.append(event('FINALITY',funding_complete=True,net_cash_usdt='-.20'))
    s=j.snapshot();assert s['all_ten_complete'] and s['terminal_net_usdt']=='-0.20'
    assert s['leg_rounding_shortfalls'] and not s['counts_toward_C1_C2_C3']


def test_existing_legacy_go_cannot_authorize_batch(tmp_path):
    from research_lab.kity_micro_post_go_pricing_v1 import make_policy,GO_PREFIX
    from research_lab.kity_micro_transport_v1 import SourceError
    policy=make_policy(created_ms=1000,valid_until_ms=100000,physical_config_sha256='a'*64,
                       predecessor_plan_id='b'*64,bounds=V3)
    b=batch.make_batch_policy(policy);calls=[]
    with pytest.raises(SourceError,match='NEW_EXACT_BATCH_GO'):
        batch.consume_batch_policy_once(tmp_path,b,GO_PREFIX+policy['policy_id'],2000,lambda:calls.append(1),clock=lambda:2100)
    assert not calls and not list(tmp_path.iterdir())


def test_private_socket_auth_subscribe_and_no_rest_before_entry(tmp_path):
    class Socket:
        def __init__(self):
            self.out=[];self.frames=iter([json.dumps(dict(op='auth',success=True)),json.dumps(dict(op='subscribe',success=True))])
        def send(self,f):self.out.append(json.loads(f))
        def recv(self,timeout):return next(self.frames)
        def close(self):pass
    socket=Socket();inbox=batch.PrivateInbox(tmp_path)
    feed=batch.PrivateFeed(batch.PrivateSession('k','secret',clock=lambda:2000),inbox,
        connect=lambda *a,**k:socket,clock=lambda:2000)
    result=feed.open()
    assert result['authenticated'] and [f['op'] for f in socket.out]==['auth','subscribe']
    assert not inbox.ready
    inbox.rest_reconciled();assert inbox.transport_fresh(2000) and not inbox.transport_fresh(22001)
    feed.close();assert not inbox.ready
    assert not list(tmp_path.iterdir()),'auth headers/frames are never stored'


def test_fresh_view_fetches_each_route_once_no_new_get_in_ten_preflights():
    calls=[]
    class Reader:
        def get(self,path,params):calls.append((path,params));return dict(path=path,params=params)
        def result(self,cap):return cap
    p=plan();view=batch.FreshBatchView(Reader(),p);before=len(calls)
    for _ in p['legs']:
        view.get('/v5/account/info',{})
        for l in p['legs']:view.get('/v5/market/orderbook',dict(category='linear',symbol=l['symbol'],limit='50'))
    assert len(calls)==before==65
    assert sum(p=='/v5/account/info' for p,v in calls)==1
    with pytest.raises(ValueError):view.get('/v5/order/create',{})


def test_batch_owner_real_lease_claim_and_restart_never_reenter(tmp_path,monkeypatch):
    from research_lab.kity_micro_physical_owner_v1 import AccountLease,publish
    from research_lab.kity_micro_post_go_pricing_v1 import compile_after_go
    from test_kity_micro_post_go_pricing_v1 import policy,fresh
    p=policy();d,c=fresh();out=compile_after_go(p,d,c,go_ms=4999800,now_ms=5000001)
    b=batch.make_batch_policy(p);store=tmp_path/'owner';store.mkdir();clock=[5000010];calls=[]
    # Only the saved-source parser boundary is substituted, as in the existing
    # owner harness; real journal/lease/exact GO/claim/restart code runs below.
    monkeypatch.setattr(batch,'verify_compilation',lambda _:None)
    j=batch.BatchJournal(tmp_path/'j.sqlite',out['plan']);inbox=batch.PrivateInbox(tmp_path/'inbox')
    inbox.connected('a');inbox.authenticated();inbox.subscribed();inbox.rest_reconciled();inbox.last_receive_ms=clock[0]
    lease=AccountLease(tmp_path/'account.lock')
    o=batch.BatchPhysicalOwner(j,None,lease,store,platform_check=lambda:None,post=lambda *a:calls.append(a),
        clock=lambda:clock[0],dossier=out,batch_policy=b,inbox=inbox)
    with pytest.raises(ValueError):o.accept_go('GO KITY_EXECUTION_MICRO_LIVE '+j.plan['plan_id'])
    with pytest.raises(ValueError):o.accept_batch_go(batch.GO_PREFIX+b['batch_policy_id'])
    publish(store/'batch-policy-claim.json',dict(batch_policy_id=b['batch_policy_id'],
        exact_go=batch.GO_PREFIX+b['batch_policy_id'],go_ms=4999800))
    o.accept_batch_go(batch.GO_PREFIX+b['batch_policy_id'])
    assert o._authorized and not calls
    batch.commit_intent(j,at_ms=clock[0]);clock[0]+=100000;o._authorized=False;o.recover_go()
    assert o._authorized and j.snapshot()['entry_blocked']
    with pytest.raises(ValueError):o.entry_fence()
    with pytest.raises(ValueError):batch.commit_intent(j,at_ms=clock[0])
    assert not calls
    lease.close()


def test_stale_or_disconnected_stream_blocks_after_intent_before_wire(tmp_path,monkeypatch):
    # Real final send fence, deliberately no valid source ticket: no transport.
    o=batch.BatchPhysicalOwner.__new__(batch.BatchPhysicalOwner);j=journal(tmp_path)
    o.journal=j;o.clock=lambda:22001;o._authorized=True;o._batch_ticket=None;o.store=tmp_path
    o.dossier={'post_go_go_ms':1000};o.batch_policy={'base_policy':{'created_ms':1,'valid_until_ms':100000,'dispatch_window_ms':60000}}
    o.lease=type('Lease',(),{'path':tmp_path/'lock'})();o.inbox=batch.PrivateInbox(tmp_path/'inbox')
    o.inbox.connected('a');o.inbox.authenticated();o.inbox.subscribed();o.inbox.rest_reconciled();o.inbox.last_receive_ms=2000
    calls=[];o.post=lambda *a:calls.append(a);monkeypatch.setattr(o,'assert_exclusive',lambda *_:None)
    batch.commit_intent(j,at_ms=2000)
    with pytest.raises(ValueError,match='STREAM'):o.post_once('/v5/order/create-batch',batch.payload(j.plan))
    assert not calls


def test_proven_final_fence_no_wire_can_finish_flat_without_fake_broker_rejection(tmp_path):
    j=journal(tmp_path)
    class Owner:
        clock=staticmethod(lambda:2100)
        def assert_exclusive(self,p):pass
        def validate_batch(self,p,r):pass
        def post_once(self,*a):
            self.batch_no_wire_proof=dict(status='FINAL_FENCE_NO_WIRE',plan_id=j.plan['plan_id'],at_ms=2100)
            raise ValueError('EXPIRED_BEFORE_TRANSPORT')
    r=batch.dispatch_batch(j,Owner(),now_ms=2100,apply=True)
    assert r['status']=='BATCH_NO_SEND_REQUIRES_FLAT_READBACK'
    assert j.actions(2200)[0]['kind']=='FINALITY_READBACK'
    assert all(o['local_not_sent'] and 'definite_rejection' not in o for o in j.snapshot()['entries'].values())


def test_unknown_wire_failure_keeps_ten_pending_ids_for_rest_not_safe_flat(tmp_path):
    j=journal(tmp_path)
    class Owner:
        clock=staticmethod(lambda:2100)
        def assert_exclusive(self,p):pass
        def validate_batch(self,p,r):pass
        def post_once(self,*a):raise TimeoutError()
    r=batch.dispatch_batch(j,Owner(),now_ms=2100,apply=True)
    assert r['status']=='BATCH_UNKNOWN_RECONCILE_REQUIRED'
    assert len(j.actions(2200))==10 and all(a['kind']=='RECONCILE' for a in j.actions(2200))
    assert not j.snapshot()['broker_flat_proven']


def test_actual_signed_get_fresh_ticket_and_batch_post_path(tmp_path,monkeypatch):
    """Synthetic exchange wire; actual credential signing, GO, lease and gates."""
    from urllib.parse import urlsplit,parse_qsl
    from research_lab.kity_micro_transport_v1 import BybitReadTransport
    from research_lab.kity_micro_physical_owner_v1 import AccountLease,publish
    from research_lab.kity_micro_post_go_pricing_v1 import compile_after_go
    from test_kity_micro_post_go_pricing_v1 import policy,fresh
    p=policy();d,c=fresh();out=compile_after_go(p,d,c,go_ms=4999800,now_ms=5000001)
    b=batch.make_batch_policy(p);clock=[5000010];calls=[]
    def wire(method,url,headers,data,timeout):
        path=urlsplit(url).path;params=dict(parse_qsl(urlsplit(url).query));s=params.get('symbol')
        calls.append((method,path,params))
        if method=='POST':
            assert path=='/v5/order/create-batch' and headers['X-BAPI-SIGN']
            assert json.loads(data)==batch.payload(out['plan'])
            return 200,json.dumps(ack(out['plan'])).encode()
        if path=='/v5/user/query-api':r=dict(readOnly=0,permissions=dict(ContractTrade=['Order','Position']))
        elif path=='/v5/account/info':r=dict(marginMode='REGULAR_MARGIN',unifiedMarginStatus=5)
        elif path=='/v5/account/wallet-balance':r=dict(list=[dict(totalAvailableBalance='1000')])
        elif path in ('/v5/market/instruments-info','/v5/account/instruments-info'):
            r=dict(category='linear',list=[dict(symbol=s,contractType='LinearPerpetual',status='Trading',
                quoteCoin='USDT',settleCoin='USDT',unifiedMarginTrade=True,isPreListing=False,
                lotSizeFilter=dict(minOrderQty='.001',maxOrderQty='10000',maxMktOrderQty='10000',minNotionalValue='.1',qtyStep='.001'),
                priceFilter=dict(tickSize='.0001'))])
        elif path=='/v5/order/realtime':r=dict(list=[],nextPageCursor='')
        elif path=='/v5/position/list':r=dict(list=[dict(symbol=s,positionIdx=0,isReduceOnly=False,size='0')] if s else [],nextPageCursor='')
        elif path=='/v5/account/fee-rate':r=dict(list=[dict(symbol=s,takerFeeRate='.00055')])
        elif path=='/v5/market/tickers':r=dict(list=[dict(symbol=s,lastPrice='.95')])
        elif path=='/v5/market/orderbook':r=dict(s=s,b=[['.95','1000']],a=[['.95','1000']],cts=clock[0])
        else:raise AssertionError(path)
        return 200,json.dumps(dict(retCode=0,result=r,time=clock[0])).encode()
    # Only disk-source parsing is substituted. All actual signed GET adapters
    # and all ten unchanged account/instrument/CTS/cap validators run.
    monkeypatch.setattr(batch,'verify_compilation',lambda _:None)
    store=tmp_path/'owner';store.mkdir();j=batch.BatchJournal(tmp_path/'batch.sqlite',out['plan'])
    inbox=batch.PrivateInbox(tmp_path/'inbox');inbox.connected('a');inbox.authenticated();inbox.subscribed();inbox.rest_reconciled();inbox.last_receive_ms=clock[0]
    reader=BybitReadTransport('fixture-key','fixture-secret',wire=wire,clock=lambda:clock[0])
    writer=batch.BatchSignedPostOnce('fixture-key','fixture-secret',tmp_path/'wire',wire=wire,clock=lambda:clock[0])
    lease=AccountLease(tmp_path/'account.lock')
    o=batch.BatchPhysicalOwner(j,reader,lease,store,platform_check=lambda:None,post=writer.post,
        clock=lambda:clock[0],dossier=out,batch_policy=b,inbox=inbox)
    publish(store/'batch-policy-claim.json',dict(batch_policy_id=b['batch_policy_id'],
        exact_go=batch.GO_PREFIX+b['batch_policy_id'],go_ms=4999800))
    o.accept_batch_go(batch.GO_PREFIX+b['batch_policy_id'])
    result=batch.dispatch_batch(j,o,now_ms=clock[0],apply=True)
    assert result['status']=='BATCH_ACK_RECONCILE_REQUIRED'
    assert sum(m=='POST' for m,_,_ in calls)==1 and sum(m=='GET' for m,_,_ in calls)==65
    assert not j.snapshot()['fills'] and len(j.snapshot()['entries'])==10
    before=len(calls)
    with pytest.raises(ValueError):batch.dispatch_batch(j,o,now_ms=clock[0],apply=True)
    assert len(calls)==before
    lease.close()


def test_aggregate_sell_price_improvement_cannot_exceed_gross_cap():
    p=plan()
    for l in p['legs']:l['quantity']=l['request']['qty']='20'
    p['planned_limit_gross_usdt']=p['reference_gross_usdt']='200'
    p['plan_id']=digest({k:v for k,v in p.items() if k!='plan_id'})
    class View:
        def get(self,path,params):
            if path in ('/v5/order/realtime','/v5/position/list'):return dict(list=[],nextPageCursor='')
            if path=='/v5/account/fee-rate':return dict(list=[dict(symbol=params['symbol'],takerFeeRate='.001')])
            if path=='/v5/account/wallet-balance':return dict(list=[dict(totalAvailableBalance='1000')])
            return dict(s=params['symbol'],b=[['1.2','1000']],a=[['1','1000']])
        result=staticmethod(lambda cap:cap)
    with pytest.raises(ValueError,match='AGGREGATE_FRESH_GROSS'):batch.validate_batch_account_and_gross(View(),p)


def test_deployed_source_verifier_is_no_network_and_rejects_drift(tmp_path,capsys):
    from scripts.verify_kity_batch_ws_orders_off_v1 import main
    assert main([])==0
    assert 'NO_NETWORK' in capsys.readouterr().out
    app=tmp_path/'app';app.mkdir();src=app/'candidate.py';src.write_text('source')
    spec=dict(schema='TRADING_OS_DISABLED_CANDIDATE_V1',component='kity-batch-ws',default_orders_off=True,
        monetary_transport_bound=False,new_policy_issued=False,old_go_reused=False,files={'candidate.py':batch.sha(b'source')})
    raw=json.dumps(spec).encode();p=tmp_path/'spec.json';p.write_bytes(raw)
    args=['--spec',str(p),'--spec-sha256',batch.sha(raw)]
    assert main(args)==0
    src.write_text('drift')
    with pytest.raises(ValueError,match='DRIFT'):main(args)


def test_old_committed_ws_native_row_does_not_reexpand_stop_on_replay(tmp_path):
    from test_kity_micro_runtime_v1 import fill,terminal
    j=journal(tmp_path);batch.commit_intent(j,at_ms=2000);l=j.plan['legs'][0];s=l['symbol']
    fill(j,s);terminal(j,s)
    j.append(event('NATIVE_PROTECTION_BIND',symbol=s,quantity='1',order_id='sl-0',trigger_price='.9',
                   side='Sell',reduce_only=True,position_idx=0))
    inbox=batch.PrivateInbox(tmp_path/'inbox');inbox.connected('a')
    row=dict(category='linear',symbol=s,orderId='sl-0',orderLinkId='',side='Sell',qty='1',
        reduceOnly=True,positionIdx=0,orderType='Market',stopOrderType='StopLoss',orderStatus='Untriggered',cumExecQty='0',triggerPrice='.9')
    inbox.ingest(dict(topic='order.linear',data=[row]),observed_ms=2100);inbox.project(j)
    native=j.snapshot()['exits'][l['exit_prefix']+'-SL']
    j.append(event('NATIVE_PROTECTION_RESIZE',symbol=s,order_link_id=native['link'],order_id='sl-0',quantity='.5'))
    inbox.project(j)
    assert j.snapshot()['exits'][native['link']]['quantity']=='0.5'
