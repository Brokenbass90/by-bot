#!/usr/bin/env python3
"""Isolated eight-symbol public source probe. Never imports a trading owner."""
from pathlib import Path
import sys,json,time,hashlib,os,asyncio,urllib.request,urllib.error,urllib.parse,ssl,inspect
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.pump4_source_probe_v1 import Probe,H,need,decode,projection,same
URL='wss://stream.bybit.com/v5/public/linear'
SYMBOLS=('AAVEUSDT','ACTUSDT','APTUSDT','BANANAS31USDT','BTCUSDT','ETHUSDT','SOLUSDT','ZROUSDT')
T=1793106000000
stamp=lambda:time.time_ns()//1000000
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**kw):raise ValueError('PROBE_REDIRECT_REJECTED')

class Log:
 def __init__(self,root):
  self.path=root/'raw.jsonl';self.f=self.path.open('x');self.count=0;self.bytes=0;self.synced=time.monotonic()
 def add(self,kind,**values):
  row=dict(kind=kind,received_ms=stamp(),received_monotonic_ns=time.monotonic_ns());row.update(values);raw=json.dumps(row,sort_keys=True)+'\n';self.count+=1;self.bytes+=len(raw.encode());need(self.count<=6000 and self.bytes<=16000000,'CAPTURE_BOUND');self.f.write(raw);self.f.flush()
  if time.monotonic()-self.synced>=1:os.fsync(self.f.fileno());self.synced=time.monotonic()
  return row
 def close(self):self.f.flush();os.fsync(self.f.fileno());self.f.close()

def rest_diagnostic(log):
 # Late REST diagnostic of the preceding boundary; never timely entry evidence.
 boundary=T-H;out={};opener=urllib.request.build_opener(NoRedirect(),urllib.request.ProxyHandler({}))
 for symbol in SYMBOLS:
  status=None
  params=dict(category='linear',symbol=symbol,interval='60',start=boundary-H,end=boundary+H-1,limit=2);begun=stamp();cpu=time.process_time();wall=time.monotonic()
  try:
   request=urllib.request.Request('https://api.bybit.com/v5/market/kline?'+urllib.parse.urlencode(params),headers={'User-Agent':'PUMP4-isolated-source-probe/1'},method='GET')
   try:response=opener.open(request,timeout=3)
   except urllib.error.HTTPError as exc:response=exc
   with response:status=response.code;raw=response.read(1000001)
   received=stamp();log.add('REST_FRAME',symbol=symbol,params=params,request_ms=begun,http_status=status,raw=raw.decode(errors='replace'),wire_raw_b64=__import__('base64').b64encode(raw).decode(),raw_sha256=hashlib.sha256(raw).hexdigest());body=decode(raw.decode());need(status==200 and type(body.get('retCode')) is int and body['retCode']==0,'REST_API');r=body['result'];need(r.get('category')=='linear' and r.get('symbol')==symbol and len(r['list'])==2,'REST_SCOPE');need([int(v[0]) for v in r['list']]==[boundary,boundary-H],'REST_PAIR')
   out[symbol]=dict(rows=r['list'],request_ms=begun,receive_ms=received,server_ms=body['time'],raw_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),wall_seconds=time.monotonic()-wall,cpu_seconds=time.process_time()-cpu,timely_entry_evidence=False)
   reference=Path('/opt/bybot-research/pump4-server-orders-off-20261023/candidate-e4feca498f37e27d/app/.private/pump4-supervisor-v1/archives')/str(boundary)
   seal=decode((reference/'receipt.json').read_text());rp=reference/'symbols'/(symbol+'.json');rr=rp.read_bytes();need(hashlib.sha256(rr).hexdigest()==seal['source_capture_files']['symbols/'+symbol+'.json'],'REFERENCE_HASH')
   full=decode(rr.decode());prior={int(bar[0]):tuple(bar[1:]) for cap in full['captures'] for bar in cap['body']['result']['list'] if int(bar[0]) in (boundary-H,boundary)}
   small={int(bar[0]):tuple(bar[1:]) for bar in r['list']};out[symbol]['closed_matches_sealed_prior']=same(small[boundary-H],prior[boundary-H]);out[symbol]['next_open_matches_sealed_prior']=__import__('decimal').Decimal(small[boundary][0])==__import__('decimal').Decimal(prior[boundary][0])
   log.add('REST_DIAGNOSTIC',symbol=symbol,params=params,request_ms=begun,http_status=status,raw=raw.decode(),raw_sha256=hashlib.sha256(raw).hexdigest())
  except Exception as exc:
   log.add('REST_DIAGNOSTIC_ERROR',symbol=symbol,request_ms=begun,error_type=type(exc).__name__)
   if status==403:break
  time.sleep(.15)
 return out

