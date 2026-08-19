"""РЕАЛИСТИЧНОЕ исполнение для кандидата №1.
Вход можно ждать лимиткой (не исполнилось - пропустили сделку).
ВЫХОД ждать нельзя - позицию надо закрыть -> тейкер.
Считаем смешанный сценарий, а не оптимистичный чистый мейкер."""
import json,os
D=json.load(open("research_lab/data/daily_closes.json"))
syms=sorted(D); px={s:{int(k):v for k,v in D[s].items()} for s in syms}
days=sorted(set().union(*[set(px[s]) for s in syms])); N=len(days)
R=3;K=5;LOOK=[7,14,21,30,45]
MAKER=0.0002; TAKER=0.00055
def leg(L,i,cost_in,cost_out):
    if i-L<0 or i+R>=N: return None
    t=days[i];t0=days[i-L];t2=days[i+R];sc=[]
    for s in syms:
        p0=px[s].get(t0);p1=px[s].get(t);p2=px[s].get(t2)
        if p0 and p1 and p2 and p0>0 and p1>0: sc.append((p1/p0-1.0,s))
    if len(sc)<2*K+2: return None
    sc.sort(reverse=True); f=lambda s:(px[s][t2]/px[s][t]-1.0)
    gross=sum(f(s) for s in [s for _,s in sc[:K]])/K - sum(f(s) for s in [s for _,s in sc[-K:]])/K
    return gross - 2*cost_in - 2*cost_out       # 2 ноги вход + 2 ноги выход
def stats(r):
    r=[x for x in r if x is not None]
    if len(r)<6: return None
    e=1.0;pk=1.0;dd=0.0
    for x in r: e*=(1+x);pk=max(pk,e);dd=max(dd,(pk-e)/pk)
    mu=sum(r)/len(r);v=sum((x-mu)**2 for x in r)/max(1,len(r)-1);sd=v**0.5
    return round((e-1)*100,1),round(dd*100,1),round((mu/sd)*(len(r)**0.5),2) if sd>0 else 0,len(r)
bars=list(range(max(LOOK)+1,N-R-1,R))
scen=[("чистый мейкер (оптимизм)",MAKER,MAKER),
      ("РЕАЛИЗМ: вход мейкер / выход тейкер",MAKER,TAKER),
      ("чистый тейкер (пессимизм)",TAKER,TAKER)]
print("сценарий исполнения                  | весь период | 1-я пол. | 2-я ПОЛ. | DD    | Sharpe")
for name,ci,co in scen:
    ser={L:[leg(L,i,ci,co) for i in bars] for L in LOOK}
    eq=[]
    for j in range(len(bars)):
        vs=[ser[L][j] for L in LOOK if ser[L][j] is not None]
        eq.append(sum(vs)/len(vs) if vs else None)
    e=[x for x in eq if x is not None]; h=len(e)//2
    a=stats(e); b=stats(e[:h]); c=stats(e[h:])
    print(f"{name:<36} | {a[0]:>10}% | {b[0]:>7}% | {c[0]:>7}% | {a[1]:>4}% | {a[2]:>5}")
print("\nмейкер 2 bps/нога, тейкер 5.5 bps/нога (Bybit linear)")
