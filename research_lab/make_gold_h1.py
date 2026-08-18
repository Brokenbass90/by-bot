#!/usr/bin/env python3
"""make_gold_h1.py — золото из пятиминуток в часовые .npz, как у альтов.

Машина исследований умеет читать только папку с .npz (ts, ohlcv).
Золото лежит пятиминутным CSV. Склеиваем в часы и кладём рядом.

Важно: у золота есть выходные и перерывы сессий. Часы, где меньше
трёх пятиминуток, выбрасываются — иначе разрывы дадут ложные пробои.
"""
import csv, sys
from pathlib import Path
import numpy as np

SRC = Path("research_lab/data/xauusd_m5_preholdout_20240708_20250930_v2/XAUUSD_M5.csv")
OUT = Path("research_lab/data/gold_h1"); OUT.mkdir(parents=True, exist_ok=True)

rows = []
with SRC.open() as f:
    rd = csv.reader(f)
    head = next(rd)
    print("колонки:", head)
    ix = {c.lower().strip(): i for i, c in enumerate(head)}
    def col(*names):
        for n in names:
            if n in ix: return ix[n]
        return None
    it, io, ih, il, ic, iv = (col("ts","timestamp","time","datetime","date"),
                             col("open","o"), col("high","h"), col("low","l"),
                             col("close","c"), col("volume","v","vol"))
    for r in rd:
        if not r or len(r) <= max(x for x in (it,io,ih,il,ic) if x is not None):
            continue
        t = r[it]
        try:
            tms = int(float(t))
            if tms < 10**12: tms *= 1000
        except ValueError:
            import datetime as dt
            tms = int(dt.datetime.fromisoformat(t.replace("Z","+00:00")).timestamp()*1000)
        rows.append((tms, float(r[io]), float(r[ih]), float(r[il]), float(r[ic]),
                     float(r[iv]) if iv is not None and r[iv] else 0.0))
rows.sort()
print(f"пятиминуток: {len(rows)}")

buck = {}
for t,o,h,l,c,v in rows:
    k = t // 3600000
    b = buck.setdefault(k, [t,o,h,l,c,v,0])
    b[2] = max(b[2], h); b[3] = min(b[3], l); b[4] = c; b[5] += v; b[6] += 1
keys = sorted(k for k,b in buck.items() if b[6] >= 3)
ts = np.array([k*3600000 for k in keys], dtype=np.int64)
oh = np.array([[buck[k][1],buck[k][2],buck[k][3],buck[k][4],buck[k][5]] for k in keys], dtype=np.float64)
np.savez(OUT/"XAUUSD.npz", ts=ts, ohlcv=oh)
print(f"часов сохранено: {len(ts)}  ({len(buck)-len(keys)} неполных выброшено)")
print(f"период: {ts[0]} .. {ts[-1]}")
