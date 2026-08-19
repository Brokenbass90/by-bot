import json, sys
sys.path.insert(0,".")
from research_lab.validator import validate
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
alld=sorted({d for s in px for d in px[s]}); N=len(alld)
mature=[s for s in px if len(px[s])>=390]
LOOK=[7,14,21,30,45]; R=3; K=5; MAKER=0.0002; TAKER=0.00055; TV=0.15
def vol(s,i,W):
    rs=[]
    for j in range(max(1,i-W),i):
        a=px[s].get(alld[j-1]); b=px[s].get(alld[j])
        if a and b and a>0: rs.append(b/a-1.0)
    if len(rs)<max(4,W//2): return None
    m=sum(rs)/len(rs)
    return (sum((x-m)**2 for x in rs)/(len(rs)-1))**0.5
def build(start, use_vol):
    bars=list(range(start,N-R-1,R)); ser={}
    for L in LOOK:
        row=[]
        for i in bars:
            if i-L<0: row.append(None); continue
            t=alld[i];t0=alld[i-L];t2=alld[i+R]; cand=[]
            for s in mature:
                p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
                if not(p0 and p1 and p2 and p0>0 and p1>0): continue
                v=vol(s,i,L) if use_vol else 0.0
                if use_vol and v is None: continue
                cand.append((p1/p0-1.0, v, s))
            if len(cand)<2*K+4: row.append(None); continue
            mo=sorted(range(len(cand)), key=lambda k:cand[k][0])
            rank_m={cand[k][2]:r for r,k in enumerate(mo)}
            if use_vol:
                vo=sorted(range(len(cand)), key=lambda k:cand[k][1])
                rank_v={cand[k][2]:r for r,k in enumerate(vo)}
                sc=sorted(((rank_m[c[2]]+rank_v[c[2]], c[2]) for c in cand), reverse=True)
            else:
                sc=sorted(((rank_m[c[2]], c[2]) for c in cand), reverse=True)
            f=lambda s:(px[s][t2]/px[s][t]-1.0)
            Lg=[s for _,s in sc[:K]]; Sh=[s for _,s in sc[-K:]]
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
                sh=round(mu/sd*len(r)**0.5,2) if sd>0 else 0,h1=tot(r[:h]),h2=tot(r[h:]))
for name,uv in [("БАЗА: только моментум",False),("+ФАКТОР ВОЛАТИЛЬНОСТИ",True)]:
    ph=[vt(build(46+k,uv)) for k in (0,1,2)]
    m=min(len(p) for p in ph)
    main=[sum(p[i] for p in ph)/3 for i in range(m)]
    a=M(main); pm=[M(p) for p in ph]
    print(f"{name}")
    print(f"   итог {a['tot']}%  DD {a['dd']}%  Sharpe {a['sh']}  (1-я {a['h1']}%, 2-я {a['h2']}%)")
    print(f"   фазы: " + " / ".join(f"{p['tot']}%" for p in pm))
