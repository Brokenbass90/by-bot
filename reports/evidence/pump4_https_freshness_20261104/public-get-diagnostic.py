from pathlib import Path
import json,hashlib,sys,time,datetime as dt,concurrent.futures,subprocess
candidate=Path('/opt/bybot-research/pump4-current-hour-repair-20261101/candidate-05f89618d8550664');raw=(candidate/'verification-source-hashes.json').read_bytes();assert hashlib.sha256(raw).hexdigest()=='05f89618d8550664cf2d914f000ef9f7b101d32176032adb78a6d7bbbdb03dfd'
pins=json.loads(raw)
for name,pin in pins.items():
 p=Path(name);assert not p.is_absolute() and '..' not in p.parts;assert hashlib.sha256((candidate/'app'/p).read_bytes()).hexdigest()==pin
sys.path.insert(0,str(candidate/'app'))
from research_lab.pump4_bybit_sources_v1 import public_get,closed_h1
H=3600000;entry=int(dt.datetime(2026,11,3,3,tzinfo=dt.timezone.utc).timestamp()*1000);first=entry-1001*H
queries=[dict(category='linear',symbol='SIRENUSDT',interval='60',start=first,end=entry+H-1,limit=1000),dict(category='linear',symbol='SIRENUSDT',interval='60',start=first,end=entry-999*H-1,limit=1000)]
rows=[]
for index,delay in enumerate((0,2,4)):
 if delay:time.sleep(delay)
 started=time.time_ns()//1000000
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:caps=list(pool.map(lambda p:public_get('/v5/market/kline',p),queries))
 cutoff=time.time_ns()//1000000;t0=time.perf_counter_ns();result=None;error=None
 try:result=closed_h1(caps,'SIRENUSDT',next_open_ms=entry,observed_ms=cutoff)
 except (ValueError,KeyError) as e:error=str(e)
 stages=dict(fetch_wall_ms=cutoff-started,normalize_ms=(time.perf_counter_ns()-t0)/1e6)
 checks=[]
 if result is not None:
  for name,stamp in [('source_ms',result['source_ms']),('available_ms',result['available_ms'])]:checks.append(dict(field=name,stamp_ms=stamp,age_at_actual_cutoff_ms=cutoff-stamp,within_0_to_5000=0<=cutoff-stamp<=5000))
 rows.append(dict(sample=index,actual_started_ms=started,actual_cutoff_ms=cutoff,captures=caps,stages=stages,checks=checks,normalization_error=error,diagnostic_only=True))
print(json.dumps(dict(schema='PUMP4_PUBLIC_HTTPS_FRESHNESS_DIAGNOSTIC_V1',observed_ms=time.time_ns()//1000000,source_candidate_manifest_sha256=hashlib.sha256(raw).hexdigest(),diagnostic_entry_hour_ms=entry,historical_failed_capture_recovered=False,causal_plan_run=False,financial_owner_constructed=False,financial_mutations=0,requests=len(rows)*2,rows=rows,owner_state=subprocess.check_output(['systemctl','show','pump4-execution-owner.service','--property=ActiveState,MainPID,NRestarts','--no-pager'],text=True))))
