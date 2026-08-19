"""Кросс-секционный РАЗВОРОТ (short-term reversal): лонг проигравших / шорт выигравших.
Документированная аномалия, ПРОТИВОПОЛОЖНА моментуму по знаку -> кандидат в диверсификаторы."""
import json, os
ROOT="/sessions/admiring-beautiful-heisenberg/mnt/bybit-bot-clean-v28"
D=json.load(open(os.path.join(ROOT,"research_lab/data/daily_closes.json")))
syms=sorted(D); px={s:{int(k):v for k,v in D[s].items()} for s in syms}
alldays=sorted(set().union(*[set(px[s]) for s in syms]))
COST=0.0008
def run(L,R,K,rev=True,funding_bps=0.0,universe=None):
    U=universe or syms; rets=[]; i=max(L,1)
    while i+R < len(alldays):
        t=alldays[i]; t0=alldays[i-L]; t2=alldays[i+R]
        sc=[]
        for s in U:
            p0=px[s].get(t0); p1=px[s].get(t); p2=px[s].get(t2)
            if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
        if len(sc)<2*K+2: i+=R; continue
        sc.sort(reverse=True)
        if rev: L_=[s for _,s in sc[-K:]]; S_=[s for _,s in sc[:K]]   # лонг проигравших
        else:   L_=[s for _,s in sc[:K]];  S_=[s for _,s in sc[-K:]]
        f=lambda s:(px[s][t2]/px[s][t]-1.0)
        g=sum(f(s) for s in L_)/K - sum(f(s) for s in S_)/K
        rets.append(g - 2*2*COST - funding_bps/10000.0*R); i+=R
    return rets
def st(r):
    n=len(r)
    if n<10: return None
    tot=1.0; eq=1.0; pk=1.0; dd=0
    for x in r: tot*=(1+x); eq*=(1+x); pk=max(pk,eq); dd=max(dd,(pk-eq)/pk)
    m=sum(r)/n; v=sum((x-m)**2 for x in r)/max(1,n-1); sd=v**0.5
    return dict(n=n,total=round((tot-1)*100,1),win=round(100*sum(1 for x in r if x>0)/n,1),dd=round(dd*100,1),sh=round((m/sd)*(n**0.5),2) if sd>0 else 0)
def folds(r,k=4,emb=1):
    q=len(r)//k; o=[]
    for f in range(k):
        a=f*q+(emb if f>0 else 0); b=(f+1)*q if f<k-1 else len(r)
        t=1.0
        for x in r[a:b]: t*=(1+x)
        o.append(round((t-1)*100,1))
    return o
print(f"монет={len(syms)} дней={len(alldays)}  [РАЗВОРОТ: лонг проигравших / шорт выигравших]")
print(f"{'L':>2} {'R':>3} {'K':>2} | {'n':>4} {'total%':>8} {'win%':>6} {'DD%':>6} {'Sh':>5} | фолды pos")
good=[]
for L in [1,2,3,5,7]:
    for R in [1,2,3,7]:
        for K in [3,5]:
            r=run(L,R,K,rev=True); s=st(r)
            if not s: continue
            fo=folds(r); pos=sum(1 for x in fo if x>0)
            line=f"{L:>2} {R:>3} {K:>2} | {s['n']:>4} {s['total']:>8} {s['win']:>6} {s['dd']:>6} {s['sh']:>5} | {fo} {pos}/4"
            print(line)
            if s['total']>0 and pos>=3: good.append(line)
print(f"\n=== ПЛАТО РАЗВОРОТА (total>0, >=3/4): {len(good)} ===")
for g in good: print("  ",g)
if not good: print("  нет — разворот не работает, диверсификатор искать в другом месте")
