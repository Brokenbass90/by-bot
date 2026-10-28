"""Actual GET transport through fictional HTTP bodies; no credentials or network."""
import copy,json,hashlib,importlib,urllib.parse
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_pump4_account_owner_v1 import create,inputs,KEY,SECRET,FP
from research_lab.pump4_bybit_sources_v1 import account_view,H
from research_lab.pump4_account_adapter_v1 import owned_observation


def mod():
 try:return importlib.import_module('research_lab.pump4_runtime_sources_v1')
 except ImportError:pytest.fail('Selected runner is missing its trusted fresh GET provider')


def wire_fixture(exchange,now,*,fail=None,partial=False):
 bundle,public=inputs(exchange,now=now);calls=[]
 def wire(method,url,headers,data,timeout):
  assert method=='GET' and data is None
  u=urllib.parse.urlsplit(url);q=dict(urllib.parse.parse_qsl(u.query));calls.append((u.path,q))
  if fail==u.path:raise OSError('fixture source unavailable')
  path=u.path
  if path=='/v5/market/instruments-info':body=copy.deepcopy(public['instruments']['pages'][0]['body'])
  elif path in {'/v5/order/history','/v5/execution/list','/v5/account/transaction-log'}:
   key={'/v5/order/history':'history','/v5/execution/list':'executions','/v5/account/transaction-log':'transactions'}[path]
   body=copy.deepcopy(bundle['history_windows'][0]['groups'][key]['pages'][0]['body'])
   if partial and key=='transactions':body['result']['nextPageCursor']='loop'
  else:
   key=next(k for k,v in bundle['captures'].items() if v.get('pages',[v])[0].get('endpoint')==path and (k!='symbol_position' or 'symbol' in q)) if path!='/v5/position/list' else ('symbol_position' if 'symbol' in q else 'positions')
   cap=bundle['captures'][key];body=copy.deepcopy(cap.get('pages',[cap])[0]['body'])
  if path in ('/v5/account/fee-rate','/v5/market/tickers') and q.get('symbol'):
   body['result']['list']=[r for r in body['result']['list'] if r['symbol']==q['symbol']]
  return 200,json.dumps(body).encode()
 return wire,calls


def test_full_capture_reuses_get_transport_and_keeps_history_anchor(tmp_path):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  wire,calls=wire_fixture(e,t[0]);provider=m.TrustedSources({},o,wire=wire,clock=lambda:t[0])
  bundle,public=provider.account(f.config['plan'],custody=False)
  assert account_view(bundle,expected_fingerprint=FP,now_ms=t[0])['positions_flat']
  assert bundle['history_start_ms']==f.config['plan']['entry_bar_open_ms']
  assert public['quote']==bundle['captures']['quote']
  assert any(p=='/v5/position/list' and q.get('symbol')=='ZROUSDT' for p,q in calls)
  assert all(c['account_fingerprint']==FP for v in bundle['captures'].values() for c in v.get('pages',[v]) if c['signed'])
  assert list((o.root/'source-captures').glob('*.json')) and e.state['calls']==0
 finally:lease.close()


def test_custody_does_not_wait_for_entry_instrument_source(tmp_path):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  wire,calls=wire_fixture(e,t[0],fail='/v5/market/instruments-info')
  bundle,public=m.TrustedSources({},o,wire=wire,clock=lambda:t[0]).account(f.config['plan'],custody=True)
  owned_observation(bundle,f.config['plan'],[],first_send_ms=f.config['plan']['entry_bar_open_ms'],expected_fingerprint=FP,now_ms=t[0])
  assert not any(p=='/v5/market/instruments-info' for p,q in calls) and e.state['calls']==0
 finally:lease.close()


@pytest.mark.parametrize('fault',['partial','network'])
def test_incomplete_or_failed_get_never_yields_admission(tmp_path,fault):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  wire,calls=wire_fixture(e,t[0],partial=fault=='partial',fail='/v5/account/wallet-balance' if fault=='network' else None)
  with pytest.raises(ValueError):m.TrustedSources({},o,wire=wire,clock=lambda:t[0]).account(f.config['plan'],custody=False)
  assert e.state['calls']==0
 finally:lease.close()


def test_source_provider_can_never_accept_post(tmp_path):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  p=m.TrustedSources({},o,wire=lambda *a:pytest.fail('unexpected wire'),clock=lambda:t[0])
  with pytest.raises(ValueError):p.get_wire('POST','https://api.bybit.com/v5/order/create',{},b'{}',1)
 finally:lease.close()


