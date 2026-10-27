from pathlib import Path
import json,tempfile,time,cProfile,pstats,sys,io
sys.path.insert(0,str(Path.cwd()))
from research_lab.pump4_supervisor_v1 import Supervisor
r=json.loads(Path(sys.argv[1]).read_bytes());signal=r['row']['source']['signal_bar'][0]
with tempfile.TemporaryDirectory(dir=str(Path(sys.argv[1]).parent)) as folder:
 root=Path(folder)/'state';(root/'intake').mkdir(parents=True);(root/'epochs').mkdir()
 lines=[]
 for l in r['journal'].splitlines():
  row=json.loads(l);e=row['event']
  if e['kind']=='HISTORICAL_SEED' or e['bar'][0]<signal:lines.append(l)
 (root/'intake/ZROUSDT.jsonl').write_text('\n'.join(lines)+'\n');(root/'intake/ZROUSDT.jsonl').chmod(0o600);(root/'epochs/ZROUSDT.json').write_text(json.dumps(r['epoch']))
 s=Supervisor(root,clock=lambda:r['row']['source']['observed_ms']);pr=cProfile.Profile();cpu=time.process_time();start=time.perf_counter();pr.enable();out=s._symbol('ZROUSDT',r['row'],r['header'],'profile');pr.disable();elapsed=time.perf_counter()-start
 import hashlib
 print(json.dumps(dict(seconds=elapsed,cpu_seconds=time.process_time()-cpu,status=out['status'],mode=out['mode'],journal_rows=len(lines),result_sha256=hashlib.sha256(json.dumps(out,sort_keys=True).encode()).hexdigest(),journal_sha256=hashlib.sha256((root/'intake/ZROUSDT.jsonl').read_bytes()).hexdigest())))
 f=io.StringIO();pstats.Stats(pr,stream=f).sort_stats('cumtime').print_stats(15);print(f.getvalue())
