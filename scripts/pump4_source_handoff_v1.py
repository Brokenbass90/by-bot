"""One exact flat/unspent PUMP4 handoff. Default no requests, no order API.

Financial apply needs a NEW exact packet GO. A start with an unknown response is
never retried. Post-start rollback only revokes entries and leaves custody intact.
"""
import argparse,copy,fcntl,hashlib,importlib.util,json,os,re,stat,subprocess,sys,time,uuid
from contextlib import contextmanager
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
if sys.flags.optimize:raise RuntimeError('OPTIMIZED_PYTHON_FORBIDDEN')

BASE=Path('/opt/bybot-research/pump4-current-hour-repair-20261101')
UNIT=Path('/etc/systemd/system/pump4-execution-owner.service')
OLD_CONFIG=Path('/opt/bybot-research/pump4-server-orders-off-20261023/tiny-activation-20261028-v1/runner.json')
OLD_CONFIG_PIN='fa0b3b2ec893f5167d79e71ef7fcf5a1d3788075105a2732663a8dafec53014a'
OLD_SCOPE_PIN='fec235e3dea12245d96859a6786d811551f9341d9a860ee4fac88dea4bfcf794'
POLICY=dict(allocation_usdt='50',gross_usdt='30',reserve_usdt='20',risk_usdt='1',day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',slippage_bps='10',max_entries=1,max_positions=1)
DAY=86400000
SOURCE_PIN='05f89618d8550664cf2d914f000ef9f7b101d32176032adb78a6d7bbbdb03dfd'
BASE_HELPER_PIN='3f3efc987041f755219b3c241ca3048a22eec5a6fa02f26ce47f2210dec825d7'
HEALTH_TEMPLATE_PIN='396c6d21413217a664b26516dd55e9bf72ebcc530fd33ffc119cea2ff1444370'
OLD_UID_PIN='4a67566b52682b7089213b24bb7d562686486c365d6adcad9cbc6cac1a2bec87'
HEALTH_SPEC=Path('/opt/bybot-research/kity-micro-owner-20261015/monitor-v1/spec.json')
HEALTH_SPEC_PIN='87d419af4ea92dfd7a1c6463afbfcfba4c41920e6afe62f9436478cf49dff747'
PRESERVED_UNITS={
 'pump4-data-supervisor.service':'cb9de84027ee8d42e72068ce9f66fbbdb6fcf433cc27f435883f52c01d495a35',
 'alpaca-monthly-owned.service':'9d94467d301cf5f545bee18e50b838623c061b72f46a2fbdd9b7d1991932cc1d',
 'alpaca-monthly-owned.timer':'33a1bd34d3a99a92d8273717f43c49f178309f263656a8f67c44b6cbd55c3bcb'}


class HandoffError(ValueError):pass
def need(value,reason):
    if not value:raise HandoffError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
def safe(path):
    path=Path(path).absolute()
    need('..' not in path.parts and not any(p.is_symlink() for p in (path,*path.parents)),'PATH_CUSTODY')
    return path
def read(path):
    path=safe(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd);need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.geteuid() and st.st_size<=5000000,'FILE_CUSTODY')
        with os.fdopen(os.dup(fd),'rb') as f:raw=f.read(5000001)
        ident=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        need(len(raw)==st.st_size and ident(st)==ident(os.fstat(fd))==ident(path.lstat()),'FILE_CHANGED')
        return raw
    finally:os.close(fd)
def once(path,raw):
    path=safe(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(os.dup(fd),'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    finally:os.close(fd)
    d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(d)
    finally:os.close(d)
def cas(path,before,after):
    path=safe(path);need(read(path)==before,'CAS_DRIFT')
    mode=path.stat().st_mode&0o777;temp=path.with_name(path.name+'.pump4-'+uuid.uuid4().hex)
    once(temp,after);os.chmod(temp,mode);need(read(path)==before,'CAS_RACE');os.replace(temp,path)
    d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(d)
    finally:os.close(d)
@contextmanager
def file_lock(path,inode=None):
    path=safe(path);fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd);need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.geteuid()
            and (inode is None or st.st_ino==inode) and st.st_ino==path.stat().st_ino,'LOCK_IDENTITY')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
    finally:os.close(fd)
def unused(root,*,revocation=None):
    root=safe(root);need(root.is_dir(),'OLD_ROOT_MISSING')
    for name in ('admitted-lifecycle.json','risk.jsonl','entry-loss-stop.json'):
        need(not os.path.lexists(root/name),'OLD_FINANCIAL_HISTORY:'+name)
    marker=root/'entry-revoked.json'
    if os.path.lexists(marker):need(revocation is not None and read(marker)==encode(revocation),'OLD_REVOCATION_CONFLICT')
    for name in ('flows','tickets','send-barriers','supervisor/attempts'):
        folder=safe(root/name)
        need(not folder.exists() or (folder.is_dir() and next(folder.iterdir(),None) is None),'OLD_FINANCIAL_HISTORY:'+name)
