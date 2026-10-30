#!/usr/bin/env python3
"""Standalone, network-free Brain observer. No financial modules/constructor."""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab import pump4_brain_timely_v1 as B
from research_lab.att1_lifecycle_journal import LifecycleJournal

now=lambda:time.time_ns()//1000000
MANIFEST_FILES={
 'scripts/run_pump4_brain_timely_v1.py',
 'research_lab/pump4_brain_timely_v1.py',
 'research_lab/att1_lifecycle_journal.py',
 'research_lab/pump4_execution_plan_v1.py',
 'research_lab/pump4_source_probe_v1.py',
 'research_lab/alpaca_dynamic_v1.py',
 'strategies/pump_fade_v4r.py','strategies/signals.py',
 'reports/evidence/pump4_brain_timely_20261029/brain_shadow_v1.pinned.py',
}


def write_new(path,value):
 path=Path(path);raw=B.canonical(value)+b'\n'
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush();os.fsync(f.fileno())
 finally:os.close(fd)
 dfd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(dfd)
 finally:os.close(dfd)


def epoch(runtime,manifest_pin,*,now_ms):
 runtime=Path(runtime)
 B.need(not any(p.is_symlink() for p in (runtime,*runtime.parents)),'RUNTIME_SYMLINK')
 runtime.mkdir(mode=0o700,parents=True,exist_ok=True);path=runtime/'epoch.json'
 if path.exists():
  v=B.read_json(path)
  B.need(v.get('schema')=='PUMP4_BRAIN_OBSERVER_EPOCH_V1' and v.get('manifest_sha256')==manifest_pin
         and B.stamp(v.get('started_ms')) and v['started_ms']<=now_ms,'EPOCH_PIN')
  return v
 value=dict(schema='PUMP4_BRAIN_OBSERVER_EPOCH_V1',started_ms=now_ms,manifest_sha256=manifest_pin,
            money_authority=False,orders_allowed=False)
 write_new(path,value);return value


def tick(source,runtime,policy,*,now_ms,epoch_ms,clock):
 source=Path(source).absolute();runtime=Path(runtime).absolute()
 B.need(not runtime.is_relative_to(source) and not source.is_relative_to(runtime),'ROOT_OVERLAP')
 B.need(not any(p.is_symlink() for p in (source,*source.parents)),'SOURCE_SYMLINK')
 hour=now_ms//B.H*B.H;folder=source/str(hour)/'published'
 names=sorted(folder.glob('*.json')) if folder.exists() else []
 B.need(len(names)<=137,'PUBLICATION_BOUND')
 counts=dict(schema='PUMP4_BRAIN_OBSERVER_HEALTH_V1',observed_ms=now_ms,hour_ms=hour,
             new=0,observations=0,no_opportunity=0,shadow_pairs=0,timely=0,
             prospective=0,pending=0,mode='SHADOW',money_authority=False,orders_allowed=False,
             pre_live_decision_proven='UNKNOWN',learning_economic_pass=False)
 hour_dir=runtime/str(hour)
 hour_dir.mkdir(mode=0o700,exist_ok=True)
 for p in names:
  B.need(re.fullmatch('[A-Z0-9]{1,24}USDT[.]json',p.name) is not None,'PUBLICATION_NAME')
  try:
   value=B.read_json(p)
   B.need(value.get('symbol')==p.stem,'PUBLICATION_FILENAME_IDENTITY')
   if value.get('status')!='CLOSED_H1_INTAKE_PASS':continue
   d=value['decisions'][0]['decision']
   B.need(d.get('symbol')==p.stem,'SYMBOL')
   B.need(d.get('bar_open_ms')==hour-B.H,'PUBLICATION_HOUR')
   # Existing late/recovery publications remain in source; never upgrade them.
   if value.get('mode')!='CURRENT_CLOSED_BAR':continue
   next_open=B.next_open_from_source(source,value) if d.get('signal') is not None else None
   event=B.pair_event(value,policy=policy,observed_ms=clock(),epoch_ms=epoch_ms,next_open=next_open)
   path=hour_dir/(p.stem+'.jsonl')
   existing=B.reduce_events(LifecycleJournal(path).read())
   key=event['event_id'];wkey=key.replace(':pair',':witness')
   if key in existing and wkey in existing:
    old=existing[key]
    B.need(all(old.get(k)==event.get(k) for k in ('source_sha256','policy_sha','policy_source_sha256','epoch_ms')),'SOURCE_CONFLICT')
    result=dict(new=False,witness=existing[wkey])
   else:result=B.record_pair(path,event,clock=clock)
   w=result['witness']
   counts['new']+=int(result['new']);counts['observations']+=1
   counts['no_opportunity']+=int(event['kind']=='NO_OPPORTUNITY')
   counts['shadow_pairs']+=int(event['kind']=='SHADOW_PAIR')
   counts['timely']+=int(w['within_entry_60s']);counts['prospective']+=int(w['prospective'])
  except B.SourcePending:counts['pending']+=1
 counts['status']='OBSERVING' if names else ('WAITING_H1' if now_ms-hour<90000 else 'SOURCE_MISSING')
 receipt=source/str(hour)/'receipt.json'
 counts['source_hour_complete']='UNKNOWN'
 if receipt.exists():
  try:r=B.read_json(receipt)
  except B.SourcePending:
   counts['status']='SOURCE_PUBLISHING';return counts
  B.need(r.get('schema')=='PUMP4_WS_FULL137_DATA_RECEIPT_V1' and r.get('source_hour_open_ms')==hour,'FULL_HOUR_IDENTITY')
  counts['source_hour_complete']=r.get('hour_pass') is True
  counts['expected_trading']=r.get('expected_trading','UNKNOWN')
  if counts['source_hour_complete'] is False:counts['status']='SOURCE_HOUR_INCOMPLETE'
 if counts['pending']:counts['status']='SOURCE_PUBLISHING'
 if counts['source_hour_complete'] is True and counts['observations']!=counts['expected_trading'] and not counts['pending']:
  counts['status']='SOURCE_OBSERVATION_COUNT_MISMATCH'
 return counts


