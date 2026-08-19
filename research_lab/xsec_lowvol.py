"""ВТОРАЯ НОГА: кросс-секционная низкая волатильность (betting-against-beta).
ДРУГОЙ механизм: ранжируем не по доходности, а по РИСКУ. Документированная аномалия.
Ключевое - корреляция с моментумом. Низкая корреляция = падение просадки портфеля."""
import json
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
alld=sorted({d for s in px for d in px[s]}); N=len(alld)
mature=[s for s in px if len(px[s])>=390]
R=3; K=5; MAKER=0.0002; TAKER=0.00055; TV=0.15
def vol(s,i,W):
    rs=[]
    for j in range(i-W,i):
        a=px[s].get(alld[j-1]); b=px[s].get(alld[j])
        if a and b and a>0: rs.append(b/a-1.0)
    if len(rs)<W//2: return None
    m=sum(rs)/len(rs)
    return (sum((x-m)**2 for x in rs)/(len(rs)-1))**0.5
def build(mode, W):
    bars=list(range(max(60,W+2), N-R-1, R)); out=[]
    for i in bars:
        t=alld[i]; t2=alld[i+R]; sc=[]
        for s in mature:
            p1=px[s].get(t); p2=px[s].get(t2)
            if not(p1 and p2 and p1>0): continue
            if mode=="lowvol":
                v=vol(s,i,W)
                if v is None or v<=0: continue
                sc.append((-v,s))           # чем НИЖЕ вол, тем выше ранг
            else:
                p0=px[s].get(alld[i-W])
                if not(p0 and p0>0): continue
                sc.append((p1/p0-1.0,s))
        if len(sc)<2*K+4: out.append(None); continue
        sc.sort(reverse=True); f=lambda s:(px[s][t2]/px[s][t]-1.0)
        out.append(sum(f(s) for s in [s for _,s in sc[:K]])/K
                  -sum(f(s) for s in [s for _,s in sc[-K:]])/K -2*MAKER-2*TAKER)
    return out
def vt(r,win=20):
    o=[]
    for i,x in enumerate(r):
        if x is None: o.append(None); continue
        h=[y for y in r[max(0,i-win):i] if y is not None]
        if len(h)<8: o.append(x*0.5); continue
        m=sum(h)/len(h); sd=(sum((y-m)**2 for y in h)/(len(h)-1))**0.5
        ann=sd*(365/R)**0.5
        o.append(x*(min(1.0,TV/ann) if ann>0 else 1.0))
    return o
def M(r):
    r=[x for x in r if x is not None]
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
print("НИЗКАЯ ВОЛАТИЛЬНОСТЬ (лонг спокойные / шорт бешеные), 62 зрелых монеты")
print("окно | итог   | DD    | Sharpe | 1-я    | 2-я")
best=None
for W in (10,20,30,45):
    r=vt(build("lowvol",W)); a=M(r)
    print(f"{W:>4} | {a['tot']:>6}% | {a['dd']:>4}% | {a['sh']:>6} | {a['h1']:>5}% | {a['h2']:>5}%")
    if best is None or a['sh']>best[1]['sh']: best=(W,a,r)
# корреляция с моментумом
mom=[]
for L in (7,14,21,30,45):
    mom.append(build("mom",L))
m=min(len(x) for x in mom)
momp=[]
for j in range(m):
    v=[s[j] for s in mom if s[j] is not None]
    momp.append(sum(v)/len(v) if v else None)
momv=vt(momp)
W,a,lv=best
n=min(len(momv),len(lv))
pa=[(momv[i],lv[i]) for i in range(n) if momv[i] is not None and lv[i] is not None]
ma=sum(x for x,_ in pa)/len(pa); mb=sum(y for _,y in pa)/len(pa)
cov=sum((x-ma)*(y-mb) for x,y in pa)/(len(pa)-1)
sa=(sum((x-ma)**2 for x,_ in pa)/(len(pa)-1))**0.5
sb=(sum((y-mb)**2 for _,y in pa)/(len(pa)-1))**0.5
corr=cov/(sa*sb) if sa*sb>0 else 0
print(f"\nКОРРЕЛЯЦИЯ с моментумом (окно {W}): {corr:.3f}")
comb=[(x+y)/2 for x,y in pa]; c=M(comb)
mm=M([x for x,_ in pa])
print(f"\nтолько моментум:      итог {mm['tot']}%  DD {mm['dd']}%  Sharpe {mm['sh']}")
print(f"только низкая вол:    итог {a['tot']}%  DD {a['dd']}%  Sharpe {a['sh']}")
print(f"ДВЕ НОГИ 50/50:       итог {c['tot']}%  DD {c['dd']}%  Sharpe {c['sh']}  (1-я {c['h1']}%, 2-я {c['h2']}%)")
