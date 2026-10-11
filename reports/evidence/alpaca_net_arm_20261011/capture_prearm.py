"""One bounded fresh GET-only read of account/finality/writers and app pins."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
def literal(path,name):
    tree=ast.parse(path.read_bytes())
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
parent=ROOT/'reports/evidence/alpaca_opening_20261009/read_postcheck.py'
companion=ROOT/'reports/evidence/alpaca_handoff_20261010/capture_non_dispatch.py'
ending='print(json.dumps(out))\n'
remote=literal(parent,'remote');extra=literal(companion,'extra')
assert remote.endswith(ending) and extra.endswith(ending)
remote=remote[:-len(ending)]+extra[:-len(ending)]+r'''
import signal
signal.alarm(65)
env=dotenv_values('/root/by-bot/configs/alpaca_live_v38.env')
assert env['ALPACA_BASE_URL'].rstrip('/')=='https://api.alpaca.markets'
for name,path in {
 'asset_NET':'/v2/assets/NET',
 'closed_order_source':'/v2/orders?status=all&after=2026-09-30T00:00:00Z&limit=100&direction=asc',
 'account_activity_source':'/v2/account/activities?after=2026-09-30T00:00:00Z&direction=asc&page_size=100'
}.items():
 req=urllib.request.Request('https://api.alpaca.markets'+path,method='GET',headers={'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
 with opener.open(req,timeout=7) as response:raw=response.read(1000001)
 assert len(raw)<1000000
 if name!='asset_NET':assert len(json.loads(raw))<100,'TRUNCATED_'+name
 out[name]={'raw':raw.decode(),'sha256':hashlib.sha256(raw).hexdigest(),'received_ms':time.time_ns()//1000000}
out['app_source_maps']={root:json.loads((Path(root)/'source_manifest.json').read_bytes()) for root in out['source_manifests']}
out['profile_source_pins']={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in ['/root/by-bot/configs/alpaca_live_v38.env','/root/by-bot/configs/alpaca_paper_local.env']}
live=Path('/root/by-bot/runtime/alpaca_intended_live')
out['live_runtime_pins']={name:hashlib.sha256((live/name).read_bytes()).hexdigest() for name in ['binding.json','profile.env','run.sh']}
out['cron_inventory']={}
for directory in ['/var/spool/cron/crontabs','/etc/cron.d','/etc/cron.hourly','/etc/cron.daily']:
 d=Path(directory);rows={}
 if d.exists():
  for p in d.iterdir():
   if not p.is_file() or p.is_symlink() or p.stat().st_size>100000:continue
   raw=p.read_bytes();rows[p.name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'contains_alpaca':b'alpaca' in raw.lower()}
 out['cron_inventory'][directory]=rows
out['alpaca_units']={}
listed=subprocess.run(['systemctl','list-unit-files','--no-pager','--plain'],capture_output=True,text=True,timeout=5)
assert listed.returncode==0
for line in listed.stdout.splitlines():
 parts=line.split()
 if parts and 'alpaca' in parts[0].lower():
  p=subprocess.run(['systemctl','cat',parts[0]],capture_output=True,timeout=5)
  assert p.returncode==0
  out['alpaca_units'][parts[0]]={'sha256':hashlib.sha256(p.stdout).hexdigest(),'raw':p.stdout.decode()}
out['observed_ms']=time.time_ns()//1000000
signal.alarm(0)
print(json.dumps(out))
'''
out=Path(sys.argv[1]);assert not out.exists() and out.parent.is_dir()
p=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119','/root/by-bot/.venv/bin/python','-B','-'],input=remote.encode(),capture_output=True,timeout=100)
if p.returncode:sys.stderr.write(p.stderr.decode()[-1800:]);raise SystemExit(p.returncode)
assert len(p.stdout)<5000000
raw=json.loads(p.stdout)
capture={'capture_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'remote_query_sha256':hashlib.sha256(remote.encode()).hexdigest(),'response':raw}
with out.open('x') as f:os.chmod(out,0o600);json.dump(capture,f,indent=2);f.write('\n')
print(json.dumps({'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'observed_ms':raw['observed_ms'],
 'live_halted':raw['live_halt']['halted'],'live_positions':len(json.loads(raw['live_broker']['positions']['raw'])),
 'paper_orders':len(json.loads(raw['paper_broker']['orders']['raw'])),'broker_writes':0,'remote_writes':0}))
