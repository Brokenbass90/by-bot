"""Exact owner-approved PUMP4 one-lifecycle activation. Default: no requests.

No direct order API, reset or retry. An explicit reviewed packet GO is required
before changing money authority. Existing personal KITY/Monthly launchers unused.
"""
from pathlib import Path
import argparse,copy,fcntl,hashlib,importlib.util,json,os,re,subprocess,sys,time
if sys.flags.optimize != 0:raise RuntimeError('OPTIMIZED_PYTHON_FORBIDDEN')
HERE=Path(__file__).absolute().parent
spec=importlib.util.spec_from_file_location('pump4_base_ops',HERE/'base_ops.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
sha,encode,digest,safe,once,replace,ctl,state,held=base.sha,base.encode,base.digest,base.safe,base.once,base.replace,base.ctl,base.state,base.held
BASE=Path('/opt/bybot-research/pump4-server-orders-off-20261023')
UNIT=Path('/etc/systemd/system/pump4-execution-owner.service')
POLICY=dict(allocation_usdt='50',gross_usdt='30',reserve_usdt='20',risk_usdt='1',day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',slippage_bps='10',max_entries=1,max_positions=1)

def secure_once(path,raw):
 path=safe(path);fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  os.fchmod(fd,0o600)
  with os.fdopen(os.dup(fd),'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 finally:os.close(fd)
 directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(directory)
 finally:os.close(directory)


def policy_check(value):assert value==POLICY,'EXACT_50_30_20_RISK1_ONE_ENTRY_REQUIRED'

def build_generated(before,p,arm_ms):
 c=copy.deepcopy(before['config']);s=copy.deepcopy(before['scope']);policy_check(s['policy'])
 assert c['mode']==s['mode']=='ORDERS_OFF' and type(arm_ms) is int and s['valid_from_ms']<=arm_ms<s['valid_until_ms'],'AUTHORITY_MODE_OR_WINDOW'
 folder=Path(p['packet_dir']);c['mode']=s['mode']='OWNER_TINY_LIVE';c['app_root']=p['financial_app'];c['source_files']=p['financial_source_files'];c['custody_runtime_root']=s['root']=p['live_root']
 c['epoch_started_ms']=s['valid_from_ms']=arm_ms # financial admission only; DATA epochs/journals never change
 c['execution_policy']['source_manifest_sha256']=digest(c['source_files']);s['execution_policy']=copy.deepcopy(c['execution_policy'])
 assert c['execution_policy']['max_delay_ms']==c['entry_max_delay_ms']==60000 and c['execution_policy']['max_reference_drift_bps']=='10'
 c['notifications']=dict(path=str(folder/'notifications.json'),sha256=p['notification_pin'])
 c['guard_source_files'][p['wrapper_path']]=sha(p['wrapper_new'].encode());c['guard_source_files'].update(p['extra_guard_files'])
 unit=before['units'][UNIT.name].replace(before['old_config_path'],str(folder/'runner.json')).replace(before['config']['app_root'],p['financial_app']).replace(before['scope']['root'],p['live_root'])
 assert unit.count('--orders-off')==1;unit=unit.replace('--orders-off','--dispatch')
 c['unit_template_sha256']=sha(re.sub(r'--config-sha256 [0-9a-f]{64}','--config-sha256 <PIN>',unit).encode())
 s['runner_config_sha256']=digest({k:v for k,v in c.items() if k!='authority'})
 c['authority']=dict(path=str(folder/'scope.json'),sha256=sha(encode(s)))
 unit=re.sub(r'--config-sha256 [0-9a-f]{64}','--config-sha256 '+sha(encode(c)),unit)
 go=dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=digest(s),owner_go_text='GO PUMP4_TINY '+digest(s))
 return dict(config=c,scope=s,unit=unit,go=go)

def revoke_and_is_empty(root,scope_digest):
 root=safe(root);root.mkdir(mode=0o700,exist_ok=True)
 marker=root/'entry-revoked.json';value=dict(scope_sha256=scope_digest,reason='OWNER_PACKET_ROLLBACK_NO_NEW_ENTRY')
 if marker.exists():assert json.loads(marker.read_bytes())==value,'REVOCATION_SCOPE_CONFLICT'
 else:once(marker,encode(value))
 if any(os.path.lexists(root/n) for n in ('admitted-lifecycle.json','risk.jsonl')):return False
 return not any(any((root/n).rglob('*')) for n in ('tickets','send-barriers','supervisor/attempts','flows'))

def load_packet(folder,pin):
 folder=safe(folder);raw=(folder/'packet.json').read_bytes();assert sha(raw)==pin,'PACKET_PIN';p=json.loads(raw)
 assert p['schema']=='PUMP4_TINY_ACTIVATION_PACKET_V1' and Path(p['packet_dir'])==folder==HERE and folder.is_relative_to(BASE),'PACKET_PATH'
 policy_check(p['policy'])
 assert p['financial_app']==str(Path(p['financial_candidate']['path'])/'app') and safe(p['live_root']).is_relative_to(Path(p['financial_candidate']['path'])/'runtime'),'FINANCIAL_RUNTIME_PATH'
 for n,h in p['files'].items():assert '/' not in n and sha(safe(folder/n).read_bytes())==h,'PACKET_FILE_PIN'
 b=json.loads((folder/'before.json').read_bytes());assert b['scope']['policy']==p['policy'] and b['config']['mode']==b['scope']['mode']=='ORDERS_OFF'
 return p,b

def static_guards(p,b):
 policy_check(b['scope']['policy'])
 for item in ('financial_candidate','data_candidate'):
  x=p[item];base.verify_candidate(safe(x['path']),x['material_sha256'],x['manifest_sha256'])
  acceptance=json.loads((Path(x['path'])/'acceptance.json').read_bytes());assert acceptance['status']=='PASS' and acceptance['material_sha256']==x['material_sha256'] and acceptance['network_denied'] and acceptance['real_broker_writes']==acceptance['real_broker_requests']==0,'EXACT_ACCEPTANCE_REQUIRED'
 c=b['config']
 assert c['account_fingerprint']==b['scope']['account_fingerprint']==b['original']['account_fingerprint'],'ORIGINAL_ACCOUNT_SCOPE'
 for n,h in c['source_files'].items():assert sha((Path(c['app_root'])/n).read_bytes())==h,'ORIGINAL_OFF_SOURCE_DRIFT'
 base.monthly_health()
 lock=Path(b['scope']['account_lock_path']);assert lock.stat().st_ino==b['scope']['account_lock_inode']==818853 and lock.stat().st_nlink==1,'ORIGINAL_LOCK_IDENTITY'
 assert sha(Path(c['credential_source']).read_bytes())==c['credential_source_sha256'],'CREDENTIAL_BINDING_DRIFT'
 assert sha(subprocess.check_output(['crontab','-l']))==c['original_cron_sha256'],'CRON_DRIFT'
 assert sha(Path('/etc/systemd/system/alpaca-monthly-owned.service').read_bytes())==p['monthly_unit_sha256'],'MONTHLY_DRIFT'
 assert sha(Path('/etc/systemd/system/pump4-data-supervisor.service').read_bytes())==p['data_unit_sha256'],'DATA_UNIT_DRIFT'
 assert sha(Path(c['data_source']['binding']['path']).read_bytes())==c['data_source']['binding']['sha256'],'DATA_BINDING_DRIFT'
 ds=state('pump4-data-supervisor.service');assert ds['ActiveState']=='active' and held(Path(c['data_source']['root'])/'data-writer.lock',ds['MainPID']),'SOLE_DATA_WRITER'
 completed=sorted((Path(c['data_source']['root'])/'ws-hours').glob('*/receipt.json'));assert completed,'ACTUAL_H1_REQUIRED'
 last=json.loads(completed[-1].read_bytes());assert last['hour_pass'] and last['census']==137 and last['within60s']==last['expected_trading'] and 0<=time.time_ns()//1000000-last['source_hour_open_ms']<7200000,'RECENT_TIMELY_H1_REQUIRED'
 for name,h in c['inhibitors'].items():
  s=state(name);assert s['MainPID']=='0' and s['ActiveState'] in ('inactive','failed'),'COMPETING_OWNER'
  assert sha(Path('/etc/systemd/system',name+'.d/90-kity-micro-inhibit.conf').read_bytes())==h,'INHIBITOR_DRIFT'
 assert Path(c['inhibit_marker']).is_file(),'INHIBIT_MARKER'

def off_not_sent(b):
 root=Path(b['scope']['root']);assert not os.path.lexists(root/'owner-go.json'),'OLD_ROOT_HAS_GO'
 for name in ('tickets','send-barriers'):assert not any((root/name).rglob('*')),'OLD_WIRE_HISTORY'
 # OFF-only simulation journals are retained; they are never adopted into LIVE.

def fresh_flat(folder,p,b):
 sys.path.insert(0,p['financial_app'])
 from types import SimpleNamespace
 from research_lab.kity_micro_physical_owner_v1 import load_bound_credentials
 from research_lab.pump4_runtime_sources_v1 import TrustedSources
 from research_lab.pump4_bybit_sources_v1 import flat_account
 original=b['original'];c=b['config'];assert all(original[k]==c[k] for k in ('account_fingerprint','credential_source','credential_source_sha256')),'ORIGINAL_ACCOUNT_DRIFT'
 key,secret=load_bound_credentials(original);out=folder/'activation-get-captures';out.mkdir(mode=0o700,exist_ok=True)
 src=TrustedSources({},SimpleNamespace(key=key,secret=secret,root=out,scope=dict(account_fingerprint=c['account_fingerprint']),clock=lambda:time.time_ns()//1000000))
 bundle,_=src.flat();now=time.time_ns()//1000000;v=flat_account(bundle,expected_fingerprint=c['account_fingerprint'],now_ms=now)
 from decimal import Decimal as D
 assert D(v['available_balance'])>=D('50'),'ALLOCATION_AND_RESERVE_CASH_REQUIRED'
 return dict(observed_ms=now,source_ms=v['source_ms'],positions_flat=True,open_orders_empty=True,borrowed_funds=False,capture_sha256=digest(bundle))

def readback(folder,p):
 c=json.loads((folder/'runner.json').read_bytes());s=json.loads((folder/'scope.json').read_bytes());u=UNIT.read_text();pin=sha(encode(c))
 assert c['mode']==s['mode']=='OWNER_TINY_LIVE' and c['authority']['sha256']==sha(encode(s)) and s['runner_config_sha256']==digest({k:v for k,v in c.items() if k!='authority'}),'LIVE_BINDING'
 assert u==(folder/'new-owner.service').read_text() and '--dispatch' in u and '--config-sha256 '+pin in u,'LIVE_UNIT'
 st=state(UNIT.name);assert st['ActiveState']=='active' and held(s['account_lock_path'],st['MainPID']),'LIVE_LEASE'
 sp=importlib.util.spec_from_file_location('pinned_live_health',folder/'health.py');h=importlib.util.module_from_spec(sp);sp.loader.exec_module(h);health=h.observe()
 return dict(schema='PUMP4_TINY_ACTIVATION_READBACK_V1',status='LIVE_ARMED_HEALTHY' if health['status']=='HEALTHY' else 'LIVE_ARMED_OWNER_ACTION_REQUIRED',observed_ms=time.time_ns()//1000000,scope_sha256=digest(s),config_sha256=pin,original_lock_inode=Path(s['account_lock_path']).stat().st_ino,owner_state=st,health=health,actual_entry_executed=health.get('financial_trading_proven') if health['status']=='HEALTHY' else 'UNKNOWN',broker_writes=None,one_lifecycle_only=True)

def activate(folder,p,b):
 assert not (folder/'activation-claim.json').exists() and not os.path.lexists(p['live_root']),'ACTIVATION_ALREADY_ATTEMPTED_DO_NOT_REPEAT'
 assert UNIT.read_text()==b['units'][UNIT.name] and Path(p['wrapper_path']).read_text()==b['wrapper']['text'],'BEFORE_UNIT_OR_WRAPPER_DRIFT'
 static_guards(p,b)
 for path,h in b['config']['guard_source_files'].items():assert sha(Path(path).read_bytes())==h,'BEFORE_GUARD_DRIFT'
 assert sha(Path(b['old_config_path']).read_bytes())==sha(encode(b['config'])),'BEFORE_CONFIG_DRIFT'
 st=state(UNIT.name);assert st['ActiveState']=='active' and held(b['scope']['account_lock_path'],st['MainPID']) and all(not st.get(k) for k in ('DropInPaths','ExecStop','ExecStopPost','Job')),'BEFORE_OWNER_CUSTODY'
 off_not_sent(b);first=fresh_flat(folder,p,b)
 raw=Path(p['health_spec']['path']).read_bytes();assert sha(raw)==p['health_spec']['sha256'],'HEALTH_SPEC_PIN';spec=json.loads(raw)
 fd=os.open(spec['observer_lock'],os.O_RDONLY|os.O_NOFOLLOW);lease=None
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  once(folder/'activation-claim.json',encode(dict(started_ms=time.time_ns()//1000000,first_flat=first,packet_policy=p['policy'],no_retry=True)))
  ctl('stop',UNIT.name);base.quiet(UNIT.name);off_not_sent(b)
  lease=os.open(b['scope']['account_lock_path'],os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
  second=fresh_flat(folder,p,b);static_guards(p,b)
  arm=time.time_ns()//1000000;g=build_generated(b,p,arm)
  base.prepare_runtime(Path(p['live_root']))
  for name,value in [('scope.json',g['scope']),('runner.json',g['config'])]:once(folder/name,encode(value))
  once(folder/'new-owner.service',g['unit'].encode())
  replace(Path(p['wrapper_path']),sha(b['wrapper']['text'].encode()),p['wrapper_new'].encode())
  replace(UNIT,sha(b['units'][UNIT.name].encode()),g['unit'].encode())
  subprocess.run(['systemd-analyze','verify',str(UNIT)],check=True,capture_output=True,timeout=20);ctl('daemon-reload')
  secure_once(Path(p['live_root'])/'owner-go.json',encode(g['go']))
  os.close(lease);lease=None;ctl('start',UNIT.name) # exactly one start; never retry this financial transition
  started=time.monotonic();proof=None
  while time.monotonic()-started<90:
   st=state(UNIT.name)
   for path in (Path(p['live_root'])/'supervisor/receipts').glob('*.json'):
    r=json.loads(path.read_bytes())
    if r['pid']==int(st['MainPID']) and r['scope_sha256']==digest(g['scope']) and r['runner_config_sha256']==sha(encode(g['config'])) and r['mode']=='OWNER_TINY_LIVE':proof=r;break
   if proof or st['ActiveState']=='failed':break
   time.sleep(.2)
  assert proof,'LIVE_START_UNPROVEN_DO_NOT_REPEAT'
  result=readback(folder,p);result.update(first_flat=first,second_flat=second,financial_command_repeated=False,packet_policy=p['policy'])
  once(folder/'activation-receipt.json',encode(result));return result
 finally:
  if lease is not None:os.close(lease)
  os.close(fd)

def rollback(folder,p,b):
 root=Path(p['live_root']);sf=folder/'scope.json';newfile=folder/'new-owner.service';oldunit=b['units'][UNIT.name].encode();newunit=newfile.read_bytes() if newfile.exists() else oldunit
 assert UNIT.read_bytes() in (oldunit,newunit),'UNKNOWN_ROLLBACK_UNIT'
 wrapper=Path(p['wrapper_path']);assert wrapper.read_text() in (b['wrapper']['text'],p['wrapper_new']),'UNKNOWN_ROLLBACK_WRAPPER'
 scope=json.loads(sf.read_bytes()) if sf.exists() else None
 if scope:
  assert scope['root']==str(root) and scope['mode']=='OWNER_TINY_LIVE' and scope['policy']==p['policy'],'ROLLBACK_SCOPE'
 sid=digest(scope) if scope else 'UNINITIALIZED_NO_GO'
 if (root/'owner-go.json').exists():
  assert scope and json.loads((root/'owner-go.json').read_bytes())==dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=sid,owner_go_text='GO PUMP4_TINY '+sid),'ROLLBACK_GO_SCOPE'
 if not revoke_and_is_empty(root,sid):return dict(status='ENTRY_REVOKED_CUSTODY_LEFT_UNCHANGED',broker_writes=None,owner_state=state(UNIT.name),owner_action_required=True)
 raw=Path(p['health_spec']['path']).read_bytes();assert sha(raw)==p['health_spec']['sha256'],'HEALTH_SPEC_PIN'
 fd=os.open(json.loads(raw)['observer_lock'],os.O_RDONLY|os.O_NOFOLLOW)
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  once(folder/'rollback-claim.json',encode(dict(observed_ms=time.time_ns()//1000000,scope_sha256=sid)))
  ctl('stop',UNIT.name);base.quiet(UNIT.name)
  if not revoke_and_is_empty(root,sid):
   assert UNIT.read_bytes()==newunit and scope and (root/'owner-go.json').exists(),'RACED_CUSTODY_UNKNOWN'
   ctl('start',UNIT.name) # same LIVE owner, entry revoked; restore custody, never a new GO
   return dict(status='ENTRY_REVOKED_RACED_ACTION_CUSTODY_RESTORED',broker_writes=None,owner_action_required=True)
  try:flat=fresh_flat(folder,p,b)
  except Exception:
   ctl('start',UNIT.name) # keep current manager; revoke marker forbids a new entry
   raise
  base.restore_owner_files(UNIT,wrapper,oldunit,newunit,b['wrapper']['text'].encode(),p['wrapper_new'].encode())
  ctl('daemon-reload');ctl('start',UNIT.name)
  result=dict(status='ROLLED_BACK_TO_ORIGINAL_OFF_AUTHORITY_REVOKED',observed_ms=time.time_ns()//1000000,flat=flat,go_and_histories_preserved=True,broker_writes=0)
  once(folder/'rollback-receipt.json',encode(result));return result
 finally:os.close(fd)

def main():
 os.umask(0o077)
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--packet',type=Path);parser.add_argument('--packet-sha256');modes=parser.add_mutually_exclusive_group();modes.add_argument('--activate-once',action='store_true');modes.add_argument('--readback',action='store_true');modes.add_argument('--revoke-and-rollback',action='store_true');parser.add_argument('--owner-go-text');args=parser.parse_args()
 if not any((args.activate_once,args.readback,args.revoke_and_rollback)):
  print(json.dumps(dict(status='NO_REQUESTS_NO_GO',broker_writes=0)));return 0
 assert args.packet is not None and args.packet_sha256,'EXACT_PACKET_REQUIRED'
 folder=safe(args.packet).parent;p,b=load_packet(folder,args.packet_sha256)
 if args.activate_once:
  assert args.owner_go_text=='GO PUMP4_TINY_PACKET '+args.packet_sha256,'EXACT_REVIEWED_PACKET_OWNER_GO_REQUIRED';value=activate(folder,p,b)
 elif args.revoke_and_rollback:
  assert args.owner_go_text=='REVOKE PUMP4_TINY_PACKET '+args.packet_sha256,'EXACT_ROLLBACK_OWNER_REQUEST_REQUIRED';value=rollback(folder,p,b)
 else:value=readback(folder,p)
 print(json.dumps(value));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except (AssertionError,OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:
  print(json.dumps(dict(status='BLOCKED_OR_UNKNOWN_DO_NOT_REPEAT',reason=str(exc),broker_writes=None)));raise SystemExit(2)
