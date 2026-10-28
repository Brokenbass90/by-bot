#!/usr/bin/env python3
"""Resident public137 DATA bridge; existing financial owner remains separate/OFF."""
from pathlib import Path
import sys,argparse,asyncio,json,time,hashlib,signal,threading,ssl,inspect,shutil,os
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.pump4_stream_intake_v1 import StreamIntake,clock_guard
from research_lab.pump4_closed_bar_intake_v1 import Pump4Intake,_bar
from research_lab.pump4_bybit_sources_v1 import checked,universe,H
from research_lab.pump4_public_retry_v1 import observed_public_get
from research_lab.kity_micro_physical_owner_v1 import publish
from research_lab.pump4_supervisor_v1 import need,read
from research_lab.alpaca_dynamic_v1 import digest
from research_lab.kity_oct15_deadline_v1 import decode
URL='wss://stream.bybit.com/v5/public/linear'
now=lambda:time.time_ns()//1000000

def metadata(folder,*,get=None):
 get=get or (lambda p,q:observed_public_get(p,q,timeout=3))
 c=get('/v5/market/time',{});publish(folder/'clock.json',c);checked(c,'/v5/market/time',now_ms=now(),private=False)
 rows={};cursor='';seen=set()
 for page in range(8):
  params=dict(category='linear',limit=1000,**({'cursor':cursor} if cursor else {}));cap=get('/v5/market/instruments-info',params);publish(folder/('instruments-'+str(page)+'.json'),cap);result=checked(cap,'/v5/market/instruments-info',now_ms=now(),private=False)
  for row in result['list']:need(row['symbol'] not in rows,'STREAM_METADATA_DUPLICATE');rows[row['symbol']]=row
  cursor=result.get('nextPageCursor','');need(isinstance(cursor,str) and cursor not in seen,'STREAM_METADATA_CURSOR')
  if not cursor:return rows
  seen.add(cursor)
 raise ValueError('PUMP4_STREAM_METADATA_PAGE_BOUND')

