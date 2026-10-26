"""PREREG_SESSII_BTC_ETH_2026_10_26. python3 research_lab/sessii_btc_eth.py <binance_h1_dir> <out.json>"""
import collections, datetime as dt, json, math, sys
from pathlib import Path
D, OUT = Path(sys.argv[1]), Path(sys.argv[2])
BL = {"A": (0, 8), "E": (8, 14), "U": (14, 21), "N": (21, 24)}
DEV, HO = (dt.date(2021, 4, 1), dt.date(2023, 12, 31)), (dt.date(2024, 1, 1), dt.date(2026, 9, 30))
COST = 16e-4
def load(s):
    r = json.load(open(D / f"{s}.json")); return {x[0]: (x[1], x[2]) for x in r}
P = {s: load(s) for s in ("BTCUSDT", "ETHUSDT")}
def blok_dohod(den, b):
    h0, h1 = BL[b]; t0 = int(dt.datetime(den.year, den.month, den.day, h0, tzinfo=dt.timezone.utc).timestamp() * 1000)
    out = []
    for s in P:
        o = P[s].get(t0); c = P[s].get(t0 + (h1 - h0 - 1) * 3600_000)
        if o is None or c is None: return None
        out.append(c[1] / o[0] - 1)
    return sum(out) / 2
def stat(x):
    n = len(x); m = sum(x) / n; sd = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1)); return {"n": n, "sred_bps": round(m * 1e4, 2), "t": round(m / (sd / math.sqrt(n)), 2)}
def dni(a, b):
    d = a
    while d <= b: yield d; d += dt.timedelta(days=1)
out = {"dev": {}, "chasy_dev_bps": {}}
for b in BL:
    x = [v for d in dni(*DEV) if (v := blok_dohod(d, b)) is not None]; out["dev"][b] = stat(x)
for h in range(24):
    x = []
    for d in dni(*DEV):
        t0 = int(dt.datetime(d.year, d.month, d.day, h, tzinfo=dt.timezone.utc).timestamp() * 1000)
        v = [P[s][t0][1] / P[s][t0][0] - 1 for s in P if t0 in P[s]]
        if len(v) == 2: x.append(sum(v) / 2)
    out["chasy_dev_bps"][h] = stat(x)
best = max(BL, key=lambda b: abs(out["dev"][b]["t"])); znak = 1 if out["dev"][best]["sred_bps"] > 0 else -1
out["vybor"] = {"blok": best, "napravlenie": "long" if znak > 0 else "short"}
ho = [(d, znak * v - COST, znak * v) for d in dni(*HO) if (v := blok_dohod(d, best)) is not None]
out["holdout_net"] = stat([x[1] for x in ho]); out["holdout_gross"] = stat([x[2] for x in ho])
out["holdout_vse_bloki_gross_bps"] = {b: stat([v for d in dni(*HO) if (v := blok_dohod(d, b)) is not None]) for b in BL}
pg = collections.defaultdict(list)
for d, n, g in ho: pg[d.year].append(n)
out["po_godam_net_%"] = {y: round((math.prod(1 + v for v in xs) - 1) * 100, 1) for y, xs in pg.items()}
h = out["holdout_net"]; out["verdikt"] = "PASS" if h["sred_bps"] > 0 and h["t"] >= 2 else "FAIL"
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in out.items() if k != "chasy_dev_bps"}, ensure_ascii=False, indent=1))
print("часы DEV (bps, t):", {h: (v["sred_bps"], v["t"]) for h, v in out["chasy_dev_bps"].items()})
