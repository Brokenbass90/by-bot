"""Жив ли моментум В СВЕЖЕМ ПЕРИОДЕ? Скан семейства на последней трети данных."""
import json,os
ROOT="/sessions/admiring-beautiful-heisenberg/mnt/bybit-bot-clean-v28"
D=json.load(open(os.path.join(ROOT,"research_lab/data/daily_closes.json")))
syms=sorted(D); px={s:{int(k):v for k,v in D[s].items()} for s in syms}
alldays=sorted(set().union(*[set(px[s]) for s in syms]))
N=len(alldays); COST=0.0008
def run(L,R,K,i0,i1,mode="ls"):
    rets=[]; i=max(i0,max(L,25)); end=min(i1,N-R-1)
    while i<end:
        t=alldays[i]; t0=alldays[i-L]; t2=alldays[i+R]; sc=[]
        for s in syms:
            p0=px[s].get(t0); p1=px[s].get(t); p2=px[s].get(t2)
            if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
        if len(sc)<2*K+2: i+=R; continue
        sc.sort(reverse=True); Lg=[s for _,s in sc[:K]]; Sh=[s for _,s in sc[-K:]]
        f=lambda s:(px[s][t2]/px[s][t]-1.0)
        lr=sum(f(s) for s in Lg)/K; sr=sum(f(s) for s in Sh)/K
        if mode=="ls": rets.append(lr-sr-4*COST)
        elif mode=="long": rets.append(lr-2*COST)
        else: rets.append(-sr-2*COST)
        i+=R
    return rets
def tot(r):
    if len(r)<6: return None
    e=1.0
    for x in r: e*=(1+x)
    return round((e-1)*100,1)
cut=int(N*0.66)
print(f"СВЕЖИЙ ПЕРИОД: последние {N-cut} дней из {N}\n")
print("L    R    K    long-short   only-long   only-short")
pos=0; tot_n=0
for L in (7,14,21,30,45):
    for R in (3,7,14):
        for K in (3,5):
            a=tot(run(L,R,K,cut,N)); b=tot(run(L,R,K,cut,N,"long")); c=tot(run(L,R,K,cut,N,"short"))
            if a is None: continue
            tot_n+=1; pos+= 1 if a>0 else 0
            print(f"{L:<5}{R:<5}{K:<5}{a:>10}%{b:>11}%{c:>12}%")
print(f"\nПоложительных long-short в свежем периоде: {pos}/{tot_n}")
