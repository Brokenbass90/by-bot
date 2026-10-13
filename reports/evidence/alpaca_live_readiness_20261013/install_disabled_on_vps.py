"""Owner-authorized conditional new-app install; zero broker/service writes.

Only after actual original PAPER PASS and October13 14:05 UTC. Inert unit drafts
stay under the new isolated base, never /etc; no systemctl/cron/HALT operation.
The remote helper verifies the exact package and every installed byte, then
returns its physical-source receipt. Credentials/profile contents are not sent.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_dynamic_v1 import canonical,digest
from research_lab.alpaca_dynamic_live_runtime_v1 import read_json
from research_lab.alpaca_live_readiness_v1 import verify_package,POSTCHECK_MS

BOOTSTRAP=r'''
import base64,hashlib,json,os,signal,sys,tempfile,time
from pathlib import Path
signal.alarm(70)
canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
sha=lambda raw:hashlib.sha256(raw).hexdigest()
payload=json.load(sys.stdin);package=payload['package'];paper=payload['paper']
assert time.time_ns()//1000000>=1791900300000,'ORIGINAL_POSTCHECK_NOT_DUE'
assert paper['status']=='PAPER_EXECUTION_PASS'
assert paper['receipt_sha256']==sha(canonical({k:v for k,v in paper.items() if k!='receipt_sha256'}))
assert package['base']=='/opt/bybot-research/alpaca-dynamic-live-20261013'
assert package['orders_allowed'] is False and package['enabled'] is False
assert package['package_sha256']==sha(canonical({k:v for k,v in package.items() if k!='package_sha256'}))
for name in [*package['units'],*package['unapproved_activation_templates']]:
 assert not any((Path(p)/name).exists() for p in ['/etc/systemd/system','/run/systemd/system','/lib/systemd/system']), 'DYNAMIC_UNIT_ALREADY_REGISTERED'
with tempfile.TemporaryDirectory(prefix='alpaca-disabled-stage-20261013-',dir='/opt/bybot-research') as staged:
 app=Path(staged)/'app';app.mkdir(mode=0o700)
 for name,row in package['files'].items():
  p=Path(name)
  assert not p.is_absolute() and '..' not in p.parts and '.private' not in p.parts and not name.endswith('.env')
  raw=base64.b64decode(row['content_b64'],validate=True);assert sha(raw)==row['sha256']
  target=app/p;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as f:f.write(raw)
 sys.path.insert(0,str(app))
 from research_lab.alpaca_live_readiness_v1 import install_disabled,verify_package
 assert sha(Path(sys.modules['research_lab.alpaca_live_readiness_v1'].__file__).read_bytes())==package['files']['research_lab/alpaca_live_readiness_v1.py']['sha256']
 verify_package(package)
 result=install_disabled(package,paper,now_ms=time.time_ns()//1000000)
 result['broker_writes']=0;result['unit_or_service_writes']=0
 print(json.dumps(result))
signal.alarm(0)
'''


def main(package_path,paper_path,output):
    assert time.time_ns()//1000000>=POSTCHECK_MS,'ORIGINAL_POSTCHECK_NOT_DUE'
    package=read_json(str(package_path));paper=read_json(str(paper_path));verify_package(package)
    assert paper['status']=='PAPER_EXECUTION_PASS'
    assert paper['receipt_sha256']==digest({k:v for k,v in paper.items() if k!='receipt_sha256'})
    assert output.parent.is_dir() and not output.exists()
    assert not any(p.is_symlink() for p in (output,*output.absolute().parents))
    # Remote Python takes code in -c and the credential-free bounded input on
    # stdin. Shell receives no JSON, secrets, substitutions or dynamic code.
    from shlex import quote
    command='/root/by-bot/.venv/bin/python -B -c '+quote(BOOTSTRAP)
    r=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119',command],
        input=canonical(dict(package=package,paper=paper)),capture_output=True,timeout=90)
    if r.returncode:
        print('DISABLED_INSTALL_FAILED exit='+str(r.returncode),file=sys.stderr);raise SystemExit(r.returncode)
    receipt=json.loads(r.stdout)
    assert receipt['package_sha256']==package['package_sha256'] and receipt['orders_allowed'] is False
    assert receipt['enabled'] is False and receipt['service_activation_count']==0
    out=dict(query_sha256=hashlib.sha256(BOOTSTRAP.encode()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),deployment=receipt)
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(canonical(out));f.flush();os.fsync(f.fileno())
    print(json.dumps(dict(status=receipt['status'],package_sha256=receipt['package_sha256'],
        enabled=False,orders_allowed=False,broker_writes=0,unit_or_service_writes=0,
        capture_sha256=hashlib.sha256(output.read_bytes()).hexdigest())))


if __name__=='__main__':main(*(Path(p) for p in sys.argv[1:]))
