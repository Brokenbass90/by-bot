"""Токсичность потока: markout ММ в разрезе размера агрессора и времени удержания."""
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
if n<1000: print("мало данных"); sys.exit()
srt=sorted(sz); q=lambda p: srt[int(len(srt)*p)]
buckets=[("мельчайшие <p50",0,q(0.50)),("p50-p80",q(0.50),q(0.80)),("p80-p95",q(0.80),q(0.95)),
         ("p95-p99",q(0.95),q(0.99)),("КРУПНЫЕ >p99",q(0.99),9e18)]
print(f"сделок {n}, медианный размер {q(0.5):.0f} USDT, p99 {q(0.99):.0f} USDT\n")
print("бакет агрессора        | n      | markout 5s | 30s   | 60s   (bps, + = ММ зарабатывает)")
for name,lo,hi in buckets:
    idx=[i for i in range(n) if lo<=sz[i]<hi]
    row=[]
    for H in (5000,30000,60000):
        v=[]
        for i in idx:
            j=bisect.bisect_left(ts,ts[i]+H)
            if j>=n: continue
            v.append(-sd[i]*(px[j]-px[i])/px[i]*10000.0)
        row.append(sum(v)/len(v) if v else 0.0)
    print(f"{name:<22} | {len(idx):<6} | {row[0]:>9.3f}  | {row[1]:>5.2f} | {row[2]:>5.2f}")
