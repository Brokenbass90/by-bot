import copy,json,hashlib
from pathlib import Path
import pytest
from scripts import measure_polymarket_snapshot_v1 as cli
from research_lab.polymarket_ws_data_v1 import SegmentStore
from scripts.pull_polymarket_ws_data_v1 import import_segment
from test_polymarket_v2_snapshot_inputs_v1 import gamma,book


def archive(tmp_path):
 source=tmp_path/'source';s=SegmentStore(source,'catalog',clock=lambda:1000,min_free=0)
 s.append('CATALOGUE',dict(markets=[dict(id='123',tokens=['11','22'],token='11')]),received_ms=1000);s.close()
 seal_path=next((source/'catalog/sealed').glob('*.delivery.json'));seal=json.loads(seal_path.read_bytes());raw=(source/seal['file']).read_bytes();dest=tmp_path/'archive';import_segment(dest,seal,raw,observed_ms=1002)
 return dest,dest/(seal['file']+'.delivery.json')


def test_default_mode_cannot_access_network(monkeypatch,capsys):
 monkeypatch.setattr(cli.urllib.request,'urlopen',lambda *a,**k:pytest.fail('Network was attempted'))
 assert cli.main([])==0 and 'NO_NETWORK_ORDERS_OFF' in capsys.readouterr().out


def test_get_transport_has_no_auth_or_order_body(monkeypatch):
 seen=[]
 class Response:
  status=200
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def geturl(self):return 'https://clob.polymarket.com/book?token_id=22'
  def read(self,n):return b'{"asset_id":"22"}'
 def opened(req,**kwargs):
  seen.append(req);assert req.get_method()=='GET' and req.data is None
  assert not any('auth' in k.lower() or 'key' in k.lower() for k in req.headers)
  return Response()
 monkeypatch.setattr(cli.urllib.request,'urlopen',opened)
 monkeypatch.setattr(cli.urllib.request,'build_opener',lambda *a:type('Opener',(),{'open':staticmethod(opened)})())
 c=cli.get_capture('https://clob.polymarket.com/book?token_id=22')
 assert c['raw_sha256']==hashlib.sha256(c['raw_text'].encode()).hexdigest() and c['received_ms']>=c['request_ms']
 for url in ['https://clob.polymarket.com/order','https://example.com/book?token_id=22','http://clob.polymarket.com/book?token_id=22']:
  with pytest.raises(ValueError,match='PUBLIC_GET_ALLOWLIST'):cli.get_capture(url)
 assert len(seen)==1


def test_three_samples_capture_both_outcomes_without_creating_three_trades(tmp_path,monkeypatch):
 a,seal=archive(tmp_path);calls=[]
 monkeypatch.setattr(cli.time,'time_ns',lambda:1010*1000000);monkeypatch.setattr(cli.time,'sleep',lambda x:None)
 def get(url):
  calls.append(url)
  return gamma() if '/markets/' in url else book(url.rsplit('=',1)[1])
 monkeypatch.setattr(cli,'get_capture',get)
 dest=tmp_path/'run';result=cli.run(a,seal,'123',dest,repeat=3,interval=1)
 assert len(calls)==9 and len(result['samples'])==3
 assert all(x['status']=='MEASURED_SNAPSHOTS' and x['fee_rate']=='0.05' and len(x['outcomes'])==2 for x in result['samples'])
 assert result['actual_strategy_trades']==result['order_posts']==result['distinct_supplied_signals']==0
 assert result['continuous_worker_installed'] is False
 for file in dest.rglob('*.json'):assert file.stat().st_mode&0o777==0o600
 before=(dest/'summary.json').read_bytes()
 with pytest.raises(ValueError,match='DESTINATION_CREATE_EXCLUSIVE'):cli.run(a,seal,'123',dest)
 assert (dest/'summary.json').read_bytes()==before


def test_failed_source_stops_without_retry_or_substitution(tmp_path,monkeypatch):
 a,seal=archive(tmp_path);calls=[];monkeypatch.setattr(cli.time,'time_ns',lambda:1010*1000000)
 def get(url):calls.append(url);raise ValueError('SOURCE_DOWN')
 monkeypatch.setattr(cli,'get_capture',get)
 result=cli.run(a,seal,'123',tmp_path/'run',repeat=3,interval=1)
 assert len(calls)==len(result['samples'])==1 and result['samples'][0]['status']=='UNKNOWN'


def test_market_and_signal_identity_fail_before_network(tmp_path,monkeypatch):
 a,seal=archive(tmp_path);monkeypatch.setattr(cli,'get_capture',lambda *a:pytest.fail('Network before membership/signal qualification'))
 with pytest.raises(ValueError,match='FIXED_MARKET_NOT_IN_EXISTING_MONITOR'):cli.run(a,seal,'999',tmp_path/'run')
 with pytest.raises(ValueError,match='SUPPLIED_SIGNAL_IDENTITY'):cli.run(a,seal,'123',tmp_path/'run',signal=dict(market_id='999'))
 for repeat in [0,4,True]:
  with pytest.raises(ValueError,match='BOUNDED_MEASUREMENT_ONLY'):cli.run(a,seal,'123',tmp_path/'run',repeat=repeat)


def test_redirect_never_sends_a_request_outside_the_get_allowlist(monkeypatch):
 import urllib.response,io,email.message
 calls=[];original_build=cli.urllib.request.build_opener
 class FakeHTTPS(cli.urllib.request.HTTPSHandler):
  def https_open(self,req):
   calls.append(req.full_url);headers=email.message.Message()
   code=302 if len(calls)==1 else 200
   if code==302:headers['Location']='https://outside-allowlist.invalid/private'
   r=urllib.response.addinfourl(io.BytesIO(b'{}'),headers,req.full_url,code);r.msg='Found' if code==302 else 'OK';return r
 def builder(*handlers):return original_build(*handlers,FakeHTTPS())
 monkeypatch.setattr(cli.urllib.request,'build_opener',builder);monkeypatch.setattr(cli.urllib.request,'_opener',builder())
 try:cli.get_capture('https://clob.polymarket.com/book?token_id=22')
 except ValueError:pass
 assert calls==['https://clob.polymarket.com/book?token_id=22']


def test_repeated_quotes_share_one_signal_identity_and_do_not_claim_independence(tmp_path,monkeypatch):
 a,seal=archive(tmp_path);monkeypatch.setattr(cli.time,'time_ns',lambda:1010*1000000);monkeypatch.setattr(cli.time,'sleep',lambda x:None)
 monkeypatch.setattr(cli,'get_capture',lambda url:gamma() if '/markets/' in url else book(url.rsplit('=',1)[1]))
 signal=dict(market_id='123',token_id='22',policy_sha256='b'*64,received_ms=999,model_price='.97');dest=tmp_path/'run'
 result=cli.run(a,seal,'123',dest,signal=signal,repeat=3,interval=1)
 receipts=[json.loads(p.read_bytes()) for p in sorted(dest.glob('sample-*/measurement.json'))]
 assert len(receipts)==3 and sum(r['independent_opportunities'] for r in receipts)==0
 assert len({r['signal_observation_id'] for r in receipts})==1
 assert result['distinct_supplied_signals']==1 and result['actual_strategy_trades']==0
