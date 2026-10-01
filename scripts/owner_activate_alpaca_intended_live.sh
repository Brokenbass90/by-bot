#!/usr/bin/env bash
# OWNER EXECUTION ONLY. Enables real broker orders. Never invoked by Codex.
# Exact preflight + exclusive handoff blocks from the reviewed owner procedure.
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
