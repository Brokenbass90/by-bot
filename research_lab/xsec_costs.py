"""Съедают ли издержки живой эдж? Тейкер 8bps vs мейкер 2bps, свежий период."""
import json,os
ROOT="/sessions/admiring-beautiful-heisenberg/mnt/bybit-bot-clean-v28"
D=json.load(open(os.path.join(ROOT,"research_lab/data/daily_closes.json")))
syms=sorted(D); px={s:{int(k):v for k,v in D[s].items()} for s in syms}
alldays=sorted(set().union(*[set(px[s]) for s in syms])); N=len(alldays)
def run(L,R,K,i0,i1,cost):
    r=[]; i=max(i0,max(L,25)); end=min(i1,N-R-1)
    while i<end:
        t=alldays[i]; t0=alldays[i-L]; t2=alldays[i+R]; sc=[]
        for s in syms:
            p0=px[s].get(t0); p1=px[s].get(t); p2=px[s].get(t2)
            if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
        if len(sc)<2*K+2: i+=R; continue
        sc.sort(reverse=True); Lg=[s for _,s in sc[:K]]; Sh=[s for _,s in sc[-K:]]
        f=lambda s:(px[s][t2]/px[s][t]-1.0)
        r.append(sum(f(s) for s in Lg)/K - sum(f(s) for s in Sh)/K - 4*cost); i+=R
    return r
def m(r):
    if len(r)<6: return None,None,None
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x); pk=max(pk,e); dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r); v=sum((x-mu)**2 for x in r)/max(1,len(r)-1); sd=v**0.5
    return round((e-1)*100,1), round(dd*100,1), round((mu/sd)*(len(r)**0.5),2) if sd>0 else 0
cut=int(N*0.66)
TAKER=0.0008; MAKER=0.0002
print("СВЕЖИЙ ПЕРИОД (373 дня, рынок -43%)\n")
print("L    R    K  | тейкер 8bps | МЕЙКЕР 2bps | DD    | Sharpe")
pt=pm=n=0
for L in (7,14,21,30,45):
    for R in (3,7,14):
        for K in (3,5):
            a,_,_ = m(run(L,R,K,cut,N,TAKER))
            b,dd,sh= m(run(L,R,K,cut,N,MAKER))
            if a is None: continue
            n+=1; pt+= a>0; pm+= b>0
            flag=" <<<" if b>30 else ""
            print(f"{L:<5}{R:<5}{K:<4}|{a:>10}%  |{b:>10}%  |{dd:>5}% |{sh:>6}{flag}")
print(f"\nПоложительных: тейкер {pt}/{n}  ->  МЕЙКЕР {pm}/{n}")
