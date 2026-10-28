from pathlib import Path
import json,hashlib,time,subprocess,collections,re,os
B=Path('/opt/bybot-research/pump4-server-orders-off-20261023');D=B/'candidate-7d8ae05dab162ec5/app/.private/pump4-supervisor-v1';O=B/'ws-handoff-20261028';now=time.time_ns()//1000000
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def st(n):return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',n,'--property=MainPID,ActiveState,SubState,NRestarts,Job,DropInPaths,Result'],text=True,timeout=6).splitlines() if '=' in x)
u=Path('/etc/systemd/system/pump4-execution-owner.service').read_text();cp=Path(re.search(r'--config (\S+)',u)[1]);c=json.loads(cp.read_bytes());s=json.loads(Path(c['authority']['path']).read_bytes());rt=Path(s['root']);out=dict(observed_ms=now,units={n:st(n) for n in ('pump4-data-supervisor.service','pump4-data-supervisor.timer','pump4-execution-owner.service','alpaca-monthly-owned.service','alpaca-monthly-owned.timer')},selected_config_path=str(cp),config_sha256=sha(cp),scope_sha256=hashlib.sha256(json.dumps(s,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),mode=c['mode'],financial_app=c['app_root'],data_root=c['data_source']['root'],owner_go_present=(rt/'owner-go.json').exists(),hours=[])
for p in sorted((D/'ws-hours').glob('*')):
 row=dict(target_ms=int(p.name),receipt_exists=(p/'receipt.json').exists(),attempt_sha256=sha(p/'attempt.json') if (p/'attempt.json').exists() else None,published_count=len(list((p/'published').glob('*.json'))))
 if (p/'receipt.json').exists():
  raw=(p/'receipt.json').read_bytes();v=json.loads(raw);row.update({k:x for k,x in v.items() if k!='rows'});row.update(receipt_sha256=hashlib.sha256(raw).hexdigest(),statuses=dict(collections.Counter(x['status'] for x in v['rows'])),signals=[x['symbol'] for x in v['rows'] if any(y['decision'].get('signal') is not None for y in x.get('decisions',[]))],max_publication_delay_ms=max((x['publication_completed_ms']-v['source_hour_open_ms'] for x in v['rows'] if x['status']=='CLOSED_H1_INTAKE_PASS'),default=None))
 if (p/'disconnect.json').exists():row['disconnect']=json.loads((p/'disconnect.json').read_bytes())
 out['hours'].append(row)
out['watchers']={str(p.relative_to(O)):json.loads(p.read_bytes()) for p in O.glob('actual-h1-*/final.json')}
out['watcher_failures']={str(p.relative_to(O)):json.loads(p.read_bytes()) for p in O.glob('actual-h1-*/protected-health-failure.json')}
rs=sorted((rt/'supervisor/receipts').glob('*.json'),key=lambda p:p.stat().st_mtime_ns);out['latest_owner_receipts']=[json.loads(p.read_bytes()) for p in rs[-3:]]
mr=Path('/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-dcaafa089ff8f81f-t32a6a356/runtime/monthly400-v4/observations');ms=[json.loads(p.read_bytes()) for p in sorted(mr.glob('*.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True)[:24]];last=max((x for x in ms if x.get('operation')=='DISPATCH_TICK'),key=lambda x:x['observed_ms']);out['monthly_latest']=dict(observed_ms=last['observed_ms'],status=last['result'].get('status'),issues=last['result'].get('issues'),source_status=(last['result'].get('source') or {}).get('status'),maintenance=last['result'].get('maintenance'));out['monthly_unit_sha256']=sha('/etc/systemd/system/alpaca-monthly-owned.service')
out['data_recent_journal']=subprocess.check_output(['journalctl','-u','pump4-data-supervisor.service','--no-pager','-n','16','-o','cat'],text=True,timeout=8)
print(json.dumps(out))
