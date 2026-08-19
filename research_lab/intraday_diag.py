"""Диагностика: нет сигнала или издержки? Считаем ВАЛОВОЙ результат обоих направлений."""
import json, os
UNI=json.load(open("research_lab/prereg/xsec_mature_universe_v2.json"))["symbols"]
D="research_lab/data/movers_5m"
series={}
for s in UNI:
    p=os.path.join(D,s+".json")
    if not os.path.exists(p): continue
    r=json.load(open(p))
    if len(r)<20000: continue
    series[s]={b[0]//300000:b[4] for b in r}
syms=sorted(series); allk=sorted(set().union(*[set(series[s]) for s in syms]))
BPS=0.0002+0.00055
def run(Hh,K):
    step=Hh*12; g=[]; i=step
    while i+step<len(allk):
        k0=allk[i-step];k1=allk[i];k2=allk[i+step]; sc=[]
        for s in syms:
            p0=series[s].get(k0);p1=series[s].get(k1);p2=series[s].get(k2)
            if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
        if len(sc)<2*K+4: i+=step; continue
        sc.sort(); f=lambda s:(series[s][k2]/series[s][k1]-1.0)
        lo=[s for _,s in sc[:K]]; hi=[s for _,s in sc[-K:]]
        g.append(sum(f(s) for s in lo)/K - sum(f(s) for s in hi)/K)   # ВАЛОВОЙ разворот
        i+=step
    return g
print("H,ч K  |   n  | вал.разворот | вал.МОМЕНТУМ | издержки за круг | момент. ЧИСТЫЙ")
for H in (2,4,8,12,24):
    for K in (5,10):
        g=run(H,K)
        if len(g)<50: continue
        n=len(g)
        mr=sum(g)/n*10000          # средний валовой разворот, bps за ребаланс
        mm=-mr                      # моментум = зеркало
        cost=4*BPS*10000            # 30 bps
        print(f"{H:>3} {K:>3} | {n:>4} | {mr:>11.2f} | {mm:>12.2f} | {cost:>16.1f} | {mm-cost:>14.2f}")
print("\nвсе величины в bps на один ребаланс")
