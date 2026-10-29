from pathlib import Path
from datetime import date
import hashlib,json,time,sys,os
base=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/alpaca_25_75_20261029');source=base/'source';os.chdir(source);sys.path.insert(0,str(source))
import research_lab.alpaca_u2 as U2
import research_lab.alpaca_h3 as H3
import research_lab.alpaca_h5_bil as H5
import research_lab.alpaca_doli_svobodnogo as MIX
cache=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/equities_1h_parity_20260914');fund=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/research_lab/data/alpaca_bil_sgov_20261019/all/bars/BIL.json')
inputs={}
for p in [*sorted(cache.glob('*_M5.csv')),fund]:
 st=p.stat();inputs[str(p)]=dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size=st.st_size,mtime_ns=st.st_mtime_ns,inode=st.st_ino)
U=U2.zagruzit_u58(cache,bez_sektorov=False);want=set(next(w["symbols"] for w in json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_bytes())["windows"] if w["id"]=="live_universe_2024_2026_cached_intraday_proxy"))|{"SPY"};assert want.issubset(U.p)
U=U2.Vselennaya({s:v for s,v in U.p.items() if s in want},U.sessii,{}, {},U.sektora,filtr=False)
assert set(U.p)==want and len(want)==58 and 'QQQ' not in U.p
B=H5.fond(fund);S={b.session_date:H5.Bar(float(b.open),float(b.close)) for b in U.p['SPY']}
window=[s for i,s in enumerate(U.sessii) if i>=200 and date.fromisoformat(U2.OKNO[0])<=s<=date.fromisoformat(U2.OKNO[1]) and s in S and s in B];assert len(window)>200
cfg=json.loads(Path('configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json').read_bytes());clusters=[set(x) for x in cfg['clusters']]
decisions=U2.mesyachnye(U,U2.raspisanie(U.sessii,window),clusters);z,rows,rot,stop=H3.monthly_kniga(U,window,decisions,20.0)
base_metrics,days,base_eq=H3.overlay(U,window,rows,rot,stop,20.0,'NONE');F=MIX.smes(S,B,.25)
overlay_metrics,overlay_days,overlay_eq=H5.overlay_fond(rows,rot,stop,F,3.0,polosa=.05)
assert days==overlay_days
stress,sd,se=H5.overlay_fond(rows,rot,stop,F,10.0,polosa=.05)
def monthly(ds,eq):
 out={};prev=1000.;start=prev;key=None
 for d,value in zip(ds,eq):
  k=d.isoformat()[:7]
  if key is not None and k!=key:out[key]=(prev/start-1)*100;start=prev
  key=k;prev=value
 if key:out[key]=(prev/start-1)*100
 return out
bm=monthly(days,base_eq);om=monthly(days,overlay_eq)
for label,m,mr in [('monthly_cash',base_metrics,bm),('monthly_idle_25_75',overlay_metrics,om)]:m.update(worst_month_pct=min(mr.values()),months=len(mr),negative_months=sum(v<0 for v in mr.values()))
for name,before in inputs.items():
 p=Path(name);st=p.stat();assert dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size=st.st_size,mtime_ns=st.st_mtime_ns,inode=st.st_ino)==before,'INPUT_CHANGED'
out=dict(schema='ALPACA_SAME_DATA_PAIRED_REPLAY_V1',status='PASS_RESEARCH_FULL_WARMUP_REPLAY_NOT_PRODUCTION_ACCEPTANCE',warmup_sessions=200,observed_ms=time.time_ns()//1000000,period=[str(window[0]),str(window[-1])],sessions=len(window),universe=sorted(want),universe_sha256=hashlib.sha256(json.dumps(sorted(want),sort_keys=True,separators=(',',':')).encode()).hexdigest(),stock_cost_bps_per_side=20,fund_cost_bps_per_side=3,arms=dict(monthly_cash=base_metrics,monthly_idle_25_75=overlay_metrics,monthly_idle_25_75_fund10bps=stress),months=dict(monthly_cash=bm,monthly_idle_25_75=om),selection_count=len(decisions),trade_count=len(z['trades']),inputs=inputs,production_400_280_40_loss_latch_simulated=False,internal_synthetic_rebalance_cost_charged=False,source_refs=['47b90288c55114ad7e730377c2265b54c5a97406','2e68b1f5ba6d2767c2144c5dafd8f10a6d2908c6'],broker_requests=0,broker_writes=0)
(base/'paired-full-warmup-result.json').write_text(json.dumps(out,indent=2,ensure_ascii=False,default=str)+'\n');(base/'equity-full-warmup-curves.json').write_text(json.dumps(dict(dates=[str(d) for d in days],monthly_cash=base_eq,monthly_idle_25_75=overlay_eq,monthly_idle_25_75_fund10bps=se))+'\n')
print(json.dumps({k:out[k] for k in ('status','period','sessions','arms','selection_count','trade_count')},ensure_ascii=False))