def test_candidate_requires_pinned_data_binding_and_never_repairs_journal(tmp_path):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  p=m.TrustedSources({},o,wire=lambda *a:pytest.fail('unexpected wire'),clock=lambda:t[0])
  with pytest.raises(ValueError,match='DATA_BINDING'):p.candidate()
  assert not (o.root/'admitted-lifecycle.json').exists() and e.state['calls']==0
 finally:lease.close()


def bound_candidate(tmp_path):
 from test_pump4_supervisor_v1 import fixture_candidate,NOW
 from research_lab.pump4_selected_runner_v1 import source_pins,ROOT
 candidate=fixture_candidate(tmp_path/'fixture');app=tmp_path/'data-app';root=app/'.private/state'
 (root/'intake').mkdir(parents=True);(root/'observations').mkdir()
 source=root/'intake/ZROUSDT.jsonl';source.write_bytes(candidate['intake'].journal.path.read_bytes());source.chmod(0o600)
 d=candidate['intake'].snapshot()['decisions'][-1]
 observation=dict(decision=d,mode='CURRENT_CLOSED_BAR',status='CAUSAL_PLAN_DATA_ONLY',orders_allowed=False,money_authority=False)
 (root/'observations'/(d['decision_id']+'.json')).write_text(json.dumps(observation))
 pins=source_pins()
 for n in pins:
  p=app/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/n).read_bytes())
 binding=root/'data-binding.json';binding.write_text(json.dumps(dict(schema='PUMP4_DATA_SUPERVISOR_V1',universe_sha256=__import__('research_lab.pump4_bybit_sources_v1',fromlist=['UNIVERSE_SHA']).UNIVERSE_SHA,source_files=pins,orders_allowed=False,money_authority=False)))
 config=dict(epoch_started_ms=NOW-1,entry_max_delay_ms=60000,data_source=dict(root=str(root),binding=dict(path=str(binding),sha256=hashlib.sha256(binding.read_bytes()).hexdigest())))
 def wire(method,url,headers,data,timeout):
  assert method=='GET' and data is None
  q=dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
  cap=next(c for c in candidate['captures'] if int(q['end'])==c['params']['end'])
  return 200,cap['raw'].encode()
 return config,candidate,wire,source


def test_current_candidate_replays_frozen_decision_and_fresh_captures(tmp_path):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  c,candidate,wire,path=bound_candidate(tmp_path);before=path.read_bytes()
  p=m.TrustedSources(c,o,wire=wire,clock=lambda:t[0]);got=p.candidate()
  assert got['decision_id']==candidate['decision_id'] and got['intake'].symbol=='ZROUSDT'
  assert path.read_bytes()==before and p.candidate() is None and e.state['calls']==0
 finally:lease.close()


@pytest.mark.parametrize('fault',['bootstrap','late','changed_code','changed_binding'])
def test_candidate_cannot_bypass_epoch_or_source_binding(tmp_path,fault):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  c,candidate,wire,path=bound_candidate(tmp_path);root=Path(c['data_source']['root']);observation=next((root/'observations').glob('*.json'))
  if fault=='bootstrap':
   r=json.loads(observation.read_bytes());r['mode']='BOOTSTRAP_REPLAY';observation.write_text(json.dumps(r))
  if fault=='late':t[0]+=60001
  if fault=='changed_code':(root.parent.parent/'strategies/signals.py').write_text('changed')
  if fault=='changed_binding':(root/'data-binding.json').write_text('{}')
  p=m.TrustedSources(c,o,wire=wire,clock=lambda:t[0])
  if fault in {'bootstrap','late'}:assert p.candidate() is None
  else:
   with pytest.raises(ValueError):p.candidate()
  assert not (o.root/'admitted-lifecycle.json').exists() and e.state['calls']==0
 finally:lease.close()


