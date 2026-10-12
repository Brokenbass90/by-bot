"""Bounded read-only VPS filesystem provenance; timestamps are not Git proof."""
import hashlib,json,os,subprocess,sys
from pathlib import Path

REMOTE=r'''
import ast,datetime,hashlib,json,os,signal,time
from pathlib import Path
signal.alarm(30);records=[];visited=0;bounded=False
for root in [Path('/root/by-bot/research_lab'),Path('/opt/bybot-research')]:
 if not root.is_dir():continue
 for directory,dirs,files in os.walk(root,followlinks=False):
  visited+=1
  if visited>1024:bounded=True;break
  depth=len(Path(directory).relative_to(root).parts)
  dirs[:]=[d for d in dirs if depth<5 and d not in ['data','runtime','.git','.venv','__pycache__'] and not d.startswith('.')]
  for name in ['research_machine.py','ten.py']:
   if name not in files:continue
   p=Path(directory)/name
   if p.is_symlink() or p.stat().st_size>1000000:continue
   b=p.read_bytes();stat=p.stat();tree=ast.parse(b)
   nodes=[ast.dump(n.value,include_attributes=False) for n in tree.body if isinstance(n,ast.Assign)
          and any(isinstance(t,ast.Name) and t.id=='MAX_LEV' for t in n.targets)]
   records.append({'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),
    'mtime_ns':stat.st_mtime_ns,'mtime_utc':datetime.datetime.fromtimestamp(stat.st_mtime,datetime.timezone.utc).isoformat(),
    'ctime_utc':datetime.datetime.fromtimestamp(stat.st_ctime,datetime.timezone.utc).isoformat(),
    'MAX_LEV_assignment_ast':nodes,'MAX_LEV_name_references':sum(isinstance(n,ast.Name) and n.id=='MAX_LEV' for n in ast.walk(tree))})
guard=Path('/opt/bybot-research/alpaca-net-paper-session-20261012/runtime/guard/latest.json')
result={'observed_ms':time.time_ns()//1000000,'files':records,'directories_visited':visited,
 'inventory_bound_hit':bounded,'scope':'VPS_FILESYSTEM_METADATA_ONLY_NOT_HISTORICAL_GIT_PROOF',
 'broker_calls':0,'remote_writes':0,'guard_latest':json.loads(guard.read_bytes()) if guard.exists() else None}
signal.alarm(0);print(json.dumps(result))
'''
if __name__=='__main__':
 output=Path(sys.argv[1]);assert not output.exists()
 r=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes',
  '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119',
  '/root/by-bot/.venv/bin/python -B -'],input=REMOTE.encode(),capture_output=True,timeout=50)
 if r.returncode:print('PROVENANCE_READ_FAILED exit='+str(r.returncode));raise SystemExit(r.returncode)
 assert len(r.stdout)<1000000
 d={'query_sha256':hashlib.sha256(REMOTE.encode()).hexdigest(),'response':json.loads(r.stdout)}
 with output.open('x') as f:json.dump(d,f,indent=2);f.write('\n')
 print(json.dumps(d['response']))
