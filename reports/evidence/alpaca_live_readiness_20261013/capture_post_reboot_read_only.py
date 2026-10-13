"""One post-Mac-reboot read-only VPS and same-lifecycle fee observation.

Compose the existing readers, preserve private raw sources separately and do
not install, lock, dispatch, poll again, restart or mutate any remote state.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT/'reports/evidence/alpaca_live_readiness_20261013'
PRIVATE = ROOT/'.private/alpaca_live_readiness_20261013'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, EVIDENCE/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


OUTER = r'''
import contextlib,hashlib,io,json,os,signal,time
from pathlib import Path
payload=json.load(__import__('sys').stdin);captured={}
for name,code in payload['readers'].items():
 stream=io.StringIO()
 with contextlib.redirect_stdout(stream):
  exec(compile(code,name,'exec'),{'__name__':'post_reboot_read_only','payload':payload})
 captured[name]=json.loads(stream.getvalue())
base=Path('/opt/bybot-research/alpaca-dynamic-live-20261013')
custody=json.loads((base/'session/static_custody_pending_v2.json').read_bytes())
lock=Path(custody['original_shared_lock']);halt=Path(custody['halt_path'])
stat=lock.stat()
captured['lock_custody']=dict(original_shared_lock=str(lock),
 lock_regular_file=lock.is_file(),lock_symlink=lock.is_symlink(),
 lock_uid=stat.st_uid,lock_device=stat.st_dev,lock_inode=stat.st_ino,
 lock_acquisitions=0,custody_status=custody['status'],
 custody_sha256=hashlib.sha256((base/'session/static_custody_pending_v2.json').read_bytes()).hexdigest(),
 custody_package_sha256=custody['package_sha256'],
 halt_sha256=hashlib.sha256(halt.read_bytes()).hexdigest(),
 halted=json.loads(halt.read_bytes())['halted'],
 observed_ms=time.time_ns()//1000000)
print(json.dumps(captured));signal.alarm(0)
'''


def main():
    outputs = {name: PRIVATE/filename for name,filename in {
        'deployed':'post_reboot_deployed_oct13.json',
        'authority':'post_reboot_authority_oct13.json',
        'finality':'post_reboot_finality_oct13.json',
        'lock_custody':'post_reboot_lock_custody_oct13.json'}.items()}
    assert all(not p.exists() and not any(x.is_symlink() for x in (p,*p.parents))
               for p in outputs.values()),'NEW_PRIVATE_CAPTURES_ONLY'
    old=json.loads((PRIVATE/'orders_off_install_handoff_v2_capture.json').read_bytes())['response']
    canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    verify=module('installed_readback','verify_orders_off_deployment_v2.py').REMOTE
    assert verify.count('expect=json.load(sys.stdin)')==1
    verify=verify.replace('expect=json.load(sys.stdin)',"expect=payload['verify_expected']")
    readers={
        'deployed':verify,
        'authority':module('authority_readback','capture_authority_read_only.py').REMOTE,
        'finality':module('fee_readback','capture_oct13_finality_v2.py').query()}
    payload=dict(readers=readers,verify_expected=dict(
        handoff_file_sha256=hashlib.sha256(canonical(old)).hexdigest()))
    # One SSH connection, one invocation of the original full-coverage fee reader.
    from shlex import quote
    call=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),
        '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
        'root@64.226.73.119','/root/by-bot/.venv/bin/python -B -c '+quote(OUTER)],
        input=canonical(payload),capture_output=True,timeout=180)
    if call.returncode:
        print(json.dumps(dict(status='READ_ONLY_POST_REBOOT_QUERY_FAILED',
            exit=call.returncode,stderr_sha256=hashlib.sha256(call.stderr).hexdigest())))
        return 2
    assert len(call.stdout)<7000000,'CAPTURE_BOUND'
    raw=json.loads(call.stdout)
    summary={}
    for name,path in outputs.items():
        row=dict(query_sha256=hashlib.sha256((readers.get(name) or OUTER).encode()).hexdigest(),
                 script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),response=raw[name])
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as handle:json.dump(row,handle,indent=2);handle.write('\n')
        summary[name]=dict(capture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           observed_ms=raw[name].get('observed_ms'))
    print(json.dumps(dict(status='READ_ONLY_POST_REBOOT_SOURCES_CAPTURED',
        captures=summary,broker_writes=0,remote_writes=0,lock_acquisitions=0)))
    return 0


if __name__=='__main__':raise SystemExit(main())
