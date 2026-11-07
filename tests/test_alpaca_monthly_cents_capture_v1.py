"""Owner-approved candidate only: real wire/permit and private rejection persistence, fake HTTP."""
import copy
import hashlib
import json
import stat
from decimal import Decimal
from types import MethodType
from email.message import Message
import pytest
from scripts import equities_alpaca_paper_bridge as native
from research_lab.alpaca_dynamic_live_runtime_v1 import DynamicLiveClient,LIVE
from test_alpaca_monthly_native_binding_v1 import setup,ticket
from test_alpaca_http_rejection_evidence_v1 import Endpoint,KEY,SECRET
from test_alpaca_monthly_cycle_custody_v1 import wired

@pytest.mark.parametrize('cap,want',[(101.413902261,'101.41'),(100.009999999,'100.00'),(.019999999,'.01')])
def test_monthly_cents_helper_floors_without_spending_above_cap(cap,want):
    got=native._monthly_notional_wire(cap,precision=2)
    assert Decimal(got)==Decimal(want) and Decimal(got)<=Decimal(str(cap))
    assert len(got.split('.')[1])==2

@pytest.mark.parametrize('cap',[.009999999,.000000001])
def test_subcent_budget_is_rejected_before_dispatch(cap):
    with pytest.raises(native.IntendedPaperProtectionError):native._monthly_notional_wire(cap,precision=2)

