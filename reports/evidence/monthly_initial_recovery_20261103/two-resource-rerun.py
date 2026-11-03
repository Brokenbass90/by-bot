"""Two exact failed nodes only, same source bytes, no network or broker."""
import hashlib,json,os,socket,sys,time,xml.etree.ElementTree as E
from pathlib import Path
P=Path('/opt/bybot-research/monthly-initial-recovery-20261103/candidate-0709fccba0d97cc6-t659a61b8');app=P/'app';os.chdir(app);sys.path.insert(0,str(app));os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
source=json.loads((P/'source-manifest.json').read_bytes());tests=json.loads((P/'test-manifest.json').read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def valid():return all(sha((app/n).read_bytes())==h for n,h in source['files'].items()) and all(sha((app/'tests'/n).read_bytes())==h for n,h in tests['files'].items())
assert valid(),'BYTES_CHANGED'
class NoNetwork(socket.socket):
 def connect(self,*a,**k):raise AssertionError('NETWORK_FORBIDDEN')
 connect_ex=connect;sendto=connect
socket.socket=NoNetwork;socket.create_connection=lambda *a,**k:(_ for _ in ()).throw(AssertionError('NETWORK_FORBIDDEN'))
import pytest
nodes=['test_full_frozen_rotation_runs_through_production_cli','test_default_cli_clock_is_sampled_after_slow_authority_checks'];args=[str(app/'tests/test_alpaca_monthly_production_runner_v1.py')+'::'+n for n in nodes];xml=P/'two-resource-rerun.xml';start=time.monotonic();rc=pytest.main(['-q','-p','pytest_timeout','--timeout=600','--rootdir',str(app),'--confcutdir',str(app),'--basetemp',str(P/'two-resource-runtime'),*args,'--junitxml='+str(xml)])
assert valid(),'BYTES_CHANGED_AFTER';fallback=[]
for m in tuple(sys.modules.values()):
 f=getattr(m,'__file__',None)
 if not f:continue
 q=Path(f).resolve()
 for n in source['files']:
  if str(q).endswith('/'+n) and q!=app/n:fallback.append(n)
assert not fallback
suites=E.parse(xml).getroot();suites=[suites] if suites.tag=='testsuite' else list(suites);counts={k:sum(int(s.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
x=dict(schema='MONTHLY_EXACT_TWO_RESOURCE_RERUN_V1',status='PASS' if rc==0 and counts==dict(tests=2,failures=0,errors=0,skipped=0) else 'FAIL',source_material_sha256=source['source_material_sha256'],nodes=nodes,counts=counts,elapsed_seconds=time.monotonic()-start,network_denied=True,real_broker_requests=0,real_broker_writes=0,checkout_fallback=fallback,original_acceptance_sha256=sha((P/'acceptance.json').read_bytes()),original_xml_sha256=sha((P/'exact-tests.xml').read_bytes()),rerun_xml_sha256=sha(xml.read_bytes()))
with (P/'two-resource-rerun.json').open('x') as f:json.dump(x,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps(x,sort_keys=True));raise SystemExit(rc)
