#!/usr/bin/env python3
"""Network-free native BTC context assessments and mature descriptive joins."""
from pathlib import Path
import sys,argparse,fcntl,os,json,hashlib,signal,time,threading,stat
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab import brain_context_cycle_v1 as C
from research_lab import pump4_brain_timely_v1 as B
from research_lab.att1_lifecycle_journal import LifecycleJournal
from scripts.run_pump4_brain_timely_v1 import epoch,MANIFEST_FILES

now=lambda:time.time_ns()//1000000
FILES=MANIFEST_FILES|{'research_lab/brain_context_cycle_v1.py','scripts/run_brain_context_cycle_v1.py'}


def census(source,*,observed_ms):
 hour=observed_ms//B.H*B.H;p=Path(source)/str(hour)/'receipt.json';raw=B.read_bytes(p);v=B.decode(raw)
 B.need(v.get('schema')=='PUMP4_WS_FULL137_DATA_RECEIPT_V1' and v.get('source_hour_open_ms')==hour
        and v.get('census')==137 and v.get('hour_pass') is True,'CONTEXT_SOURCE_HOUR')
 rows=v.get('rows');B.need(isinstance(rows,list) and len(rows)==137,'CONTEXT_CENSUS_ROWS')
 active=[];seen=set()
 for r in rows:
  s=r.get('symbol');B.need(isinstance(s,str) and s not in seen,'CONTEXT_CENSUS_SYMBOL');seen.add(s)
  if r.get('status')=='UNAVAILABLE_INSTRUMENT':continue
  B.need(r.get('status')=='CLOSED_H1_INTAKE_PASS' and r.get('mode')=='CURRENT_CLOSED_BAR','CONTEXT_CENSUS_ROW')
  d=r['decisions'][0]['decision'];B.need(d['symbol']==s and d['bar_open_ms']==hour-B.H and d['source_pins']==B.FROZEN_SIGNAL_PINS,'CONTEXT_CENSUS_IDENTITY')
  B.need(r['publication_completed_ms']<=observed_ms and d.get('money_authority') is False and d.get('orders_allowed') is False,'CONTEXT_CENSUS_TIME')
  active.append(d)
 return dict(hour_ms=hour,expected_trading=v['expected_trading'],observations=len(active),signals=sum(d['signal'] is not None for d in active),source_complete=True,source_sha256=hashlib.sha256(raw).hexdigest())


def read_btc(path):
 # Read bytes without acquiring a source flock: never compete with its writer.
 p=Path(path).absolute();B.need(not any(x.is_symlink() for x in (p,*p.parents)),'CONTEXT_SOURCE_SYMLINK')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  a=os.fstat(fd);B.need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_size<=8*1024*1024,'CONTEXT_SOURCE_BOUND')
  result=LifecycleJournal(p,max_bytes=8*1024*1024)._load(fd)[0]
  b=os.fstat(fd);B.need((a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns),'CONTEXT_SOURCE_CHANGED_DURING_READ')
  return result
 finally:os.close(fd)


