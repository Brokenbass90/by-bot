"""КЛАСС-ТЕСТ свежих монет: после импульса цена продолжает или откатывает?
Если ни одно направление не даёт эджа после издержек - весь класс пробойных/фейдовых стратегий мёртв."""
import json, os, random, sys
D="research_lab/data/movers_5m"
files=sorted(os.listdir(D)); random.seed(7); random.shuffle(files)
files=files[:int(sys.argv[1]) if len(sys.argv)>1 else 70]
TAKER=0.00055; MAKER=0.0002
res={}
nsym=0; nbars=0
for fn in files:
    try: rows=json.load(open(os.path.join(D,fn)))
    except: continue
    if len(rows)<500: continue
    nsym+=1; nbars+=len(rows)
    c=[r[4] for r in rows]; v=[r[5] for r in rows]; h=[r[2] for r in rows]; l=[r[3] for r in rows]
    n=len(c)
    for i in range(60,n-25):
        vm=sum(v[i-20:i])/20.0
        if vm<=0: continue
        ret=c[i]/c[i-1]-1.0
        if abs(ret)<0.02: continue          # импульс >=2% за 5 минут
        if v[i] < 3*vm: continue            # на объёме >=3x
        d=1 if ret>0 else -1
        for H in (3,6,12,24):               # 15м / 30м / 1ч / 2ч
            j=i+H
            if j>=n: continue
            fwd=(c[j]/c[i]-1.0)
            res.setdefault(("ПРОДОЛЖЕНИЕ",H),[]).append(d*fwd)
            res.setdefault(("ОТКАТ",H),[]).append(-d*fwd)
print(f"монет: {nsym}, баров: {nbars:,}\n")
print("сторона        гориз | n      | сырой bps | МЕЙКЕР(-4bps) | ТЕЙКЕР(-11bps) | win%")
for (name,H),v in sorted(res.items()):
    if len(v)<200: continue
    m=sum(v)/len(v)*10000
    w=sum(1 for x in v if x>0)/len(v)*100
    print(f"{name:<14} {H*5:>3}м | {len(v):<6} | {m:>9.2f} | {m-4:>13.2f} | {m-11:>14.2f} | {w:.1f}%")
