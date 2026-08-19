"""КАНДИДАТ №1 на ТРЕТЬЕМ универсуме: 241 монета вместо 20, другой период.
Параметры НЕ меняются: 5 lookback'ов, R=3, равный портфель."""
import json
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
syms=sorted(px)
days=sorted({d for s in syms for d in px[s]}); N=len(days)
LOOK=[7,14,21,30,45]; R=3
MAKER=0.0002; TAKER=0.00055
def leg(L,i,K,ci,co):
    if i-L<0 or i+R>=N: return None
    t=days[i];t0=days[i-L];t2=days[i+R];sc=[]
    for s in syms:
        p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
        if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
    if len(sc)<2*K+4: return None
    sc.sort(reverse=True); f=lambda s:(px[s][t2]/px[s][t]-1.0)
    g=sum(f(s) for s in [s for _,s in sc[:K]])/K - sum(f(s) for s in [s for _,s in sc[-K:]])/K
    return g-2*ci-2*co, len(sc)
def stats(r):
    r=[x for x in r if x is not None]
    if len(r)<6: return None
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x);pk=max(pk,e);dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r);v=sum((x-mu)**2 for x in r)/max(1,len(r)-1);sd=v**0.5
    return round((e-1)*100,1),round(dd*100,1),round((mu/sd)*(len(r)**0.5),2) if sd>0 else 0,len(r)
bars=list(range(max(LOOK)+1,N-R-1,R))
for K in (5,12,25):
    print(f"\n===== K={K} (лонг топ-{K} / шорт дно-{K}) =====")
    print("исполнение                    | итог    | 1-я пол | 2-я пол | DD    | Sharpe | монет в отборе")
    for name,ci,co in [("чистый мейкер",MAKER,MAKER),("вход мейкер/выход тейкер",MAKER,TAKER),("чистый тейкер",TAKER,TAKER)]:
        ser={}; cnt=[]
        for L in LOOK:
            row=[]
            for i in bars:
                r=leg(L,i,K,ci,co)
                if r is None: row.append(None)
                else: row.append(r[0]); cnt.append(r[1])
            ser[L]=row
        eq=[]
        for j in range(len(bars)):
            vs=[ser[L][j] for L in LOOK if ser[L][j] is not None]
            eq.append(sum(vs)/len(vs) if vs else None)
        e=[x for x in eq if x is not None]; h=len(e)//2
        a=stats(e); b=stats(e[:h]); c=stats(e[h:])
        if not a: continue
        avg=sum(cnt)//max(1,len(cnt))
        print(f"{name:<29} | {a[0]:>6}% | {b[0]:>6}% | {c[0]:>6}% | {a[1]:>4}% | {a[2]:>6} | {avg}")
