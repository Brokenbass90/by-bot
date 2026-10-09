"""Opening read-only broker/source/writer observation; no broker or remote writes."""
import base64,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
EXTRA=r'''
from pathlib import Path
import fcntl,hashlib,json,os,subprocess,time,sqlite3
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
base=Path('/root/by-bot');legacy=base/'runtime/alpaca_intended_paper'
paths=['runtime/alpaca_intended_paper/legacy_preserve.sh','scripts/run_alpaca_adaptive_paper.sh','scripts/run_equities_alpaca_monthly_autopilot.sh','configs/alpaca_live_v38_safe_hold.env']
sources={}
for relative in paths:
 p=base/relative;raw=p.read_bytes();assert len(raw)<100000
 # Credentials are never part of the returned configuration/source inventory.
 if relative.endswith('.env'):sources[relative]={'sha256':sha(p),'flags':[s for s in raw.decode().splitlines() if s.startswith(('ALPACA_SEND_ORDERS=','ALPACA_ALLOW_NEW_ENTRIES=','ALPACA_ALLOW_ROTATION='))]}
 else:sources[relative]={'sha256':sha(p),'raw':raw.decode()}
processes=[]
for d in Path('/proc').iterdir():
 if not d.name.isdigit():continue
 try:
  raw=(d/'cmdline').read_bytes();args=raw.decode().split('\0');env=(d/'environ').read_bytes().decode().split('\0')
  selected=any('alpaca' in a.lower() for a in args) or any(x.startswith(('ALPACA_API_KEY_ID=','ALPACA_BASE_URL=')) for x in env)
  if selected:processes.append({'pid':int(d.name),'cmdline_sha256':hashlib.sha256(raw).hexdigest(),'paths':[a for a in args if a.endswith(('.py','.sh','.env')) and not a.startswith('-')],'send_orders':'--send-orders' in args,'base_url':next((x.split('=',1)[1] for x in env if x.startswith('ALPACA_BASE_URL=')),None)})
 except (FileNotFoundError,PermissionError,ProcessLookupError,UnicodeError):continue
lock=Path('/root/by-bot/runtime/locks/alpaca_bridge_5cec021eb9d04382.lock')
fd=os.open(lock,os.O_RDONLY|os.O_NOFOLLOW)
try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);lock_available=True
finally:os.close(fd)
old=Path('/opt/bybot-research/alpaca-dynamic-v1-20261006-paperintake-v2/runtime/closed_source.json');raw=old.read_bytes();assert len(raw)<20000000
print(json.dumps({'observed_ms':time.time_ns()//1000000,'source_writers':sources,'matching_processes':processes,'shared_lock_available':lock_available,'shared_lock_path':str(lock),'closed_source':{'sha256':sha(old),'raw':raw.decode()},'broker_writes':0,'remote_writes':0}))
'''
sources={p:(ROOT/p).read_text() for p in ['reports/evidence/money_morning_20261008/alpaca_broker_read_only.py','reports/evidence/money_morning_20261008/alpaca_quote_lineage_read_only.py']}
sources['opening_writer_sources']=EXTRA
encoded=base64.b64encode(json.dumps(sources).encode()).decode()
remote="import base64,contextlib,io,json\nsources=json.loads(base64.b64decode("+repr(encoded)+"));r={}\nfor name,code in sources.items():\n out=io.StringIO()\n with contextlib.redirect_stdout(out):exec(compile(code,name,'exec'),{})\n r[name]=json.loads(out.getvalue())\nprint(json.dumps(r))\n"
out=Path(sys.argv[1]);assert not out.exists() and out.parent.is_dir()
p=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119','/root/by-bot/.venv/bin/python -B -'],input=remote.encode(),capture_output=True,timeout=110)
if p.returncode:sys.stderr.write(p.stderr.decode()[-1500:]);raise SystemExit(p.returncode)
assert len(p.stdout)<22000000
data={'capture_source_pins':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},'response':json.loads(p.stdout)}
raw=(json.dumps(data,indent=2)+'\n').encode()
with out.open('xb') as f:os.chmod(out,0o600);f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps({'path':str(out),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'broker_writes':0,'remote_writes':0}))
