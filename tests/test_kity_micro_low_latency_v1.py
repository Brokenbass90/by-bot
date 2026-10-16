"""GET reuse must never become a replay, redirected request or money path."""
import json
import ssl
import pytest

from research_lab import kity_micro_low_latency_v1 as ll
from research_lab.kity_micro_transport_v1 import BybitReadTransport


class Response:
    status=200
    will_close=False
    def __init__(self,body=b'{"retCode":0,"result":{}}'):self.body=body
    def read(self,n):return self.body[:n]


class Connection:
    def __init__(self,*args,**kwargs):self.requests=[];self.closed=False;self.sock=None;self.response=Response()
    def request(self,method,path,body=None,headers=None):
        self.requests.append((method,path,body,headers))
    def getresponse(self):return self.response
    def close(self):self.closed=True


def pool():
    made=[];clock=[0.0]
    def factory(*args,**kwargs):
        assert args[0]=='api.bybit.com' and kwargs['context'].verify_mode==ssl.CERT_REQUIRED
        assert kwargs['context'].check_hostname
        c=Connection();made.append(c);return c
    p=ll.ReusableGetWire(connection_factory=factory,clock=lambda:clock[0],
        sleep=lambda t:clock.__setitem__(0,clock[0]+t))
    return p,made,clock


def test_successful_get_reuses_connection_but_always_sends_a_new_request():
    p,made,clock=pool()
    a=p('GET','https://api.bybit.com/v5/account/info',{},None,2)
    clock[0]=.1;b=p('GET','https://api.bybit.com/v5/account/info',{},None,2)
    assert a==b==(200,b'{"retCode":0,"result":{}}')
    assert len(made)==1 and len(made[0].requests)==2
    assert p.metrics()['reused_connections']==1


@pytest.mark.parametrize('method,url,data',[
    ('POST','https://api.bybit.com/v5/order/create',b'{}'),
    ('GET','https://evil.invalid/v5/account/info',None),
    ('GET','http://api.bybit.com/v5/account/info',None),
    ('GET','https://user@api.bybit.com/v5/account/info',None),
    ('GET','https://api.bybit.com:444/v5/account/info',None),
    ('GET','https://api.bybit.com/v5/order/create',None),
    ('GET','https://api.bybit.com/v5/account/info#foreign',None),
    ('GET','https://api.bybit.com/v5/account/info',b'{}'),
])
def test_scope_rejected_before_any_connection(method,url,data):
    p,made,clock=pool()
    with pytest.raises(ValueError):p(method,url,{},data,2)
    assert not made


def test_unknown_get_response_is_not_retried_and_broken_connection_is_discarded():
    p,made,clock=pool();p('GET','https://api.bybit.com/v5/account/info',{},None,2)
    def disconnected():raise ConnectionResetError('not an excuse to repeat')
    made[0].getresponse=disconnected
    with pytest.raises(ConnectionResetError):p('GET','https://api.bybit.com/v5/account/info',{},None,2)
    assert len(made[0].requests)==2 and made[0].closed
    # This is a separate explicit GET, never an internal repeat of the failed one.
    p('GET','https://api.bybit.com/v5/account/info',{},None,2)
    assert len(made)==2 and len(made[1].requests)==1


def test_idle_connection_and_connection_close_response_are_not_reused():
    p,made,clock=pool();p('GET','https://api.bybit.com/v5/account/info',{},None,2)
    clock[0]=3;p('GET','https://api.bybit.com/v5/account/info',{},None,2)
    assert len(made)==2 and made[0].closed
    made[1].response.will_close=True
    p('GET','https://api.bybit.com/v5/account/info',{},None,2)
    p('GET','https://api.bybit.com/v5/account/info',{},None,2)
    assert len(made)==3 and made[1].closed


