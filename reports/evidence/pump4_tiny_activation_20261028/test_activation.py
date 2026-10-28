from pathlib import Path
import importlib.util,json,copy
import pytest
s=importlib.util.spec_from_file_location('activation',Path(__file__).with_name('activation.py'));m=importlib.util.module_from_spec(s)
# The module is not implemented yet; fail visibly rather than silently skip.
try:s.loader.exec_module(m)
except FileNotFoundError:m=None

def before():
 return dict(config=dict(mode='ORDERS_OFF',app_root='/old/app',source_files={'x':'old'},execution_policy=dict(source_manifest_sha256='old',risk_policy_sha256='risk',max_delay_ms=60000,max_reference_drift_bps='10'),custody_runtime_root='/old/runtime',epoch_started_ms=1,entry_max_delay_ms=60000,guard_source_files={},authority={}),scope=dict(schema='PUMP4_ACCOUNT_OWNER_SCOPE_V1',mode='ORDERS_OFF',root='/old/runtime',policy=dict(allocation_usdt='50',gross_usdt='30',reserve_usdt='20',risk_usdt='1',day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',slippage_bps='10',max_entries=1,max_positions=1),execution_policy=dict(source_manifest_sha256='old',risk_policy_sha256='risk',max_delay_ms=60000,max_reference_drift_bps='10'),valid_from_ms=1,valid_until_ms=9999999),old_config_path='/old/runner.json',units={'pump4-execution-owner.service':'ExecStart=/old/app/run --config /old/runner.json --config-sha256 '+('a'*64)+' --orders-off\nReadWritePaths=/old/runtime /existing/account.lock\n'})

def test_builder_preserves_budget_and_delayed_entry_but_uses_activation_epoch():
 assert m is not None
 b=before();p=dict(packet_dir='/packet',financial_app='/new/app',financial_source_files={'x':'new'},live_root='/new/runtime',notification_pin='n',health_pin='h',wrapper_path='/health.py',wrapper_new='new wrapper',extra_guard_files={'/packet/health.py':'h'})
 result=m.build_generated(b,p,2000)
 c,s=result['config'],result['scope']
 assert c['mode']==s['mode']=='OWNER_TINY_LIVE' and c['epoch_started_ms']==s['valid_from_ms']==2000
 assert s['valid_until_ms']==b['scope']['valid_until_ms'] and s['policy']==b['scope']['policy']
 assert c['data_source'] if 'data_source' in c else True
 assert c['execution_policy']==s['execution_policy'] and c['execution_policy']['max_delay_ms']==60000
 assert c['execution_policy']['max_reference_drift_bps']=='10' and c['execution_policy']['risk_policy_sha256']=='risk'
 assert '--dispatch' in result['unit'] and '--orders-off' not in result['unit'] and '/new/app/run' in result['unit']
 assert c['authority']['sha256']==m.sha(m.encode(s)) and s['runner_config_sha256']==m.digest({k:v for k,v in c.items() if k!='authority'})
 assert result['go']==dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=m.digest(s),owner_go_text='GO PUMP4_TINY '+m.digest(s))
 assert b==before()

@pytest.mark.parametrize('field,value',[('risk_usdt','2'),('gross_usdt','31'),('max_entries',2),('reserve_usdt','0')])
def test_packet_cannot_raise_or_reinterpret_policy(field,value):
 assert m is not None
 b=before();b['scope']['policy'][field]=value
 with pytest.raises(AssertionError):m.policy_check(b['scope']['policy'])

def test_rollback_never_stops_or_erases_owned_custody(tmp_path,monkeypatch):
 assert m is not None
 root=tmp_path/'live';root.mkdir();(root/'admitted-lifecycle.json').write_text('{}')
 calls=[];monkeypatch.setattr(m,'ctl',lambda *a:calls.append(a))
 assert m.revoke_and_is_empty(root,'scope') is False
 assert (root/'entry-revoked.json').is_file() and (root/'admitted-lifecycle.json').read_text()=='{}' and not calls

@pytest.mark.parametrize('name',['tickets/x.json','send-barriers/x.json','supervisor/attempts/x.json','risk.jsonl','flows/x/execution.jsonl'])
def test_rollback_blocks_on_any_potential_financial_history(tmp_path,name):
 assert m is not None
 p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
 assert m.revoke_and_is_empty(tmp_path,'scope') is False and p.read_text()=='{}'

def test_new_entry_revocation_is_durable_and_repeat_is_identical(tmp_path):
 assert m is not None
 assert m.revoke_and_is_empty(tmp_path,'scope') is True
 raw=(tmp_path/'entry-revoked.json').read_bytes()
 assert m.revoke_and_is_empty(tmp_path,'scope') is True and (tmp_path/'entry-revoked.json').read_bytes()==raw

@pytest.fixture
def physical_fixture(tmp_path,monkeypatch):
 import time
 b=before();folder=tmp_path/'packet';folder.mkdir();root=tmp_path/'live';unit=tmp_path/'pump4-execution-owner.service';wrapper=tmp_path/'health.py';wrapper.write_text('old wrapper');unit.write_text(b['units'][unit.name]);monkeypatch.setattr(m,'UNIT',unit)
 lock=tmp_path/'account.lock';lock.touch();observer=tmp_path/'observer.lock';observer.touch();spec=tmp_path/'spec.json';spec.write_text(json.dumps(dict(observer_lock=str(observer))))
 b['wrapper']=dict(text='old wrapper');b['scope'].update(account_lock_path=str(lock),account_lock_inode=lock.stat().st_ino,valid_from_ms=1,valid_until_ms=int(time.time()*1000)+3600000)
 oldroot=tmp_path/'old';oldroot.mkdir();b['scope']['root']=b['config']['custody_runtime_root']=str(oldroot)
 b['units'][unit.name]=unit.read_text().replace('/old/runtime',str(oldroot));unit.write_text(b['units'][unit.name])
 cp=tmp_path/'old-runner.json';b['old_config_path']=str(cp);cp.write_bytes(m.encode(b['config']))
 p=dict(packet_dir=str(folder),financial_app='/new/app',financial_source_files={'x':'new'},live_root=str(root),notification_pin='n',health_pin='h',wrapper_path=str(wrapper),wrapper_new='new wrapper',extra_guard_files={},health_spec=dict(path=str(spec),sha256=m.sha(spec.read_bytes())),policy=b['scope']['policy'])
 states=dict(ActiveState='active',MainPID='123',DropInPaths='',ExecStop='',ExecStopPost='',Job='',NRestarts='0');calls=[]
 def ctl(*args):
  calls.append(args)
  if args[0]=='stop':states.update(ActiveState='inactive',MainPID='0')
  if args[0]=='start':
   states.update(ActiveState='active',MainPID='124')
   if (folder/'runner.json').exists() and '--dispatch' in unit.read_text():
    c=json.loads((folder/'runner.json').read_bytes());scope=json.loads((folder/'scope.json').read_bytes());q=root/'supervisor/receipts';q.mkdir(parents=True,exist_ok=True);(q/'first.json').write_text(json.dumps(dict(pid=124,scope_sha256=m.digest(scope),runner_config_sha256=m.sha(m.encode(c)),mode='OWNER_TINY_LIVE',observed_ms=int(time.time()*1000),result=dict(status='NO_NEW_SIGNAL'),broker_writes=None)))
  return ''
 monkeypatch.setattr(m,'ctl',ctl);monkeypatch.setattr(m.base,'ctl',ctl);monkeypatch.setattr(m,'state',lambda *_:dict(states));monkeypatch.setattr(m.base,'state',lambda *_:dict(states));monkeypatch.setattr(m,'held',lambda *_:True)
 monkeypatch.setattr(m,'static_guards',lambda *_:None);monkeypatch.setattr(m,'off_not_sent',lambda *_:None)
 monkeypatch.setattr(m,'fresh_flat',lambda *_:dict(observed_ms=int(time.time()*1000),source_ms=int(time.time()*1000)-1,positions_flat=True,open_orders_empty=True))
 monkeypatch.setattr(m,'readback',lambda *_:dict(status='LIVE_ARMED_HEALTHY'))
 monkeypatch.setattr(m.subprocess,'run',lambda args,**kw:None)
 return folder,p,b,states,calls,unit,wrapper,root

def test_activation_once_real_files_and_scope_no_old_h1_adoption(physical_fixture):
 f,p,b,st,calls,u,w,root=physical_fixture
 r=m.activate(f,p,b);assert r['status']=='LIVE_ARMED_HEALTHY'
 assert calls.count(('start',u.name))==1 and calls.count(('stop',u.name))==1
 c=json.loads((f/'runner.json').read_bytes());s=json.loads((f/'scope.json').read_bytes());assert s['policy']==m.POLICY and c['epoch_started_ms']==s['valid_from_ms']>b['config']['epoch_started_ms']
 assert json.loads((root/'owner-go.json').read_bytes())['scope_sha256']==m.digest(s)
 with pytest.raises(AssertionError,match='ALREADY_ATTEMPTED'):m.activate(f,p,b)
 assert calls.count(('start',u.name))==1

def test_start_error_leaves_claim_and_no_automatic_retry_or_rollback(physical_fixture,monkeypatch):
 f,p,b,st,calls,u,w,root=physical_fixture;original=m.ctl
 def failed(*args):
  if args[0]=='start':calls.append(args);raise OSError('fixture start unknown')
  return original(*args)
 monkeypatch.setattr(m,'ctl',failed)
 with pytest.raises(OSError):m.activate(f,p,b)
 assert (f/'activation-claim.json').exists() and (root/'owner-go.json').exists() and '--dispatch' in u.read_text()
 assert calls.count(('start',u.name))==1
 with pytest.raises(AssertionError):m.activate(f,p,b)
 assert calls.count(('start',u.name))==1

@pytest.mark.parametrize('stage',['no_generated_scope','only_scope'])
def test_partial_activation_rollback_before_go_restores_original_off(physical_fixture,stage):
 f,p,b,st,calls,u,w,root=physical_fixture
 root.mkdir();g=m.build_generated(b,p,b['scope']['valid_until_ms']-10000)
 if stage=='only_scope':(f/'scope.json').write_bytes(m.encode(g['scope']))
 (f/'activation-claim.json').write_text('{}');st.update(ActiveState='inactive',MainPID='0')
 r=m.rollback(f,p,b)
 assert 'OFF' in r['status'] and '--orders-off' in u.read_text() and w.read_text()=='old wrapper'
 assert (root/'entry-revoked.json').exists() and not (root/'owner-go.json').exists()

def test_default_cli_cannot_create_authority_or_call_systemd(tmp_path):
 import subprocess,sys
 before=set(tmp_path.rglob('*'))
 result=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('activation.py'))],cwd=tmp_path,capture_output=True,text=True,check=True)
 assert json.loads(result.stdout)['status']=='NO_REQUESTS_NO_GO' and set(tmp_path.rglob('*'))==before