def consume_frame(log,probe,raw,*,connection,received,request,acked,errors):
 wire=raw.encode() if type(raw) is str else bytes(raw)
 log.add('WS_FRAME',connection=connection,wire_received_ms=received,raw=raw if type(raw) is str else None,wire_raw_b64=__import__('base64').b64encode(wire).decode(),raw_sha256=hashlib.sha256(wire).hexdigest())
 try:
  need(type(raw) is str and len(wire)<=1000000,'WS_FRAME')
  value=decode(raw)
  if value.get('op')=='subscribe':
   need(value.get('success') is True and value.get('req_id')==request['req_id'],'SUBSCRIPTION_REJECTED')
   acked.append(dict(connection=connection,received_ms=received))
  probe.add(raw,received_ms=received,connection=connection)
 except Exception as exc:
  errors.append(dict(connection=connection,received_ms=received,error_type=type(exc).__name__))
  log.add('WS_VALIDATION_ERROR',**errors[-1])

def supported(result,boundary):
 r=result.get('comparison',{});pairs=result.get('symbols',{});acks=result.get('subscription_acks',[])
 return (r.get('status')=='SEALED_REFERENCE_COMPARED' and len(r.get('symbols',{}))==8 and len(pairs)==8
  and all(v['closed_decimal_equal'] and v['next_open_equal'] for v in r['symbols'].values())
  and all(v['timely_pair'] and v['same_connection'] for v in pairs.values())
  and result.get('connection_attempts')==1 and not result.get('connection_errors')
  and not result.get('reconnected') and not result.get('validation_errors')
  and any(v['connection']==1 and v['received_ms']<boundary for v in acks))

async def observe(log,probe):
 import websockets
 while stamp()<T-120000:await asyncio.sleep(min(5,(T-120000-stamp())/1000))
 attempts=0;acked=[];errors=[];connection_errors=[]
 while stamp()<T+120000 and attempts<3:
  attempts+=1;connection=attempts;log.add('CONNECT_ATTEMPT',connection=connection,endpoint=URL)
  try:
   options=dict(open_timeout=8,ping_interval=20,ping_timeout=20,close_timeout=3,max_size=1000000,compression=None,ssl=ssl.create_default_context())
   if 'proxy' in inspect.signature(websockets.connect).parameters:options['proxy']=None
   async with websockets.connect(URL,**options) as ws:
    request=dict(op='subscribe',args=['kline.60.'+s for s in SYMBOLS],req_id='PUMP4-SOURCE-PROBE-'+str(connection));await ws.send(json.dumps(request));log.add('SUBSCRIBE_SENT',connection=connection,request=request);last_ping=time.monotonic()
    while stamp()<T+120000:
     if time.monotonic()-last_ping>=20:await ws.send(json.dumps(dict(op='ping')));last_ping=time.monotonic();log.add('APP_PING_SENT',connection=connection)
     try:raw=await asyncio.wait_for(ws.recv(),timeout=min(5,max(.01,(T+120000-stamp())/1000)))
     except asyncio.TimeoutError:continue
     consume_frame(log,probe,raw,connection=connection,received=stamp(),request=request,acked=acked,errors=errors)
  except Exception as exc:
   connection_errors.append(dict(connection=connection,error_type=type(exc).__name__,received_ms=stamp()))
   log.add('DISCONNECT',**connection_errors[-1])
  if stamp()<T+120000:await asyncio.sleep(2**attempts)
 return dict(subscription_acks=acked,validation_errors=errors,connection_attempts=attempts,connection_errors=connection_errors)

