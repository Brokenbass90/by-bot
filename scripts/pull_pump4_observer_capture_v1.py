#!/usr/bin/env python3
"""SSH GET of explicitly allowed PUMP4 evidence, never credential/source paths.

Only scope.json, runner.json, selected owner-scope.json, bounded supervisor
receipts and the three named lifecycle journals are opened remotely. A config's
credential_source/source_files are NEVER traversed or opened. No broker client,
activation, service mutation, source repair or financial constructor is invoked.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_lab.pump4_live_observer_v1 import safe_path
from research_lab.os2_shadow_journal import strict_json
from research_lab.os2_shadow_bridge import canonical

SCOPE='fec235e3dea12245d96859a6786d811551f9341d9a860ee4fac88dea4bfcf794'
CONFIG='fa0b3b2ec893f5167d79e71ef7fcf5a1d3788075105a2732663a8dafec53014a'
REMOTE = r'''
from pathlib import Path
import os,stat,json,hashlib,base64,time
packet=Path('/opt/bybot-research/pump4-server-orders-off-20261023/tiny-activation-20261028-v1')
root=Path('/opt/bybot-research/pump4-server-orders-off-20261023/candidate-bfbd987d6137f819/runtime/tiny-one-lifecycle-20261028')
def sha(b):return hashlib.sha256(b).hexdigest()
def scope_hash(b):return sha(json.dumps(json.loads(b),sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode())
def read(p):
 assert not any(x.is_symlink() for x in (p,*p.parents)), 'source_symlink'
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  a=os.fstat(fd);assert stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_size<=16*1024*1024,'source_bound'
  raw=b''
  while len(raw)<a.st_size:
   b=os.read(fd,min(1048576,a.st_size-len(raw)))
   assert b,'source_short_read';raw+=b
  b=os.fstat(fd)
  assert (a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns),'source_changed'
  return raw
 finally:os.close(fd)
scope=read(packet/'scope.json');config=read(packet/'runner.json')
assert scope_hash(scope)=='fec235e3dea12245d96859a6786d811551f9341d9a860ee4fac88dea4bfcf794','scope_pin'
assert sha(config)=='fa0b3b2ec893f5167d79e71ef7fcf5a1d3788075105a2732663a8dafec53014a','config_pin'
assert json.loads(read(root/'owner-scope.json'))==json.loads(scope),'selected_owner_scope'
files=[];payload={};total=0

def add(name,kind,raw,**kw):
 global total
 total+=len(raw);assert total<=64*1024*1024 and len(files)<512,'capture_bound'
 files.append(dict(name=name,kind=kind,sha256=sha(raw),**kw));payload[name]=base64.b64encode(raw).decode()
add('scope.json','scope',scope);add('config.json','config',config)
receipts=sorted((root/'supervisor/receipts').glob('*.json'),key=lambda p:p.stat().st_mtime_ns)[-96:]
for i,p in enumerate(receipts):add('receipt-%03d.json'%i,'receipt',read(p))
streams=sorted(p for p in (root/'flows').rglob('*.jsonl') if p.name in ('execution.jsonl','observations.jsonl','risk.jsonl'))
for i,p in enumerate(streams):
 raw=read(p);end=raw.rfind(b'\n')+1
 add('lifecycle-%03d.jsonl'%i,'lifecycle',raw[:end],partial_tail_bytes=len(raw)-end,source_stream=str(p.relative_to(root)))
m=dict(schema='PUMP4_OBSERVER_CAPTURE_V1',observed_ms=time.time_ns()//1000000,
 scope_sha256=scope_hash(scope),config_sha256=sha(config),files=files,
 coverage='SAMPLED_STATUS_NOT_OPPORTUNITY_CENSUS',
 entry_valid_until_ms=json.loads(scope)['valid_until_ms'],
 admitted_marker_present=(root/'admitted-lifecycle.json').exists(),
 no_trade_inventory_complete=False,broker_flat_verified=False,
 source_code_reverification='NOT_PERFORMED_BY_FILE_CAPTURE_USE_EXISTING_HEALTH_READBACK')
print(json.dumps(dict(manifest=m,payload=payload),sort_keys=True))
'''


def save_bundle(bundle, destination):
    dest=safe_path(destination)
    m=bundle['manifest']; payload=bundle['payload']
    if m['scope_sha256']!=SCOPE or m['config_sha256']!=CONFIG:raise ValueError('capture_scope_config_pin')
    if not isinstance(m['files'],list) or not 2<=len(m['files'])<=512:raise ValueError('capture_file_bound')
    verified={};total=0
    for f in m['files']:
        name=f['name']
        if not isinstance(name,str) or Path(name).name!=name or name in ('.','..','manifest.json') or name in verified:
            raise ValueError('capture_name')
        raw=base64.b64decode(payload[name],validate=True);total+=len(raw)
        if len(raw)>16*1024*1024 or total>64*1024*1024 or hashlib.sha256(raw).hexdigest()!=f['sha256']:
            raise ValueError('capture_hash_bound')
        verified[name]=raw
    if set(payload)!=set(verified):raise ValueError('capture_payload_contract')
    dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True);dest.mkdir(mode=0o700)
    for name,raw in [*verified.items(),('manifest.json',canonical(m))]:
        fd=os.open(dest/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
    return {'manifest':str(dest/'manifest.json'),'manifest_sha256':hashlib.sha256(canonical(m)).hexdigest(),
            'files':len(verified),'observed_ms':m['observed_ms'],'broker_requests':0,'broker_writes':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--identity',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args()
    command=['ssh','-i',str(a.identity),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
             'root@64.226.73.119','/root/by-bot/.venv/bin/python','-B','-']
    try:
        result=subprocess.run(command,input=REMOTE.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,check=True)
        if len(result.stdout)>96*1024*1024:raise ValueError('transport_bound')
        r=save_bundle(strict_json(result.stdout),a.destination)
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as e:
        print(json.dumps({'status':'BLOCKED','reason':type(e).__name__}));return 2
    print(json.dumps(r,sort_keys=True));return 0

if __name__=='__main__':raise SystemExit(main())
