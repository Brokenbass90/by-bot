#!/usr/bin/env python3
"""Замеры механизма «в игре» (PREREG_INPLAY_MEHANIZM_ZAMERY_2026_10_20). Без доходностей стратегии.
python3 research_lab/inplay_zamery.py → research_lab/results/inplay_zamery_20261020.json"""
import glob, json, math, sys, datetime as dt
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parent
T0 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
BAZA = "--baza" in sys.argv          # диагностическая ветка 1
T1 = int(dt.datetime(2026, 8, 11, 23, tzinfo=dt.timezone.utc).timestamp() * 1000)


def sobytiya(ts, o, h, l, c, v):
    q = c * v; n = len(c)
    cs = np.concatenate([[0.0], np.cumsum(q)])
    vol24 = np.full(n, np.nan); vol24[23:] = cs[24:] - cs[:-24]
    out, pauza = [], -1
    for t in range(24 + 720, n - 96):
        if ts[t] < T0 or ts[t] > T1 or t < pauza:
            continue
        r24 = c[t] / c[t - 24] - 1
        baza = BAZA and (t % 48 == 0)
        if r24 < 0.05 and not baza:
            continue
        hist = vol24[[t - 24 * k for k in range(1, 31)]]
        if np.isnan(hist).any() or np.isnan(vol24[t]):
            continue
        m = float(np.median(hist))
        if m <= 0:
            continue
        x = vol24[t] / m
        klass = "BAZA" if baza else ("V_IGRE" if x >= 3 else ("KONTROL" if x <= 1.5 else None))
        if baza and r24 >= 0.05:
            klass = "BAZA"
        if klass is None:
            continue
        H = float(h[t - 23:t + 1].max()); L = float(l[t - 23:t + 1].min())
        m1 = bool(h[t + 1:t + 49].max() > H)
        m2 = None
        z = H - 0.382 * (H - L)
        hit = np.where(l[t + 1:t + 49] <= z)[0]
        if len(hit) and H > L:
            j0 = t + 1 + int(hit[0])
            m2 = False
            for j in range(j0, t + 97):
                if l[j] < L: break
                if h[j] > H: m2 = True; break
        m3 = None
        S = float(h[t - 720:t - 23].max())
        if H < S <= 1.10 * H:
            seg_h = h[t + 1:t + 97]; seg_c = c[t + 1:t + 97]
            doshel = bool(seg_h.max() >= 0.99 * S)
            m3 = {"doshel": doshel, "proboy": bool(doshel and seg_c.max() > 1.01 * S)}
        out.append(dict(t=int(ts[t]), klass=klass, m1=m1, m2=m2, m3=m3))
        if not baza: pauza = t + 48
    return out


def dolya(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs) if xs else None), len(xs)


def z2(p1, n1, p2, n2):
    if not n1 or not n2: return None
    p = (p1 * n1 + p2 * n2) / (n1 + n2); se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return (p1 - p2) / se if se > 0 else None


def main():
    vse, po_monetam = [], {}
    for f in sorted(glob.glob(str(LAB / "data" / "h1" / "*.npz"))):
        d = np.load(f); ts = d["ts"].astype(np.int64); a = d["ohlcv"].astype(float)
        ev = sobytiya(ts, a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4])
        for e in ev: e["sym"] = Path(f).stem
        vse += ev
    rez = {}
    for k in (("V_IGRE", "KONTROL", "BAZA") if BAZA else ("V_IGRE", "KONTROL")):
        g = [e for e in vse if e["klass"] == k]
        m3d = [e["m3"] for e in g if e["m3"] is not None]
        rez[k] = dict(sobytiy=len(g), monet=len({e["sym"] for e in g}),
                      M1=dolya([e["m1"] for e in g]), M2=dolya([e["m2"] for e in g]),
                      M3_doshli=dolya([x["doshel"] for x in m3d]),
                      M3_proboy_sredi_doshedshih=dolya([x["proboy"] for x in m3d if x["doshel"]]))
    a, b = rez["V_IGRE"], rez["KONTROL"]
    for m in ("M1", "M2"):
        rez[f"{m}_raznica_pp"] = None if a[m][0] is None or b[m][0] is None else round((a[m][0] - b[m][0]) * 100, 2)
        rez[f"{m}_z"] = z2(a[m][0], a[m][1], b[m][0], b[m][1]) if a[m][0] is not None and b[m][0] is not None else None
    ok = all(rez[f"{m}_raznica_pp"] is not None and rez[f"{m}_raznica_pp"] >= 5 and (rez[f"{m}_z"] or 0) >= 2 for m in ("M1", "M2"))
    rez["mehanizm_viden"] = ok
    god = {}
    for e in vse:
        y = dt.datetime.utcfromtimestamp(e["t"] / 1000).year
        g = god.setdefault(f"{y}:{e['klass']}", [])
        g.append(e)
    rez["po_godam"] = {k: dict(n=len(v), M1=dolya([e["m1"] for e in v])[0], M2=dolya([e["m2"] for e in v])[0]) for k, v in sorted(god.items())}
    if BAZA:
        b2 = rez["BAZA"]
        for m in ("M1", "M2"):
            rez[f"{m}_KONTROL_minus_BAZA_pp"] = round((b[m][0] - b2[m][0]) * 100, 2)
            rez[f"{m}_KONTROL_vs_BAZA_z"] = z2(b[m][0], b[m][1], b2[m][0], b2[m][1])
    out = LAB / "results" / ("inplay_zamery_baza_20261020.json" if BAZA else "inplay_zamery_20261020.json"); out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(dict(prereg="PREREG_INPLAY_MEHANIZM_ZAMERY_2026_10_20", rez=rez), ensure_ascii=False, indent=1))
    print(json.dumps(rez, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
