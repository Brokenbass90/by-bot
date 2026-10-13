"""Original October13 14:05 UTC GET-only check, full cash-reference coverage.

Preserves the original reader and guard. Adds only the earlier activity cutoff
required by the existing Oct11 cash-before source. Never a broker/service write.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
PARENT=ROOT/'reports/evidence/alpaca_tuesday_preparation_20261012/capture_finality_read_only.py'
PARENT_PIN='23ced0c8b469f44d880fdddaa546456fb1e913ce4fcf6a0ff7662294d2154837'
DUE_MS=1791900300000


def query():
    assert hashlib.sha256(PARENT.read_bytes()).hexdigest()==PARENT_PIN
    spec=importlib.util.spec_from_file_location('original_oct13_get_finality',PARENT)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    remote=module.query()
    old='/v2/account/activities?after=2026-10-12T00%3A00%3A00Z&direction=asc&page_size=100'
    assert remote.count(old)==1
    remote=remote.replace(old,old.replace('2026-10-12','2026-10-11'))
    end='print(json.dumps(out))\n';assert remote.endswith(end)
    return remote[:-len(end)]+"out['activity_request_after_ms']=1791676800000\n"+end


def main(output):
    assert time.time_ns()//1000000>=DUE_MS,'ORIGINAL_OCT13_1405_CHECK_NOT_DUE'
    assert output.absolute().parent==ROOT/'.private/alpaca_live_readiness_20261013'
    assert output.parent.is_dir() and not output.exists()
    assert not any(p.is_symlink() for p in (output,*output.absolute().parents))
    remote=query()
    r=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119',
        '/root/by-bot/.venv/bin/python -B -'],input=remote.encode(),capture_output=True,timeout=100)
    if r.returncode:
        print('READ_ONLY_FINALITY_FAILED exit='+str(r.returncode),file=sys.stderr);raise SystemExit(r.returncode)
    assert len(r.stdout)<5000000
    capture=dict(query_sha256=hashlib.sha256(remote.encode()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        original_finality_reader_sha256=PARENT_PIN,response=json.loads(r.stdout))
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(capture,f,indent=2);f.write('\n')
    print(json.dumps(dict(capture_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        observed_ms=capture['response']['observed_ms'],broker_writes=0,remote_writes=0)))


if __name__=='__main__':main(Path(sys.argv[1]))
