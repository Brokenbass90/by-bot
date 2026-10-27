#!/usr/bin/env python3
"""skaner_sobytiy_v1.py — prereg/PREREG_SKANER_SOBYTIY_V1_2026_10_27.md (27.10.2026, Claude). Только чтение данных на диске.
    python3 research_lab/skaner_sobytiy_v1.py → research_lab/results/skaner_sobytiy_v1_<время>.json"""
import collections, glob, hashlib, json, math, sys, time, calendar
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; D = HERE / "data"; H = 3600000
PREREG = HERE / "prereg/PREREG_SKANER_SOBYTIY_V1_2026_10_27.md"; SHA = "038437586713ffb687794c2e8c1efa74af738df26d3885d759e7d78301cc26cd"
T = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d")) * 1000
W1 = (T("2024-01-01"), T("2025-10-01")); W2 = (T("2025-10-01"), T("2026-09-30")); POL = T("2026-04-01")
COST, HOLD, NCTRL = 16.0, 24, 20
SOB = ["E1_OI_RYVOK_VVERH", "E2_OI_SBROS", "E3_FANDING_MINUS", "E4_OBEM_BEZ_HODA", "E5_OBEM_BEZ_HODA_S_OI"]

def oi_ryad(sym):
    f = D / "bybit_oi_h1_full" / f"{sym}.json"
    if not f.exists(): return {}
    return {int(t): float(v) for t, v in json.load(open(f))}

def bary(sym, okno):
    if okno == "W1":
        f = D / "h1" / f"{sym}.npz"
        if not f.exists(): return None, []
        z = np.load(f); ts = z["ts"].astype(np.int64); o = z["ohlcv"].astype(float)
        m = (ts >= W1[0] - 400 * H) & (ts < W1[1] + (HOLD + 2) * H); return np.column_stack([ts[m], o[m]]), []
    f = D / "bybit_fanding_h1_2025_2026" / f"{sym}.json"
    if not f.exists(): return None, []
    x = json.load(open(f)); b = np.array(sorted(x["h1"]), dtype=float)
    return b, sorted((int(t), float(r)) for t, r in x["funding"])

def prohod(sym, okno, rng):
    b, fr = bary(sym, okno)
    if b is None or len(b) < 500: return []
    ts = b[:, 0].astype(np.int64); o, h, l, c, v = (b[:, k] for k in range(1, 6))
    oi = oi_ryad(sym); n = len(ts)
    tr = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1)))); tr[0] = h[0] - l[0]
    atr = np.convolve(tr, np.ones(24) / 24, "full")[:n]; atr[:24] = np.nan
    vmed = np.array([np.median(v[max(0, i - 168):i]) if i >= 168 else np.nan for i in range(n)])
    oi_t = np.array([oi.get(int(t), np.nan) for t in ts]); oi_4 = np.array([oi.get(int(t) - 4 * H, np.nan) for t in ts])
    doi = oi_t / oi_4 - 1
    frt = np.array([t for t, _ in fr], dtype=np.int64); frr = np.array([r for _, r in fr])
    def fund_long(t0, t1):              # long платит положительный фандинг за выплаты в (t0, t1]
        if not len(frt): return 0.0
        a, z = np.searchsorted(frt, t0, "right"), np.searchsorted(frt, t1, "right"); return -float(frr[a:z].sum()) * 1e4
    def posl_fand(t):                   # последняя выплата не позже закрытия бара t
        if not len(frt): return np.nan
        k = np.searchsorted(frt, t + H, "right") - 1; return frr[k] if k >= 0 else np.nan
    absmove = abs(c - o)
    usl = {"E1_OI_RYVOK_VVERH": doi >= 0.15, "E2_OI_SBROS": doi <= -0.15,
           "E3_FANDING_MINUS": np.array([(posl_fand(int(t)) <= -0.0005) if okno == "W2" else False for t in ts]),
           "E4_OBEM_BEZ_HODA": (v >= 5 * vmed) & (absmove <= 0.5 * atr),
           "E5_OBEM_BEZ_HODA_S_OI": (v >= 5 * vmed) & (absmove <= 0.5 * atr) & (doi >= 0.05)}
    a0, a1 = W1 if okno == "W1" else W2
    def dohod(i):                        # вход open(i+1), выход close(i+HOLD)
        if i + HOLD >= n or ts[i + HOLD] - ts[i + 1] != (HOLD - 1) * H: return None
        r = (c[i + HOLD] / o[i + 1] - 1) * 1e4; f = fund_long(int(ts[i + 1]), int(ts[i + HOLD]) + H)
        return r, f
    mes = collections.defaultdict(list)
    for i in range(n):
        if a0 <= ts[i] < a1: mes[time.gmtime(ts[i] / 1000)[:2]].append(i)
    out = []
    for e, m in usl.items():
        posl = -10 ** 9
        for i in np.flatnonzero(m):
            if not (a0 <= ts[i] < a1) or i - posl < HOLD: continue
            d = dohod(i)
            if d is None: continue
            posl = i
            pool = mes[time.gmtime(ts[i] / 1000)[:2]]
            cc = [dohod(int(j)) for j in rng.choice(pool, size=min(NCTRL, len(pool)), replace=False)] if pool else []
            cc = [x for x in cc if x is not None]
            if not cc: continue
            cr, cf = np.mean([x[0] for x in cc]), np.mean([x[1] for x in cc])
            out.append(dict(sob=e, okno=okno, sym=sym, ts=int(ts[i]), r=round(d[0], 2), f=round(d[1], 2), cr=round(float(cr), 2), cf=round(float(cf), 2)))
    return out

