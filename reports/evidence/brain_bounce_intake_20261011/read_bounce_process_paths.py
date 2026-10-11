import subprocess, os, json, hashlib
from pathlib import Path
pid=1648585
proc=Path('/proc')/str(pid)
cwd=Path(os.readlink(proc/'cwd'))
argv=(proc/'cmdline').read_bytes().split(b'\0')
scripts=[a.decode() for a in argv if a and a.endswith(b'.py')]
roots={cwd,Path('/root/by-bot')}
for script in scripts:
 p=Path(script); p=p if p.is_absolute() else cwd/p
 roots.add(p.parent)
selected_env={}
for item in (proc/'environ').read_bytes().split(b'\0'):
 k,sep,v=item.partition(b'=')
 if sep and k.decode(errors='ignore') in {'BOUNCE1_SHADOW_STATE_PATH','BOUNCE1_SHADOW_LEDGER_PATH','BOUNCE1_SYMBOL_ALLOWLIST','BOUNCE1_RISK_MULT','BOUNCE1_SHADOW_ENABLE'}: selected_env[k.decode()]=v.decode()
out={'cwd':str(cwd),'main_scripts':scripts,'selected_initial_process_env_not_runtime_proof':selected_env,'files':{},'units':[]}
u=subprocess.run(['systemctl','list-units','--all','--type=service','--no-legend','--no-pager'],capture_output=True,text=True,timeout=5)
for line in u.stdout.splitlines():
 name=line.split()[0] if line.split() else ''
 if ('bybot' in name or 'att1' in name) and 'alpaca' not in name:
  q=subprocess.run(['systemctl','show',name,'--property=MainPID,NRestarts,ActiveState,SubState'],capture_output=True,text=True,timeout=5)
  out['units'].append({'name':name,'properties':dict(x.split('=',1) for x in q.stdout.splitlines() if '=' in x)})
for root in sorted(roots):
 for rel in ['smart_pump_reversal_bot.py','bot/strategy_shadow_ledger.py','strategies/bounce1_live.py','strategies/alt_support_bounce_v1.py','configs/approved_strategy_params.env','runtime/bounce1_shadow_ledger.jsonl','runtime/bounce1_shadow_state.json']:
  p=root/rel
  if not p.exists(): out['files'][str(p)]={'missing':True}; continue
  n=p.stat().st_size
  if n>32*1024*1024: out['files'][str(p)]={'status':'BYTE_BOUND','bytes':n}; continue
  raw=p.read_bytes(); d={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'size_after':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns}
  if p.name=='bounce1_shadow_ledger.jsonl':
   events=[json.loads(x) for x in raw.splitlines()]; close=[x for x in events if x.get('event')=='close']
   d.update(event_counts={k:sum(x.get('event')==k for x in events) for k in ['decision','fill','target','cancel','close']},unique_closed=len({x.get('signal_id') for x in close}),symbols=sorted({x.get('symbol') for x in events}),first_ms=min([x['ts_ms'] for x in events],default=None),last_ms=max([x['ts_ms'] for x in events],default=None),duplicate_closes=len(close)-len({x.get('signal_id') for x in close}),authority_safe=all(x.get('broker_calls') is False and x.get('mode')=='shadow' for x in events),complete_tail=not raw or raw.endswith(b'\n'))
  elif p.name=='bounce1_shadow_state.json':
   j=json.loads(raw);d.update({k:j.get(k) for k in ['schema_id','strategy','mode','broker_calls','closed_count']});d.update(open_symbols=sorted(j.get('open',{})),pending_symbols=sorted(j.get('pending',{})))
  out['files'][str(p)]=d
print(json.dumps(out,sort_keys=True))