def test_alert_reuses_only_explicitly_pinned_existing_channel(tmp_path,monkeypatch):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  cfg=tmp_path/'notification.json';cfg.write_text(json.dumps(dict(scope_label='Trading OS PUMP4',output_root=str(o.root/'alerts'),telegram_env='fixture-env',telegram_env_sha256='1'*64,telegram_helper='fixture-helper',telegram_helper_sha256='2'*64)))
  config=dict(notifications=dict(path=str(cfg),sha256=hashlib.sha256(cfg.read_bytes()).hexdigest()))
  from research_lab import alpaca_day_monitor_v1 as channel
  events=[];monkeypatch.setattr(channel,'telegram',lambda c,e:(events.append((c,e)) or dict(delivered=True)))
  provider=m.TrustedSources(config,o,wire=lambda *a:pytest.fail('no account GET'),clock=lambda:t[0])
  result=provider.alert(dict(status='BLOCKED_OBSERVATION',terminal_id='a'*64))
  assert result['delivered'] and events[0][0]['scope_label']=='Trading OS PUMP4'
  assert events[0][1]['issues']==[dict(code='BLOCKED_OBSERVATION')] and e.state['calls']==0
  cfg.write_text('{}')
  with pytest.raises(ValueError):provider.alert(dict(status='BLOCKED_OBSERVATION',terminal_id='b'*64))
  assert len(events)==1
 finally:lease.close()


def test_flat_handoff_uses_recent_account_capture_not_historical_strategy_plan(tmp_path):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  wire,calls=wire_fixture(e,t[0]);provider=m.TrustedSources({},o,wire=wire,clock=lambda:t[0])
  bundle,public=provider.flat()
  assert bundle['history_start_ms']==t[0]-H
  assert account_view(bundle,expected_fingerprint=FP,now_ms=t[0])['positions_flat']
  assert not any(p=='/v5/market/instruments-info' or 'symbol' in q for p,q in calls)
  assert e.state['calls']==0 and not (o.root/'admitted-lifecycle.json').exists()
 finally:lease.close()


def negative_provider(tmp_path):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 c,candidate,wire,journal=bound_candidate(tmp_path);root=Path(c['data_source']['root']);obs=next((root/'observations').glob('*.json'))
 r=json.loads(obs.read_bytes());r['decision']['signal']=None;obs.write_text(json.dumps(r))
 return m,m.TrustedSources(c,o,wire=wire,clock=lambda:t[0]),obs,t,lease


def test_immutable_negative_observation_is_not_decoded_every_poll(tmp_path,monkeypatch):
 m,p,obs,t,lease=negative_provider(tmp_path)
 try:
  calls=[];original=m.decode
  def counted(raw):
   if raw==obs.read_bytes():calls.append(1)
   return original(raw)
  monkeypatch.setattr(m,'decode',counted)
  assert p.candidate() is None and p.candidate() is None
  assert len(calls)==1
 finally:lease.close()


@pytest.mark.parametrize('fault',['replace','overwrite','permissions','directory_symlink'])
def test_negative_cache_rechecks_changed_custody(tmp_path,fault):
 m,p,obs,t,lease=negative_provider(tmp_path)
 try:
  assert p.candidate() is None
  r=json.loads(obs.read_bytes());r['orders_allowed']=True;raw=json.dumps(r)
  if fault=='replace':
   new=obs.with_suffix('.new');new.write_text(raw);new.replace(obs)
  elif fault=='overwrite':obs.write_text(raw)
  elif fault=='permissions':obs.write_text(raw);obs.chmod(0o644)
  else:
   directory=obs.parent;other=directory.with_name('moved-observations');directory.rename(other);directory.symlink_to(other,target_is_directory=True)
  with pytest.raises(ValueError):p.candidate()
 finally:lease.close()


def test_expired_cache_reconsiders_signal_after_clock_rollback(tmp_path):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  c,candidate,wire,path=bound_candidate(tmp_path);p=m.TrustedSources(c,o,wire=wire,clock=lambda:t[0]);now=t[0]
  t[0]+=60001;assert p.candidate() is None and p.candidate() is None
  t[0]=now;got=p.candidate();assert got['decision_id']==candidate['decision_id']
 finally:lease.close()


def test_observation_replaced_during_fd_read_is_not_cached(tmp_path,monkeypatch):
 m,p,obs,t,lease=negative_provider(tmp_path)
 try:
  original=m.os.read;changed=[];inode=obs.stat().st_ino
  def raced(fd,n):
   raw=original(fd,n)
   if m.os.fstat(fd).st_ino==inode and not changed:
    changed.append(True);new=obs.with_suffix('.replacement');new.write_bytes(obs.read_bytes());new.replace(obs)
   return raw
  monkeypatch.setattr(m.os,'read',raced)
  with pytest.raises(ValueError,match='OBSERVATION_(CHANGED|CUSTODY)'):p.candidate()
  assert not p._negative_observations
 finally:lease.close()


