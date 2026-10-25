"""Pinned ORDERS_OFF physical handoff only; never mint GO or change source/risk."""
from pathlib import Path
import hashlib,json,os,subprocess,time,sys
from types import SimpleNamespace
SYSTEMD=Path('/etc/systemd/system')
PROC_LOCKS=Path('/proc/locks')
STARTUP_TIMEOUT_SECONDS=30


def need(ok,reason):
    if not ok:raise ValueError('PUMP4_HANDOFF_'+reason)


def read(path,pin=None):
    path=Path(path);need(path.is_absolute() and not any(p.is_symlink() for p in (path,*path.parents)),'PATH')
    raw=path.read_bytes()
    if pin is not None:need(hashlib.sha256(raw).hexdigest()==pin,'PIN')
    return json.loads(raw)


def systemctl(*args):return subprocess.check_output(['/usr/bin/systemctl',*args],text=True,timeout=30)


def state(unit):return dict(r.split('=',1) for r in systemctl('show',unit,'--property=ActiveState,SubState,MainPID,UnitFileState,FragmentPath,DropInPaths,Job,ExecStop,ExecStopPost,NRestarts,Restart').splitlines() if '=' in r)


def lock_held_by(lock,pid):
    """Linux flock ownership, bound to the original device/inode and MainPID."""
    st=lock.stat()
    key=f'{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}'
    for line in PROC_LOCKS.read_text().splitlines():
        row=line.split()
        if len(row)==8 and row[1:4]==['FLOCK','ADVISORY','WRITE'] and row[4]==str(pid) and row[5]==key and row[6:]==['0','EOF']:
            return True
    return False


def no_go(scope):
    need(not os.path.lexists(Path(scope['root'])/'owner-go.json'),'GO_PRESENT_BLOCK_HANDOFF')


def inactive(unit):
    return unit['MainPID']=='0' and unit['ActiveState'] in {'inactive','failed'} and not unit.get('Job')


def await_owner(config,scope,lock,started_ms,*,old=False,config_pin=None,prior_receipts=()):
    """Observe one start only. Never restart/retry a failed owner."""
    deadline=time.monotonic()+STARTUP_TIMEOUT_SECONDS
    while True:
        no_go(scope);unit=state(config['unit']);proof=None
        if unit['ActiveState']=='active' and unit['MainPID']!='0' and not unit.get('Job') and lock_held_by(lock,unit['MainPID']):
            if old:
                try:
                    proof=terminal(config,unit)
                    if proof['observed_ms']<started_ms:proof=None
                except (ValueError,FileNotFoundError):pass
            elif (unit.get('NRestarts')=='0' and unit.get('Restart')=='no'
                  and unit.get('FragmentPath')==str(SYSTEMD/config['unit'])
                  and not unit.get('DropInPaths') and not unit.get('ExecStop') and not unit.get('ExecStopPost')):
                from research_lab.alpaca_dynamic_v1 import digest
                for path in sorted((Path(scope['root'])/'supervisor'/'receipts').glob('*.json')):
                    if path.name in prior_receipts:continue
                    row=read(path);at=row.get('observed_ms')
                    if (row.get('schema')=='PUMP4_EXECUTION_SUPERVISOR_RECEIPT_V1' and type(row.get('tick')) is int and row['tick']>=1 and isinstance(row.get('run_id'),str) and bool(row['run_id'])
                        and str(row.get('pid'))==unit['MainPID'] and row.get('mode')=='ORDERS_OFF'
                        and row.get('scope_sha256')==digest(scope) and row.get('runner_config_sha256')==config_pin
                        and row.get('broker_writes')==0 and row.get('receipt_persisted',True) is True
                        and type(at) is int and started_ms<=at<=time.time_ns()//1000000 and time.time_ns()//1000000-at<10000
                        and isinstance(row.get('result'),dict) and not row['result'].get('status','BLOCKED').startswith('BLOCKED')):
                        proof=dict(run_id=row['run_id'],tick=row['tick'],receipt_path=str(path),receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),pid=int(unit['MainPID']),observed_ms=at)
                        break
            after=state(config['unit'])
            if proof and after['ActiveState']=='active' and after['MainPID']==unit['MainPID'] and not after.get('Job') and lock_held_by(lock,unit['MainPID']):
                return proof
        if time.monotonic()>=deadline or unit['ActiveState']=='failed':
            # Only bounded non-secret physical diagnostics; no implicit rollback.
            diagnostic={k:unit.get(k) for k in ('ActiveState','SubState','MainPID','NRestarts','UnitFileState')}
            raise ValueError('PUMP4_HANDOFF_STARTUP_UNPROVEN:'+json.dumps(diagnostic,sort_keys=True))
        time.sleep(.2)


