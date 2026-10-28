"""Installed WS DATA / original e4 financial consumer; literal read-only observer."""
from pathlib import Path
import json,hashlib,os,time,subprocess,re
b=Path('/opt/bybot-research/pump4-server-orders-off-20261023');op=b/'ws-handoff-20261028';oldapp=b/'candidate-e4feca498f37e27d/app';dataapp=b/'candidate-7d8ae05dab162ec5/app';root=dataapp/'.private/pump4-supervisor-v1';now=time.time_ns()//1000000
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def state(n):return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',n,'--property=MainPID,NRestarts,ActiveState,SubState,DropInPaths,Job,CPUWeight,CPUQuotaPerSecUSec,MemoryMax'],text=True).splitlines() if '=' in x)
def held(lock,pid):
 s=Path(lock).stat();key=f'{os.major(s.st_dev):02x}:{os.minor(s.st_dev):02x}:{s.st_ino}'
 return any(len(x)==8 and x[1:4]==['FLOCK','ADVISORY','WRITE'] and x[4:]==[str(pid),key,'0','EOF'] for x in (r.split() for r in Path('/proc/locks').read_text().splitlines()))
before=json.loads((op/'before.json').read_bytes());unit=Path('/etc/systemd/system/pump4-execution-owner.service');text=unit.read_text();cp=Path(re.search(r'--config (\S+)',text)[1]);pin=re.search(r'--config-sha256 (\w+)',text)[1]
assert cp==op/'owner-review-stream-v1/runner.json' and sha(cp)==pin and text==(cp.parent/'pump4-execution-owner.service').read_text() and '--orders-off' in text
c=json.loads(cp.read_bytes());s=json.loads(Path(c['authority']['path']).read_bytes());rt=Path(s['root'])
assert c['mode']==s['mode']=='ORDERS_OFF' and c['app_root']==str(oldapp) and sha(c['authority']['path'])==c['authority']['sha256'] and s['runner_config_sha256']==digest({k:v for k,v in c.items() if k!='authority'})
for k in ('source_files','execution_policy','credential_source','credential_source_sha256','account_fingerprint','entry_max_delay_ms','epoch_started_ms'):assert c[k]==before['config'][k],k
for k in ('policy','execution_policy','account_lock_path','account_lock_inode'):assert s[k]==before['scope'][k],k
assert all(sha(Path(p))==h for p,h in c['guard_source_files'].items()) and all(sha(oldapp/n)==h for n,h in c['source_files'].items())
m=json.loads((dataapp.parent/'manifest.json').read_bytes());assert m['material_sha256']=='7d8ae05dab162ec5eaded17a7ed779c14d092880553dcd96345cf3d3198e6cf0' and all(sha(dataapp/n)==h for n,h in m['files'].items())
assert c['data_source']['root']==str(root) and c['data_source']['binding']['sha256']==sha(root/'data-binding.json')
bound=json.loads((root/'data-binding.json').read_bytes());assert not bound['orders_allowed'] and not bound['money_authority'] and all(sha(dataapp/n)==h for n,h in bound['source_files'].items())
for name in ('research_lab/pump4_closed_bar_intake_v1.py','research_lab/pump4_supervisor_v1.py','strategies/pump_fade_v4r.py','strategies/signals.py'):assert bound['source_files'][name]==c['source_files'][name]
for name in ('owner-go.json','admitted-lifecycle.json','entry-revoked.json','risk.jsonl'):assert not os.path.lexists(rt/name)
for name in ('flows','send-barriers','supervisor/attempts'):assert not any((rt/name).rglob('*'))
st=state(unit.name);assert st['ActiveState']=='active' and st['NRestarts']=='0' and not st['DropInPaths'] and not st['Job']
lock=Path(s['account_lock_path']);assert lock.stat().st_ino==818853 and held(lock,st['MainPID'])
cmd=(Path('/proc')/st['MainPID']/'cmdline').read_bytes().split(b'\0');assert str(oldapp/'scripts/run_pump4_execution_supervisor_v1.py').encode() in cmd and b'--orders-off' in cmd
rs=sorted((rt/'supervisor/receipts').glob('*.json'),key=lambda p:p.stat().st_mtime_ns);receipts=[json.loads(p.read_bytes()) for p in rs[-3:]];assert receipts and 0<=now-receipts[-1]['observed_ms']<90000
assert all(v['mode']=='ORDERS_OFF' and v['pid']==int(st['MainPID']) and v['broker_writes']==0 and v['runner_config_sha256']==pin and v['scope_sha256']==digest(s) and not v['result']['status'].startswith('BLOCKED') for v in receipts)
ds=state('pump4-data-supervisor.service');assert ds['ActiveState']=='active' and ds['NRestarts']=='0' and not ds['DropInPaths'] and ds['CPUQuotaPerSecUSec']=='2s' and ds['MemoryMax']=='805306368' and ds['CPUWeight'] in ('[not set]','100')
assert Path('/etc/systemd/system/pump4-data-supervisor.service').read_bytes()==(op/'new-data.service').read_bytes()
assert held(root/'data-writer.lock',ds['MainPID'])
dcmd=(Path('/proc')/ds['MainPID']/'cmdline').read_bytes().split(b'\0');assert str(dataapp/'scripts/run_pump4_stream_v1.py').encode() in dcmd and b'--run' in dcmd and b'--once' not in dcmd
assert state('pump4-data-supervisor.timer')['ActiveState']=='active'
history=json.loads((op/'data-history-before.json').read_bytes());old=Path(before['config']['data_source']['root']);checked=0
for n,h in history.items():
 assert sha(old/n)==h,'OLD_HISTORY_CHANGED'
 if n=='data-binding.json':continue
 raw=(root/n).read_bytes()
 if sha(root/n)!=h:assert n.endswith('.jsonl') and raw.startswith((old/n).read_bytes()),'HISTORY_CHANGED'
 checked+=1
