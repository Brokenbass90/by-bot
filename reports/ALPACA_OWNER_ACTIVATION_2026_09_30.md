# Owner procedure — Sep 30 selection / Oct 1 possible entry

PREPARED ONLY. Not executed. LIVE remains OFF. Frozen implementation: source
`74b7214b2d722b9e45c12024065d9a78c162567f`, installed release
`/opt/bybot-research/alpaca-intended-live/releases/73345c03fa823d82`.
Capital cap $487.42, gross .70, four positions, max weight .60. Cash regime can
legitimately produce no entry. Calendar/data must pass the existing driver checks.
No trade is promised on Oct 1; do not bypass monthly timing if a check fails.

Run the following **only after explicit owner activation**, as root on the VPS.
Do not paste the entire document into a shell. Each block has a separate purpose.
No CLI command or config should enable a second manager.

## 1. Read-only preflight and source verification

```bash
set -euo pipefail
umask 077
R=/root/by-bot/runtime/alpaca_intended_live
APP=/opt/bybot-research/alpaca-intended-live/app
PY=/root/by-bot/.venv/bin/python
cd "$APP"
"$PY" - <<'PY'
import hashlib,json
from pathlib import Path
m=Path('source_manifest.json')
assert hashlib.sha256(m.read_bytes()).hexdigest()=='73345c03fa823d82a2c330902624206d14123ed6269667774569ec5db1f0fbb2'
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in json.loads(m.read_text()).items())
assert Path('source_commit.txt').read_text().strip()=='74b7214b2d722b9e45c12024065d9a78c162567f'
print('SOURCE_HASH_PASS')
PY
bash "$R/run.sh" --preflight
crontab -l | sed -n '/alpaca/p'
```

Preflight must return zero, `LIVE_ACCOUNT_BOUND_READ_ONLY`, exact bound account
suffix `f295c6`, USD cash at least the cap, zero positions/open orders. This is
initial activation only. If nonflat, STOP; never close/adopt holdings to force PASS.

## 2. Exclusive OLD → NEW handoff and enable

The next block changes money authority. It removes exactly two OLD tags, waits
for their processes to finish, takes the shared account lock and NEW cycle lock,
repeats fresh broker preflight, then enables the binding and converts exactly one
NEW cron line. No immediate buy is submitted by this block. Native cron invokes
normal frozen monthly decisions afterward.

```bash
"$PY" - <<'PY'
import fcntl,json,os,subprocess,time
from pathlib import Path
r=Path('/root/by-bot/runtime/alpaca_intended_live')
p=r/'binding.json';b=json.loads(p.read_text());assert b['enabled'] is False
assert b['capital_usd']==487.42 and b['gross_exposure']==.7
old_tags=('alpaca_live_v38_manager','alpaca_protective_exit_only')
cron=subprocess.check_output(['crontab','-l'],text=True)
lines=cron.splitlines()
for tag in old_tags:assert sum(l.rstrip().endswith('# '+tag) for l in lines)==1,tag
stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
backup=r/('owner_activation_'+stamp);backup.mkdir(mode=0o700)
(backup/'crontab.before').write_text(cron);(backup/'binding.before.json').write_bytes(p.read_bytes())
kept=[l for l in lines if not any(l.rstrip().endswith('# '+t) for t in old_tags)]
retired='\n'.join(kept)+'\n'
subprocess.run(['crontab','-'],input=retired,text=True,check=True)
needles=('run_alpaca_live_v38_once.sh','run_alpaca_protective_exit_manager.sh',
         ' scripts/alpaca_protective_exit_manager.py','/root/by-bot/scripts/alpaca_protective_exit_manager.py')
for attempt in range(60):
    active=subprocess.check_output(['ps','ax','-o','command='],text=True).splitlines()
    if not any(any(n in line for n in needles) for line in active):break
    time.sleep(1)
else:raise RuntimeError('OLD_PROCESS_STILL_ACTIVE: binding remains OFF; inspect, do not kill blindly')
with (r/'readonly.lock').open('a') as cycle, Path(b['account_lock_path']).open('a') as account:
    fcntl.flock(cycle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    fcntl.flock(account,fcntl.LOCK_EX|fcntl.LOCK_NB)
    subprocess.run(['bash',str(r/'run.sh'),'--preflight'],check=True,timeout=90)
    assert json.loads(p.read_text())==b
    assert subprocess.check_output(['crontab','-l'],text=True)==retired
    targets=[l for l in kept if l.rstrip().endswith('# alpaca_intended_live_readonly')]
    assert len(targets)==1 and targets[0].count(' --read-only ')==1
    enabled=targets[0].replace(' --read-only ',' --send-orders ')
    new='\n'.join(enabled if l==targets[0] else l for l in kept)+'\n'
    b['enabled']=True
    tmp=p.with_suffix('.owner.tmp');tmp.write_text(json.dumps(b,indent=2)+'\n');tmp.chmod(0o600);os.replace(tmp,p)
    subprocess.run(['crontab','-'],input=new,text=True,check=True)
    assert subprocess.check_output(['crontab','-l'],text=True)==new
    (backup/'crontab.after').write_text(new)
    print('OWNER_ACTIVATION_WRITTEN; verify scheduled receipt before declaring operational')
PY
```

