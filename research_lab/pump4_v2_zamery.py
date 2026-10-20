#!/usr/bin/env python3
"""Замеры PREREG_PUMP4_V2_TOPLIVO_ZAMERY_2026_10_20. python3 research_lab/pump4_v2_zamery.py"""
import bisect, glob, json, math, datetime as dt
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parent
T0 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
T1 = int(dt.datetime(2026, 8, 4, tzinfo=dt.timezone.utc).timestamp() * 1000)


def zagr(f):
    d = np.load(f); a = d["ohlcv"].astype(float); return d["ts"].astype(np.int64), a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4]


def main():
    bts, _, _, _, bc, _ = zagr(LAB / "data" / "h1" / "BTCUSDT.npz"); bidx = {int(t): i for i, t in enumerate(bts)}
    ev = []
    for f in sorted(glob.glob(str(LAB / "data" / "h1" / "*.npz"))):
        sym = Path(f).stem
        ts, o, h, l, c, v = zagr(f); n = len(c)
        fp = LAB / "data" / "binance_kity" / "funding" / f"{sym}.json"
        fr = json.loads(fp.read_text()) if fp.exists() else []
        frt = [int(x[0]) for x in fr]
        q = c * v; cs = np.concatenate([[0.0], np.cumsum(q)]); vol24 = np.full(n, np.nan); vol24[23:] = cs[24:] - cs[:-24]
        pauza = -1
        for t in range(744, n - 168):
            if ts[t] < T0 or ts[t] > T1 or t < pauza:
                continue
            P = h[t - 23:t + 1].max()
            if c[t] / c[t - 24] - 1 < 0.15 or c[t] < 0.97 * P:
                continue
            pauza = t + 72
            L = l[t - 23:t + 1].min(); cel = P - 0.5 * (P - L); skv = 1.05 * P
            ishod = "NEYASNO"
            for j in range(t + 1, t + 169):
                a_, b_ = l[j] <= cel, h[j] >= skv
                if a_ and b_: ishod = "NEYASNO"; break
                if a_: ishod = "OTKAT"; break
                if b_: ishod = "SKVIZ"; break
            hist = vol24[[t - 24 * k for k in range(1, 31)]]; m = float(np.median(hist)) if not np.isnan(hist).any() else None
            x = vol24[t] / m if m else None
            f1 = None if x is None else ("da" if x >= 3 else ("net" if x <= 1.5 else None))
            bi = bidx.get(int(ts[t])); f2 = None
            if bi is not None and bi >= 168:
                r = bc[bi] / bc[bi - 168] - 1; f2 = "da" if r >= 0.05 else ("net" if r <= 0 else None)
            k = bisect.bisect_right(frt, int(ts[t])) - 1; f3 = None
            if k >= 0 and int(ts[t]) - frt[k] <= 9 * 3600_000:
                s = fr[k][1]; f3 = "da" if s >= 0.0003 else ("net" if s <= 0.0001 else None)
            ev.append(dict(sym=sym, t=int(ts[t]), god=dt.datetime.utcfromtimestamp(ts[t] / 1000).year, ishod=ishod, F1=f1, F2=f2, F3=f3))

    def dolya(g):
        r = [e for e in g if e["ishod"] != "NEYASNO"]
        return (sum(e["ishod"] == "OTKAT" for e in r) / len(r) if r else None), len(r)
    out = dict(sobytiy=len(ev), neyasno=sum(e["ishod"] == "NEYASNO" for e in ev), vse=dolya(ev), filtry={})
    for F in ("F1", "F2", "F3"):
        pa, na = dolya([e for e in ev if e[F] == "da"]); pn, nn = dolya([e for e in ev if e[F] == "net"])
        z = None
        if pa is not None and pn is not None:
            p = (pa * na + pn * nn) / (na + nn); se = math.sqrt(p * (1 - p) * (1 / na + 1 / nn)); z = (pa - pn) / se if se else None
        goda = {}
        for y in (2023, 2024, 2025, 2026):
            a1, _ = dolya([e for e in ev if e[F] == "da" and e["god"] == y]); b1, _ = dolya([e for e in ev if e[F] == "net" and e["god"] == y])
            goda[y] = None if a1 is None or b1 is None else round((a1 - b1) * 100, 1)
        d = None if pa is None or pn is None else (pa - pn) * 100
        znak = [g for g in goda.values() if g is not None and d is not None and (g > 0) == (d > 0)]
        out["filtry"][F] = dict(da=(pa, na), net=(pn, nn), raznica_pp=d, z=z, po_godam_pp=goda,
                                v_V2=bool(d is not None and abs(d) >= 5 and z is not None and abs(z) >= 2 and len(znak) >= 3))
    p = LAB / "results" / "pump4_v2_zamery_20261020.json"; p.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
