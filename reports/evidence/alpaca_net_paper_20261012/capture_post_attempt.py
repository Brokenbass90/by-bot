"""One bounded GET/SQLite-RO NET session readback after the opening window.

Never execute the opener/guard, acquire their lock, prepare, restart or dispatch.
Private raw evidence is saved exclusively; credentials are never printed/saved.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REMOTE = r'''
import hashlib,json,os,signal,sqlite3,subprocess,time,urllib.request,urllib.error
from pathlib import Path
from dotenv import dotenv_values
signal.alarm(80)
assert time.time_ns()//1000000 >= 1791812100000, 'POST_WINDOW_ONLY'
sha=lambda b:hashlib.sha256(b).hexdigest()
session=Path('/opt/bybot-research/alpaca-net-paper-session-20261012')
raw=(session/'session/packet.json').read_bytes();packet=json.loads(raw)
assert packet['symbol']=='NET' and packet['open_ms']==1791811800000
out={'started_ms':time.time_ns()//1000000,'packet_sha256':sha(raw),'packet':packet,
     'broker_writes':0,'remote_writes':0,'runtime':{},'databases':{},'services':{}}
for relative in ['runtime/install_receipt.json','runtime/opening/prepared.json',
 'runtime/opening/ready.json','runtime/opening/fresh.json','runtime/opening/reserve.json',
 'runtime/opening/invoking_adapter.json','runtime/opening/terminal.json',
 'runtime/guard/latest.json','runtime/guard/terminal.json']:
 p=session/relative
 if p.exists():
  assert p.is_file() and not p.is_symlink() and p.stat().st_size<1000000
  b=p.read_bytes();out['runtime'][relative]={'sha256':sha(b),'payload':json.loads(b)}
 else:out['runtime'][relative]=None
for label,path in [('book',Path(packet['source_book'])),
                   ('paper',Path(packet['paper_runtime'])/'paper.sqlite')]:
 with sqlite3.connect(path.absolute().as_uri()+'?mode=ro',uri=True,timeout=3) as db:
  db.execute('BEGIN')
  tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  selected={}
  for table in ['meta','rankings','slots','intents','exits','intent_retirements','intent_attempts']:
   if table in tables:
    selected[table]={'columns':[r[1] for r in db.execute('PRAGMA table_info('+table+')')],
                     'rows':db.execute('SELECT * FROM '+table+' ORDER BY 1 LIMIT 1000').fetchall(),
                     'count':db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]}
  out['databases'][label]={'path':str(path),'tables':selected}
runtime=Path(packet['paper_runtime']);out['paper_runtime']={}
for p in sorted(runtime.glob('*.json')):
 assert p.is_file() and not p.is_symlink() and p.stat().st_size<1000000
 b=p.read_bytes();out['paper_runtime'][p.name]={'sha256':sha(b),'payload':json.loads(b)}
out['paper_runtime_file_names']=sorted(p.name for p in runtime.iterdir())
for label,host,profile in [('paper','https://paper-api.alpaca.markets',packet['paper_env']),
                           ('live','https://api.alpaca.markets',packet['live_env'])]:
 env=dotenv_values(profile);assert env['ALPACA_BASE_URL'].rstrip('/')==host
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args,**kwargs):raise ValueError('REDIRECT_REFUSED')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 paths={'account':'/v2/account','positions':'/v2/positions',
        'open_orders':'/v2/orders?status=open&limit=100&nested=true'}
 if label=='paper':
  paths['net_orders']='/v2/orders?status=all&symbols=NET&after=2026-10-12T00%3A00%3A00Z&limit=100&direction=asc&nested=true'
  paths['net_position']='/v2/positions/NET'
  paths['fills']='/v2/account/activities/FILL?after=2026-10-12T00%3A00%3A00Z&direction=asc&page_size=100'
 out[label+'_broker']={}
 for name,path in paths.items():
  req=urllib.request.Request(host+path,method='GET',headers={
   'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
  try:
   with opener.open(req,timeout=7) as response:b=response.read(1000001)
   assert len(b)<1000000
   out[label+'_broker'][name]={'payload':json.loads(b),'sha256':sha(b),
                             'receive_ms':time.time_ns()//1000000,'http_status':200}
  except urllib.error.HTTPError as exc:
   out[label+'_broker'][name]={'http_status':exc.code,'receive_ms':time.time_ns()//1000000}
binding=json.loads(Path('/root/by-bot/runtime/alpaca_intended_live/binding.json').read_bytes())
halt=Path(binding['account_lock_path']).with_suffix('.paper-kill')/'.paper-entry-halt.json'
out['live_halt']=json.loads(halt.read_bytes())
exclusions=Path('/root/by-bot/runtime/alpaca_intended_paper/legacy_exclusions.json').read_bytes()
out['legacy_exclusions']={'sha256':sha(exclusions),'payload':json.loads(exclusions)}
for name in ['alpaca-net-paper-open-20261012.service','alpaca-net-paper-guard-20261012.service',
             'bybot.service','trading-journal-web.service','att1-lifecycle-zero-risk-v2.service']:
 r=subprocess.run(['systemctl','show',name,'-p','MainPID','-p','NRestarts','-p','ActiveState',
  '-p','SubState','-p','ExecMainStatus','-p','Restart'],capture_output=True,text=True,timeout=5)
 assert r.returncode==0
 out['services'][name]=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
manifest_raw=(session/'app/source_manifest.json').read_bytes();manifest=json.loads(manifest_raw)
out['app_manifest']={'sha256':sha(manifest_raw),'files':len(manifest),
 'mismatches':[p for p,h in manifest.items() if sha((session/'app'/p).read_bytes())!=h]}
out['logs']={}
for name in ['open.log','guard.log']:
 p=session/'runtime'/name
 if p.exists():
  b=p.read_bytes();out['logs'][name]={'sha256':sha(b),'bytes':len(b),'tail':b.decode()[-10000:]}
out['observed_ms']=time.time_ns()//1000000
signal.alarm(0)
print(json.dumps(out))
'''

if __name__ == '__main__':
    assert time.time_ns()//1000000 >= 1791812100000, 'POST_WINDOW_ONLY'
    output = Path(sys.argv[1])
    assert output.parent.is_dir() and not output.exists()
    call = subprocess.run([
        'ssh', '-i', str(Path.home()/'.ssh/by-bot'), '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
        'root@64.226.73.119', '/root/by-bot/.venv/bin/python -B -',
    ], input=REMOTE.encode(), capture_output=True, timeout=100)
    if call.returncode:
        print('READBACK_FAILED exit='+str(call.returncode), file=sys.stderr)
        raise SystemExit(call.returncode)
    assert len(call.stdout) < 5000000
    response = json.loads(call.stdout)
    capture = {'query_sha256':hashlib.sha256(REMOTE.encode()).hexdigest(),
               'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'response':response}
    fd = os.open(output, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    with os.fdopen(fd,'w') as handle:
        json.dump(capture, handle, indent=2);handle.write('\n')
    terminal=response['runtime'].get('runtime/opening/terminal.json')
    print(json.dumps({'capture_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'observed_ms':response['observed_ms'],'terminal':terminal,
        'broker_writes':0,'remote_writes':0,'app_mismatches':response['app_manifest']['mismatches']}))
