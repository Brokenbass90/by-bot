"""РЫЧАГИ снижения просадки. Каждый принципиальный, без новых подгоняемых параметров.
ВАЖНО: это НЕ модификация прошедшего ворота конфига - тот заморожен.
Это кандидаты в ОТДЕЛЬНУЮ пре-регистрацию."""
import json
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
alld=sorted({d for s in px for d in px[s]}); N=len(alld)
mature=[s for s in px if len(px[s])>=390]
LOOK=[7,14,21,30,45]; R=3; K=5; MAKER=0.0002; TAKER=0.00055; TV=0.15
def leg_at(L,i,K_):
    if i-L<0 or i+R>=N: return None
    t=alld[i];t0=alld[i-L];t2=alld[i+R];sc=[]
    for s in mature:
        p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
        if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
    if len(sc)<2*K_+4: return None
    sc.sort(reverse=True); f=lambda s:(px[s][t2]/px[s][t]-1.0)
    return sum(f(s) for s in [s for _,s in sc[:K_]])/K_ - sum(f(s) for s in [s for _,s in sc[-K_:]])/K_ -2*MAKER-2*TAKER
def build(offset, K_=K, looks=LOOK):
    bars=list(range(max(looks)+1+offset, N-R-1, R))
    out=[]
    for i in bars:
        v=[leg_at(L,i,K_) for L in looks]
        v=[x for x in v if x is not None]
        out.append(sum(v)/len(v) if v else None)
    return [x for x in out if x is not None]
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
                sh=round(mu/sd*len(r)**0.5,2) if sd>0 else 0,
                h1=tot(r[:h]),h2=tot(r[h:]),n=len(r))
print("рычаг                                  | итог  | DD    | Sharpe | 1-я  | 2-я")
base=vt(build(0)); a=M(base)
print(f"{'БАЗА (прошла ворота)':<38} | {a['tot']:>5}% | {a['dd']:>4}% | {a['sh']:>6} | {a['h1']:>4}% | {a['h2']:>4}%")
# рычаг 1: разнесение стартов ребаланса (3 подпортфеля со сдвигом 1 день)
subs=[vt(build(o)) for o in (0,1,2)]
m=min(len(x) for x in subs)
stag=[sum(s[i] for s in subs)/3 for i in range(m)]
a=M(stag); print(f"{'1. РАЗНЕСЕНИЕ ребалансов (3 сдвига)':<38} | {a['tot']:>5}% | {a['dd']:>4}% | {a['sh']:>6} | {a['h1']:>4}% | {a['h2']:>4}%")
# рычаг 2: шире корзина K=8
a=M(vt(build(0,K_=8))); print(f"{'2. Шире корзина K=8':<38} | {a['tot']:>5}% | {a['dd']:>4}% | {a['sh']:>6} | {a['h1']:>4}% | {a['h2']:>4}%")
# рычаг 3: больше lookback'ов
a=M(vt(build(0,looks=[5,7,10,14,21,30,45,60])))
print(f"{'3. Больше lookbackов (8 штук)':<38} | {a['tot']:>5}% | {a['dd']:>4}% | {a['sh']:>6} | {a['h1']:>4}% | {a['h2']:>4}%")
# рычаг 4: разнесение + шире корзина
subs=[vt(build(o,K_=8)) for o in (0,1,2)]
m=min(len(x) for x in subs)
both=[sum(s[i] for s in subs)/3 for i in range(m)]
a=M(both); print(f"{'4. РАЗНЕСЕНИЕ + K=8 (вместе)':<38} | {a['tot']:>5}% | {a['dd']:>4}% | {a['sh']:>6} | {a['h1']:>4}% | {a['h2']:>4}%")
