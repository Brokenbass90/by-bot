"""Bounded file/process inventory. No broker request, lock, write or restart."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

REMOTE = r'''
import hashlib,json,signal,subprocess,time
from pathlib import Path
from dotenv import dotenv_values
signal.alarm(45)
sha=lambda raw:hashlib.sha256(raw).hexdigest()
root=Path('/root/by-bot')
out=dict(broker_writes=0,remote_writes=0,lock_acquisitions=0,profiles={},writers={},cron={},units={},processes=[],services={})
for name in ['configs/alpaca_live_v38.env','configs/alpaca_paper_local.env','runtime/alpaca_intended_live/profile.env']:
 p=root/name;raw=p.read_bytes();env=dotenv_values(p,interpolate=False)
 out['profiles'][name]={'sha256':sha(raw),'base_url':env.get('ALPACA_BASE_URL'),
  'flags':{k:env.get(k) for k in ['ALPACA_ALLOW_NEW_ENTRIES','ALPACA_ALLOW_ROTATION','ALPACA_SEND_ORDERS','ALPACA_BRIDGE_LOCK_PATH','ALPACA_PROTECTIVE_EXIT_HWM_PATH']}}
 if name=='configs/alpaca_live_v38.env':
  host=env['ALPACA_BASE_URL'];assert host=='https://api.alpaca.markets'
  out['original_live_lock']=env.get('ALPACA_BRIDGE_LOCK_PATH') or str(root/'runtime/locks'/('alpaca_bridge_'+sha((host+'|'+env['ALPACA_API_KEY_ID']).encode())[:16]+'.lock'))
for name in ['runtime/alpaca_intended_live/binding.json','runtime/alpaca_intended_live/run.sh',
 'runtime/alpaca_intended_paper/legacy_preserve.sh','scripts/run_alpaca_adaptive_paper.sh',
 'scripts/run_equities_alpaca_monthly_autopilot.sh','configs/alpaca_live_v38_safe_hold.env',
 'scripts/equities_alpaca_paper_bridge.py','scripts/alpaca_protective_exit_manager.py']:
 p=root/name;raw=p.read_bytes();assert len(raw)<3000000 and not p.is_symlink()
 out['writers'][name]={'sha256':sha(raw),'bytes':len(raw)}
 if name.endswith('binding.json'):out['original_live_binding']=json.loads(raw)
 if name.endswith('run.sh'):out['old_live_wrapper']=raw.decode()
for directory in ['/var/spool/cron/crontabs','/etc/cron.d','/etc/cron.hourly','/etc/cron.daily']:
 d=Path(directory);rows={}
 if d.exists():
  for p in d.iterdir():
   if not p.is_file() or p.is_symlink() or p.stat().st_size>100000:continue
   raw=p.read_bytes();rows[p.name]={'sha256':sha(raw),'bytes':len(raw),'contains_alpaca':b'alpaca' in raw.lower()}
 out['cron'][directory]=rows
r=subprocess.run(['systemctl','list-unit-files','--no-pager','--plain'],capture_output=True,text=True,timeout=5);assert r.returncode==0
for line in r.stdout.splitlines():
 parts=line.split()
 if not parts or 'alpaca' not in parts[0].lower():continue
 name=parts[0]
 r=subprocess.run(['systemctl','cat',name],capture_output=True,timeout=5);assert r.returncode==0
 out['units'][name]={'sha256':sha(r.stdout),'unit_text':r.stdout.decode(),'enabled_state':parts[1]}
for d in Path('/proc').iterdir():
 if not d.name.isdigit():continue
 try:
  raw=(d/'cmdline').read_bytes();args=raw.decode().split('\0')
  env=(d/'environ').read_bytes().decode().split('\0')
  if any('alpaca' in a.lower() for a in args) or any(s.startswith('ALPACA_BASE_URL=') for s in env):
   out['processes'].append({'pid':int(d.name),'cmdline_sha256':sha(raw),
    'scripts':[a for a in args if a.endswith(('.py','.sh'))],
    'send_orders':'--send-orders' in args,'apply':'--apply' in args,
    'base_url':next((s.split('=',1)[1] for s in env if s.startswith('ALPACA_BASE_URL=')),None)})
 except (FileNotFoundError,ProcessLookupError,PermissionError,UnicodeError):continue
for name in ['alpaca-net-paper-guard-20261012.service','alpaca-net-paper-open-20261012.service',
 'bybot.service','trading-journal-web.service','att1-lifecycle-zero-risk-v2.service']:
 r=subprocess.run(['systemctl','show',name,'-p','MainPID','-p','NRestarts','-p','ActiveState','-p','Restart'],capture_output=True,text=True,timeout=5);assert r.returncode==0
 out['services'][name]=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
out['new_live_base_exists']=Path('/opt/bybot-research/alpaca-dynamic-live-20261013').exists()
out['observed_ms']=time.time_ns()//1000000
signal.alarm(0)
print(json.dumps(out))
'''


def main(output):
    assert output.parent.is_dir() and not output.exists()
    assert not any(p.is_symlink() for p in (output, *output.absolute().parents))
    r = subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119',
        '/root/by-bot/.venv/bin/python -B -'],input=REMOTE.encode(),capture_output=True,timeout=70)
    if r.returncode:
        print('READ_ONLY_INVENTORY_FAILED exit='+str(r.returncode),file=sys.stderr)
        raise SystemExit(r.returncode)
    assert len(r.stdout)<3000000
    out=dict(query_sha256=hashlib.sha256(REMOTE.encode()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),response=json.loads(r.stdout))
    fd=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as handle:json.dump(out,handle,indent=2);handle.write('\n')
    print(json.dumps(dict(capture_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        observed_ms=out['response']['observed_ms'],broker_writes=0,remote_writes=0,lock_acquisitions=0)))


if __name__=='__main__':main(Path(sys.argv[1]))