def test_prepared_ticket_actual_wire_permit_and_recovery_use_same_cents(setup):
    book,s,a,io,now=setup;t=ticket(setup);wire=[]
    assert t['notional']==204.71 and t['notional_precision']==2
    assert Decimal(str(t['notional']))<=Decimal(str(t['notional_cap']))
    def request(method,path,payload):
        assert method=='POST' and path=='/v2/orders';wire.append(copy.deepcopy(payload))
        DynamicLiveClient._monthly_payload(payload)
        row=dict(**payload,id='entry',qty='.3',status='filled',filled_qty='.3',filled_avg_price='311.222',filled_at='2026-11-02T14:30:01Z')
        io.orders['entry']=row;io.positions=[dict(symbol='NET',qty='.3',avg_entry_price='311.222',side='long')]
        return copy.deepcopy(row)
    io._request=request;io.submit_market_buy=MethodType(native.AlpacaClient.submit_market_buy,io)
    assert a.enter(t,now_ms=now,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    intent=json.loads(a.reentry.read_bytes())['entry_intents'][t['client_order_id']]
    assert wire[0]['notional']=='204.71' and intent['baseline_wire_notional']=='204.71'
    assert intent['notional']==204.71
    a.enter(t,now_ms=now+1000,apply=True)
    assert len(wire)==1

def test_cents_transport_permit_is_exact_and_consumed_once():
    c=DynamicLiveClient('fixture','fixture',writes_enabled=True,order_contract='ALPACA_BASELINE_MONTHLY_DAILY_V1');sent=[]
    c._http=lambda url,method,payload:sent.append(payload) or payload
    payload=dict(symbol='LLY',notional='101.41',side='buy',type='market',time_in_force='day',client_order_id='abm-'+'a'*32)
    c.permit_write('POST','/v2/orders',payload)
    assert c.submit_market_buy('LLY',101.41,client_order_id=payload['client_order_id'],notional_precision=2)==payload
    with pytest.raises(ValueError):c.submit_market_buy('LLY',101.41,client_order_id=payload['client_order_id'],notional_precision=2)
    assert len(sent)==1

def test_old_nine_decimal_buy_cannot_use_future_cents_transport():
    with pytest.raises(ValueError):DynamicLiveClient._monthly_payload(dict(symbol='LLY',notional='101.413902261',side='buy',type='market',time_in_force='day',client_order_id='abm-'+'a'*32))

def capture_in_tick(setup,tmp_path,monkeypatch,body,*,broken=False,unsafe=False,request_id=None):
    m,n,s,io,now=wired(setup,tmp_path)
    c=DynamicLiveClient(KEY,SECRET,writes_enabled=True,order_contract='ALPACA_BASELINE_MONTHLY_DAILY_V1')
    h=Message();h['X-Request-ID']=request_id or 'private-request-'+KEY
    endpoint=Endpoint(body,h,broken);c.opener=endpoint
    payload=dict(symbol='LLY',notional='101.41',side='buy',type='market',time_in_force='day',client_order_id='abm-'+'b'*32)
    def fail(*args,**kwargs):
        c.permit_write('POST','/v2/orders',payload)
        return c._request('POST','/v2/orders',payload)
    monkeypatch.setattr(m,'recover',fail)
    if unsafe:
        target=tmp_path/'foreign';target.mkdir();(m.root/'http-rejections').symlink_to(target,target_is_directory=True)
    out=m.tick(n,now_ms=now,apply=True)
    issue=next(x for x in out['issues'] if x['phase']=='RECOVERY')
    assert issue['reason']=='ALPACA_HTTP_422' and c.write_permit is None and len(endpoint.requests)==1
    for value in [out,*[json.loads(p.read_bytes()) for p in (m.root/'observations').glob('*.json')]]:
        assert KEY not in json.dumps(value) and SECRET not in json.dumps(value)
    return m,issue

@pytest.mark.parametrize('body',[b'{"code":42210000,"message":"fixture rejected","unknown":"'+SECRET.encode()+b'"}',b'non-json-private:'+KEY.encode()+b'x'*12000],ids=['json-private','non-json-over8KiB'])
def test_full_rejection_body_and_request_id_are_private_and_exact(setup,tmp_path,monkeypatch,body):
    m,issue=capture_in_tick(setup,tmp_path,monkeypatch,body)
    reference=issue['http_error_private_capture'];assert reference['status']=='COMPLETE'
    manifests=list((m.root/'http-rejections').glob('*.json'));assert len(manifests)==1
    p=manifests[0];meta=json.loads(p.read_bytes());raw=p.with_suffix('.body').read_bytes()
    assert raw==body and meta['body_sha256']==hashlib.sha256(body).hexdigest()
    assert meta['request_id']=='private-request-'+KEY and meta['body_complete'] is True
    assert stat.S_IMODE(p.stat().st_mode)==stat.S_IMODE(p.with_suffix('.body').stat().st_mode)==0o600
    assert stat.S_IMODE(p.parent.stat().st_mode)==0o700

def test_oversize_rejection_is_explicitly_truncated_not_complete(setup,tmp_path,monkeypatch):
    body=b'z'*2000010;m,issue=capture_in_tick(setup,tmp_path,monkeypatch,body)
    assert issue['http_error_private_capture']['status']=='TRUNCATED'
    p=next((m.root/'http-rejections').glob('*.json'));meta=json.loads(p.read_bytes())
    assert p.with_suffix('.body').read_bytes()==body[:2000000]
    assert meta['body_complete'] is False and meta['body_bytes']==2000000

def test_unreadable_body_is_unavailable_and_original_rejection_survives(setup,tmp_path,monkeypatch):
    m,issue=capture_in_tick(setup,tmp_path,monkeypatch,b'',broken=True)
    assert issue['http_error_private_capture']['status']=='UNAVAILABLE'

def test_unsafe_private_capture_path_never_masks_original_error_or_writes_foreign(setup,tmp_path,monkeypatch):
    m,issue=capture_in_tick(setup,tmp_path,monkeypatch,b'private',unsafe=True)
    assert issue['http_error_private_capture']['status']=='WRITE_FAILED'
    assert list((tmp_path/'foreign').iterdir())==[]

@pytest.mark.parametrize('short_length',[None,999])
def test_response_capture_reads_to_eof_and_never_calls_short_body_complete(short_length):
    import io
    from urllib.error import HTTPError
    class ShortReads(io.BytesIO):
        def read(self,n=-1):return super().read(min(n,7))
    body=b'{"code":42210000,"message":"exact full body"}'
    h=Message()
    if short_length is not None:h['Content-Length']=str(short_length)
    exc=HTTPError(LIVE+'/v2/orders',422,'fixture',h,ShortReads(body))
    c=DynamicLiveClient(KEY,SECRET);private={}
    c._http_error_evidence(exc,'POST',LIVE+'/v2/orders',{},b'{}',private_capture=private)
    assert private['body']==body
    assert private['status']==('COMPLETE' if short_length is None else 'INCOMPLETE')
    assert private['body_complete'] is (short_length is None)

def test_capture_write_failure_preserves_original_http_error(setup,tmp_path,monkeypatch):
    import research_lab.alpaca_monthly_cycle_v1 as cycle
    original=cycle.publish_once
    def fail(path,raw):
        if path.suffix=='.body':raise OSError('fixture disk failure')
        return original(path,raw)
    monkeypatch.setattr(cycle,'publish_once',fail)
    m,issue=capture_in_tick(setup,tmp_path,monkeypatch,b'private body')
    assert issue['http_error_private_capture']['status']=='WRITE_FAILED'
    assert list((m.root/'http-rejections').glob('*.json'))==[]

def test_ordinary_request_identifier_stays_private(setup,tmp_path,monkeypatch):
    rid='request-ordinary-123'
    m,issue=capture_in_tick(setup,tmp_path,monkeypatch,b'{"code":42210000,"message":"rejected"}',request_id=rid)
    assert rid not in json.dumps(issue)
    assert rid not in ''.join(p.read_text() for p in (m.root/'observations').glob('*.json'))
    metadata=json.loads(next((m.root/'http-rejections').glob('*.json')).read_bytes())
    assert metadata['request_id']==rid

@pytest.mark.parametrize('unwind_fails',[False,True])
def test_handled_stop422_is_saved_before_native_handler_or_unwind_failure(setup,tmp_path,monkeypatch,unwind_fails):
    from scripts.equities_alpaca_paper_bridge import AlpacaAPIError
    m,n,s,io,now=wired(setup,tmp_path)
    body=b'{"code":42210000,"message":"fixture stop rejected"}'
    c=DynamicLiveClient(KEY,SECRET);c.opener=Endpoint(body)
    with pytest.raises(AlpacaAPIError) as caught:c._http(LIVE+'/v2/orders','POST',{})
    def rejected_stop(*args,**kwargs):raise caught.value
    monkeypatch.setattr(io,'submit_stop_sell',rejected_stop)
    def unwind(*args,**kwargs):
        manifests=list((m.root/'http-rejections').glob('*.json'));assert len(manifests)==1
        assert manifests[0].with_suffix('.body').read_bytes()==body
        if unwind_fails:raise OSError('fixture unwind failed')
        return {'status':'FIXTURE_UNWIND'}
    monkeypatch.setattr(n,'_settle_owned',unwind)
    prepared=n.prepare_entry({},s['selection_id'],'NET',quote=dict(ask=311.,quote_ts=now,received_ms=now,source='recorded-iex'),now_ms=now,cash=487.42,open_equity=487.42)
    if unwind_fails:
        with pytest.raises(OSError,match='unwind failed'):n.enter(prepared,now_ms=now,apply=True)
    else:assert n.enter(prepared,now_ms=now,apply=True)['status']=='FIXTURE_UNWIND'
    assert len(list((m.root/'http-rejections').glob('*.json')))==1
    assert io.sent==['buy']

def test_old_reserved_nine_decimal_intent_recovers_without_repricing_or_second_buy(setup):
    b,s,a,io,now=setup;prepared=ticket(setup);io.lose_once=True
    with pytest.raises(OSError):a.enter(prepared,now_ms=now,apply=True)
    # A historical fixture: lost reply from the former9dp implementation.
    saved=json.loads(a.reentry.read_bytes());intent=saved['entry_intents'][prepared['client_order_id']]
    intent['notional']=204.71639999999998;intent['baseline_wire_notional']='204.716399999'
    intent.pop('baseline_notional_cap',None)
    a.reentry.write_text(json.dumps(saved));io.orders['entry']['notional']='204.716399999'
    assert a.enter(prepared,now_ms=now+1000,apply=True)['status']=='MONTHLY_NATIVE_PROTECTED'
    recovered=json.loads(a.reentry.read_bytes())['entry_intents'][prepared['client_order_id']]
    assert recovered['baseline_wire_notional']=='204.716399999' and recovered['notional']==204.71639999999998
    assert io.sent==['buy','stop']

def test_non_monthly_legacy_serializer_keeps_its_existing_precision_behavior():
    sink=type('Sink',(),{'_request':lambda self,method,path,payload:payload})()
    assert native.AlpacaClient.submit_market_buy(sink,'NET',100.009,notional_precision=2)['notional']=='100.01'
    assert native.AlpacaClient.submit_market_buy(sink,'NET',101.413902261,notional_precision=9)['notional']=='101.413902261'

def test_transport_persists_before_caller_consumes_error_and_tick_does_not_duplicate(setup,tmp_path):
    m,n,s,io,now=wired(setup,tmp_path)
    c=DynamicLiveClient(KEY,SECRET);m.native(c,base_url=LIVE)
    c.opener=Endpoint(b'private consumed rejection')
    with pytest.raises(native.AlpacaAPIError) as caught:c._http(LIVE+'/v2/orders','POST',{})
    assert len(list((m.root/'http-rejections').glob('*.json')))==1
    first=m._capture_http_rejection(caught.value);again=m._capture_http_rejection(caught.value)
    assert first==again and first['status']=='COMPLETE'
    assert len(list((m.root/'http-rejections').glob('*.json')))==1
