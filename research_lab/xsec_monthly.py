"""ПОМЕСЯЧНАЯ разбивка V2: не держится ли всё на одном удачном месяце?"""
import json, datetime, collections
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
alld=sorted({d for s in px for d in px[s]}); N=len(alld)
mature=[s for s in px if len(px[s])>=390]
LOOK=[7,14,21,30,45]; R=3; K=5; MAKER=0.0002; TAKER=0.00055; TV=0.15
def build(start):
    bars=list(range(start,N-R-1,R)); ser={}; keep=[]
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
                      -sum(f(s) for s in [s for _,s in sc[-K:]])/K-2*MAKER-2*TAKER)
        ser[L]=row
    out=[]
    for j,i in enumerate(bars):
        v=[ser[L][j] for L in LOOK if ser[L][j] is not None]
        if v: out.append((alld[i], sum(v)/len(v)))
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
allp=[]
for k in (0,1,2): allp += vt(build(46+k))
allp.sort()
mon=collections.defaultdict(list)
for day,x in allp:
    d=datetime.datetime.utcfromtimestamp(day*86400)
    mon[f"{d.year}-{d.month:02d}"].append(x/3.0)   # каждая фаза = треть капитала
print("месяц    | доходность | сделок-ребалансов")
tot=1.0; vals=[]
for m in sorted(mon):
    r=mon[m]; e=1.0
    for x in r: e*=(1+x)
    p=(e-1)*100; vals.append(p); tot*=e
    bar="#"*int(abs(p)*3)
    print(f"{m}  | {p:>8.2f}%  | {len(r):>3}  {'+' if p>0 else '-'}{bar}")
pos=sum(1 for v in vals if v>0)
print(f"\nвсего: {(tot-1)*100:.1f}%   месяцев в плюсе: {pos}/{len(vals)}")
srt=sorted(vals,reverse=True)
without_best=1.0
for v in vals:
    if v!=srt[0]: without_best*=(1+v/100)
print(f"лучший месяц: {srt[0]:.2f}%   худший: {srt[-1]:.2f}%")
print(f"БЕЗ лучшего месяца итог: {(without_best-1)*100:.1f}%")
print(f"доля лучшего месяца в прибыли: {srt[0]/sum(v for v in vals if v>0)*100:.1f}%")
