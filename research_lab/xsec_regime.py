"""Короткая нога зарабатывает из-за падения рынка или из-за ранжирования? Тест против бенчмарка."""
import json,os
ROOT="/sessions/admiring-beautiful-heisenberg/mnt/bybit-bot-clean-v28"
D=json.load(open(os.path.join(ROOT,"research_lab/data/daily_closes.json")))
syms=sorted(D); px={s:{int(k):v for k,v in D[s].items()} for s in syms}
alldays=sorted(set().union(*[set(px[s]) for s in syms])); N=len(alldays); COST=0.0008
def legs(L,R,K,i0,i1):
    out=[]; i=max(i0,max(L,25)); end=min(i1,N-R-1)
    while i<end:
        t=alldays[i]; t0=alldays[i-L]; t2=alldays[i+R]; sc=[]
        for s in syms:
            p0=px[s].get(t0); p1=px[s].get(t); p2=px[s].get(t2)
            if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
        if len(sc)<2*K+2: i+=R; continue
        sc.sort(reverse=True); Lg=[s for _,s in sc[:K]]; Sh=[s for _,s in sc[-K:]]
        uni=[s for _,s in sc]
        f=lambda s:(px[s][t2]/px[s][t]-1.0)
        mkt=sum(f(s) for s in uni)/len(uni)
        out.append((sum(f(s) for s in Lg)/K, sum(f(s) for s in Sh)/K, mkt))
        i+=R
    return out
def cmp_(r):
    e=1.0
    for x in r: e*=(1+x)
    return round((e-1)*100,1)
cut=int(N*0.66)
for name,(a,b) in [("ВЕСЬ ПЕРИОД",(0,N)),("СВЕЖИЙ (373 дн)",(cut,N))]:
    print(f"\n===== {name} =====")
    print("L  R  K | рынок  | шорт-дно | шорт-рынка | АЛЬФА шорта | АЛЬФА лонга")
    for L,R,K in [(7,7,3),(14,7,5),(7,3,3),(45,14,5)]:
        d=legs(L,R,K,a,b)
        if len(d)<6: continue
        mkt=cmp_([m for _,_,m in d])
        sb =cmp_([-s-2*COST for _,s,_ in d])
        sm =cmp_([-m-2*COST for _,_,m in d])
        al =cmp_([l-m for l,_,m in d])       # лонг сверх рынка
        as_=cmp_([m-s for _,s,m in d])       # рынок сверх дна = альфа шорта
        print(f"{L:<3}{R:<3}{K:<3}|{mkt:>7}%|{sb:>9}%|{sm:>11}%|{as_:>12}%|{al:>12}%")
print("\nАЛЬФА = чистое ранжирование, рыночное движение вычтено.")
