"""One-shot public raw intake; no strategy verdict, credentials, or orders."""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import threading
import time

signal.alarm(600)
ROOT = Path('/opt/bybot-research/kity-oct8-raw-intake-20261008')
ROOT.mkdir(mode=0o700)
FACADE = Path('/opt/bybot-research/kity-cutoff-census-20261007/app/scripts/kity_m3_orders_off.py')
assert hashlib.sha256(FACADE.read_bytes()).hexdigest() == '522c7e6b4accd5375c472b16cca21da941c4b292735efc8b22e873c847495834'
SOURCE = Path('/opt/bybot-research/kity-cutoff-census-20261007/app/.private/kity_m3_orders_off/census-2026-10-08.json')
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == '26dbd005d7562eaab500f24466a8558e7561b85f8f0cd6796a34d3a7a961541a'
spec = importlib.util.spec_from_file_location('public_facade', FACADE)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
cutoff = 1791417300000
census = json.loads(SOURCE.read_text())
rows = json.loads(census['raw'])['symbols']
population = [r for r in rows if r.get('contractType') == 'PERPETUAL' and r.get('quoteAsset') == 'USDT'
              and r.get('marginAsset') == 'USDT' and r.get('onboardDate', 0) <= cutoff
              and r.get('deliveryDate', 0) > cutoff]
assert len(population) <= 900
symbols = sorted(r['symbol'] for r in population)
assert len(set(symbols)) == len(symbols)
lock = threading.Lock()
next_call = 0.0
def save(name, value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
    assert len(raw) <= 2 * 1024 * 1024
    with (ROOT / name).open('xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    return hashlib.sha256(raw).hexdigest()
save('intake_manifest.json', dict(day='2026-10-08', cutoff_ms=cutoff, started_ms=time.time_ns() // 1000000,
     census_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), population=symbols,
     statuses={r['symbol']:r['status'] for r in population}, max_calls=900, concurrency=4,
     min_request_spacing_ms=100, total_alarm_seconds=600, orders_allowed=False, broker_writes=0))
def capture(sym):
    global next_call
    with lock:
        delay = max(0.0, next_call - time.monotonic())
        if delay:
            time.sleep(delay)
        next_call = time.monotonic() + 0.1
    params = dict(symbol=sym, period='5m', endTime=cutoff, limit=1)
    try:
        cap = api.get_public('BINANCE', '/futures/data/openInterestHist', params)
        sha = save('oi-' + sym + '.json', cap)
        body = json.loads(cap['raw'])
        points = [r for r in body if isinstance(r, dict) and r.get('timestamp') == cutoff] if isinstance(body,list) else []
        return dict(symbol=sym, capture_sha256=sha, raw_sha256=cap['sha256'], exact_points=len(points))
    except api.PublicIOError as exc:
        error = dict(symbol=sym, endpoint='/futures/data/openInterestHist', params=params,
                     failed_ms=time.time_ns() // 1000000, error=str(exc))
        save('error-' + sym + '.json', error)
        return dict(symbol=sym, error=str(exc), exact_points=0)
results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for result in pool.map(capture, symbols):
        results.append(result)
        if len(results) % 100 == 0:
            print(json.dumps(dict(progress=len(results), total=len(symbols))), flush=True)
files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.iterdir() if p.is_file()}
summary = dict(completed_ms=time.time_ns() // 1000000, population_count=len(symbols), results=results,
     files=files, total_bytes=sum(p.stat().st_size for p in ROOT.iterdir()), orders_allowed=False,
     broker_writes=0, capture_complete=len(results)==len(symbols),
     exact_oi_complete=all(r.get('exact_points')==1 and not r.get('error') for r in results))
save('terminal.json', summary)
print(json.dumps({k:v for k,v in summary.items() if k not in ('files','results')}, sort_keys=True), flush=True)
