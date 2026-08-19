"""МАРКЕТ-МЕЙКИНГ: тест жизнеспособности через markout.
Логика: агрессор Buy -> ММ ПРОДАЛ по P. Агрессор Sell -> ММ КУПИЛ по P.
Прибыль ММ = -sign*(P_future - P), где sign=+1 для Buy. Меряем на горизонтах."""
import sys, json, bisect
path=sys.argv[1]
ts=[]; px=[]; sd=[]; sz=[]
for line in sys.stdin:
    if '"kind":"trade"' not in line: continue
    try: o=json.loads(line)
    except: continue
    t=o.get("exch_ts_ms")
    if not t: continue
    ts.append(int(t)); px.append(float(o["price"])); sd.append(1 if o["side"]=="Buy" else -1); sz.append(float(o["size"]))
n=len(ts)
print(f"сделок: {n}  период: {(ts[-1]-ts[0])/3600000:.1f} ч")
if n<1000: sys.exit()
avg=sum(px)/n
print(f"средняя цена: {avg:.4f}   объём: {sum(a*b for a,b in zip(px,sz))/1e6:.2f} млн USDT")
HOR=[1000,5000,30000,60000,300000]
print("\nMARKOUT маркет-мейкера (bps от цены), горизонт -> средний / медиана / доля>0")
res={}
for H in HOR:
    vals=[]
    for i in range(n):
        j=bisect.bisect_left(ts, ts[i]+H)
        if j>=n: break
        # ММ занял противоположную агрессору сторону
        pnl = -sd[i]*(px[j]-px[i])/px[i]*10000.0
        vals.append(pnl)
    if len(vals)<500: continue
    vals.sort(); m=sum(vals)/len(vals); med=vals[len(vals)//2]
    pos=sum(1 for v in vals if v>0)/len(vals)*100
    res[H]=m
    print(f"  {H//1000:>4}s  ->  {m:>7.3f} bps   {med:>7.3f}    {pos:.1f}%   n={len(vals)}")
print("\nЧТО ЭТО ЗНАЧИТ (Bybit linear: maker 2bps, taker 5.5bps):")
for H,m in res.items():
    for exit_name,fee in (("выход мейкером (2+2=4bps)",4.0),("выход тейкером (2+5.5=7.5bps)",7.5)):
        net=m-fee
        if H==30000:
            print(f"  {H//1000}s, {exit_name}: {m:.3f} - {fee} = {net:+.3f} bps {'ПРИБЫЛЬ' if net>0 else 'убыток'}")
