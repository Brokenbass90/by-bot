"""Предсказывает ли прошлый фандинг будущий? Pre-reg: CARRY_SELECTION_2026_07_22.json"""
import csv, os, statistics
d='data/funding_rates/crypto_static_v1_20260425'
F={}
for fn in sorted(os.listdir(d)):
    if not fn.endswith('.csv'): continue
    r=list(csv.DictReader(open(os.path.join(d,fn))))
    s=fn[:-4]
    F[s]=[(int(x['timestamp_ms'])//1000, float(x['funding_rate'])) for x in r if x['funding_rate']]
syms=sorted(F); n=min(len(F[s]) for s in syms)
print(f"символов: {len(syms)}, выплат каждые 8ч: {n} (~{n/3:.0f} дней)\n")
PER_DAY=3
def window_mean(s, i0, i1):
    v=[x for _,x in F[s][max(0,i0):i1]]
    return sum(v)/len(v) if v else None
def run(L,H,K,select=True):
    lb=L*PER_DAY; hd=H*PER_DAY
    got=[]; i=lb
    while i+hd<=n:
        if select:
            sc=[(window_mean(s,i-lb,i), s) for s in syms]
            sc=[(m,s) for m,s in sc if m is not None]
            if len(sc)<K+1: i+=hd; continue
            sc.sort(reverse=True)
            pick=[s for _,s in sc[:K]]
        else:
            pick=syms
        fwd=[]
        for s in pick:
            v=[x for _,x in F[s][i:i+hd]]
            if v: fwd.append(sum(v))
        if fwd: got.append(sum(fwd)/len(fwd))
        i+=hd
    return got
def summ(g,H):
    if not g: return None
    tot=sum(g)
    periods_per_year=365/H
    apr=(tot/len(g))*periods_per_year*100
    h=len(g)//2
    a1=sum(g[:h])/max(1,h)*periods_per_year*100
    a2=sum(g[h:])/max(1,len(g)-h)*periods_per_year*100
    return dict(n=len(g), apr=round(apr,2), h1=round(a1,2), h2=round(a2,2))
print("L,дн H,дн  K | ОТБОР годовых | 1-я    | 2-я    | КОРЗИНА годовых | превосходство")
best=None
for L in (30,60,90):
    for H in (30,60):
        base=summ(run(L,H,0,select=False),H)
        for K in (3,4):
            a=summ(run(L,H,K,select=True),H)
            if not a or not base: continue
            edge=a['apr']-base['apr']
            stable = (a['h1']>base['h1']) and (a['h2']>base['h2'])
            mark=" <<< устойчиво" if edge>0 and stable else (" (нестабильно)" if edge>0 else "")
            print(f"{L:>4} {H:>5} {K:>3} | {a['apr']:>13.2f}% | {a['h1']:>6.2f} | {a['h2']:>6.2f} | {base['apr']:>15.2f}% | {edge:>+7.2f}%{mark}")
