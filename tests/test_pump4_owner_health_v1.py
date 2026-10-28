import copy
import pytest
from scripts.pump4_owner_health_v1 import assess

def good():return dict(unit=dict(ActiveState='active',MainPID='123'),old_inhibited=True,lock_held=True,go_present=False,scope_digest='scope',config_sha256='config',receipt=dict(schema='PUMP4_EXECUTION_SUPERVISOR_RECEIPT_V1',mode='ORDERS_OFF',broker_writes=0,pid=123,scope_sha256='scope',runner_config_sha256='config',observed_ms=1000,result=dict(status='NO_NEW_SIGNAL')))
def test_off_is_observed_without_claiming_trading_or_protection():
 r=assess(good(),1001);assert r['status']=='HEALTHY' and r['orders_allowed'] is r['restart_allowed'] is r['financial_trading_proven'] is False
@pytest.mark.parametrize('field,value',[('old_inhibited',False),('lock_held',False),('go_present',True)])
def test_physical_conflict_fails(field,value):
 v=good();v[field]=value;assert assess(v,1001)['status']=='UNHEALTHY'
@pytest.mark.parametrize('field,value',[('pid',456),('observed_ms',1002),('observed_ms',0),('mode','OWNER_TINY_LIVE'),('broker_writes',1),('scope_sha256','wrong'),('runner_config_sha256','wrong'),('result',dict(status='BLOCKED_OBSERVATION'))])
def test_bad_or_stale_receipt_fails(field,value):
 v=good();v['receipt'][field]=value;assert assess(v,100000 if field=='observed_ms' and value==0 else 1001)['status']=='UNHEALTHY'


from scripts import pump4_owner_health_v1 as health
from test_pump4_account_adapter_v1 import fixture,reseal
from test_pump4_bybit_sources_v1 import account,NOW

def live_good(proof):
 v=good();v.update(mode='OWNER_TINY_LIVE',go_present=True,go_verified=True,live_evidence=proof)
 v['receipt'].update(mode='OWNER_TINY_LIVE',broker_writes=None,observed_ms=NOW+1)
 return v

def owned_flow():
 b,p,req=fixture();c=dict(domain='PUMP4_BYBIT_EXECUTION_ORDERS_OFF_V1',plan=p,qty='10',qty_step='.01',min_qty='.01',min_notional='5',tick_size='.01',orders_allowed=False,money_authority=False)
 return b,c,req

def test_live_flat_requires_real_fresh_account_without_claiming_protection():
 proof=health.live_evidence(account(),fingerprint='a'*64,now_ms=NOW+2)
 v=live_good(proof);r=assess(v,NOW+2)
 assert r['status']=='HEALTHY' and r['reason']=='LIVE_FLAT_WAITING_SIGNAL'
 assert r['actual_protection_proven'] is False and r['orders_allowed'] is False

@pytest.mark.parametrize('fault',['no_go','bad_go','stale_proof','wrong_mode','missing_proof'])
def test_live_cannot_be_enabled_by_heartbeat_or_boolean_only(fault):
 v=live_good(dict(status='LIVE_FLAT_WAITING_SIGNAL',source_ms=NOW,actual_protection_proven=False,financial_trading_proven=False))
 if fault=='no_go':v['go_present']=False
 if fault=='bad_go':v['go_verified']=False
 if fault=='stale_proof':v['live_evidence']['source_ms']=NOW-6000
 if fault=='wrong_mode':v['mode']='OTHER'
 if fault=='missing_proof':v.pop('live_evidence')
 assert assess(v,NOW+2)['status']=='UNHEALTHY'

def test_live_checks_full_native_stop_and_owned_fills_from_get():
 b,c,req=owned_flow();proof=health.live_evidence(b,fingerprint='a'*64,now_ms=NOW+2,config=c,requests=req)
 assert proof['status']=='LIVE_NATIVE_PROTECTED' and proof['held_qty']=='10'
 r=assess(live_good(proof),NOW+2)
 assert r['status']=='HEALTHY' and r['actual_protection_proven'] is True
 assert r['orders_allowed'] is r['restart_allowed'] is False

