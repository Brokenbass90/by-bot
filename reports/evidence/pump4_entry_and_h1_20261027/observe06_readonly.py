"""One-hour diagnostic only: immutable receipts + public GET quotes. No project imports."""
from pathlib import Path
import time,json,hashlib,urllib.request,statistics,datetime,os
root=Path('/opt/bybot-research/pump4-server-orders-off-20261023/candidate-ffb31e24c703d9ed/app/.private/pump4-supervisor-v1');op=root.parents[3]/'entry-handoff-20261027'
hour=1793080800000 # 27Oct06UTC
now=lambda:time.time_ns()//1000000
assert hour==int(datetime.datetime(2026,10,27,6,tzinfo=datetime.timezone.utc).timestamp()*1000)
archive=root/'archives'/str(hour);cache={};pending={};last_summary=None;last_quote=0;quotes=0;heartbeat=0;quote_links=[]
quote_root=op/'observer06-public-quotes';assert not quote_root.exists();quote_root.mkdir(mode=0o700)
while now()<hour+6*60000:
    context=archive/'capture-context.json'
    if context.exists():
        cid=hashlib.sha256(context.read_bytes()).hexdigest()
        for p in (root/'streamed'/cid).glob('*.json'):
            if p.name not in cache:
                r=json.loads(p.read_bytes());cache[p.name]=r
                if any(d['decision']['signal'] is not None for d in r['result'].get('decisions',[])):pending[r['symbol']]=r
    rows=list(cache.values());values=[r['publication_completed_ms']-hour for r in rows if r['result'].get('status')=='CLOSED_H1_INTAKE_PASS'];proof=root/'capture-process'/(str(hour)+'.json')
    if pending and now()>=hour and quotes<30 and now()-last_quote>=7000:
        last_quote=now();url='https://api.bybit.com/v5/market/tickers?category=linear'
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'PUMP4-one-hour-public-quote-observer/1'}),timeout=3) as f:raw=f.read(3000001)
            assert len(raw)<=3000000;body=json.loads(raw);assert body['retCode']==0;received=now();sha=hashlib.sha256(raw).hexdigest();qfile=quote_root/(str(last_quote)+'-'+sha+'.json')
            with qfile.open('xb') as f:f.write(raw)
            tickers={r['symbol']:r for r in body['result']['list']}
            for symbol,r in pending.items():
                q=tickers.get(symbol);link=dict(symbol=symbol,publication_ms=r['publication_completed_ms'],observer_seen_after_publication=True,quote_source_ms=body['time'],quote_request_ms=last_quote,quote_received_ms=received,quote_capture_sha256=sha,quote_after_publication_ms=body['time']-r['publication_completed_ms'],signal_present=any(x['decision']['signal'] is not None for x in r['result'].get('decisions',[])))
                if q:link.update({k:q[k] for k in ('lastPrice','bid1Price','ask1Price')})
                quote_links.append(link)
            pending.clear();quotes+=1
        except Exception as exc:
            print(json.dumps(dict(kind='QUOTE_UNKNOWN',observed_ms=now(),reason=type(exc).__name__)),flush=True);quotes+=1
    summary=dict(kind='PROGRESS',root=str(root),observed_ms=now(),source_hour_open_ms=hour,published=len(rows),intake_pass=len(values),published_within60s=sum(0<=v<=60000 for v in values),publication_delay_ms=dict(min=min(values),median=statistics.median(values),max=max(values)) if values else None,full_seal_present=(archive/'receipt.json').exists(),process_proof_present=proof.exists(),signal_symbols=[r['symbol'] for r in rows if any(d['decision']['signal'] is not None for d in r['result'].get('decisions',[]))],quote_captures=quotes,quote_linked_symbols=len(quote_links),broker_writes=0,diagnostic_not_execution=True)
    key=(len(rows),summary['process_proof_present'],quotes)
    if key!=last_summary or now()-heartbeat>=30000:print(json.dumps(summary),flush=True);last_summary=key;heartbeat=now()
    if len(rows)==137 and proof.exists() and not pending:break
    time.sleep(2)
print(json.dumps(dict(kind='FINAL_QUOTE_LINKS',observed_ms=now(),source_hour_open_ms=hour,links=quote_links,quote_captures=quotes,execution_fill_prices_NOT_observed=True,quote_lag_is_explicit=True,broker_writes=0)),flush=True)
