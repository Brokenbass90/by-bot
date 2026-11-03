"""Restore only the known original DATA unit; retain every spent source record."""
from pathlib import Path
import subprocess,json,hashlib,os,fcntl,time
P=Path('/opt/bybot-research/pump4-data-throughput-20261103/patch-59f6639e8c700153');ROOT=Path('/opt/bybot-research/pump4-server-orders-off-20261023/candidate-7d8ae05dab162ec5/app/.private/pump4-supervisor-v1');U=Path('/etc/systemd/system/pump4-data-supervisor.service')
def sha(b):return hashlib.sha256(b).hexdigest()
def state(u):return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',u,'-p','MainPID','-p','NRestarts','-p','ActiveState','-p','Job','-p','DropInPaths'],text=True).splitlines() if '=' in x)
def once(p,x):
 with p.open('x') as f:json.dump(x,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
assert sha((P/'patch-manifest.json').read_bytes())=='59f6639e8c70015391e756bb1d5a217904dc6b2c204f750d6e52e254522d4e15'
patch=json.loads((P/'patch-manifest.json').read_bytes());original=(P/'original-manifest.json').read_bytes();assert sha(original)==patch['files']['original-manifest.json'];old=json.loads(original)
for n,h in old['files'].items():assert sha((ROOT.parent.parent/n).read_bytes())==h,'ORIGINAL_SOURCE_DRIFT'
b=(P/'old-data-exact.service').read_bytes();assert sha(b)=='cb9de84027ee8d42e72068ce9f66fbbdb6fcf433cc27f435883f52c01d495a35'
assert sha(U.read_bytes())=='0e227ab316240795ba73bc3ec81d513b12b579327d691ecaac84ad5b8efff8c1'
assert sha(Path('/etc/systemd/system/pump4-data-supervisor.timer').read_bytes())=='d31f4ba785c56b0dda7b15f2060578effd9d10a2fab89df8f1457b2411fbca98'
assert state('pump4-data-supervisor.service')['MainPID']=='0' and not state('pump4-data-supervisor.service')['Job']
assert state('pump4-data-supervisor.timer')['ActiveState']=='inactive' and state('pump4-data-warm-handoff-v2-20261103.service')['MainPID']=='0'
before=state('pump4-execution-owner.service');assert before['MainPID']=='3669955' and before['NRestarts']=='0' and before['ActiveState']=='active'
fi=Path('/etc/systemd/system/pump4-execution-owner.service');fi_pin=sha(fi.read_bytes());moneylock=Path('/opt/bybot-research/kity-micro-owner-20261015/runtime/account.lock');assert moneylock.stat().st_ino==818853
once(P/'restore-original-claim-v1.json',dict(observed_ms=time.time_ns()//1000000,original_unit_sha256=sha(b),broker_writes=0,reason='Owner explicit original DATA restoration; no optimized retry'))
lock=ROOT/'data-writer.lock';fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
try:
 assert state('pump4-data-supervisor.service')['MainPID']=='0' and not state('pump4-data-supervisor.service')['DropInPaths']
 preserved={str(f.relative_to(ROOT)):sha(f.read_bytes()) for folder,glob in [('intake','*.jsonl'),('epochs','*.json')] for f in (ROOT/folder).glob(glob)}
 preserved.update({str((ROOT/'ws-hours'/str(h)/'receipt.json').relative_to(ROOT)):sha((ROOT/'ws-hours'/str(h)/'receipt.json').read_bytes()) for h in [1793689200000,1793692800000,1793696400000]})
 binding=sha((ROOT/'data-binding.json').read_bytes());inode=os.fstat(fd).st_ino
 tmp=U.with_name('.pump4-data-original-restore-v1');assert not tmp.exists()
 with tmp.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 tmp.chmod(0o644);os.replace(tmp,U);d=os.open(U.parent,os.O_RDONLY);os.fsync(d);os.close(d)
finally:os.close(fd)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','start','pump4-data-supervisor.service'],check=True)
subprocess.run(['systemctl','start','pump4-data-supervisor.timer'],check=True)
after=state('pump4-execution-owner.service');assert before==after and sha(fi.read_bytes())==fi_pin and moneylock.stat().st_ino==818853
assert sha(U.read_bytes())==sha(b) and sha((ROOT/'data-binding.json').read_bytes())==binding and lock.stat().st_ino==inode
for n,h in preserved.items():assert sha((ROOT/n).read_bytes())==h,'SOURCE_CHANGED_DURING_RESTORE'
data=state('pump4-data-supervisor.service');assert data['ActiveState']=='active' and data['MainPID']!='0'
out=dict(schema='PUMP4_ORIGINAL_DATA_RESTORED_V1',observed_ms=time.time_ns()//1000000,status='ORIGINAL_DATA_PROCESS_RESTORED_SPENT09_PRESERVED',data=data,timer=state('pump4-data-supervisor.timer'),financial_owner=after,financial_unit_sha256=fi_pin,account_lock_inode=818853,data_lock_inode=inode,original_sources_verified=len(old['files']),preserved_files=len(preserved),aborted_hour_ms=1793696400000,next_clean_hour_ms=1793700000000,broker_requests=0,broker_writes=0,optimized_code_selected=False)
once(P/'restore-original-result-v1.json',out);print(json.dumps(out,sort_keys=True))