def verify_manifest(path,pin):
 raw=B.read_bytes(path);B.need(hashlib.sha256(raw).hexdigest()==pin,'MANIFEST_PIN');v=B.decode(raw)
 B.need(v.get('schema')=='PUMP4_BRAIN_OBSERVER_SOURCE_V1' and set(v.get('files',{}))==MANIFEST_FILES,'MANIFEST_FILES')
 for rel,sha in v['files'].items():B.need(hashlib.sha256(B.read_bytes(ROOT/rel)).hexdigest()==sha,'APP_SOURCE_DRIFT')
 return v


def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--source',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True)
 p.add_argument('--manifest',type=Path,required=True);p.add_argument('--manifest-sha256',required=True)
 p.add_argument('--once',action='store_true');a=p.parse_args(argv)
 verify_manifest(a.manifest,a.manifest_sha256)
 policy=B.FrozenBrain(ROOT/'reports/evidence/pump4_brain_timely_20261029/brain_shadow_v1.pinned.py')
 a.runtime.mkdir(mode=0o700,parents=True,exist_ok=True)
 fd=os.open(a.runtime/'observer.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 stop=threading.Event();previous={}
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  e=epoch(a.runtime,a.manifest_sha256,now_ms=now())
  for sig in (signal.SIGTERM,signal.SIGINT):previous[sig]=signal.signal(sig,lambda *_:stop.set())
  anchor=(now(),time.monotonic_ns());last=None;printed=0
  def guarded_now():
   wall=now();mono=time.monotonic_ns()
   B.need(wall>=anchor[0] and mono>=anchor[1] and abs((wall-anchor[0])-(mono-anchor[1])/1e6)<=1000,'CLOCK_STEP')
   return wall
  while not stop.is_set():
   wall=guarded_now()
   # A bounded standalone DATA observation is not a financial scope extension.
   B.need(wall-e['started_ms']<7*24*B.H,'OBSERVER_SEVEN_DAY_BOUND')
   result=tick(a.source,a.runtime,policy,now_ms=wall,epoch_ms=e['started_ms'],clock=guarded_now)
   signature=(result['hour_ms'],result['status'],result['observations'],result['source_hour_complete'])
   if result['new'] or signature!=last or wall-printed>=60000:
    print(json.dumps(result,sort_keys=True),flush=True);last=signature;printed=wall
   if a.once:return 0
   stop.wait(1)
  return 0
 except (ValueError,OSError,KeyError,TypeError) as exc:
  print(json.dumps(dict(status='BRAIN_OBSERVER_BLOCKED',observed_ms=now(),error=str(exc)[:240],
                       money_authority=False,orders_allowed=False)),flush=True)
  return 1
 finally:
  for sig,handler in previous.items():signal.signal(sig,handler)
  os.close(fd)

if __name__=='__main__':raise SystemExit(main())
