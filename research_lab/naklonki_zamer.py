import glob, json, math, datetime as dt
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parent; H = 3600_000; H4 = 4 * H
T0 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000); T1 = int(dt.datetime(2026, 8, 4, tzinfo=dt.timezone.utc).timestamp() * 1000)
ev = []
for f in sorted(glob.glob(str(LAB / "data" / "h1" / "*.npz"))):
    if "_B21" in f: continue
    d = np.load(f); ts = d["ts"].astype(np.int64); a = d["ohlcv"].astype(float); o, h, l, c, v = a.T
    if len(ts) < 3000: continue
    k = ts // H4; gr = np.flatnonzero(np.r_[True, k[1:] != k[:-1]]); en = np.r_[gr[1:], len(ts)]
    Hh = np.array([h[s:e].max() for s, e in zip(gr, en)]); Hl = np.array([l[s:e].min() for s, e in zip(gr, en)]); Hc = c[en - 1]
    tr = np.maximum(Hh[1:] - Hl[1:], np.maximum(abs(Hh[1:] - Hc[:-1]), abs(Hl[1:] - Hc[:-1])))
    atr = np.r_[np.nan, np.convolve(tr, np.ones(14) / 14, "full")[:len(tr)]]; atr[:15] = np.nan
    for kind in ("sup", "res"):
        sgn = 1 if kind == "sup" else -1; X = Hl if kind == "sup" else Hh
        piv = [j for j in range(3, len(gr) - 3) if (sgn * (X[j - 3:j].min() if kind == "sup" else -X[j - 3:j].max()) > sgn * X[j] * (1 if kind == "sup" else -1) * 0 + (X[j] if kind == "sup" else -X[j])) ]
        piv = [j for j in range(3, len(gr) - 3) if ((X[j] < X[j-3:j].min() and X[j] < X[j+1:j+4].min()) if kind == "sup" else (X[j] > X[j-3:j].max() and X[j] > X[j+1:j+4].max()))]
        for p1, p2 in zip(piv, piv[1:]):
            if not (6 <= p2 - p1 <= 60): continue
            if sgn * (X[p2] - X[p1]) <= 0: continue                 # поддержка растёт, сопротивление падает
            A = atr[p2 + 3]
            if not A > 0: continue
            slope = (X[p2] - X[p1]) / (p2 - p1)                     # за бар H4
            j0 = p2 + 3
            if ts[gr[j0]] < T0 or ts[gr[j0]] > T1: continue
            ushla = False
            for i in range(gr[j0], min(len(ts) - 97, gr[min(len(gr) - 1, j0 + 120)])):
                jj = (ts[i] // H4) - k[gr[p1]]                        # баров H4 от p1 (по времени)
                lvl = X[p1] + slope * float(jj)
                dist = sgn * (c[i] - lvl) / A
                hb = (i + 1) < len(ts) and (ts[i] // H4 != ts[i + 1] // H4)   # последний H1 внутри H4 → закрытие H4
                if hb and dist <= -0.25:                              # ПРОБОЙ закрытием H4
                    start = -dist                                    # уже прошли за линию (в ATR)
                    ish = "NEYASNO"
                    for q in range(i + 1, i + 97):
                        lv = lvl                                              # доп.1: уровень заморожен в момент события
                        dal = -sgn * ((l[q] if sgn == 1 else h[q]) - lv) / A; nazad = sgn * ((h[q] if sgn == 1 else l[q]) - lv) / A
                        if dal >= start + 1 and nazad >= 0.5: break
                        if dal >= start + 1: ish = "DA"; break
                        if nazad >= 0.5: ish = "NET"; break
                    ev.append(dict(tip="proboy", kind=kind, god=dt.datetime.utcfromtimestamp(ts[i] / 1000).year, ish=ish, p_rw=0.5 / (0.5 + 1 + 0.0) if False else (start + 0.5) / (start + 0.5 + 1)))
                    break
                if dist >= 1: ushla = True
                tch = ushla and (((l[i] - lvl) / A <= 0.1) if sgn == 1 else ((lvl - h[i]) / A <= 0.1)) and dist > -0.5
                if tch:
                    ushla = False; start = dist
                    if not (-0.5 < start < 1): continue
                    ish = "NEYASNO"
                    for q in range(i + 1, i + 97):
                        lv = lvl                                              # доп.1: уровень заморожен в момент события
                        up = sgn * ((h[q] if sgn == 1 else l[q]) - lv) / A; dn = -sgn * ((l[q] if sgn == 1 else h[q]) - lv) / A
                        if up >= 1 and dn >= 0.5: break
                        if up >= 1: ish = "DA"; break
                        if dn >= 0.5: ish = "NET"; break
                    ev.append(dict(tip="kasanie", kind=kind, god=dt.datetime.utcfromtimestamp(ts[i] / 1000).year, ish=ish, p_rw=(start + 0.5) / 1.5))
def d(g):
    r = [e for e in g if e["ish"] != "NEYASNO"]; n = len(r)
    if not n: return dict(n=0)
    p = sum(e["ish"] == "DA" for e in r) / n; e0 = sum(e["p_rw"] for e in r) / n; var = sum(e["p_rw"] * (1 - e["p_rw"]) for e in r) / n
    return dict(n=n, dolya=round(p, 4), etalon=round(e0, 4), izbytok_pp=round((p - e0) * 100, 2), z=round((p - e0) / math.sqrt(var / n), 2))
out = {}
for t in ("kasanie", "proboy"):
    g = [e for e in ev if e["tip"] == t]
    out[t] = dict(vse=d(g), po_storone={kk: d([e for e in g if e["kind"] == kk]) for kk in ("sup", "res")},
                  po_godam={y: d([e for e in g if e["god"] == y]) for y in (2023, 2024, 2025, 2026)})
    x = out[t]["vse"]; out[t]["mehanizm_viden"] = bool(x["n"] and x["izbytok_pp"] >= 5 and x["z"] >= 3 and all(y.get("izbytok_pp", -1) >= 0 for y in out[t]["po_godam"].values() if y.get("n")))
(LAB / "results" / "naklonki_20261020.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))
