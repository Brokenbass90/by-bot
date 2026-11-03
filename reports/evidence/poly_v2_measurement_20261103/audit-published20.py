"""Independent, read-only replay of the 20 already published V2 observations."""
from pathlib import Path
import json,hashlib,datetime,collections,math,re,os
S=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/research_lab');R=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824');D=R/'.private/poly_v2_execution_20261103';D.mkdir(mode=0o700,exist_ok=True)
files=['data/poly_95_v2_sdelki.jsonl','data/poly_monitor/knigi.jsonl','data/poly_monitor/rynki.jsonl','fabrika/poly_95_v2_sudya.py','poly_monitor_minuty.py','ZADANIE_CODEX_POLY_V2_ISPOLNITEL_2026_11_03.md','prereg/PREREG_POLY_95_V2_INPLAY_2026_11_01.md','prereg/PREREG_POLY_95_V2_INPLAY_2026_11_01_DOPOLNENIE1.md','prereg/PREREG_POLY_95_V2_INPLAY_2026_11_01_DOPOLNENIE2.md','results/poly_v2_istoriya_20261103T1325Z.json']
raw={};manifest={}
for n in files:
 p=S/n;b=p.read_bytes()
 if n.endswith('.jsonl'):b=b[:b.rfind(b'\n')+1]
 raw[n]=b;manifest[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'source':str(p),'copied_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 q=D/'source'/n;q.parent.mkdir(parents=True,exist_ok=True)
 with q.open('xb') as f:f.write(b)
books=[json.loads(l) for l in raw['data/poly_monitor/knigi.jsonl'].splitlines()];markets=[json.loads(l) for l in raw['data/poly_monitor/rynki.jsonl'].splitlines()];trades=[json.loads(l) for l in raw['data/poly_95_v2_sdelki.jsonl'].splitlines()];assert len(trades)==20,'EXACT_PUBLISHED_20_REQUIRED'
byid=collections.defaultdict(list)
for z in books:byid[z['id']].append(z)
added={};closed={}
for z in markets:
 if z['sob']=='dobavlen':added[z['id']]=z
 elif z.get('closed'):closed[z['id']]=z
results=[]
for k,t in enumerate(trades):
 candidates=[]
 for mid,m in added.items():
  if m.get('vopros')!=t['vopros'] or not m.get('konec'):continue
  r=sorted(byid[mid],key=lambda z:z['t']);start=datetime.datetime.fromisoformat(m['konec']).timestamp()
  for z in r:
   if z['bid'] is None or z['ask'] is None:continue
   middle=(z['bid']+z['ask'])/2;side=1 if middle>=.95 else 0 if middle<=.05 else None
   if side is None:continue
   if z['t']-r[0]['t']<300:break
   price=z['ask'] if side==1 else 1-z['bid']
   if price>.985 or z['t']<start:break
   if z['t']==t['t_vhod'] and math.isclose(price,t['cena'],abs_tol=1e-12):candidates.append((mid,m,z,side,closed.get(mid)))
   break
 a={'index':k+1,'question':t['vopros'],'match':t['match'],'entry_time_seconds':t['t_vhod'],'price':t['cena'],'recorded_win':t['win'],'candidate_count':len(candidates),'execution_status':'UNKNOWN_NOT_A_FILL','missing_execution_fields':['response_received_ms','actual_token_ask_ladder','accepting_orders','market_fee_schedule','future_capital_release_time'],'real_fills':0}
 if len(candidates)==1:
  mid,m,z,side,c=candidates[0];a.update(market_id=mid,known_token=m['token'],side='A' if side else 'B',price_origin='OBSERVED_A_ASK' if side else 'SYNTHETIC_ONE_MINUS_A_BID',depth_origin='A_ASK_WITHIN_TWO_CENTS' if side else 'A_BID_WITHIN_TWO_CENTS',quote_sha256=hashlib.sha256(json.dumps(z,sort_keys=True,separators=(',',':')).encode()).hexdigest(),quote_timestamp_origin='MONITOR_LOOP_START_BEFORE_REQUEST',observed_ms_authenticated=False)
  prices=json.loads(c['outcomePrices']) if c and isinstance(c.get('outcomePrices'),str) else c.get('outcomePrices') if c else None
  y=1 if prices and str(prices[0])=='1' else 0 if prices else None
  win=(side==y) if y is not None else None;net=(int(win)/t['cena']-1-.05*(1-t['cena'])) if win is not None else None
  a.update(outcome_matches=win==t['win'],frozen_formula_net=net,net_matches=net is not None and math.isclose(net,t['dohod'],abs_tol=1e-12),recorded_depth_matches=t['glubina']==z['gl_ask' if side else 'gl_bid'])
 results.append(a)
report={'schema':'POLY_V2_EXACT20_INDEPENDENT_SOURCE_AUDIT_V1','observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'published_observations':len(trades),'independent_match_keys':len({t['match'] for t in trades}),'uniquely_reproduced':sum(a['candidate_count']==1 for a in results),'outcome_and_frozen_net_matches':sum(a.get('outcome_matches') and a.get('net_matches') for a in results),'observed_a_ask':sum(a.get('side')=='A' for a in results),'synthetic_b_ask':sum(a.get('side')=='B' for a in results),'real_fills':0,'execution_qualified':0,'source_manifest':manifest,'observations':results,'note':'Descriptive published-cohort verification only; no judge run, new verdict, live order or source rewrite. Minute-monitor timestamps precede per-market requests; depth covers best+2c, not the requested limit0.985; original raw ladders/acceptance/fee schedule absent.'}
with (D/'audit.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in report.items() if k not in {'source_manifest','observations'}},ensure_ascii=False))
