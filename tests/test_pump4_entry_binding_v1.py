"""Delayed entry is explicit, source-bound and never inherits legacy GO."""
import copy
from decimal import Decimal as D
import pytest
from test_pump4_native_stop_v1 import material
from test_pump4_bybit_sources_v1 import capture

def entry_material(now=7230000,side='short'):
    from research_lab.pump4_entry_binding_v1 import execution_policy
    p,i,t=material(side);t.update(lastPrice='100.02',bid1Price='100.02',ask1Price='100.03')
    tick=capture('/v5/market/tickers',dict(category='linear'),dict(category='linear',list=[t]))
    path=capture('/v5/market/kline',dict(category='linear',symbol=p['symbol'],interval='60',start=7200000,end=10799999,limit=1),dict(category='linear',symbol=p['symbol'],list=[['7200000','100','100.04','99.99','100.02','10','1000']]))
    import json,hashlib
    for c in (tick,path):
        c.update(request_ms=now-2,receive_ms=now-1);c['body']['time']=now-2;c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest()
    policy=execution_policy(dict(risk_usdt='1'),max_reference_drift_bps='10')
    return p,i,t,dict(quote=tick,entry_interval=path),policy

def test_explicit_30s_binding_preserves_reference_and_original_deadline():
    from research_lab.pump4_entry_binding_v1 import bind_entry,verify_binding
    p,i,t,public,policy=entry_material();before=copy.deepcopy(p)
    b=bind_entry(p,policy,public,'103.8',now_ms=7230000)
    assert b['valid_until_ms']==7260000 and b['reference_entry']=='100.0' and p==before
    assert b['execution_quote_price']=='100.02' and b['reference_drift_bps']!='0'
    assert verify_binding(p,b,now_ms=7230001)==b
    with pytest.raises(ValueError,match='DEADLINE'):verify_binding(p,b,now_ms=7260001)

@pytest.mark.parametrize('fault',['past60','stale','future','drift','stop_touch','tp_touch','missing','tamper'])
def test_invalid_delayed_entry_is_fail_closed(fault):
    from research_lab.pump4_entry_binding_v1 import bind_entry,verify_binding
    import json,hashlib
    p,i,t,public,policy=entry_material();now=7230000
    if fault=='past60':now=7260001
    elif fault=='stale':now+=6000
    elif fault=='future':now-=6000
    elif fault=='missing':public.pop('entry_interval')
    else:
        if fault=='drift':public['quote']['body']['result']['list'][0]['bid1Price']='100.2'
        elif fault=='stop_touch':public['entry_interval']['body']['result']['list'][0][2]='104'
        elif fault=='tp_touch':public['entry_interval']['body']['result']['list'][0][3]='97'
        for c in public.values():c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest()
    with pytest.raises((ValueError,KeyError)):
        b=bind_entry(p,policy,public,'103.8',now_ms=now)
        if fault=='tamper':b['max_delay_ms']=300000;verify_binding(p,b,now_ms=now)

def test_side_specific_executable_quote():
    from research_lab.pump4_entry_binding_v1 import bind_entry
    p,i,t,public,policy=entry_material(side='long');b=bind_entry(p,policy,public,'96',now_ms=7230000)
    assert b['execution_quote_price']=='100.03'

def explicit_owner(tmp_path,mode='ORDERS_OFF'):
    from research_lab.pump4_entry_binding_v1 import execution_policy
    from research_lab.pump4_account_owner_v1 import Pump4AccountOwner
    from test_pump4_native_stop_v1 import owner_material
    from test_pump4_account_owner_v1 import KEY,SECRET
    (tmp_path/'legacy').mkdir();s,p,_,_=owner_material(tmp_path/'legacy');old,e,t,_,_,lease=s
    scope=copy.deepcopy(old.scope);scope.update(root=str(tmp_path/'explicit'),mode=mode)
    scope['execution_policy']=execution_policy(scope['policy'],max_reference_drift_bps='10')
    o=Pump4AccountOwner(scope,lease=lease,key=KEY,secret=SECRET,wire=e.wire,platform_check=old.platform_check,clock=lambda:t[0])
    return o,e,t,lease,p,old.scope_sha256

def explicit_inputs(o,e,t,p,price='100.02',flow=None):
    from test_pump4_account_owner_v1 import inputs,reseal
    x,public=inputs(e,now=t[0],price=price)
    if flow is not None:
        times={r['request']['orderLinkId']:r['observed_ms'] for r in flow._events()}
        for cap in x['history_windows'][0]['groups']['executions']['pages']:
            for r in cap['body']['result']['list']:r['execTime']=str(times[r['orderLinkId']]+1)
            reseal(cap)
    now=t[0];start=p['entry_bar_open_ms']
    cap=capture('/v5/market/kline',dict(category='linear',symbol=p['symbol'],interval='60',start=start,end=start+3600000-1,limit=1),dict(category='linear',symbol=p['symbol'],list=[[str(start),'100','100.04','99.99','100.02','10','1000']]))
    cap.update(request_ms=now-1,receive_ms=now);cap['body']['time']=now-1;reseal(cap);public['entry_interval']=cap
    return x,public

