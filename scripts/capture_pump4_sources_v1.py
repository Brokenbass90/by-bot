#!/usr/bin/env python3
"""PUBLIC DATA_ONLY137 capture; optional existing causal DATA intake callback."""
import argparse,concurrent.futures as cf,hashlib,json,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.pump4_bybit_sources_v1 import checked,closed_h1,universe,UNIVERSE_SHA,H,need
from research_lab.pump4_public_retry_v1 import observed_public_get as public_get,PublicRetry
from research_lab.kity_micro_physical_owner_v1 import publish


def capture(root,*,on_symbol=None):
    root=Path(root).absolute()
    need(root.is_relative_to(ROOT/'.private') and not root.exists() and '..' not in root.parts
        and not any(p.is_symlink() for p in (root,*root.parents)),'EXCLUSIVE_PRIVATE_ROOT')
    root.mkdir(mode=0o700,parents=True);start=time.time_ns()//1000000
    def failed_attempt(value):
        publish(root/'http-attempts'/('failed-'+str(value['request_serial'])+'.json'),value)
    reader=PublicRetry(getter=lambda path,params,**kw:public_get(path,params,**kw),persist=failed_attempt)
    clock=reader.get('/v5/market/time',{});checked(clock,'/v5/market/time',now_ms=time.time_ns()//1000000,private=False)
    next_open=clock['body']['time']//H*H;publish(root/'clock.json',clock)
    reader.anchor(next_open+60000)
    pages=[];cursor='';seen=set();instruments={}
    for _ in range(8):
        c=reader.get('/v5/market/instruments-info',dict(category='linear',limit=1000,**({'cursor':cursor} if cursor else {})))
        b=checked(c,'/v5/market/instruments-info',now_ms=time.time_ns()//1000000,private=False);pages.append(c)
        for row in b['list']:
            need(row['symbol'] not in instruments,'DUPLICATE_INSTRUMENT');instruments[row['symbol']]=row
        cursor=b.get('nextPageCursor','');need(isinstance(cursor,str) and cursor not in seen,'INSTRUMENT_CURSOR')
        if not cursor:break
        seen.add(cursor)
    else:raise ValueError('INSTRUMENT_PAGE_BOUND')
    publish(root/'instrument-pages.json',dict(complete=True,pages=pages))
    tickers=reader.get('/v5/market/tickers',dict(category='linear'))
    checked(tickers,'/v5/market/tickers',now_ms=time.time_ns()//1000000,private=False);publish(root/'tickers.json',tickers)
    # This immutable prefix permits per-symbol processing before full coverage.
    # The final receipt still proves the complete137 census separately.
    context=dict(schema='PUMP4_PUBLIC_CAPTURE_CONTEXT_V1',universe_sha256=UNIVERSE_SHA,
        census=137,source_hour_open_ms=next_open,started_ms=start,
        source_capture_files={n:hashlib.sha256((root/n).read_bytes()).hexdigest()
            for n in ('clock.json','instrument-pages.json','tickers.json')},
        orders_allowed=False,money_authority=False)
    publish(root/'capture-context.json',context)
    def one(symbol):
        caps=[];i=instruments.get(symbol)
        if not i or i.get('status')!='Trading' or i.get('quoteCoin')!='USDT' or i.get('contractType')!='LinearPerpetual':
            result=dict(status='UNAVAILABLE_INSTRUMENT',symbol=symbol,captures=[])
        else:
            try:
                first=next_open-1001*H;end=next_open+H-1
                for _ in range(3):
                    c=reader.get('/v5/market/kline',dict(category='linear',symbol=symbol,interval='60',start=first,end=end,limit=1000));caps.append(c)
                    b=checked(c,'/v5/market/kline',now_ms=time.time_ns()//1000000,private=False)
                    if not b['list']:break
                    end=min(int(row[0]) for row in b['list'])-1
                    if end<first:break
                source=closed_h1(caps,symbol,next_open_ms=next_open,observed_ms=time.time_ns()//1000000)
                result=dict(status='READY_H1_BOOTSTRAP_NOT_ENTRY',symbol=symbol,source=source,captures=caps)
            except (ValueError,KeyError,TypeError,OSError) as e:
                result=dict(status='BLOCKED_SOURCE',symbol=symbol,reason=str(e),captures=caps)
        publish(root/'symbols'/(symbol+'.json'),result);return result
    results={}
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(one,symbol):symbol for symbol in universe()}
        for future in cf.as_completed(futures):
            result=future.result();symbol=futures[future];results[symbol]=result
            # one() returned only after atomic publication/fsync. Main-thread
            # callback avoids concurrent strategy/journal writers.
            if on_symbol is not None:on_symbol(root,symbol)
    results=[results[symbol] for symbol in universe()]
    receipt=dict(schema='PUMP4_FROZEN137_PUBLIC_BOOTSTRAP_RECEIPT_V1',status='DATA_ONLY_BOOTSTRAP_COMPLETED',
        universe_sha256=UNIVERSE_SHA,census=len(results),ready=sum(r['status']=='READY_H1_BOOTSTRAP_NOT_ENTRY' for r in results),
        blocked=[{k:v for k,v in r.items() if k not in ('source','captures')} for r in results if r['status']!='READY_H1_BOOTSTRAP_NOT_ENTRY'],
        source_hour_open_ms=next_open,started_ms=start,completed_ms=time.time_ns()//1000000,
        public_get_requests=reader.http_attempts,
        public_capture_pages=1+len(pages)+1+sum(len(r['captures']) for r in results),
        failed_http_attempts=len(list((root/'http-attempts').glob('*.json'))),
        source_capture_files={str(p.relative_to(root)):__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.json')},
        bootstrap_only=True,prospective_decisions_credited=0,
        strategy_calls=0 if on_symbol is None else None,data_intake_callback_used=on_symbol is not None,
        broker_private_requests=0,broker_writes=0,
        orders_allowed=False,money_authority=False)
    publish(root/'receipt.json',receipt);return receipt


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',action='store_true');p.add_argument('--root',type=Path)
    p.add_argument('--stream-symbols',action='store_true')
    a=p.parse_args(argv)
    if not a.capture:print(json.dumps(dict(status='DATA_ONLY_OFFLINE_NO_REQUESTS',broker_writes=0)));return 0
    if not a.root:raise ValueError('EXPLICIT_OUTPUT_ROOT_REQUIRED')
    def completed(root,symbol):
        raw=(root/'symbols'/(symbol+'.json')).read_bytes()
        print(json.dumps(dict(schema='PUMP4_PUBLIC_SYMBOL_NOTICE_V1',symbol=symbol,
            capture_sha256=hashlib.sha256(raw).hexdigest()),sort_keys=True),flush=True)
    r=capture(a.root,on_symbol=completed if a.stream_symbols else None)
    if not a.stream_symbols:print(json.dumps({k:v for k,v in r.items() if k!='source_capture_files'},sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
