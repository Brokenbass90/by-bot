"""Bounded one-H1 acceptance observer. No financial imports/account requests."""
from pathlib import Path
import json,time,subprocess,os,hashlib
B=Path('/opt/bybot-research/pump4-server-orders-off-20261023');D=B/'candidate-7d8ae05dab162ec5/app/.private/pump4-supervisor-v1';O=B/'ws-handoff-20261028';C=O/'owner-review-stream-v1/runner.json'
H=3600000;target=(time.time_ns()//1000000//H+1)*H;end=target+120000
out=O/('actual-h1-'+str(target)+'-v2');out.mkdir(mode=0o700)
def save(name,value):
 with (out/name).open('x') as f:json.dump(value,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def state(n):return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',n,'--property=MainPID,NRestarts,ActiveState,SubState'],text=True,timeout=5).splitlines() if '=' in x)
class Latest:
 def __init__(self,root,monthly=False):self.root=Path(root);self.monthly=monthly;self.known=set();self.latest=None
 def read(self):
  paths={e.name for e in os.scandir(self.root) if e.name.endswith('.json')};fresh=paths-self.known
  if not self.known:fresh=set(sorted(fresh,key=lambda n:(self.root/n).stat().st_mtime_ns,reverse=True)[:24])
  for n in fresh:
   v=json.loads((self.root/n).read_bytes())
   if self.monthly and v.get('operation')!='DISPATCH_TICK':continue
   if self.latest is None or v['observed_ms']>self.latest['observed_ms']:self.latest=v
  self.known=paths;return self.latest
c=json.loads(C.read_bytes());m=Latest('/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-dcaafa089ff8f81f-t32a6a356/runtime/monthly400-v4/observations',True);p=Latest(Path(c['custody_runtime_root'])/'supervisor/receipts')
save('start.json',dict(target_ms=target,started_ms=time.time_ns()//1000000,observer_pid=os.getpid(),stop_only_data_on_monthly_guard=True,broker_writes=0))
previous=None;seq=0;worst_m=0;worst_p=0
while time.time_ns()//1000000<end:
 mr=m.read();pr=p.read();stamp=time.time_ns()//1000000;ma=stamp-mr['observed_ms'];pa=stamp-pr['observed_ms'];worst_m=max(worst_m,ma);worst_p=max(worst_p,pa)
 healthy=(0<=ma<=90000 and (mr['result'].get('source') or {}).get('status')=='ORDERS_OFF_OPERATIONAL_PASS' and not mr['result'].get('issues'))
 v=dict(observed_ms=stamp,target_ms=target,monthly_age_ms=ma,pump_age_ms=pa,monthly_healthy=healthy,data_state=state('pump4-data-supervisor.service'),owner_state=state('pump4-execution-owner.service'),broker_writes=0)
 if not healthy:
  save('protected-health-failure.json',v);subprocess.run(['systemctl','stop','pump4-data-supervisor.service'],check=True,timeout=100);print(json.dumps(dict(status='PROTECTED_HEALTH_FAIL_DATA_STOPPED',**v)),flush=True);raise SystemExit(2)
 folder=D/'ws-hours'/str(target);setup=D/'ws-setup'/str(target)
 for name,path in [('preloaded',setup/'preloaded.json'),('ack',folder/'subscription-ack.json'),('receipt',folder/'receipt.json')]:
  if path.exists():v[name]=json.loads(path.read_bytes()) if name!='receipt' else {k:x for k,x in json.loads(path.read_bytes()).items() if k!='rows'}
 v['published']=len(list((folder/'published').glob('*.json')));v['worst_monthly_age_ms']=worst_m;v['worst_pump_age_ms']=worst_p
 key=(v['published'],bool(v.get('preloaded')),bool(v.get('ack')),bool(v.get('receipt')),v['data_state']['ActiveState'])
 if key!=previous or stamp>=target-20000:
  seq+=1;save(str(seq).zfill(5)+'.json',v);print(json.dumps(v),flush=True);previous=key
 if v.get('receipt'):
  raw=(folder/'receipt.json').read_bytes();save('final.json',dict(status='PASS' if v['receipt']['hour_pass'] and healthy else 'FAIL',receipt_sha256=hashlib.sha256(raw).hexdigest(),**v));raise SystemExit(0 if v['receipt']['hour_pass'] else 1)
 time.sleep(10 if stamp<target-20000 else 2)
save('final.json',dict(status='FAIL_MISSING_H1_RECEIPT',observed_ms=time.time_ns()//1000000,target_ms=target,broker_writes=0));raise SystemExit(1)
