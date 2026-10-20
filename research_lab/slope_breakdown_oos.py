import glob, json, math, datetime as dt
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parent; H = 3600_000; H4 = 4 * H
S0 = int(dt.datetime(2026, 8, 5, tzinfo=dt.timezone.utc).timestamp() * 1000); FEE = 6.0; HOLD = 96; RAZ = 20
rng = np.random.default_rng(31)
def sim(o, h, l, c, i, stop_pct, tp_r):
    e = i + 1; en = o[e]; risk = en * stop_pct; sl = en + risk; tp = en - tp_r * risk
    if e + HOLD > len(c): return None
    for j in range(e, e + HOLD):
        if h[j] >= sl: R = -1.0; break
        if l[j] <= tp: R = tp_r; break
    else: R = (en - c[e + HOLD - 1]) / risk
    return R - 2 * FEE / 1e4 / stop_pct
res = {"A": [], "B": []}
for f in sorted(glob.glob(str(LAB / "data" / "oos_bybit_h1_20261020" / "*.json"))):
    sym = Path(f).stem
    if "_B21" in sym: continue
    b = json.load(open(f))
    if len(b) < 2000: continue
    a = np.array(b, float); ts = a[:, 0].astype(np.int64); o, h, l, c, v = a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
    k = ts // H4; gr = np.flatnonzero(np.r_[True, k[1:] != k[:-1]]); en_ = np.r_[gr[1:], len(ts)]
    Hh = np.array([h[s:e].max() for s, e in zip(gr, en_)]); Hl = np.array([l[s:e].min() for s, e in zip(gr, en_)]); Hc = c[en_ - 1]
    Hv = np.array([v[s:e].sum() for s, e in zip(gr, en_)])
    tr = np.maximum(Hh[1:] - Hl[1:], np.maximum(abs(Hh[1:] - Hc[:-1]), abs(Hl[1:] - Hc[:-1])))
    atr = np.r_[np.nan, np.convolve(tr, np.ones(14) / 14, "full")[:len(tr)]]; atr[:15] = np.nan
    piv = [j for j in range(3, len(gr) - 3) if Hl[j] < Hl[j - 3:j].min() and Hl[j] < Hl[j + 1:j + 4].min()]
    zanyato = -1
    sig = []
    for p1, p2 in zip(piv, piv[1:]):
        if not (6 <= p2 - p1 <= 60) or Hl[p2] <= Hl[p1]: continue
        A = atr[p2 + 3]
        if not A > 0: continue
        slope = (Hl[p2] - Hl[p1]) / (p2 - p1)
        for j in range(p2 + 4, min(len(gr), p2 + 3 + 120)):
            lvl = Hl[p1] + slope * float(k[gr[j]] - k[gr[p1]])
            if (Hc[j] - lvl) / A <= -0.25:
                i = en_[j] - 1                                   # последний H1 внутри H4-бара пробоя
                if ts[i] >= S0:
                    vok = j >= 20 and Hv[j] >= 1.5 * Hv[j - 20:j].mean()
                    sig.append((i, lvl, A, vok))
                break
    for i, lvl, A, vok in sorted(sig):
        if i <= zanyato or i + 1 >= len(c): continue
        en = o[i + 1]; stop = lvl + 0.5 * A
        if stop <= en: continue
        sp = (stop - en) / en; tpr = A / (stop - en)
        R = sim(o, h, l, c, i, sp, tpr)
        if R is None: continue
        zanyato = i + HOLD
        pool = np.flatnonzero(ts >= S0); pool = pool[pool < len(c) - HOLD - 2]
        ctrl = [sim(o, h, l, c, int(rng.choice(pool)), sp, tpr) for _ in range(RAZ)] if len(pool) > 5 else []
        ctrl = [x for x in ctrl if x is not None]
        for var in ("A", "B") if vok else ("A",):
            res[var].append(dict(sym=sym, R=R, ctrl=float(np.mean(ctrl)) if ctrl else None, ts=int(ts[i])))
out = {}
for var, g in res.items():
    g = [x for x in g if x["ctrl"] is not None]
    if len(g) < 3: out[var] = dict(n=len(g)); continue
    R = np.array([x["R"] for x in g]); C = np.array([x["ctrl"] for x in g]); d = R - C
    po = {}
    for x in g: po.setdefault(x["sym"], []).append(x["R"])
    sig = float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d))))
    plus = sum(np.mean(v) > 0 for v in po.values())
    out[var] = dict(n=len(g), sredniy_R=round(float(R.mean()), 4), kontrol=round(float(C.mean()), 4), edzh=round(float(d.mean()), 4),
                    sigma=round(sig, 2), vinreyt=round(float((R > 0).mean()), 3), monet_v_pluse=int(plus), monet=len(po),
                    OOS_PASS=bool(len(g) >= 50 and d.mean() > 0 and sig >= 2.24 and plus * 2 >= len(po)))
(LAB / "results" / "slope_breakdown_oos_20261020.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))
