"""Bounded public read recovery; no wire, owner, credentials or actual sleep."""
import importlib,json,hashlib,copy
import pytest
from test_pump4_bybit_sources_v1 import capture,NOW,H

def module():return importlib.import_module('research_lab.pump4_public_retry_v1')

def fixture(codes=(10006,0),*,deadline=NOW+60000,headers=None,status=200):
 t=[NOW+1000];mono=[1.0];calls=[];saved=[];slept=[]
 def sleep(seconds):slept.append(seconds);mono[0]+=seconds;t[0]+=int(seconds*1000)
 def get(path,params,*,timeout):
  calls.append((path,copy.deepcopy(params),timeout));code=codes[min(len(calls)-1,len(codes)-1)];c=capture(path,params,{},at=t[0]);c['receive_ms']=t[0];c['body']['retCode']=code;c['http_status']=status
  c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest();c['response_headers']=headers or {};return c
 reader=module().PublicRetry(getter=get,persist=lambda v:saved.append(copy.deepcopy(v)),clock=lambda:t[0],monotonic=lambda:mono[0],sleep=sleep)
 if deadline is not None:reader.anchor(deadline)
 return reader,t,mono,calls,saved,slept


def test_same_query_recovers_with_durable_failure_and_counts_actual_attempts():
 r,t,mono,calls,saved,slept=fixture();params=dict(category='linear')
 cap=r.get('/v5/market/tickers',params)
 assert cap['body']['retCode']==0 and len(calls)==2 and calls[0][:2]==calls[1][:2]
 assert len(saved)==1 and saved[0]['attempt_index']==1 and saved[0]['capture']['body']['retCode']==10006
 assert r.http_attempts==2 and sum(slept)>=1

@pytest.mark.parametrize('kind',['not_anchored','expired','403','other_code','exhausted'])
def test_only_bounded_anchored_rate_retries(kind):
 kwargs=dict(deadline=None if kind=='not_anchored' else NOW if kind=='expired' else NOW+60000,
 codes=(10001,) if kind=='other_code' else (10006,),status=403 if kind=='403' else 200)
 r,t,m,calls,saved,sleep=fixture(**kwargs);cap=r.get('/v5/market/tickers',dict(category='linear'))
 expected=3 if kind=='exhausted' else 1
 assert len(calls)==len(saved)==expected and cap['body']['retCode']!=0


def test_failure_persistence_error_stops_before_retry():
 r,t,m,calls,saved,slept=fixture()
 def fail(value):raise OSError('fsync unavailable')
 r.persist=fail
 with pytest.raises(OSError):r.get('/v5/market/tickers',dict(category='linear'))
 assert len(calls)==1 and not slept


def test_reset_header_cooldown_is_shared_with_first_attempt_and_never_shortened():
 r,t,m,calls,saved,slept=fixture(codes=(10006,),deadline=NOW+2000,headers={'x-bapi-limit-reset-timestamp':str(NOW+3500)})
 # Failed first request persists and sets cooldown; its deadline precludes a retry.
 r.get('/v5/market/tickers',dict(category='linear'));assert len(calls)==1
 r.get('/v5/market/tickers',dict(category='linear'))
 assert slept and slept[0]>=2.5 and len(calls)==2


def test_clock_rollback_cannot_extend_original_retry_budget():
 r,t,m,calls,saved,slept=fixture(codes=(10006,));original=r.sleep
 def jumped(seconds):original(seconds);m[0]+=60;t[0]-=120000
 r.sleep=jumped;r.get('/v5/market/tickers',dict(category='linear'))
 assert len(calls)==1


def test_timeout_is_capped_by_remaining_original_deadline():
 r,t,m,calls,saved,slept=fixture(deadline=NOW+2500)
 r.get('/v5/market/tickers',dict(category='linear'))
 assert len(calls)==2 and calls[1][2]<=.5


@pytest.mark.parametrize('header',['garbage',str(NOW+999999999),'-1'])
def test_malformed_reset_uses_bounded_fallback(header):
 r,t,m,calls,saved,slept=fixture(headers={'x-bapi-limit-reset-timestamp':header})
 assert r.get('/v5/market/tickers',dict(category='linear'))['body']['retCode']==0
 assert sum(slept)==1


def test_longer_concurrent_cooldown_cannot_be_shortened():
 r,t,m,calls,saved,slept=fixture()
 cap=capture('/v5/market/tickers',dict(category='linear'),{},at=t[0]);cap['response_headers']={'x-bapi-limit-reset-timestamp':str(t[0]+5000)}
 r.defer(cap);until=r.until;cap['response_headers']={};r.defer(cap);assert r.until==until


def test_retry_anchor_is_immutable():
 r,*_=fixture()
 with pytest.raises(ValueError,match='ANCHOR_ONCE'):r.anchor(NOW+999999)


def test_network_failure_is_preserved_without_retry():
 r,t,m,calls,saved,slept=fixture()
 def failed(*args,**kw):raise TimeoutError('offline fixture')
 r.getter=failed;cap=r.get('/v5/market/tickers',dict(category='linear'))
 assert cap['error_type']=='TimeoutError' and r.http_attempts==len(saved)==1 and not slept