def revoke(root,scope,pin,reason):
    value=dict(scope_sha256=scope,packet_sha256=pin,reason=reason);path=safe(root)/'entry-revoked.json'
    if os.path.lexists(path):need(read(path)==encode(value),'REVOCATION_CONFLICT')
    else:once(path,encode(value))
    return value
def check_snapshot(snapshot,e,now):
    need(type(snapshot['observed_ms']) is int and 0<=now-snapshot['observed_ms']<=5000,'ACCOUNT_SNAPSHOT_STALE')
    need(snapshot['flat'] is True and snapshot['history_empty'] is True,'ACCOUNT_OR_HISTORY_NOT_EMPTY')
    need(snapshot['account_identity_sha256']==e['old_account_identity_sha256'],'DIFFERENT_BYBIT_UID')
    need(snapshot['account_fingerprint']==e['new_account_fingerprint'],'NEW_KEY_FINGERPRINT')
    amount=Decimal(snapshot['available_usdt'])
    need(amount.is_finite() and amount>=Decimal(POLICY['allocation_usdt']),'INSUFFICIENT_ALLOCATION')
    until=snapshot.get('key_valid_until_ms')
    need((type(until) is int and until>=e['required_key_until_ms']) or snapshot.get('key_no_fixed_expiry') is True,'KEY_EXPIRES_DURING_CUSTODY')

def apply_once(folder,pin,e,ops,*,owner_go_text):
    need(owner_go_text=='GO PUMP4_SOURCE_REPAIR_PACKET '+pin,'EXACT_NEW_OWNER_GO_REQUIRED')
    need(e.get('acceptance_ready') is True,'INDEPENDENT_AND_OFFLINE_ACCEPTANCE_REQUIRED')
    folder=safe(folder);claim=folder/'handoff-claim.json'
    need(not os.path.lexists(claim),'ATTEMPT_ALREADY_CLAIMED_NO_RETRY')
    old=safe(e['old_scope']['root']);new=safe(e['new_scope']['root'])
    need(not os.path.lexists(new),'NEW_ROOT_EXISTS_NO_RESET')
    if ops.clock()<e['new_scope']['valid_from_ms']:
        return dict(status='NOT_DUE_NO_COMMAND_SENT',broker_writes=0,financial_command_sent=False)
    need(ops.clock()<e['new_scope']['valid_until_ms'],'NEW_SCOPE_EXPIRED')
    ops.verify(e);unused(old)
    first=ops.snapshot(e);check_snapshot(first,e,ops.clock())
    stop_attempted=False;new_start_attempted=False
    with ops.observer_lock(e):
        # Another approved handoff may have completed during the first GET.
        # Recheck the selected owner INSIDE the shared observer lock, before
        # claiming, revoking or stopping any process.
        ops.verify(e);unused(old);check_snapshot(first,e,ops.clock())
        once(claim,encode(dict(packet_sha256=pin,started_ms=ops.clock(),first_snapshot=first,no_retry=True)))
        try:
            revoked=revoke(old,e['old_scope_sha256'],pin,'OWNER_SOURCE_REPAIR_HANDOFF')
            stop_attempted=True;ops.stop(e)
            with ops.account_lock(e):
                ops.verify(e,stopped=True);unused(old,revocation=revoked)
                second=ops.snapshot(e);check_snapshot(second,e,ops.clock())
                unused(old,revocation=revoked)
                need(ops.clock()<e['new_scope']['valid_until_ms'],'WINDOW_ENDED_DURING_HANDOFF')
                need(not os.path.lexists(new),'NEW_ROOT_RACED')
                new.mkdir(parents=True,mode=0o700)
                ops.install(e)
                go=dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=e['new_scope_sha256'],owner_go_text='GO PUMP4_TINY '+e['new_scope_sha256'])
                once(new/'owner-go.json',encode(go))
            new_start_attempted=True  # Set BEFORE sending start: a lost reply is UNKNOWN.
            ops.start(e)
            result=ops.readback(e)
            result.update(packet_sha256=pin,first_snapshot=first,second_snapshot=second,
                financial_command_repeated=False,installer_broker_writes=0)
            once(folder/'handoff-receipt.json',encode(result));return result
        except Exception as exc:
            if stop_attempted and not new_start_attempted:
                # No new start has been attempted. Only old, entry-revoked custody
                # may be restored; the claim and all histories remain forever.
                if new.exists():revoke(new,e['new_scope_sha256'],pin,'PRESTART_FAILURE_ENTRY_REVOKED')
                ops.restore_revoked_old(e)
            try:once(folder/'handoff-error.json',encode(dict(observed_ms=ops.clock(),packet_sha256=pin,
                status='UNKNOWN_READBACK_ONLY' if new_start_attempted else 'FAILED_PRESTART_OLD_ENTRY_REVOKED',error_type=type(exc).__name__)))
            except OSError:pass
            raise

