from pathlib import Path
import asyncio,hashlib,json,time,urllib.request,urllib.error,urllib.parse
import websockets
root=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/poly_execution_20261029');out=root/'public-probe';out.mkdir()
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**kw):raise ValueError('REDIRECT_REFUSED')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect());results=[]
def get(name,url):
 assert urllib.parse.urlsplit(url).hostname in {'gamma-api.polymarket.com','clob.polymarket.com','site.api.espn.com'}
 start=time.time_ns()//1000000;raw=b'';code=None;err=None
 try:
  with opener.open(urllib.request.Request(url,headers={'User-Agent':'Codex-data-only-window-check/1.0'},method='GET'),timeout=10) as f:raw=f.read(5000001);code=f.status
 except urllib.error.HTTPError as e:raw=e.read(5000001);code=e.code
 except Exception as e:err=type(e).__name__+': '+str(e)[:140]
 received=time.time_ns()//1000000
 with (out/(name+'.raw')).open('xb') as f:f.write(raw)
 meta=dict(name=name,url=url,method='GET',request_started_ms=start,response_received_ms=received,http_status=code,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),truncated=len(raw)>5000000,error=err)
 try:body=json.loads(raw)
 except Exception:body=None
 (out/(name+'.receipt.json')).write_text(json.dumps(meta,indent=2)+'\n');results.append(meta);return body
async def sports():
 start=time.time_ns()//1000000;messages=[];error=None;connected=None
 try:
  async with websockets.connect('wss://sports-api.polymarket.com/ws',open_timeout=12,ping_interval=None,max_size=2000000,proxy=None) as ws:
   connected=time.time_ns()//1000000;deadline=time.monotonic()+45
   while time.monotonic()<deadline:
    try:raw=await asyncio.wait_for(ws.recv(),timeout=min(5,max(.01,deadline-time.monotonic())))
    except asyncio.TimeoutError:continue
    received=time.time_ns()//1000000
    if raw=='ping':await ws.send('pong');continue
    if isinstance(raw,bytes):raw=raw.decode()
    messages.append(dict(received_ms=received,raw=raw,sha256=hashlib.sha256(raw.encode()).hexdigest()))
 except Exception as e:error=type(e).__name__+': '+str(e)[:180]
 (out/'sports-ws.json').write_text(json.dumps(dict(url='wss://sports-api.polymarket.com/ws',started_ms=start,connected_ms=connected,finished_ms=time.time_ns()//1000000,bounded_seconds=45,messages=messages,error=error),indent=2)+'\n')
async def main():
 sport=asyncio.create_task(sports())
 inp=root/'inputs';es=[json.loads(l) for l in (inp/'poly_espn/matchi.jsonl').read_bytes().splitlines()];ms={r['id']:r for r in (json.loads(l) for l in (inp/'poly_monitor/rynki.jsonl').read_bytes().splitlines()) if r['sob']=='dobavlen'};matched=[]
 for e in es:
  if not e.get('completed'):continue
  names=[str(x[0]).split()[-1].lower() for x in e.get('komandy',[])]
  candidates=[m for m in ms.values() if len(names)==2 and ' vs' in m['vopros'].lower() and ':' not in m['vopros'] and all(t in m['vopros'].lower() for t in names) and m['konec'][:10]==e['start'][:10]]
  if len(candidates)==1:matched.append(dict(event=e,market=candidates[0]))
 for league in ('basketball/nba','hockey/nhl'):
  await asyncio.to_thread(get,'espn-'+league.replace('/','-'),'https://site.api.espn.com/apis/site/v2/sports/'+league+'/scoreboard')
 for item in matched:
  m=item['market'];mid=m['id'];await asyncio.to_thread(get,'gamma-'+mid,'https://gamma-api.polymarket.com/markets/'+mid)
  await asyncio.to_thread(get,'clob-market-'+mid,'https://clob.polymarket.com/markets/'+m['cid'])
  await asyncio.to_thread(get,'book-'+mid,'https://clob.polymarket.com/book?token_id='+m['token'])
  await asyncio.to_thread(get,'fee-'+mid,'https://clob.polymarket.com/fee-rate?token_id='+m['token'])
 await sport
 (out/'matches.json').write_text(json.dumps(matched,ensure_ascii=False,indent=2)+'\n');(out/'requests.json').write_text(json.dumps(results,indent=2)+'\n')
 print(json.dumps(dict(status='CAPTURE_COMPLETE_DATA_ONLY',matched_events=len(matched),requests=len(results),http_statuses={str(s):sum(x['http_status']==s for x in results) for s in set(x['http_status'] for x in results)},sports=json.loads((out/'sports-ws.json').read_bytes())['error'],broker_writes=0)))
asyncio.run(main())
