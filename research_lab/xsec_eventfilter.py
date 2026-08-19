import json, sys, statistics
sys.path.insert(0,".")
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
alld=sorted({d for s in px for d in px[s]}); N=len(alld)
mature=[s for s in px if len(px[s])>=390]
LOOK=[7,14,21,30,45]; R=3; K=5; MAKER=0.0002; TAKER=0.00055; TV=0.15
def rets(s,i,W):
    o=[]
    for j in range(max(1,i-W),i):
        a=px[s].get(alld[j-1]); b=px[s].get(alld[j])
        if a and b and a>0: o.append(b/a-1.0)
    return o
def sd(x):
    if len(x)<2: return None
    m=sum(x)/len(x); return (sum((y-m)**2 for y in x)/(len(x)-1))**0.5
def market_stress(i):
    cur=[]
    for s in mature:
        a=px[s].get(alld[i-1]); b=px[s].get(alld[i])
        if a and b and a>0: cur.append(abs(b/a-1.0))
    if len(cur)<10: return False
    med=statistics.median(cur)
    hist=[]
    for j in range(max(1,i-60),i):
        v=[]
        for s in mature:
            a=px[s].get(alld[j-1]); b=px[s].get(alld[j])
            if a and b and a>0: v.append(abs(b/a-1.0))
        if len(v)>=10: hist.append(statistics.median(v))
    if len(hist)<30: return False
    hist.sort()
    return med > hist[int(len(hist)*0.90)]
def build(syms,start,f1,f2):
    bars=list(range(start,N-R-1,R)); ser={}
    for L in LOOK:
        row=[]
        for i in bars:
            if i-L<0: row.append(None); continue
            if f2 and market_stress(i): row.append(0.0); continue
            t=alld[i];t0=alld[i-L];t2=alld[i+R]; cand=[]
            for s in syms:
                p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
                if not(p0 and p1 and p2 and p0>0 and p1>0): continue
                rr=rets(s,i,L); v=sd(rr)
                if v is None or v<=0: continue
                if f1:
                    a=px[s].get(alld[i-1])
                    if a and a>0 and abs(p1/a-1.0) > 3*v: continue
                cand.append((p1/p0-1.0,v,s))
            if len(cand)<2*K+4: row.append(None); continue
            mo=sorted(range(len(cand)),key=lambda k:cand[k][0]); rm={cand[k][2]:r for r,k in enumerate(mo)}
            vo=sorted(range(len(cand)),key=lambda k:cand[k][1]); rv={cand[k][2]:r for r,k in enumerate(vo)}
            sc=sorted(((rm[x[2]]+rv[x[2]],x[2]) for x in cand),reverse=True)
            f=lambda s:(px[s][t2]/px[s][t]-1.0)
            row.append(sum(f(s) for s in [s for _,s in sc[:K]])/K
                      -sum(f(s) for s in [s for _,s in sc[-K:]])/K-2*MAKER-2*TAKER)
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
        m=sum(h)/len(h); s_=(sum((y-m)**2 for y in h)/(len(h)-1))**0.5
        ann=s_*(365/R)**0.5
        o.append(x*(min(1.0,TV/ann) if ann>0 else 1.0))
    return o
def M(r):
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x);pk=max(pk,e);dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r);v=sum((y-mu)**2 for y in r)/max(1,len(r)-1);s_=v**0.5
    h=len(r)//2
    def tot(z):
        q=1.0
        for x in z: q*=(1+x)
        return round((q-1)*100,1)
    return dict(tot=round((e-1)*100,1),dd=round(dd*100,1),
                sh=round(mu/s_*len(r)**0.5,2) if s_>0 else 0,h1=tot(r[:h]),h2=tot(r[h:]))
print("вариант                    | итог  | DD   | Sharpe | 1-я  | 2-я  | фазы")
for name,f1,f2 in [("БАЗА V3",False,False),("F1 шум после события",True,False),
                   ("F2 рыночный стресс",False,True),("F3 оба",True,True)]:
    ph=[vt(build(mature,46+k,f1,f2)) for k in (0,1,2)]
    m=min(len(p) for p in ph)
    main=[sum(p[i] for p in ph)/3 for i in range(m)]
    a=M(main); pm=[M(p)['tot'] for p in ph]
    mark=" <<<" if a['sh']>2.19 else ""
    print(f"{name:<26} | {a['tot']:>5}% | {a['dd']:>4}% | {a['sh']:>6} | {a['h1']:>4}% | {a['h2']:>4}% | {'/'.join(f'{x:.0f}' for x in pm)}{mark}")
