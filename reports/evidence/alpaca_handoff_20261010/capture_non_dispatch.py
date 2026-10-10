"""Extend the archived GET-only readback with missing retirement/writer evidence.

No server files, broker orders or services are mutated. Raw capture is private.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
old=ROOT/'reports/evidence/alpaca_opening_20261009/read_postcheck.py'
tree=ast.parse(old.read_text())
remote=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='remote' for t in n.targets))
assert remote.endswith('print(json.dumps(out))\n')
extra=r'''
import fcntl,os,subprocess
legacy=Path('/opt/bybot-research/alpaca-intended-paper/app')
manifest_raw=(legacy/'source_manifest.json').read_bytes();manifest=json.loads(manifest_raw)
out['source_manifests'][str(legacy)]={'files':len(manifest),'mismatches':[p for p,h in manifest.items() if hashlib.sha256((legacy/p).read_bytes()).hexdigest()!=h]}
for root in out['source_manifests']:
 out['source_manifests'][root]['manifest_sha256']=hashlib.sha256((Path(root)/'source_manifest.json').read_bytes()).hexdigest()
exclusions=Path('/root/by-bot/runtime/alpaca_intended_paper/legacy_exclusions.json').read_bytes()
out['legacy_exclusions']={'sha256':hashlib.sha256(exclusions).hexdigest(),'payload':json.loads(exclusions)}
with sqlite3.connect((base/'runtime/rehearsal/replacement.sqlite').absolute().as_uri()+'?mode=ro',uri=True) as db:
 tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 out['book']['retirements']=db.execute('SELECT * FROM intent_retirements').fetchall() if 'intent_retirements' in tables else []
 out['book']['attempts']=db.execute('SELECT * FROM intent_attempts').fetchall() if 'intent_attempts' in tables else []
 original={t:db.execute('SELECT * FROM '+t+' ORDER BY 1').fetchall() for t in ['meta','rankings','slots','intents','exits']}
 out['book']['original_table_sha256']=hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
plan=json.loads(out['book']['intents'][0][2]);assert len(out['book']['intents'])==1
paper_account=json.loads(out['paper_broker']['account']['raw'])['id']
canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
identity=hashlib.sha256(canonical({'parent':plan['receipt_id'],'paper_account':paper_account})).hexdigest()
assert 'dyp-'+identity[:32]=='dyp-6f5db25236e869c2939c2201ed41e797'
env=dotenv_values('/root/by-bot/configs/alpaca_paper_local.env');host='https://paper-api.alpaca.markets'
assert env['ALPACA_BASE_URL'].rstrip('/')==host
stop_cid='dys-'+identity[:32]
req=urllib.request.Request(host+'/v2/orders:by_client_order_id?client_order_id='+stop_cid,method='GET',headers={'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
try:
 with opener.open(req,timeout=5) as response:body=response.read(1000001)
 assert len(body)<1000000;stop={'raw':body.decode(),'receive_ms':time.time_ns()//1000000}
except urllib.error.HTTPError as exc:stop={'http_status':exc.code,'receive_ms':time.time_ns()//1000000}
out['retirement_extra']={'entry_cid':'dyp-'+identity[:32],'stop_cid':stop_cid,'stop_source':stop,
 'paper_hwm_present':(base/'runtime/broker_paper/protective_exit_hwm.json').exists(),
 'paper_runtime_files':sorted(p.name for p in (base/'runtime/broker_paper').iterdir())}
lock=Path('/root/by-bot/runtime/locks/alpaca_bridge_5cec021eb9d04382.lock')
fd=os.open(lock,os.O_RDONLY|os.O_NOFOLLOW)
try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);out['shared_lock_available']=True
finally:os.close(fd)
cr=subprocess.run(['crontab','-l'],capture_output=True,timeout=5)
assert cr.returncode==0
out['root_crontab']={'raw':cr.stdout.decode(),'sha256':hashlib.sha256(cr.stdout).hexdigest()}
out['writer_sources']={}
for relative in ['runtime/alpaca_intended_paper/legacy_preserve.sh','scripts/run_alpaca_adaptive_paper.sh','scripts/run_equities_alpaca_monthly_autopilot.sh','configs/alpaca_live_v38_safe_hold.env']:
 p=Path('/root/by-bot')/relative;raw=p.read_bytes();assert len(raw)<100000
 out['writer_sources'][relative]={'sha256':hashlib.sha256(raw).hexdigest(),
  'raw':raw.decode() if not relative.endswith('.env') else None,
  'flags':[s for s in raw.decode().splitlines() if s.startswith(('ALPACA_SEND_ORDERS=','ALPACA_ALLOW_NEW_ENTRIES=','ALPACA_ALLOW_ROTATION='))]}
out['matching_processes']=[]
for d in Path('/proc').iterdir():
 if not d.name.isdigit():continue
 try:
  raw=(d/'cmdline').read_bytes();args=raw.decode().split('\0');e=(d/'environ').read_bytes().decode().split('\0')
  if any('alpaca' in a.lower() for a in args) or any(s.startswith(('ALPACA_API_KEY_ID=','ALPACA_BASE_URL=')) for s in e):
   out['matching_processes'].append({'pid':int(d.name),'cmdline_sha256':hashlib.sha256(raw).hexdigest(),
    'paths':[a for a in args if a.endswith(('.sh','.py','.env'))],
    'send_orders':'--send-orders' in args,'base_url':next((s.split('=',1)[1] for s in e if s.startswith('ALPACA_BASE_URL=')),None)})
 except (FileNotFoundError,ProcessLookupError,PermissionError,UnicodeError):continue
out['services']={}
for name in ['bybot.service','trading-journal-web.service','att1-lifecycle-zero-risk-v2.service']:
 p=subprocess.run(['systemctl','show',name,'-p','MainPID','-p','NRestarts','-p','ActiveState'],capture_output=True,timeout=5)
 assert p.returncode==0;out['services'][name]=p.stdout.decode().splitlines()
out['observed_ms']=time.time_ns()//1000000
if out['book']['retirements']:
 assert len(out['book']['retirements'])==1 and not out['book']['attempts']
 receipt_id,raw=out['book']['retirements'][0];retired=json.loads(raw)
 assert retired['status']=='EXPIRED_NEVER_DISPATCHED' and retired['receipt_id']==plan['receipt_id']==receipt_id
 assert retired['original_plan_sha256']==hashlib.sha256(canonical(plan)).hexdigest()
 assert retired['proof_sha256']==hashlib.sha256(canonical(retired['proof'])).hexdigest()
 out['retirement_readback']='ORIGINAL_INTENT_RETAINED_ONE_RETIREMENT_NO_ATTEMPT'
print(json.dumps(out))
'''
remote=remote[:-len('print(json.dumps(out))\n')]+extra
out=Path(sys.argv[1]);assert not out.exists()
p=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes',
 '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119',
 '/root/by-bot/.venv/bin/python -B -'],input=remote.encode(),capture_output=True,timeout=80)
if p.returncode:sys.stderr.write(p.stderr.decode()[-1800:]);raise SystemExit(p.returncode)
assert len(p.stdout)<5000000
capture={'capture_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'parent_capture_script_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),
 'remote_query_sha256':hashlib.sha256(remote.encode()).hexdigest(),'response':json.loads(p.stdout)}
with out.open('x') as f:os.chmod(out,0o600);json.dump(capture,f,indent=2);f.write('\n')
print(json.dumps({'path':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
                 'broker_writes':0,'remote_writes':0,'observed_ms':capture['response']['observed_ms']}))