def exact_artifact(path,pin,reason,*,required=True):
    from research_lab.kity_oct15_deadline_v1 import stable_bytes
    path=Path(path)
    need(path.is_absolute() and not any(p.is_symlink() for p in (path,*path.parents)),reason+'_PATH')
    if not path.exists():need(not required,reason+'_MISSING');return False
    need(path.is_file() and path.stat().st_nlink==1 and hashlib.sha256(stable_bytes(path)).hexdigest()==pin,reason)
    return True


def command_free(c):
    root=Path(c['runtime_root'])
    need(not any(not (root/'results'/p.name).is_file() for p in (root/'commands').glob('*.json')),'PENDING_OLD_COMMAND')


def guard_original(c):
    for n,h in c['source_files'].items():need(hashlib.sha256((Path(c['app_root'])/n).read_bytes()).hexdigest()==h,'ORIGINAL_SOURCE_DRIFT')
    for n,h in c['guard_source_files'].items():need(hashlib.sha256(Path(n).read_bytes()).hexdigest()==h,'ORIGINAL_GUARD_DRIFT')
    need(hashlib.sha256(subprocess.run(['crontab','-l'],check=True,capture_output=True).stdout).hexdigest()==c['original_cron_sha256'],'CRON_DRIFT')
    lock=Path(c['custody_runtime_root'])/'account.lock';st=lock.stat()
    need(not lock.is_symlink() and st.st_ino==c['account_lock_inode'] and st.st_dev==64769,'ORIGINAL_LOCK_CHANGED')
    need(lock.stat().st_nlink==1,'LOCK_LINKS')
    return lock


