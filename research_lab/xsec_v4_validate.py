import json, sys, statistics, datetime, collections
sys.path.insert(0,".")
from research_lab.validator import validate
exec(open("research_lab/xsec_eventfilter.py").read().split('print("вариант')[0])
def build2(syms,start,c=None):
    bars=list(range(start,N-R-1,R)); ser={}
    for L in LOOK:
        row=[]
        for i in bars:
            if i-L<0: row.append(None); continue
            if market_stress(i): row.append(0.0); continue
            t=alld[i];t0=alld[i-L];t2=alld[i+R]; cand=[]
            for s in syms:
                p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
                if not(p0 and p1 and p2 and p0>0 and p1>0): continue
                rr=rets(s,i,L); v=sd(rr)
                if v is None or v<=0: continue
                a=px[s].get(alld[i-1])
                if a and a>0 and abs(p1/a-1.0)>3*v: continue
                cand.append((p1/p0-1.0,v,s))
            if len(cand)<2*K+4: row.append(None); continue
            mo=sorted(range(len(cand)),key=lambda k:cand[k][0]); rm={cand[k][2]:r for r,k in enumerate(mo)}
            vo=sorted(range(len(cand)),key=lambda k:cand[k][1]); rv={cand[k][2]:r for r,k in enumerate(vo)}
            sc=sorted(((rm[x[2]]+rv[x[2]],x[2]) for x in cand),reverse=True)
            f=lambda s:(px[s][t2]/px[s][t]-1.0)
            Lg=[s for _,s in sc[:K]]; Sh=[s for _,s in sc[-K:]]
            if c is not None:
                for s in Lg: c[s]+=f(s)/K
                for s in Sh: c[s]-=f(s)/K
            row.append(sum(f(s) for s in Lg)/K-sum(f(s) for s in Sh)/K-2*MAKER-2*TAKER)
        ser[L]=row
    out=[]
    for j,i in enumerate(bars):
        v=[ser[L][j] for L in LOOK if ser[L][j] is not None]
        if v: out.append((alld[i],sum(v)/len(v)))
    return out
def vt2(seq,win=20):
    r=[x for _,x in seq]; o=[]
    for i,x in enumerate(r):
        h=r[max(0,i-win):i]
        if len(h)<8: o.append(x*0.5); continue
        m=sum(h)/len(h); s_=(sum((y-m)**2 for y in h)/(len(h)-1))**0.5
        ann=s_*(365/R)**0.5
        o.append(x*(min(1.0,TV/ann) if ann>0 else 1.0))
    return [(seq[i][0],o[i]) for i in range(len(o))]
def stag(syms,c=None):
    ph=[vt2(build2(syms,46+k,c if k==0 else None)) for k in (0,1,2)]
    m=min(len(p) for p in ph)
    return [sum(p[i][1] for p in ph)/3 for i in range(m)], ph
def tot(r):
    e=1.0
    for x in r: e*=(1+x)
    return round((e-1)*100,1)
c=collections.defaultdict(float)
main,ph=stag(mature,c)
A=sorted(mature)[0::2]; B=sorted(mature)[1::2]
ta=tot(stag(A)[0]); tb=tot(stag(B)[0])
best=max(c.items(),key=lambda kv:kv[1])[0]
tl=tot(stag([s for s in mature if s!=best])[0])
allp=sorted([x for p in ph for x in p])
mon=collections.defaultdict(list)
for day,x in allp:
    d=datetime.datetime.utcfromtimestamp(day*86400)
    mon[f"{d.year}-{d.month:02d}"].append(x/3.0)
bm={k:tot(v) for k,v in mon.items()}
print(f"ХОЛДАУТ СИМВОЛОВ: A {ta}%   B {tb}%")
print(f"LOSO без {best}: {tl}%")
print("помесячно:", " ".join(f"{k[-2:]}:{v:+.1f}" for k,v in sorted(bm.items())))
print()
print(validate(returns=main,
  meta={"windows_overlap":False,"posthoc_thresholds":"порог зрелости 390 дней (унаследован)",
        "universe_includes_delisted":False,"taker_bps":5.5},
  phases=[[x for _,x in p] for p in ph], by_symbol=dict(c), by_month=bm,
  min_sharpe=2.19).text())
