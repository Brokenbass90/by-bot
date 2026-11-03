"""Owner-authorized source-only repair. Never invokes enter/dispatch or an order."""
import argparse,ast,hashlib,importlib.util,io,json,os,sqlite3,subprocess,sys,time
from contextlib import redirect_stdout
from pathlib import Path
P=Path(__file__).resolve().parent
PIN='4cf04904195eb0f4db6fb369524dced38d6f18e5f70481050db943b876ab2ab4'
def need(ok,why):
 if not ok:raise ValueError(why)
def raw(path,pin=None):
 p=Path(path);need(p.is_absolute() and not any(x.is_symlink() for x in (p,*p.parents)) and p.is_file() and p.stat().st_nlink==1 and p.stat().st_uid==0,'FILE_CUSTODY');b=p.read_bytes()
 if pin:need(hashlib.sha256(b).hexdigest()==pin,'PIN_DRIFT')
 return b
def put(path,b,mode=0o600):
 p=Path(path);need(p.parent.is_dir() and not any(x.is_symlink() for x in (p,*p.parents)),'WRITE_PATH');fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 d=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(d)
 finally:os.close(d)
def enc(x):return (json.dumps(x,sort_keys=True)+'\n').encode()
def ctl(*a):return subprocess.check_output(['systemctl',*a],text=True,timeout=20)
def state():return dict(x.split('=',1) for x in ctl('show','alpaca-monthly-owned.service','-p','MainPID','-p','Job','-p','DropInPaths').splitlines() if '=' in x)
def select_unit(target,old,new,revocation,retire):
 need(target.read_bytes()==old,'UNIT_CAS_BEFORE')
 tmp=target.with_name('.'+target.name+'.opening-v7-stage')
 try:
  put(tmp,new,0o644);os.replace(tmp,target)
  d=os.open(target.parent,os.O_RDONLY)
  try:os.fsync(d)
  finally:os.close(d)
  ctl('daemon-reload');need(target.read_bytes()==new,'UNIT_CAS_AFTER')
  need('NeedDaemonReload=no' in ctl('show','alpaca-monthly-owned.service','-p','NeedDaemonReload'),'RELOAD_NOT_EFFECTIVE')
  retire() # only AFTER new unit is selected/reloaded under the original lock
 except BaseException:
  # An uncertain retirement publication may already have revoked the old scope.
  # In that case keep the verified new source selected; never clear the marker.
  if not os.path.lexists(revocation) and target.read_bytes()==new:
   restore=target.with_name('.'+target.name+'.opening-v7-rollback');put(restore,old,0o644);os.replace(restore,target);ctl('daemon-reload')
  if tmp.exists():tmp.unlink()
  raise

