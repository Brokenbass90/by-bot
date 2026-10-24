"""Selected runner factory; fake unit/profile only, real temporary flock."""
import copy,hashlib,json
from contextlib import contextmanager
from pathlib import Path
import pytest
from test_pump4_account_owner_v1 import create,inputs,KEY,SECRET,FP
from research_lab.alpaca_dynamic_v1 import digest


def module():
 try:from research_lab import pump4_selected_runner_v1 as m
 except ImportError:pytest.fail('Selected physical PUMP runner is not wired to the accepted financial owner')
 return m


def fixture(tmp_path,monkeypatch,*,dispatch=False,go=True):
 m=module();s=create(tmp_path);o,e,t,c,f,lease=s;lease.close()
 lock=lease.path.parent/'account.lock';lease.path.rename(lock);lease.path=lock
 original=dict(unit='kity-execution-micro-owner.service',custody_runtime_root=str(lease.path.parent),account_lock_inode=lease.inode,account_fingerprint=FP,credential_source=str(tmp_path/'fixture-profile'),credential_source_sha256='1'*64)
 def save(name,value):
  p=tmp_path/name;p.write_text(json.dumps(value,sort_keys=True));return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 original_pin=save('original-config.json',original)
 config=dict(schema='PUMP4_SELECTED_ACCOUNT_RUNNER_V1',unit='pump4-execution-owner.service',app_root=str(m.ROOT),custody_runtime_root=str(tmp_path/'selected-account'),account_fingerprint=FP,credential_source=original['credential_source'],credential_source_sha256=original['credential_source_sha256'],original_owner=original_pin,inhibitors={original['unit']:'2'*64},source_files=m.source_pins(),entry_max_delay_ms=60000,epoch_started_ms=t[0]-2)
 scope=copy.deepcopy(o.scope);scope['account_lock_path']=str(lock);scope.update(root=config['custody_runtime_root'],mode='OWNER_TINY_LIVE' if dispatch else 'ORDERS_OFF',runner_config_sha256=m.config_sha(config))
 config['authority']=save('scope.json',scope)
 path=tmp_path/'config.json';path.write_text(json.dumps(config,sort_keys=True));pin=hashlib.sha256(path.read_bytes()).hexdigest()
 called=[]
 def check():called.append('physical')
 monkeypatch.setattr(m,'platform_verifier',lambda x:check)
 monkeypatch.setattr(m,'load_bound_credentials',lambda x:(called.append('credentials') or (KEY,SECRET)))
 if go and dispatch:
  root=Path(scope['root']);root.mkdir();(root/'owner-go.json').write_text(json.dumps(dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=digest(scope),owner_go_text='GO PUMP4_TINY '+digest(scope))));(root/'owner-go.json').chmod(0o600)
 return m,s,path,pin,config,scope,called


def test_orders_off_selected_factory_holds_original_lease_and_has_no_wire(tmp_path,monkeypatch):
 m,s,path,pin,c,scope,called=fixture(tmp_path,monkeypatch);o,e,t,_,f,l=s
 with m.selected_owner(path,pin,dispatch=False,clock=lambda:t[0]) as selected:
  from research_lab.kity_micro_physical_owner_v1 import AccountLease
  with pytest.raises(BlockingIOError):AccountLease(l.path)
  x,p=inputs(e,now=t[0]);r=selected.cycle(selected.prepare(f.config['plan'],x,p),x,p,apply=False)
  assert r['status']=='ACTION_RESERVED_ORDERS_OFF' and e.state['calls']==0
 assert called[0]=='physical' and 'credentials' in called


def test_missing_go_blocks_before_profile_or_lease(tmp_path,monkeypatch):
 m,s,path,pin,c,scope,called=fixture(tmp_path,monkeypatch,dispatch=True,go=False)
 with pytest.raises(ValueError,match='EXACT_OWNER_GO'):
  with m.selected_owner(path,pin,dispatch=True):pytest.fail('must not construct')
 assert called==[]


def test_kity_cannot_be_relabelled_as_pump_owner(tmp_path,monkeypatch):
 m,s,path,pin,c,scope,called=fixture(tmp_path,monkeypatch)
 c['unit']='kity-execution-micro-owner.service';path.write_text(json.dumps(c));pin=hashlib.sha256(path.read_bytes()).hexdigest()
 with pytest.raises(ValueError,match='SEPARATE_SELECTED_OWNER'):
  with m.selected_owner(path,pin,dispatch=False):pytest.fail('must not construct')
 assert not called


def test_causal_entry_rejects_bootstrap_even_with_fresh_account(tmp_path,monkeypatch):
 from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
 m=module();x=json.loads((Path(__file__).parent/'fixtures/pump4_cycle_20261022.json').read_bytes())
 journal=Pump4Intake(tmp_path/'intake.jsonl',x['symbol']);entry=x['signal_bar'][0]+3600000
 journal.seed(x['seed'],available_ms=entry,observed_ms=entry)
 result=journal.accept(x['signal_bar'],available_ms=entry+1,observed_ms=entry+1)
 with pytest.raises(ValueError,match='PROSPECTIVE'):
  m.causal_plan(journal,result['decision']['decision_id'],[],epoch_started_ms=entry,max_delay_ms=60000,now_ms=entry+2)