def recover(s,hour,instruments,*,get=None):
 """Missing CLOSED bars only; immutable failure, old epoch, never CURRENT."""
 need(s.owned,'STREAM_RECOVERY_WRITER');get=get or (lambda p,q:observed_public_get(p,q,timeout=3));out=dict(recovered=0,blocked=[])
 for symbol in universe():
  i=instruments.get(symbol)
  if not i or any(i.get(k)!=v for k,v in dict(status='Trading',quoteCoin='USDT',contractType='LinearPerpetual').items()):continue
  try:
   intake=Pump4Intake(s.root/'intake'/(symbol+'.jsonl'),symbol);events=intake.journal.read();need(events,'STREAM_EXISTING_SEED_REQUIRED');cursor=events[-1]['bar'][0] if len(events)>1 else events[0]['bars'][-1][0]
   cached=getattr(s,'warm',{}).get(symbol)
   state=cached.snapshot() if cached is not None and cached.reusable(intake,events) else intake._replay(events)
   epoch=read(s.root/'epochs'/(symbol+'.json'))
   need(epoch['schema']=='PUMP4_DATA_EPOCH_V1' and epoch['symbol']==symbol and epoch['financial_authority'] is False and epoch['seed_sha256']==state['seed_bars_sha256'] and events[0]['observed_ms']<epoch['epoch_started_ms']<=s.clock(),'STREAM_RECOVERY_ORIGINAL_EPOCH')
   if cursor==hour-H:continue
   need(cursor<hour-H and (hour-H-cursor)//H<=1000,'STREAM_RECOVERY_GAP_BOUND')
   folder=s.root/'ws-recovery'/str(hour);marker=folder/(symbol+'.attempt.json');need(not marker.exists(),'STREAM_RECOVERY_PARTIAL_PRESERVED')
   publish(marker,dict(symbol=symbol,cursor_ms=cursor,target_ms=hour,observed_ms=s.clock(),orders_allowed=False))
   params=dict(category='linear',symbol=symbol,interval='60',start=cursor+H,end=hour-1,limit=1000);cap=get('/v5/market/kline',params);publish(folder/(symbol+'.capture.json'),cap);r=checked(cap,'/v5/market/kline',now_ms=s.clock(),private=False)
   need(r['category']=='linear' and r['symbol']==symbol and cap['params']==params and cap['body']['time']>=hour,'STREAM_RECOVERY_SOURCE')
   bars=[]
   for row in reversed(r['list']):
    need(isinstance(row,list) and len(row)==7,'STREAM_RECOVERY_ROW');bar=[int(row[0]),*map(float,row[1:6])];_bar(bar);need(__import__('decimal').Decimal(row[6]).is_finite() and __import__('decimal').Decimal(row[6])>=0,'STREAM_RECOVERY_TURNOVER');bars.append(bar)
   need([b[0] for b in bars]==list(range(cursor+H,hour,H)),'STREAM_RECOVERY_CONTIGUITY')
   for bar in bars:
    result=intake.accept(bar,available_ms=cap['receive_ms'],observed_ms=s.clock());d=result['decision'];p=s.root/'observations'/(d['decision_id']+'.json')
    if not p.exists():publish(p,dict(schema='PUMP4_DATA_DECISION_OBSERVATION_V1',decision=d,archive_id=digest(cap),mode='CATCHUP_REPLAY',status='RECOVERY_NOT_PROSPECTIVE',orders_allowed=False,money_authority=False))
    out['recovered']+=int(result['new'])
   publish(folder/(symbol+'.complete.json'),dict(symbol=symbol,cursor_ms=hour-H,broker_writes=0))
  except (ValueError,KeyError,TypeError,OSError) as exc:out['blocked'].append(dict(symbol=symbol,reason=str(exc)))
 return out

def verify_dependencies(path,pin):
 import importlib.util
 from research_lab.pump4_account_owner_v1 import safe
 from research_lab.kity_oct15_deadline_v1 import stable_bytes
 raw=stable_bytes(safe(path));need(hashlib.sha256(raw).hexdigest()==pin,'STREAM_DEPENDENCY_MANIFEST_PIN');v=decode(raw)
 spec=importlib.util.find_spec('websockets');need(spec is not None and Path(spec.origin).parent==Path(v['root']),'STREAM_DEPENDENCY_ROOT')
 root=safe(v['root']);actual={str(p) for p in root.rglob('*') if p.is_file() and p.suffix in ('.py','.so')}
 need(actual==set(v['files']),'STREAM_DEPENDENCY_CLOSURE')
 for p,h in v['files'].items():need(safe(p).is_relative_to(root) and hashlib.sha256(stable_bytes(safe(p))).hexdigest()==h,'STREAM_DEPENDENCY_DRIFT')
 return v

async def hour_stream(s,stop):
 import websockets
 while now()<s.hour-120000:
  if stop.is_set():return
  await asyncio.sleep(min(1,(s.hour-120000-now())/1000))
 need(now()<s.hour,'STREAM_SUBSCRIPTION_MISSED_BOUNDARY');anchor=(now(),time.monotonic_ns());options=dict(open_timeout=8,ping_interval=20,ping_timeout=20,close_timeout=3,max_size=1000000,compression=None,ssl=ssl.create_default_context())
 if 'proxy' in inspect.signature(websockets.connect).parameters:options['proxy']=None
 try:
  async with websockets.connect(URL,**options) as ws:
   pending=set();symbols=tuple(s.probes)
   for index in range(0,len(symbols),20):
    rid='PUMP4-'+str(s.hour)+'-'+str(index);request=dict(op='subscribe',req_id=rid,args=['kline.60.'+v for v in symbols[index:index+20]]);await ws.send(json.dumps(request));pending.add(rid);publish(s.folder/'subscriptions'/(rid+'.json'),dict(request=request,sent_ms=now()))
   ping=time.monotonic()
   while now()<s.hour+90000 and not stop.is_set():
    clock_guard(*anchor,now(),time.monotonic_ns())
    if time.monotonic()-ping>=20:await ws.send(json.dumps(dict(op='ping')));ping=time.monotonic()
    try:raw=await asyncio.wait_for(ws.recv(),timeout=min(5,max(.01,(s.hour+90000-now())/1000)))
    except asyncio.TimeoutError:continue
    received=now();received_mono=time.monotonic_ns()
    if not isinstance(raw,str):
     publish(s.folder/'binary-rejected.json',dict(raw_b64=__import__('base64').b64encode(raw).decode(),received_ms=received));raise ValueError('PUMP4_STREAM_BINARY_FRAME')
    s.feed(raw,received_ms=received,received_monotonic_ns=received_mono) # raw capture is durable BEFORE decode/ACK/admission
    value=decode(raw)
    if value.get('op')=='subscribe':
     rid=value.get('req_id');need(value.get('success') is True and rid in pending,'STREAM_SUBSCRIPTION_REJECTED');pending.remove(rid)
     if not pending:s.ack(received)
    if now()>=s.hour:need(not pending,'STREAM_ACK_MISSED_BOUNDARY')
 except Exception as exc:
  s.disconnect(type(exc).__name__+':'+str(exc));raise

def unspent_target(root,observed_ms):
 """Never repeat a setup/attempt from this hour, including partial failures."""
 target=(observed_ms//H+1)*H
 if any(os.path.lexists(Path(root)/name/str(target)) for name in ('ws-setup','ws-hours')):return None
 return target

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path);p.add_argument('--run',action='store_true');p.add_argument('--once',action='store_true');p.add_argument('--dependencies',type=Path);p.add_argument('--dependencies-sha256');a=p.parse_args(argv)
 if not a.run:print(json.dumps(dict(status='ORDERS_OFF_NO_REQUESTS',broker_writes=0)));return 0
 need(a.dependencies is not None and a.dependencies_sha256 is not None,'STREAM_PINNED_DEPENDENCY_REQUIRED');verify_dependencies(a.dependencies,a.dependencies_sha256)
 need(a.root is not None and a.root.absolute().is_relative_to(ROOT/'.private'),'STREAM_PRIVATE_ROOT');s=StreamIntake(a.root);stop=threading.Event();previous={sig:signal.signal(sig,lambda *_:stop.set()) for sig in (signal.SIGTERM,signal.SIGINT)}
 try:
  with s._writer():
   while not stop.is_set():
    need(shutil.disk_usage(s.root).free>=3*1024**3,'STREAM_DISK_GUARD')
    hour=unspent_target(s.root,now())
    if hour is None:
     if a.once:
      print(json.dumps(dict(status='STREAM_EXISTING_HOUR_PRESERVED',broker_writes=0)),flush=True);return 1
     stop.wait(1);continue
    setup=s.root/'ws-setup'/str(hour)
    publish(setup/'attempt.json',dict(schema='PUMP4_WS_SETUP_ATTEMPT_V1',target_ms=hour,observed_ms=now(),orders_allowed=False,money_authority=False))
    instruments=metadata(setup);recovery=recover(s,hour-H,instruments);publish(setup/'recovery-summary.json',recovery);active=s.prepare(hour,instruments)
    publish(setup/'preloaded.json',dict(target_ms=hour,active=len(active),completed_ms=now(),broker_writes=0));print(json.dumps(dict(status='STREAM_PRELOADED_ORDERS_OFF',hour=hour,active=len(active),observed_ms=now())),flush=True)
    try:asyncio.run(hour_stream(s,stop))
    except Exception as exc:print(json.dumps(dict(status='STREAM_HOUR_FAILED',hour=hour,error_type=type(exc).__name__,reason=str(exc),broker_writes=0)),flush=True)
    receipt=s.finish();print(json.dumps({k:v for k,v in receipt.items() if k!='rows'}),flush=True)
    if a.once:return 0 if receipt['hour_pass'] and not recovery['blocked'] else 1
    # An interrupted hour is never reconnected/retried. Recovery precedes NEXT H1.
    while now()<hour+120000 and not stop.is_set():stop.wait(1)
  return 0
 finally:
  for sig,handler in previous.items():signal.signal(sig,handler)
if __name__=='__main__':raise SystemExit(main())
