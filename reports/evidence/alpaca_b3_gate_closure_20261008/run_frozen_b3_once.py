"""Owner-authorized Oct8 frozen judge. Any execution attempt is irrevocably spent."""
import datetime as dt
import hashlib,json,os,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3]
E=Path(__file__).resolve().parent
P=R/'.private/b3_frozen_once_20261008'
accept=json.loads((E/'b3_input_acceptance.json').read_text())
for name,pin in accept['files'].items():
 assert hashlib.sha256((P/name).read_bytes()).hexdigest()==pin['sha256'],name
assert '17 passed' in (E/'b3_frozen_tests.log').read_text(),'frozen fixture tests not passed'
assert not (P/'research_lab/os2/B3_KVITANCIYA.json').exists(),'B3 already consumed'
claim={'status':'EXECUTION_ATTEMPT_SPENT','owner_scope':'October8 single frozen B3, no repair/retune','research_ref':accept['research_ref'],'accepted_manifest_sha256':hashlib.sha256((E/'b3_input_acceptance.json').read_bytes()).hexdigest(),'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'command':accept['judge_command'],'rerun_forbidden':True}
with (E/'b3_execution_claim.json').open('x') as f:
 f.write(json.dumps(claim,indent=2)+'\n');f.flush();os.fsync(f.fileno())
# The frozen code is unchanged. Clear inherited broker/provider variables.
env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ}
env.update(PYTHONHASHSEED='0',PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
with (E/'b3_stdout.log').open('xb') as out,(E/'b3_stderr.log').open('xb') as err:
 result=subprocess.run(accept['judge_command'],cwd=P,env=env,stdout=out,stderr=err,timeout=180)
claim.update(returncode=result.returncode,completed_utc=dt.datetime.now(dt.timezone.utc).isoformat())
receipt=P/'research_lab/os2/B3_KVITANCIYA.json'
if receipt.exists():
 raw=receipt.read_bytes();(E/'B3_KVITANCIYA.json').open('xb').write(raw)
 d=json.loads(raw);claim.update(status=d['verdikt'],receipt_sha256=hashlib.sha256(raw).hexdigest())
else:claim.update(status='BLOCKED_IMPLEMENTATION',reason='no frozen receipt; spent attempt, no repeat')
(E/'b3_execution_result.json').write_text(json.dumps(claim,indent=2)+'\n')
print(json.dumps(claim))
