"""Install/start one exact independently reviewed Oct12 PAPER session. No orders now."""
import base64,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
proposal_path=Path(sys.argv[1]);review_path=Path(sys.argv[2]);out=Path(sys.argv[3])
raw=proposal_path.read_bytes();review=json.loads(review_path.read_bytes())
assert review['status']=='APPROVED_FOR_PAPER_INSTALL_ONLY' and review['remaining_material_findings']==0
assert review['proposal_sha256']==hashlib.sha256(raw).hexdigest()
data=json.loads(raw);data['review']=review
# A failed synthetic-test stage has never started a process or sent an order.
# Complete only that exact reviewed predecessor; no session reset is permitted.
if len(sys.argv)==5:
 previous_raw=Path(sys.argv[4]).read_bytes()
 data['previous_staged_proposal']=json.loads(previous_raw)
 data['previous_staged_sha256']=hashlib.sha256(previous_raw).hexdigest()
encoded=base64.b64encode(json.dumps(data).encode()).decode()
remote=r'''
import base64,hashlib,json,os,fcntl,sqlite3,subprocess,time
from pathlib import Path
from dotenv import dotenv_values
import urllib.request
D=json.loads(base64.b64decode(ENCODED));base=Path(D['base']);assert str(base)=='/opt/bybot-research/alpaca-net-paper-session-20261012'
previous=D.get('previous_staged_proposal')
assert base.exists()==bool(previous),'SESSION_ALREADY_EXISTS_NO_RESET'
packet=json.loads(base64.b64decode(D['session_files']['packet.json']))
assert time.time_ns()//1000000<1791810900000,'STATIC_DEADLINE_EXPIRED'
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**k):raise ValueError('REDIRECT_REFUSED')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def get(profile,host,path):
 env=dotenv_values(profile);assert env['ALPACA_BASE_URL']==host
 req=urllib.request.Request(host+path,method='GET',headers={'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
 with opener.open(req,timeout=7) as r:raw=r.read(1000001)
 assert len(raw)<1000000
 return json.loads(raw)
def hashed(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,raw):
 p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 assert not any(x.is_symlink() for x in [p,*p.parents])
 with p.open('xb') as f:os.chmod(p,0o600);f.write(raw);f.flush();os.fsync(f.fileno())
def fsync_parent(p):
 fd=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
lock=Path('/root/by-bot/runtime/locks/alpaca_bridge_5cec021eb9d04382.lock')
with lock.open('a') as shared:
 fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB)
 live=get(packet['live_env'],'https://api.alpaca.markets','/v2/account')
 assert live['id']=='afd9ffea-e99d-4d2a-b64a-f07fb0f295c6' and live['pending_reg_taf_fees']==live['accrued_fees']=='0'
 assert not get(packet['live_env'],'https://api.alpaca.markets','/v2/positions')
 assert not get(packet['live_env'],'https://api.alpaca.markets','/v2/orders?status=open&limit=100')
 paper=get(packet['paper_env'],'https://paper-api.alpaca.markets','/v2/account')
 assert paper['id']==packet['paper_account'] and not paper['trading_blocked'] and not paper['account_blocked']
 positions=get(packet['paper_env'],'https://paper-api.alpaca.markets','/v2/positions')
 assert {p['symbol'] for p in positions}=={'ABNB','ABT','AMZN','MA','SCHW'}
 assert not get(packet['paper_env'],'https://paper-api.alpaca.markets','/v2/orders?status=open&limit=100')
 binding=json.loads(Path('/root/by-bot/runtime/alpaca_intended_live/binding.json').read_text())
 halt=Path(binding['account_lock_path']).with_suffix('.paper-kill')/'.paper-entry-halt.json'
 assert json.loads(halt.read_text())['halted'] is True
 excl=Path('/root/by-bot/runtime/alpaca_intended_paper/legacy_exclusions.json');before=excl.read_bytes()
 assert hashlib.sha256(before).hexdigest()==D['legacy_exclusions_before_sha256']
 for name,path in packet['static_paths'].items():
  if not path.startswith(str(base)) and name!='legacy_exclusions' and not name.startswith('unit:'):
   assert hashed(path)==packet['expected_sha256'][name],'SOURCE_DRIFT:'+name
 for root,info in D['expected_original_manifests'].items():
  app=Path(root);assert hashed(app/'source_manifest.json')==info['manifest_sha256']
  for n,h in json.loads((app/'source_manifest.json').read_text()).items():assert hashed(app/n)==h
 book=Path(packet['source_book'])
 with sqlite3.connect(book.as_uri()+'?mode=ro',uri=True) as db:
  original={t:db.execute('SELECT * FROM '+t+' ORDER BY 1').fetchall() for t in ['meta','rankings','slots','exits','intents']}
  assert hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==D['expected_original_table_sha256']
 with sqlite3.connect((Path(packet['paper_runtime'])/'paper.sqlite').as_uri()+'?mode=ro',uri=True) as db:assert not db.execute('SELECT * FROM intents').fetchall()
 if previous:
  assert D['previous_staged_sha256']=='52cfacc3d7bb0d12957bfd558fc708fba23d9a19611a269931e659f2e7936d7f'
  fixture='reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json'
  assert set(D['app_files'])-set(previous['app_files'])=={fixture}
  assert set(previous['app_files'])-set(D['app_files'])==set()
  assert all(D['app_files'][n]==v for n,v in previous['app_files'].items() if n!='source_manifest.json')
  assert D['units']==previous['units']
  for n in D['units']:
   state=subprocess.run(['systemctl','show',n,'-p','MainPID','-p','ActiveState'],capture_output=True,text=True,check=True,timeout=5).stdout
   assert 'MainPID=0\n' in state and 'ActiveState=inactive\n' in state,'STAGED_UNIT_ALREADY_STARTED'
   assert (Path('/etc/systemd/system')/n).read_bytes()==previous['units'][n].encode()
  assert {p.name for p in (base/'runtime').iterdir()}=={'targeted_tests.txt'},'STAGED_RUNTIME_HAS_AUTHORITY_STATE'
  assert hashed(base/'runtime/targeted_tests.txt')=='c9e5320f4f2c97622731c77eee0f5bcade61ecdf8e0f1ca2d0a2532ec7cdde18'
  for group,folder in [('app_files','app'),('session_files','session')]:
   for n,b64 in previous[group].items():assert (base/folder/n).read_bytes()==base64.b64decode(b64),'STAGED_SOURCE_DRIFT:'+n
  assert (base/'session/legacy_exclusions.before.json').read_bytes()==before
  def replace_preserving(p,content):
   if p.exists():save(base/'runtime/staged_before' / p.relative_to(base),p.read_bytes())
   temp=p.with_name(p.name+'.reviewed-closure.tmp');save(temp,content);os.replace(temp,p);fsync_parent(p)
  for group,folder in [('app_files','app'),('session_files','session')]:
   for n,b64 in D[group].items():
    if previous[group].get(n)!=b64:replace_preserving(base/folder/n,base64.b64decode(b64))
  replace_preserving(base/'session/review.json',(json.dumps(D['review'],indent=2)+'\n').encode())
  save(base/'runtime/staged_completion.json',(json.dumps({'previous_proposal_sha256':D['previous_staged_sha256'],'added_exact_fixture':fixture,'previous_test_output_retained':True,'broker_writes':0})+'\n').encode())
 else:
  for name in D['units']:assert not (Path('/etc/systemd/system')/name).exists()
  base.mkdir(mode=0o700)
  for n,b64 in D['app_files'].items():
   assert '..' not in Path(n).parts and not Path(n).is_absolute();save(base/'app'/n,base64.b64decode(b64))
  for n,b64 in D['session_files'].items():save(base/'session'/n,base64.b64decode(b64))
  save(base/'session/review.json',(json.dumps(D['review'],indent=2)+'\n').encode())
  save(base/'session/legacy_exclusions.before.json',before)
  (base/'runtime').mkdir(mode=0o700)
  for n,value in D['units'].items():save(Path('/etc/systemd/system')/n,value.encode())
 env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
 cmd=['/root/by-bot/.venv/bin/python','-B','-m','pytest','-q','-p','no:cacheprovider',
 'tests/test_alpaca_paper_source_plan.py','tests/test_alpaca_paper_session_guard.py',
 'tests/test_alpaca_initial_protection_recovery.py',
 'tests/test_alpaca_expired_reservation_handoff.py','tests/test_alpaca_dynamic_paper.py',
 'tests/test_alpaca_dynamic_paper_maintenance.py','tests/test_alpaca_open_dispatch_v2.py']
 test=subprocess.run(cmd,cwd=base/'app',env=env,capture_output=True,text=True,timeout=90)
 test_name='targeted_tests_completed.txt' if previous else 'targeted_tests.txt'
 save(base/'runtime'/test_name,(test.stdout+test.stderr).encode());assert test.returncode==0,'VPS_TARGETED_TEST_FAILURE'
 sys_path=__import__('sys').path;sys_path.insert(0,str(base/'app'))
 from research_lab.alpaca_dynamic_v1 import DynamicBook
 with sqlite3.connect(book.as_uri()+'?mode=ro',uri=True) as db:assert not DynamicBook.active_from_db(db)
 # Preserve exact old exclusions and update only NET under the original account lock.
 after=base64.b64decode(D['legacy_exclusions_after_b64']);assert json.loads(after)=={**json.loads(before),'NET':'ALPACA_DYNAMIC_V1_PAPER_OCT12_OWNED_OR_PENDING'}
 assert excl.read_bytes()==before
 temp=excl.with_name(excl.name+'.oct12.tmp');save(temp,after);os.replace(temp,excl);fsync_parent(excl)
 for name,path in packet['static_paths'].items():assert hashed(path)==packet['expected_sha256'][name],'FINAL_PIN_CONFLICT:'+name
 save(base/'runtime/install_receipt.json',(json.dumps({'installed_ms':time.time_ns()//1000000,'paper_only':True,'live_halt_preserved':True,'legacy_exclusions_after_sha256':hashed(excl),'source_book_original_sha256':D['expected_original_table_sha256'],'broker_writes':0,'targeted_test_returncode':test.returncode})+'\n').encode())
# These are new one-shot PAPER units only; never restart an existing service.
subprocess.run(['systemctl','daemon-reload'],check=True,timeout=10)
subprocess.run(['systemctl','start',*D['units']],check=True,timeout=15)
print(json.dumps({'status':'INSTALLED_NEW_PAPER_UNITS_READBACK_REQUIRED','observed_ms':time.time_ns()//1000000,'base':str(base),'units':list(D['units']),'broker_writes':0,'live_changed':False}))
'''.replace('ENCODED',repr(encoded))
p=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/by-bot'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','root@64.226.73.119','/root/by-bot/.venv/bin/python -B -'],input=remote.encode(),capture_output=True,timeout=160)
if p.returncode:sys.stderr.write(p.stderr.decode()[-3000:]);raise SystemExit(p.returncode)
value=json.loads(p.stdout)
with out.open('x') as f:os.chmod(out,0o600);json.dump(value,f,indent=2);f.write('\n')
print(json.dumps(value))