monthly=sha('/etc/systemd/system/alpaca-monthly-owned.service');assert monthly=='9d94467d301cf5f545bee18e50b838623c061b72f46a2fbdd9b7d1991932cc1d'
mr=Path('/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-dcaafa089ff8f81f-t32a6a356/runtime/monthly400-v4/observations');rows=[json.loads(p.read_bytes()) for p in sorted(mr.glob('*.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True)[:24]];monthly_last=max((v for v in rows if v.get('operation')=='DISPATCH_TICK'),key=lambda v:v['observed_ms']);monthly_now=time.time_ns()//1000000;assert 0<=monthly_now-monthly_last['observed_ms']<=90000 and not monthly_last['result'].get('issues') and (monthly_last['result'].get('source') or {}).get('status')=='ORDERS_OFF_OPERATIONAL_PASS'
for n in c['inhibitors']:assert state(n)['MainPID']=='0' and state(n)['ActiveState'] in ('inactive','failed')
st2=state(unit.name);ds2=state('pump4-data-supervisor.service');assert st2==st and ds2==ds,'PROCESS_CHANGED_DURING_READBACK'
rs=sorted((rt/'supervisor/receipts').glob('*.json'),key=lambda p:p.stat().st_mtime_ns);receipts=[json.loads(p.read_bytes()) for p in rs[-3:]];owner_now=time.time_ns()//1000000;assert 0<=owner_now-receipts[-1]['observed_ms']<90000 and held(lock,st['MainPID'])
preloads=[json.loads(p.read_bytes()) for p in (root/'ws-setup').glob('*/preloaded.json')]
print(json.dumps(dict(schema='PUMP4_RESIDENT_WS_OFF_READBACK_V1',observed_ms=time.time_ns()//1000000,started_ms=now,status='PASS',financial_app=str(oldapp),data_app=str(dataapp),config_sha256=pin,scope_sha256=digest(s),data_binding_sha256=sha(root/'data-binding.json'),owner_state=st,data_state=ds,original_lock_inode=818853,original_lock_held=True,clean_off_cycles=len(rs),last_receipts=receipts,financial_policy_unchanged=True,financial_history_empty=True,owner_go_created=False,preserved_history_files=checked,monthly_unit_unchanged=True,monthly_source_status='PASS',monthly_receipt_age_ms=monthly_now-monthly_last['observed_ms'],preloads=preloads,actual_new_h1_status='PENDING',broker_writes=0,tiny_ready=False)))