def test_go_permissions_are_0600_even_with_permissive_shell_umask(physical_fixture):
 import os,stat
 f,p,b,st,calls,u,w,root=physical_fixture;oldmask=os.umask(0o022)
 try:m.activate(f,p,b)
 finally:os.umask(oldmask)
 assert stat.S_IMODE((root/'owner-go.json').stat().st_mode)==0o600

def test_optimized_python_cannot_bypass_owner_authorization(tmp_path):
 import subprocess,sys
 path=Path(__file__).with_name('activation.py')
 code="import importlib.util,sys,json; p=sys.argv[1]; s=importlib.util.spec_from_file_location('isolated',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.load_packet=lambda *a:({},{}); m.activate=lambda *a:dict(status='UNAUTHORIZED_ACTIVATION_REACHED'); sys.argv=['x','--packet',sys.argv[2],'--packet-sha256','"+('a'*64)+"','--activate-once']; m.main()"
 got=subprocess.run([sys.executable,'-O','-B','-c',code,str(path),str(tmp_path/'packet.json')],cwd=tmp_path,capture_output=True,text=True)
 assert got.returncode!=0 and 'OPTIMIZED_PYTHON_FORBIDDEN' in got.stderr
 assert 'UNAUTHORIZED_ACTIVATION_REACHED' not in got.stdout
