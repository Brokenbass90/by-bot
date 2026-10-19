import sys, json, math, os
sys.path.insert(0,'.')
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import research_lab.alpaca_smart_v1 as S
from research_lab.alpaca_dannye import chasovye, v_dnevnye
from research_lab.alpaca_dvizhok_x_v1 import dvizhok_x
import research_lab.alpaca_u2 as U2M
D=Path('/root/w/data/alpaca_pit_daily_deep_20260925')
sk={}
for f in sorted((D/'bars').glob('*.json')):
    r=json.load(open(f))['records']; best=(0,None)
    for a,b in zip(r,r[1:]):
        if a['c']>0 and b['c']>0:
            x=abs(math.log(b['c']/a['c']))
            if x>best[0]: best=(x,b['t'])
    if best[0]>math.log(4): sk[f.stem]=datetime.fromtimestamp(best[1]/1000,tz=timezone.utc).date()
syrye,_=chasovye(Path('data_cache/equities_daily_10y')); U=U2M.zagruzit_u2(D,Path('/root/w/data/akcii_grouped'),v_dnevnye(syrye))
v_u2=[s for s in sk if s in U.p]; print('sklejki v U2:',len(v_u2),v_u2)
cfg=json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text()); clusters=[{str(x) for x in g} for g in cfg["clusters"]]
o0,o1=date.fromisoformat(U2M.OKNO[0]),date.fromisoformat(U2M.OKNO[1]); okno=[s for s in U.sessii if o0<=s<=o1]; rasp=U2M.raspisanie(U.sessii,okno)
S.CTX["ruka"]="BASE"; base=U2M.mesyachnye(U,rasp,clusters)
z=dvizhok_x(U.p,okno,base,initial_capital=1000.0,target_gross_exposure=0.70,cost_bps_per_side=20.0,policy=U2M.POL,mest=4)
hit=[]
for t in z['trades']:
    s=t['symbol']
    if s in sk:
        d=sk[s]; e0=date.fromisoformat(t['entry_session']); e1=date.fromisoformat(t['exit_session'])
        hit.append(dict(s=s,sklejka=d.isoformat(),vhod=t['entry_session'],vyhod=t['exit_session'],pnl=round(t['pnl'],1),
                        cherez=e0<d<=e1, otbor_v_okne_80d=(e0-timedelta(days=130))<=d<=e0))
print('sdelok BASE po sklejkam:',len(hit)); [print(h) for h in hit]
print('PnL sdelok cherez sklejku:',sum(h['pnl'] for h in hit if h['cherez']),' otbor posle sklejki (<130d):',sum(h['pnl'] for h in hit if h['otbor_v_okne_80d']))
json.dump(dict(sklejki={k:v.isoformat() for k,v in sk.items()},v_u2=v_u2,sdelki=hit),open('out/sklejki_u2.json','w'),ensure_ascii=False,indent=1)
