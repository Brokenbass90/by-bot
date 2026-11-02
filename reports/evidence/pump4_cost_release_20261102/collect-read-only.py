"""Bounded real-account GET capture. No owner, lease, financial journal or send.

Run only from the separately manifested unselected candidate. Never repin drift.
Capture/replay may prove flat-source compatibility, not a real cost lifecycle.
"""
import hashlib,importlib.util,json,os,subprocess,sys,time,uuid
from pathlib import Path
from types import SimpleNamespace

PACKET=Path('/opt/bybot-research/pump4-current-hour-repair-20261101/owner-packet-v6-new-key')
PACKET_SHA='3aa49421dfb628dc6703986cc9c988f394d0fa94e4955f496db1a3a39f8fec7b'
HANDOFF_SHA='d8a3003d8cbfe254ee81a45fb477b56b1895969b5ba309358834e687bd8613ba'
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from research_lab.kity_oct15_deadline_v1 import stable_bytes,decode
from research_lab.kity_micro_physical_owner_v1 import load_bound_credentials,publish
from research_lab.pump4_runtime_sources_v1 import TrustedSources
from research_lab.pump4_serial_source_supervisor_v1 import audit_capture


def need(ok,why):
    if not ok:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def clock():return time.time_ns()//1000000

def state():
    raw=subprocess.check_output(['systemctl','show','pump4-execution-owner.service','-p','MainPID','-p','ActiveState','-p','NRestarts'],text=True)
    return dict(line.split('=',1) for line in raw.splitlines())

def verify(e):
    p=e['packet'];s=e['new_scope'];c=e['new_config']
    need(state()==dict(MainPID='3669955',ActiveState='active',NRestarts='0'),'LIVE_OWNER_CHANGED')
    need(h.read(Path('/etc/systemd/system/pump4-execution-owner.service'))==h.read(PACKET/'new-owner.service'),'SELECTED_UNIT_DRIFT')
    need(h.read(p['wrapper_path'])==h.read(PACKET/'new-wrapper.py'),'SELECTED_WRAPPER_DRIFT')
    for unit,pin in p['preserved_units'].items():need(sha(h.read(Path('/etc/systemd/system')/unit))==pin,'PRESERVED_UNIT_DRIFT')
    manifest=Path(p['candidate_root'])/'verification-source-hashes.json'
    raw=h.read(manifest);need(sha(raw)==p['source_manifest_sha256'],'LIVE_SOURCE_MANIFEST_DRIFT')
    for name,pin in decode(raw).items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts and sha(h.read(Path(c['app_root'])/name))==pin,'LIVE_SOURCE_DRIFT')
    lock=Path(s['account_lock_path']);st=lock.stat();need(st.st_ino==s['account_lock_inode']==818853,'ORIGINAL_LOCK_CHANGED')
    owned=[]
    for line in Path('/proc/locks').read_text().splitlines():
        bits=line.split()
        if len(bits)>5 and bits[4]=='3669955':
            a=bits[5].split(':')
            if len(a)==3 and int(a[0],16)==os.major(st.st_dev) and int(a[1],16)==os.minor(st.st_dev) and int(a[2])==st.st_ino:owned.append(line)
    need(len(owned)==1,'ORIGINAL_LOCK_NOT_HELD_BY_SOLE_OWNER')
    h.unused(Path(s['root']))
    need(h.digest(decode(h.read(Path(s['root'])/'owner-scope.json')))==e['new_scope_sha256'],'LIVE_SCOPE_DRIFT')
    return dict(pid=3669955,account_lock_inode=818853,selected_scope_sha256=e['new_scope_sha256'],
        selected_config_sha256=e['new_config_sha256'],live_source_files=len(decode(raw)),preserved_units=True,
        no_admission_or_money_history=True,observed_ms=clock())


if __name__=='__main__':
    os.umask(0o077)
    # Own package closure checked before importing this script; verify again here.
    stage=ROOT.parent;manifest=stage/'verification-source-hashes.json'
    raw=stable_bytes(manifest);need(sha(raw)==sys.argv[1],'OFF_SOURCE_MANIFEST_PIN')
    for name,pin in decode(raw).items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts and sha(stable_bytes(ROOT/name))==pin,'OFF_SOURCE_DRIFT')
    need(sha(stable_bytes(PACKET/'handoff.py'))==HANDOFF_SHA,'LIVE_HANDOFF_PIN')
    spec=importlib.util.spec_from_file_location('accepted_live_handoff',PACKET/'handoff.py')
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    e=h.load_packet(PACKET/'packet.json',PACKET_SHA)
    before=verify(e)
    out=stage/'runtime'/('capture-'+str(clock())+'-'+uuid.uuid4().hex)
    out.mkdir(parents=True,mode=0o700,exist_ok=False)
    key,secret=load_bound_credentials(e['new_config'])
    owner=SimpleNamespace(root=out,scope=e['new_scope'],key=key,secret=secret,clock=clock)
    p=TrustedSources(e['new_config'],owner)
    meta=p.reader.get('/v5/user/query-api',{});identity=p.reader.result(meta)
    need(h.digest(dict(userID=str(identity['userID']),parentUid=str(identity['parentUid']),isMaster=identity['isMaster']))==e['old_account_identity_sha256'],'DIFFERENT_ACCOUNT_UID')
    bundle,_=p._capture(None,e['new_scope']['valid_from_ms'],custody=True,metadata_symbol='BTCUSDT')
    closed=p.serial_closed_pnl(bundle['history_start_ms'],bundle['history_end_ms'])
    observed=clock();after=verify(e)
    value=dict(schema='PUMP4_SERIAL_READ_ONLY_CAPTURE_V1',bundle=bundle,closed_pnl_sources=closed,
        registry=[],account_fingerprint=p.reader.account_fingerprint,source_observed_ms=observed,
        selected_packet_sha256=PACKET_SHA,collector_sha256=sha(stable_bytes(__file__)),
        physical_before=before,physical_after=after,broker_writes=0)
    file=out/'capture.json';publish(file,value)
    result=audit_capture(file,sha(stable_bytes(file)),out/'audit-receipt.json')
    print(json.dumps(dict(result,capture_path=str(file),capture_receipt_path=str(out/'audit-receipt.json'),
        live_preserved=after,source_requests=1+sum(len(g.get('pages',[g])) for g in bundle['captures'].values())+
        sum(len(g['pages']) for w in bundle['history_windows'] for g in w['groups'].values())+
        sum(len(w['group']['pages']) for w in closed)),sort_keys=True))
