"""ВТОРАЯ НОГА: внутридневной кросс-секционный разворот. Pre-reg: INTRADAY_REVERSAL_2026_07_22.json"""
import json, os, sys
UNI=json.load(open("research_lab/prereg/xsec_mature_universe_v2.json"))["symbols"]
D="research_lab/data/movers_5m"
BPS=0.0002+0.00055   # мейкер вход + тейкер выход на ногу
series={}
for s in UNI:
    p=os.path.join(D,s+".json")
    if not os.path.exists(p): continue
    r=json.load(open(p))
    if len(r)<20000: continue
    series[s]={b[0]//300000:b[4] for b in r}   # индекс 5-минутки -> close
syms=sorted(series)
allk=sorted(set().union(*[set(series[s]) for s in syms]))
print(f"монет: {len(syms)}, 5-мин баров в объединении: {len(allk)}")
def run(Hh,K):
    step=Hh*12                     # 12 баров в часе
    rets=[]
    i=step
    while i+step < len(allk):
        k0=allk[i-step]; k1=allk[i]; k2=allk[i+step]
        sc=[]
        for s in syms:
            p0=series[s].get(k0); p1=series[s].get(k1); p2=series[s].get(k2)
            if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
        if len(sc)<2*K+4: i+=step; continue
        sc.sort()                  # по возрастанию: начало = ПРОИГРАВШИЕ
        f=lambda s:(series[s][k2]/series[s][k1]-1.0)
        lo=[s for _,s in sc[:K]]; hi=[s for _,s in sc[-K:]]
        rets.append(sum(f(s) for s in lo)/K - sum(f(s) for s in hi)/K - 4*BPS)
        i+=step
    return rets
def M(r):
    if len(r)<20: return None
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x);pk=max(pk,e);dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r);v=sum((y-mu)**2 for y in r)/max(1,len(r)-1);sd=v**0.5
    h=len(r)//2
    def tot(z):
        q=1.0
        for x in z: q*=(1+x)
        return round((q-1)*100,1)
    return dict(tot=round((e-1)*100,1),dd=round(dd*100,1),
                sh=round(mu/sd*len(r)**0.5,2) if sd>0 else 0,h1=tot(r[:h]),h2=tot(r[h:]),n=len(r))
print("\nH,ч  K  |    n | итог    | DD    | Sharpe | 1-я    | 2-я")
best=None
for H in (2,4,8,12):
    for K in (5,10):
        r=run(H,K); a=M(r)
        if not a: continue
        mark=" <<<" if a['sh']>0.8 and a['h1']>0 and a['h2']>0 else ""
        print(f"{H:>3} {K:>3}  | {a['n']:>4} | {a['tot']:>7}% | {a['dd']:>4}% | {a['sh']:>6} | {a['h1']:>6}% | {a['h2']:>6}%{mark}")
        if a['sh']>0.8 and a['h1']>0 and a['h2']>0 and (best is None or a['sh']>best[2]['sh']):
            best=(H,K,a)
print()
print("ПОБЕДИТЕЛЬ:" , f"H={best[0]}ч K={best[1]} Sharpe={best[2]['sh']}" if best else "нет прошедших базовые ворота")
