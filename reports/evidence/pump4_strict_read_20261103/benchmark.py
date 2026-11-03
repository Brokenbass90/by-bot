import pathlib,sys,json,tempfile,hashlib,time,statistics,importlib.util
app=pathlib.Path(sys.argv[1]);source=pathlib.Path(sys.argv[2]);prefix=pathlib.Path(sys.argv[3]);repeat=int(sys.argv[4]);sys.path.insert(0,str(app))
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
from research_lab.pump4_warm_reducer_v1 import WarmIntake
from research_lab.att1_lifecycle_journal import LifecycleJournal
spec=importlib.util.spec_from_file_location('strict_bench',source);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
raw=prefix.read_bytes();assert raw.endswith(b'\n');lines=raw.splitlines(keepends=True);last=json.loads(lines[-1])['event'];samples={'reference':[],'strict_read':[]};decisions={}
with tempfile.TemporaryDirectory(prefix='pump4-strict-',dir='/private/tmp' if pathlib.Path('/private/tmp').is_dir() else '/tmp') as tmp:
 for k in range(repeat):
  for name,cls in ([('reference',LifecycleJournal),('strict_read',mod.Pump4StrictReadJournal)] if k%2==0 else [('strict_read',mod.Pump4StrictReadJournal),('reference',LifecycleJournal)]):
   p=pathlib.Path(tmp)/(name+str(k)+'.jsonl');p.write_bytes(b''.join(lines[:-1]));p.chmod(0o600);i=Pump4Intake(p,'BTCUSDT');i.journal=cls(p);w=WarmIntake(i)
   t=time.perf_counter();result=w.accept(last['bar'],available_ms=last['available_ms'],observed_ms=last['observed_ms']);samples[name].append((time.perf_counter()-t)*1000)
   assert p.read_bytes()==raw and w.snapshot()==i.snapshot() and w.prefix==json.dumps(w.events,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
   decisions[name]=result
assert decisions['reference']==decisions['strict_read']
results={n:dict(median_ms=statistics.median(v),min_ms=min(v),max_ms=max(v),samples=v) for n,v in samples.items()}
print(json.dumps(dict(schema='PUMP4_STRICT_READ_SAME_WARM_BENCH_V1',observed_ms=time.time_ns()//1000000,source_sha256=hashlib.sha256(raw).hexdigest(),parser_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),rows=len(lines),prospective=False,broker_requests=0,broker_writes=0,full_bytes_restart_state_decision_parity=True,results=results,median_improvement_pct=100*(1-results['strict_read']['median_ms']/results['reference']['median_ms']))))
