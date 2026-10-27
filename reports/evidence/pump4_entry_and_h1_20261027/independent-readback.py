"""Literal read-only installed OFF evidence; no project imports or mutations."""
from pathlib import Path
import json,hashlib,os,time,subprocess,re
base=Path('/opt/bybot-research/pump4-server-orders-off-20261023');op=base/'entry-handoff-20261027';app=base/'candidate-ffb31e24c703d9ed/app';root=app/'.private/pump4-supervisor-v1'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
unit=Path('/etc/systemd/system/pump4-execution-owner.service');text=unit.read_text();cp=Path(re.search(r'--config (\S+)',text)[1]);pin=re.search(r'--config-sha256 ([0-9a-f]{64})',text)[1]
assert cp==op/'owner-review-stream-v1/runner.json' and sha(cp)==pin and '--orders-off' in text
c=json.loads(cp.read_bytes());s=json.loads(Path(c['authority']['path']).read_bytes());rt=Path(s['root']);now=time.time_ns()//1000000
assert c['mode']==s['mode']=='ORDERS_OFF' and c['app_root']==str(app) and c['custody_runtime_root']==s['root']
assert sha(c['authority']['path'])==c['authority']['sha256'] and s['runner_config_sha256']==digest({k:v for k,v in c.items() if k!='authority'})
assert text==(op/'owner-review-stream-v1/pump4-execution-owner.service').read_text()
assert all(sha(Path(p))==h for p,h in c['guard_source_files'].items())
assert all(sha(app/n)==h for n,h in c['source_files'].items())
m=json.loads((app.parent/'manifest.json').read_bytes());assert m['material_sha256']=='ffb31e24c703d9ed71cfa3acd4e64c9d6fd1b6e9d0251843fc16c4a156971f1a' and all(sha(app/n)==h for n,h in m['files'].items())
ep=c['execution_policy'];assert ep==s['execution_policy'] and ep['source_manifest_sha256']==digest(c['source_files']) and ep['risk_policy_sha256']==digest(s['policy'])
assert ep['max_delay_ms']==c['entry_max_delay_ms']==60000 and ep['max_reference_drift_bps']=='10'
assert c['data_source']['root']==str(root) and c['data_source']['binding']['sha256']==sha(root/'data-binding.json')
bound=json.loads((root/'data-binding.json').read_bytes());assert bound['source_files']==c['source_files'] and not bound['orders_allowed'] and not bound['money_authority']
for name in ('owner-go.json','admitted-lifecycle.json','entry-revoked.json','risk.jsonl'):assert not os.path.lexists(rt/name)
for name in ('flows','send-barriers','supervisor/attempts'):assert not any((rt/name).rglob('*'))
def state(name):return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',name,'--property=MainPID,NRestarts,ActiveState,SubState,DropInPaths,Job'],text=True).splitlines() if '=' in x)
st=state(unit.name);assert st['ActiveState']=='active' and st['NRestarts']=='0' and not st['DropInPaths'] and not st['Job']
lock=Path(s['account_lock_path']);ls=lock.stat();assert ls.st_ino==s['account_lock_inode']==818853
ident=f'{os.major(ls.st_dev):02x}:{os.minor(ls.st_dev):02x}:{ls.st_ino}'
held=any(len(v)==8 and v[1:4]==['FLOCK','ADVISORY','WRITE'] and v[4:]==[st['MainPID'],ident,'0','EOF'] for v in (l.split() for l in Path('/proc/locks').read_text().splitlines()));assert held
cmd=(Path('/proc')/st['MainPID']/'cmdline').read_bytes().split(b'\0');assert b'--orders-off' in cmd and str(app/'scripts/run_pump4_execution_supervisor_v1.py').encode() in cmd
receipts=sorted((rt/'supervisor/receipts').glob('*.json'),key=lambda p:p.stat().st_mtime_ns);rs=[json.loads(p.read_bytes()) for p in receipts[-3:]];assert rs and 0<=now-rs[-1]['observed_ms']<90000
assert all(v['mode']=='ORDERS_OFF' and v['runner_config_sha256']==pin and v['scope_sha256']==digest(s) and v['pid']==int(st['MainPID']) and v['broker_writes']==0 and v['result']==dict(status='NO_NEW_SIGNAL',broker_writes=0) for v in rs)
history=json.loads((op/'data-history-before.json').read_bytes());original=Path(json.loads((op/'before.json').read_bytes())['config']['data_source']['root']);oldintakes=[]
for n,h in history.items():
 if n.startswith(('intake/','epochs/')):
  assert sha(original/n)==h and (root/n).read_bytes().startswith((original/n).read_bytes());oldintakes.append(n)
monthly=sha('/etc/systemd/system/alpaca-monthly-owned.service');assert monthly=='9d94467d301cf5f545bee18e50b838623c061b72f46a2fbdd9b7d1991932cc1d'
assert Path('/etc/systemd/system/pump4-data-supervisor.service').read_bytes()==(op/'new-data.service').read_bytes()
assert state('pump4-data-supervisor.timer')['ActiveState']=='active'
for name in c['inhibitors']:
 x=state(name);assert x['MainPID']=='0' and x['ActiveState'] in ('inactive','failed')
print(json.dumps(dict(schema='PUMP4_SELECTED_EXPLICIT_ENTRY_OFF_READBACK_V1',observed_ms=now,code_pass=True,selected_app=str(app),data_root=str(root),config_sha256=pin,scope_sha256=digest(s),data_binding_sha256=sha(root/'data-binding.json'),execution_policy=ep,original_lock_inode=ls.st_ino,original_lock_held=held,unit_state=st,clean_actual_cycles=len(receipts),last_receipts=rs,financial_history_empty=True,owner_go_present=False,guard_source_pins_pass=True,source_pins_pass=True,checked_history_prefix_files=len(oldintakes),monthly_unit_sha256=monthly,data_timer_active=True,actual_new_h1_status='PENDING',broker_writes=0,financial_go=False)))
