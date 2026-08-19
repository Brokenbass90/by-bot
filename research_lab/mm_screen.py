"""Скрининг ММ-пригодности по трейдам: тик как доля цены = минимальный спред."""
import sys, json
px=[]; ticks=set(); sd=[]
for line in sys.stdin:
    if '"kind":"trade"' not in line: continue
    try: o=json.loads(line)
    except: continue
    p=o["price"]; px.append(float(p))
    dec=len(p.split(".")[1]) if "." in p else 0
    ticks.add(dec)
    sd.append(1 if o["side"]=="Buy" else -1)
if len(px)<2000: print("мало данных"); sys.exit()
dec=max(ticks); tick=10.0**(-dec)
avg=sum(px)/len(px)
tick_bps=tick/avg*10000.0
# Roll: эффективный спред из автоковариации приращений
d=[px[i+1]-px[i] for i in range(len(px)-1)]
m=sum(d)/len(d)
cov=sum((d[i]-m)*(d[i+1]-m) for i in range(len(d)-1))/(len(d)-1)
roll=2*((-cov)**0.5)/avg*10000.0 if cov<0 else 0.0
sym=sys.argv[1]
print(f"{sym:<14} цена={avg:<10.5f} тик={tick:<10g} ТИК_bps={tick_bps:>6.2f}  Roll-спред_bps={roll:>6.2f}  n={len(px)}")
