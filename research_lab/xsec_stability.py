"""Проверка кандидата L14/R7/K5: (1) устойчивость во времени, (2) взвешивание по волатильности."""
import json, os, math
ROOT="/sessions/admiring-beautiful-heisenberg/mnt/bybit-bot-clean-v28"
D=json.load(open(os.path.join(ROOT,"research_lab/data/daily_closes.json")))
syms=sorted(D); px={s:{int(k):v for k,v in D[s].items()} for s in syms}
alldays=sorted(set().union(*[set(px[s]) for s in syms]))
COST=0.0008
def vol(s,t_idx,win=20):
    rs=[]
    for j in range(t_idx-win, t_idx):
        a=px[s].get(alldays[j-1]); b=px[s].get(alldays[j])
        if a and b and a>0: rs.append(b/a-1.0)
    if len(rs)<5: return None
    m=sum(rs)/len(rs); v=sum((x-m)**2 for x in rs)/(len(rs)-1)
    return v**0.5
def run(L,R,K,weight="equal",i0=None,i1=None):
    rets=[]; dts=[]
    i=max(L,25) if i0 is None else max(i0,max(L,25))
    end=(len(alldays)-R-1) if i1 is None else min(i1,len(alldays)-R-1)
    while i<end:
        t=alldays[i]; t0=alldays[i-L]; t2=alldays[i+R]
        sc=[]
        for s in syms:
            p0=px[s].get(t0); p1=px[s].get(t); p2=px[s].get(t2)
            if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
        if len(sc)<2*K+2: i+=R; continue
        sc.sort(reverse=True)
        Lg=[s for _,s in sc[:K]]; Sh=[s for _,s in sc[-K:]]
        f=lambda s:(px[s][t2]/px[s][t]-1.0)
        if weight=="equal":
            lr=sum(f(s) for s in Lg)/K; sr=sum(f(s) for s in Sh)/K
        else:  # inverse-vol
            def wts(lst):
                ws=[]
                for s in lst:
                    v=vol(s,i)
                    ws.append(1.0/v if v and v>0 else 0.0)
                tot=sum(ws) or 1.0
                return [w/tot for w in ws]
            wl=wts(Lg); ws_=wts(Sh)
            lr=sum(w*f(s) for w,s in zip(wl,Lg)); sr=sum(w*f(s) for w,s in zip(ws_,Sh))
        rets.append(lr-sr-2*2*COST); dts.append(t); i+=R
    return rets,dts
def st(r):
    n=len(r)
    if n<8: return "n<8"
    tot=1.0; eq=1.0; pk=1.0; dd=0
    for x in r: tot*=(1+x); eq*=(1+x); pk=max(pk,eq); dd=max(dd,(pk-eq)/pk)
    m=sum(r)/n; v=sum((x-m)**2 for x in r)/max(1,n-1); sd=v**0.5
    return f"n={n} total={round((tot-1)*100,1)}% win={round(100*sum(1 for x in r if x>0)/n,1)}% DD={round(dd*100,1)}% Sh={round((m/sd)*(n**0.5),2) if sd>0 else 0}"
L,R,K=14,7,5
print("=== 1) УСТОЙЧИВОСТЬ ВО ВРЕМЕНИ (равные веса) ===")
r,dts=run(L,R,K)
print(" весь период:      ", st(r))
h=len(r)//2
print(" первая половина:  ", st(r[:h]))
print(" ВТОРАЯ половина:  ", st(r[h:]), "  <-- ключевое: жив ли эдж недавно")
q=len(r)//4
for i in range(4):
    seg=r[i*q:(i+1)*q] if i<3 else r[3*q:]
    print(f"   четверть {i+1}: {st(seg)}")
print("\n=== 2) ВЗВЕШИВАНИЕ ПО ВОЛАТИЛЬНОСТИ (inverse-vol) ===")
rv,_=run(L,R,K,weight="invvol")
print(" равные веса:      ", st(r))
print(" inverse-vol:      ", st(rv))
hv=len(rv)//2
print(" inv-vol 2-я пол.: ", st(rv[hv:]))