def test_redirect_is_not_followed_and_oversized_body_is_not_reused():
    p,made,clock=pool();p('GET','https://api.bybit.com/v5/account/info',{},None,2)
    made[0].response.status=302
    cap=BybitReadTransport('test-key','test-secret',wire=p,clock=lambda:1000).get('/v5/account/info',{})
    assert cap['http_status']==302 and len(made[0].requests)==2
    with pytest.raises(ValueError):BybitReadTransport.result(cap)
    made[0].response.status=200;made[0].response.body=b'x'*2000001
    cap=BybitReadTransport('test-key','test-secret',wire=p,clock=lambda:1000).get('/v5/account/info',{})
    assert cap['error_type']=='BODY_BOUND' and made[0].closed


def test_existing_source_timestamps_and_signing_are_preserved():
    p,made,clock=pool();r=BybitReadTransport('test-key','test-secret',wire=p,clock=lambda:1000)
    a=r.get('/v5/account/info',{});b=r.get('/v5/account/info',{})
    assert a['request_ms']==a['receive_ms']==1000 and a['raw_sha256']==b['raw_sha256']
    assert made[0].requests[0][3]['X-BAPI-TIMESTAMP']=='1000'
    assert 'test-secret' not in json.dumps(p.metrics())


def test_fee_rate_requests_are_scheduled_below_five_per_second_without_retry():
    p,made,clock=pool();at=[]
    for n in range(10):
        p('GET','https://api.bybit.com/v5/account/fee-rate?category=linear&symbol=LTCUSDT',{},None,2)
        at.append(clock[0])
    assert len(made[0].requests)==10
    assert all(b-a>=.249 for a,b in zip(at,at[1:]))


def test_concurrent_gets_never_share_one_in_flight_connection():
    import concurrent.futures as cf
    import threading,time
    made=[];lock=threading.Lock();active=set();maximum=[0]
    class SlowConnection(Connection):
        def request(self,*args,**kwargs):
            with lock:
                assert id(self) not in active
                active.add(id(self));maximum[0]=max(maximum[0],len(active))
            time.sleep(.01);super().request(*args,**kwargs)
        def getresponse(self):
            with lock:active.remove(id(self))
            return super().getresponse()
    def factory(*args,**kwargs):c=SlowConnection();made.append(c);return c
    p=ll.ReusableGetWire(connection_factory=factory)
    with cf.ThreadPoolExecutor(max_workers=12) as executor:
        results=list(executor.map(lambda _:p('GET','https://api.bybit.com/v5/account/info',{},None,2),range(16)))
    assert all(x[0]==200 for x in results) and sum(len(c.requests) for c in made)==16
    assert maximum[0]<=10


def test_parallel_pages_reuses_exact_complete_sources_and_keeps_incomplete_unknown():
    class Reader:
        def __init__(self):self.calls=[]
        def pages(self,path,params):
            self.calls.append((path,dict(params)))
            return dict(complete=path!='bad',pages=[dict(endpoint=path,params=dict(params))])
    r=Reader();view=ll.ParallelPages(r,[('good',{'limit':'50'}),('bad',{}),('good',{'limit':'50'})])
    assert view.pages('good',{'limit':'50'})==dict(complete=True,pages=[dict(endpoint='good',params={'limit':'50'})])
    assert view.pages('bad',{})['complete'] is False
    assert len(r.calls)==2


def test_entry_progress_removes_unconditional_sleep_but_does_not_spin_when_waiting():
    a=dict(phase='ENTERING',entry_blocked=False,entries={})
    b=dict(a,entries={'LTCUSDT':dict(filled='0',protected='0',terminal=False)})
    assert ll.cycle_delay(a,b)==.01
    assert ll.cycle_delay(b,b)==.25
    assert ll.cycle_delay(b,dict(b,entry_blocked=True))==1
    assert ll.cycle_delay(b,dict(b,phase='PROTECTED'))==1


def test_parallel_bridge_still_runs_full_native_restart_and_cash_lifecycle(tmp_path,monkeypatch):
    import test_kity_micro_physical_e2e_v1 as venue
    monkeypatch.setattr(venue,'MicroAccountBridge',ll.ParallelReadBridge)
    venue.test_concrete_owner_all_ten_native_restart_deadline_and_actual_cash_path(tmp_path,monkeypatch)


