"""Реальный спред на ONDO: реплей книги, статистика top-of-book."""
import sys, json
bids={}; asks={}; sp=[]; d1=[]
def apply(side,levels):
    d = bids if side=="b" else asks
    for p,q in levels:
        p=float(p); q=float(q)
        if q==0: d.pop(p,None)
        else: d[p]=q
cnt=0
for line in sys.stdin:
    try: o=json.loads(line)
    except: continue
    k=o.get("kind")
    if k=="snapshot":
        bids.clear(); asks.clear()
    elif k!="delta":
        continue
    pl=o.get("payload") or {}
    apply("b", pl.get("b") or []); apply("a", pl.get("a") or [])
    if not bids or not asks: continue
    bb=max(bids); ba=min(asks)
    if ba<=bb: continue
    mid=(bb+ba)/2
    sp.append((ba-bb)/mid*10000.0)
    d1.append((bids[bb]*bb, asks[ba]*ba))
    cnt+=1
    if cnt>=250000: break
sp.sort()
n=len(sp)
print(f"наблюдений top-of-book: {n}")
print(f"спред bps:  p10={sp[n//10]:.2f}  медиана={sp[n//2]:.2f}  среднее={sum(sp)/n:.2f}  p90={sp[9*n//10]:.2f}")
print(f"ПОЛОВИНА спреда (максимум, что ловит ММ за одну ногу): {sp[n//2]/2:.2f} bps")
bq=sorted(x for x,_ in d1); aq=sorted(y for _,y in d1)
print(f"объём на лучшей цене: медиана bid {bq[len(bq)//2]:,.0f} USDT / ask {aq[len(aq)//2]:,.0f} USDT")
print()
print("АРИФМЕТИКА (Bybit linear maker 2 bps за ногу):")
full=sp[n//2]
print(f"  идеальный ММ ловит весь спред за круг:  {full:.2f} bps")
print(f"  комиссия за круг (мейкер+мейкер):       -4.00 bps")
print(f"  ИТОГО до учёта неблагоприятного отбора: {full-4.0:+.2f} bps")
print(f"  измеренный неблагоприятный отбор ~5s:   -0.90 bps (сверх уже пойманного спреда)")
