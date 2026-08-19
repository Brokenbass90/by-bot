"""ПРЕ-РЕГИСТРАЦИЯ (объявлено ДО прогона, один прогон, без перебора):
вход: закрытие импульсного бара, направление - против импульса
стоп:  1.0 x величина импульса
тейк:  2.0 x величина импульса
таймаут: 24 бара (2ч), выход по цене
издержки: мейкер 4 bps круг.  Окна НЕПЕРЕСЕКАЮЩИЕСЯ."""
import json, os, random, sys
D="research_lab/data/movers_5m"
files=sorted(os.listdir(D)); random.seed(7); random.shuffle(files); files=files[:int(sys.argv[1])]
STOP_R, TAKE_R, MAXH, FEE = 1.0, 2.0, 24, 0.0004
ev=[]
for fn in files:
    try: rows=json.load(open(os.path.join(D,fn)))
    except: continue
    if len(rows)<500: continue
    sym=fn.replace(".json","")
    o=[r[1] for r in rows]; hi=[r[2] for r in rows]; lo=[r[3] for r in rows]
    c=[r[4] for r in rows]; v=[r[5] for r in rows]; t=[r[0] for r in rows]; n=len(c)
    i=60
    while i<n-MAXH-1:
        vm=sum(v[i-20:i])/20.0
        if vm<=0: i+=1; continue
        ret=c[i]/c[i-1]-1.0
        if abs(ret)<0.02 or v[i]<3*vm: i+=1; continue
        d=-1 if ret>0 else 1              # фейд: импульс вверх -> шорт
        e=c[i]; R=abs(ret)*e
        stop = e - d*STOP_R*R
        take = e + d*TAKE_R*R
        out=None
        for j in range(i+1, i+1+MAXH):
            if d>0:
                if lo[j]<=stop: out=(stop-e)/e; break
                if hi[j]>=take: out=(take-e)/e; break
            else:
                if hi[j]>=stop: out=-(stop-e)/e; break
                if lo[j]<=take: out=-(take-e)/e; break
        if out is None:
            j=min(i+MAXH, n-1); out=d*(c[j]-e)/e
        ev.append((t[i], sym, 1 if ret>0 else -1, out-FEE))
        i+=MAXH
ev.sort()
def st(rows):
    if len(rows)<30: return None
    p=[x[3] for x in rows]; m=sum(p)/len(p)
    sd=(sum((x-m)**2 for x in p)/max(1,len(p)-1))**0.5
    gp=sum(x for x in p if x>0); gl=-sum(x for x in p if x<0)
    return dict(n=len(p), bps=round(m*10000,1), win=round(sum(1 for x in p if x>0)/len(p)*100,1),
                pf=round(gp/gl,3) if gl>0 else 99.9, t=round(m/sd*len(p)**0.5,2) if sd>0 else 0)
print(f"монет {len(files)}, непересекающихся событий {len(ev)}, стоп 1R / тейк 2R / таймаут 2ч\n")
print("срез                        |    n | bps    | win%  | PF    | t-стат")
def row(name, rows):
    s=st(rows)
    if s: print(f"{name:<27} | {s['n']:>4} | {s['bps']:>6} | {s['win']:>5} | {s['pf']:>5} | {s['t']:>5}")
row("ВСЁ", ev)
row("  фейд разгона ВВЕРХ", [x for x in ev if x[2]>0])
row("  фейд пролива ВНИЗ", [x for x in ev if x[2]<0])
k=int(len(ev)*0.8)
print()
row("первые 80% (IS)", ev[:k]); row("ПОСЛЕДНИЕ 20% (OOS)", ev[k:])
json.dump(ev, open("research_lab/data/fade_rr_events.json","w"))
