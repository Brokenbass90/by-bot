"""Exact public DATA migration only. No financial API, keys or owner constructors."""
import argparse,hashlib,json,os,re,subprocess,time,uuid
from pathlib import Path

NAMES={'poly-ws-data.slice','poly-ws-data-catalog.service','poly-ws-data-catalog.timer','poly-ws-data-sports.service','poly-ws-data-clob.service'}
FINANCIAL={'pump4-execution-owner.service':'991211ed5db0c9dd163193141179eefe9a266298d9bdde1491dc0904793fb843','alpaca-monthly-owned.service':'9d94467d301cf5f545bee18e50b838623c061b72f46a2fbdd9b7d1991932cc1d','alpaca-monthly-owned.timer':'33a1bd34d3a99a92d8273717f43c49f178309f263656a8f67c44b6cbd55c3bcb','pump4-data-supervisor.service':'cb9de84027ee8d42e72068ce9f66fbbdb6fcf433cc27f435883f52c01d495a35'}

def need(ok,why):
    if not ok:raise ValueError('POLY_DATA_INSTALL_'+why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def now():return time.time_ns()//1000000
def read(path):
    p=Path(path);need(not p.is_symlink() and p.stat().st_size<=8000000,'FILE_CUSTODY');return p.read_bytes()
def once(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def command(*args):return subprocess.check_output(args,text=True,timeout=220)
def state(unit):
    raw=command('systemctl','show',unit,'-p','MainPID','-p','NRestarts','-p','ActiveState','-p','SubState','-p','MemoryCurrent','-p','CPUUsageNSec')
    return dict(x.split('=',1) for x in raw.splitlines())
def snapshot(packet):
    hashes={}
    for unit,pin in dict(FINANCIAL,**packet['preserved_units']).items():
        raw=read(Path('/etc/systemd/system')/unit);need(sha(raw)==pin,'PRESERVED_UNIT_DRIFT:'+unit);hashes[unit]=pin
    pump=state('pump4-execution-owner.service');data=state('pump4-data-supervisor.service')
    need(pump['MainPID']=='3669955' and pump['NRestarts']=='0' and pump['ActiveState']=='active','PUMP_OWNER_CHANGED')
    need(data['MainPID']=='3152955' and data['NRestarts']=='0' and data['ActiveState']=='active','PUMP_DATA_CHANGED')
    lock=Path(packet['original_account_lock']);need(lock.stat().st_ino==818853,'ORIGINAL_LOCK_CHANGED')
    for unit,pid in packet['preserved_pids'].items():need(state(unit)['MainPID']==str(pid),'LIQ_PID_CHANGED')
    return dict(observed_ms=now(),unit_hashes=hashes,pump_pid=3669955,data_pid=3152955,account_lock_inode=818853,preserved_liq_pids=packet['preserved_pids'])
def load(path,pin):
    path=Path(path);need(re.fullmatch(r'/opt/bybot-research/polymarket-ws-data-20261102/candidate-[0-9a-f]{16}/data-packet.json',str(path)) is not None,'PACKET_PATH')
    raw=read(path);need(sha(raw)==pin,'PACKET_PIN');p=json.loads(raw);root=path.parent
    need(p['schema']=='POLY_WS_DATA_INSTALL_PACKET_V1' and set(p['units'])==NAMES,'PACKET_SCOPE')
    manifest=read(root/'verification-source-hashes.json');need(sha(manifest)==p['manifest_sha256'],'MANIFEST_PIN')
    for name,h in json.loads(manifest).items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts and sha(read(root/'app'/name))==h,'SOURCE_PIN')
    for unit,h in p['units'].items():need(sha(read(root/'units'/unit))==h,'UNIT_PIN')
    need(sha(read(root/'spec.json'))==p['spec_sha256'],'SPEC_PIN');return root,p

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--packet',type=Path);ap.add_argument('--packet-sha256');g=ap.add_mutually_exclusive_group();g.add_argument('--install-catalog',action='store_true');g.add_argument('--activate-streams',action='store_true');g.add_argument('--readback',action='store_true');g.add_argument('--stop-new-streams',action='store_true');ap.add_argument('--mac-proof',type=Path);ap.add_argument('--mac-proof-sha256');a=ap.parse_args(argv)
    if not any((a.install_catalog,a.activate_streams,a.readback,a.stop_new_streams)):print(json.dumps(dict(status='DATA_ONLY_NO_COMMANDS')));return 0
    root,p=load(a.packet,a.packet_sha256);before=snapshot(p)
    if a.install_catalog:
        need(not (root/'install-claim.json').exists(),'INSTALL_ALREADY_CLAIMED_READBACK_ONLY')
        for n in NAMES:need(not os.path.lexists(Path('/etc/systemd/system')/n),'UNIT_EXISTS_NO_OVERWRITE')
        once(root/'install-claim.json',dict(started_ms=now(),packet_sha256=a.packet_sha256,before=before))
        for n in sorted(NAMES):
            target=Path('/etc/systemd/system')/n;fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o644)
            with os.fdopen(fd,'wb') as f:f.write(read(root/'units'/n));f.flush();os.fsync(f.fileno())
        command('systemctl','daemon-reload');command('systemctl','start','poly-ws-data-catalog.service');command('systemctl','enable','--now','poly-ws-data-catalog.timer')
        label='CATALOGUE_ONLY_INSTALLED_WS_NOT_STARTED'
    else:
        for n,h in p['units'].items():need(sha(read(Path('/etc/systemd/system')/n))==h,'SELECTED_DATA_UNIT_DRIFT')
        if a.activate_streams:
            need(a.mac_proof and a.mac_proof_sha256 and not (root/'activation-claim.json').exists(),'ACTIVATION_ALREADY_CLAIMED_OR_MAC_PROOF_MISSING')
            raw=read(a.mac_proof);need(sha(raw)==a.mac_proof_sha256,'MAC_PROOF_PIN');proof=json.loads(raw)
            need(proof['schema']=='POLY_WS_MAC_CUTOVER_PROOF_V1' and proof['canonical_ws_processes_remaining']==0
                 and proof['roles']==['sportsws','clobws'] and proof['selector_pid']>0 and all(x['inode_unchanged'] and x['held_by_selector'] for x in proof['locks'])
                 and 0<=now()-proof['observed_ms']<=300000,'MAC_PRODUCER_NOT_PROVEN_STOPPED')
            once(root/'activation-claim.json',dict(started_ms=now(),mac_proof_sha256=a.mac_proof_sha256,before=before))
            command('systemctl','enable','--now','poly-ws-data-sports.service','poly-ws-data-clob.service');label='PUBLIC_DATA_STREAMS_ACTIVATED'
        elif a.stop_new_streams:
            command('systemctl','disable','--now','poly-ws-data-sports.service','poly-ws-data-clob.service');label='ONLY_NEW_DATA_STREAMS_STOPPED'
        else:label='DATA_ONLY_READBACK'
    after=snapshot(p);units={n:state(n) for n in sorted(NAMES) if n.endswith('.service')}
    result=dict(schema='POLY_WS_DATA_INSTALL_RECEIPT_V1',status=label,observed_ms=now(),before=before,after=after,units=units,financial_commands=0,broker_requests=0)
    once(root/('receipt-'+str(now())+'-'+uuid.uuid4().hex+'.json'),result);print(json.dumps(result,sort_keys=True));return 0

if __name__=='__main__':raise SystemExit(main())
