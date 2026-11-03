"""Exact initial-entry date exception. Requires a separate owner GO; never dispatches an order."""
import argparse,ast,hashlib,importlib.util,io,json,os,sqlite3,subprocess,sys,time
from contextlib import redirect_stdout
from pathlib import Path
P=Path(__file__).resolve().parent
PIN='5f828ca8a22b256c0cff202082bed75f4ce337af34e85def6dbb224902182e79'
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

def run(mode,owner_go_text=None):
 packet=json.loads(raw(P/'packet.json',PIN));
 if mode=='apply':need(owner_go_text==packet['owner_go_text'],'SEPARATE_EXACT_OWNER_GO_REQUIRED')
 for n,h in packet['helpers'].items():raw(P/n,h)
 C=Path(packet['candidate']);spec=json.loads(raw(packet['spec']['path'],packet['spec']['sha256']));scope=json.loads(raw(packet['scope']['path'],packet['scope']['sha256']));old=json.loads(raw(packet['old_spec']['path'],packet['old_spec']['sha256']));oldscope=json.loads(raw(old['authority']['scope_path'],packet['old_scope_sha256']))
 manifest=json.loads(raw(C/'source-manifest.json'));need(manifest['source_material_sha256']==packet['source_material_sha256'],'SOURCE_MATERIAL')
 for n,h in manifest['files'].items():raw(C/'app'/n,h)
 qual_spec=importlib.util.spec_from_file_location('exact_qualification',P/'qualification.py');qual=importlib.util.module_from_spec(qual_spec);qual_spec.loader.exec_module(qual);qualification=qual.qualify(C,packet,raw)
 sys.path[:0]=[str(C/'app')]
 compare_spec=importlib.util.spec_from_file_location('pure_compare',P/'compare.py');compare=importlib.util.module_from_spec(compare_spec);compare_spec.loader.exec_module(compare);compare.compare(old,spec,oldscope,scope,C/'app')
 from scripts.run_alpaca_monthly_cycle_v1 import verify,runner_config_sha256
 from research_lab.alpaca_monthly_binding_v1 import strategy_identity
 for name,module in tuple(sys.modules.items()):
  if name.split('.')[0] in {'research_lab','scripts','backtest','strategies'} and getattr(module,'__file__',None):need(Path(module.__file__).resolve().is_relative_to(C/'app'),'CHECKOUT_IMPORT_FALLBACK')
 from research_lab.alpaca_dynamic_live_runtime_v1 import account_lock
 from research_lab.kity_oct15_deadline_v1 import publish_once
 verify(packet['spec']['path'],packet['spec']['sha256'],dispatch=True);need(scope['strategy_identity']==strategy_identity() and runner_config_sha256(spec)==scope['runner_config_sha256'],'PROPOSED_AUTHORITY_IDENTITY')
 raw(packet['approved_prior_go']['path'],packet['approved_prior_go']['sha256'])
 oldgo=json.loads(raw(old['authority']['owner_go_path']));need(oldgo==dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',scope_sha256=packet['old_scope_sha256'],owner_go_text='GO ALPACA_MONTHLY_STANDING '+packet['old_scope_sha256']),'EXISTING_OWNER_AUTHORITY')
 target=Path('/etc/systemd/system/alpaca-monthly-owned.service');unit=raw(P/'new-monthly.service',packet['new_unit_sha256']);raw(target,packet['old_unit_sha256']);need(not state()['DropInPaths'],'UNIT_OVERRIDE')
 root=Path(spec['manager']['root']);lock=Path(spec['manager']['account_lock_path']);need([lock.stat().st_dev,lock.stat().st_ino]==scope['original_lock_identity'],'ORIGINAL_LOCK')
 for f in [Path(oldscope['revocation_path']),Path(scope['revocation_path']),root/'ENTRY_HALT.json',root/'native/standing-loss-stop.json',root/'native/standing-loss-observation.json']:need(not os.path.lexists(f),'EXISTING_BLOCK_PRESERVED')
 out=dict(schema='MONTHLY_INITIAL_RECOVERY_HANDOFF_V1',status='INITIAL_RECOVERY_STATIC_VERIFIED_ORDERS_OFF',observed_ms=time.time_ns()//1000000,capital_or_risk_limits_changed=False,execution_window_changed=True,broker_writes=0,qualification=qualification)
 need(time.time_ns()//1000000<packet['policy']['close_ms'],'RECOVERY_WINDOW_EXPIRED_NO_CARRY')
 with sqlite3.connect((root/'book/monthly-orders-off.sqlite').as_uri()+'?mode=ro',uri=True) as db:need(db.execute('SELECT COUNT(*) FROM selections').fetchone()[0]==1 and all(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]==0 for t in ['positions','exits','dispatches','rotations']),'INITIAL_BOOK_PHASE_REQUIRED')
 need(not (root/'native/native-intents.json').exists() and not (root/'native/native-floor.json').exists(),'NATIVE_INTENT_ALREADY_EXISTS')
 if mode=='verify':return out
 oldtimer=ctl('is-active','alpaca-monthly-owned.timer').strip();need(oldtimer=='active','EXPECTED_TIMER_ACTIVE')
 claim=P/'install-claim.json';need(not os.path.lexists(claim),'ALREADY_ATTEMPTED_READBACK_ONLY');put(claim,enc(dict(packet_sha256=PIN,observed_ms=out['observed_ms'],authorization=owner_go_text)))
 committed=False;revoked=False
 try:
  ctl('stop','alpaca-monthly-owned.timer')
  deadline=time.monotonic()+180
  while state()['MainPID']!='0' or state()['Job']:
   need(time.monotonic()<deadline,'SERVICE_BUSY_NO_KILL');time.sleep(.25)
  with account_lock(dict(lock_path=str(lock))):
   need(state()['MainPID']=='0' and not state()['Job'],'OLD_NOT_IDLE')
   # Separate exact owner GO approves only the named initial-entry exception.
   # Future period, capital, risk, reserve and custody remain unchanged.
   go=Path(spec['authority']['owner_go_path']);value=dict(schema='ALPACA_MONTHLY_STANDING_OWNER_GO_V1',scope_sha256=packet['scope']['sha256'],owner_go_text='GO ALPACA_MONTHLY_STANDING '+packet['scope']['sha256'])
   put(go,enc(value));put(P/'initial-recovery-authorization.json',enc(dict(original_scope_sha256=packet['old_scope_sha256'],replacement_scope_sha256=packet['scope']['sha256'],capital_or_risk_limits_changed=False,execution_window_changed=True,authorization=owner_go_text,observed_ms=time.time_ns()//1000000)))
  ps=importlib.util.spec_from_file_location('actual_get_probe',P/'probe-v3.py');probe=importlib.util.module_from_spec(ps);ps.loader.exec_module(probe)
  result=probe.run_probe(spec,P);put(P/'actual-get-prepost.json',enc(result));need(result['status'] in {'GET_PREPOST_FEES_PASS_WINDOW_BLOCKED','GET_PREPOST_PASS_NO_POST'},'GET_PREPOST_NOT_ACCEPTED')
  with account_lock(dict(lock_path=str(lock))):
   need(state()['MainPID']=='0' and not state()['Job'],'OLD_NOT_IDLE_AFTER_PROBE');raw(target,packet['old_unit_sha256'])
   with sqlite3.connect((root/'book/monthly-orders-off.sqlite').as_uri()+'?mode=ro',uri=True) as db:need(all(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]==0 for t in ['positions','exits','dispatches']),'BOOK_NOT_EMPTY')
   # Probe held the same account lock; its final account GETs and no-write readback
   # are no more than5s old at this commit, otherwise abort without a fresh claim.
   need(0<=time.time_ns()//1000000-result['final_flat_started_ms']<=5000,'PROBE_COMMIT_STALE')
   from research_lab.alpaca_monthly_cycle_v1 import MonthlyManager
   from research_lab.alpaca_monthly_binding_v1 import entry_cid
   manager=MonthlyManager(**spec['manager'])
   with manager.guard('dispatch.lock'),manager.guard():
    need(not (root/'native/native-intents.json').exists() and not (root/'native/native-floor.json').exists(),'NATIVE_INTENT_ALREADY_EXISTS')
    ticket=json.loads(raw(P/'original-ticket.json',packet['original_ticket_file_sha256']))
    selected=manager.book.seal_initial_recovery(packet['policy'],ticket,now_ms=time.time_ns()//1000000)
    put(P/'initial-recovery-selection.json',enc(selected))
   def retire():
    effective=ctl('show','alpaca-monthly-owned.service','-p','ExecStart','--value')
    need(all(v in effective for v in [str(C/'app/scripts/run_alpaca_monthly_cycle_v1.py'),packet['spec']['path'],packet['spec']['sha256']]),'EFFECTIVE_SOURCE_NOT_SELECTED')
    need(state()['MainPID']=='0' and not state()['DropInPaths'],'SELECTED_UNIT_OVERRIDE_OR_BUSY')
    approved=json.loads(raw(packet['approved_prior_scope']['path'],packet['approved_prior_scope']['sha256']))
    publish_once(Path(approved['revocation_path']),enc(dict(reason='EXPLICIT_OWNER_APPROVED_CACHE_SOURCE_REPLACEMENT',replacement_scope_sha256=packet['scope']['sha256'])))
    publish_once(Path(oldscope['revocation_path']),enc(dict(reason='OWNER_APPROVED_EXACT_INITIAL_RECOVERY_V1',replacement_scope_sha256=packet['scope']['sha256'])))
   select_unit(target,raw(P/'old-monthly.service'),unit,Path(oldscope['revocation_path']),retire)
   revoked=True;committed=True
  ctl('start','alpaca-monthly-owned.timer')
  out.update(status='MONTHLY_INITIAL_RECOVERY_CACHE_REPAIR_ARMED_NO_BUY',financial_terms_same_as_approved_1d6a09ad=True,scope_sha256=packet['scope']['sha256'],spec_sha256=packet['spec']['sha256'],separate_initial_recovery_go_verified=True,initial_recovery_selection_id=selected['selection_id'],probe_status=result['status'],probe_proof_checks=result['proof_checks'],account_lock_inode=lock.stat().st_ino,financial_process_killed=False,observed_ms=time.time_ns()//1000000)
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
 a=argparse.ArgumentParser();a.add_argument('mode',choices=['verify','apply']);a.add_argument('--owner-go-text');v=a.parse_args();print(json.dumps(run(v.mode,v.owner_go_text),sort_keys=True))
