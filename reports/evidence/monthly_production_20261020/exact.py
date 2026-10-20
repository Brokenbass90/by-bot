"""Isolated exact-code acceptance: all broker traffic is memory-only."""
import hashlib,json,os,sys,time,socket,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(__file__).resolve().parent; app=root/'app'; os.chdir(app)
sys.path=[str(app),*sys.path]
os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
manifest=json.loads((root/'source-manifest.json').read_bytes()); tests=json.loads((root/'test-manifest.json').read_bytes())
def hashes_ok():
 return all(hashlib.sha256((app/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items()) and all(hashlib.sha256((app/'tests'/n).read_bytes()).hexdigest()==h for n,h in tests['files'].items())
assert hashes_ok(),'PACKAGE_DRIFT_BEFORE'
def refused(*a,**k):raise AssertionError('EXACT_REHEARSAL_NETWORK_FORBIDDEN')
class NoNetworkSocket(socket.socket):
 connect=refused;connect_ex=refused;sendto=refused
socket.socket=NoNetworkSocket;socket.create_connection=refused
import pytest
start=time.monotonic(); xml=root/'exact-tests.xml'
rc=pytest.main(['-q','-p','pytest_timeout','--timeout=600','--rootdir',str(app),'--confcutdir',str(app),'--basetemp',str(root/'test-runtime'),*[str(app/'tests'/n) for n in tests['executed_nodes']],'--junitxml='+str(xml)])
loaded={};fallback=[]
for m in tuple(sys.modules.values()):
 f=getattr(m,'__file__',None)
 if not f:continue
 q=Path(f).resolve()
 for n in manifest['files']:
  if str(q).endswith('/'+n):
   loaded[n]=str(q.relative_to(app)) if q.is_relative_to(app) else str(q)
   if q!=app/n:fallback.append(n)
assert not fallback,('CHECKOUT_FALLBACK',fallback)
assert hashes_ok(),'PACKAGE_DRIFT_AFTER'
suites=ET.parse(xml).getroot(); suites=[suites] if suites.tag=='testsuite' else list(suites)
counts={k:sum(int(s.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
receipts=[]
for path in sorted((root/'test-runtime').rglob('receipt.json')):
 value=json.loads(path.read_bytes())
 if value.get('status','').startswith('MONTHLY_'):
  assert value.get('real_broker_requests')==value.get('real_broker_writes')==0
  receipts.append(dict(path=str(path.relative_to(root)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),receipt=value))
acceptance=dict(schema='ALPACA_MONTHLY_PRODUCTION_EXACT_ACCEPTANCE_V1',status='PASS' if rc==0 and not any(counts[k] for k in ['failures','errors','skipped']) else 'FAIL',source_material_sha256=manifest['source_material_sha256'],test_file_count=len(tests['files']),source_file_count=len(manifest['files']),counts=counts,elapsed_seconds=round(time.monotonic()-start,3),source_import_count=len(loaded),checkout_fallback=fallback,network_denied=True,real_broker_requests=0,real_broker_writes=0,orders_allowed=False,money_authority=False,whole_live_handoff='OPEN',receipt_count=len(receipts))
(root/'exact-imports.json').write_text(json.dumps(dict(imports=loaded,fallback=fallback),indent=2)+'\n')
(root/'rehearsal-receipts.json').write_text(json.dumps(receipts,indent=2,sort_keys=True)+'\n')
(root/'acceptance.json').write_text(json.dumps(acceptance,indent=2,sort_keys=True)+'\n')
print(json.dumps(acceptance,sort_keys=True));raise SystemExit(rc)
