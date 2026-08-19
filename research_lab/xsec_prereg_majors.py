"""Тот же ЗАМОРОЖЕННЫЙ конфиг на ИСХОДНОМ универсуме мажоров (другие монеты, другие 3 года)."""
import json
D=json.load(open("research_lab/data/daily_closes.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
syms=sorted(px); alld=sorted({d for s in syms for d in px[s]}); N=len(alld)
LOOK=[7,14,21,30,45]; R=3; K=5; MAKER=0.0002; TAKER=0.00055; TARGET_VOL=0.15
def series(sy):
    bars=list(range(max(LOOK)+1,N-R-1,R)); ser={}
    for L in LOOK:
        row=[]
        for i in bars:
            t=alld[i];t0=alld[i-L];t2=alld[i+R];sc=[]
            for s in sy:
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
def voltarget(r,win=20):
    out=[]
    for i,x in enumerate(r):
        h=r[max(0,i-win):i]
        if len(h)<8: out.append(x*0.5); continue
        m=sum(h)/len(h); sd=(sum((y-m)**2 for y in h)/(len(h)-1))**0.5
        ann=sd*(365/R)**0.5
        out.append(x*(min(1.0,TARGET_VOL/ann) if ann>0 else 1.0))
    return out
def M(r):
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x);pk=max(pk,e);dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r);v=sum((y-mu)**2 for y in r)/max(1,len(r)-1);sd=v**0.5
    return dict(tot=round((e-1)*100,1),dd=round(dd*100,1),
                sh=round(mu/sd*len(r)**0.5,2) if sd>0 else 0,n=len(r))
raw=series(syms); vt=voltarget(raw)
print(f"универсум мажоров: {len(syms)} монет, {N} дней (~3 года)\n")
for nm,r in [("сырой",raw),("ТАРГЕТ ВОЛАТИЛЬНОСТИ 15%",vt)]:
    a=M(r); h=len(r)//2; b=M(r[:h]); c=M(r[h:])
    print(f"{nm}: итог {a['tot']}%  DD {a['dd']}%  Sharpe {a['sh']}  n={a['n']}")
    print(f"    1-я половина {b['tot']}%   2-я половина {c['tot']}%")
A=syms[0::2]; B=syms[1::2]
va=M(voltarget(series(A))); vb=M(voltarget(series(B)))
print(f"\nхолдаут по символам: A({len(A)}) {va['tot']}%  |  B({len(B)}) {vb['tot']}%")
