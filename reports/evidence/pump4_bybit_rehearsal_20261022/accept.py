"""Exact isolated source acceptance; no credentials/profile or real broker."""
import hashlib,json,os,socket,sys,time,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(__file__).resolve().parent;app=root/'app';os.chdir(app)
sys.path.insert(0,str(app));os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONPATH=str(app),PYTHONDONTWRITEBYTECODE='1')
m=json.loads((root/'manifest.json').read_bytes())
def verify():assert all(hashlib.sha256((app/n).read_bytes()).hexdigest()==h for n,h in m['files'].items()),'SOURCE_DRIFT'
verify()
def denied(*a,**k):raise AssertionError('ORDERS_OFF_NETWORK_DENIED')
class OffSocket(socket.socket):connect=denied;connect_ex=denied;sendto=denied
socket.socket=OffSocket;socket.create_connection=denied
# Also block interpreter child traffic on Mac; VPS additionally uses unshare--net.
deny=root/'deny';deny.mkdir();(deny/'sitecustomize.py').write_text("import socket\ndef denied(*a,**k):raise AssertionError('ORDERS_OFF_CHILD_NETWORK_DENIED')\nclass Off(socket.socket):\n connect=denied\n connect_ex=denied\n sendto=denied\nsocket.socket=Off\nsocket.create_connection=denied\n")
os.environ['PYTHONPATH']=str(deny)+os.pathsep+str(app)
import pytest
start=time.monotonic();xml=root/'tests.xml'
rc=pytest.main(['-q','-c','/dev/null','--rootdir',str(app),'--confcutdir',str(app),'--basetemp',str(root/'test-runtime'),*[str(app/'tests'/n) for n in m['executed_tests']],'--junitxml='+str(xml)])
verify();fallback=[];imports={}
for module in tuple(sys.modules.values()):
 f=getattr(module,'__file__',None)
 if not f:continue
 p=Path(f).resolve()
 for n in m['files']:
  if str(p).endswith('/'+n):
   imports[n]=str(p)
   if p!=app/n:fallback.append(n)
assert not fallback,('CHECKOUT_FALLBACK',fallback)
suites=ET.parse(xml).getroot();suites=[suites] if suites.tag=='testsuite' else list(suites)
counts={k:sum(int(x.get(k,0)) for x in suites) for k in ('tests','failures','errors','skipped')}
receipts=[]
for p in sorted((root/'test-runtime').rglob('receipt.json')):
 r=json.loads(p.read_bytes())
 if str(r.get('schema','')).startswith('PUMP4_'):receipts.append(dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),receipt=r))
out=dict(schema='MONEY_CANDIDATE_EXACT_ORDERS_OFF_ACCEPTANCE_V1',status='PASS' if rc==0 and not any(counts[k] for k in ('failures','errors','skipped')) else 'FAIL',material_sha256=m['material_sha256'],counts=counts,elapsed_seconds=round(time.monotonic()-start,3),source_files=len(m['files']),imports=len(imports),checkout_fallback=fallback,network_denied=True,real_broker_requests=0,real_broker_writes=0,orders_allowed=False,money_authority=False,tiny_ready=False,receipt_count=len(receipts))
for name,value in [('acceptance.json',out),('imports.json',imports),('receipts.json',receipts)]:
 with (root/name).open('x') as f:json.dump(value,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps(out,sort_keys=True));raise SystemExit(rc)
