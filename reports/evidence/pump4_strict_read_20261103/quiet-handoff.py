"""One DATA-only quiet-boundary handoff. Never changes the financial owner."""
import argparse,hashlib,json,os,subprocess,time,fcntl
from pathlib import Path
OLD_UNIT_SHA='0e227ab316240795ba73bc3ec81d513b12b579327d691ecaac84ad5b8efff8c1'
NEW_UNIT_SHA='9c7ff89367ba1a69c419fc5ffc8260f078e998a2886bbc6373148bc06f7bbcbe'
TIMER='pump4-data-supervisor.timer'
TIMER_SHA='d31f4ba785c56b0dda7b15f2060578effd9d10a2fab89df8f1457b2411fbca98'
UNIT='pump4-data-supervisor.service';ROOT=Path('/opt/bybot-research/pump4-server-orders-off-20261023/candidate-7d8ae05dab162ec5/app/.private/pump4-supervisor-v1');H=3600000
def need(v,e):
 if not v:raise ValueError(e)
def sha(b):return hashlib.sha256(b).hexdigest()
def now():return time.time_ns()//1000000
def get(u):return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',u,'-p','MainPID','-p','ActiveState','-p','SubState','-p','NRestarts','-p','ExecMainCode','-p','ExecMainStatus','-p','Result','-p','Job','-p','DropInPaths'],text=True).splitlines() if '=' in x)
def control(*args):
 need(args==('daemon-reload',) or len(args)==2 and args[1] in {UNIT,TIMER} and args[0] in {'stop','start'},'DATA_UNIT_ONLY')
 subprocess.run(['systemctl',*args],check=True,timeout=110)