def svod(g, storona):
    if len(g) < 3: return dict(n=len(g))
    s = 1 if storona == "long" else -1
    net = np.array([s * x["r"] - COST + (x["f"] if s == 1 else -x["f"]) for x in g])
    ctrl = np.array([s * x["cr"] - COST + (x["cf"] if s == 1 else -x["cf"]) for x in g])
    ex = net - ctrl; dni = collections.defaultdict(list)
    for x, e in zip(g, ex): dni[x["ts"] // 86400000].append(e)
    a = np.array([np.mean(z) for z in dni.values()])
    t = float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))) if len(a) > 2 and a.std(ddof=1) > 0 else 0.0
    return dict(n=len(g), dney=len(a), net_bps=round(float(net.mean()), 1), kontrol_bps=round(float(ctrl.mean()), 1),
                prevyshenie_bps=round(float(ex.mean()), 1), t_dni=round(t, 2), monet=len({x["sym"] for x in g}))

def main():
    if hashlib.sha256(PREREG.read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    syms = sorted(Path(f).stem for f in glob.glob(str(D / "bybit_oi_h1_full" / "*.json")))
    rng = np.random.default_rng(20261027); vse = []
    for k, s in enumerate(syms, 1):
        for okno in ("W1", "W2"): vse += prohod(s, okno, rng)
        if k % 20 == 0: print(k, len(syms), len(vse), flush=True)
    tab = {}
    for e in SOB:
        for st in ("long", "short"):
            g1 = [x for x in vse if x["sob"] == e and x["okno"] == "W1"]; g2 = [x for x in vse if x["sob"] == e and x["okno"] == "W2"]
            tab[f"{e}|{st}"] = dict(W1=svod(g1, st), W2=svod(g2, st), W2_do=svod([x for x in g2 if x["ts"] < POL], st), W2_posle=svod([x for x in g2 if x["ts"] >= POL], st))
    prosh = []
    for k, v in tab.items():
        w1, w2 = v["W1"], v["W2"]
        if k.startswith("E3"):
            a, b = v["W2_do"], v["W2_posle"]
            ok = w2.get("n", 0) and abs(w2.get("t_dni", 0)) >= 3.0 and w2["t_dni"] > 0 and w2["net_bps"] > 0 and w2["dney"] >= 30 \
                 and a.get("prevyshenie_bps", 0) > 0 and b.get("prevyshenie_bps", 0) > 0
        else:
            ok = w1.get("n", 0) and w2.get("n", 0) and w1.get("t_dni", 0) >= 3.0 and w2.get("t_dni", 0) >= 2.0 and w1["net_bps"] > 0 \
                 and w2["net_bps"] > 0 and w1["dney"] >= 30 and w2["dney"] >= 30
        if ok: prosh.append((w2["net_bps"], k))
    kand = max(prosh)[1] if prosh else None
    out = dict(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), monet=len(syms), sobytiy=len(vse), tablica=tab,
               proshli=[k for _, k in sorted(prosh, reverse=True)], kandidat=kand, itog="CANDIDATE" if kand else "NONE",
               prereg_sha256=SHA, kod_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               primechanie="W1 без фандинга (данных нет) — только цена; W2 с фактическим фандингом Bybit")
    f = HERE / "results" / time.strftime("skaner_sobytiy_v1_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(dict(svod=out, sobytiya=vse), ensure_ascii=False)); print(json.dumps(out, ensure_ascii=False, indent=1)); print("файл:", f)

if __name__ == "__main__": main()