def compare_archive(probe,root,hour):
 a=root/'archives'/str(hour)
 if not (a/'receipt.json').exists():return dict(status='SEALED_ARCHIVE_NOT_YET_PRESENT')
 seal=decode((a/'receipt.json').read_text());need(seal['source_hour_open_ms']==hour,'ARCHIVE_HOUR');out={}
 for symbol in SYMBOLS:
  path=a/'symbols'/(symbol+'.json');raw=path.read_bytes();need(hashlib.sha256(raw).hexdigest()==seal['source_capture_files']['symbols/'+symbol+'.json'],'SEALED_CAPTURE_HASH');v=decode(raw.decode());need(v['status']=='READY_H1_BOOTSTRAP_NOT_ENTRY','REFERENCE_SOURCE_NOT_READY');rows=[row for cap in v['captures'] for row in cap['body']['result']['list']];out[symbol]=probe.compare(symbol,rows)
 return dict(status='SEALED_REFERENCE_COMPARED',symbols=out)

def main():
 os.nice(10)
 root=Path(sys.argv[1]).absolute();need(root==ROOT.parent/'run13','DETACHED_OUTPUT_ROOT');need(not root.exists() and not any(p.is_symlink() for p in (root,*root.parents)),'EXCLUSIVE_PROBE_ROOT');root.mkdir(mode=0o700,parents=True)
 universe=decode((ROOT/'configs/preregistered/pump4_v1_universe_20261020.json').read_text());need(hashlib.sha256(('\n'.join(universe['symbols'])+'\n').encode()).hexdigest()==universe['universe_sha256'] and all(s in universe['symbols'] for s in SYMBOLS) and universe['universe_sha256']=='935880315e2450e03e1df0beb43a8598a9e5440d86036a5469e436f76f6bd71a','FROZEN_UNIVERSE')
 manifest=dict(schema='PUMP4_EIGHT_SYMBOL_SOURCE_EXPERIMENT_V1',symbols=SYMBOLS,target_ms=T,ws_connect_ms=T-120000,stop_ms=T+120000,rest_boundary_ms=T-H,rest_mode='LATE_DIAGNOSTIC_ONLY_ONE_READ_PER_SYMBOL',selection='three majors plus fixed mid/late operational examples; no signal outcomes',universe_sha256=universe['universe_sha256'],source_files={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('research_lab/pump4_source_probe_v1.py','scripts/probe_pump4_source_architecture_v1.py')},production_admission=False,orders_allowed=False,money_authority=False)
 with (root/'manifest.json').open('x') as f:f.write(json.dumps(manifest,sort_keys=True,indent=2)+'\n');f.flush();os.fsync(f.fileno())
 log=Log(root);probe=Probe(T,SYMBOLS)
 try:
  rest=rest_diagnostic(log);(root/'rest-diagnostic.json').write_text(json.dumps(rest,sort_keys=True,indent=2)+'\n');print(json.dumps(dict(status='ISOLATED_PROBE_WAITING_FOR_WS_BOUNDARY',root=str(root),target_ms=T,rest_symbols=len(rest))),flush=True)
  ws=asyncio.run(observe(log,probe));result=dict(probe.summary(),**ws,broker_private_requests=0,broker_writes=0,quote_or_fill_not_measured=True)
  archive=Path('/opt/bybot-research/pump4-server-orders-off-20261023/candidate-e4feca498f37e27d/app/.private/pump4-supervisor-v1')
  try:result['comparison']=compare_archive(probe,archive,T)
  except Exception as exc:result['comparison']=dict(status='REFERENCE_COMPARISON_UNKNOWN',error_type=type(exc).__name__)
 except Exception as exc:
  result=dict(probe.summary(),status='PROBE_ABORTED',error_type=type(exc).__name__,source_delivery_hypothesis_supported=False,broker_private_requests=0,broker_writes=0)
 finally:log.close()
 if result.get('status')!='PROBE_ABORTED':
  result['source_delivery_hypothesis_supported']=supported(result,T)
 result['raw_log_sha256']=hashlib.sha256(log.path.read_bytes()).hexdigest();(root/'receipt.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
