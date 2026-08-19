"""Кросс-секционный моментум v2: 20 монет, включение по ДОСТУПНОСТИ данных (монета участвует только
когда у неё есть история) — реалистичнее и частично снижает survivorship. Фолды с эмбарго."""
import json, os
ROOT="/sessions/admiring-beautiful-heisenberg/mnt/bybit-bot-clean-v28"
D=json.load(open(os.path.join(ROOT,"research_lab/data/daily_closes.json")))
syms=sorted(D)
px={s:{int(k):v for k,v in D[s].items()} for s in syms}
alldays=sorted(set().union(*[set(px[s]) for s in syms]))
COST=0.0008
def run(L,R,K,mode="ls",funding_bps=0.0,universe=None):
    U=universe or syms
    rets=[]; dts=[]; picks=[]
    i=L
    while i+R < len(alldays):
        t=alldays[i]; t0=alldays[i-L]; t2=alldays[i+R]
        scored=[]
        for s in U:
            p0=px[s].get(t0); p1=px[s].get(t); p2=px[s].get(t2)
            if p0 and p1 and p2 and p0>0 and p1>0: scored.append((p1/p0-1.0,s))
        if len(scored) < 2*K+2: i+=R; continue
        scored.sort(reverse=True)
        L_=[s for _,s in scored[:K]]; S_=[s for _,s in scored[-K:]]
        f=lambda s: (px[s][t2]/px[s][t]-1.0)
        lr=sum(f(s) for s in L_)/K; sr=sum(f(s) for s in S_)/K
        gross=lr-sr if mode=="ls" else lr
        legs=2 if mode=="ls" else 1
        rets.append(gross - legs*2*COST - funding_bps/10000.0*R*(1 if mode=="ls" else 0))
        dts.append(t); picks.append((L_,S_))
        i+=R
    return rets,dts,picks
def st(rets):
    n=len(rets)
    if n<10: return None
    tot=1.0; eq=1.0; peak=1.0; dd=0
    for r in rets:
        tot*=(1+r); eq*=(1+r); peak=max(peak,eq); dd=max(dd,(peak-eq)/peak)
    m=sum(rets)/n; v=sum((r-m)**2 for r in rets)/max(1,n-1); sd=v**0.5
    return dict(n=n,total=round((tot-1)*100,1),win=round(100*sum(1 for r in rets if r>0)/n,1),
                dd=round(dd*100,1),sharpe=round((m/sd)*(n**0.5),2) if sd>0 else 0)
def folds_embargo(rets,k=4,emb=1):
    q=len(rets)//k; out=[]
    for f in range(k):
        a=f*q+ (emb if f>0 else 0); b=(f+1)*q if f<k-1 else len(rets)
        seg=rets[a:b]; t=1.0
        for r in seg: t*=(1+r)
        out.append(round((t-1)*100,1))
    return out
print(f"монет={len(syms)} дней={len(alldays)}")
print(f"{'L':>3} {'R':>3} {'K':>2} | {'n':>4} {'total%':>8} {'win%':>6} {'DD%':>6} {'Sh':>5} | фолды(emb) pos")
good=[]
for L in [14,30,60]:
    for R in [7,14,30]:
        for K in [3,4,5]:
            r,_,_=run(L,R,K,"ls")
            s=st(r)
            if not s: continue
            fo=folds_embargo(r); pos=sum(1 for x in fo if x>0)
            line=f"{L:>3} {R:>3} {K:>2} | {s['n']:>4} {s['total']:>8} {s['win']:>6} {s['dd']:>6} {s['sharpe']:>5} | {fo} {pos}/4"
            print(line)
            if s['total']>0 and pos>=3: good.append((s,L,R,K,line))
print(f"\n=== ПЛАТО (total>0, >=3/4 фолда): {len(good)} из 27 ===")
for g in good: print("  ",g[4])
