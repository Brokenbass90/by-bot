"""Парный стат-арб: торгуем расхождение пары монет (market-neutral, не предсказание направления).
ЧЕСТНО: оцениваем стратегию на ВСЕХ парах агрегированно, НЕ выбираем лучшие пары (это было бы переобучение).
"""
import json, os, math, itertools
ROOT="/sessions/admiring-beautiful-heisenberg/mnt/bybit-bot-clean-v28"
D=json.load(open(os.path.join(ROOT,"research_lab/data/daily_closes.json")))
syms=sorted(D)
days=sorted(set.intersection(*[set(int(k) for k in D[s]) for s in syms]))
px={s:{int(k):v for k,v in D[s].items()} for s in syms}
COST=0.0008  # 8bps на ногу

def run(W, ZIN, ZOUT, MAXHOLD, funding_bps=0.0):
    all_tr=[]; by_pair={}
    for a,b in itertools.combinations(syms,2):
        series=[]
        for d in days:
            pa=px[a].get(d); pb=px[b].get(d)
            if pa and pb and pa>0 and pb>0: series.append((d, math.log(pa/pb)))
        if len(series)<W+30: continue
        pos=None; trades=[]
        for i in range(W,len(series)):
            d,s_now=series[i]
            win=[v for _,v in series[i-W:i]]
            m=sum(win)/W
            var=sum((x-m)**2 for x in win)/(W-1)
            sd=var**0.5
            if sd<=0: continue
            z=(s_now-m)/sd
            if pos is None:
                if z>=ZIN: pos=(i,-1,s_now)     # спред высок -> шорт спреда (шорт a, лонг b)
                elif z<=-ZIN: pos=(i,+1,s_now)  # лонг спреда
            else:
                i0,side,s0=pos
                held=i-i0
                if abs(z)<=ZOUT or held>=MAXHOLD:
                    pnl=side*(s_now-s0)                 # доход в лог-спреде ~ доходность market-neutral
                    fund=funding_bps/10000.0*held
                    net=pnl - 2*2*COST - fund           # 2 ноги, вход+выход
                    trades.append(net); pos=None
        if trades:
            all_tr.extend(trades); by_pair[f"{a}/{b}"]=trades
    return all_tr, by_pair

def stats(tr):
    n=len(tr)
    if n<20: return None
    tot=sum(tr); wins=sum(1 for r in tr if r>0)
    mean=tot/n; var=sum((r-mean)**2 for r in tr)/max(1,n-1); sd=var**0.5
    sharpe=(mean/sd)*(n**0.5) if sd>0 else 0
    eq=0; peak=0; dd=0
    for r in tr:
        eq+=r; peak=max(peak,eq); dd=max(dd,peak-eq)
    return dict(n=n, total=round(tot*100,1), win=round(100*wins/n,1), maxdd=round(dd*100,1), sharpe=round(sharpe,2))

print(f"монет={len(syms)} пар={len(list(itertools.combinations(syms,2)))} дней={len(days)}")
print(f"{'W':>3} {'Zin':>4} {'Zout':>5} {'hold':>5} | {'n':>5} {'total%':>8} {'win%':>6} {'maxDD%':>7} {'Sharpe':>6} | фолды 4")
cands=[]
for W in [30,60,90]:
    for ZIN in [1.5,2.0,2.5]:
        for ZOUT in [0.0,0.5]:
            for MH in [10,20,40]:
                tr,bp=run(W,ZIN,ZOUT,MH)
                st=stats(tr)
                if not st: continue
                q=len(tr)//4
                folds=[round(sum(tr[f*q:(f+1)*q] if f<3 else tr[3*q:])*100,1) for f in range(4)]
                pos=sum(1 for f in folds if f>0)
                line=f"{W:>3} {ZIN:>4} {ZOUT:>5} {MH:>5} | {st['n']:>5} {st['total']:>8} {st['win']:>6} {st['maxdd']:>7} {st['sharpe']:>6} | {folds} {pos}/4"
                print(line)
                if st['total']>0 and pos>=3: cands.append((st,W,ZIN,ZOUT,MH,line))
print("\n=== КАНДИДАТЫ (total>0, >=3/4 фолда) ===")
for c in cands: print("  ",c[5])
if not cands: print("  нет")