def test_replacing_cached_negative_with_signal_still_verifies_live_journal(tmp_path):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  c,candidate,wire,journal=bound_candidate(tmp_path);obs=next((Path(c['data_source']['root'])/'observations').glob('*.json'));original=obs.read_bytes();r=json.loads(original);r['decision']['signal']=None;obs.write_text(json.dumps(r))
  p=m.TrustedSources(c,o,wire=wire,clock=lambda:t[0]);assert p.candidate() is None
  obs.write_bytes(original);journal.write_bytes(b'changed journal')
  with pytest.raises(ValueError):p.candidate()
  assert not p._candidate_consumed and e.state['calls']==0
 finally:lease.close()


@pytest.mark.parametrize('custody',[False,True])
def test_owned_capture_scopes_only_quote_and_fee_not_account_exposure(tmp_path,custody):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  wire,calls=wire_fixture(e,t[0]);p=m.TrustedSources({},o,wire=wire,clock=lambda:t[0]);bundle,public=p.account(f.config['plan'],custody=custody)
  for path in ('/v5/account/fee-rate','/v5/market/tickers'):
   assert any(route==path and q==dict(category='linear',symbol='ZROUSDT') for route,q in calls)
  assert any(route=='/v5/position/list' and q==dict(category='linear',settleCoin='USDT',limit='200') for route,q in calls)
  assert any(route=='/v5/order/realtime' and q.get('settleCoin')=='USDT' and 'symbol' not in q for route,q in calls)
  stored=next((o.root/'source-captures').glob('*.json'));cap=m.load_capture(stored)
  assert cap['bundle']==bundle and cap['public']==public and cap['custody']==custody
 finally:lease.close()

def test_health_flat_metadata_hint_does_not_filter_positions(tmp_path):
 m=mod();s=create(tmp_path);o,e,t,_,f,lease=s
 try:
  wire,calls=wire_fixture(e,t[0]);p=m.TrustedSources({},o,wire=wire,clock=lambda:t[0]);b,_=p.flat(metadata_symbol='ZROUSDT')
  assert account_view(b,expected_fingerprint=FP,now_ms=t[0])['positions_flat']
  assert any(route=='/v5/account/fee-rate' and q.get('symbol')=='ZROUSDT' for route,q in calls)
  assert not any('symbol' in q for route,q in calls if route in ('/v5/order/realtime','/v5/account/wallet-balance'))
 finally:lease.close()

def test_capture_archive_is_lossless_versioned_and_keeps_legacy_files(tmp_path):
 m=mod();payload=dict(bundle=dict(captures=dict(raw='original raw bytes '*10000),source_ms=1234),public={},custody=True)
 path=tmp_path/'archive.json';m.publish_capture(path,payload)
 assert path.stat().st_size<len(json.dumps(payload).encode())//10
 assert m.load_capture(path)==payload
 with pytest.raises(FileExistsError):m.publish_capture(path,payload)
 legacy=tmp_path/'legacy.json';legacy.write_text(json.dumps(payload));assert m.load_capture(legacy)==payload
 bad=json.loads(path.read_bytes());bad['uncompressed_sha256']='0'*64;path.write_text(json.dumps(bad))
 with pytest.raises(ValueError):m.load_capture(path)

def test_capture_archive_refuses_oversized_decoded_bytes(tmp_path):
 m=mod();p=tmp_path/'archive.json';m.publish_capture(p,dict(raw='a'*10000))
 with pytest.raises(ValueError):m.load_capture(p,max_bytes=100)


def test_archive_legacy_and_encoded_input_are_bounded_before_decode(tmp_path,monkeypatch):
 m=mod();p=tmp_path/'legacy.json';p.write_text(json.dumps(dict(raw='a'*10000)))
 with pytest.raises(ValueError):m.load_capture(p,max_bytes=100)
 q=tmp_path/'envelope.json';q.write_text(json.dumps(dict(schema='PUMP4_LOSSLESS_GET_ARCHIVE_V1',payload='A'*100000)))
 calls=[];original=m.decode
 monkeypatch.setattr(m,'decode',lambda raw:(calls.append(True) or original(raw)))
 with pytest.raises(ValueError):m.load_capture(q,max_bytes=100)
 assert not calls