def revoke_entry(folder,pin,e,ops,*,owner_go_text):
    need(owner_go_text=='REVOKE PUMP4_SOURCE_REPAIR_PACKET '+pin,'EXACT_REVOKE_REQUIRED')
    root=safe(e['new_scope']['root']);need(root.is_dir(),'NO_SELECTED_RUNTIME')
    expected=dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',scope_sha256=e['new_scope_sha256'],owner_go_text='GO PUMP4_TINY '+e['new_scope_sha256'])
    need(json.loads(read(root/'owner-go.json'))==expected,'REVOCATION_SCOPE')
    revoke(root,e['new_scope_sha256'],pin,'OWNER_REVOKE_NEW_ENTRIES_KEEP_CUSTODY')
    return dict(status='ENTRY_REVOKED_CUSTODY_PRESERVED',observed_ms=ops.clock(),broker_writes=0,owner_action_required=True)

def load_packet(path,pin):
    folder=safe(path).parent;raw=read(path);need(sha(raw)==pin,'PACKET_PIN')
    p=json.loads(raw);need(p['schema']=='PUMP4_SOURCE_REPAIR_OWNER_PACKET_V1' and p['packet_dir']==str(folder)
        and folder.is_relative_to(BASE),'PACKET_PATH')
    mandatory={'handoff.py','base_ops.py','before.json','runner.json','scope.json',
        'health.py','health-legacy-immutable.py','notifications.json','old-owner.service',
        'new-owner.service','old-wrapper.py','new-wrapper.py','old-original-owner.json','old-notifications.json'}
    proof_names={'offline-acceptance.json','independent-review.json'}
    actual=set(p['files']);runtime=actual-proof_names
    need(runtime in (mandatory,mandatory|{'original-owner.json'}) and (actual&proof_names in (set(),proof_names)),'EXACT_PACKET_FILE_SET')
    material={k:v for k,v in p.items() if k not in {'files','material_sha256'}}
    material['files']={k:v for k,v in p['files'].items() if k not in proof_names}
    need(digest(material)==p['material_sha256'],'MATERIAL_BINDING')
    for name,h in p['files'].items():
        need('/' not in name and name not in {'.','..'} and sha(read(folder/name))==h,'PACKET_FILE_PIN')
    need(p['files'].get('handoff.py')==sha(read(Path(__file__))),'INSTALLER_SELF_PIN')
    b=json.loads(read(folder/'before.json'));c=json.loads(read(folder/'runner.json'));s=json.loads(read(folder/'scope.json'))
    oldc=b['config'];olds=b['scope']
    need(sha(encode(oldc))==OLD_CONFIG_PIN and digest(olds)==OLD_SCOPE_PIN,'EXACT_PREDECESSOR')
    originalraw=read(folder/'old-original-owner.json');notificationraw=read(folder/'old-notifications.json')
    need(sha(originalraw)==oldc['original_owner']['sha256'] and json.loads(originalraw)==b['original'],'PINNED_LEGACY_CONFIGURATION')
    need(sha(notificationraw)==oldc['notifications']['sha256'] and json.loads(notificationraw)==b['notifications'],'PINNED_LEGACY_NOTIFICATION')
    need(set(p['old_money_anchors'])=={'owner-scope.json','owner-go.json','send-barrier-binding.json'},'REQUIRED_MONEY_ANCHORS')
    need(olds['policy']==s['policy']==POLICY and s['mode']==c['mode']=='OWNER_TINY_LIVE','UNCHANGED_ONE_ENTRY_POLICY')
    need(all(s[k]==olds[k] for k in ('account_lock_path','account_lock_inode')) and s['account_lock_inode']==818853,'ORIGINAL_LOCK')
    need(olds['valid_until_ms']<=s['valid_from_ms']<s['valid_until_ms'] and s['valid_until_ms']-s['valid_from_ms']<=7*DAY,'SEPARATE_BOUNDED_SCOPE')
    need(c['data_source']==oldc['data_source'] and c['epoch_started_ms']==oldc['epoch_started_ms'],'ORIGINAL_DATA_EPOCH')
    need(c['entry_max_delay_ms']==60000 and c['candidate_source']=='CURRENT_H1_PUBLICATIONS_V1','ENTRY_SOURCE')
    need(c['execution_policy']==s['execution_policy'] and all(c['execution_policy'][k]==v for k,v in oldc['execution_policy'].items() if k!='source_manifest_sha256'),'UNCHANGED_EXECUTION_RULES')
    need(c['execution_policy']['source_manifest_sha256']==digest(c['source_files']),'SOURCE_EXECUTION_BINDING')
    need(s['runner_config_sha256']==digest({k:v for k,v in c.items() if k!='authority'}) and c['authority']==dict(path=str(folder/'scope.json'),sha256=sha(encode(s))),'NEW_CONFIG_SCOPE')
    need(c['account_fingerprint']==s['account_fingerprint'] and c['custody_runtime_root']==s['root'],'NEW_IDENTITY_ROOT')
    need(safe(p['candidate_root'])==BASE/'candidate-05f89618d8550664' and safe(c['app_root'])==safe(p['candidate_root'])/'app' and safe(s['root']).is_relative_to(safe(p['candidate_root'])/'runtime'),'CANDIDATE_PATHS')
    need(p['source_manifest_sha256']==SOURCE_PIN and p['files']['base_ops.py']==BASE_HELPER_PIN
        and p['old_account_identity_sha256']==OLD_UID_PIN and p['preserved_units']==PRESERVED_UNITS,'FIXED_ACCEPTED_SOURCES')
    need(sha(read(folder/'old-owner.service'))=='78a3b337ac6dfcea5b50b23824c6ee4beda16a1cf89353d355a0d7b594c7a970','OLD_UNIT_PIN')
    need(p['wrapper_path']=='/opt/bybot-research/kity-micro-owner-20261015/monitor-v1/health.py'
        and sha(read(folder/'old-wrapper.py'))==oldc['guard_source_files'][p['wrapper_path']],'OLD_WRAPPER_PIN')
    health=read(folder/'health.py').decode()
    normalized=re.sub(r"CONFIG=Path\('[^']*'\)","CONFIG=Path('/PACKET/runner.json')",health)
    need(sha(normalized.encode())==HEALTH_TEMPLATE_PIN and "CONFIG=Path('"+str(folder/'runner.json')+"')" in health,'HEALTH_TEMPLATE')
    need(p['files']['health-legacy-immutable.py']=='4c1674865daf0e2da2014642d2d474f8e206c2c885f14f0cc40bc16b65654ed8','LEGACY_NOTIFY_HELPER')
    notification=json.loads(read(folder/'notifications.json'))
    need(notification==dict(b['notifications'],output_root=s['root']+'/notifications'),'PRESERVED_NOTIFICATION_CHANNEL')
    guards=dict(oldc['guard_source_files']);guards[p['wrapper_path']]=p['files']['new-wrapper.py']
    for name in ('health.py','health-legacy-immutable.py','notifications.json'):guards[str(folder/name)]=p['files'][name]
    credential_fields=('credential_source','credential_source_sha256','account_fingerprint')
    if any(c[k]!=oldc[k] for k in credential_fields):
        need(c['credential_source']!=oldc['credential_source'],'NO_ACTIVE_ENV_REPLACEMENT')
        original=json.loads(read(folder/'original-owner.json'))
        need(original==dict(b['original'],**{k:c[k] for k in credential_fields})
            and c['original_owner']==dict(path=str(folder/'original-owner.json'),sha256=p['files']['original-owner.json']),'ROTATED_ORIGINAL_BINDING')
        guards[c['credential_source']]=c['credential_source_sha256']
    else:need(c['original_owner']==oldc['original_owner'],'ORIGINAL_OWNER_REFERENCE')
    expected=copy.deepcopy(oldc)
    for k in ('app_root','source_files','custody_runtime_root','authority','unit_template_sha256',*credential_fields,'original_owner','execution_policy'):
        expected[k]=c[k]
    expected.update(candidate_source='CURRENT_H1_PUBLICATIONS_V1',guard_source_files=guards,
        notifications=dict(path=str(folder/'notifications.json'),sha256=p['files']['notifications.json']))
    need(c==expected,'UNREVIEWED_CONFIG_FIELD_CHANGE')
    expected_scope=copy.deepcopy(olds)
    for k in ('root','account_fingerprint','execution_policy','runner_config_sha256','valid_from_ms','valid_until_ms'):expected_scope[k]=s[k]
    need(s==expected_scope,'UNREVIEWED_SCOPE_FIELD_CHANGE')
    unit=read(folder/'old-owner.service').decode().replace(oldc['app_root'],c['app_root']).replace(str(OLD_CONFIG),str(folder/'runner.json')).replace(olds['root'],s['root'])
    unit=unit.replace('Environment=PYTHONDONTWRITEBYTECODE=1\n','Environment=PYTHONDONTWRITEBYTECODE=1\nEnvironment=PYTHONOPTIMIZE=0\n')
    unit=re.sub(r'--config-sha256 [0-9a-f]{64}','--config-sha256 '+sha(encode(c)),unit)
    need(read(folder/'new-owner.service')==unit.encode()
        and c['unit_template_sha256']==sha(re.sub(r'--config-sha256 [0-9a-f]{64}','--config-sha256 <PIN>',unit).encode()),'EXACT_DERIVED_UNIT')
    wrapper=("from pathlib import Path\nimport hashlib,runpy\np=Path('"+str(folder/'health.py')+"')\nif hashlib.sha256(p.read_bytes()).hexdigest()!='"+p['files']['health.py']+"':raise RuntimeError('HEALTH_SOURCE_PIN')\nrunpy.run_path(str(p),run_name='__main__')\n").encode()
    need(read(folder/'new-wrapper.py')==wrapper,'EXACT_WRAPPER')
    ready=False
    if proof_names<=actual:
        offline=json.loads(read(folder/'offline-acceptance.json'));review=json.loads(read(folder/'independent-review.json'))
        need(offline.get('material_sha256')==review.get('material_sha256')==p['material_sha256'],'ACCEPTANCE_MATERIAL_MISMATCH')
        ready=(offline.get('status')=='PASS' and offline.get('network_denied') is True
            and offline.get('broker_requests')==offline.get('broker_writes')==0
            and review.get('status')=='PASS' and review.get('unresolved_important')==0
            and review.get('runtime_model_verified') is True and review.get('model')=='gpt-6-astra'
            and review.get('effort') in {'high','xhigh'})
    return dict(packet=p,folder=folder,before=b,new_config=c,old_scope=olds,new_scope=s,
        old_scope_sha256=digest(olds),new_scope_sha256=digest(s),new_config_sha256=sha(encode(c)),
        new_account_fingerprint=c['account_fingerprint'],old_account_identity_sha256=p['old_account_identity_sha256'],
        required_key_until_ms=s['valid_until_ms']+8*DAY,acceptance_ready=ready)

