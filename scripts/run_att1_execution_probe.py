#!/usr/bin/env python3
"""Bounded public research only: never imports credentials or an order client."""
import argparse
import asyncio
from collections import Counter
from copy import deepcopy
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research_lab.att1_execution_research import book_projection, funding_comparison

MAX_MS=48*3600*1000
MAX_WIRE=262144
SYMBOLS=('SEIUSDT','SUIUSDT')
SOURCE=Path('/opt/bybot-research/att1-lifecycle-zero-risk-v2/runtime/20261002-paired-observation/sessions')


class StudyStopped(RuntimeError):pass


def now():return time.time_ns()//1000000
def sha(data):return hashlib.sha256(data).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def atomic(path,value):
    if path.is_symlink():raise StudyStopped('OUTPUT_SYMLINK')
    temp=path.with_suffix('.tmp')
    with temp.open('wb') as f:
        os.chmod(temp,0o600);f.write(encoded(value));f.flush();os.fsync(f.fileno())
    temp.replace(path)
    directory=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(directory)
    finally:os.close(directory)


class Study:
    def __init__(self,root,kind,context_sha,*,now_ms=None,duration_ms=MAX_MS,
                 min_free=5*1024**3,max_bytes=4*1024**3,baseline_source=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.root.is_symlink():raise StudyStopped('OUTPUT_SYMLINK')
        self.lock=(self.root/'writer.lock').open('a')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close();raise StudyStopped('ALREADY_RUNNING')
        if not 0<duration_ms<=MAX_MS: self.close();raise ValueError('invalid duration')
        t=now() if now_ms is None else now_ms
        path=self.root/'study.json'
        if path.exists():
            self.spec=json.loads(path.read_bytes())
            if self.spec['kind']!=kind or self.spec['context_sha256']!=context_sha:
                self.close();raise StudyStopped('CONTEXT_CHANGED')
        else:
            if kind=='funding' and baseline_source is not None:
                source=Path(baseline_source)
                if not source.is_dir() or source.is_symlink():self.close();raise StudyStopped('SOURCE_DIRECTORY_INVALID')
                frontier=self.root/'frontier.json'
                if not frontier.exists():atomic(frontier,initial_frontier(source))
                if now_ms is None:t=now()
            self.spec={'schema_id':'att1_execution_probe_v1','kind':kind,
                'started_ms':t,'deadline_ms':t+duration_ms,'context_sha256':context_sha,
                'min_free_bytes':min_free,'max_capture_bytes':max_bytes,
                'orders_allowed':False,'private_api_allowed':False}
            atomic(path,self.spec)
        self.bytes=sum(p.stat().st_size for p in self.root.glob('capture-*.jsonl.gz'))
        self.counts=Counter();self.file=None;self.part=None

    def check(self,t=None):
        t=now() if t is None else t
        if t<self.spec['started_ms']:raise StudyStopped('STOP_CLOCK_REGRESSION')
        if t>=self.spec['deadline_ms']:raise StudyStopped('COMPLETE_DEADLINE')
        if self.bytes>=self.spec['max_capture_bytes']:raise StudyStopped('STOP_STORAGE_CAP')
        if shutil.disk_usage(self.root).free<self.spec['min_free_bytes']:raise StudyStopped('STOP_FREE_SPACE')

    def append(self,row,*,now_ms=None):
        t=now() if now_ms is None else now_ms;self.check(t)
        data=encoded(row)+b'\n'
        if len(data)>2*MAX_WIRE+4096:raise StudyStopped('STOP_CAPTURE_ROW_SIZE')
        # Independent gzip members bound the exact disk increment before write.
        packed=gzip.compress(data,compresslevel=3,mtime=0)
        if self.bytes+len(packed)>self.spec['max_capture_bytes']:raise StudyStopped('STOP_STORAGE_CAP')
        part=t//3600000
        if part!=self.part:
            if self.file:self.file.close()
            path=self.root/f'capture-{part}.jsonl.gz'
            if path.is_symlink():raise StudyStopped('OUTPUT_SYMLINK')
            self.file=path.open('ab',buffering=0);os.chmod(path,0o600);self.part=part
        remaining=memoryview(packed)
        while remaining:
            written=self.file.write(remaining)
            if not written:raise OSError('incomplete capture write')
            remaining=remaining[written:]
        if self.spec['kind']=='funding':
            os.fsync(self.file.fileno())
            directory=os.open(self.root,os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
        self.bytes+=len(packed);self.counts[row.get('kind','unknown')]+=1

    def heartbeat(self,status='RUNNING',**fields):
        atomic(self.root/'heartbeat.json',{'as_of_ms':now(),'pid':os.getpid(),
            'status':status,'study':self.spec,'capture_bytes':self.bytes,
            'counts_this_process':dict(self.counts),'orders_allowed':False,**fields})

    def close(self):
        if getattr(self,'file',None):self.file.close();self.file=None
        if getattr(self,'lock',None):self.lock.close();self.lock=None


def _first(path):
    if path.is_symlink():raise StudyStopped('SOURCE_SYMLINK')
    before=path.stat()
    with path.open('rb') as f:data=f.readline(MAX_WIRE+1)
    after=path.stat()
    if (before.st_ino,before.st_dev)!=(after.st_ino,after.st_dev):raise StudyStopped('SOURCE_REPLACED_DURING_READ')
    if len(data)>MAX_WIRE:raise StudyStopped('SOURCE_START_TOO_LARGE')
    if not data.endswith(b'\n'):return None
    value=json.loads(data)
    if value.get('seq')!=1 or value.get('event',{}).get('kind')!='START':raise StudyStopped('SOURCE_START_INVALID')
    from research_lab.att1_lifecycle_journal import _canonical,_hash,_event,GENESIS
    core={k:v for k,v in value.items() if k!='hash'}
    if (set(value)!={'seq','prev_hash','event','event_sha256','hash'} or value['prev_hash']!=GENESIS
            or value['event_sha256']!=_hash(_event(value['event'])) or value['hash']!=_hash(core)
            or data!=_canonical(value)+b'\n'):raise StudyStopped('SOURCE_START_HASH_INVALID')
    return {'prefix_sha256':sha(data),'inode':after.st_ino,'device':after.st_dev,
            'start':value,'prefix_bytes':len(data)}


def initial_frontier(source):
    state={}
    for p in sorted(source.glob('*.jsonl')):
        row=_first(p)
        if row:state[p.name]={k:v for k,v in row.items() if k!='start'}
    return state


def new_starts(source,state,*,started_ms):
    rows=[]
    paths=sorted(source.glob('*.jsonl'))
    if not set(state).issubset({p.name for p in paths}):raise StudyStopped('SOURCE_DISAPPEARED')
    for p in paths:
        row=_first(p)
        if not row:
            if p.name in state:raise StudyStopped('SOURCE_PREFIX_CHANGED')
            continue
        pin={k:v for k,v in row.items() if k!='start'}
        if p.name in state:
            if state[p.name]!=pin:raise StudyStopped('SOURCE_PREFIX_CHANGED')
            continue
        submit=row['start']['event']['intent']['submit_ms']
        if type(submit) is not int:raise StudyStopped('SOURCE_START_CLOCK_INVALID')
        rows.append({'kind':'funding_start','file':p.name,'source_pin':pin,
            'start':row['start'],'status':'FUTURE_START' if submit>=started_ms else 'PRELAUNCH_START_EXCLUDED'})
        state[p.name]=pin
    return rows


def public_instrument(symbol):
    url='https://api.bybit.com/v5/market/instruments-info?'+urlencode({'category':'linear','symbol':symbol})
    with urlopen(url,timeout=10) as response:data=response.read(MAX_WIRE+1)
    received=now()
    if len(data)>MAX_WIRE:raise ValueError('public response size')
    page=json.loads(data)
    if page.get('retCode')!=0 or len(page['result']['list'])!=1 or page['result']['list'][0]['symbol']!=symbol:
        raise ValueError('instrument envelope')
    return page,received


def funding_row(row,context):
    """Hypothetical sizing via the existing frozen admission oracle, not account truth."""
    from research_lab.att1_lifecycle_profile import admit_signal,bind_broker_replay_profile
    intent=row['start']['event']['intent'];symbol=intent['signal']['symbol']
    if symbol not in context['symbols']:return {**row,'status':'OUTSIDE_EXECUTION_ADMISSION','orders_allowed':False}
    base=context['public_profile'];synthetic_sha=sha(encoded({'kind':'SYNTHETIC_SIZING_ONLY','study':context['study_id']}))
    binding={'base_profile_sha256':base['profile_sha256'],
        'account_fingerprint_sha256':synthetic_sha,'broker_truth_sha256':synthetic_sha,
        'account_mode':'UNIFIED_ONE_WAY_USDT','observed_ms':intent['submit_ms'],
        'absolute_risk_cap':'0.4','old_budget_ceiling':'0.4','max_notional':'100',
        'daily_loss_cap':'0.8','max_concurrent_positions':1,'send_enabled':False}
    profile=bind_broker_replay_profile(base,binding)
    admitted=admit_signal(profile,intent['signal'],intent['instrument'],intent['book_state'],
        book='ATT1_BROKER_REPLAY:'+synthetic_sha,submit_ms=intent['submit_ms'])
    out={**row,'sizing':admitted,'sizing_scope':'HYPOTHETICAL_R0.4_N100_SAME_FROZEN_SIGNAL_AND_ORIGINAL_INSTRUMENT',
         'synthetic_binding_is_account_evidence':False,'actual_account_mode_confirmed':False,
         'shared_one_slot_simulated':False,'orders_allowed':False,'candidate_money_ready':False}
    if not admitted['accepted']:out['status']='FROZEN_QUANTITY_REJECTED';return out
    page,received=public_instrument(symbol);item=page['result']['list'][0];inputs=context['symbols'][symbol]
    out.update(public_instrument=page,instrument_received_ms=received,
        fee_status='DATED_CAPTURED_FEE_ASSUMPTION_NOT_REFRESHED',fee_source=inputs,
        comparison=funding_comparison(qty=admitted['plan']['requested_qty'],
            entry=admitted['plan']['nominal_entry'],stop=admitted['plan']['original_stop'],
            lower_rate=item['lowerFundingRate'],interval_minutes=item['fundingInterval'],
            taker_rate=inputs['taker_fee'],historical43_adverse=inputs['historical43_adverse']),
        status='RESEARCH_COMPARISON_ONLY')
    return out


async def funding(study,context,source):
    if not source.is_dir() or source.is_symlink():raise StudyStopped('SOURCE_DIRECTORY_INVALID')
    frontier=study.root/'frontier.json'
    if not frontier.exists():raise StudyStopped('BLOCKED_FRONTIER_MISSING')
    state=json.loads(frontier.read_bytes())
    study.heartbeat(baseline_or_processed_headers=len(state),new_start_count=0)
    total=0
    while True:
        study.check()
        # Work on a copy; durable output precedes cursor advancement. A crash may
        # repeat a source pin; consumers must dedup by that exact pin, never count twice.
        updated=deepcopy(state)
        for row in new_starts(source,updated,started_ms=study.spec['started_ms']):
            if row['status']=='FUTURE_START':
                try:row=await asyncio.to_thread(funding_row,row,context)
                except Exception as exc:row.update(status='BLOCKED_SOURCE_INPUTS',error=type(exc).__name__+':'+str(exc)[:180])
                total+=1
            study.append(row)
        atomic(frontier,updated);state=updated
        study.heartbeat(baseline_or_processed_headers=len(state),new_start_count_this_process=total)
        await asyncio.sleep(10)


async def transport(study):
    import websockets
    latest={};ws_snapshot=set();connection=0
    async def rest(symbol):
        def request():
            start=now();url='https://api.bybit.com/v5/market/orderbook?'+urlencode({'category':'linear','symbol':symbol,'limit':50})
            with urlopen(url,timeout=8) as response:wire=response.read(MAX_WIRE+1)
            return wire,start,now()
        while True:
            study.check();started=time.monotonic()
            try:
                wire,start,rx=await asyncio.to_thread(request)
                if len(wire)>MAX_WIRE:raise ValueError('response size')
                raw=json.loads(wire)
                if raw.get('retCode')!=0 or raw.get('result',{}).get('s')!=symbol:raise ValueError('book envelope')
                projection=book_projection(raw,kind='rest',received_ms=rx,used_ms=now())
                study.append({'kind':'rest_book','raw_wire':wire.decode(),'raw_sha256':sha(wire),
                    'request_started_ms':start,'projection':projection,'latest_ws':deepcopy(latest.get(symbol)),
                    'quiet_or_stale_cause':'NOT_PROVEN'})
            except StudyStopped:raise
            except Exception as exc:study.append({'kind':'rest_error','symbol':symbol,'as_of_ms':now(),'error':type(exc).__name__+':'+str(exc)[:180]})
            await asyncio.sleep(max(.05,2-(time.monotonic()-started)))
    async def ws():
        nonlocal connection
        delay=1
        while True:
            study.check();connection+=1;ws_snapshot.clear()
            try:
                async with websockets.connect('wss://stream.bybit.com/v5/public/linear',max_size=MAX_WIRE,
                        max_queue=16,ping_interval=20,ping_timeout=20,open_timeout=10) as socket:
                    await socket.send(json.dumps({'op':'subscribe','args':[f'{topic}.{s}' for s in SYMBOLS for topic in ('orderbook.50','publicTrade')]}))
                    study.append({'kind':'ws_connect','connection':connection,'as_of_ms':now()});delay=1
                    while True:
                        study.check()
                        try:wire=await asyncio.wait_for(socket.recv(),timeout=20)
                        except asyncio.TimeoutError:
                            await socket.send('{"op":"ping"}');study.append({'kind':'ws_quiet_timeout','connection':connection,'as_of_ms':now()});continue
                        rx=now();data=wire.encode() if isinstance(wire,str) else wire;raw=json.loads(data)
                        row={'kind':'ws_control','connection':connection,'received_ms':rx,
                             'raw_wire':data.decode(),'raw_sha256':sha(data)}
                        topic=raw.get('topic','')
                        if topic.startswith('orderbook.50.'):
                            symbol=topic.split('.')[-1]
                            if symbol not in SYMBOLS or raw.get('data',{}).get('s')!=symbol:raise ValueError('WS symbol')
                            p=book_projection(raw,kind='ws',received_ms=rx,used_ms=now())
                            reset=raw.get('type')=='snapshot' or p['u']==1
                            if reset:ws_snapshot.add(symbol)
                            old=latest.get(symbol)
                            row.update(kind='ws_book',projection=p,book_type=raw.get('type'),
                                reset=reset,delta_without_snapshot=symbol not in ws_snapshot,
                                sequence_regression=(not reset and old is not None and old['connection']==connection
                                  and type(p['seq']) is int and type(old['seq']) is int and p['seq']<old['seq']))
                            latest[symbol]={**p,'connection':connection}
                        elif topic.startswith('publicTrade.'):row['kind']='ws_trade'
                        study.append(row)
            except StudyStopped:raise
            except Exception as exc:
                study.append({'kind':'ws_disconnect','connection':connection,'as_of_ms':now(),'error':type(exc).__name__+':'+str(exc)[:180]})
                await asyncio.sleep(delay);delay=min(30,delay*2)
    async def guard():
        while True:
            study.check();study.heartbeat(latest_ws=latest);await asyncio.sleep(5)
    tasks=[asyncio.create_task(rest(s)) for s in SYMBOLS]+[asyncio.create_task(ws()),asyncio.create_task(guard())]
    try:await asyncio.gather(*tasks)
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--kind',required=True,choices=('transport','funding'))
    p.add_argument('--runtime',type=Path,required=True);p.add_argument('--context',type=Path,required=True)
    args=p.parse_args();raw=args.context.read_bytes();context=json.loads(raw)
    # The exclusive writer persists the baseline before the study start clock.
    study=Study(args.runtime,args.kind,sha(raw),baseline_source=SOURCE if args.kind=='funding' else None)
    try:
        study.append({'kind':'process_start','pid':os.getpid(),'as_of_ms':now()})
        asyncio.run(transport(study) if args.kind=='transport' else funding(study,context,SOURCE))
    except StudyStopped as exc:study.heartbeat(status=str(exc))
    except KeyboardInterrupt:study.heartbeat(status='STOP_OPERATOR')
    except BaseException as exc:
        study.heartbeat(status='BLOCKED_RUNTIME',error=type(exc).__name__+':'+str(exc)[:180]);raise
    finally:study.close()


if __name__=='__main__':main()
