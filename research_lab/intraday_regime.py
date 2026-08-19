"""РАЗБОР ПЕРЕЛОМА: почему H=12ч дал +171% в первой половине и -80% во второй?
Ищем ИЗМЕРИМОЕ отличие режимов, а не просто отбрасываем результат."""
import json, os, datetime, statistics
UNI=json.load(open("research_lab/prereg/xsec_mature_universe_v2.json"))["symbols"]
D="research_lab/data/movers_5m"
series={}
for s in UNI:
    p=os.path.join(D,s+".json")
    if not os.path.exists(p): continue
    r=json.load(open(p))
    if len(r)<20000: continue
    series[s]={b[0]//300000:b[4] for b in r}
syms=sorted(series); allk=sorted(set().union(*[set(series[s]) for s in syms]))
COST=2*0.0002+2*0.00055
H=12; step=H*12; K=5
rows=[]
i=step
while i+step<len(allk):
    k0=allk[i-step];k1=allk[i];k2=allk[i+step]; sc=[]
    for s in syms:
        p0=series[s].get(k0);p1=series[s].get(k1);p2=series[s].get(k2)
        if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
    if len(sc)<2*K+4: i+=step; continue
    sc.sort()
    f=lambda s:(series[s][k2]/series[s][k1]-1.0)
    lo=[s for _,s in sc[:K]]; hi=[s for _,s in sc[-K:]]
    pnl=sum(f(s) for s in hi)/K - sum(f(s) for s in lo)/K - COST
    # характеристики режима на момент решения
    past=[x for x,_ in sc]
    disp=statistics.pstdev(past) if len(past)>3 else 0.0     # разброс доходностей
    mkt=sum(f(s) for _,s in sc)/len(sc)                       # движение рынка вперёд
    mkt_past=sum(past)/len(past)                              # движение рынка назад
    ts=k1*300
    rows.append((ts,pnl,disp,mkt,mkt_past))
    i+=step
n=len(rows); h=n//2
def blk(r,name):
    p=[x[1] for x in r]
    e=1.0
    for x in p: e*=(1+x)
    print(f"{name:<16} n={len(p):<4} итог={(e-1)*100:>8.1f}%  средн.сделка={sum(p)/len(p)*10000:>7.2f}bps  "
          f"разброс={statistics.mean([x[2] for x in r])*100:>5.2f}%  рынок/12ч={statistics.mean([x[3] for x in r])*10000:>7.1f}bps")
d0=datetime.datetime.utcfromtimestamp(rows[0][0]).date()
dm=datetime.datetime.utcfromtimestamp(rows[h][0]).date()
d1=datetime.datetime.utcfromtimestamp(rows[-1][0]).date()
print(f"период: {d0} -> {dm} -> {d1}\n")
blk(rows[:h],"1-я половина"); blk(rows[h:],"2-я половина")
print()
# разбиение по РАЗБРОСУ - гипотеза: моментум живёт при высокой дисперсии
med=statistics.median([x[2] for x in rows])
blk([x for x in rows if x[2]>=med],"разброс ВЫСОКИЙ")
blk([x for x in rows if x[2]<med],"разброс низкий")
print()
# разбиение по направлению рынка
blk([x for x in rows if x[4]>0],"рынок рос")
blk([x for x in rows if x[4]<=0],"рынок падал")
print()
# помесячно
import collections
mon=collections.defaultdict(list)
for ts,p,_,_,_ in rows:
    d=datetime.datetime.utcfromtimestamp(ts)
    mon[f"{d.year}-{d.month:02d}"].append(p)
print("помесячно (средняя сделка, bps):")
for k in sorted(mon):
    v=mon[k]; print(f"   {k}  n={len(v):<3} {sum(v)/len(v)*10000:>8.2f}")
