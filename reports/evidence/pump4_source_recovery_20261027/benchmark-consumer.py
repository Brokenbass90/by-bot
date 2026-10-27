import subprocess,json
base='/opt/bybot-research/pump4-server-orders-off-20261023'
child='''from pathlib import Path
import json,sys,time,hashlib
app=Path(sys.argv[1]);sys.path.insert(0,str(app))
from research_lab.pump4_runtime_sources_v1 import TrustedSources
from research_lab.alpaca_dynamic_v1 import digest
config=json.loads(Path(sys.argv[2]).read_bytes());p=TrustedSources.__new__(TrustedSources);p.config=config;p.config_sha=digest(config);p.clock=lambda:time.time_ns()//1000000;p._candidate_consumed=set();p._negative_observations={};p._negative_clock=None
rows=[]
for i in range(3):
 start=time.perf_counter();cpu=time.process_time();r=p.candidate();assert r is None;rows.append(dict(iteration=i,seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,negative_cache_entries=len(p._negative_observations)))
print(json.dumps(dict(app=str(app),observations=len(list((Path(config['data_source']['root'])/'observations').glob('*.json'))),samples=rows,result='NO_SIGNAL',broker_writes=0)))
'''
rows=[]
for name in ('candidate-ffb31e24c703d9ed','candidate-e4feca498f37e27d'):
 app=base+'/'+name+'/app';config=base+'/entry-handoff-20261027/owner-review-stream-v1/runner.json';raw=subprocess.check_output(['/root/by-bot/.venv/bin/python','-B','-c',child,app,config],cwd=app,text=True);rows.append(json.loads(raw))
print(json.dumps(dict(schema='PUMP4_NEGATIVE_CONSUMER_BENCHMARK_V1',runs=rows,new_H1_proof=False,owner_constructed=False,credentials_read=False,network_disabled=True,broker_writes=0)))