If a block aborts after retiring OLD, binding should remain OFF unless it reached
the final write. Inspect exact binding + cron before retrying; do not blindly rerun
or restore a stale full crontab. No automatic rollback over positions.

## 3. Verification after the next scheduled cycle

```bash
crontab -l | sed -n '/alpaca/p'
"$PY" - <<'PY'
import json
from pathlib import Path
r=Path('/root/by-bot/runtime/alpaca_intended_live')
b=json.loads((r/'binding.json').read_text())
print({'enabled':b['enabled'],'capital_usd':b['capital_usd'],'gross_exposure':b['gross_exposure']})
x=json.loads((r/'latest_intended_run.json').read_text())
print(json.dumps(x,indent=2))
PY
tail -40 "$R/logs/readonly.log"
```

Require one NEW money cron and zero OLD manager cron/processes. Preserve private
receipts. On Sep30 verify prepared selection is from that completed session. On
Oct1 require broker fills, owned quantities, accepted DAY stop IDs, durable
entry-relative floor/HWM and no NOT_CONFIRMED/reconcile errors. `enabled=true`
alone is not an executed/healthy lifecycle. The earlier flat preflight is expected
to reject after entry; use the normal runner receipts/reconciliation then.

## 4. Halt new entries while retaining the same protection manager

Do not set binding OFF while positions remain. The durable account halt suppresses
entries even when the normal monthly driver sets its own entry flag.

```bash
set -a
source "$R/profile.env"
set +a
export ALPACA_INTENDED_LIVE=1
"$PY" - <<'PY'
import json,os,fcntl
from pathlib import Path
from scripts import equities_alpaca_paper_bridge as b
binding=json.loads(Path(os.environ['ALPACA_INTENDED_LIVE_BINDING_PATH']).read_text())
with Path(binding['account_lock_path']).open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    b._halt_intended_paper_entries(b._paper_kill_state_dir(os.environ['ALPACA_BASE_URL'],os.environ['ALPACA_API_KEY_ID']),binding['account_id'],'owner_kill')
print('ENTRY_HALT_PERSISTED; protection runner retained')
PY
```

## 5. Exact owned kill: build proof, validate, then separately apply

Run after entry halt, during a regular session. Build proof exclusively from the
existing durable owned records and current positions. Never add a foreign symbol.

