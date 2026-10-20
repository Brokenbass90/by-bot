# Exact ORDERS_OFF component acceptance

`source_manifest.json` pins all52 explicit source/config files. `test_manifest.json`
pins13 test files including imported helpers; its six nodes select29 tests.
`exact.py` is the identical portable local/VPS harness. It refuses sockets and
checks imports, source/test bytes before and after, and the five synthetic receipts.
No real profile, broker, owner grant, unit installation or LIVE handoff is tested.
The repeated local/server counts are the same cases, not58 independent tests.

Reconstruct an exclusive disposable candidate from the pinned checkout (POSIX,
repository `.venv` with pytest/pytest-timeout and existing dependencies):

```sh
.venv/bin/python -B - <<'PY'
import hashlib, json, os, shutil, sys, tempfile
from pathlib import Path
r=Path.cwd(); e=r/'reports/evidence/monthly_production_20261020'
p=Path(tempfile.mkdtemp(prefix='monthly-production-')); app=p/'app'
for public, private in [('source_manifest.json','source-manifest.json'),
                        ('test_manifest.json','test-manifest.json')]:
    shutil.copyfile(e/public,p/private)
for manifest, prefix in [('source_manifest.json',''),('test_manifest.json','tests/')]:
    for name, pin in json.loads((e/manifest).read_bytes())['files'].items():
        rel=Path(prefix+name); assert not rel.is_absolute() and '..' not in rel.parts
        raw=(r/rel).read_bytes(); assert hashlib.sha256(raw).hexdigest()==pin, str(rel)
        dest=app/rel; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(raw)
shutil.copyfile(e/'exact.py',p/'exact.py')
print('Exclusive memory-only candidate:',p,flush=True)
os.execv(sys.executable,[sys.executable,'-I','-B',str(p/'exact.py')])
PY
```

On VPS the harness additionally ran inside `unshare --net`, under `env -i`,
`nice15`, one BLAS thread and timeout1200. This timeout belongs to the acceptance
process; no production unit timeout was changed. Test clocks/calendars are
explicit fixtures, not official session/PIT/latency evidence.

Real NET observer/broker/unit receipts stay private and are not included here.
