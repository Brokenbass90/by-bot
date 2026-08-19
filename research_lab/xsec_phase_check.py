"""КРИТИЧНО: зависит ли прошедший ворота результат от ФАЗЫ сетки ребалансов?"""
import json
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
alld=sorted({d for s in px for d in px[s]}); N=len(alld)
mature=[s for s in px if len(px[s])>=390]
LOOK=[7,14,21,30,45]; R=3; K=5; MAKER=0.0002; TAKER=0.00055; TV=0.15
def build(start):
    bars=list(range(start, N-R-1, R)); ser={}
    for L in LOOK:
        row=[]
        for i in bars:
            if i-L<0: row.append(None); continue
            t=alld[i];t0=alld[i-L];t2=alld[i+R];sc=[]
            for s in mature:
                p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
                if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
            if len(sc)<2*K+4: row.append(None); continue
            sc.sort(reverse=True); f=lambda s:(px[s][t2]/px[s][t]-1.0)
            row.append(sum(f(s) for s in [s for _,s in sc[:K]])/K
                      -sum(f(s) for s in [s for _,s in sc[-K:]])/K -2*MAKER-2*TAKER)
        ser[L]=row
    eq=[]
    for j in range(len(bars)):
        v=[ser[L][j] for L in LOOK if ser[L][j] is not None]
        eq.append(sum(v)/len(v) if v else None)
    return [x for x in eq if x is not None]
def vt(r,win=20):
    o=[]
    for i,x in enumerate(r):
        h=r[max(0,i-win):i]
        if len(h)<8: o.append(x*0.5); continue
        m=sum(h)/len(h); sd=(sum((y-m)**2 for y in h)/(len(h)-1))**0.5
        ann=sd*(365/R)**0.5
        o.append(x*(min(1.0,TV/ann) if ann>0 else 1.0))
    return o
def M(r):
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x);pk=max(pk,e);dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r);v=sum((y-mu)**2 for y in r)/max(1,len(r)-1);sd=v**0.5
    h=len(r)//2
    def tot(z):
        q=1.0
        for x in z: q*=(1+x)
        return round((q-1)*100,1)
    return dict(tot=round((e-1)*100,1),dd=round(dd*100,1),
                sh=round(mu/sd*len(r)**0.5,2) if sd>0 else 0,h1=tot(r[:h]),h2=tot(r[h:]),n=len(r))
print("СТАРТОВЫЙ БАР ЕДИНСТВЕННОЕ ОТЛИЧИЕ. Конфиг тот же, прошедший ворота.\n")
print("старт | фаза | итог   | DD    | Sharpe | 1-я    | 2-я    | n")
rs=[]
for start in (46,47,48,49,50,51,58,59,60):
    r=vt(build(start)); a=M(r); rs.append((start,a))
    print(f"{start:>5} | {start%3:>4} | {a['tot']:>6}% | {a['dd']:>4}% | {a['sh']:>6} | {a['h1']:>5}% | {a['h2']:>5}% | {a['n']}")
sh=[a['sh'] for _,a in rs]; to=[a['tot'] for _,a in rs]
print(f"\nSharpe: от {min(sh)} до {max(sh)}   итог: от {min(to)}% до {max(to)}%")
print(f"средний Sharpe {sum(sh)/len(sh):.2f}, средний итог {sum(to)/len(to):.1f}%")
