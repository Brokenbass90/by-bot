from pathlib import Path
import hashlib,json,os,time
repo=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824');src=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/research_lab/data');out=repo/'.private/poly_execution_20261029/inputs';out.mkdir(parents=True)
manifest={};profiles={}
for name in ('poly_monitor/knigi.jsonl','poly_monitor/rynki.jsonl','poly_monitor/novosti.jsonl','poly_espn/matchi.jsonl'):
 p=src/name;before=p.stat();raw=p.read_bytes()[:before.st_size];after=p.stat();assert before.st_ino==after.st_ino and len(raw)==before.st_size
 with p.open('rb') as f:assert hashlib.sha256(f.read(before.st_size)).digest()==hashlib.sha256(raw).digest(),'PREFIX_CHANGED'
 complete=raw[:raw.rfind(b'\n')+1] if b'\n' in raw else b'';rows=[];errors=0
 for line in complete.splitlines():
  try:rows.append(json.loads(line))
  except Exception:errors+=1
 target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('xb') as f:f.write(raw)
 manifest[name]=dict(source=str(p),source_inode=before.st_ino,source_mtime_ns=before.st_mtime_ns,source_prefix_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),complete_newline_bytes=len(complete),partial_tail_bytes=len(raw)-len(complete),observed_ms=time.time_ns()//1000000)
 profiles[name]=dict(rows=len(rows),parse_errors=errors,keys=sorted(set(k for row in rows for k in row)),first=rows[:1],last=rows[-1:])
(out.parent/'input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(out.parent/'profiles.json').write_text(json.dumps(profiles,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:{x:v[x] for x in ('rows','parse_errors','keys')} for k,v in profiles.items()},ensure_ascii=False))
