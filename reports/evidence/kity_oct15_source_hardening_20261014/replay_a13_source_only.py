"""Pinned external source functions, memory HTTP and isolated temporary fixtures only."""
import ast,datetime as dt,hashlib,json,math,os,subprocess,tempfile,time,types
from pathlib import Path
from research_lab.kity_oct15_deadline_v1 import run_once,END
R=Path.cwd();C=R.parent/'bybit-bot-clean-v28'
REF='e27ef524c94f8d7835c5e8e99f5d77ab6fdc5552'
PIN='8d05c3988f34d2939c06cdcd56cdceb19fa3b143c5c1ded96abc6bbc2326140a'
blob=subprocess.run(['git','show',REF+':research_lab/kity_bybit_ten.py'],cwd=C,capture_output=True,check=True).stdout
assert hashlib.sha256(blob).hexdigest()==PIN
names=('opublikovat','konec_okna','oi_valid','kvitanciya_snimka','snimok','propusk_okna')
functions=[n for n in ast.parse(blob).body if isinstance(n,ast.FunctionDef) and n.name in names]
checks=[]
with tempfile.TemporaryDirectory(prefix='kity-a13-contract-',dir='/private/tmp') as tmp:
 def case(label,value):
  root=Path(tmp)/label;clock=[dt.datetime(2026,10,14,23,55,tzinfo=dt.timezone.utc)]
  ticker={'symbol':'BTCUSDT'}
  if value!='MISSING':ticker['openInterestValue']=value
  raw=json.dumps({'list':[ticker]}).encode()
  env=dict(D=root,dt=dt,json=json,os=os,time=time,math=math,POSL_NEIZV={},PRODUCER_SHA256=PIN,
   sha=lambda b:hashlib.sha256(b).hexdigest(),log=lambda *a:None,
   get=lambda *a,**kw:({'list':[ticker]},raw),instrumenty=lambda:{'BTCUSDT':{}},utc=lambda:clock[0])
  exec(compile(ast.Module(body=functions,type_ignores=[]),'a13-offline-temp-fixture','exec'),env)
  return root,clock,raw,env
 def passed(name):checks.append(dict(case=name,status='PASS'))
 for label,v in [('missing','MISSING'),('null',None),('nan',float('nan')),('inf',float('inf')),('bool',True),('negative',-1),('valid','5')]:
  root,clock,raw,env=case(label,v);env['snimok'](dt.date(2026,10,14));folder=root/'2026-10-15'
  f=folder/'snimok_2355.json';q=folder/'snimok_CAPTURE_RECEIPT.json';expected=label=='valid'
  assert f.exists()==expected and q.exists()==expected
  assert any(p.read_bytes()==raw for p in (folder/'popytki').iterdir())
  if expected:
   receipt=json.loads(q.read_bytes())
   assert receipt['status']=='CAPTURE_PASS' and receipt['producer_sha256']==PIN
   assert receipt['snapshot_sha256']==hashlib.sha256(f.read_bytes()).hexdigest()
   assert receipt['source_sha256']==hashlib.sha256((folder/receipt['source_raw']).read_bytes()).hexdigest()
   src=root/'producer.py';src.write_bytes(blob)
   cfg=dict(schema='KITY_OCT15_DEADLINE_OBSERVER_V1',day='2026-10-15',approval_scope='SOURCE_ONLY_NO_STRATEGY_CHANGE',
    producer_path=str(src),producer_sha256=PIN,snapshot_path=str(f),publisher_receipt_path=str(q),
    source_raw_dir=str(folder/'popytki'),output_path=str(root/'independent.json'))
   assert run_once(cfg,now_ms=END)['status']=='CAPTURE_OBSERVATION_PASS';passed('actual-a13-receipt-adapter')
  passed(label)
 root,clock,raw,env=case('publication','5');real=env['opublikovat']
 fake=types.SimpleNamespace(**{k:getattr(os,k) for k in dir(os) if not k.startswith('__')})
 fake.write=lambda fd,b:os.write(fd,b[:2]);env['os']=fake;p=root/'partial.json'
 real(p,'{"complete":true}');assert p.read_bytes()==b'{"complete":true}';passed('short-write-completed')
 env['os']=os;assert not real(p,b'overwrite') and p.read_bytes()==b'{"complete":true}';passed('no-overwrite')
 fake=types.SimpleNamespace(**{k:getattr(os,k) for k in dir(os) if not k.startswith('__')})
 def fail(fd):raise OSError('file fsync fixture')
 fake.fsync=fail;env['os']=fake;p=root/'failed.json'
 try:real(p,b'complete');raise AssertionError('must fail')
 except OSError:pass
 assert not p.exists() and not list(root.glob('.*.tmp'));passed('file-fsync-failure-no-final');env['os']=os
 root,clock,raw,env=case('late-fsync','5');publisher=env['opublikovat']
 def late(f,b):
  done=publisher(f,b)
  if f.name=='snimok_2355.json':clock[0]=dt.datetime(2026,10,15,tzinfo=dt.timezone.utc)
  return done
 env['opublikovat']=late;env['snimok'](dt.date(2026,10,14));folder=root/'2026-10-15'
 assert not (folder/'snimok_CAPTURE_RECEIPT.json').exists() and env['kvitanciya_snimka'](folder) is None
 env['propusk_okna'](dt.date(2026,10,14));assert json.loads((folder/'snimok_PROPUSHCHEN.json').read_bytes())['status']=='BLOCKED_DATA'
 passed('late-publication-unconsumed-blocked')
 root,clock,raw,env=case('crash-between-raw-and-snapshot','5');publisher=env['opublikovat'];first=[True]
 def crash(f,b):
  if f.name=='snimok_2355.json' and first[0]:first[0]=False;raise OSError('fixture crash after raw publication')
  return publisher(f,b)
 env['opublikovat']=crash
 try:env['snimok'](dt.date(2026,10,14))
 except OSError:pass
 old_file=next((root/'2026-10-15/popytki').iterdir());before=old_file.read_bytes();clock[0]+=dt.timedelta(minutes=1)
 changed=json.dumps({'list':[{'symbol':'BTCUSDT','openInterestValue':'6'}]}).encode()
 env['get']=lambda *a,**kw:({'list':[{'symbol':'BTCUSDT','openInterestValue':'6'}]},changed)
 env['snimok'](dt.date(2026,10,14));folder=root/'2026-10-15';receipt=json.loads((folder/'snimok_CAPTURE_RECEIPT.json').read_bytes())
 assert receipt['source_sha256']==hashlib.sha256((folder/receipt['source_raw']).read_bytes()).hexdigest() and old_file.read_bytes()==before
 passed('retry-after-raw-only-crash')
 root,clock,raw,env=case('attempt-name-conflict','5');folder=root/'2026-10-15/popytki';folder.mkdir(parents=True)
 p=folder/'tickers_1792022100000.raw';p.write_bytes(b'existing');env['snimok'](dt.date(2026,10,14))
 assert p.read_bytes()==b'existing' and not (folder.parent/'snimok_CAPTURE_RECEIPT.json').exists();passed('attempt-name-conflict-no-pass')
 assert not list(Path(tmp).rglob('*.tmp'));passed('temp-cleanup')
result=dict(schema='KITY_A13_OFFLINE_SOURCE_REPLAY_V1',status='SOURCE_CONTRACT_REPLAY_PASS',research_commit=REF,
 producer_sha256=PIN,checks=checks,checks_passed=len(checks),network_calls=0,actual_prospective_data_reads=0,claude_writes=0)
print(json.dumps(result))
