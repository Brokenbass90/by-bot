#!/usr/bin/env python3
"""Замер PREREG_PROBOY_30D_ZAMER_2026_10_20."""
import glob, json, math, datetime as dt
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parent
T0 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
T1 = int(dt.datetime(2026, 8, 4, tzinfo=dt.timezone.utc).timestamp() * 1000)
ev = []
for f in sorted(glob.glob(str(LAB / "data" / "h1" / "*.npz"))):
    d = np.load(f); ts = d["ts"].astype(np.int64); a = d["ohlcv"].astype(float); h, l, c, v = a[:, 1], a[:, 2], a[:, 3], a[:, 4]
    n = len(c); cs = np.concatenate([[0.0], np.cumsum(c * v)]); vol24 = np.full(n, np.nan); vol24[23:] = cs[24:] - cs[:-24]
    pauza = -1
    for t in range(744, n - 168):
        if ts[t] < T0 or ts[t] > T1 or t < pauza: continue
        S = h[t - 720:t - 24].max()
        if not (c[t] > S and c[t - 1] <= S): continue
        pauza = t + 72
        up, dn, ish = 1.05 * c[t], 0.95 * c[t], "NEYASNO"
        for j in range(t + 1, t + 169):
            a_, b_ = h[j] >= up, l[j] <= dn
            if a_ and b_: break
            if a_: ish = "VVERH"; break
            if b_: ish = "VNIZ"; break
        hist = vol24[[t - 24 * k for k in range(1, 31)]]
        x = None if np.isnan(hist).any() or np.median(hist) <= 0 else vol24[t] / np.median(hist)
        ev.append(dict(god=dt.datetime.utcfromtimestamp(ts[t] / 1000).year, ish=ish, ob=None if x is None else ("da" if x >= 3 else ("net" if x <= 1.5 else None))))
def d(g):
    r = [e for e in g if e["ish"] != "NEYASNO"]; p = sum(e["ish"] == "VVERH" for e in r) / len(r) if r else None
    return dict(dolya=p, n=len(r), z=(p - 0.5) / math.sqrt(0.25 / len(r)) if r else None)
out = dict(sobytiy=len(ev), vse=d(ev), po_godam={y: d([e for e in ev if e["god"] == y]) for y in (2023, 2024, 2025, 2026)},
           obem_da=d([e for e in ev if e["ob"] == "da"]), obem_net=d([e for e in ev if e["ob"] == "net"]))
v = out["vse"]; out["mehanizm_viden"] = bool(v["dolya"] >= 0.55 and v["z"] >= 3 and all(x["dolya"] is None or x["dolya"] >= 0.5 for x in out["po_godam"].values()))
(LAB / "results" / "proboy_30d_zamer_20261020.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))
