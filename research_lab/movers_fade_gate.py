"""ФЕЙД ИМПУЛЬСА -> ВОРОТА. Непересекающиеся окна + стороны раздельно + time-OOS."""
import json, os, random, sys
D="research_lab/data/movers_5m"
files=sorted(os.listdir(D)); random.seed(7); random.shuffle(files)
files=files[:int(sys.argv[1])]
H=12                      # 60 минут
MAKER=0.0002
ev=[]                     # (ts, sym, side_of_impulse, pnl)
for fn in files:
    try: rows=json.load(open(os.path.join(D,fn)))
    except: continue
    if len(rows)<500: continue
    sym=fn.replace(".json","")
    c=[r[4] for r in rows]; v=[r[5] for r in rows]; t=[r[0] for r in rows]; n=len(c)
    i=60
    while i<n-H-1:
        vm=sum(v[i-20:i])/20.0
        if vm<=0: i+=1; continue
        ret=c[i]/c[i-1]-1.0
        if abs(ret)<0.02 or v[i]<3*vm: i+=1; continue
        d=1 if ret>0 else -1
        pnl=-d*(c[i+H]/c[i]-1.0) - 4*MAKER      # фейд, мейкер обе ноги
        ev.append((t[i], sym, d, pnl))
        i+=H                                     # НЕПЕРЕСЕКАЮЩИЕСЯ окна
ev.sort()
def st(rows):
    if len(rows)<30: return None
    p=[x[3] for x in rows]
    m=sum(p)/len(p); sd=(sum((x-m)**2 for x in p)/max(1,len(p)-1))**0.5
    w=sum(1 for x in p if x>0)/len(p)*100
    gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    return dict(n=len(p), bps=round(m*10000,2), win=round(w,1),
                pf=round(gp/gl,3) if gl>0 else 99.9,
                t=round(m/sd*len(p)**0.5,2) if sd>0 else 0)
print(f"монет: {len(files)}   НЕПЕРЕСЕКАЮЩИХСЯ событий: {len(ev)}   горизонт 60м, мейкер\n")
print("срез                        |    n | bps    | win%  | PF    | t-стат")
def row(name, rows):
    s=st(rows)
    if s: print(f"{name:<27} | {s['n']:>4} | {s['bps']:>6} | {s['win']:>5} | {s['pf']:>5} | {s['t']:>5}")
row("ВСЁ", ev)
row("  фейд разгона ВВЕРХ", [x for x in ev if x[2]>0])
row("  фейд пролива ВНИЗ", [x for x in ev if x[2]<0])
k=int(len(ev)*0.8)
print()
row("время: первые 80% (IS)", ev[:k])
row("время: ПОСЛЕДНИЕ 20% (OOS)", ev[k:])
row("  OOS фейд ВВЕРХ", [x for x in ev[k:] if x[2]>0])
row("  OOS фейд ВНИЗ", [x for x in ev[k:] if x[2]<0])
json.dump([[a,b,c_,d_] for a,b,c_,d_ in ev], open("research_lab/data/fade_events.json","w"))
print("\nсобытия сохранены -> research_lab/data/fade_events.json")
