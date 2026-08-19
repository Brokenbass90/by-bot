"""Спасает ли ММ правило «не котировать против потока»?
Дисбаланс потока за последние 10с; ММ берёт сторону против агрессора.
Если агрессор идёт ПО тренду потока - вероятно информирован (токсично)."""
import sys, json, bisect
ts=[];px=[];sd=[];sz=[]
for line in sys.stdin:
    if '"kind":"trade"' not in line: continue
    try: o=json.loads(line)
    except: continue
    t=o.get("exch_ts_ms")
    if not t: continue
    ts.append(int(t)); px.append(float(o["price"])); sd.append(1 if o["side"]=="Buy" else -1); sz.append(float(o["size"])*float(o["price"]))
n=len(ts)
if n<1000: print("мало"); sys.exit()
# скользящий дисбаланс за 10с
W=10000; cum=[0.0]*(n+1)
for i in range(n): cum[i+1]=cum[i]+sd[i]*sz[i]
cumabs=[0.0]*(n+1)
for i in range(n): cumabs[i+1]=cumabs[i]+sz[i]
def imb(i):
    k=bisect.bisect_left(ts, ts[i]-W)
    tot=cumabs[i]-cumabs[k]
    if tot<=0: return 0.0
    return (cum[i]-cum[k])/tot
groups={"поток СПОКОЙНЫЙ |imb|<0.2":[], "агрессор ПО потоку (imb*side>0.4)":[], "агрессор ПРОТИВ потока (imb*side<-0.4)":[]}
for i in range(n):
    v=imb(i); a=v*sd[i]
    if abs(v)<0.2: groups["поток СПОКОЙНЫЙ |imb|<0.2"].append(i)
    elif a>0.4: groups["агрессор ПО потоку (imb*side>0.4)"].append(i)
    elif a<-0.4: groups["агрессор ПРОТИВ потока (imb*side<-0.4)"].append(i)
print("группа                                | n      | 5s     | 30s    | 60s   (bps)")
for name,idx in groups.items():
    row=[]
    for H in (5000,30000,60000):
        v=[]
        for i in idx:
            j=bisect.bisect_left(ts,ts[i]+H)
            if j>=n: continue
            v.append(-sd[i]*(px[j]-px[i])/px[i]*10000.0)
        row.append(sum(v)/len(v) if v else 0.0)
    print(f"{name:<37} | {len(idx):<6} | {row[0]:>6.3f} | {row[1]:>6.3f} | {row[2]:>6.3f}")
