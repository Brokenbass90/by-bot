"""Read-only exact-hour source/publication evidence; no project imports."""
from pathlib import Path
import hashlib,json,time,statistics,collections
base=Path('/opt/bybot-research/pump4-server-orders-off-20261023');root=base/'candidate-e4feca498f37e27d/app/.private/pump4-supervisor-v1';hour=1793088000000;archive=root/'archives'/str(hour)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
process=root/'capture-process'/(str(hour)+'.json');failure=root/'capture-process-failures'/(str(hour)+'.json')
out=dict(observed_ms=time.time_ns()//1000000,source_hour_open_ms=hour,data_root=str(root),process_present=process.exists(),process_failure=json.loads(failure.read_bytes()) if failure.exists() else None,broker_writes=0)
context=archive/'capture-context.json';rows=[]
if context.exists():
 cid=sha(context);rows=[json.loads(p.read_bytes()) for p in (root/'streamed'/cid).glob('*.json')];out['context_sha256']=cid
out['rows']=rows;groups={};api=[]
for r in rows:
 result=r['result'];mode=result.get('mode',result['status']);g=groups.setdefault(mode,dict(count=0,within60s=0,publication_delays_ms=[],source_delays_ms=[]));delay=r['publication_completed_ms']-hour;g['count']+=1;g['within60s']+=int(0<=delay<=60000);g['publication_delays_ms'].append(delay)
 for d in result.get('decisions',[]):g['source_delays_ms'].append(d['decision']['first_observed_ms']-hour)
 if result['status']=='BLOCKED_SOURCE':
  source=json.loads((archive/'symbols'/(r['symbol']+'.json')).read_bytes());api.append(dict(symbol=r['symbol'],reason=source.get('reason'),captures=[dict(endpoint=c['endpoint'],params=c['params'],request_ms=c['request_ms'],receive_ms=c['receive_ms'],raw_sha256=c.get('raw_sha256'),retCode=c['body'].get('retCode'),retMsg=c['body'].get('retMsg')) for c in source.get('captures',[])]))
for g in groups.values():
 for field in ('publication_delays_ms','source_delays_ms'):
  v=g[field];g[field+'_summary']=dict(min=min(v),median=statistics.median(v),max=max(v)) if v else None
out['groups']=groups;out['api_failures']=api;out['signal_symbols']=[r['symbol'] for r in rows if any(d['decision']['signal'] is not None for d in r['result'].get('decisions',[]))]
if process.exists():
 p=json.loads(process.read_bytes());out['process_receipt']=p;ns=p['notices'];im=[n for n in ns if n['scheduling']=='IMMEDIATE'];de=[n for n in ns if n['scheduling']=='DEFERRED_CATCHUP_NON_ENTRY'];out['priority_pass']=not de or max(n['parent_publication_finished_ms'] for n in im)<=min(n['parent_processing_started_ms'] for n in de);out['classification_wall_ms']=sum(n['classification_completed_ms']-n['classification_started_ms'] for n in ns);out['parent_processing_ms']=sum(n['parent_publication_finished_ms']-n['parent_processing_started_ms'] for n in ns)
if (archive/'receipt.json').exists():
 seal=json.loads((archive/'receipt.json').read_bytes());out['archive_receipt_sha256']=sha(archive/'receipt.json');out['archive_seal']=seal;out['archive_files_hashes_pass']=all(sha(archive/n)==h for n,h in seal['source_capture_files'].items())
print(json.dumps(out))