```bash
"$PY" - <<'PY'
import os,json,fcntl
from pathlib import Path
from scripts import equities_alpaca_paper_bridge as b
r=Path('/root/by-bot/runtime/alpaca_intended_live')
binding=json.loads((r/'binding.json').read_text())
with Path(binding['account_lock_path']).open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    c=b.AlpacaClient(os.environ['ALPACA_BASE_URL'],os.environ['ALPACA_API_KEY_ID'],os.environ['ALPACA_API_SECRET_KEY'])
    assert c.get_clock()['is_open'] is True
    state,error=b._load_protective_floor_state(r/'protective_exit/protective_exit_hwm.json');assert not error,error
    rows=[]
    for pos in c.list_positions():
        s=pos['symbol'];v=state.get(s)
        if not v or v.get('account_id')!=binding['account_id'] or v.get('strategy_id')!=b._INTENDED_PAPER_STRATEGY_ID:continue
        rows.append({'symbol':s,'entry_order_id':v['entry_order_id'],'qty':v['entry_fill_qty'],'avg_entry_price':v['entry_price']})
    proof={'reason':'owner_kill','account_id':binding['account_id'],'positions':rows}
    b._validated_paper_kill_scope(proof=proof,client=c,base_url=os.environ['ALPACA_BASE_URL'],intended_live=True)
    b._atomic_write_json(r/'owner_kill_proof.json',proof)
    print('FRESH_OWNED_PROOF_VALIDATED',len(rows))
PY
export ALPACA_SEND_ORDERS=1 ALPACA_ALLOW_NEW_ENTRIES=0
export ALPACA_INTENDED_LIVE_KILL_ACK=INTENDED_OWNED_EXITS_ONLY
# Review dry-run receipt; this command validates again and does not close.
/usr/bin/flock -n "$ALPACA_BRIDGE_LOCK_PATH" "$PY" scripts/equities_alpaca_paper_bridge.py --intended-live-kill-owned "$R/owner_kill_proof.json"
# Separate owner emergency action: this DOES submit owned exits.
/usr/bin/flock -n "$ALPACA_BRIDGE_LOCK_PATH" "$PY" scripts/equities_alpaca_paper_bridge.py --intended-live-kill-owned "$R/owner_kill_proof.json" --apply-kill
```

The apply path revalidates fresh account/order/fill identity and remaining quantity.
Require `confirmed_flat`; pending/awaiting_regular_session is not a successful kill.
Foreign positions are excluded, and never use account-wide liquidation. Keep the
same protection runner until fresh reconciliation proves no owned exposure/orders.

## 6. Flat rollback only

After direct broker truth again proves the entire account flat, remove only the two
NEW cron tags and disable binding under the same account/cycle locks. This rolls
back to **no NEW trading**, not automatic OLD reactivation. Do not delete state,
restore old HWM files, clear the entry halt or change source symlink.

```bash
"$PY" - <<'PY'
import json,subprocess,fcntl,os
from pathlib import Path
from scripts import equities_alpaca_paper_bridge as bridge
r=Path('/root/by-bot/runtime/alpaca_intended_live');p=r/'binding.json';b=json.loads(p.read_text())
with (r/'readonly.lock').open('a') as cycle, Path(b['account_lock_path']).open('a') as account:
    fcntl.flock(cycle,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(account,fcntl.LOCK_EX|fcntl.LOCK_NB)
    c=bridge.AlpacaClient(os.environ['ALPACA_BASE_URL'],os.environ['ALPACA_API_KEY_ID'],os.environ['ALPACA_API_SECRET_KEY'])
    assert c.base_url=='https://api.alpaca.markets'
    assert c.get_account()['id']==b['account_id']
    assert c.list_positions()==[] and c.list_orders(status='open',limit=100)==[]
    cron=subprocess.check_output(['crontab','-l'],text=True)
    tags=('alpaca_intended_live_readonly','alpaca_intended_live_data')
    result='\n'.join(l for l in cron.splitlines() if not any(l.rstrip().endswith('# '+t) for t in tags))+'\n'
    subprocess.run(['crontab','-'],input=result,text=True,check=True)
    b['enabled']=False;tmp=p.with_suffix('.owner.tmp');tmp.write_text(json.dumps(b,indent=2)+'\n');tmp.chmod(0o600);os.replace(tmp,p)
    print('FLAT_ROLLBACK; OLD not re-enabled; all evidence retained')
PY
```

Prepared against installed paths and existing CLI/functions. Embedded shell/Python
syntax checked offline; activation, kill and rollback have NOT been executed.