def readback_status(health,now,scope):
    status=health['status'];actual='UNKNOWN'
    if status in {'HEALTHY','PENDING_SOURCE'}:
        value=health.get('financial_trading_proven')
        if type(value) is bool:actual=value
    if status=='HEALTHY':
        label=('ENTRY_PERIOD_EXPIRED_CUSTODY_RETAINED' if now>=scope['valid_until_ms']
            else 'OWNER_ARMED_FUTURE' if now<scope['valid_from_ms'] else 'LIVE_ARMED_HEALTHY')
    else:label='OWNER_ARMED_SOURCE_PENDING' if status=='PENDING_SOURCE' else 'OWNER_ACTION_REQUIRED'
    return label,actual

def key_lifetime(metadata,exact_vps_ip):
    expiry=metadata.get('expiredAt');millis=None
    if isinstance(expiry,str) and expiry:
        dt=datetime.fromisoformat(expiry.replace('Z','+00:00'))
        need(dt.tzinfo is not None,'KEY_EXPIRY_TIMEZONE_UNKNOWN')
        millis=int(dt.timestamp()*1000)
    return millis,(exact_vps_ip is True and metadata.get('deadlineDay')==-2 and millis==0)

class SystemOps:
    """Existing helpers and GET sources only; unit mutation is apply-only."""
    def __init__(self,e):
        self.e=e;folder=e['folder'];p=e['packet']
        spec=importlib.util.spec_from_file_location('pinned_handoff_base',folder/'base_ops.py')
        need(sha(read(folder/'base_ops.py'))==p['files']['base_ops.py']==BASE_HELPER_PIN,'BASE_HELPER_PIN')
        specraw=read(HEALTH_SPEC);need(sha(specraw)==HEALTH_SPEC_PIN,'EXISTING_OBSERVER_SPEC')
        need(json.loads(specraw)['observer_lock']==p['observer_lock'],'ORIGINAL_OBSERVER_LOCK')
        self.base=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.base)
    def packet_pins(self,e):
        for name,h in e['packet']['files'].items():need(sha(read(e['folder']/name))==h,'PACKET_DRIFT_DURING_HANDOFF')
    def clock(self):return time.time_ns()//1000000
    def observer_lock(self,e):return file_lock(e['packet']['observer_lock'],e['packet']['observer_lock_inode'])
    def account_lock(self,e):return file_lock(e['old_scope']['account_lock_path'],e['old_scope']['account_lock_inode'])
    def _candidate(self,e):
        root=safe(e['packet']['candidate_root']);raw=read(root/'verification-source-hashes.json')
        need(sha(raw)==e['packet']['source_manifest_sha256']==SOURCE_PIN,'CANDIDATE_MANIFEST')
        pins=json.loads(raw)
        for name,h in pins.items():
            need(not Path(name).is_absolute() and '..' not in Path(name).parts and sha(read(root/'app'/name))==h,'CANDIDATE_SOURCE_PIN')
        need(set(e['new_config']['source_files'])==set(e['before']['config']['source_files'])
            and all(pins.get(k)==v for k,v in e['new_config']['source_files'].items()),'RUNTIME_SOURCE_CLOSURE')
        sys.path.insert(0,str(root/'app'))
    def verify(self,e,*,stopped=False):
        self.packet_pins(e);self._candidate(e);b=e['before'];c=b['config'];folder=e['folder'];p=e['packet']
        need(read(OLD_CONFIG)==encode(c) and json.loads(read(Path(e['old_scope']['root'])/'owner-scope.json'))==e['old_scope'],'PREDECESSOR_DRIFT')
        need(read(UNIT)==read(folder/'old-owner.service') and read(p['wrapper_path'])==read(folder/'old-wrapper.py'),'OLD_UNIT_WRAPPER_DRIFT')
        for name,h in c['source_files'].items():need(sha(read(Path(c['app_root'])/name))==h,'OLD_SOURCE_DRIFT')
        for name,h in c['guard_source_files'].items():need(sha(read(name))==h,'OLD_GUARD_DRIFT')
        need(sha(subprocess.check_output(['crontab','-l']))==c['original_cron_sha256'],'CRON_DRIFT')
        for unit,h in p['preserved_units'].items():need(sha(read(Path('/etc/systemd/system')/unit))==h,'PRESERVED_UNIT_DRIFT')
        for unit,h in c['inhibitors'].items():
            st=self.base.state(unit);need(st['MainPID']=='0' and st['ActiveState'] in {'inactive','failed'},'COMPETING_OWNER')
            need(sha(read(Path('/etc/systemd/system')/(unit+'.d/90-kity-micro-inhibit.conf')))==h,'INHIBITOR_DRIFT')
        need(safe(c['inhibit_marker']).is_file(),'INHIBIT_MARKER')
        st=self.base.state(UNIT.name)
        need(all(not st.get(k) for k in ('DropInPaths','ExecStop','ExecStopPost','Job')),'UNKNOWN_OWNER_OVERRIDE')
        if stopped:self.base.quiet_state(st)
        else:need(st['ActiveState']=='active' and int(st['MainPID'])==p['old_owner_pid']
            and self.base.held(e['old_scope']['account_lock_path'],st['MainPID']),'OLD_OWNER_LEASE')
        oldroot=Path(e['old_scope']['root'])
        for name,h in p['old_money_anchors'].items():need('/' not in name and sha(read(oldroot/name))==h,'OLD_MONEY_ANCHOR_DRIFT')
        need((oldroot/'send-barriers').stat().st_ino==p['old_barrier_inode'],'OLD_BARRIER_IDENTITY')
        need(json.loads(read(oldroot/'owner-go.json'))==dict(schema='PUMP4_EXACT_ACCOUNT_OWNER_GO_V1',
            scope_sha256=OLD_SCOPE_PIN,owner_go_text='GO PUMP4_TINY '+OLD_SCOPE_PIN),'OLD_EXACT_GO')
        need(read(c['original_owner']['path'])==read(folder/'old-original-owner.json'),'OLD_ORIGINAL_REFERENCE_DRIFT')
        need(sha(read(c['credential_source']))==c['credential_source_sha256'],'OLD_CREDENTIAL_SOURCE_DRIFT')
        cred=safe(e['new_config']['credential_source']);need(cred.stat().st_mode&0o777==0o600
            and sha(read(cred))==e['new_config']['credential_source_sha256'],'NEW_CREDENTIAL_CUSTODY')

        data_state=self.base.state("pump4-data-supervisor.service")
        need(data_state["ActiveState"]=="active" and self.base.held(Path(c["data_source"]["root"])/"data-writer.lock",data_state["MainPID"]),"SOLE_ACTIVE_DATA_WRITER_REQUIRED")
        from research_lab.pump4_runtime_sources_v1 import TrustedSources
        from research_lab.alpaca_dynamic_v1 import digest as source_digest
        obj=object.__new__(TrustedSources);obj.config=e['new_config'];obj.config_sha=source_digest(obj.config)
        data=obj._data();obj._candidate_files(data,self.clock())
        need(obj.candidate_scan['coverage_complete'] is True,'CURRENT_SOURCE_PENDING_OR_FAILED')
    def snapshot(self,e):
        from types import SimpleNamespace
        from concurrent.futures import ThreadPoolExecutor
        from research_lab.kity_micro_physical_owner_v1 import load_bound_credentials
        from research_lab.kity_micro_transport_v1 import BybitReadTransport,wire_get
        from research_lab.pump4_runtime_sources_v1 import TrustedSources
        from research_lab.pump4_bybit_sources_v1 import flat_account
        from research_lab.pump4_account_adapter_v1 import time_windows
        c=e['new_config'];key,secret=load_bound_credentials(c);meta={};calls=[]
        def wire(method,url,headers,data,timeout):
            need(method=='GET' and data is None,'GET_ONLY');calls.append(1)
            status,raw=wire_get(method,url,headers,None,timeout)
            if url.split('?')[0]=='https://api.bybit.com/v5/user/query-api':
                body=json.loads(raw);meta['exact_ip']=body.get('result',{}).get('ips')==['64.226.73.119']
            return status,raw
        reader=BybitReadTransport(key,secret,wire=wire,symbols=('BTCUSDT',))
        api=reader.get('/v5/user/query-api',{});ar=reader.result(api)
        need(type(ar.get('readOnly')) is int and ar['readOnly']==0 and {'Order','Position'}<=set(ar.get('permissions',{}).get('ContractTrade',[]))
            and not ar.get('permissions',{}).get('Wallet'),'KEY_TRADE_PERMISSIONS')
        uid=digest(dict(userID=str(ar['userID']),parentUid=str(ar['parentUid']),isMaster=ar['isMaster']))
        end=self.clock();windows=time_windows(e['old_scope']['valid_from_ms'],end)
        tasks=[(name,path,dict(category='linear',startTime=str(lo),endTime=str(hi),limit=limit,**extra))
            for lo,hi in windows for name,path,limit,extra in (
            ('history','/v5/order/history','50',{}),('executions','/v5/execution/list','100',{}),
            ('transactions','/v5/account/transaction-log','50',dict(accountType='UNIFIED',currency='USDT')))]
        def collect(spec):
            _,path,params=spec;cap=reader.pages(path,params);need(cap.get('complete') is True,'HISTORY_PAGE_INCOMPLETE')
            rows=[x for page in cap['pages'] for x in reader.result(page)['list']];return dict(capture=cap,rows=len(rows))
        with ThreadPoolExecutor(max_workers=6) as pool:history=list(pool.map(collect,tasks))
        out=e['folder']/'get-proof';out.mkdir(mode=0o700,exist_ok=True)
        owner=SimpleNamespace(key=key,secret=secret,root=out,scope=dict(account_fingerprint=c['account_fingerprint']),clock=self.clock)
        src=TrustedSources({},owner,wire=wire);bundle,_=src.flat(metadata_symbol='BTCUSDT')
        now=self.clock();view=flat_account(bundle,expected_fingerprint=c['account_fingerprint'],now_ms=now)
        expiry_ms,indefinite=key_lifetime(ar,meta.get('exact_ip'))
        proof=dict(api=api,history=history,flat_bundle_sha256=digest(bundle));pid=digest(proof)
        once(out/(str(now)+'-'+pid+'.json'),encode(proof))
        return dict(observed_ms=now,flat=True,history_empty=all(x['rows']==0 for x in history),
            available_usdt=view['available_balance'],account_identity_sha256=uid,
            account_fingerprint=reader.account_fingerprint,key_valid_until_ms=expiry_ms,
            key_no_fixed_expiry=indefinite,key_exact_vps_ip=meta.get('exact_ip'),get_requests=len(calls),
            history_cutoff_ms=end,evidence_sha256=pid,terminal_cost_finality_proven=False)
    def stop(self,e):self.base.ctl('stop',UNIT.name);self.base.quiet(UNIT.name)
    def install(self,e):
        self.packet_pins(e);folder=e['folder'];p=e['packet'];unit=read(folder/'new-owner.service')
        cas(p['wrapper_path'],read(folder/'old-wrapper.py'),read(folder/'new-wrapper.py'))
        cas(UNIT,read(folder/'old-owner.service'),unit)
        subprocess.run(['systemd-analyze','verify',str(UNIT)],check=True,capture_output=True,timeout=20)
        self.base.ctl('daemon-reload')
    def start(self,e):self.base.ctl('start',UNIT.name)
    def restore_revoked_old(self,e):
        folder=e['folder'];wrapper=Path(e['packet']['wrapper_path'])
        current=self.base.state(UNIT.name)
        need(current['MainPID']=='0' or int(current['MainPID'])==e['packet']['old_owner_pid'],'UNKNOWN_REPLACEMENT_OWNER_NO_ROLLBACK')
        for path,old,new in ((UNIT,read(folder/'old-owner.service'),read(folder/'new-owner.service')),
            (wrapper,read(folder/'old-wrapper.py'),read(folder/'new-wrapper.py'))):
            raw=read(path);need(raw in (old,new),'ROLLBACK_UNKNOWN_FILE')
            if raw==new:cas(path,new,old)
        self.base.ctl('daemon-reload');st=self.base.state(UNIT.name)
        if st['MainPID']=='0':self.base.quiet_state(st);self.base.ctl('start',UNIT.name)
        else:need(st['ActiveState']=='active' and self.base.held(e['old_scope']['account_lock_path'],st['MainPID']),'ROLLBACK_CUSTODY_UNKNOWN')
    def readback(self,e):
        self.packet_pins(e);folder=e['folder'];need(read(UNIT)==read(folder/'new-owner.service')
            and read(e['packet']['wrapper_path'])==read(folder/'new-wrapper.py'),'NEW_SELECTED_FILES')
        spec=importlib.util.spec_from_file_location('pinned_new_health',folder/'health.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        deadline=time.monotonic()+45
        while True:
            state=self.base.state(UNIT.name)
            need(state['ActiveState'] not in {'failed','inactive'},'NEW_OWNER_NOT_RUNNING')
            try:
                receipt=mod.read(mod.latest_receipt(Path(e['new_scope']['root'])))
                ready=(receipt['pid']==int(state['MainPID']) and receipt['scope_sha256']==e['new_scope_sha256']
                    and receipt['runner_config_sha256']==e['new_config_sha256'] and receipt['mode']=='OWNER_TINY_LIVE')
            except (OSError,KeyError,ValueError):ready=False
            if ready:break
            need(time.monotonic()<deadline,'NEW_OWNER_RECEIPT_UNKNOWN_READBACK_ONLY')
            time.sleep(.2)
        result=mod.observe();now=self.clock();label,actual=readback_status(result,now,e['new_scope'])
        return dict(schema='PUMP4_SOURCE_HANDOFF_READBACK_V1',observed_ms=now,status=label,
            health=result,scope_sha256=e['new_scope_sha256'],config_sha256=e['new_config_sha256'],
            actual_entry_executed=actual,broker_writes=None)

def main(argv=None):
    os.umask(0o077);ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--packet',type=Path);ap.add_argument('--packet-sha256');ap.add_argument('--owner-go-text')
    modes=ap.add_mutually_exclusive_group();modes.add_argument('--apply-once',action='store_true');modes.add_argument('--verify-only',action='store_true');modes.add_argument('--readback',action='store_true');modes.add_argument('--revoke-entry',action='store_true')
    a=ap.parse_args(argv)
    if not any((a.apply_once,a.verify_only,a.readback,a.revoke_entry)):
        print(json.dumps(dict(status='NO_REQUESTS_NO_AUTHORITY',broker_writes=0)));return 0
    need(a.packet is not None and a.packet_sha256,'EXACT_PACKET_REQUIRED')
    if a.apply_once:need(a.owner_go_text=='GO PUMP4_SOURCE_REPAIR_PACKET '+a.packet_sha256,'EXACT_NEW_OWNER_GO_REQUIRED')
    if a.revoke_entry:need(a.owner_go_text=='REVOKE PUMP4_SOURCE_REPAIR_PACKET '+a.packet_sha256,'EXACT_REVOKE_REQUIRED')
    e=load_packet(a.packet,a.packet_sha256)
    if a.apply_once:need(e['acceptance_ready'],'INDEPENDENT_AND_OFFLINE_ACCEPTANCE_REQUIRED')
    ops=SystemOps(e);folder=e['folder']
    if a.apply_once:result=apply_once(folder,a.packet_sha256,e,ops,owner_go_text=a.owner_go_text)
    elif a.revoke_entry:result=revoke_entry(folder,a.packet_sha256,e,ops,owner_go_text=a.owner_go_text)
    elif a.readback:result=ops.readback(e)
    else:
        need(not os.path.lexists(folder/'handoff-claim.json') and not os.path.lexists(e['new_scope']['root']),'ATTEMPT_ALREADY_CLAIMED_NO_RETRY')
        ops.verify(e);unused(e['old_scope']['root']);snapshot=ops.snapshot(e)
        try:check_snapshot(snapshot,e,ops.clock())
        except HandoffError as exc:
            print(json.dumps(dict(status='BLOCKED_PREFLIGHT',reason=str(exc),observed_ms=ops.clock(),snapshot=snapshot,broker_writes=0)))
            return 2
        need(e['acceptance_ready'],'INDEPENDENT_AND_OFFLINE_ACCEPTANCE_REQUIRED')
        result=dict(status='READY_FOR_OWNER_GO_PREFLIGHT',observed_ms=ops.clock(),snapshot=snapshot,broker_writes=0)
    print(json.dumps(result));return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(dict(status='BLOCKED_OR_UNKNOWN_DO_NOT_REPEAT',reason=str(exc) if isinstance(exc,HandoffError) else type(exc).__name__,broker_writes=None)));raise SystemExit(2)
