"""Кросс-секционный моментум на АКЦИЯХ (Alpaca). Комиссия ~0 - главный блокер крипты отсутствует."""
import csv, os
d="data/equities_daily"
px={}; 
for f in sorted(os.listdir(d)):
    s=f.split("_")[0]
    px[s]={int(r["ts"]):float(r["c"]) for r in csv.DictReader(open(os.path.join(d,f)))}
syms=sorted(px); days=sorted(set().union(*[set(px[s]) for s in syms])); N=len(days)
def stats(r):
    if len(r)<8: return None
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x);pk=max(pk,e);dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r);v=sum((x-mu)**2 for x in r)/max(1,len(r)-1);sd=v**0.5
    return round((e-1)*100,1),round(dd*100,1),round((mu/sd)*(len(r)**0.5),2) if sd>0 else 0,len(r)
def run(L,R,K,cost,mode="ls",i0=0,i1=None):
    out=[];i=max(i0,L);end=(N-R-1) if i1 is None else min(i1,N-R-1)
    while i<end:
        t=days[i];t0=days[i-L];t2=days[i+R];sc=[]
        for s in syms:
            p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
            if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
        if len(sc)<2*K+2: i+=R; continue
        sc.sort(reverse=True); f=lambda s:(px[s][t2]/px[s][t]-1.0)
        lr=sum(f(s) for s in [s for _,s in sc[:K]])/K
        sr=sum(f(s) for s in [s for _,s in sc[-K:]])/K
        mk=sum(f(s) for _,s in sc)/len(sc)
        if mode=="ls": out.append(lr-sr-4*cost)
        elif mode=="long": out.append(lr-2*cost)
        elif mode=="alpha": out.append(lr-mk)
        else: out.append(mk)
        i+=R
    return out
# бенчмарк
bh=stats(run(20,20,3,0.0,"mkt"))
print(f"БЕНЧМАРК buy&hold равновзвешенно: {bh[0]}%  DD={bh[1]}%  Sharpe={bh[2]}\n")
print("L   R   K | long-short | ТОЛЬКО ЛОНГ | альфа лонга | DD(LS) | Sharpe(LS)")
COST=0.0002   # 2 bps: Alpaca комиссия 0, закладываем проскальзывание/спред
pos=0;n=0
for L in (20,40,60,120):
    for R in (5,10,20):
        for K in (2,3,4):
            a=stats(run(L,R,K,COST,"ls")); b=stats(run(L,R,K,COST,"long")); c=stats(run(L,R,K,0.0,"alpha"))
            if not a: continue
            n+=1; pos+= a[0]>0
            fl=" <<<" if a[0]>40 and a[2]>1.0 else ""
            print(f"{L:<4}{R:<4}{K:<3}|{a[0]:>10}% |{b[0]:>11}% |{c[0]:>11}% |{a[1]:>6}% |{a[2]:>9}{fl}")
print(f"\nПоложительных long-short: {pos}/{n}")
