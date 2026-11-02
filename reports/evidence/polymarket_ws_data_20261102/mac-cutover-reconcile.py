"""Finish the spent DATA cutover after screen exited but exact children survived."""
import fcntl,hashlib,json,os,runpy,signal,stat,subprocess,time
from pathlib import Path
ROOT=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824')
P=ROOT/'.private/poly_ws_data_20261102'
def need(ok,why):
    if not ok:raise ValueError('POLY_RECONCILE_'+why)
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    prep=json.loads((P/'mac-prepared-response.json').read_bytes());c=json.loads(Path(prep['config']).read_bytes())
    need(sha(Path(prep['config']).read_bytes())==prep['config_sha256'] and sha(Path(prep['plist']).read_bytes())==prep['plist_sha256'],'PREPARED_DRIFT')
    helper=Path(prep['mac_cutover_script']);need(sha(helper.read_bytes())=='8122dc1802467b04cad5dd6b665d2a31a43e6330a046abef793af3ceae44fd57','HELPER_DRIFT')
    h=runpy.run_path(str(helper));claim=json.loads((P/'mac-cutover-proof.claim.json').read_bytes());need(not Path(prep['proof']).exists(),'READBACK_ONLY')
    mac=Path(c['mac_root']);survivors=[]
    for old in claim['old']:
        need(h['processes'](old['script'])==[old['pid']],'EXACT_SURVIVOR_CHANGED')
        need(sha((mac/'research_lab'/old['script']).read_bytes())==c['original_source_pins'][old['script']],'ORIGINAL_SOURCE_DRIFT')
        cwd=subprocess.check_output(['lsof','-a','-p',str(old['pid']),'-d','cwd','-Fn'],text=True,stderr=subprocess.DEVNULL)
        need('n'+str(mac) in cwd.splitlines(),'SURVIVOR_CWD');survivors.append(old['pid'])
    h['once'](P/'mac-screen-child-reconciliation-claim.json',dict(observed_ms=time.time_ns()//1000000,exact_data_pids=survivors,no_blind_retry=True))
    for pid in survivors:os.kill(pid,signal.SIGTERM)
    deadline=time.monotonic()+15
    while any(h['processes'](x['script']) for x in claim['old']):
        need(time.monotonic()<deadline,'CHILD_EXIT_UNKNOWN');time.sleep(.1)
    subprocess.run(['launchctl','bootstrap','gui/'+str(os.getuid()),prep['plist']],check=True,timeout=15)
    status=Path(c['status_path']);deadline=time.monotonic()+25
    while True:
        if status.exists():
            st=json.loads(status.read_bytes())
            if st.get('locks_held') and time.time_ns()//1000000-st['observed_ms']<30000:os.kill(st['pid'],0);break
        need(time.monotonic()<deadline,'CONSUMER_START_UNKNOWN');time.sleep(.2)
    locks=[]
    for old in claim['locks']:
        path=Path(old['path']);s=path.stat();need(s.st_ino==old['inode'] and stat.S_IMODE(s.st_mode)==old['mode'],'LOCK_CHANGED')
        fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:held=True
            else:held=False
        finally:os.close(fd)
        need(held,'LOCK_NOT_HELD');locks.append(dict(role=path.stem,inode_unchanged=True,mode_unchanged=True,inode=s.st_ino,held_by_selector=True))
    need(not any(h['processes'](x['script']) for x in claim['old']),'PRODUCER_RETURNED')
    proof=dict(schema='POLY_WS_MAC_CUTOVER_PROOF_V1',observed_ms=time.time_ns()//1000000,roles=['sportsws','clobws'],canonical_ws_processes_remaining=0,selector_pid=st['pid'],locks=locks,old=claim['old'],financial_commands=0,screen_children_reconciled=True)
    h['once'](prep['proof'],proof);print(json.dumps(proof))
if __name__=='__main__':main()
