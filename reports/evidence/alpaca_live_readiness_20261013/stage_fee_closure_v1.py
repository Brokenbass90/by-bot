"""Stage only NEW inert closure tooling below the approved isolated base.

No app overwrite, broker GET/write, cron/profile/service/HALT change or runtime
reservation. Run the installed verifier in --verify-only, never the fee reader.
"""
import hashlib
import json
from pathlib import Path
from shlex import quote
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_dynamic_v1 import canonical
from research_lab.alpaca_live_readiness_v1 import write_new

REMOTE=r'''
import base64,hashlib,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
signal.alarm(60)
p=json.load(sys.stdin);base=Path('/opt/bybot-research/alpaca-dynamic-live-20261013')
kit=base/'control/fee-to-live-v1'
sha=lambda b:hashlib.sha256(b).hexdigest()
assert p['schema']=='ALPACA_FEE_TO_LIVE_STAGE_PAYLOAD_V1' and p['base']==str(kit)
assert not kit.exists() and not any(x.is_symlink() for x in (kit,*kit.parents)),'NEW_INERT_KIT_ONLY'
handoff_raw=(base/'control/handoff_v2_receipt.json').read_bytes();handoff=json.loads(handoff_raw)
custody_path=base/'session/static_custody_pending_v2.json';custody_raw=custody_path.read_bytes();custody=json.loads(custody_raw)
halt=Path(custody['halt_path']);halt_raw=halt.read_bytes();assert json.loads(halt_raw)['halted'] is True
def cli(args):
 r=subprocess.run(args,capture_output=True,timeout=6);assert r.returncode==0;return r.stdout
cron=cli(['crontab','-l']);assert sha(cron)==handoff['cron_after_sha256']
for row in handoff['deployment']['source_files']+custody['source_files']:
 q=Path(row['path']);assert q.is_file() and not any(x.is_symlink() for x in (q,*q.parents)) and sha(q.read_bytes())==row['sha256']
def services():
 return {n:cli(['systemctl','show',n,'-p','MainPID','-p','NRestarts','-p','ActiveState']).decode()
   for n in ('bybot.service','trading-journal-web.service','att1-lifecycle-zero-risk-v2.service')}
before=services()
for d in (base/'disabled-unit-templates',base/'unapproved-activation-templates'):
 for q in d.iterdir():assert not any((Path(r)/q.name).exists() for r in ('/etc/systemd/system','/run/systemd/system','/lib/systemd/system'))
assert not (base/'session/owner-go.json').exists() and not (base/'session/intake.json').exists()
assert len(p['files'])<=40 and sum(len(x['content_b64']) for x in p['files'].values())<8000000
with tempfile.TemporaryDirectory(prefix='fee-closure-stage-',dir=base/'control') as temp:
 stage=Path(temp)
 for name,row in p['files'].items():
  assert '/' not in name and name not in ('.','..') and name.endswith(('.py','.json'))
  raw=base64.b64decode(row['content_b64'],validate=True);assert sha(raw)==row['sha256']
  if name.endswith('.py'):compile(raw,name,'exec')
  fd=os.open(stage/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as f:f.write(raw)
 os.rename(stage,kit)
check=subprocess.run(['/root/by-bot/.venv/bin/python','-B',str(kit/'observe-close-once.py'),p['kit_sha256'],'--verify-only'],capture_output=True,timeout=35)
assert check.returncode==0,'INERT_STATIC_VERIFICATION_FAILED:'+check.stderr.decode()[-600:]
result=json.loads(check.stdout);assert result['status']=='FEE_TO_LIVE_STATIC_PINS_VERIFIED_NOT_OBSERVED'
assert cli(['crontab','-l'])==cron and halt.read_bytes()==halt_raw and custody_path.read_bytes()==custody_raw
assert (base/'control/handoff_v2_receipt.json').read_bytes()==handoff_raw and services()==before
for row in handoff['deployment']['source_files']+custody['source_files']:assert sha(Path(row['path']).read_bytes())==row['sha256']
print(json.dumps(dict(status='FEE_TO_LIVE_STATIC_KIT_STAGED_ORDERS_OFF',kit_sha256=p['kit_sha256'],
 observed_ms=time.time_ns()//1000000,files=len(p['files']),verification=result,
 original_app_custody_cron_halt_production_unchanged=True,broker_queries=0,broker_writes=0,
 service_activations=0,lock_acquisitions=0,orders_allowed=False)))
signal.alarm(0)
'''


def main(payload_file):
    path=Path(payload_file).absolute();private=ROOT/'.private/alpaca_live_readiness_20261013'
    assert path.parent==private and not any(p.is_symlink() for p in (path,*path.parents))
    payload=json.loads(path.read_bytes())
    output=private/('fee_to_live_stage_capture_'+payload['kit_sha256'][:12]+'.json')
    assert not output.exists(),'NO_STAGE_RETRY'
    call=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119',
        '/root/by-bot/.venv/bin/python -B -c '+quote(REMOTE)],input=canonical(payload),capture_output=True,timeout=90)
    if call.returncode:
        print(json.dumps(dict(status='INERT_STAGE_FAILED_NO_RETRY',exit=call.returncode,stderr_sha256=hashlib.sha256(call.stderr).hexdigest())))
        return 2
    capture=dict(query_sha256=hashlib.sha256(REMOTE.encode()).hexdigest(),response=json.loads(call.stdout))
    write_new(output,canonical(capture));print(json.dumps(capture['response']));return 0


if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