def terminal(c,unit):
    h=read(Path(c['custody_runtime_root'])/'heartbeat.json');s=h.get('state') or {}
    need(h.get('mode')=='ORDERS_OFF' and h.get('phase')==s.get('phase')=='TERMINAL','OLD_OWNER_NOT_TERMINAL')
    need(str(h['pid'])==unit['MainPID'] and 0<=time.time_ns()//1000000-h['at_ms']<10000,'OLD_OWNER_HEARTBEAT')
    need(h.get('account_lock_inode')==c['account_lock_inode'],'OLD_HEARTBEAT_LOCK')
    command_free(c)
    return dict(mode=h['mode'],phase=h['phase'],pid=h['pid'],observed_ms=h['at_ms'])


def once_file(path,raw,mode=0o600):
    path=Path(path);need(not any(p.is_symlink() for p in (path,*path.parents)),'CREATE_PATH')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(parent)
    finally:os.close(parent)


def run(packet_path,packet_sha,mode):
    need(mode in {'inspect','handoff','rollback','complete-stopped'},'MODE')
    p=read(packet_path,packet_sha);root=Path(p['candidate']);sys.path.insert(0,str(root/'app'))
    from research_lab.pump4_selected_runner_v1 import pinned,source_pins,config_sha
    from research_lab.pump4_runtime_sources_v1 import TrustedSources
    from research_lab.pump4_bybit_sources_v1 import flat_account
    from research_lab.kity_micro_physical_owner_v1 import load_bound_credentials,AccountLease
    from research_lab.pump4_account_adapter_v1 import frozen_plan
    from research_lab.kity_micro_physical_owner_v1 import publish
    from research_lab.pump4_execution_plan_v1 import frozen_sources
    config=pinned(p['config']);scope=pinned(config['authority']);old=pinned(config['original_owner'])
    need(config['source_files']==source_pins() and scope['runner_config_sha256']==config_sha(config),'SOURCE_OR_SCOPE')
    need(config['mode']==scope['mode']=='ORDERS_OFF' and config['unit']=='pump4-execution-owner.service','ORDERS_OFF_ONLY')
    no_go(scope)
    accept=read(root/'acceptance.json');need(accept['status']=='PASS' and all(accept['counts'][k]==0 for k in ('failures','errors','skipped')),'ACCEPTANCE')
    need(old['unit']=='kity-execution-micro-owner.service','ORIGINAL_OWNER_IDENTITY')
    lock=guard_original(old);before=state(old['unit']);new_before=state(config['unit'])
    fragment=SYSTEMD/config['unit'];drop=Path(p['inhibitor_path']);marker=Path(config['inhibit_marker'])
    need(drop==SYSTEMD/(old['unit']+'.d')/'90-kity-micro-inhibit.conf','INHIBITOR_IDENTITY')
    need(hashlib.sha256(p['inhibitor_text'].encode()).hexdigest()==p['inhibitor_sha256']
        and hashlib.sha256(p['unit_text'].encode()).hexdigest()==p['unit_sha256'],'PACKET_ARTIFACT_PINS')
    need(not before.get('ExecStop') and not before.get('ExecStopPost') and not before.get('Job'),'UNKNOWN_OLD_STOP_HOOK_OR_JOB')
    need(not new_before.get('ExecStop') and not new_before.get('ExecStopPost') and not new_before.get('DropInPaths') and not new_before.get('Job'),'UNKNOWN_NEW_OVERRIDE_OR_JOB')
    command_free(old)
    if mode in {'inspect','handoff'}:
        need(before['ActiveState']=='active' and before['UnitFileState']=='enabled' and before['MainPID']!='0','ORIGINAL_OWNER_INACTIVE')
        need(not before.get('DropInPaths'),'UNKNOWN_STOP_HOOK_OR_OVERRIDE')
        heartbeat=terminal(old,before)
        need(lock_held_by(lock,before['MainPID']),'ORIGINAL_OWNER_LEASE')
        need(new_before['FragmentPath']=='' and inactive(new_before),'NEW_OWNER_ALREADY_EXISTS_RECONCILE')
        need(not any(os.path.lexists(path) for path in (fragment,drop,marker)),'HANDOFF_ALREADY_STARTED_NO_AUTORETRY')
    else:
        # The immutable exact marker survives every partial state and rollback.
        exact_artifact(marker,hashlib.sha256(p['marker_text'].encode()).hexdigest(),'ROLLBACK_MARKER')
        exact_artifact(drop,p['inhibitor_sha256'],'ROLLBACK_INHIBITOR',required=False)
        fragment_exists=exact_artifact(fragment,p['unit_sha256'],'ROLLBACK_UNIT',required=False)
        if mode=='complete-stopped':
            need(inactive(before) and before['UnitFileState']=='disabled','PARTIAL_OLD_NOT_RETIRED')
            need(not fragment_exists and new_before['FragmentPath']=='' and inactive(new_before),'PARTIAL_NEW_ALREADY_EXISTS')
            exact_artifact(drop,p['inhibitor_sha256'],'PARTIAL_EXACT_INHIBITOR_REQUIRED')
        need(before.get('DropInPaths','') in ('',str(drop)),'UNKNOWN_OLD_OVERRIDE')
        need(not any(path!=drop for path in drop.parent.glob('*.conf')),'UNKNOWN_OLD_OVERRIDE_FILE')
        need(new_before['FragmentPath'] in ('',str(fragment)),'ROLLBACK_UNKNOWN_FRAGMENT')
        need(fragment_exists or (inactive(new_before) and new_before['FragmentPath']==''),'ROLLBACK_UNKNOWN_PROCESS')
        old_active=before['ActiveState']=='active' and before['MainPID']!='0'
        need(old_active or inactive(before),'ROLLBACK_OLD_TRANSITIONING')
        if old_active:
            need(inactive(new_before),'ROLLBACK_COMPETING_OWNERS')
            heartbeat=terminal(old,before)
            need(lock_held_by(lock,before['MainPID']),'ORIGINAL_OWNER_LEASE')
        else:
            # Last durable heartbeat still proves terminal history while stopped.
            h=read(Path(old['custody_runtime_root'])/'heartbeat.json')
            need(h.get('mode')=='ORDERS_OFF' and h.get('phase')==(h.get('state') or {}).get('phase')=='TERMINAL'
                and h.get('account_lock_inode')==old['account_lock_inode'],'OLD_OWNER_NOT_TERMINAL')
            heartbeat={}
    key,secret=load_bound_credentials(old)
    capture_root=Path(scope['root'])/'handoff-captures';capture_root.mkdir(mode=0o700,parents=True,exist_ok=True)
    observer=SimpleNamespace(key=key,secret=secret,root=capture_root,scope=dict(account_fingerprint=old['account_fingerprint']),clock=lambda:time.time_ns()//1000000)
    sources=TrustedSources({},observer)
    def fresh():
        bundle,public=sources.flat();now=time.time_ns()//1000000
        view=flat_account(bundle,expected_fingerprint=old['account_fingerprint'],now_ms=now)
        need(view['positions_flat'] is True and view['open_orders_empty'] is True,'ACCOUNT_NOT_FLAT')
        return dict(observed_ms=now,source_ms=view['source_ms'],bundle_sha256=__import__('research_lab.alpaca_dynamic_v1',fromlist=['digest']).digest(bundle),positions_flat=view['positions_flat'],open_orders_empty=view['open_orders_empty'],borrowed_funds=view['borrowed_funds'],margin_mode=view['margin_mode'],available_balance=view['available_balance'])
    account=fresh()
    if mode=='inspect':
        result=dict(schema='PUMP4_READONLY_HANDOFF_PREFLIGHT_V1',status='READ_ONLY_FLAT_TERMINAL_ORDERS_OFF_PASS',account=account,old_owner=before,heartbeat=heartbeat,original_lock_inode=lock.stat().st_ino,broker_writes=0,owner_go_created=False,financial_units_changed=0)
        print(json.dumps(result));return result
    need(0<=time.time_ns()//1000000-account['observed_ms']<5000,'ACCOUNT_READBACK_STALE')
    no_go(scope);guard_original(old);command_free(old)
    if mode in {'handoff','complete-stopped'}:
        if mode=='handoff':
            # The active old owner is terminal and command-free; original lock remains.
            terminal(old,state(old['unit']))
            once_file(marker,p['marker_text'].encode())
            once_file(drop,p['inhibitor_text'].encode(),0o644)
            systemctl('daemon-reload')
            systemctl('disable','--now',old['unit'])
            need(state(old['unit'])['MainPID']=='0' and state(old['unit'])['ActiveState']=='inactive','OLD_OWNER_STILL_ACTIVE')
        need(inactive(state(old['unit'])),'OLD_OWNER_STILL_ACTIVE')
        lease=AccountLease(lock)
        try:need(lease.inode==old['account_lock_inode'],'LEASE_IDENTITY')
        finally:lease.close()
        after=fresh() # Independent post-stop broker truth before new selection.
        once_file(fragment,p['unit_text'].encode(),0o644)
        subprocess.run(['/usr/bin/systemd-analyze','verify',str(fragment)],check=True,capture_output=True,timeout=20)
        systemctl('daemon-reload')
        no_go(scope)
        prior_receipts={path.name for path in (Path(scope['root'])/'supervisor'/'receipts').glob('*.json')}
        started_ms=time.time_ns()//1000000
        systemctl('enable','--now',config['unit'])
        startup=await_owner(config,scope,lock,started_ms,config_pin=p['config']['sha256'],prior_receipts=prior_receipts)
    else:
        # Recover only reviewed partial artifacts. No repeated handoff or GO.
        if fragment.exists():systemctl('disable','--now',config['unit'])
        need(inactive(state(config['unit'])),'NEW_OWNER_STILL_ACTIVE')
        current_old=state(old['unit'])
        if current_old['ActiveState']=='active':
            terminal(old,current_old)
            need(lock_held_by(lock,current_old['MainPID']),'ORIGINAL_OWNER_LEASE')
        else:
            need(inactive(current_old),'ROLLBACK_OLD_TRANSITIONING')
            lease=AccountLease(lock)
            try:need(lease.inode==old['account_lock_inode'],'LEASE_IDENTITY')
            finally:lease.close()
        after=fresh();no_go(scope);guard_original(old);command_free(old)
        if exact_artifact(drop,p['inhibitor_sha256'],'ROLLBACK_INHIBITOR_CHANGED',required=False):
            drop.unlink() # Only engineering inhibitor; marker and all history stay.
            parent=os.open(drop.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(parent)
            finally:os.close(parent)
        systemctl('daemon-reload')
        started_ms=time.time_ns()//1000000 if current_old['ActiveState']!='active' else 0
        # enable --now does not restart an already active terminal original owner.
        systemctl('enable','--now',old['unit'])
        startup=await_owner(old,scope,lock,started_ms,old=True)
    no_go(scope);guard_original(old)
    need(inactive(state(old['unit'] if mode in {'handoff','complete-stopped'} else config['unit'])),'COMPETING_OWNER_AFTER_STARTUP')
    result=dict(schema='PUMP4_ORDERS_OFF_HANDOFF_RECEIPT_V1',operation_mode=mode,status='PUMP4_ORDERS_OFF_SELECTED' if mode in {'handoff','complete-stopped'} else 'ORIGINAL_OWNER_RESTORED_ORDERS_OFF',observed_ms=time.time_ns()//1000000,account_before=account,account_after=after,old_owner=state(old['unit']),new_owner=state(config['unit']),startup_proof=startup,scope_mode=scope['mode'],original_lock_inode=lock.stat().st_ino,broker_writes=0,owner_go_created=False,tiny_ready=False)
    publish(root/('handoff-'+str(result['observed_ms'])+'-'+mode+'.json'),result);print(json.dumps(result));return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--packet',required=True);parser.add_argument('--packet-sha256',required=True);parser.add_argument('--mode',choices=('inspect','handoff','rollback','complete-stopped'),default='inspect')
    args=parser.parse_args();run(args.packet,args.packet_sha256,args.mode)