@pytest.mark.parametrize('fault',['native_missing','native_short','native_looser','native_wrong_side','foreign','held_not_fills','stale','wrong_account','unresolved_entry'])
def test_live_uncertain_or_unprotected_never_passes(fault):
 b,c,req=owned_flow();now=NOW+2
 if fault=='native_missing':b['captures']['orders']['pages'][0]['body']['result']['list']=[]
 if fault=='native_short':b['captures']['orders']['pages'][0]['body']['result']['list'][0]['qty']='9'
 if fault=='native_looser':
  b['captures']['orders']['pages'][0]['body']['result']['list'][0]['triggerPrice']='105'
  b['captures']['positions']['pages'][0]['body']['result']['list'][0]['stopLoss']='105'
 if fault=='native_wrong_side':b['captures']['orders']['pages'][0]['body']['result']['list'][0]['side']='Sell'
 if fault=='foreign':b['captures']['positions']['pages'][0]['body']['result']['list'].append(dict(symbol='BTCUSDT',side='Sell',size='1',positionIdx=0))
 if fault=='held_not_fills':
  b['captures']['positions']['pages'][0]['body']['result']['list'][0]['size']='9'
  b['captures']['orders']['pages'][0]['body']['result']['list'][0]['qty']='9'
 if fault=='stale':now+=6000
 if fault=='wrong_account':b['account_fingerprint']='b'*64
 if fault=='unresolved_entry':
  b['captures']['positions']['pages'][0]['body']['result']['list']=[]
  b['captures']['orders']['pages'][0]['body']['result']['list']=[]
  b['history_windows'][0]['groups']['history']['pages'][0]['body']['result']['list']=[]
  b['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['list']=[]
 reseal(b)
 with pytest.raises((ValueError,KeyError)):
  health.live_evidence(b,fingerprint='a'*64,now_ms=now,config=c,requests=req)

def test_live_no_admission_never_adopts_existing_position():
 b,c,req=owned_flow()
 with pytest.raises(ValueError):health.live_evidence(b,fingerprint='a'*64,now_ms=NOW+2)

def test_health_does_not_change_owner_or_flow_bytes(tmp_path):
 from test_pump4_account_owner_v1 import create,cycle,inputs,FP
 s=create(tmp_path);o,e,t,_,flow,lease=s
 try:
  cycle(s);t[0]+=1000;cycle(s)
  before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
  cfg,req,known,pin=health.read_flow(o.root,o.scope_sha256)
  b,_=inputs(e,now=t[0]);health.live_evidence(b,fingerprint=FP,now_ms=t[0],config=cfg,requests=req,known_native_ids=known)
  after={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
  assert before==after and e.state['calls']==1 and pin
 finally:lease.close()


@pytest.mark.parametrize('admitted',[False,True])
def test_live_collector_uses_get_without_owner_lease_or_lifecycle_constructor(tmp_path,monkeypatch,admitted):
 import json,hashlib
 from test_pump4_account_owner_v1 import create,cycle,KEY,SECRET,FP
 from test_pump4_runtime_sources_v1 import wire_fixture
 from research_lab import kity_micro_physical_owner_v1 as physical,pump4_runtime_sources_v1 as sources,pump4_account_owner_v1 as owner,pump4_execution_lifecycle_v1 as life
 s=create(tmp_path);o,e,t,_,flow,lease=s
 try:
  if admitted:cycle(s);t[0]+=1000
  packet=tmp_path/'packet';packet.mkdir();monkeypatch.setattr(health,'CONFIG',packet/'runner.json')
  original=dict(credential_source='fictional-only',credential_source_sha256='f'*64,account_fingerprint=FP)
  p=packet/'original.json';p.write_text(json.dumps(original));c=dict(original,original_owner=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
  monkeypatch.setattr(physical,'load_bound_credentials',lambda v:(KEY,SECRET))
  wire,calls=wire_fixture(e,t[0]);monkeypatch.setattr(sources,'wire_get',wire)
  monkeypatch.setattr(health.time,'time_ns',lambda:t[0]*1000000)
  def forbidden(*a,**k):pytest.fail('health instantiated monetary runtime')
  monkeypatch.setattr(physical,'AccountLease',forbidden);monkeypatch.setattr(owner.Pump4AccountOwner,'__init__',forbidden);monkeypatch.setattr(life.Pump4Lifecycle,'__init__',forbidden)
  before={str(p):p.read_bytes() for p in o.root.rglob('*') if p.is_file()}
  got=health.collect_live(c,o.scope)
  assert got['status']==('LIVE_NATIVE_PROTECTED' if admitted else 'LIVE_FLAT_WAITING_SIGNAL')
  assert before=={str(p):p.read_bytes() for p in o.root.rglob('*') if p.is_file()}
  assert e.state['calls']==int(admitted) and calls and all('/v5/order/create' not in x[0] for x in calls)
  assert list((packet/'health-readonly/source-captures').glob('*.json'))
 finally:lease.close()


@pytest.mark.parametrize('fault',['foreign_order','fill_side','fill_order_id','missing_order_row'])
def test_live_rejects_foreign_orders_or_incomplete_fill_ownership(fault):
 b,c,req=owned_flow()
 if fault=='foreign_order':b['captures']['orders']['pages'][0]['body']['result']['list'].append(dict(orderId='foreign',orderLinkId='foreign',symbol='BTCUSDT',side='Buy',qty='1',cumExecQty='0',orderStatus='New',reduceOnly=False,positionIdx=0,updatedTime=str(NOW)))
 if fault=='fill_side':b['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['list'][0]['side']='Buy'
 if fault=='fill_order_id':b['history_windows'][0]['groups']['executions']['pages'][0]['body']['result']['list'][0]['orderId']='another'
 if fault=='missing_order_row':b['history_windows'][0]['groups']['history']['pages'][0]['body']['result']['list']=[]
 reseal(b)
 with pytest.raises(ValueError):health.live_evidence(b,fingerprint='a'*64,now_ms=NOW+2,config=c,requests=req)