def run(mode):
 packet=json.loads(raw(P/'packet.json',PIN));C=Path(packet['candidate']);spec=json.loads(raw(packet['spec']['path'],packet['spec']['sha256']));scope=json.loads(raw(packet['scope']['path'],packet['scope']['sha256']));old=json.loads(raw(packet['old_spec']['path'],packet['old_spec']['sha256']));oldscope=json.loads(raw(old['authority']['scope_path'],packet['old_scope_sha256']))
 compare_spec=importlib.util.spec_from_file_location('pure_compare',P/'compare.py');compare=importlib.util.module_from_spec(compare_spec);compare_spec.loader.exec_module(compare);compare.compare(old,spec,oldscope,scope,C/'app')
 manifest=json.loads(raw(C/'source-manifest.json'));need(manifest['source_material_sha256']==packet['source_material_sha256'],'SOURCE_MATERIAL')
 for n,h in manifest['files'].items():raw(C/'app'/n,h)
 accept=json.loads(raw(C/'acceptance.json'));need(accept['status']=='PASS' and accept['counts']==dict(tests=281,failures=0,errors=0,skipped=0) and not accept['checkout_fallback'],'EXACT_ACCEPTANCE')
 sys.path[:0]=[str(C/'app')]
 from scripts.run_alpaca_monthly_cycle_v1 import verify,runner_config_sha256
 from research_lab.alpaca_monthly_binding_v1 import strategy_identity
 from research_lab.alpaca_dynamic_live_runtime_v1 import account_lock
 from research_lab.kity_oct15_deadline_v1 import publish_once
 verify(packet['spec']['path'],packet['spec']['sha256'],dispatch=True);need(scope['strategy_identity']==strategy_identity() and runner_config_sha256(spec)==scope['runner_config_sha256'],'PROPOSED_AUTHORITY_IDENTITY')
 oldgo=json.loads(raw(old['authority']['owner_go_path']));need(oldgo==dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',scope_sha256=packet['old_scope_sha256'],owner_go_text='GO ALPACA_MONTHLY_STANDING '+packet['old_scope_sha256']),'EXISTING_OWNER_AUTHORITY')
 target=Path('/etc/systemd/system/alpaca-monthly-owned.service');unit=raw(P/'new-monthly.service',packet['new_unit_sha256']);raw(target,packet['old_unit_sha256']);need(not state()['DropInPaths'],'UNIT_OVERRIDE')
 root=Path(spec['manager']['root']);lock=Path(spec['manager']['account_lock_path']);need([lock.stat().st_dev,lock.stat().st_ino]==scope['original_lock_identity'],'ORIGINAL_LOCK')
 for f in [Path(oldscope['revocation_path']),Path(scope['revocation_path']),root/'ENTRY_HALT.json',root/'native/standing-loss-stop.json',root/'native/standing-loss-observation.json']:need(not os.path.lexists(f),'EXISTING_BLOCK_PRESERVED')
 out=dict(schema='MONTHLY_SOURCE_PATCH_V7_RECEIPT',status='SOURCE_PATCH_STATIC_VERIFIED',observed_ms=time.time_ns()//1000000,financial_parameters_changed=False,execution_window_changed=False,broker_writes=0)
 if mode=='verify':return out
 oldtimer=ctl('is-active','alpaca-monthly-owned.timer').strip();need(oldtimer=='active','EXPECTED_TIMER_ACTIVE')
 claim=P/'install-claim.json';need(not os.path.lexists(claim),'ALREADY_ATTEMPTED_READBACK_ONLY');put(claim,enc(dict(packet_sha256=PIN,observed_ms=out['observed_ms'],authorization=packet['authorization'])))
 committed=False;revoked=False
 try:
  ctl('stop','alpaca-monthly-owned.timer')
  deadline=time.monotonic()+180
  while state()['MainPID']!='0' or state()['Job']:
   need(time.monotonic()<deadline,'SERVICE_BUSY_NO_KILL');time.sleep(.25)
  with account_lock(dict(lock_path=str(lock))):
   need(state()['MainPID']=='0' and not state()['Job'],'OLD_NOT_IDLE')
   # Source-only rebinding, authorized by the current owner installation request.
   # No term/period/window/capital/loss/strategy rule may differ from original GO.
   go=Path(spec['authority']['owner_go_path']);value=dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',scope_sha256=packet['scope']['sha256'],owner_go_text='GO ALPACA_MONTHLY_STANDING '+packet['scope']['sha256'])
   put(go,enc(value));put(P/'source-only-authorization.json',enc(dict(original_scope_sha256=packet['old_scope_sha256'],replacement_scope_sha256=packet['scope']['sha256'],financial_parameters_changed=False,execution_window_changed=False,authorization=packet['authorization'],observed_ms=time.time_ns()//1000000)))
  ps=importlib.util.spec_from_file_location('actual_get_probe',P/'probe-v2.py');probe=importlib.util.module_from_spec(ps);ps.loader.exec_module(probe)
  result=probe.run_probe(spec,P);put(P/'actual-get-prepost.json',enc(result));need(result['status'] in {'GET_PREPOST_FEES_PASS_WINDOW_BLOCKED','GET_PREPOST_PASS_NO_POST'},'GET_PREPOST_NOT_ACCEPTED')
  with account_lock(dict(lock_path=str(lock))):
   need(state()['MainPID']=='0' and not state()['Job'],'OLD_NOT_IDLE_AFTER_PROBE');raw(target,packet['old_unit_sha256'])
   with sqlite3.connect((root/'book/monthly-orders-off.sqlite').as_uri()+'?mode=ro',uri=True) as db:need(all(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]==0 for t in ['positions','exits','dispatches']),'BOOK_NOT_EMPTY')
   # Probe held the same account lock; its final account GETs and no-write readback
   # are no more than5s old at this commit, otherwise abort without a fresh claim.
   need(0<=time.time_ns()//1000000-result['final_flat_started_ms']<=5000,'PROBE_COMMIT_STALE')
   def retire():
    effective=ctl('show','alpaca-monthly-owned.service','-p','ExecStart','--value')
    need(all(v in effective for v in [str(C/'app/scripts/run_alpaca_monthly_cycle_v1.py'),packet['spec']['path'],packet['spec']['sha256']]),'EFFECTIVE_SOURCE_NOT_SELECTED')
    need(state()['MainPID']=='0' and not state()['DropInPaths'],'SELECTED_UNIT_OVERRIDE_OR_BUSY')
    publish_once(Path(oldscope['revocation_path']),enc(dict(reason='OWNER_AUTHORIZED_OPENING_SOURCE_PATCH_V7',replacement_scope_sha256=packet['scope']['sha256'])))
   select_unit(target,raw(P/'old-monthly.service'),unit,Path(oldscope['revocation_path']),retire)
   revoked=True;committed=True
  ctl('start','alpaca-monthly-owned.timer')
  out.update(status='MONTHLY_SOURCE_PATCH_V7_INSTALLED_NO_BUY',scope_sha256=packet['scope']['sha256'],spec_sha256=packet['spec']['sha256'],source_only_owner_go_rebound=True,probe_status=result['status'],probe_proof_checks=result['proof_checks'],account_lock_inode=lock.stat().st_ino,financial_process_killed=False,observed_ms=time.time_ns()//1000000)
  put(P/'install-result.json',enc(out));return out
 except BaseException as error:
  revoked=os.path.lexists(oldscope['revocation_path']);selected=target.read_bytes()==unit
  cleanup_error=None
  try:
   need(target.read_bytes() in (raw(P/'old-monthly.service'),unit),'UNKNOWN_SELECTED_UNIT')
   need(not revoked or selected,'OLD_REVOKED_REPLACEMENT_NOT_SELECTED')
   ctl('start','alpaca-monthly-owned.timer')
  except BaseException as cleanup:cleanup_error=type(cleanup).__name__+':'+str(cleanup)
  put(P/'install-failed.json',enc(dict(error_type=type(error).__name__,reason=str(error),revoked=revoked,selected_new_source=selected,committed=committed,cleanup_error=cleanup_error,readback_required=True,observed_ms=time.time_ns()//1000000)));raise
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['verify','apply']);v=a.parse_args();print(json.dumps(run(v.mode),sort_keys=True))
