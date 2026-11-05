from pathlib import Path
import json,hashlib,os,time
root=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824');lab=root.parent/'bybit-bot-clean-v28/research_lab';state=root/'.private/poly_signal_cycle_20261104/runtime-state/E2_20261104/POLY_SCHET_V3/signals'
rows=[]
for p in sorted(state.glob('*/blocked.json')):
 s=json.loads((p.parent/'source-signal.json').read_bytes());b=json.loads(p.read_bytes());rows.append(dict(id=p.parent.name,source_signal_sha256=hashlib.sha256((p.parent/'source-signal.json').read_bytes()).hexdigest(),question=s['question'],market_id=s['market_id'],declared_source=s['source'].split('+')[0],expected_sha256=s['source_sha256'],expected_received_ms=s['received_ms'],signal_ms=s['signal_ms'],blocked_ms=b['observed_ms'],reason=b['reason'],score_on_mac_ms=s['score']['score_on_mac_ms'],score_age_at_block_ms=b['observed_ms']-s['score']['score_on_mac_ms'],matches=[]))
target={z['expected_sha256'] for z in rows};inventory=[]
for directory in ('poly_monitor','poly_sport_shiroko'):
 p=lab/'data'/directory/'knigi.jsonl';fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  first=os.fstat(f.fileno());assert first.st_size<512*2**20;offset=0;counts={}
  while offset<first.st_size:
   line=f.readline(min(1048577,first.st_size-offset));assert len(line)<=1048576
   start=offset;offset+=len(line)
   if not line.endswith(b'\n'):continue
   raw=line[:-1];h=hashlib.sha256(raw).hexdigest()
   if h not in target:continue
   x=json.loads(raw)
   for z in rows:
    if h==z['expected_sha256']:
     z['matches'].append(dict(directory=directory,byte_offset=start,raw_sha256=h,market_id=x.get('id'),t=x.get('t'),timestamp_equal=int(x['t']*1000)==z['expected_received_ms'],bytes_behind_current_eof=first.st_size-start))
  last=os.fstat(f.fileno());assert (first.st_dev,first.st_ino)==(last.st_dev,last.st_ino) and last.st_size>=first.st_size
 inventory.append(dict(directory=directory,observed_prefix_bytes=first.st_size,mtime_ns=first.st_mtime_ns,inode=first.st_ino))
print(json.dumps(dict(actual_observed_ms=time.time_ns()//1000000,source_inventory=inventory,rows=rows,source_files_mutated=False,producer_or_judge_run=False),sort_keys=True,indent=2))
