"""Invoke only the existing scoped PAPER runner: GET rehearsal, then one submit."""
import json,os,subprocess,sys
from pathlib import Path
remote=r'''
import json,subprocess,time
from pathlib import Path
base=Path('/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007')
common=['/root/by-bot/.venv/bin/python','-B','scripts/run_alpaca_dynamic_paper.py','--plan',str(base/'runtime/opening_oct9/plan.json'),'--plan-store',str(base/'runtime/rehearsal/replacement.sqlite'),'--paper-env','/root/by-bot/configs/alpaca_paper_local.env','--paper-account','4cdbfb77-d1e0-4789-86b2-341bc886efaf','--runtime',str(base/'runtime/broker_paper')]
assert 1791552600000<=time.time_ns()//1000000<1791552900000
p=subprocess.run(common+['--output',str(base/'runtime/opening_oct9/paper_read_only.json')],cwd=base/'app',capture_output=True,text=True,timeout=35)
ready=json.loads(p.stdout);out={'read_only':ready,'read_only_exit':p.returncode}
if p.returncode==0 and ready['status']=='PAPER_READ_ONLY_READY':
 assert time.time_ns()//1000000<1791552900000
 p=subprocess.run(common+['--paper-submit','--output',str(base/'runtime/opening_oct9/paper_submit.json')],cwd=base/'app',capture_output=True,text=True,timeout=80)
 out.update(submit=json.loads(p.stdout),submit_exit=p.returncode)
print(json.dumps(out))
'''
p=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119','/root/by-bot/.venv/bin/python -B -'],input=remote.encode(),capture_output=True,timeout=125)
if p.returncode:sys.stderr.write(p.stderr.decode()[-2000:]);raise SystemExit(p.returncode)
r=json.loads(p.stdout);out=Path(sys.argv[1])
with out.open('x') as f:os.chmod(out,0o600);json.dump(r,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
print(json.dumps(r))
