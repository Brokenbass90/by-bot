"""Прогон валидатора на кандидате XSEC_MATURE V2 — контрольный пример."""
import sys, json, datetime, collections
sys.path.insert(0,".")
from research_lab.validator import validate
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
alld=sorted({d for s in px for d in px[s]}); N=len(alld)
mature=[s for s in px if len(px[s])>=390]
LOOK=[7,14,21,30,45]; R=3; K=5; MAKER=0.0002; TAKER=0.00055; TV=0.15
contrib=collections.defaultdict(float)
def build(start,c=None):
    bars=list(range(start,N-R-1,R)); ser={}
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
def vt(seq,win=20):
    r=[x for _,x in seq]; o=[]
    for i,x in enumerate(r):
        h=r[max(0,i-win):i]
        if len(h)<8: o.append(x*0.5); continue
        m=sum(h)/len(h); sd=(sum((y-m)**2 for y in h)/(len(h)-1))**0.5
        ann=sd*(365/R)**0.5
        o.append(x*(min(1.0,TV/ann) if ann>0 else 1.0))
    return [(seq[i][0],o[i]) for i in range(len(o))]
ph=[vt(build(46+k, contrib if k==0 else None)) for k in (0,1,2)]
m=min(len(p) for p in ph)
main=[sum(p[i][1] for p in ph)/3 for i in range(m)]
allp=sorted([x for p in ph for x in p])
mon=collections.defaultdict(list)
for day,x in allp:
    d=datetime.datetime.utcfromtimestamp(day*86400)
    mon[f"{d.year}-{d.month:02d}"].append(x/3.0)
bm={}
for k,v in mon.items():
    e=1.0
    for x in v: e*=(1+x)
    bm[k]=(e-1)*100
rep=validate(returns=main,
  meta={"windows_overlap":False,"posthoc_thresholds":"порог зрелости 390 дней",
        "universe_includes_delisted":False,"taker_bps":5.5},
  phases=[[x for _,x in p] for p in ph], by_symbol=dict(contrib), by_month=bm)
print(rep.text())