def cycle(btc,source,runtime,*,policy_path,observed_ms,epoch_ms,clock):
 events=read_btc(btc);path=Path(runtime)/'context.jsonl';journal=LifecycleJournal(path)
 existing=C.reduce_events(journal.read());joins=0;decision=None
 for d in list(existing.values()):
  if d['kind']!='MARKET_CONTEXT_DECISION' or d['event_id']+':outcome' in existing:continue
  w=existing.get(d['event_id']+':durable')
  if w is None:
   w=C.durability_witness(d,completed_ms=clock(),recovered=True);C.record(path,w);existing[w['event_id']]=w
  result=C.outcome(d,events,observed_ms=observed_ms,witness=w)
  if result is not None:joins+=int(C.record(path,result))
 view=census(source,observed_ms=observed_ms)
 key=f"context:{view['hour_ms']}:{epoch_ms}"
 if key not in existing:
  decision=C.assessment(events,view,policy_path=policy_path,observed_ms=observed_ms,epoch_ms=epoch_ms)
  C.record(path,decision);completed=clock()
  w=C.durability_witness(decision,completed_ms=completed);C.record(path,w);existing[w['event_id']]=w
  print(json.dumps(dict(status='CAUSAL_CONTEXT_RECORDED' if w['before_outcome_open'] else 'LATE_NOT_CAUSAL',decision=decision,decision_durable_by_ms=completed)),flush=True)
 else:decision=existing[key]
 w=existing.get(key+':durable')
 return dict(status='CONTEXT_SHADOW_RUNNING',observed_ms=clock(),decision_id=decision['event_id'],action=decision['action'],
             context=decision['context'],outcome_status=('LATE_NOT_CAUSAL' if not w or not w['before_outcome_open'] else ('PENDING_OUTCOME' if decision['event_id']+':outcome' not in existing else 'ANNOTATED')),new_outcome_joins=joins,
             policy_sha=decision['policy_sha'],context_version=decision['context_version'],economic_pass=False,money_authority=False,orders_allowed=False)


def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('btc','source','runtime','manifest','manifest-sha256'):p.add_argument('--'+n,required=True)
 p.add_argument('--once',action='store_true');a=p.parse_args(argv)
 raw=B.read_bytes(a.manifest);B.need(hashlib.sha256(raw).hexdigest()==a.manifest_sha256,'CONTEXT_MANIFEST_PIN');m=B.decode(raw)
 B.need(m['schema']=='BRAIN_CONTEXT_WORKER_SOURCE_V1' and set(m['files'])==FILES,'CONTEXT_MANIFEST_FILES')
 for rel,pin in m['files'].items():B.need(hashlib.sha256(B.read_bytes(ROOT/rel)).hexdigest()==pin,'CONTEXT_SOURCE_DRIFT')
 runtime=Path(a.runtime).absolute();source=Path(a.source).absolute();btc=Path(a.btc).absolute()
 B.need(not runtime.is_relative_to(source) and not source.is_relative_to(runtime) and not btc.is_relative_to(runtime),'CONTEXT_ROOT_OVERLAP')
 runtime.mkdir(mode=0o700,parents=True,exist_ok=True);fd=os.open(runtime/'context-observer.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 stop=threading.Event();previous={}
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);e=epoch(runtime,a.manifest_sha256,now_ms=now());anchor=(now(),time.monotonic_ns())
  def checked_clock():
   t=now();mono=time.monotonic_ns();B.need(t>=anchor[0] and abs((t-anchor[0])-(mono-anchor[1])/1e6)<=1000,'CONTEXT_CLOCK_STEP');return t
  for sig in (signal.SIGTERM,signal.SIGINT):previous[sig]=signal.signal(sig,lambda *_:stop.set())
  while not stop.is_set():
   t=checked_clock();B.need(t-e['started_ms']<7*24*B.H,'CONTEXT_SEVEN_DAY_BOUND')
   try:
    result=cycle(btc,source,runtime,policy_path=ROOT/'reports/evidence/pump4_brain_timely_20261029/brain_shadow_v1.pinned.py',observed_ms=t,epoch_ms=e['started_ms'],clock=checked_clock)
   except (ValueError,OSError,KeyError,TypeError) as exc:
    result=dict(status='CONTEXT_SOURCE_NOT_READY',observed_ms=checked_clock(),error=str(exc)[:160],money_authority=False,orders_allowed=False)
   print(json.dumps(result,sort_keys=True),flush=True)
   if a.once:return 0 if result['status']=='CONTEXT_SHADOW_RUNNING' else 2
   stop.wait(30)
  return 0
 finally:
  for sig,handler in previous.items():signal.signal(sig,handler)
  os.close(fd)

if __name__=='__main__':raise SystemExit(main())
