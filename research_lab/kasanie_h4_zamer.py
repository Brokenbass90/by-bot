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
    H4h = np.array([h[s:e].max() for s, e in zip(gr, en)]); H4l = np.array([l[s:e].min() for s, e in zip(gr, en)]); H4c = c[en - 1]
    tr = np.maximum(H4h[1:] - H4l[1:], np.maximum(abs(H4h[1:] - H4c[:-1]), abs(H4l[1:] - H4c[:-1])))
    atr = np.r_[np.nan, np.convolve(tr, np.ones(14) / 14, "full")[:len(tr)]]; atr[:15] = np.nan
    atrp = atr / H4c
    vol20 = np.convolve(v, np.ones(20) / 20, "full")[:len(v)]
    for j in range(3, len(gr) - 3):
        for kind in ("sup", "res"):
            if kind == "sup" and not (H4l[j] < H4l[j - 3:j].min() and H4l[j] < H4l[j + 1:j + 4].min()): continue
            if kind == "res" and not (H4h[j] > H4h[j - 3:j].max() and H4h[j] > H4h[j + 1:j + 4].max()): continue
            A = atr[j + 3]
            if not A > 0: continue
            L = H4l[j] if kind == "sup" else H4h[j]; sgn = 1 if kind == "sup" else -1
            i0 = en[j + 3]
            if ts[min(i0, len(ts) - 1)] < T0 or ts[min(i0, len(ts) - 1)] > T1: continue
            okno = atrp[max(0, j + 3 - 540):j + 4]; spok = atrp[j + 3] < np.nanmedian(okno)
            ushla, nomer, i = False, 0, i0
            while i < min(len(ts) - 97, i0 + 24 * 60):
                dist = sgn * (c[i] - L)
                if dist < -0.5 * A: break                                   # уровень пробит закрытием (H1 как приближение)
                if dist >= A: ushla = True
                kas = (l[i] <= L + 0.1 * A) if sgn == 1 else (h[i] >= L - 0.1 * A)
                if ushla and kas:
                    nomer += 1; ushla = False
                    ish, prokol = "NEYASNO", 0.0
                    for q in range(i, i + 96):
                        mn = (L - l[q]) / A if sgn == 1 else (h[q] - L) / A; mx = (h[q] - L) / A if sgn == 1 else (L - l[q]) / A
                        prokol = max(prokol, mn)
                        if mn >= 0.5 and mx >= 1: break
                        if mn >= 0.5: ish = "PROBOY"; break
                        if mx >= 1: ish = "OTSKOK"; break
                    ev.append(dict(god=dt.datetime.utcfromtimestamp(ts[i] / 1000).year, nomer=min(nomer, 3), kind=kind, spok=bool(spok),
                                   obem=bool(v[i] < vol20[i]), ish=ish, prokol=round(float(prokol), 3)))
                    if ish == "PROBOY": break
                i += 1
def d(g):
    r = [e for e in g if e["ish"] != "NEYASNO"]; n = len(r)
    if not n: return dict(n=0)
    p = sum(e["ish"] == "OTSKOK" for e in r) / n
    return dict(n=n, dolya=round(p, 4), z=round((p - 1 / 3) / math.sqrt((1 / 3) * (2 / 3) / n), 2))
out = {"vse": d(ev), "kasanie": {n: d([e for e in ev if e["nomer"] == n]) for n in (1, 2, 3)}}
k12 = [e for e in ev if e["nomer"] <= 2]
out["k12"] = d(k12); out["k12_po_godam"] = {y: d([e for e in k12 if e["god"] == y]) for y in (2023, 2024, 2025, 2026)}
out["k12_spok"] = {"spokoynye": d([e for e in k12 if e["spok"]]), "volatilnye": d([e for e in k12 if not e["spok"]])}
out["k12_obem"] = {"nizkiy": d([e for e in k12 if e["obem"]]), "vysokiy": d([e for e in k12 if not e["obem"]])}
out["k12_storona"] = {"podderzhka": d([e for e in k12 if e["kind"] == "sup"]), "soprotivlenie": d([e for e in k12 if e["kind"] == "res"])}
ot = [e for e in k12 if e["ish"] == "OTSKOK"]
out["zakol_sredi_otskokov"] = {">0.1ATR": round(sum(e["prokol"] > 0.1 for e in ot) / max(1, len(ot)), 3), ">0.25ATR": round(sum(e["prokol"] > 0.25 for e in ot) / max(1, len(ot)), 3)}
k = out["k12"]; out["mehanizm_viden"] = bool(k["n"] and k["dolya"] >= 1 / 3 + 0.05 and k["z"] >= 3 and all(x.get("dolya", 0) >= 1 / 3 for x in out["k12_po_godam"].values() if x.get("n")))
(LAB / "results" / "kasanie_h4_20261020.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))
