"""One-shot approved-scope GET observer. No financial constructors or order writes."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess,time,uuid
BASE=Path('/opt/bybot-research/monthly-recovery-cache-20261103/read-only-window-check-v1')
P=Path('/opt/bybot-research/monthly-recovery-cache-20261103/candidate-684518513910cd6e-t01be717f/owner-review-cache-v2')
assert time.time()>=1793716800,'NOT_BEFORE_2026_11_03_14_40_UTC'
def pin(p,h):
 b=p.read_bytes();assert hashlib.sha256(b).hexdigest()==h,'PIN_DRIFT:'+p.name;return b
out={'schema':'MONTHLY_12509204_POSTWINDOW_GET_V1','observed_ms':time.time_ns()//1000000,'broker_writes':0,'window_open_ms':1793716200000,'window_close_ms':1793716500000,'history_complete':False}
try:
 packet=json.loads(pin(P/'packet.json','5f828ca8a22b256c0cff202082bed75f4ce337af34e85def6dbb224902182e79'))
 C=Path(packet['candidate']);m=json.loads((C/'source-manifest.json').read_bytes())
 assert m['source_material_sha256']=='684518513910cd6ed80a4b8a39e7425b970cd213ae07dbeafa37ee45e3cf4797'
 for n,h in m['files'].items():pin(C/'app'/n,h)
 pin(P/'readback.py','0e9791646620a83970e8a46ccac839946351e711d6f17fd1b2a3656aff375d1c')
 r=subprocess.run(['/root/by-bot/.venv/bin/python','-B',str(P/'readback.py')],capture_output=True,text=True,timeout=120)
 assert r.returncode==0,'GET_READBACK_FAILED:'+r.stderr[-1000:]
 out['broker']=json.loads(r.stdout)
 root=Path('/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-dcaafa089ff8f81f-t32a6a356/runtime/monthly400-v4')
 out['observations']=[]
 for f in sorted((root/'observations').glob('*.json'),key=lambda f:f.stat().st_mtime_ns)[-70:]:
  b=f.read_bytes();v=json.loads(b)
  if v.get('observed_ms',0)>=1793715900000:out['observations'].append({'name':f.name,'sha256':hashlib.sha256(b).hexdigest(),'value':v})
 out['monthly_status']=subprocess.check_output(['systemctl','show','alpaca-monthly-owned.service','-p','MainPID','-p','Result','-p','ExecMainStatus','-p','ExecStart'],text=True)
 out['window_journal']=subprocess.check_output(['journalctl','-u','alpaca-monthly-owned.service','--since','2026-11-03 14:25:00 UTC','--until','2026-11-03 14:40:00 UTC','-n','40','--no-pager','-o','cat'],text=True)
 out['status']='ACTUAL_POSTWINDOW_GET_CAPTURED_NOT_A_VERDICT'
except BaseException as e:out.update(status='UNKNOWN',error_type=type(e).__name__,reason=str(e))
out['completed_ms']=time.time_ns()//1000000
f=BASE/('receipt-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex+'.json')
fd=os.open(f,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as h:json.dump(out,h,sort_keys=True);h.flush();os.fsync(h.fileno())
print(json.dumps({'status':out['status'],'observed_ms':out['observed_ms'],'receipt':str(f),'broker_writes':0}))
