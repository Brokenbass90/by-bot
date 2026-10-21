# Exact ORDERS_OFF transition/loss-latch component acceptance

The source manifest pins53 files; test manifest pins16 files/helpers and exact
executed nodes. The local/VPS harness is identical: sockets denied, hashes checked
before/after, imported checkout fallbacks rejected, synthetic E2E receipts retained.
No actual account/profile/financial service/owner launcher is exercised. Server
candidate remains UNSELECTED; this component is not full financial activation.

The two full paths are the actual production CLI frozen-source rotation with
lost BUY/stop replies and restart, and the frozen-source pending-fee replacement
cycle. Release/source-preview copies of those long scenarios are not repeated.
Additional tests cover fee producer/replay, immutable legacy seal+anchor, final
dispatch pin changes, partial exits, ownership, write-ahead loss observation,
disk failure, interrupted restart, healthy completion, custody and entry bounds.

Reconstruct an exclusive disposable candidate from the pinned checkout:

```sh
.venv/bin/python -B - <<'PY'
import hashlib,json,os,shutil,sys,tempfile
from pathlib import Path
r=Path.cwd();e=r/'reports/evidence/monthly_transition_20261021'
p=Path(tempfile.mkdtemp(prefix='monthly-transition-'));app=p/'app'
for public,private in [('source_manifest.json','source-manifest.json'),
                       ('test_manifest.json','test-manifest.json')]:
    shutil.copyfile(e/public,p/private)
for manifest,prefix in [('source_manifest.json',''),('test_manifest.json','tests/')]:
    for name,pin in json.loads((e/manifest).read_bytes())['files'].items():
        rel=Path(prefix+name);assert not rel.is_absolute() and '..' not in rel.parts
        raw=(r/rel).read_bytes();assert hashlib.sha256(raw).hexdigest()==pin,str(rel)
        dest=app/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
shutil.copyfile(e/'exact.py',p/'exact.py')
os.execv(sys.executable,[sys.executable,'-I','-B',str(p/'exact.py')])
PY
```

VPS additionally runs env-i/unshare--net/nice15. The600s per-test timeout changes
no trading deadline. Earlier superseded rehearsal hit the known recovery/WAL
regression and was cancelled; it is not counted as a final PASS.

One independent critical review and same-worker targeted fixes are recorded in
review.json. Independent27 cases overlap root acceptance, not new observations.
Actual source/receipt hashes are independently read back after the server run.

**Scope limit:** posted legacy charges are supported using a separately pinned
terminal NET seal, complete activity and account-day fee allocation. Pending
legacy attribution remains blocked before loss observation; first-entry legacy
liabilities without Monthly exits remain unclassified. Neither a terminal seal
nor zero API fee fields proves final posting. No fee filtering or new authority.

Private broker/owner/unit/profile data are excluded. Budget GO is recorded in the
private owner dossier; exact executable LIVE scope/config is still not issued.
