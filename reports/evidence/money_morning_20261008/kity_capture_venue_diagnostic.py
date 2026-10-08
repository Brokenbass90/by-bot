"""Public comparison for diagnostic basket; no admission or account authority."""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import time

signal.alarm(180)
ROOT=Path('/opt/bybot-research/kity-oct8-raw-intake-20261008')
OUT=ROOT/'venue-evidence';OUT.mkdir(mode=0o700)
FACADE=Path('/opt/bybot-research/kity-cutoff-census-20261007/app/scripts/kity_m3_orders_off.py')
assert hashlib.sha256(FACADE.read_bytes()).hexdigest()=='522c7e6b4accd5375c472b16cca21da941c4b292735efc8b22e873c847495834'
spec=importlib.util.spec_from_file_location('facade',FACADE)
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
diag=json.loads((ROOT/'closed-research-projection/diagnostic.json').read_text())
assert not diag['orders_allowed'] and diag['feature_count']==49 and diag['decile_count']==4
symbols=[r['symbol'] for r in diag['long']+diag['short']]
assert len(symbols)==8 and len(set(symbols))==8
def save(name,obj):
    raw=json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    assert len(raw)<2*1024*1024
    with (OUT/name).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    return hashlib.sha256(raw).hexdigest()
def cap(name,venue,endpoint,params):
    try:
        capture=api.get_public(venue,endpoint,params);save(name,capture);return capture
    except api.PublicIOError as exc:
        save(name,dict(venue=venue,endpoint=endpoint,params=params,error=str(exc),observed_ms=time.time_ns()//1000000))
        return None
save('scope.json',dict(evidence_kind='PUBLIC_DIAGNOSTIC_EXTERNAL_BASKET_NOT_ADMITTED',symbols=symbols,
    orders_allowed=False,money_ready=False,strict_signal_valid=False,clock_bound_is_observed_not_future_guarantee=True))
cap('binance-instruments.json','BINANCE','/fapi/v1/exchangeInfo',{})
cap('binance-funding-info.json','BINANCE','/fapi/v1/fundingInfo',{})
tasks=[]
for s in symbols:
    tasks += [(f'bybit-instrument-{s}.json','BYBIT','/v5/market/instruments-info',dict(category='linear',symbol=s)),
              (f'bybit-ticker-{s}.json','BYBIT','/v5/market/tickers',dict(category='linear',symbol=s)),
              (f'bybit-funding-{s}.json','BYBIT','/v5/market/funding/history',dict(category='linear',symbol=s,limit=50)),
              (f'binance-funding-{s}.json','BINANCE','/fapi/v1/fundingRate',dict(symbol=s,limit=100))]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(lambda args:cap(*args),tasks))
for venue in ('BINANCE','BYBIT'):
    endpoint='/fapi/v1/time' if venue=='BINANCE' else '/v5/market/time'
    cap(venue.lower()+'-clock-before.json',venue,endpoint,{})
    tasks=[(venue.lower()+f'-book-{s}.json',venue,
            '/fapi/v1/depth' if venue=='BINANCE' else '/v5/market/orderbook',
            dict(symbol=s,limit=100) if venue=='BINANCE' else dict(category='linear',symbol=s,limit=100)) for s in symbols]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda args:cap(*args),tasks))
    cap(venue.lower()+'-clock-after.json',venue,endpoint,{})
    save(venue.lower()+'-common-assessment.json',dict(now_ms=time.time_ns()//1000000))
files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}
save('terminal.json',dict(completed_ms=time.time_ns()//1000000,files=files,broker_writes=0,
    orders_allowed=False,money_ready=False,total_bytes=sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())))
print(json.dumps(dict(files=len(files),completed_ms=time.time_ns()//1000000,broker_writes=0,orders_allowed=False)),flush=True)
