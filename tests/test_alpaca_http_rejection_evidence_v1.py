import io,json,hashlib
from email.message import Message
from urllib.error import HTTPError
import pytest
from research_lab.alpaca_dynamic_live_runtime_v1 import DynamicLiveClient
from scripts.equities_alpaca_paper_bridge import AlpacaAPIError

PAYLOAD=dict(symbol='LLY',notional='101.413902261',side='buy',type='market',time_in_force='day',client_order_id='abm-'+'a'*32)
KEY='fixture-key-123';SECRET='fixture-secret-456'

class Endpoint:
 def __init__(self,body,headers=None,broken=False):self.body=body;self.headers=headers or Message();self.broken=broken;self.requests=[]
 def open(self,req,timeout):
  self.requests.append(req)
  class Broken(io.BytesIO):
   def read(self,*args):raise OSError('fixture body failure')
  raise HTTPError(req.full_url,422,'fixture rejection',self.headers,Broken() if self.broken else io.BytesIO(self.body))

def rejected(body,headers=None,broken=False):
 c=DynamicLiveClient(KEY,SECRET,writes_enabled=True,order_contract='ALPACA_BASELINE_MONTHLY_DAILY_V1');e=Endpoint(body,headers,broken);c.opener=e
 c.permit_write('POST','/v2/orders',PAYLOAD)
 with pytest.raises(AlpacaAPIError) as caught:c._request('POST','/v2/orders',PAYLOAD)
 return c,e,caught.value

def test_real_http422_preserves_sanitized_body_request_id_and_wire_hash():
 body=b'{"code":42210000,"message":"notional must have at most 2 decimal places"}'
 h=Message();h['X-Request-ID']='request-fixture-1';c,e,exc=rejected(body,h)
 d=exc.http_error_evidence
 assert exc.status_code==422 and str(exc)=='ALPACA_HTTP_422'
 assert d['broker_code']==42210000 and d['message']=='notional must have at most 2 decimal places'
 assert d['request_id']=='request-fixture-1' and not d['body_truncated']
 assert d['body_prefix_sha256']==hashlib.sha256(body).hexdigest()
 req=e.requests[0];assert req.get_method()=='POST' and json.loads(req.data)==PAYLOAD
 assert d['request_payload_sha256']==hashlib.sha256(req.data).hexdigest()
 assert d['request_payload']['notional']=='101.413902261'
 assert d['client_order_id_sha256']==hashlib.sha256(PAYLOAD['client_order_id'].encode()).hexdigest()
 assert c.write_permit is None
 with pytest.raises(ValueError,match='LIVE_EXACT_WRITE_PERMIT_REQUIRED'):c._request('POST','/v2/orders',PAYLOAD)
 assert len(e.requests)==1

def test_error_evidence_never_contains_keys_headers_or_balance_values():
 body=json.dumps({'code':42210000,'message':f'{KEY} {SECRET} balance $487.42 account 123e4567-e89b-12d3-a456-426614174000','secret':'OTHER_SECRET','buying_power':'487.42'}).encode()
 _,_,exc=rejected(body);s=json.dumps(exc.http_error_evidence)
 for secret in [KEY,SECRET,'OTHER_SECRET','487.42','123e4567-e89b-12d3-a456-426614174000','APCA-API-SECRET-KEY']:assert secret not in s
 assert 'headers' not in exc.http_error_evidence

def test_http_error_body_is_bounded_and_prefix_hash_is_explicit():
 body=b'x'*20000;_,_,exc=rejected(body);d=exc.http_error_evidence
 assert d['body_truncated'] and d['body_prefix_bytes']==8192
 assert d['body_prefix_sha256']==hashlib.sha256(body[:8192]).hexdigest()
 assert d['body_format']=='NON_JSON' and d['message'] is None

def test_body_read_failure_preserves_original_http_error_without_retry():
 _,e,exc=rejected(b'',broken=True)
 assert exc.status_code==422 and len(e.requests)==1
 assert exc.http_error_evidence['body_capture_status']=='UNAVAILABLE'

def test_unknown_json_body_fields_are_not_persisted():
 _,_,exc=rejected(b'{"code":42210000,"message":"rejected","account":{"cash":"999"},"unknown":"secret"}')
 s=json.dumps(exc.http_error_evidence);assert '999' not in s and 'unknown' not in s and 'secret' not in s

def test_existing_monthly_observation_retains_error_evidence_without_resend(setup,tmp_path,monkeypatch):
 from test_alpaca_monthly_cycle_custody_v1 import wired
 m,n,s,broker,now=wired(setup,tmp_path)
 _,_,exc=rejected(b'{"code":42210000,"message":"fixture rejected"}')
 def failed(**kwargs):raise exc
 monkeypatch.setattr(m,'recover',lambda *a,**kw:failed())
 out=m.tick(n,now_ms=now,apply=True)
 issue=next(i for i in out['issues'] if i['phase']=='RECOVERY')
 assert issue['http_error_evidence']['broker_code']==42210000
 assert out['entry_status']=='BLOCKED' and broker.sent==[]
 rows=[json.loads(p.read_bytes()) for p in (m.root/'observations').glob('*.json')]
 assert any(any(i.get('http_error_evidence',{}).get('broker_code')==42210000 for i in row['result'].get('issues',[])) for row in rows)

from test_alpaca_monthly_native_binding_v1 import setup

def test_monetary_contexts_redact_integer_single_decimal_exponent_and_comma_amounts():
 body=json.dumps({'code':42210000,'message':'available 4321, cash 814.5, equity 1e4, balance EUR 4,321.00; notional must have at most 2 decimal places'}).encode()
 _,_,exc=rejected(body);s=exc.http_error_evidence['message']
 for amount in ['4321','814.5','1e4','4,321.00']:assert amount not in s
 # Mixed monetary messages fail closed for all numbers; the pure precision
 # message remains exact in test_real_http422_preserves... above.
 assert 'decimal places' in s

@pytest.mark.parametrize('credential',[KEY,SECRET])
def test_request_id_containing_credential_is_omitted(credential):
 h=Message();h['X-Request-ID']='request-'+credential
 _,_,exc=rejected(b'{"code":42210000,"message":"rejected"}',h)
 assert exc.http_error_evidence['request_id'] is None

@pytest.mark.parametrize('message',['cash balance of 4321 is insufficient','available balance: -$4,321'])
def test_monetary_message_fails_closed_for_unrecognized_amount_format(message):
 _,_,exc=rejected(json.dumps({'code':42210000,'message':message}).encode())
 assert not any(c.isdigit() for c in exc.http_error_evidence['message'])
