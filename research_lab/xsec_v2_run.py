import json, collections
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
alld=sorted({d for s in px for d in px[s]}); N=len(alld)
LOOK=[7,14,21,30,45]; R=3; K=5; MAKER=0.0002; TAKER=0.00055; TV=0.15
def build(syms,start,contrib=None):
    bars=list(range(start,N-R-1,R)); ser={}
    for L in LOOK:
        row=[]
        for i in bars:
            if i-L<0: row.append(None); continue
            t=alld[i];t0=alld[i-L];t2=alld[i+R];sc=[]
            for s in syms:
                p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
                if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
            if len(sc)<2*K+4: row.append(None); continue
            sc.sort(reverse=True); f=lambda s:(px[s][t2]/px[s][t]-1.0)
            Lg=[s for _,s in sc[:K]]; Sh=[s for _,s in sc[-K:]]
            if contrib is not None:
                for s in Lg: contrib[s]+=f(s)/K
                for s in Sh: contrib[s]-=f(s)/K
            row.append(sum(f(s) for s in Lg)/K-sum(f(s) for s in Sh)/K-2*MAKER-2*TAKER)
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
def stag(syms,contrib=None):
    ps=[vt(build(syms,46+k,contrib)) for k in (0,1,2)]
    m=min(len(p) for p in ps)
    return [sum(p[i] for p in ps)/3 for i in range(m)], [p[:m] for p in ps]
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
mature=[s for s in px if len(px[s])>=390]
contrib=collections.defaultdict(float)
main,phases=stag(mature,contrib)
a=M(main)
print(f"V2 РАЗНЕСЁННЫЙ, {len(mature)} зрелых монет")
print(f"итог {a['tot']}%  DD {a['dd']}%  Sharpe {a['sh']}  n={a['n']}  (1-я {a['h1']}%, 2-я {a['h2']}%)\n")
res={}
res["G1 обе половины > 0"]=(a['h1']>0 and a['h2']>0, f"{a['h1']}% / {a['h2']}%")
res["G2 Sharpe >= 0.8"]=(a['sh']>=0.8, f"{a['sh']}")
res["G3 просадка <= 50%"]=(a['dd']<=50, f"{a['dd']}%")
A=sorted(mature)[0::2]; B=sorted(mature)[1::2]
ma=M(stag(A)[0]); mb=M(stag(B)[0])
res["G4 обе половины символов > 0"]=(ma['tot']>0 and mb['tot']>0, f"A {ma['tot']}% / B {mb['tot']}%")
best=max(contrib.items(),key=lambda kv:kv[1])[0]
ml=M(stag([s for s in mature if s!=best])[0])
res["G5 LOSO без лучшей > 0"]=(ml['tot']>0, f"убрали {best}: {ml['tot']}%")
pm=[M(p) for p in phases]
res["G6 КАЖДАЯ фаза > 0"]=(all(p['tot']>0 for p in pm), " / ".join(f"{p['tot']}%(Sh {p['sh']})" for p in pm))
ok=True
for k,(p,d) in res.items():
    ok=ok and p
    print(f"  [{'PASS' if p else 'FAIL'}]  {k:<32} {d}")
print("\nИТОГ:", "ПРОЙДЕНО" if ok else "ОТКЛОНЕНО")
