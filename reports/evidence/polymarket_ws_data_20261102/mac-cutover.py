"""One DATA-only Mac producer cutover. Defaults to no commands, no code edits."""
import argparse,fcntl,hashlib,json,os,shlex,signal,stat,subprocess,time
from pathlib import Path

MAC=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28')
LABEL='com.bybot.poly-ws-consumer-20261102'
ROLES={'sportsws':'poly_sports_ws_sbor.py','clobws':'poly_clob_ws_sbor.py'}

def need(ok,reason):
    if not ok:raise ValueError('POLY_MAC_'+reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def once(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(value,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def ps(pid):
    r=subprocess.run(['ps','-p',str(pid),'-o','ppid=','-o','command='],capture_output=True,text=True,check=True)
    parent,command=r.stdout.strip().split(None,1);return int(parent),command

def processes(script):
    r=subprocess.run(['pgrep','-f','research_lab/'+script+'$'],capture_output=True,text=True)
    need(r.returncode in (0,1),'PGREP_FAILED');out=[]
    for pid in r.stdout.split():
        try:parent,command=ps(int(pid));words=shlex.split(command)
        except (ProcessLookupError,subprocess.CalledProcessError):continue
        if len(words)==2 and words[1]=='research_lab/'+script and Path(words[0]).name in ('Python','python','python3','python3.13'):out.append(int(pid))
    return out

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--apply-data-cutover',action='store_true');ap.add_argument('--config',type=Path);ap.add_argument('--config-sha256');ap.add_argument('--plist',type=Path);ap.add_argument('--plist-sha256');ap.add_argument('--proof',type=Path);a=ap.parse_args(argv)
    if not a.apply_data_cutover:print(json.dumps(dict(status='DATA_ONLY_NO_COMMANDS')));return 0
    need(a.config and a.plist and a.proof,'EXPLICIT_SCOPE');raw=a.config.read_bytes();need(sha(raw)==a.config_sha256,'CONFIG_PIN');c=json.loads(raw)
    need(c['mac_root']==str(MAC) and a.plist==Path.home()/'Library/LaunchAgents'/(LABEL+'.plist') and sha(a.plist.read_bytes())==a.plist_sha256,'FIXED_PLIST_SCOPE')
    old=[];locks=[]
    for role,script in ROLES.items():
        need(sha((MAC/'research_lab'/script).read_bytes())==c['original_source_pins'][script],'ORIGINAL_SOURCE_DRIFT')
        pids=processes(script);need(len(pids)==1,'EXPECTED_ONE_ORIGINAL_PRODUCER:'+role);pid=pids[0]
        cwd=subprocess.check_output(['lsof','-a','-p',str(pid),'-d','cwd','-Fn'],text=True)
        need(('n'+str(MAC)) in cwd.splitlines(),'PRODUCER_CWD')
        current=pid;screen=None
        for _ in range(8):
            parent,command=ps(current)
            if command.startswith('SCREEN -dmS '+role+' '):screen=str(current)+'.'+role;break
            need(parent>1,'SCREEN_ANCESTRY');current=parent
        need(screen is not None,'SCREEN_IDENTITY')
        p=MAC/'research_lab/data/locks'/(role+'.lock');st=p.lstat();need(stat.S_ISREG(st.st_mode) and st.st_nlink==1 and st.st_uid==os.getuid(),'DATA_LOCK_CUSTODY')
        old.append(dict(role=role,script=script,pid=pid,screen=screen));locks.append(dict(path=str(p),inode=st.st_ino,mode=stat.S_IMODE(st.st_mode)))
    once(a.proof.with_suffix('.claim.json'),dict(schema='POLY_WS_MAC_CUTOVER_CLAIM_V1',started_ms=time.time_ns()//1000000,old=old,locks=locks,no_automatic_retry=True))
    for x in old:subprocess.run(['screen','-S',x['screen'],'-X','quit'],check=True,timeout=10)
    deadline=time.monotonic()+15
    while any(processes(script) for script in ROLES.values()):
        need(time.monotonic()<deadline,'OLD_PRODUCER_EXIT_UNKNOWN');time.sleep(.2)
    subprocess.run(['launchctl','bootstrap','gui/'+str(os.getuid()),str(a.plist)],check=True,timeout=15)
    deadline=time.monotonic()+20;status=Path(c['status_path'])
    while True:
        if status.exists():
            x=json.loads(status.read_bytes())
            if x.get('locks_held') and x.get('roles')==['sportsws','clobws'] and time.time_ns()//1000000-x['observed_ms']<30000:
                os.kill(x['pid'],0);break
        need(time.monotonic()<deadline,'MAC_CONSUMER_START_UNKNOWN');time.sleep(.2)
    result=[]
    for lock in locks:
        p=Path(lock['path']);st=p.stat();need(st.st_ino==lock['inode'] and stat.S_IMODE(st.st_mode)==lock['mode'],'ORIGINAL_DATA_LOCK_CHANGED')
        fd=os.open(p,os.O_RDWR|os.O_NOFOLLOW)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:held=True
            else:held=False
        finally:os.close(fd)
        need(held,'NORMAL_LAUNCHER_NOT_BLOCKED');result.append(dict(inode_unchanged=True,held_by_selector=True,inode=st.st_ino,mode_unchanged=True,role=Path(lock['path']).stem))
    need(not any(processes(script) for script in ROLES.values()),'LOCAL_PRODUCER_REAPPEARED')
    proof=dict(schema='POLY_WS_MAC_CUTOVER_PROOF_V1',observed_ms=time.time_ns()//1000000,roles=['sportsws','clobws'],canonical_ws_processes_remaining=0,selector_pid=x['pid'],locks=result,old=old,financial_commands=0)
    once(a.proof,proof);print(json.dumps(proof,sort_keys=True));return 0

if __name__=='__main__':raise SystemExit(main())
