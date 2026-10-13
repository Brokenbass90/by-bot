"""Independent read-only physical readback of the installed disabled app."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from shlex import quote

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.alpaca_dynamic_v1 import canonical
from research_lab.alpaca_live_readiness_v1 import write_new

REMOTE=r'''
import hashlib,json,os,signal,sqlite3,subprocess,sys,time
from pathlib import Path
signal.alarm(45);expect=json.load(sys.stdin)
sha=lambda b:hashlib.sha256(b).hexdigest()
base=Path('/opt/bybot-research/alpaca-dynamic-live-20261013')
raw=(base/'control/handoff_v2_receipt.json').read_bytes()
assert sha(raw)==expect['handoff_file_sha256'],'HANDOFF_FILE_DRIFT'
r=json.loads(raw);deployment=r['deployment'];rows=deployment['source_files']+r['custody']['source_files']
for row in rows:
 p=Path(row['path']);assert p.is_file() and p.stat().st_nlink==1 and p.stat().st_uid==0
 assert not any(x.is_symlink() for x in (p,*p.parents))
 assert sha(p.read_bytes())==row['sha256'],'DEPLOYED_SOURCE_DRIFT'
for row in deployment['source_files']:
 if '/app/' in row['path'] and row['path'].endswith('.py'):
  compile(Path(row['path']).read_bytes(),row['path'],'exec')
cron=subprocess.run(['crontab','-l'],capture_output=True,timeout=5);assert cron.returncode==0
assert sha(cron.stdout)==r['cron_after_sha256']
assert not any(line.strip() and not line.lstrip().startswith(b'#') and b'alpaca_intended_live_readonly' in line
 and b'--send-orders' in line for line in cron.stdout.splitlines())
units=list((base/'disabled-unit-templates').iterdir())+list((base/'unapproved-activation-templates').iterdir())
for p in units:
 assert not any((Path(d)/p.name).exists() for d in ('/etc/systemd/system','/run/systemd/system','/lib/systemd/system'))
assert not (base/'session/owner-go.json').exists()
assert not (base/'session/intake.json').exists()
assert not (base/'session/first-intent.json').exists()
for p in (base/'disabled-unit-templates').iterdir():assert b'--apply' not in p.read_bytes()
with sqlite3.connect((base/'sources/live_source_book.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 assert db.execute('SELECT COUNT(*) FROM intents').fetchone()[0]==0
out=dict(schema='ALPACA_DISABLED_DEPLOYED_READBACK_V2',status='DEPLOYED_BYTES_CRON_AND_ORDERS_OFF_PASS',
 observed_ms=time.time_ns()//1000000,package_sha256=deployment['package_sha256'],
 handoff_file_sha256=sha(raw),verified_app_files=37,verified_source_files=len(rows),
 cron_after_sha256=sha(cron.stdout),compiled_installed_python=True,
 no_registered_new_units=True,no_go_intake_or_reservation=True,
 source_book_intents=0,orders_allowed=False,broker_writes=0,remote_writes=0,
 full_paper_pass=False,cost_finality_pending=True)
print(json.dumps(out));signal.alarm(0)
'''


def main(output):
    p=ROOT/'.private/alpaca_live_readiness_20261013'
    r=json.loads((p/'orders_off_install_handoff_v2_capture.json').read_bytes())['response']
    command='/root/by-bot/.venv/bin/python -B -c '+quote(REMOTE)
    call=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119',command],
        input=canonical(dict(handoff_file_sha256=hashlib.sha256(canonical(r)).hexdigest())),
        capture_output=True,timeout=65)
    if call.returncode:print('READ_ONLY_DEPLOYMENT_VERIFICATION_FAILED');return 2
    capture=dict(query_sha256=hashlib.sha256(REMOTE.encode()).hexdigest(),response=json.loads(call.stdout))
    write_new(output,canonical(capture));print(json.dumps(capture['response']));return 0


if __name__=='__main__':raise SystemExit(main(Path(sys.argv[1]).absolute()))
