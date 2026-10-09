"""Exact post-attempt broker/state readback; no sends or state changes."""
import json,os,subprocess,sys
from pathlib import Path
remote=r'''
from pathlib import Path
import hashlib,json,sqlite3,time
from dotenv import dotenv_values
import urllib.request
from io import StringIO
base=Path('/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007');out={'observed_ms':time.time_ns()//1000000,'broker_writes':0,'remote_writes':0}
for label,path in [('book',base/'runtime/rehearsal/replacement.sqlite'),('paper',base/'runtime/broker_paper/paper.sqlite')]:
 with sqlite3.connect(path.absolute().as_uri()+'?mode=ro',uri=True) as db:
  out[label]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'intents':db.execute('SELECT * FROM intents').fetchall()}
for label,profile,host in [('paper','/root/by-bot/configs/alpaca_paper_local.env','https://paper-api.alpaca.markets'),('live','/root/by-bot/configs/alpaca_live_v38.env','https://api.alpaca.markets')]:
 env=dotenv_values(profile);assert env['ALPACA_BASE_URL'].rstrip('/')==host
 reqs={}
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs):raise ValueError('REDIRECT_REFUSED')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 paths={'account':'/v2/account','positions':'/v2/positions','orders':'/v2/orders?status=open&limit=100&nested=true'}
 if label=='paper':
  paths['entry_cid']='/v2/orders:by_client_order_id?client_order_id=dyp-6f5db25236e869c2939c2201ed41e797'
 for k,path in paths.items():
  request=urllib.request.Request(host+path,method='GET',headers={'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
  try:
   with opener.open(request,timeout=7) as r:raw=r.read(1000001)
   assert len(raw)<1000000;reqs[k]={'raw':raw.decode(),'sha256':hashlib.sha256(raw).hexdigest(),'receive_ms':time.time_ns()//1000000}
  except urllib.error.HTTPError as exc:reqs[k]={'http_status':exc.code,'receive_ms':time.time_ns()//1000000}
 out[label+'_broker']=reqs
out['source_manifests']={}
for root in ['/opt/bybot-research/alpaca-rearm-isolation-20261007-r2/app','/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/app']:
 app=Path(root);manifest=json.loads((app/'source_manifest.json').read_text());out['source_manifests'][root]={'files':len(manifest),'mismatches':[p for p,h in manifest.items() if hashlib.sha256((app/p).read_bytes()).hexdigest()!=h]}
from pathlib import Path
binding=json.loads(Path('/root/by-bot/runtime/alpaca_intended_live/binding.json').read_text());halt=Path(binding['account_lock_path']).with_suffix('.paper-kill')/'.paper-entry-halt.json';out['live_halt']=json.loads(halt.read_text())
print(json.dumps(out))
'''
p=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119','/root/by-bot/.venv/bin/python -B -'],input=remote.encode(),capture_output=True,timeout=80)
if p.returncode:sys.stderr.write(p.stderr.decode()[-2000:]);raise SystemExit(p.returncode)
r=json.loads(p.stdout);out=Path(sys.argv[1])
with out.open('x') as f:os.chmod(out,0o600);json.dump(r,f,indent=2);f.write('\n')
print(json.dumps({'observed_ms':r['observed_ms'],'paper_intents':len(r['paper']['intents']),'reserved_intents':len(r['book']['intents']),'live_halt':r['live_halt']['halted'],'broker_writes':0,'remote_writes':0}))