def once(p,x):
 b=(json.dumps(x,sort_keys=True,indent=2)+'\n').encode()
 with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def replace_unit(target,b):
 tmp=target.with_name('.'+target.name+'.warmpatch');need(not tmp.exists(),'TEMP_EXISTS')
 with tmp.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 tmp.chmod(0o644);os.replace(tmp,target)
 fd=os.open(target.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def continuity():
 units=['pump4-execution-owner.service','alpaca-monthly-owned.service','alpaca-monthly-owned.timer']
 return {'units':{u:sha((Path('/etc/systemd/system')/u).read_bytes()) for u in units},'pump_owner':get(units[0]),'account_lock_inode':Path('/opt/bybot-research/kity-micro-owner-20261015/runtime/account.lock').stat().st_ino}
def summary(hour):
 p=ROOT/'ws-hours'/str(hour)/'receipt.json';b=p.read_bytes();v=json.loads(b);rows=[r for r in v['rows'] if r.get('status')=='CLOSED_H1_INTAKE_PASS']
 return dict(hour_open_ms=hour,receipt_sha256=sha(b),complete=v['complete_pairs'],expected=v['expected_trading'],within60=v['within60s'],hour_pass=v['hour_pass'],disconnected=v['disconnected'],last_publication_offset_ms=max((r['publication_completed_ms']-hour for r in rows),default=None),raw_signals=sum(bool(r['decisions'][0]['decision']['signal']) for r in rows))
def clean_stopped(state):
 return state['MainPID']=='0' and state['ActiveState']=='inactive' and state['SubState']=='dead' and state.get('Result')=='success' and not state.get('Job') and state['ExecMainStatus']=='0'
def has_attempt(hour):
 return (ROOT/'ws-hours'/str(hour)).exists() or (ROOT/'ws-setup'/str(hour)).exists()
def cleanup_failure(unit,old,new,oldstate,next_hour,stop_requested):
 # Reconcile actual bytes/PID after uncertain systemctl return, never rely on
 # an assignment following a command that may have applied before failing.
 if not stop_requested:return 'NO_DATA_MUTATION_REQUESTED'
 actual=unit.read_bytes();state=get(UNIT)
 need(actual in (old,new),'CLEANUP_FOREIGN_UNIT_NO_CHANGE')
 if actual==old and state['MainPID']==oldstate['MainPID']:
  return 'ORIGINAL_DATA_STILL_RUNNING'
 if state['MainPID']!='0':
  # Only the candidate selected by this handoff may be stopped here.
  need(actual==new,'CLEANUP_FOREIGN_DATA_PID_NO_CHANGE')
  control('stop',UNIT);need(get(UNIT)['MainPID']=='0','CANDIDATE_STOP_UNCONFIRMED')
 if has_attempt(next_hour):
  return 'DATA_STOPPED_SPENT_NEXT_ATTEMPT_PRESERVED_NO_RESTART'
 if unit.read_bytes()==new:replace_unit(unit,old)
 need(unit.read_bytes()==old,'ROLLBACK_UNIT_CAS')
 control('daemon-reload');control('start',UNIT)
 return 'ORIGINAL_DATA_RESTARTED_BEFORE_NEXT_ATTEMPT'
def reconcile_failure(unit,old,new,oldstate,next_hour,stop_requested,timer_stop_requested):
 # Timer may already have been restarted before a later fsync/check failed.
 # Quiesce it first, otherwise it can resurrect a spent next-hour attempt.
 if timer_stop_requested:
  control('stop',TIMER);need(get(TIMER)['ActiveState']=='inactive','CLEANUP_TIMER_NOT_STOPPED')
 result=cleanup_failure(unit,old,new,oldstate,next_hour,stop_requested)
 if timer_stop_requested and get(UNIT)['MainPID']!='0':control('start',TIMER)
 return result

def verify_unit_bytes(old,new):
 need(sha(old)==OLD_UNIT_SHA and sha(new)==NEW_UNIT_SHA,'DATA_UNIT_PIN')
def preload_deadline(target,monotonic_now,wall_now):
 # Measured cold preload was147s. Existing DATA unit permits900s. Reserve the
 # entire next WS subscription interval; never convert timeout into hour replay.
 seconds=min(900,(target+H-120000-wall_now)/1000)
 need(seconds>=180,'INSUFFICIENT_PRELOAD_HEADROOM')
 return monotonic_now+seconds

def run(folder,pin,target):
 p=Path(folder);raw=(p/'patch-manifest.json').read_bytes();need(sha(raw)==pin,'PATCH_MANIFEST_PIN');v=json.loads(raw)
 for n,h in v['files'].items():need(sha((p/n).read_bytes())==h,'PATCH_FILE_PIN')
 old=(p/'old-data-exact.service').read_bytes();new=(p/'new-data-final.service').read_bytes();verify_unit_bytes(old,new);unit=Path('/etc/systemd/system')/UNIT
 need(unit.read_bytes()==old,'OLD_DATA_UNIT_DRIFT');timer_file=Path('/etc/systemd/system')/TIMER;need(sha(timer_file.read_bytes())==TIMER_SHA,'DATA_TIMER_DRIFT');need(get(TIMER)['ActiveState']=='active' and not get(TIMER).get('DropInPaths'),'DATA_TIMER_NOT_ACTIVE');oldstate=get(UNIT);need(oldstate['ActiveState']=='active' and oldstate['MainPID']=='4126455' and not oldstate.get('DropInPaths'),'DATA_PID_CHANGED')
 need(now()<target+80000 and target%H==0,'MISSED_TARGET_NO_REPLAY');need(not (p/'strict-v1-handoff-claim.json').exists(),'ALREADY_ATTEMPTED_READBACK_ONLY')
 once(p/'strict-v1-handoff-claim.json',dict(observed_ms=now(),target_hour_ms=target,patch_manifest_sha256=pin,financial_changes=False))
 stop_requested=False;timer_stop_requested=False
 try:
  while now()<target+65000:time.sleep(min(1,max(.01,(target+65000-now())/1000)))
  while now()<=target+80000:
   need(get(UNIT)['MainPID']==oldstate['MainPID'],'OLD_DATA_PID_CHANGED')
   folder=ROOT/'ws-hours'/str(target);pub=list((folder/'published').glob('*.json'));prefixes=list((folder/'prefixes').glob('*.json'))
   if len(pub)==len(prefixes)==134 and {f.name for f in pub}=={f.name for f in prefixes}:break
   time.sleep(.2)
  else:raise ValueError('NO_SAFE_COMPLETE_PAIR_BOUNDARY_NO_STOP')
  need(not has_attempt(target+H),'NEXT_ATTEMPT_ALREADY_EXISTS_NO_REPLAY')
  before=continuity();need(before['units']['pump4-execution-owner.service']=='991211ed5db0c9dd163193141179eefe9a266298d9bdde1491dc0904793fb843' and before['units']['alpaca-monthly-owned.service']=='f167c6ccf922902d5bee874ca4946bfb6d5c8bf227df31f2144f595e2ad0a81c' and before['pump_owner']['MainPID']=='3669955' and before['pump_owner']['NRestarts']=='0' and before['account_lock_inode']==818853,'APPROVED_FINANCIAL_CONTEXT_DRIFT');preload_deadline(target,time.monotonic(),now());timer_stop_requested=True;control('stop',TIMER);need(get(TIMER)['ActiveState']=='inactive','DATA_TIMER_NOT_STOPPED')
  stop_requested=True;control('stop',UNIT);s=get(UNIT);need(clean_stopped(s),'DATA_DID_NOT_STOP_CLEANLY')
  before_hour=summary(target);need(before_hour['complete']==before_hour['expected']==134 and not before_hour['disconnected'],'OLD_COMPLETE_RECEIPT_NOT_PRESERVED')
  epochs={f.name:sha(f.read_bytes()) for f in (ROOT/'epochs').glob('*.json')};journals={f.name:sha(f.read_bytes()) for f in (ROOT/'intake').glob('*.jsonl')};binding=sha((ROOT/'data-binding.json').read_bytes());inode=(ROOT/'data-writer.lock').stat().st_ino
  need(unit.read_bytes()==old,'UNIT_CAS');replace_unit(unit,new);control('daemon-reload');control('start',UNIT)
  deadline=preload_deadline(target,time.monotonic(),now())
  while time.monotonic()<deadline:
   state=get(UNIT)
   if state['ActiveState']=='failed':raise ValueError('NEW_DATA_FAILED')
   next_folder=ROOT/'ws-hours'/str(target+H)
   if state['MainPID']!='0' and len(list((next_folder/'prefixes').glob('*.json')))==134 and (ROOT/'ws-setup'/str(target+H)/'preloaded.json').is_file():break
   time.sleep(1)
  else:raise ValueError('NEW_DATA_PRELOAD_NOT_READY')
  need(epochs=={f.name:sha(f.read_bytes()) for f in (ROOT/'epochs').glob('*.json')},'EPOCH_CHANGED')
  need(journals=={f.name:sha(f.read_bytes()) for f in (ROOT/'intake').glob('*.jsonl')},'JOURNAL_CHANGED_DURING_REWARM')
  need(binding==sha((ROOT/'data-binding.json').read_bytes()) and inode==(ROOT/'data-writer.lock').stat().st_ino,'DATA_BINDING_OR_LOCK_CHANGED')
  need(unit.read_bytes()==new,'NEW_DATA_UNIT_CHANGED');after=continuity();need(before==after,'FINANCIAL_CONTINUITY_CHANGED')
  need(sha(timer_file.read_bytes())==TIMER_SHA,'DATA_TIMER_BYTES_CHANGED');control('start',TIMER);need(get(TIMER)['ActiveState']=='active','DATA_TIMER_NOT_RESTORED')
  receipt=dict(schema='PUMP4_STRICT_READ_PHYSICAL_HANDOFF_V1',observed_ms=now(),patch_manifest_sha256=pin,before_hour=before_hour,old_data_pid=int(oldstate['MainPID']),new_data_pid=int(state['MainPID']),data_lock_inode=inode,epochs_preserved=len(epochs),journals_preserved=len(journals),financial_continuity=after,financial_changes=False,broker_requests=0,broker_writes=0,actual_new_h1='PENDING',next_hour_ms=target+H)
  once(p/'strict-v1-handoff-result.json',receipt)
 except BaseException as error:
  # Preserve all spent attempts and source bytes. Never replay an old hour.
  # Restore old DATA code only if the replacement failed before its next attempt.
  cleanup=None
  try:
   if timer_stop_requested:need(sha(timer_file.read_bytes())==TIMER_SHA,'CLEANUP_TIMER_DRIFT')
   cleanup=reconcile_failure(unit,old,new,oldstate,target+H,stop_requested,timer_stop_requested)
  except BaseException as e:cleanup=type(e).__name__+':'+str(e)
  once(p/'strict-v1-handoff-failed.json',dict(observed_ms=now(),reason=str(error),error_type=type(error).__name__,cleanup_error=cleanup,financial_changes=False,automatic_retry=False));raise
 # Actual prospective hour, no fixture replay and no timestamp substitution.
 while now()<target+H+125000:time.sleep(1)
 try:
  actual=summary(target+H);actual_state=get(UNIT);actual_continuity=continuity()
  need(unit.read_bytes()==new and actual_state['MainPID']==state['MainPID'] and actual_state['ActiveState']=='active','ACTUAL_H1_PATCH_IDENTITY_CHANGED')
  need(actual_continuity==before,'ACTUAL_H1_FINANCIAL_CONTINUITY_CHANGED')
  need(actual['complete']==actual['expected']==134 and not actual['disconnected'],'ACTUAL_H1_INCOMPLETE')
  once(p/'strict-v1-actual-h1-after.json',dict(observed_ms=now(),patch_manifest_sha256=pin,actual_hour=actual,financial_continuity=actual_continuity,actual_data_pid=int(actual_state['MainPID']),actual_data_unit_sha256=sha(unit.read_bytes()),actual_new_h1='PASS' if actual['hour_pass'] else 'SOURCE_BLOCKED'))
  print(json.dumps(dict(status='ACTUAL_NEW_H1_PASS' if actual['hour_pass'] else 'ACTUAL_NEW_H1_BLOCKED',actual=actual,broker_writes=0)),flush=True)
 except BaseException as e:
  once(p/'strict-v1-actual-h1-unconfirmed.json',dict(observed_ms=now(),reason=str(e),status='ACTUAL_NEW_H1_UNKNOWN',financial_changes=False,automatic_retry=False));raise
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--folder',required=True);a.add_argument('--manifest-sha256',required=True);a.add_argument('--target-hour-ms',type=int,required=True);v=a.parse_args();run(v.folder,v.manifest_sha256,v.target_hour_ms)
