"""ПРЕ-РЕГИСТРИРОВАННЫЙ ПРОГОН: research_lab/prereg/XSEC_MATURE_2026_07_22.json. Один раз."""
import json, collections
P=json.load(open("research_lab/prereg/XSEC_MATURE_2026_07_22.json"))
D=json.load(open("research_lab/data/daily_338.json"))
px={s:{int(k):v for k,v in D[s].items()} for s in D}
alld=sorted({d for s in px for d in px[s]}); N=len(alld)
LOOK=[7,14,21,30,45]; R=3; K=5; MAKER=0.0002; TAKER=0.00055
MATURE=390; TARGET_VOL=0.15
mature=[s for s in px if len(px[s])>=MATURE]
def series(syms, per_symbol=False):
    bars=list(range(max(LOOK)+1,N-R-1,R)); ser={}; contrib=collections.defaultdict(float)
    for L in LOOK:
        row=[]
        for i in bars:
            t=alld[i];t0=alld[i-L];t2=alld[i+R];sc=[]
            for s in syms:
                p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
                if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
            if len(sc)<2*K+4: row.append(None); continue
            sc.sort(reverse=True); f=lambda s:(px[s][t2]/px[s][t]-1.0)
            L5=[s for _,s in sc[:K]]; S5=[s for _,s in sc[-K:]]
            if per_symbol:
                for s in L5: contrib[s]+= f(s)/K/len(LOOK)
                for s in S5: contrib[s]+= -f(s)/K/len(LOOK)
            row.append(sum(f(s) for s in L5)/K - sum(f(s) for s in S5)/K - 2*MAKER - 2*TAKER)
        ser[L]=row
    eq=[]
    for j in range(len(bars)):
        v=[ser[L][j] for L in LOOK if ser[L][j] is not None]
        eq.append(sum(v)/len(v) if v else None)
    return [x for x in eq if x is not None], contrib
def voltarget(r, win=20):
    out=[]
    for i,x in enumerate(r):
        h=r[max(0,i-win):i]
        if len(h)<8: out.append(x*0.5); continue
        m=sum(h)/len(h); sd=(sum((y-m)**2 for y in h)/(len(h)-1))**0.5
        ann=sd*(365/R)**0.5
        lev=min(1.0, TARGET_VOL/ann) if ann>0 else 1.0
        out.append(x*lev)
    return out
def M(r):
    if len(r)<8: return None
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x);pk=max(pk,e);dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r);v=sum((y-mu)**2 for y in r)/max(1,len(r)-1);sd=v**0.5
    return dict(tot=round((e-1)*100,1), dd=round(dd*100,1),
                sh=round(mu/sd*len(r)**0.5,2) if sd>0 else 0, n=len(r))
raw,contrib = series(mature, per_symbol=True)
vt = voltarget(raw)
print(f"универсум: {len(mature)} зрелых монет (>= {MATURE} дней истории)\n")
for nm,r in [("СЫРОЙ (диагностика)",raw),("ТАРГЕТ ВОЛАТИЛЬНОСТИ 15% (основной)",vt)]:
    a=M(r); h=len(r)//2; b=M(r[:h]); c=M(r[h:])
    print(f"{nm}\n   итог {a['tot']}%  DD {a['dd']}%  Sharpe {a['sh']}  n={a['n']}")
    print(f"   1-я половина {b['tot']}%   2-я половина {c['tot']}%")
print("\n" + "="*58)
print("ВОРОТА (объявлены до прогона)")
print("="*58)
a=M(vt); h=len(vt)//2; b=M(vt[:h]); c=M(vt[h:])
res={}
res["G1 обе половины > 0"]      = (b['tot']>0 and c['tot']>0, f"1-я {b['tot']}%, 2-я {c['tot']}%")
res["G2 Sharpe >= 0.8"]         = (a['sh']>=0.8, f"{a['sh']}")
res["G3 просадка <= 50%"]       = (a['dd']<=50.0, f"{a['dd']}%")
half=len(mature)//2
A=sorted(mature)[0::2]; B=sorted(mature)[1::2]
ra,_=series(A); rb,_=series(B)
va=M(voltarget(ra)); vb=M(voltarget(rb))
res["G4 обе половины символов > 0"]=(va['tot']>0 and vb['tot']>0, f"A({len(A)}) {va['tot']}%, B({len(B)}) {vb['tot']}%")
best=max(contrib.items(), key=lambda kv: kv[1])[0]
rl,_=series([s for s in mature if s!=best]); vl=M(voltarget(rl))
res["G5 LOSO (без лучшей) > 0"] =(vl['tot']>0, f"убрали {best}: {vl['tot']}%")
ok=True
for k,(p,det) in res.items():
    ok = ok and p
    print(f"  [{'PASS' if p else 'FAIL'}]  {k:<32} {det}")
print("="*58)
print("ИТОГ:", "ПРОЙДЕНО — можно передавать на интеграцию" if ok else "ОТКЛОНЕНО — перенастройка запрещена")