def test_causal_entry_rejects_late_signal_before_source_or_owner(tmp_path):
 from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
 m=module();x=json.loads((Path(__file__).parent/'fixtures/pump4_cycle_20261022.json').read_bytes())
 journal=Pump4Intake(tmp_path/'intake.jsonl',x['symbol']);entry=x['signal_bar'][0]+3600000
 journal.seed(x['seed'],available_ms=entry-3600000,observed_ms=entry-3600000)
 result=journal.accept(x['signal_bar'],available_ms=entry+1,observed_ms=entry+1)
 with pytest.raises(ValueError,match='ENTRY_WINDOW'):
  m.causal_plan(journal,result['decision']['decision_id'],[],epoch_started_ms=entry-1,max_delay_ms=60000,now_ms=entry+60001)


def test_causal_plan_replays_actual_producer_and_preserves_frozen_geometry(tmp_path):
 from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
 from test_pump4_bybit_sources_v1 import capture
 m=module();x=json.loads((Path(__file__).parent/'fixtures/pump4_cycle_20261022.json').read_bytes())
 journal=Pump4Intake(tmp_path/'intake.jsonl',x['symbol']);entry=x['signal_bar'][0]+3600000
 journal.seed(x['seed'],available_ms=entry-3600000,observed_ms=entry-3600000)
 result=journal.accept(x['signal_bar'],available_ms=entry+1,observed_ms=entry+1)
 bars=[*x['seed'],x['signal_bar'],[entry,x['next_open'],x['next_open'],x['next_open'],x['next_open'],0.]]
 rows=[[str(b[0]),*[str(v) for v in b[1:]],'0'] for b in reversed(bars)]
 params=dict(category='linear',symbol=x['symbol'],interval='60',start=bars[0][0],end=entry+3600000-1,limit=1000)
 caps=[capture('/v5/market/kline',params,dict(category='linear',symbol=x['symbol'],list=rows[:1000]),at=entry),capture('/v5/market/kline',dict(params,end=int(rows[1000][0])+3600000-1),dict(category='linear',symbol=x['symbol'],list=rows[1000:]),at=entry)]
 plan=m.causal_plan(journal,result['decision']['decision_id'],caps,epoch_started_ms=entry-1,max_delay_ms=60000,now_ms=entry+2)
 assert plan==x['expected_plan']
 changed=copy.deepcopy(caps);changed[0]['body']['result']['list'][1][5]='1'
 changed[0]['raw']=json.dumps(changed[0]['body']);changed[0]['raw_sha256']=hashlib.sha256(changed[0]['raw'].encode()).hexdigest()
 with pytest.raises(ValueError,match='SOURCE_JOURNAL_CONFLICT'):
  m.causal_plan(journal,result['decision']['decision_id'],changed,epoch_started_ms=entry-1,max_delay_ms=60000,now_ms=entry+2)


def test_selected_factory_memory_cycle_restarts_with_one_original_lease(tmp_path,monkeypatch):
 m,s,path,pin,c,scope,called=fixture(tmp_path,monkeypatch,dispatch=True)
 o,e,t,_,f,l=s;monkeypatch.setattr(m,'wire_post',e.wire)
 for price,role in [('100','ENTRY'),('97.8','TP1'),('95.7','TP2')]:
  with m.selected_owner(path,pin,dispatch=True,clock=lambda:t[0]) as selected:
   x,p=inputs(e,now=t[0],price=price);flow=selected.prepare(f.config['plan'],x,p)
   assert selected.cycle(flow,x,p,apply=True)['role']==role
  t[0]+=1000
 with m.selected_owner(path,pin,dispatch=True,clock=lambda:t[0]) as selected:
  x,p=inputs(e,now=t[0],price='95.7');flow=selected.prepare(f.config['plan'],x,p)
  assert selected.cycle(flow,x,p,apply=True)['status']=='FLAT_COSTS_PENDING'
 assert len(e.state['submitted_links'])==3 and len(set(e.state['submitted_links']))==3


def test_failed_physical_verifier_never_loads_profile_or_opens_owner(tmp_path,monkeypatch):
 m,s,path,pin,c,scope,called=fixture(tmp_path,monkeypatch)
 def busy():raise ValueError('EXISTING_KITY_OWNER_ACTIVE')
 monkeypatch.setattr(m,'platform_verifier',lambda c:busy)
 with pytest.raises(ValueError,match='KITY_OWNER_ACTIVE'):
  with m.selected_owner(path,pin,dispatch=False):pytest.fail('must not construct')
 assert called==[] and not Path(scope['root']).exists()
