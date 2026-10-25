"""Source-bound OWNER-ONLY correction. Default verify never activates/creates GO."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
from contextlib import redirect_stdout
import io,importlib.util,sqlite3
C=Path('/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-0a0e7c6e6a4b0d53-t24685496')
R=C/'owner-review-clock-v5';PACKET_SHA='115d96413827549b318c3dff057f3bcf3dc4a61d20fc5a1d60b6e15bf627f7af'
OLD=Path('/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-dcaafa089ff8f81f-t32a6a356')

def need(v,e):
 if not v:raise ValueError('CLOCK_CORRECTION_'+e)

def raw(path,pin):
 p=Path(path);need(p.is_absolute() and not any(x.is_symlink() for x in (p,*p.parents)),'PATH')
 st=p.stat();need(p.is_file() and st.st_nlink==1 and st.st_uid==os.geteuid(),'CUSTODY');b=p.read_bytes();need(hashlib.sha256(b).hexdigest()==pin,'PIN');return b

def compare(old,new,oldscope,scope):
 need({k:v for k,v in old.items() if k not in ('files','authority')}=={k:v for k,v in new.items() if k not in ('files','authority')},'CONFIG_CHANGE')
 need(set(old['files'])==set(new['files']) and {n for n in old['files'] if old['files'][n]!=new['files'][n]}=={'research_lab/alpaca_monthly_cycle_v1.py'},'SOURCE_DIFF')
 excluded={'source_files','revocation_path'}
 need({k:v for k,v in oldscope.items() if k not in excluded}=={k:v for k,v in scope.items() if k not in excluded},'FINANCIAL_SCOPE_CHANGE')
 need(scope['revocation_path']==str(Path(old['manager']['root'])/'OWNER_ENTRY_REVOKED_clock_v5.json'),'REVOKE_PATH')
 need({Path(v['path']).relative_to(C/'app').as_posix():v['sha256'] for v in scope['source_files']}==new['files'],'SOURCE_SCOPE')

def ctl(*args):return subprocess.check_output(['/usr/bin/systemctl',*args],text=True,timeout=20)
def state():return dict(r.split('=',1) for r in ctl('show','alpaca-monthly-owned.service','--property=MainPID,ControlPID,ActiveState,Job,DropInPaths').splitlines() if '=' in r)

def run(mode,owner_text=None):
 need(mode in ('verify','activate'),'MODE')
 if mode=='activate':need(owner_text=='GO MONTHLY CLOCK_CORRECTION '+PACKET_SHA,'PERSONAL_OWNER_TEXT_REQUIRED')
 p=json.loads(raw(R/'packet.json',PACKET_SHA));spec=json.loads(raw(p['spec']['path'],p['spec']['sha256']));scope=json.loads(raw(p['scope']['path'],p['scope']['sha256']));old=json.loads(raw(p['old_spec']['path'],p['old_spec']['sha256']));oldscope=json.loads(raw(old['authority']['scope_path'],p['old_scope_sha256']));compare(old,spec,oldscope,scope)
 sys.path.insert(0,str(C/'app'))
 from scripts.run_alpaca_monthly_cycle_v1 import verify,runner_config_sha256
 from research_lab.alpaca_dynamic_live_runtime_v1 import account_lock
 from research_lab.kity_oct15_deadline_v1 import publish_once
 verify(p['spec']['path'],p['spec']['sha256'],dispatch=True)
 need(scope['runner_config_sha256']==runner_config_sha256(spec),'RUNNER_CONFIG')
 accept=json.loads((C/'acceptance.json').read_bytes());need(accept['status']=='PASS' and accept['counts']==dict(tests=260,errors=0,failures=0,skipped=0),'ACCEPTANCE')
 oldgo_path=Path(old['authority']['owner_go_path']);need(not any(x.is_symlink() for x in (oldgo_path,*oldgo_path.parents)) and oldgo_path.stat().st_nlink==1 and oldgo_path.stat().st_uid==os.geteuid() and oldgo_path.stat().st_mode&0o777==0o600,'ORIGINAL_GO_CUSTODY');oldgo=json.loads(oldgo_path.read_bytes());need(oldgo==dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',scope_sha256=p['old_scope_sha256'],owner_go_text='GO ALPACA_MONTHLY_STANDING '+p['old_scope_sha256']),'ORIGINAL_PERSONAL_GO')
 need(time.time_ns()//1000000<scope['valid_from_ms'],'PRE_ENTRY_CORRECTION_ONLY')
 unit=raw(p['unit_path'],p['new_unit_sha256']);target=Path('/etc/systemd/system/alpaca-monthly-owned.service');raw(target,p['old_unit_sha256']);raw('/etc/systemd/system/alpaca-monthly-owned.timer',p['timer_sha256'])
 need(not state()['DropInPaths'],'UNIT_OVERRIDE')
 lock=Path(spec['manager']['account_lock_path']);need([lock.stat().st_dev,lock.stat().st_ino]==scope['original_lock_identity'],'ORIGINAL_LOCK')
 root=Path(spec['manager']['root']);claim=R/'personal-correction-claim.json';go=Path(spec['authority']['owner_go_path'])
 need(not os.path.lexists(claim) and not os.path.lexists(go),'ALREADY_ATTEMPTED_RECONCILE_ONLY')
 for f in (Path(oldscope['revocation_path']),Path(scope['revocation_path']),root/'ENTRY_HALT.json',root/'native/standing-loss-stop.json',root/'native/standing-loss-observation.json'):need(not os.path.lexists(f),'EXISTING_ENTRY_BLOCK')
 capture=OLD/'owner-operations-v4/capture-alpaca.py';captured=io.StringIO();b=raw(capture,'922006306e84b1585a27f3e2e2811f0ced380d30ff037e14f41d44b1d5a9f009')
 with redirect_stdout(captured):exec(compile(b,str(capture),'exec'),{'__name__':'__main__'})
 d=json.loads(captured.getvalue());ops=OLD/'owner-operations-v4/monthly-operations.py';raw(ops,'8bd564a2b9fcd3ed64576712e153279207ebac31907b331a9223de951d304b53');s=importlib.util.spec_from_file_location('ops',ops);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.flat_capture(d,spec['manager']['account_id'])
 need(all(0<=time.time_ns()//1000000-v['started_ms']<=5000 for v in d['captures'] if v['route'] in ('/v2/account','/v2/positions','/v2/orders')),'BROKER_SNAPSHOT_STALE')
 result=dict(schema='MONTHLY_CLOCK_CORRECTION_RECEIPT_V1',status='READY_FOR_PERSONAL_CLOCK_CORRECTION',observed_ms=time.time_ns()//1000000,new_scope_sha256=p['scope']['sha256'],new_spec_sha256=p['spec']['sha256'],financial_parameters_changed=False,broker_writes=0,actual_entry_executed=False,owner_go_created=False)
 if mode=='verify':return result
 # Write-ahead personal attempt prevents automatic repeat after any ambiguity.
 publish_once(claim,(json.dumps(dict(packet_sha256=PACKET_SHA,observed_ms=result['observed_ms']))+'\n').encode())
 ctl('disable','--now','alpaca-monthly-owned.timer')
 deadline=time.monotonic()+240
 while state()['MainPID']!='0' or state()['Job']:
  need(time.monotonic()<deadline,'SERVICE_DID_NOT_FINISH_NO_KILL');time.sleep(.25)
 with account_lock(dict(lock_path=str(lock))):
  need(state()['MainPID']=='0' and not state()['Job'] and not state()['DropInPaths'],'NOT_IDLE')
  # Re-read broker truth after waiting for the old process; no stale reuse.
  fresh=io.StringIO()
  with redirect_stdout(fresh):exec(compile(b,str(capture),'exec'),{'__name__':'__main__'})
  d2=json.loads(fresh.getvalue());m.flat_capture(d2,spec['manager']['account_id'])
  need(all(0<=time.time_ns()//1000000-v['started_ms']<=5000 for v in d2['captures'] if v['route'] in ('/v2/account','/v2/positions','/v2/orders')),'FINAL_BROKER_SNAPSHOT_STALE')
  result['broker_get_requests']=d['broker_get_requests']+d2['broker_get_requests']
  need(time.time_ns()//1000000<scope['valid_from_ms'],'ENTRY_WINDOW_RECHECK')
  with sqlite3.connect((root/'book/monthly-orders-off.sqlite').as_uri()+'?mode=ro',uri=True) as db:
   need(all(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]==0 for t in ('positions','exits','dispatches')),'BOOK_NOT_EMPTY')
  raw(target,p['old_unit_sha256']);verify(p['spec']['path'],p['spec']['sha256'],dispatch=True)
  publish_once(Path(oldscope['revocation_path']),(json.dumps(dict(reason='PERSONAL_SOURCE_CLOCK_CORRECTION',replacement_scope_sha256=p['scope']['sha256']))+'\n').encode())
  newgo=dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',scope_sha256=p['scope']['sha256'],owner_go_text='GO ALPACA_MONTHLY_STANDING '+p['scope']['sha256']);publish_once(go,(json.dumps(newgo,sort_keys=True)+'\n').encode())
  from scripts.run_alpaca_monthly_cycle_v1 import runner_authority
  runner_authority(spec)
  temp=target.with_name(target.name+'.clock-v5');publish_once(temp,unit);temp.chmod(0o644);os.replace(temp,target)
  fd=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
  ctl('daemon-reload');ctl('enable','--now','alpaca-monthly-owned.timer')
 result.update(status='OWNER_ARMED_CORRECTED_FUTURE_MONTHLY',owner_go_created=True,old_scope_entries_revoked=True,server_cycle_acceptance='PENDING_INDEPENDENT_READBACK')
 publish_once(R/'personal-correction-result.json',(json.dumps(result,sort_keys=True)+'\n').encode());return result

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=('verify','activate'),default='verify',nargs='?');a.add_argument('--owner-text');v=a.parse_args();print(json.dumps(run(v.mode,v.owner_text)))
