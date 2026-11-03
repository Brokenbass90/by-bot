import pathlib,sys,importlib.util,json,tempfile,hashlib,time,statistics,os
root=pathlib.Path(sys.argv[1]);original=pathlib.Path(sys.argv[2]);new=pathlib.Path(sys.argv[3]);prefix=pathlib.Path(sys.argv[4]);repeat=int(sys.argv[5]);sys.path.insert(0,str(root))
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake
mods=[]
for name,path in [('reference',original),('optimized',new)]:
 s=importlib.util.spec_from_file_location('benchmark_'+name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);mods.append((name,m))
raw=prefix.read_bytes();assert raw.endswith(b'\n');lines=raw.splitlines(keepends=True);last=json.loads(lines[-1])['event'];results={}
with tempfile.TemporaryDirectory(prefix='pump4-profile-',dir='/private/tmp' if pathlib.Path('/private/tmp').is_dir() else '/tmp') as tmp:
 for name,m in mods:
  durations=[]
  for k in range(repeat):
   p=pathlib.Path(tmp)/(name+str(k)+'.jsonl');p.write_bytes(b''.join(lines[:-1]));p.chmod(0o600);i=Pump4Intake(p,'BTCUSDT');w=m.WarmIntake(i)
   t=time.perf_counter();r=w.accept(last['bar'],available_ms=last['available_ms'],observed_ms=last['observed_ms']);durations.append((time.perf_counter()-t)*1000)
   assert p.read_bytes()==raw and w.snapshot()==i.snapshot() and w.prefix==m.canonical(w.events)
  results[name]=dict(median_ms=statistics.median(durations),min_ms=min(durations),max_ms=max(durations),samples=durations,full_bytes_restart_state_parity=True)
print(json.dumps(dict(schema='PUMP4_EXACT_PUBLIC_PREFIX_WARM_BENCH_V1',source_sha256=hashlib.sha256(raw).hexdigest(),rows=len(lines),prospective=False,real_broker_requests=0,real_broker_writes=0,results=results,median_improvement_pct=100*(1-results['optimized']['median_ms']/results['reference']['median_ms']))))
