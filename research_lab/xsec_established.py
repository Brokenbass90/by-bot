"""Сегмент или период? Ограничиваем универсум УСТОЯВШИМИСЯ монетами (длинная история)."""
import json
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
alld=sorted({d for s in px for d in px[s]}); N=len(alld)
LOOK=[7,14,21,30,45]; R=3; MAKER=0.0002; TAKER=0.00055
def stats(r):
    r=[x for x in r if x is not None]
    if len(r)<6: return None
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x);pk=max(pk,e);dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r);v=sum((x-mu)**2 for x in r)/max(1,len(r)-1);sd=v**0.5
    return round((e-1)*100,1),round(dd*100,1),round((mu/sd)*(len(r)**0.5),2) if sd>0 else 0,len(r)
def run(syms,K,ci,co):
    bars=list(range(max(LOOK)+1,N-R-1,R)); ser={}
    for L in LOOK:
        row=[]
        for i in bars:
            if i-L<0 or i+R>=N: row.append(None); continue
            t=alld[i];t0=alld[i-L];t2=alld[i+R];sc=[]
            for s in syms:
                p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
                if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
            if len(sc)<2*K+4: row.append(None); continue
            sc.sort(reverse=True); f=lambda s:(px[s][t2]/px[s][t]-1.0)
            row.append(sum(f(s) for s in [s for _,s in sc[:K]])/K
                      -sum(f(s) for s in [s for _,s in sc[-K:]])/K -2*ci-2*co)
        ser[L]=row
    eq=[]
    for j in range(len(bars)):
        v=[ser[L][j] for L in LOOK if ser[L][j] is not None]
        eq.append(sum(v)/len(v) if v else None)
    return [x for x in eq if x is not None]
for minhist,label in [(390,"УСТОЯВШИЕСЯ (история >=390 дней)"),(300,"история >=300 дней"),(150,"история >=150 дней")]:
    syms=[s for s in px if len(px[s])>=minhist]
    if len(syms)<25: print(f"{label}: монет {len(syms)} - мало"); continue
    print(f"\n===== {label}: {len(syms)} монет =====")
    print("K   | исполнение              | итог    | 1-я пол | 2-я пол | DD    | Sharpe")
    for K in (5,10):
        for nm,ci,co in [("мейкер",MAKER,MAKER),("мейкер/тейкер",MAKER,TAKER)]:
            e=run(syms,K,ci,co)
            a=stats(e); 
            if not a: continue
            h=len(e)//2; b=stats(e[:h]); c=stats(e[h:])
            print(f"{K:<3} | {nm:<23} | {a[0]:>6}% | {b[0]:>6}% | {c[0]:>6}% | {a[1]:>4}% | {a[2]:>6}")
