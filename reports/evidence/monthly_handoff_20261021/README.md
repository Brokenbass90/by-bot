# Exact memory-only Monthly legacy-handoff acceptance

`source_manifest.json` pins53 source/config files; only the native binding,
existing runner and existing rehearsal changed from the accepted production
component, plus the new read-only retirement helper. Frozen source/strategy files
are unchanged. `test_manifest.json` pins14 test files including imported helpers
and records the exact executed nodes. `source_delta.json` records the comparison.

`exact.py` is the identical local/VPS portable harness. It denies sockets, checks
source/test bytes before and after, rejects checkout import fallback and records
synthetic E2E receipts. Test-owned systemd/cron/ps seams are fixtures. No real
profile, broker, owner grant, unit installation or LIVE handoff is exercised.
Local/server repetitions are the same test cases, not independent observations.

Reconstruct an exclusive disposable candidate from the pinned checkout:

```sh
.venv/bin/python -B - <<'PY'
import hashlib,json,os,shutil,sys,tempfile
from pathlib import Path
r=Path.cwd();e=r/'reports/evidence/monthly_handoff_20261021'
p=Path(tempfile.mkdtemp(prefix='monthly-handoff-'));app=p/'app'
for public,private in [('source_manifest.json','source-manifest.json'),
                       ('test_manifest.json','test-manifest.json')]:
    shutil.copyfile(e/public,p/private)
for manifest,prefix in [('source_manifest.json',''),('test_manifest.json','tests/')]:
    for name,pin in json.loads((e/manifest).read_bytes())['files'].items():
        rel=Path(prefix+name);assert not rel.is_absolute() and '..' not in rel.parts
        raw=(r/rel).read_bytes();assert hashlib.sha256(raw).hexdigest()==pin,str(rel)
        dest=app/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
shutil.copyfile(e/'exact.py',p/'exact.py')
print('Exclusive memory-only candidate:',p,flush=True)
os.execv(sys.executable,[sys.executable,'-I','-B',str(p/'exact.py')])
PY
```

VPS acceptance additionally uses `env -i`, `unshare --net`, `nice15`, one BLAS
thread and timeout1200. This process timeout changes no production unit.
`local-acceptance.json`/`server-acceptance.json` and the independent server hash
readback establish only the component boundary. Fixture clocks/calendars, loss
amounts and reserve.03 do not establish official session, market performance,
latency, operational retirement, actual financial authority or chosen risk terms.

Private real preflight/financial identifiers, profile hashes and unit-state
observations are excluded from this public evidence. No message was sent to Claude.
