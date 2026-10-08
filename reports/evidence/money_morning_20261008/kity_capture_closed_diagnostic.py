"""Frozen research-rule diagnostic only; strict PIT blocker remains unchanged."""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import time

signal.alarm(180)
ROOT = Path('/opt/bybot-research/kity-oct8-raw-intake-20261008')
OUT = ROOT / 'closed-research-projection'
OUT.mkdir(mode=0o700)
FACADE = Path('/opt/bybot-research/kity-cutoff-census-20261007/app/scripts/kity_m3_orders_off.py')
assert hashlib.sha256(FACADE.read_bytes()).hexdigest() == '522c7e6b4accd5375c472b16cca21da941c4b292735efc8b22e873c847495834'
spec = importlib.util.spec_from_file_location('facade', FACADE)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
census = json.loads(Path('/opt/bybot-research/kity-cutoff-census-20261007/app/.private/kity_m3_orders_off/census-2026-10-08.json').read_text())
rows = json.loads(census['raw'])['symbols']
# Explicit literal frozen research TRADING census, not a modified assessor.
# Do not pass this projection as an accepted replacement for the strict census.
population = [r for r in rows if r.get('contractType')=='PERPETUAL' and r.get('quoteAsset')=='USDT'
              and r.get('status')=='TRADING']
ranked = []
for row in population:
    cap = json.loads((ROOT / ('oi-' + row['symbol'] + '.json')).read_text())
    assert hashlib.sha256(cap['raw'].encode()).hexdigest()==cap['sha256']
    pts = [r for r in json.loads(cap['raw']) if r.get('timestamp')==1791417300000]
    assert len(pts)==1
    value = float(pts[0]['sumOpenInterestValue'])
    if value > 0:
        ranked.append((value,row['symbol']))
ranked.sort(reverse=True)
top = [s for _,s in ranked[:50]]
def save(name, obj):
    data=json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    with (OUT/name).open('xb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    return hashlib.sha256(data).hexdigest()
save('scope.json',dict(evidence_kind='FROZEN_RESEARCH_RULE_DIAGNOSTIC_ONLY',strict_assessor_reason='PIT_STATUS_AMBIGUOUS',
    orders_allowed=False,money_ready=False,explicit_status_exclusion=['GAIBUSDT'],top50=top,
    received_ms=time.time_ns()//1000000))
def capture(s):
    try:
        cap=api.get_public('BINANCE','/fapi/v1/klines',dict(symbol=s,interval='1d',endTime=1791417599999,limit=60))
        save('klines-'+s+'.json',cap)
        return s,cap
    except api.PublicIOError as exc:
        save('error-'+s+'.json',dict(symbol=s,error=str(exc)))
        return s,None
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    captured=dict(pool.map(capture,top))
features=[];excluded={}; errors=[]
for s in top:
    cap=captured[s]
    if cap is None:
        errors.append(s);continue
    bars=json.loads(cap['raw'])
    if len(bars)<60:
        excluded[s]='LT60';continue
    assert len(bars)==60 and int(bars[-1][0])==1791331200000
    assert all(int(b[6])<1791417600000 for b in bars)
    assert all(int(b[0])-int(a[0])==86400000 for a,b in zip(bars,bars[1:]))
    quote,taker=float(bars[-1][7]),float(bars[-1][10])
    assert 0<=taker<=quote
    if quote>0:features.append((taker/quote,s))
features.sort(); n=len(features);k=n//10
diag=dict(evidence_kind='FROZEN_RESEARCH_RULE_DIAGNOSTIC_ONLY',strict_assessor_reason='PIT_STATUS_AMBIGUOUS',
    population=len(population),top50=top,feature_count=n,decile_count=k,errors=errors,excluded=excluded,
    long=[dict(symbol=s,taker=round(v,6)) for v,s in features[-k:]] if n>=30 and not errors else [],
    short=[dict(symbol=s,taker=round(v,6)) for v,s in features[:k]] if n>=30 and not errors else [],
    all_features={s:v for v,s in features},completed_ms=time.time_ns()//1000000,
    orders_allowed=False,money_ready=False,signal_valid=False,prospective_eligible=False,
    total_bytes=sum(p.stat().st_size for p in OUT.iterdir() if p.is_file()))
save('diagnostic.json',diag)
print(json.dumps({k:v for k,v in diag.items() if k not in ('top50','all_features')},sort_keys=True),flush=True)
