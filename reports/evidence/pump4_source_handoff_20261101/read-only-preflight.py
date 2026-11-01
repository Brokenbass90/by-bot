"""Read-only fixed-envelope GET evidence. No owner or lifecycle construction."""
import hashlib,json,time,sys,os,subprocess
from pathlib import Path
sha=lambda b:hashlib.sha256(b).hexdigest()
digest=lambda v:sha(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
folder=Path('/opt/bybot-research/pump4-server-orders-off-20261023/tiny-activation-20261028-v1')
raw=(folder/'runner.json').read_bytes()
assert sha(raw)=='fa0b3b2ec893f5167d79e71ef7fcf5a1d3788075105a2732663a8dafec53014a'
c=json.loads(raw);s=json.loads((folder/'scope.json').read_bytes())
assert digest(s)=='fec235e3dea12245d96859a6786d811551f9341d9a860ee4fac88dea4bfcf794'
app=Path('/opt/bybot-research/pump4-current-hour-repair-20261101/candidate-badb0d4afd158e3a/app')
# The exact candidate manifest lives beside app. It is a static code allowlist.
mr=(app.parent/'verification-source-hashes.json').read_bytes()
assert sha(mr)=='badb0d4afd158e3a0a8321a36b84de6acf28f79c3d5d5388168874ca3c272e6c'
manifest=json.loads(mr)
files=manifest
for name,pin in files.items():
 assert not Path(name).is_absolute() and '..' not in Path(name).parts
 assert sha((app/name).read_bytes())==pin
sys.path.insert(0,str(app))
from research_lab.kity_micro_physical_owner_v1 import load_bound_credentials
from research_lab.kity_micro_transport_v1 import BybitReadTransport
key,secret=load_bound_credentials(c)
r=BybitReadTransport(key,secret,symbols=('BTCUSDT',))
start=s['valid_from_ms'];end=time.time_ns()//1000000
assert 0<end-start<7*86400000
api=r.get('/v5/user/query-api',{});ar=r.result(api)
summary={};captures={}
specs={
 'positions':('/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200')),
 'open_orders':('/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50')),
 'order_history':('/v5/order/history',dict(category='linear',startTime=start,endTime=end,limit='50')),
 'executions':('/v5/execution/list',dict(category='linear',startTime=start,endTime=end,limit='100')),
 'transactions':('/v5/account/transaction-log',dict(accountType='UNIFIED',category='linear',currency='USDT',startTime=start,endTime=end,limit='50')),
}
for name,(ep,params) in specs.items():
 cap=r.pages(ep,params);assert cap['complete'],name+'_INCOMPLETE'
 rows=[row for p in cap['pages'] for row in r.result(p)['list']]
 captures[name]=cap
 summary[name]=dict(endpoint=ep,params=params,complete=True,page_count=len(cap['pages']),rows=len(rows),capture_sha256=digest(cap),request_ms=min(p['request_ms'] for p in cap['pages']),receive_ms=max(p['receive_ms'] for p in cap['pages']))
 if name=='positions':summary[name]['nonzero']=sum(abs(float(x.get('size','0')))>0 for x in rows)
root=Path(s['root']);money={}
for name in ('admitted-lifecycle.json','risk.jsonl','entry-loss-stop.json','entry-revoked.json'):
 p=root/name;money[name]=dict(exists=os.path.lexists(p))
 if p.is_file():money[name].update(bytes=p.stat().st_size,sha256=sha(p.read_bytes()))
for name in ('tickets','send-barriers','flows','supervisor/attempts'):
 p=root/name;items=list(p.rglob('*'));assert len(items)<=1000,'UNEXPECTED_MONEY_TREE_BOUND'
 money[name]=dict(exists=p.exists(),entries=len(items),files={str(x.relative_to(p)):sha(x.read_bytes()) for x in items if x.is_file()})
units={}
for name in ('pump4-execution-owner.service','pump4-data-supervisor.service','alpaca-monthly-owned.service','alpaca-monthly-owned.timer'):
 p=Path('/etc/systemd/system')/name
 units[name]=dict(sha256=sha(p.read_bytes()),state=subprocess.check_output(['systemctl','show',name,'--property=MainPID,ActiveState,SubState,NRestarts'],text=True).strip())
receipt_paths=list((root/'supervisor/receipts').glob('*.json'))
latest=max(receipt_paths,key=lambda p:p.stat().st_mtime_ns)
last=json.loads(latest.read_bytes())
out=dict(schema='PUMP4_REPAIR_READ_ONLY_PREFLIGHT_V1',observed_ms=time.time_ns()//1000000,history_start_ms=start,history_cutoff_ms=end,
 old_config_sha256=sha(raw),old_scope_sha256=digest(s),api_expired_at=ar.get('expiredAt'),api_retcode=api['body']['retCode'],
 api_capture_sha256=digest(api),money=money,get_summary=summary,units=units,latest_receipt=last,
 receipt_count=len(receipt_paths),broker_writes=0,financial_owner_constructed=False,
 terminal_cost_finality_proven=False,flat_now=summary['positions']['nonzero']==summary['open_orders']['rows']==0,
 full_linear_usdt_history_empty=all(summary[n]['rows']==0 for n in ('order_history','executions','transactions')),
 total_get_requests=1+sum(x['page_count'] for x in summary.values()))
print(json.dumps(out,sort_keys=True))
