"""One bounded ORDERS_OFF handoff. No broker POST or owner GO path."""
from pathlib import Path
import fcntl,hashlib,json,os,shutil,subprocess,sys,time,re

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def digest(v):return sha(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
def verify_candidate(candidate,material,manifest_pin):
    raw=safe(candidate/'manifest.json').read_bytes();assert sha(raw)==manifest_pin,'MANIFEST_PIN'
    m=json.loads(raw);assert m['material_sha256']==material==digest(dict(files=m['files'],driver_sha256=m['acceptance_driver_sha256'])),'MATERIAL_PIN'
    assert sha(safe(candidate/'accept.py').read_bytes())==m['acceptance_driver_sha256'],'DRIVER_PIN'
    for name,h in m['files'].items():
        p=safe(candidate/'app'/name);assert p.is_relative_to(candidate/'app') and sha(p.read_bytes())==h,'CANDIDATE_DRIFT'
def safe(p):
    p=Path(p).absolute()
    assert '..' not in p.parts and not any(x.is_symlink() for x in (p,*p.parents)),'UNSAFE_PATH'
    return p
def tree(root):
    root=safe(root);out={}
    for p in sorted(root.rglob('*')):
        safe(p)
        if p.is_file():
            assert p.stat().st_nlink==1,'HARDLINK'
            out[str(p.relative_to(root))]=sha(p.read_bytes())
    return out
def once(p,raw):
    p=safe(p);p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    d=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(d)
    finally:os.close(d)
def replace(p,old_hash,raw):
    p=safe(p);assert sha(p.read_bytes())==old_hash,'CAS_DRIFT'
    stage=p.with_name(p.name+'.pump4-stream.tmp');once(stage,raw)
    os.chmod(stage,p.stat().st_mode & 0o777);os.replace(stage,p)
    d=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(d)
    finally:os.close(d)
def clone_data(old,new,binding):
    before=tree(old);assert not os.path.lexists(new),'TARGET_EXISTS'
    shutil.copytree(old,new,copy_function=shutil.copy2)
    assert tree(old)==tree(new)==before,'COPY_CHANGED'
    replace(Path(new)/'data-binding.json',before['data-binding.json'],binding)
    after=tree(new);assert all(after[n]==h for n,h in before.items() if n!='data-binding.json'),'HISTORY_CHANGED'
    sync_tree(new)
    return before
def sync_tree(root):
    paths=list(root.rglob('*'))
    for p in [x for x in paths if x.is_file()]+sorted([x for x in paths if x.is_dir()],key=lambda p:len(p.parts),reverse=True)+[root,root.parent]:
        fd=os.open(safe(p),os.O_RDONLY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
def prepare_runtime(root):
    safe(root);assert not os.path.lexists(root),'RUNTIME_ALREADY_EXISTS'
    root.mkdir(parents=True,mode=0o700)
    sync_tree(root)
def empty_off(root):
    root=safe(root)
    for n in ('owner-go.json','admitted-lifecycle.json','entry-revoked.json','risk.jsonl'):
        assert not os.path.lexists(root/n),'FINANCIAL_HISTORY:'+n
    for n in ('flows','send-barriers','supervisor/attempts'):
        assert not any((root/n).rglob('*')),'FINANCIAL_HISTORY:'+n
def copy_forward(new,old):
    old_files=tree(old);new_files=tree(new);skip={'data-binding.json','data-writer.lock'}
    # Validate the entire previous history before changing even one file.
    for name,h in old_files.items():
        if name in skip:continue
        assert name in new_files,'MISSING_HISTORY'
        if h!=new_files[name]:
            assert name.endswith('.jsonl') and (new/name).read_bytes().startswith((old/name).read_bytes()),'HISTORY_CONFLICT'
    for name,h in new_files.items():
        if name in skip:continue
        if name not in old_files:once(old/name,(new/name).read_bytes())
        elif old_files[name]!=h:
            prior=(old/name).read_bytes();raw=(new/name).read_bytes();assert raw.startswith(prior)
            replace(old/name,sha(prior),raw)
    after=tree(old)
    assert all(after[n]==h for n,h in new_files.items() if n not in skip),'FORWARD_COPY_VERIFY'
def ctl(*a):return subprocess.check_output(['systemctl',*a],text=True,timeout=30)
def state(u):return dict(x.split('=',1) for x in ctl('show',u,'--property=ActiveState,SubState,MainPID,DropInPaths,ExecStop,ExecStopPost,Job,NRestarts').splitlines() if '=' in x)
def quiet(u):
    quiet_state(state(u))
def quiet_state(s):
    assert s['MainPID']=='0' and s['ActiveState'] in ('inactive','failed'),'NOT_QUIET'
    assert all(not s.get(k) for k in ('Job','ExecStop','ExecStopPost','DropInPaths')),'UNKNOWN_WORKER_OVERRIDE'
def held(lock,pid):
    st=Path(lock).stat();key=f'{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}'
    return any(len(r)==8 and r[1:4]==['FLOCK','ADVISORY','WRITE'] and r[4:]==[str(pid),key,'0','EOF'] for r in (x.split() for x in Path('/proc/locks').read_text().splitlines()))
def resume_timer(timer,fds):
    while fds:os.close(fds.pop())
    ctl('start',timer)
def restore_owner_files(unit,wrapper,old_unit,new_unit,old_wrapper,new_wrapper):
    u=unit.read_bytes();w=wrapper.read_bytes()
    assert u in (old_unit,new_unit) and w in (old_wrapper,new_wrapper),'UNKNOWN_PARTIAL_OWNER'
    if w==new_wrapper:replace(wrapper,sha(new_wrapper),old_wrapper)
    if u==new_unit:replace(unit,sha(new_unit),old_unit)
def rollback_capture_safe(root,now_ms):
    hour=str(now_ms//3600000*3600000)+'.json'
    assert not (safe(root)/'capture-attempts'/hour).exists() or (safe(root)/'capture-complete'/hour).exists(),'INCOMPLETE_PROCESS_HOUR_WAIT_NEXT_HOUR_BEFORE_OLD_CODE_ROLLBACK'

def execute(folder,mode):
    folder=safe(folder);before=json.loads((folder/'before.json').read_bytes());c=before['config'];scope=before['scope']
    base=Path('/opt/bybot-research/pump4-server-orders-off-20261023')
    candidate=base/'candidate-8c00885cf6329bae';app=candidate/'app'
    old=safe(c['data_source']['root']);new=app/'.private/pump4-supervisor-v1'
    data_unit=Path('/etc/systemd/system/pump4-data-supervisor.service')
    owner_unit=Path('/etc/systemd/system/pump4-execution-owner.service')
    timer='pump4-data-supervisor.timer';owner='pump4-execution-owner.service'
    lock=Path(scope['account_lock_path'])
    verify_candidate(candidate,'8c00885cf6329bae8cbcaf3d186f8c37c9c980bb82805a3397152355184af079',
        '9d9c47995a7b07ce62b043dbaff79665e4e1c39e6f5200354f3d8a2f4c0e1306')
    sys.path.insert(0,str(app))
    from research_lab.pump4_selected_runner_v1 import source_pins
    from research_lab.pump4_supervisor_v1 import Supervisor
    def guards():
        assert all(sha(Path(p).read_bytes())==h for p,h in c['guard_source_files'].items()),'GUARD_DRIFT'
        assert all(sha((Path(c['app_root'])/p).read_bytes())==h for p,h in c['source_files'].items()),'OWNER_SOURCE_DRIFT'
        assert sha(subprocess.check_output(['crontab','-l']))==c['original_cron_sha256'],'CRON_DRIFT'
        assert lock.stat().st_ino==scope['account_lock_inode']==818853 and lock.stat().st_nlink==1,'LOCK_DRIFT'
        assert sha(Path(before['old_config_path']).read_bytes())==sha(encode(c)),'CONFIG_DRIFT'
        for name,h in c['inhibitors'].items():
            s=state(name);assert s['MainPID']=='0' and s['ActiveState'] in ('inactive','failed') and not s.get('Job')
            assert sha(Path('/etc/systemd/system',name+'.d/90-kity-micro-inhibit.conf').read_bytes())==h
        empty_off(scope['root'])
        acceptance=json.loads((candidate/'acceptance.json').read_bytes());assert acceptance['status']=='PASS'
        manifest=json.loads((candidate/'manifest.json').read_bytes())
        assert manifest['material_sha256']=='8c00885cf6329bae8cbcaf3d186f8c37c9c980bb82805a3397152355184af079'
        assert all(sha((app/n).read_bytes())==h for n,h in manifest['files'].items()),'CANDIDATE_DRIFT'
    if mode=='data':
        guards();assert owner_unit.read_text()==before['units'][owner]
        oscope=state(owner);assert oscope['ActiveState']=='active' and held(lock,oscope['MainPID'])
        assert oscope['MainPID']=='2904935' and oscope['NRestarts']=='0' and all(not oscope.get(k) for k in ('DropInPaths','ExecStop','ExecStopPost','Job')),'OWNER_STATE_DRIFT'
        quiet('pump4-data-supervisor.service')
        assert data_unit.read_text()==before['units'][data_unit.name]
        assert Path('/etc/systemd/system',timer).read_text()==before['units'][timer] and not state(timer).get('DropInPaths'),'TIMER_DRIFT'
        assert ctl('is-active',timer).strip()=='active'
        assert shutil.disk_usage(candidate).free>2*sum(p.stat().st_size for p in old.rglob('*') if p.is_file())+3221225472,'DISK_RESERVE'
        once(folder/'data-operation-claim.json',encode(dict(mode=mode,started_ms=time.time_ns()//1000000)))
        ctl('stop',timer);quiet('pump4-data-supervisor.service')
        fd=os.open(old/'data-writer.lock',os.O_RDWR|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            bound=dict(before['data_binding'],source_files=source_pins())
            history=clone_data(old,new,encode(bound))
            Supervisor(new) # verify constructor accepts exact new binding
            assert tree(old)==history,'OLD_HISTORY_CHANGED'
            text=before['units'][data_unit.name].replace(str(old.parent.parent),str(app)).replace('CPUQuota=100%','CPUQuota=200%')
            once(folder/'new-data.service',text.encode());once(folder/'data-history-before.json',encode(history))
            replace(data_unit,sha(before['units'][data_unit.name].encode()),text.encode())
            subprocess.run(['systemd-analyze','verify',str(data_unit)],check=True,capture_output=True,timeout=20)
            ctl('daemon-reload');ctl('start',timer)
            result=dict(status='STREAM_DATA_SELECTED',data_root=str(new),binding_sha256=sha((new/'data-binding.json').read_bytes()),preserved_files=len(history)-1,original_lock_inode=lock.stat().st_ino,owner_pid=oscope['MainPID'],broker_writes=0,owner_go_created=False,observed_ms=time.time_ns()//1000000)
            once(folder/'data-applied.json',encode(result));print(json.dumps(result))
        finally:os.close(fd)
    elif mode=='owner':
        guards();assert owner_unit.read_text()==before['units'][owner]
        old_state=state(owner);assert old_state['ActiveState']=='active' and held(lock,old_state['MainPID'])
        assert not old_state.get('DropInPaths') and not old_state.get('ExecStop') and not old_state.get('ExecStopPost') and not old_state.get('Job')
        assert data_unit.read_bytes()==(folder/'new-data.service').read_bytes()
        info=folder/'owner-review-stream-v1';info.mkdir(mode=0o700)
        runtime=candidate/'runtime/financial-orders-off-stream-v1';assert not runtime.exists()
        cc=json.loads(json.dumps(c));ss=json.loads(json.dumps(scope))
        cc['custody_runtime_root']=ss['root']=str(runtime)
        cc['data_source']=dict(root=str(new),binding=dict(path=str(new/'data-binding.json'),sha256=sha((new/'data-binding.json').read_bytes())))
        config_path=info/'runner.json';scope_path=info/'scope.json'
        notify=json.loads(Path(c['notifications']['path']).read_bytes());notify['output_root']=str(runtime/'notifications')
        once(info/'notifications.json',encode(notify));cc['notifications']=dict(path=str(info/'notifications.json'),sha256=sha(encode(notify)))
        health_old=json.loads((folder/'health-before.json').read_bytes())['health']
        health_new=health_old.replace(before['old_config_path'],str(config_path));assert health_new!=health_old
        once(info/'pump4_owner_health_v1.py',health_new.encode())
        legacy=Path(before['old_config_path']).parent/'health-legacy-immutable.py'
        once(info/legacy.name,legacy.read_bytes())
        wrapper=json.loads((folder/'wrapper-before.json').read_bytes());wp=Path(wrapper['path'])
        new_wrapper=f"from pathlib import Path\nimport hashlib,runpy\np=Path({str(info/'pump4_owner_health_v1.py')!r})\nassert hashlib.sha256(p.read_bytes()).hexdigest()=={sha(health_new.encode())!r}\nrunpy.run_path(str(p),run_name='__main__')\n".encode()
        assert wp.read_text()==wrapper['text']
        cc['guard_source_files'][str(wp)]=sha(new_wrapper)
        for p in (info/'pump4_owner_health_v1.py',info/'notifications.json',new/'data-binding.json'):
            cc['guard_source_files'][str(p)]=sha(p.read_bytes())
        text=before['units'][owner].replace(before['old_config_path'],str(config_path)).replace(scope['root'],str(runtime))
        template=re.sub(r'--config-sha256 [0-9a-f]{64}','--config-sha256 <PIN>',text)
        cc['unit_template_sha256']=sha(template.encode());ss['runner_config_sha256']=digest({k:v for k,v in cc.items() if k!='authority'})
        once(scope_path,encode(ss));cc['authority']=dict(path=str(scope_path),sha256=sha(encode(ss)))
        once(config_path,encode(cc));config_pin=sha(encode(cc))
        text=re.sub(r'--config-sha256 [0-9a-f]{64}','--config-sha256 '+config_pin,text)
        once(info/'pump4-execution-owner.service',text.encode());once(info/'wrapper-new.py',new_wrapper)
        # GET-only preflight with original credential loader. No owner constructor.
        from types import SimpleNamespace
        from research_lab.kity_micro_physical_owner_v1 import load_bound_credentials,AccountLease
        from research_lab.pump4_runtime_sources_v1 import TrustedSources
        from research_lab.pump4_bybit_sources_v1 import flat_account
        key,secret=load_bound_credentials(before['original'])
        caproot=folder/'account-captures';caproot.mkdir(mode=0o700)
        observer=SimpleNamespace(key=key,secret=secret,root=caproot,scope=dict(account_fingerprint=c['account_fingerprint']),clock=lambda:time.time_ns()//1000000)
        src=TrustedSources({},observer)
        def fresh():
            bundle,public=src.flat();now=time.time_ns()//1000000
            v=flat_account(bundle,expected_fingerprint=c['account_fingerprint'],now_ms=now)
            assert v['positions_flat'] and v['open_orders_empty'],'ACCOUNT_NOT_FLAT'
            return dict(observed_ms=now,source_ms=v['source_ms'],positions_flat=True,open_orders_empty=True,bundle_sha256=digest(bundle))
        first=fresh();guards();empty_off(runtime)
        assert time.time_ns()//1000000-first['observed_ms']<5000,'PREFLIGHT_EXPIRED'
        spec=json.loads(Path('/opt/bybot-research/kity-micro-owner-20261015/monitor-v1/spec.json').read_bytes())
        fd=os.open(spec['observer_lock'],os.O_RDONLY|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            once(folder/'owner-operation-claim.json',encode(dict(mode=mode,started_ms=time.time_ns()//1000000,first=first)))
            ctl('stop',owner);quiet(owner);empty_off(scope['root'])
            lease=AccountLease(lock)
            try:assert lease.inode==818853
            finally:lease.close()
            second=fresh();guards()
            prepare_runtime(runtime)
            replace(wp,sha(wrapper['text'].encode()),new_wrapper)
            replace(owner_unit,sha(before['units'][owner].encode()),text.encode())
            subprocess.run(['systemd-analyze','verify',str(owner_unit)],check=True,capture_output=True,timeout=20)
            ctl('daemon-reload');started=time.time_ns()//1000000;ctl('start',owner)
            deadline=time.monotonic()+30;proof=None
            while time.monotonic()<deadline:
                s=state(owner)
                for p in (runtime/'supervisor/receipts').glob('*.json'):
                    r=json.loads(p.read_bytes())
                    if (r['observed_ms']>=started and str(r['pid'])==s['MainPID'] and r['scope_sha256']==digest(ss)
                        and r['runner_config_sha256']==config_pin and r['mode']=='ORDERS_OFF' and r['broker_writes']==0
                        and not r['result']['status'].startswith('BLOCKED') and held(lock,s['MainPID'])):proof=r;break
                if proof:break
                if s['ActiveState']=='failed':break
                time.sleep(.2)
            assert proof and state(owner)['NRestarts']=='0','NEW_OWNER_START_UNPROVEN_NO_AUTORETRY'
            empty_off(scope['root']);empty_off(runtime)
            result=dict(status='STREAM_CONSUMER_ORDERS_OFF_SELECTED',config_path=str(config_path),config_sha256=config_pin,
                scope_sha256=digest(ss),old_root=scope['root'],new_root=str(runtime),original_lock_inode=lock.stat().st_ino,
                new_pid=proof['pid'],source_result=proof['result'],fresh_flat_before=first,fresh_flat_stopped=second,
                broker_writes=0,owner_go_created=False,observed_ms=time.time_ns()//1000000)
            once(folder/'owner-applied.json',encode(result));print(json.dumps(result))
        finally:os.close(fd)
    elif mode=='rollback':
        # Reconcile and run explicitly, never as an exception handler or auto-retry.
        rollback_capture_safe(new,time.time_ns()//1000000)
        info=folder/'owner-review-stream-v1';wrapper=json.loads((folder/'wrapper-before.json').read_bytes());wp=Path(wrapper['path'])
        empty_off(scope['root']);newscope=None
        if (info/'pump4-execution-owner.service').exists() and owner_unit.read_bytes()==(info/'pump4-execution-owner.service').read_bytes():
            newscope=json.loads((info/'scope.json').read_bytes());empty_off(newscope['root'])
            assert owner_unit.read_bytes()==(info/'pump4-execution-owner.service').read_bytes()
        else:assert owner_unit.read_text()==before['units'][owner],'UNKNOWN_PARTIAL_OWNER_RECONCILE'
        old_wrapper=wrapper['text'].encode()
        new_wrapper=(info/'wrapper-new.py').read_bytes() if (info/'wrapper-new.py').exists() else old_wrapper
        wrapper_changed=wp.read_bytes()==new_wrapper and new_wrapper!=old_wrapper
        assert wp.read_bytes() in (old_wrapper,new_wrapper),'UNKNOWN_PARTIAL_WRAPPER_RECONCILE'
        if wrapper_changed and newscope is None:quiet(owner)
        assert data_unit.read_bytes()==(folder/'new-data.service').read_bytes()
        once(folder/'rollback-operation-claim.json',encode(dict(started_ms=time.time_ns()//1000000)))
        ctl('stop',timer);ctl('stop','pump4-data-supervisor.service');quiet('pump4-data-supervisor.service')
        if newscope:ctl('stop',owner);quiet(owner);empty_off(newscope['root'])
        fds=[]
        try:
            for root in (old,new):
                fd=os.open(root/'data-writer.lock',os.O_RDWR|os.O_NOFOLLOW);fds.append(fd);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            copy_forward(new,old)
            replace(data_unit,sha((folder/'new-data.service').read_bytes()),before['units'][data_unit.name].encode())
            if newscope or wrapper_changed:
                restore_owner_files(owner_unit,wp,before['units'][owner].encode(),(info/'pump4-execution-owner.service').read_bytes(),old_wrapper,new_wrapper)
            guards();ctl('daemon-reload')
            if newscope or wrapper_changed:ctl('start',owner)
            resume_timer(timer,fds)
            result=dict(status='ROLLED_BACK_WITH_DATA_FORWARD',preserved_candidate_root=str(new),broker_writes=0,original_lock_inode=lock.stat().st_ino)
            once(folder/'rollback-applied.json',encode(result));print(json.dumps(result))
        finally:
            for fd in fds:os.close(fd)
    else:raise ValueError(mode)

if __name__=='__main__':execute(Path(sys.argv[1]),sys.argv[2])
