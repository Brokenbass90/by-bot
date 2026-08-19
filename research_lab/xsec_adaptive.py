"""ИДЕЯ ВЛАДЕЛЬЦА: система сама даёт вес тому контуру, что сейчас работает.
Без заглядывания вперёд: выбор делается ТОЛЬКО по прошлым результатам."""
import json,os
ROOT="/sessions/admiring-beautiful-heisenberg/mnt/bybit-bot-clean-v28"
D=json.load(open(os.path.join(ROOT,"research_lab/data/daily_closes.json")))
syms=sorted(D); px={s:{int(k):v for k,v in D[s].items()} for s in syms}
alldays=sorted(set().union(*[set(px[s]) for s in syms])); N=len(alldays)
MAKER=0.0002; R=3; K=5
LOOKBACKS=[7,14,21,30,45]
def leg_ret(L,i):
    """доход конфига L за окно, начинающееся в баре i"""
    if i-L<0 or i+R>=N: return None
    t=alldays[i]; t0=alldays[i-L]; t2=alldays[i+R]; sc=[]
    for s in syms:
        p0=px[s].get(t0); p1=px[s].get(t); p2=px[s].get(t2)
        if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
    if len(sc)<2*K+2: return None
    sc.sort(reverse=True)
    f=lambda s:(px[s][t2]/px[s][t]-1.0)
    return sum(f(s) for s in sc[:K][0:K] and [s for _,s in sc[:K]])/K - sum(f(s) for s in [s for _,s in sc[-K:]])/K - 4*MAKER
# сетка баров
bars=list(range(max(LOOKBACKS)+1, N-R-1, R))
hist={L:[] for L in LOOKBACKS}; series={}
for L in LOOKBACKS:
    series[L]=[leg_ret(L,i) for i in bars]
def stats(r):
    r=[x for x in r if x is not None]
    if len(r)<6: return None
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x); pk=max(pk,e); dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r); v=sum((x-mu)**2 for x in r)/max(1,len(r)-1); sd=v**0.5
    return round((e-1)*100,1), round(dd*100,1), round((mu/sd)*(len(r)**0.5),2) if sd>0 else 0, len(r)
print("ФИКСИРОВАННЫЕ КОНФИГИ (весь период, R=3 K=5, мейкер):")
for L in LOOKBACKS:
    s=stats(series[L])
    if s: print(f"  L={L:<3} итог={s[0]:>8}%  DD={s[1]:>5}%  Sharpe={s[2]:>5}  n={s[3]}")
print()
for M in (4,8,12):
    ad=[]; picks={}
    for j in range(len(bars)):
        if j<M: continue
        # оценка ТОЛЬКО по прошлому
        best=None; bs=-9e9
        for L in LOOKBACKS:
            past=[series[L][k] for k in range(j-M,j) if series[L][k] is not None]
            if len(past)<M//2: continue
            sc=sum(past)
            if sc>bs: bs=sc; best=L
        if best is None: continue
        v=series[best][j]
        if v is None: continue
        ad.append(v); picks[best]=picks.get(best,0)+1
    s=stats(ad)
    if s:
        mix=" ".join(f"L{k}:{v}" for k,v in sorted(picks.items()))
        print(f"АДАПТИВНЫЙ (окно {M} ребал.): итог={s[0]:>8}%  DD={s[1]:>5}%  Sharpe={s[2]:>5}  n={s[3]}")
        print(f"    выбирал: {mix}")
# равновзвешенный портфель всех L
eq=[]
for j in range(len(bars)):
    vs=[series[L][j] for L in LOOKBACKS if series[L][j] is not None]
    if vs: eq.append(sum(vs)/len(vs))
s=stats(eq)
print(f"\nРАВНЫЙ ПОРТФЕЛЬ всех L:      итог={s[0]:>8}%  DD={s[1]:>5}%  Sharpe={s[2]:>5}  n={s[3]}")