@pytest.mark.parametrize('raw',[b'<html>blocked</html>',b'\xff\xfe'])
def test_http_error_headers_and_exact_raw_bytes_are_preserved(monkeypatch,raw):
 import base64
 mod=module()
 class Response:
  code=403;headers={'x-bapi-limit':'10','x-bapi-limit-status':'0'}
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def read(self,n):return raw[:n]
 class Opener:
  def open(self,request,timeout):
   assert request.method=='GET' and request.data is None
   assert not any('KEY' in k.upper() or 'SIGN' in k.upper() for k in request.headers)
   return Response()
 monkeypatch.setattr(mod.urllib.request,'build_opener',lambda *a:Opener())
 cap=mod.observed_public_get('/v5/market/tickers',dict(category='linear'),clock=lambda:NOW+1)
 assert cap['http_status']==403 and cap['response_headers']['x-bapi-limit-status']=='0'
 assert base64.b64decode(cap['wire_raw_b64'])==raw
 assert cap['wire_raw_sha256']==hashlib.sha256(raw).hexdigest()


def test_collector_retains_failed_attempt_outside_unchanged_candle_inputs(tmp_path,monkeypatch):
 from scripts import capture_pump4_sources_v1 as collector
 from test_pump4_bybit_sources_v1 import klines
 from research_lab.pump4_bybit_sources_v1 import closed_h1
 t=[NOW+3];mono=[1.];calls=[];pages=klines();failed=[]
 def advance(seconds):t[0]+=int(seconds*1000);mono[0]+=seconds
 cls=module().PublicRetry
 def configured(**kw):return cls(**kw,clock=lambda:t[0],monotonic=lambda:mono[0],sleep=advance)
 def get(path,params,**kw):
  calls.append((path,copy.deepcopy(params)))
  if path=='/v5/market/time':return capture(path,params,{},at=NOW)
  if path=='/v5/market/instruments-info':return capture(path,params,dict(list=[dict(symbol='ZROUSDT',status='Trading',quoteCoin='USDT',contractType='LinearPerpetual')],nextPageCursor=''),at=NOW)
  if path=='/v5/market/tickers':return capture(path,params,dict(list=[]),at=NOW)
  index=0 if params['end']==pages[0]['params']['end'] else 1
  c=copy.deepcopy(pages[index]);assert c['params']==params
  if not failed:
   c['body'].update(retCode=10006,result={});c['raw']=json.dumps(c['body']);c['raw_sha256']=hashlib.sha256(c['raw'].encode()).hexdigest();failed.append(copy.deepcopy(c))
  return c
 monkeypatch.setattr(collector,'ROOT',tmp_path);monkeypatch.setattr(collector,'universe',lambda:('ZROUSDT',));monkeypatch.setattr(collector,'public_get',get);monkeypatch.setattr(collector,'PublicRetry',configured);monkeypatch.setattr(collector.time,'time_ns',lambda:t[0]*1000000)
 root=tmp_path/'.private/capture';receipt=collector.capture(root)
 row=json.loads((root/'symbols/ZROUSDT.json').read_bytes());attempt=json.loads(next((root/'http-attempts').glob('*.json')).read_bytes())
 assert row['status']=='READY_H1_BOOTSTRAP_NOT_ENTRY' and len(row['captures'])==2
 assert attempt['capture']==failed[0] and attempt['attempt_index']==1
 assert receipt['public_get_requests']==len(calls)==6 and receipt['public_capture_pages']==5 and receipt['failed_http_attempts']==1
 assert any(n.startswith('http-attempts/') for n in receipt['source_capture_files'])
 assert row['source']==closed_h1(row['captures'],'ZROUSDT',next_open_ms=NOW,observed_ms=t[0])
 assert row['source']['next_open_ms']==NOW


def test_http403_latches_public_reader_without_more_requests():
 r,t,m,calls,saved,slept=fixture(status=403)
 assert r.get('/v5/market/tickers',dict(category='linear'))['http_status']==403
 with pytest.raises(ValueError,match='HTTP403_GLOBAL_STOP'):r.get('/v5/market/tickers',dict(category='linear'))
 assert len(calls)==1 and r.http_attempts==1


def test_concurrent_first_attempt_waits_for_another_workers_rate_cooldown():
 import threading
 mod=module();clock=[NOW+1000];mono=[1.];failure=threading.Event();release=threading.Event();second_waiting=threading.Event();calls=[];counts={};guard=threading.Lock();results=[]
 def sleep(seconds):
  if threading.current_thread().name=='second':second_waiting.set()
  assert release.wait(3)
  with guard:mono[0]=max(mono[0],2.);clock[0]=max(clock[0],NOW+2000)
 def get(path,params,*,timeout):
  symbol=params['symbol']
  with guard:counts[symbol]=counts.get(symbol,0)+1;index=counts[symbol];calls.append((symbol,mono[0]))
  cap=capture(path,params,{},at=clock[0]);cap['receive_ms']=clock[0];cap['body']['retCode']=10006 if symbol=='ZROUSDT' and index==1 else 0;cap['raw']=json.dumps(cap['body']);cap['raw_sha256']=hashlib.sha256(cap['raw'].encode()).hexdigest();return cap
 r=mod.PublicRetry(getter=get,persist=lambda v:failure.set(),clock=lambda:clock[0],monotonic=lambda:mono[0],sleep=sleep);r.anchor(NOW+60000)
 def run(symbol):results.append(r.get('/v5/market/kline',dict(category='linear',symbol=symbol)))
 first=threading.Thread(target=run,args=('ZROUSDT',),name='first');second=threading.Thread(target=run,args=('BTCUSDT',),name='second');first.start();assert failure.wait(3);second.start();assert second_waiting.wait(3)
 assert calls==[('ZROUSDT',1.)];release.set();first.join(3);second.join(3)
 assert not first.is_alive() and not second.is_alive() and len(results)==2 and r.http_attempts==3
 assert all(stamp>=2 for _,stamp in calls[1:])
