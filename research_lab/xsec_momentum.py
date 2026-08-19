"""Кросс-секционный моментум: ранжируем монеты, лонг топ-K / шорт дно-K, ребаланс раз в R дней.
Документированная аномалия (cross-sectional momentum). Совершенно другой механизм, чем паттерны.
Честно: издержки на обе ноги, разбивка по фолдам, без подгонки под результат."""
import json, os, itertools
ROOT="/sessions/admiring-beautiful-heisenberg/mnt/bybit-bot-clean-v28"
D=json.load(open(os.path.join(ROOT,"research_lab/data/daily_closes.json")))
syms=sorted(D)
days=sorted(set.intersection(*[set(int(k) for k in D[s]) for s in syms]))
px={s:{int(k):v for k,v in D[s].items()} for s in syms}
COST=0.0008  # 8bps на ногу (вход+выход учитывается ниже)

def run(L,R,K,mode):
    rets=[]; dates=[]
    i=L
    while i+R < len(days):
        t=days[i]; t2=days[i+R]
        scored=[]
        for s in syms:
            p0=px[s].get(days[i-L]); p1=px[s].get(t)
            if p0 and p1 and p0>0: scored.append((p1/p0-1.0, s))
        if len(scored)<2*K+1: i+=R; continue
        scored.sort(reverse=True)
        longs=[s for _,s in scored[:K]]; shorts=[s for _,s in scored[-K:]]
        def fwd(s):
            a=px[s].get(t); b=px[s].get(t2)
            return (b/a-1.0) if (a and b and a>0) else 0.0
        lr=sum(fwd(s) for s in longs)/K
        sr=sum(fwd(s) for s in shorts)/K
        gross = lr - sr if mode=="ls" else lr
        legs = 2 if mode=="ls" else 1
        net = gross - legs*2*COST   # вход+выход по каждой ноге
        rets.append(net); dates.append(t)
        i+=R
    return rets, dates

def stats(rets):
    n=len(rets)
    if n<8: return None
    tot=1.0
    for r in rets: tot*=(1+r)
    eq=1.0; peak=1.0; dd=0.0
    for r in rets:
        eq*=(1+r); peak=max(peak,eq); dd=max(dd,(peak-eq)/peak)
    wins=sum(1 for r in rets if r>0)
    mean=sum(rets)/n
    var=sum((r-mean)**2 for r in rets)/max(1,n-1)
    sd=var**0.5
    sharpe=(mean/sd)*(len(rets)**0.5) if sd>0 else 0.0
    return dict(n=n, total=round((tot-1)*100,2), win=round(100*wins/n,1), maxdd=round(dd*100,2), sharpe=round(sharpe,2))

print(f"монет={len(syms)} общих дней={len(days)}")
print(f"{'mode':<4} {'L':>3} {'R':>3} {'K':>2} | {'n':>4} {'total%':>8} {'win%':>6} {'maxDD%':>7} {'Sharpe':>6} | фолды(total% по 4)")
best=[]
for mode in ["ls","long"]:
    for L in [14,30,60,90]:
        for R in [7,14,30]:
            for K in [2,3,4]:
                rets,dates=run(L,R,K,mode)
                st=stats(rets)
                if not st: continue
                q=len(rets)//4
                folds=[]
                for f in range(4):
                    seg=rets[f*q:(f+1)*q] if f<3 else rets[3*q:]
                    tt=1.0
                    for r in seg: tt*=(1+r)
                    folds.append(round((tt-1)*100,1))
                pos=sum(1 for f in folds if f>0)
                line=f"{mode:<4} {L:>3} {R:>3} {K:>2} | {st['n']:>4} {st['total']:>8} {st['win']:>6} {st['maxdd']:>7} {st['sharpe']:>6} | {folds} {pos}/4"
                if st['total']>0 and pos>=3: best.append(line)
                print(line)
print("\n=== КАНДИДАТЫ (total>0 и >=3/4 фолда в плюс) ===")
for b in best: print(" ", b)
if not best: print("  нет")