@pytest.mark.parametrize('get_ms',[180,300])
def test_ten_leg_deadline_with_observed_network_structure_and_rate_pacing(tmp_path,monkeypatch,get_ms):
    import test_kity_micro_physical_e2e_v1 as venue
    import test_kity_micro_post_go_owner_v1 as policy_venue
    from kity_latency_clock import Latency,Executor
    sim=Latency(get_ms=get_ms)
    monkeypatch.setattr(ll.cf,'ThreadPoolExecutor',lambda max_workers:Executor(sim,max_workers))
    monkeypatch.setattr(venue,'MicroAccountBridge',ll.ParallelReadBridge)
    class FastSupervisor(venue.Supervisor):
        def cycle(self):return ll.cycle_with_sources(self,super().cycle)
    monkeypatch.setattr(venue,'Supervisor',FastSupervisor)
    policy_venue.test_post_go_owner_all_ten_native_restart_deadline_and_final_cash(tmp_path,monkeypatch,latency=sim)
    assert sim.posts[9]-sim.go_ms<50000
    assert sim.protected_ms-sim.go_ms<55000
    print(json.dumps(dict(last_entry_ms=sim.posts[9]-sim.go_ms,all_protected_ms=sim.protected_ms-sim.go_ms,
        entry_margin_ms=60000-(sim.posts[9]-sim.go_ms),get_latency_ms=get_ms,post_ack_ms=600,initial_ms=9000,
        mode='DETERMINISTIC_LATENCY_MODEL_NOT_REAL_FILLS')))


@pytest.mark.parametrize('case',[
    'test_unknown_send_survives_restart_without_any_resend',
    'test_terminal_without_complete_execution_rows_stays_reconciliation',
    'test_same_symbol_foreign_position_is_never_adopted',
    'test_missing_fee_cash_row_cannot_be_zero_or_false_finality',
    'test_documented_parameter_rejection_is_terminal_no_fill_not_unknown_resend',
])
def test_parallel_bridge_preserves_existing_failure_recovery(case,tmp_path,monkeypatch):
    import test_kity_micro_account_bridge_v1 as original
    monkeypatch.setattr(original,'MicroAccountBridge',ll.ParallelReadBridge)
    getattr(original,case)(tmp_path)


@pytest.mark.parametrize('fees',[[],[{'symbol':'BTWUSDT','takerFeeRate':'.001'}]*2])
def test_common_fee_snapshot_missing_or_duplicate_symbol_is_unknown(tmp_path,monkeypatch,fees):
    from test_kity_micro_account_bridge_v1 import journal
    from test_kity_micro_runtime_v1 import event
    from research_lab.kity_micro_supervisor_v1 import Supervisor
    from research_lab.kity_micro_transport_v1 import BybitReadTransport
    import research_lab.kity_micro_supervisor_v1 as sup
    j=journal(tmp_path);symbol='BTWUSDT';link=j.plan['legs'][0]['request']['orderLinkId']
    j.append(event('ENTRY_INTENT',symbol=symbol))
    j.append(event('ENTRY_FILL',symbol=symbol,order_link_id=link,order_id='owned',execution_id='x',
        quantity='1',price='1',fee_usdt='.001',source_execution_ms=2000))
    class Reader:
        all_symbol_fee_snapshot=True
        result=staticmethod(BybitReadTransport.result)
        def get(self,path,params):
            if path=='/v5/account/fee-rate':rows=fees
            elif path.endswith('tickers'):rows=[dict(symbol=symbol,nextFundingTime='99999999')]
            else:rows=[dict(symbol=symbol,fundingInterval=480)]
            return dict(params=params,http_status=200,body=dict(retCode=0,result=dict(list=rows)))
    s=Supervisor.__new__(Supervisor);s.journal=j;s.reader=Reader()
    s.spec={symbol:dict(next_funding_ms='99999999',funding_interval_minutes=480)}
    monkeypatch.setattr(sup,'now_ms',lambda:3000)
    with pytest.raises(ValueError,match='RISK_SYMBOL_SOURCE_UNKNOWN'):s.funding_and_risk()