def test_explicit_off_30s_entry_and_immutable_restart(tmp_path):
    from research_lab.pump4_execution_lifecycle_v1 import Pump4Lifecycle
    o,e,t,lease,p,_=explicit_owner(tmp_path)
    try:
        t[0]=p['entry_bar_open_ms']+30000;x,public=explicit_inputs(o,e,t,p);f=o.prepare(p,x,public);old=copy.deepcopy(f.config)
        assert o.cycle(f,x,public,apply=False)['status']=='ACTION_RESERVED_ORDERS_OFF'
        assert f.config['plan']==p and Pump4Lifecycle.resume(f.root).config==old and e.state['calls']==0
        assert o.cycle(f,x,public,apply=False)['status']=='RECONCILE_ONLY'
    finally:lease.close()

def test_expired_explicit_entry_does_not_create_admission(tmp_path):
    o,e,t,lease,p,_=explicit_owner(tmp_path)
    try:
        t[0]=p['entry_bar_open_ms']+30000;x,public=explicit_inputs(o,e,t,p);f=o.prepare(p,x,public)
        t[0]=p['entry_bar_open_ms']+60001;x,public=explicit_inputs(o,e,t,p)
        with pytest.raises(ValueError,match='DEADLINE'):o.cycle(f,x,public,apply=False)
        assert not (o.root/'admitted-lifecycle.json').exists() and not f.requests()
    finally:lease.close()

def test_new_policy_requires_new_exact_go_and_expiry_keeps_owned_exits(tmp_path):
    from research_lab.kity_micro_physical_owner_v1 import publish
    o,e,t,lease,p,old_scope_sha=explicit_owner(tmp_path,mode='OWNER_TINY_LIVE')
    try:
        t[0]=p['entry_bar_open_ms']+30000;x,public=explicit_inputs(o,e,t,p);f=o.prepare(p,x,public)
        publish(o.root/'owner-go.json',dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=old_scope_sha,owner_go_text='GO PUMP4_TINY '+old_scope_sha))
        with pytest.raises(ValueError,match='EXACT_OWNER_GO'):o.cycle(f,x,public,apply=True)
        assert e.state['calls']==0
        (o.root/'owner-go.json').unlink();publish(o.root/'owner-go.json',dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=o.scope_sha256,owner_go_text='GO PUMP4_TINY '+o.scope_sha256))
        assert o.cycle(f,x,public,apply=True)['status']=='ACK_RECONCILE_REQUIRED'
        t[0]=p['entry_bar_open_ms']+70000;x,public=explicit_inputs(o,e,t,p,'97.8',f)
        assert o.cycle(f,x,public,apply=True)['role']=='TP1'
        t[0]+=1000;x,public=explicit_inputs(o,e,t,p,'95.7',f)
        assert o.cycle(f,x,public,apply=True)['role']=='TP2' and D(e.state['held'])==0
        assert e.state['calls']==3
    finally:lease.close()

def test_wire_deadline_rechecked_after_reservation_without_resend(tmp_path):
    o,e,t,lease,p,_=explicit_owner(tmp_path,mode='OWNER_TINY_LIVE')
    from research_lab.kity_micro_physical_owner_v1 import publish
    try:
        publish(o.root/'owner-go.json',dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=o.scope_sha256,owner_go_text='GO PUMP4_TINY '+o.scope_sha256))
        t[0]=p['entry_bar_open_ms']+59500;x,public=explicit_inputs(o,e,t,p);f=o.prepare(p,x,public)
        original=o.post_reserved
        def expired(*args,**kw):t[0]+=600;return original(*args,**kw)
        o.post_reserved=expired
        assert o.cycle(f,x,public,apply=True)['status']=='WIRE_UNKNOWN_RECONCILE_ONLY' and e.state['calls']==0
        assert len(f.requests())==1
        x,public=explicit_inputs(o,e,t,p);assert o.cycle(f,x,public,apply=True)['status']=='RECONCILE_ONLY' and e.state['calls']==0
    finally:lease.close()


