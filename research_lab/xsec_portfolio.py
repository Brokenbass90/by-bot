import json,os
ROOT="/sessions/admiring-beautiful-heisenberg/mnt/bybit-bot-clean-v28"
D=json.load(open(os.path.join(ROOT,"research_lab/data/daily_closes.json")))
syms=sorted(D); px={s:{int(k):v for k,v in D[s].items()} for s in syms}
alldays=sorted(set().union(*[set(px[s]) for s in syms])); N=len(alldays)
R=3;K=5;LOOK=[7,14,21,30,45]
def leg(L,i,cost):
    if i-L<0 or i+R>=N: return None
    t=alldays[i];t0=alldays[i-L];t2=alldays[i+R];sc=[]
    for s in syms:
        p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
        if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
    if len(sc)<2*K+2: return None
    sc.sort(reverse=True); f=lambda s:(px[s][t2]/px[s][t]-1.0)
    return sum(f(s) for s in [s for _,s in sc[:K]])/K - sum(f(s) for s in [s for _,s in sc[-K:]])/K - 4*cost
def stats(r):
    r=[x for x in r if x is not None]
    if len(r)<6: return None
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x);pk=max(pk,e);dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r);v=sum((x-mu)**2 for x in r)/max(1,len(r)-1);sd=v**0.5
    return round((e-1)*100,1),round(dd*100,1),round((mu/sd)*(len(r)**0.5),2) if sd>0 else 0,len(r)
bars=list(range(max(LOOK)+1,N-R-1,R))
for cname,cost in [("МЕЙКЕР 2bps",0.0002),("тейкер 8bps",0.0008)]:
    ser={L:[leg(L,i,cost) for i in bars] for L in LOOK}
    eq=[]
    for j in range(len(bars)):
        vs=[ser[L][j] for L in LOOK if ser[L][j] is not None]
        eq.append(sum(vs)/len(vs) if vs else None)
    e=[x for x in eq if x is not None]; h=len(e)//2
    a=stats(e); b=stats(e[:h]); c=stats(e[h:])
    print(f"=== ПОРТФЕЛЬ 5 КОНФИГОВ, {cname} ===")
    print(f"  весь период:     итог={a[0]:>7}%  DD={a[1]:>5}%  Sharpe={a[2]:>5}  n={a[3]}")
    print(f"  первая половина: итог={b[0]:>7}%  DD={b[1]:>5}%  Sharpe={b[2]:>5}")
    print(f"  ВТОРАЯ половина: итог={c[0]:>7}%  DD={c[1]:>5}%  Sharpe={c[2]:>5}")
    print()
