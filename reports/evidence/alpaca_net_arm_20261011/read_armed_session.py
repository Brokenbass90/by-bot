"""One GET-only installed-session readback; never prepare/restart or send."""
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
ending='print(json.dumps(out))\n'
remote=literal(ROOT/'reports/evidence/alpaca_opening_20261009/read_postcheck.py','remote')
extra=literal(ROOT/'reports/evidence/alpaca_handoff_20261010/capture_non_dispatch.py','extra')
assert remote.endswith(ending) and extra.endswith(ending)
remote=remote[:-len(ending)]+extra[:-len(ending)]+r'''
import signal
signal.alarm(50)
session=Path('/opt/bybot-research/alpaca-net-paper-session-20261012')
packet_raw=(session/'session/packet.json').read_bytes();packet=json.loads(packet_raw)
out['session']={'packet_sha256':hashlib.sha256(packet_raw).hexdigest(),
 'packet':packet,'static_mismatches':[], 'runtime':{}, 'units':{}, 'logs':{}}
for name,path in packet['static_paths'].items():
 p=Path(path)
 if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=packet['expected_sha256'][name]:
  out['session']['static_mismatches'].append(name)
manifest_raw=(session/'app/source_manifest.json').read_bytes();manifest=json.loads(manifest_raw)
out['session']['manifest']={'sha256':hashlib.sha256(manifest_raw).hexdigest(),'files':len(manifest),
 'mismatches':[n for n,h in manifest.items() if hashlib.sha256((session/'app'/n).read_bytes()).hexdigest()!=h]}
for relative in ['runtime/install_receipt.json','runtime/opening/prepared.json','runtime/opening/ready.json',
 'runtime/opening/terminal.json','runtime/opening/reserve.json','runtime/opening/invoking_adapter.json',
 'runtime/guard/latest.json','runtime/guard/terminal.json']:
 p=session/relative
 out['session']['runtime'][relative]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'payload':json.loads(p.read_bytes())} if p.exists() else None
for name in ['alpaca-net-paper-open-20261012.service','alpaca-net-paper-guard-20261012.service']:
 result=subprocess.run(['systemctl','show',name,'-p','MainPID','-p','NRestarts','-p','ActiveState','-p','SubState','-p','ExecMainStatus','-p','Restart','-p','UnitFileState'],capture_output=True,text=True,timeout=5)
 assert result.returncode==0
 fields=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
 pid=int(fields['MainPID']);fields['process_alive']=pid>0 and Path('/proc',str(pid)).exists()
 if fields['process_alive']:
  raw=Path('/proc',str(pid),'cmdline').read_bytes()
  fields['cmdline_sha256']=hashlib.sha256(raw).hexdigest()
  fields['args']=raw.decode().split('\0')
  fields['cwd']=os.readlink('/proc/'+str(pid)+'/cwd')
 out['session']['units'][name]=fields
for n in ['targeted_tests.txt','targeted_tests_completed.txt','open.log','guard.log']:
 p=session/'runtime'/n
 if p.exists():
  raw=p.read_bytes()
  out['session']['logs'][n]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'tail':raw.decode()[-2000:]}
out['session']['review_sha256']=hashlib.sha256((session/'session/review.json').read_bytes()).hexdigest()
out['profile_source_pins']={n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in [packet['paper_env'],packet['live_env']]}
live=Path('/root/by-bot/runtime/alpaca_intended_live')
out['live_runtime_pins']={n:hashlib.sha256((live/n).read_bytes()).hexdigest() for n in ['binding.json','profile.env','run.sh']}
out['root_cron_file_sha256']=hashlib.sha256(Path('/var/spool/cron/crontabs/root').read_bytes()).hexdigest()
out['observed_ms']=time.time_ns()//1000000
signal.alarm(0)
print(json.dumps(out))
'''
out=Path(sys.argv[1]);assert not out.exists()
p=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes',
 '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119',
 '/root/by-bot/.venv/bin/python -B -'],input=remote.encode(),capture_output=True,timeout=100)
if p.returncode:sys.stderr.write(p.stderr.decode()[-2000:]);raise SystemExit(p.returncode)
assert len(p.stdout)<5000000
capture={'capture_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'remote_query_sha256':hashlib.sha256(remote.encode()).hexdigest(),'response':json.loads(p.stdout)}
with out.open('x') as f:os.chmod(out,0o600);json.dump(capture,f,indent=2);f.write('\n')
print(json.dumps({'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),
 'observed_ms':capture['response']['observed_ms'],'broker_writes':0,'remote_writes':0,
 'static_mismatches':capture['response']['session']['static_mismatches'],
 'units':{n:{k:v for k,v in s.items() if k in ['MainPID','ActiveState','NRestarts','process_alive']} for n,s in capture['response']['session']['units'].items()}}))