def test_explicit_runtime_provider_captures_path_only_for_entry(tmp_path):
    import json,urllib.parse
    from test_pump4_runtime_sources_v1 import wire_fixture
    from research_lab.pump4_runtime_sources_v1 import TrustedSources
    from research_lab.pump4_account_owner_v1 import source_sizing
    o,e,t,lease,p,_=explicit_owner(tmp_path)
    try:
        t[0]=p['entry_bar_open_ms']+30000
        wire,calls=wire_fixture(e,t[0]);path_calls=[]
        def with_path(method,url,headers,data,timeout):
            parsed=urllib.parse.urlsplit(url);q=dict(urllib.parse.parse_qsl(parsed.query))
            if parsed.path!='/v5/market/kline':return wire(method,url,headers,data,timeout)
            path_calls.append(q)
            return 200,json.dumps(dict(retCode=0,retMsg='OK',time=t[0],result=dict(category='linear',symbol=p['symbol'],list=[[str(p['entry_bar_open_ms']),'100','100.04','99.99','100','10','1000']]))).encode()
        config=dict(execution_policy=o.scope['execution_policy'])
        provider=TrustedSources(config,o,wire=with_path,clock=lambda:t[0])
        x,public=provider.account(p,custody=False)
        size=source_sizing(p,x,public,o.scope['policy'],fingerprint=o.scope['account_fingerprint'],now_ms=t[0],execution_policy=o.scope['execution_policy'])
        assert size['entry_binding']['valid_until_ms']==p['entry_bar_open_ms']+60000
        assert len(path_calls)==1 and path_calls[0]['start']==str(p['entry_bar_open_ms'])
        provider.account(p,custody=True)
        assert len(path_calls)==1 and e.state['calls']==0
        with pytest.raises(ValueError,match='EXECUTION_POLICY_BINDING'):TrustedSources({},o,wire=with_path,clock=lambda:t[0])
    finally:lease.close()


@pytest.mark.parametrize('fault',['source','risk','zip_bomb','compressed_tamper','negative_volume'])
def test_policy_and_embedded_source_evidence_fail_closed(fault):
    import base64,zlib
    from research_lab.pump4_entry_binding_v1 import bind_entry,verify_binding,verify_policy
    from test_pump4_account_owner_v1 import reseal
    p,i,t,public,policy=entry_material()
    with pytest.raises(ValueError):
        if fault=='source':policy['source_manifest_sha256']='0'*64;verify_policy(policy)
        elif fault=='risk':verify_policy(policy,dict(risk_usdt='2'))
        elif fault=='negative_volume':
            public['entry_interval']['body']['result']['list'][0][5]='-1';reseal(public['entry_interval'])
            bind_entry(p,policy,public,'103.8',now_ms=7230000)
        else:
            b=bind_entry(p,policy,public,'103.8',now_ms=7230000)
            b['quote_capture']['raw_zlib_b64']=base64.b64encode(zlib.compress(b'x'*5000001)).decode() if fault=='zip_bomb' else 'broken'
            verify_binding(p,b,now_ms=7230000)


def test_owned_fill_cannot_predate_delayed_entry_reservation(tmp_path):
    o,e,t,lease,p,_=explicit_owner(tmp_path,mode='OWNER_TINY_LIVE')
    from research_lab.kity_micro_physical_owner_v1 import publish
    try:
        publish(o.root/'owner-go.json',dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=o.scope_sha256,owner_go_text='GO PUMP4_TINY '+o.scope_sha256))
        t[0]=p['entry_bar_open_ms']+30000;x,public=explicit_inputs(o,e,t,p);f=o.prepare(p,x,public)
        assert o.cycle(f,x,public,apply=True)['status']=='ACK_RECONCILE_REQUIRED'
        t[0]+=1000;x,public=explicit_inputs(o,e,t,p)
        with pytest.raises(ValueError,match='EXECUTION_BEFORE_RESERVATION'):o.cycle(f,x,public,apply=True)
        assert e.state['calls']==1
    finally:lease.close()


def test_post_dispatch_fill_uses_exchange_clock_even_if_below_local_reservation(tmp_path):
    o,e,t,lease,p,_=explicit_owner(tmp_path,mode='OWNER_TINY_LIVE')
    from research_lab.kity_micro_physical_owner_v1 import publish
    from test_pump4_account_owner_v1 import reseal
    try:
        publish(o.root/'owner-go.json',dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=o.scope_sha256,owner_go_text='GO PUMP4_TINY '+o.scope_sha256))
        t[0]=p['entry_bar_open_ms']+30000;x,public=explicit_inputs(o,e,t,p);f=o.prepare(p,x,public)
        assert o.cycle(f,x,public,apply=True)['status']=='ACK_RECONCILE_REQUIRED'
        reserved=t[0];t[0]+=1000;x,public=explicit_inputs(o,e,t,p,flow=f)
        # Captured Bybit time was local reservation minus2ms. This fill happened
        # later on that exchange clock, despite being below local reservation.
        for cap in x['history_windows'][0]['groups']['executions']['pages']:
            for row in cap['body']['result']['list']:row['execTime']=str(reserved-1)
            reseal(cap)
        assert o.cycle(f,x,public,apply=True)['status']=='PROTECTED_WAIT'
        assert e.state['calls']==1
    finally:lease.close()
