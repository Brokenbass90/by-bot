"""Bounded Oct9 never-dispatched reservation handoff; GET-only broker access.

Default is check-only. --apply requires an exact source-bound review permit.
The original account lock encloses fresh capture, CAS, append and readback.
No app deployment, order sender, scheduler or LIVE configuration mutation.
"""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
sha=lambda b:hashlib.sha256(b).hexdigest()
capture=ROOT/'reports/evidence/alpaca_handoff_20261010/capture_non_dispatch.py'
original=ROOT/'reports/evidence/alpaca_opening_20261009/read_postcheck.py'
def literal(path,name):
    return next(ast.literal_eval(n.value) for n in ast.parse(path.read_text()).body
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
remote=literal(original,'remote')
extra=literal(capture,'extra')
lock_block="""lock=Path('/root/by-bot/runtime/locks/alpaca_bridge_5cec021eb9d04382.lock')
fd=os.open(lock,os.O_RDONLY|os.O_NOFOLLOW)
try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);out['shared_lock_available']=True
finally:os.close(fd)
"""
assert extra.count(lock_block)==1
extra=extra.replace(lock_block,"out['shared_lock_available']=True\n")
assert remote.endswith('print(json.dumps(out))\n') and extra.endswith('print(json.dumps(out))\n')
module=ROOT/'research_lab/alpaca_dynamic_v1.py'
policy=ROOT/'reports/ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json'
baseline=ROOT/'.private/alpaca_handoff_20261010/custody_v3.json'
b=json.loads(baseline.read_bytes())['response']
expected={'book_sha256':b['book']['sha256'],'paper_sha256':b['paper']['sha256'],
    'root_crontab_sha256':b['root_crontab']['sha256'],
    'writer_sha256':{k:v['sha256'] for k,v in b['writer_sources'].items()},
    'services':b['services'], 'source_manifests':b['source_manifests'],
    'legacy_exclusions_sha256':b['legacy_exclusions']['sha256']}
apply='--apply' in sys.argv
args=[a for a in sys.argv[1:] if a!='--apply']
if len(args)!=(2 if apply else 1):raise SystemExit('OUTPUT [--apply REVIEW_PERMIT]')
output=Path(args[0]);assert not output.exists()
if apply:
    permit=json.loads(Path(args[1]).read_bytes())
    assert permit['status']=='APPROVED_ORDERS_OFF_RETIREMENT_ONLY'
    assert permit['operation_sha256']==sha(Path(__file__).read_bytes())
    assert permit['module_sha256']==sha(module.read_bytes())
    assert permit['capture_script_sha256']==sha(capture.read_bytes())
    assert permit['parent_capture_script_sha256']==sha(original.read_bytes())
    assert permit['baseline_capture_sha256']==sha(baseline.read_bytes())
    assert permit['single_owner_for_non_dispatch_handoff_reviewed'] is True
    review_pin=sha(Path(args[1]).read_bytes())
else:review_pin=None
header="""
import fcntl,os
from pathlib import Path
shared_lock=Path('/root/by-bot/runtime/locks/alpaca_bridge_5cec021eb9d04382.lock')
assert not any(p.is_symlink() for p in [shared_lock,*shared_lock.parents])
fd=os.open(shared_lock,os.O_RDONLY|os.O_NOFOLLOW)
st=os.fstat(fd);assert st.st_uid==os.getuid() and st.st_nlink==1
fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
"""
payload={'module':module.read_text(),'module_sha256':sha(module.read_bytes()),
         'policy':json.loads(policy.read_bytes()),'expected':expected,
         'apply':apply,'review_pin':review_pin}
header+='payload=__import__("json").loads('+repr(canonical(payload).decode())+')\n'
footer=r'''
assert out['book']['sha256']==payload['expected']['book_sha256'],'SOURCE_BOOK_CAS'
assert out['paper']['sha256']==payload['expected']['paper_sha256'],'PAPER_STORE_CAS'
assert out['root_crontab']['sha256']==payload['expected']['root_crontab_sha256'],'WRITER_SCHEDULE_CAS'
assert {k:v['sha256'] for k,v in out['writer_sources'].items()}==payload['expected']['writer_sha256'],'WRITER_SOURCE_CAS'
assert out['services']==payload['expected']['services'],'SERVICE_CAS'
assert out['source_manifests']==payload['expected']['source_manifests'],'APP_SOURCE_CAS'
assert not any(v['mismatches'] for v in out['source_manifests'].values()),'APP_SOURCE_MISMATCH'
assert out['legacy_exclusions']['sha256']==payload['expected']['legacy_exclusions_sha256'],'LEGACY_EXCLUSION_CAS'
assert out['legacy_exclusions']['payload'].get('XOM')=='ALPACA_DYNAMIC_V1_PAPER_PENDING','LEGACY_XOM_EXCLUSION_MISSING'
assert out['matching_processes']==[],'ACTIVE_WRITER_UNRESOLVED'
paper=json.loads(out['paper_broker']['account']['raw'])
live=json.loads(out['live_broker']['account']['raw'])
assert paper['id']=='4cdbfb77-d1e0-4789-86b2-341bc886efaf'
assert live['id']=='afd9ffea-e99d-4d2a-b64a-f07fb0f295c6'
assert out['live_halt']['account_id']==live['id'] and out['live_halt']['halted'] is True
assert json.loads(out['live_broker']['positions']['raw'])==[]
assert json.loads(out['live_broker']['orders']['raw'])==[]
positions=json.loads(out['paper_broker']['positions']['raw'])
orders=json.loads(out['paper_broker']['orders']['raw'])
assert len(orders)<100 and not any(r['symbol']==plan['symbol'] for r in positions+orders)
assert out['paper_broker']['entry_cid']['http_status']==404
assert out['retirement_extra']['stop_source']['http_status']==404
assert out['paper']['intents']==[] and out['retirement_extra']['paper_hwm_present'] is False
assert out['retirement_extra']['paper_runtime_files']==['paper.lock','paper.sqlite']
now=time.time_ns()//1000000
for section in ['paper_broker','live_broker']:
    assert all(0<=now-v['receive_ms']<=300000 for v in out[section].values())
assert 0<=now-out['retirement_extra']['stop_source']['receive_ms']<=300000
source_sha=hashlib.sha256(canonical(out)).hexdigest()
assert hashlib.sha256(payload['module'].encode()).hexdigest()==payload['module_sha256']
ns={'__name__':'reviewed_dynamic_handoff'};exec(compile(payload['module'],'<reviewed_source>', 'exec'),ns)
ns['policy_check'](payload['policy']);policy_sha=ns['digest'](payload['policy'])
assert plan['epoch_sha256']==policy_sha
assert plan['receipt_id']=='a23c310ccdd9c6706bf6d006d5b778e247f19d63d36de77eb7840bb4d30c560b'
proof={'schema':'ALPACA_EXPIRED_NONDISPATCH_PROOF_V1','policy_sha256':policy_sha,
 'receipt_id':plan['receipt_id'],'original_plan_sha256':ns['digest'](plan),
 'observed_ms':out['observed_ms'],'paper_account_id':paper['id'],'live_account_id':live['id'],
 'live_entry_halted':True,'single_owner_reviewed':payload['apply'],
 'entry_client_order_id':out['retirement_extra']['entry_cid'],
 'stop_client_order_id':out['retirement_extra']['stop_cid'],
 'entry_client_id_http_status':404,'stop_client_id_http_status':404,
 'paper_store_intents':0,'paper_hwm_present':False,
 'symbol_position_absent':True,'symbol_orders_absent':True,
 'source_sha256':source_sha,'broker_authenticated_by_this_validator':False,
 'review_permit_sha256':payload['review_pin']}
out['handoff']={'status':'CHECK_ONLY_NO_MUTATION','proof':proof,'module_sha256':payload['module_sha256']}
if payload['apply']:
    assert payload['review_pin'] and len(payload['review_pin'])==64
    from contextlib import contextmanager
    path=base/'runtime/rehearsal/replacement.sqlite'
    assert not any(p.is_symlink() for p in [path,*path.parents])
    stat=path.stat();assert stat.st_uid==os.getuid() and stat.st_nlink==1
    before_bytes=path.read_bytes();assert hashlib.sha256(before_bytes).hexdigest()==out['book']['sha256']
    out['handoff']['before_book_base64']=__import__('base64').b64encode(before_bytes).decode()
    with sqlite3.connect(path,timeout=5) as db:
        db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
        assert db.execute("SELECT value FROM meta WHERE key='policy'").fetchone()==(policy_sha,)
        tables=['meta','rankings','slots','intents','exits']
        before={t:db.execute('SELECT * FROM '+t+' ORDER BY 1').fetchall() for t in tables}
        assert before['intents']==out['book']['intents']
        assert not db.execute("SELECT name FROM sqlite_master WHERE name IN ('intent_attempts','intent_retirements')").fetchall()
        db.execute('CREATE TABLE intent_attempts (receipt TEXT PRIMARY KEY,entry TEXT NOT NULL,session TEXT NOT NULL,payload TEXT NOT NULL)')
        db.execute('CREATE TABLE intent_retirements (receipt TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        @contextmanager
        def same_transaction():yield db
        book=ns['DynamicBook'].__new__(ns['DynamicBook'])
        book.path=path;book.policy=payload['policy'];book.policy_hash=policy_sha;book.db=same_transaction
        result=book.retire_undispatched(plan['receipt_id'],proof,time.time_ns()//1000000)
        assert {t:db.execute('SELECT * FROM '+t+' ORDER BY 1').fetchall() for t in tables}==before
        assert ns['DynamicBook'].active_from_db(db)==[]
        assert len(ns['DynamicBook'].history_from_db(db))==1
        assert db.execute('SELECT COUNT(*) FROM intent_attempts').fetchone()[0]==0
    with sqlite3.connect(path.absolute().as_uri()+'?mode=ro',uri=True) as db:
        assert {t:db.execute('SELECT * FROM '+t+' ORDER BY 1').fetchall() for t in tables}==before
        active=ns['DynamicBook'].active_from_db(db);assert active==[]
        retained=len(ns['DynamicBook'].history_from_db(db));assert retained==1
    assert hashlib.sha256((base/'runtime/broker_paper/paper.sqlite').read_bytes()).hexdigest()==out['paper']['sha256']
    out['handoff'].update({'status':'EXPIRED_NONDISPATCH_APPLIED_ORDERS_OFF',
        'result':result,'original_rows_unchanged':True,'history_intents':retained,
        'active_intents':len(active),'after_book_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    out['remote_writes']=1
out['broker_writes']=0
print(json.dumps(out))
'''
remote=header+remote[:-len('print(json.dumps(out))\n')]+extra[:-len('print(json.dumps(out))\n')]+footer
p=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes',
 '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119',
 '/root/by-bot/.venv/bin/python -B -'],input=remote.encode(),capture_output=True,timeout=90)
if p.returncode:sys.stderr.write(p.stderr.decode()[-1800:]);raise SystemExit(p.returncode)
assert len(p.stdout)<6000000
receipt={'operation_sha256':sha(Path(__file__).read_bytes()),'remote_query_sha256':sha(remote.encode()),
         'response':json.loads(p.stdout)}
with output.open('x') as f:os.chmod(output,0o600);json.dump(receipt,f,indent=2);f.write('\n')
print(json.dumps({'path':str(output),'sha256':sha(output.read_bytes()),
 'status':receipt['response']['handoff']['status'],'broker_writes':0,
 'remote_writes':receipt['response']['remote_writes']}))
