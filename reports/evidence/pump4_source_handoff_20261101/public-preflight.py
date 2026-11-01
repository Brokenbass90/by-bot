"""Current source only; network namespace denied, no owner/lease/GET client."""
from pathlib import Path
import hashlib,json,sys,time
root=Path('/opt/bybot-research/pump4-current-hour-repair-20261101/candidate-05f89618d8550664')
raw=(root/'verification-source-hashes.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='05f89618d8550664cf2d914f000ef9f7b101d32176032adb78a6d7bbbdb03dfd'
for n,h in json.loads(raw).items():assert hashlib.sha256((root/'app'/n).read_bytes()).hexdigest()==h
sys.path.insert(0,str(root/'app'))
from research_lab.pump4_runtime_sources_v1 import TrustedSources
from research_lab.alpaca_dynamic_v1 import digest
config_path=Path('/opt/bybot-research/pump4-server-orders-off-20261023/tiny-activation-20261028-v1/runner.json')
craw=config_path.read_bytes()
assert hashlib.sha256(craw).hexdigest()=='fa0b3b2ec893f5167d79e71ef7fcf5a1d3788075105a2732663a8dafec53014a'
c=json.loads(craw);c['candidate_source']='CURRENT_H1_PUBLICATIONS_V1'
p=object.__new__(TrustedSources);p.config=c;p.config_sha=digest(c)
data=p._data();now=time.time_ns()//1000000
files,index=p._candidate_files(data,now)
print(json.dumps(dict(schema='PUMP4_CURRENT_SOURCE_COVERAGE_PREFLIGHT_V1',observed_ms=now,
    source_scan=p.candidate_scan,eligible_candidate_paths=len(files),
    original_scope_extended=False,broker_requests=0,broker_writes=0,
    financial_owner_constructed=False,network_denied=True,
    source_manifest_sha256=hashlib.sha256(raw).hexdigest(),
    actual_admission='NOT_PERFORMED',historical_durability='NOT_PROVEN')))
