import hashlib
import hmac
import json

import pytest

from research_lab.kity_micro_transport_v1 import BybitReadTransport,SourceError


class Wire:
    def __init__(self,body=None):self.calls=[];self.body=body or dict(retCode=0,result=dict(list=[]),time=1000)
    def __call__(self,method,url,headers,data,timeout):
        self.calls.append((method,url,headers,data,timeout))
        return 200,json.dumps(self.body).encode()


def client(wire):return BybitReadTransport('key-test','secret-test',wire=wire,clock=lambda:1000)


def test_real_signature_canonical_query_and_raw_source_identity():
    w=Wire();c=client(w)
    cap=c.get('/v5/position/list',dict(symbol='LTCUSDT',category='linear'))
    method,url,headers,data,timeout=w.calls[0]
    query='category=linear&symbol=LTCUSDT'
    expected=hmac.new(b'secret-test',('1000key-test10000'+query).encode(),hashlib.sha256).hexdigest()
    assert method=='GET' and url.endswith('?'+query) and data is None
    assert headers['X-BAPI-SIGN']==expected and cap['signed'] is True
    assert hashlib.sha256(cap['raw'].encode()).hexdigest()==cap['raw_sha256']
    assert 'secret-test' not in repr(c) and 'key-test' not in repr(c)


@pytest.mark.parametrize('path,params',[
 ('/v5/order/create',dict(category='linear',symbol='LTCUSDT')),
 ('/v5/position/set-leverage',dict(category='linear',symbol='LTCUSDT')),
 ('/v5/position/list',dict(category='inverse',symbol='LTCUSDT')),
 ('/v5/position/list',dict(category='linear',symbol='FOREIGNUSDT')),
 ('/v5/account/info',dict(unexpected='x'))])
def test_transport_rejects_outside_scope_before_any_network(path,params):
    w=Wire()
    with pytest.raises(SourceError):client(w).get(path,params)
    assert w.calls==[]


def test_network_failure_is_one_observation_not_retry_or_fallback():
    calls=[]
    def fail(*args):calls.append(args);raise TimeoutError('never expose key-test')
    cap=client(fail).get('/v5/account/info',{})
    assert len(calls)==1 and cap['error_type']=='TimeoutError'
    assert 'key-test' not in json.dumps(cap)


def test_query_api_key_echo_is_removed_before_serialization():
    w=Wire(dict(retCode=0,result=dict(apiKey='key-test',ips=['127.0.0.1'],readOnly=0),time=1000))
    cap=client(w).get('/v5/user/query-api',{})
    assert 'raw' not in cap and 'key-test' not in json.dumps(cap)
    assert cap['body']['result']==dict(readOnly=0)


@pytest.mark.parametrize('body',[{'retCode':False,'result':{}}, {'retCode':10001,'result':{}},
 {'retCode':0,'result':None}])
def test_non_success_is_retained_but_not_accepted_as_source(body):
    c=client(Wire(body));cap=c.get('/v5/account/info',{})
    with pytest.raises(SourceError):c.result(cap)


def test_page_cursor_loop_never_becomes_complete():
    w=Wire(dict(retCode=0,result=dict(list=[],nextPageCursor='loop'),time=1000))
    r=client(w).pages('/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'))
    assert r['complete'] is False and r['reason']=='CURSOR_LOOP' and len(w.calls)==2


def test_get_only_transport_has_no_public_money_method():
    c=client(Wire())
    assert not any(hasattr(c,n) for n in ('post','send_order','cancel_order','apply'))


def test_actual_empty_transaction_null_cursor_is_an_explicit_terminal_source_form():
    w=Wire(dict(retCode=0,result=dict(list=[],nextPageCursor=None),time=1000))
    r=client(w).pages('/v5/account/transaction-log',dict(accountType='UNIFIED',category='linear',currency='USDT'))
    assert r['complete'] is True and len(w.calls)==1
    assert r['source_contract']=='EMPTY_TRANSACTION_NULL_CURSOR_V1'
    assert r['pages'][0]['body']['result']['nextPageCursor'] is None


def test_null_cursor_with_rows_is_not_silently_assumed_complete():
    w=Wire(dict(retCode=0,result=dict(list=[dict(id='not-empty')],nextPageCursor=None),time=1000))
    r=client(w).pages('/v5/account/transaction-log',dict(accountType='UNIFIED',category='linear',currency='USDT'))
    assert r['complete'] is False
