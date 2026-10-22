"""Замеры PREREG_POLY_SPRAVEDLIVAYA_CENA_ZAMERY_2026_10_22. Без доходности стратегии."""
import collections, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, poly_favorit_sutki as P
from statistics import NormalDist
N = NormalDist().cdf; K = "open@ts"; TAU = 1 / 365


def sigma(H, a, T, n):
    ts, o = H[a]; i = np.searchsorted(ts, T)            # бары с ts < T (open@ts → бар открыт до T)
    if i < n + 1: return None
    c = o[i - n - 1:i, 0]                                # open-цены последних n+1 баров до T
    r = np.diff(np.log(c)); return float(r.std(ddof=1) * math.sqrt(8760)) if len(r) == n else None


def cl_t(x, keys):
    x = np.array(x); m = x.mean(); g = collections.defaultdict(float)
    for v, k in zip(x, keys): g[k] += v - m
    se = math.sqrt(sum(v * v for v in g.values())) / len(x); return float(m / se) if se > 0 else None


def main(out):
    H = P.h1(); rows = []
    for z in P.rynki():
        if not 0.05 <= z["p"] <= 0.95: continue
        T = z["konec"] - 86400; S = P.cena_h1(H, z["aktiv"], T, K)
        if S is None: continue
        rec = dict(aktiv=z["aktiv"], p=z["p"], data=z["sobytie"].split("|")[1])
        for n, kl in ((168, "7d"), (720, "30d")):
            s = sigma(H, z["aktiv"], T, n)
            if not s: break
            d2 = (math.log(S / z["X"]) - s * s * TAU / 2) / (s * math.sqrt(TAU)); rec["ps_" + kl] = N(d2)
        else:
            y, _, _ = P.ishod(z, H, K); rec["y"] = y; rows.append(rec)
    res = dict(rynkov=len(rows), dat=len({r["data"] for r in rows}), aktivy=dict(collections.Counter(r["aktiv"] for r in rows)))
    for kl in ("7d", "30d"):
        d = [(r["p"] - r["ps_" + kl]) * 100 for r in rows]; keys = [r["data"] for r in rows]
        blok = dict(sred_c=round(float(np.mean(d)), 2), med_c=round(float(np.median(d)), 2), t_daty=round(cl_t(d, keys), 2))
        for lo, hi in ((0.05, 0.20), (0.20, 0.50), (0.50, 0.80), (0.80, 0.95)):
            ix = [i for i, r in enumerate(rows) if lo <= r["ps_" + kl] < hi]
            if len(ix) > 5:
                blok[f"{lo:.2f}-{hi:.2f}"] = dict(n=len(ix), sred_c=round(float(np.mean([d[i] for i in ix])), 2),
                                                  t_daty=round(cl_t([d[i] for i in ix], [keys[i] for i in ix]) or 0, 2))
        for a in sorted({r["aktiv"] for r in rows}):
            ix = [i for i, r in enumerate(rows) if r["aktiv"] == a]
            blok["aktiv_" + a] = dict(n=len(ix), sred_c=round(float(np.mean([d[i] for i in ix])), 2),
                                      t_daty=round(cl_t([d[i] for i in ix], [keys[i] for i in ix]) or 0, 2))
        res["d_" + kl] = blok
    s = [r for r in rows if r["y"] is not None]
    res["brier"] = dict(n=len(s), polymarket=round(float(np.mean([(r["p"] - r["y"]) ** 2 for r in s])), 4),
                        model_7d=round(float(np.mean([(r["ps_7d"] - r["y"]) ** 2 for r in s])), 4),
                        model_30d=round(float(np.mean([(r["ps_30d"] - r["y"]) ** 2 for r in s])), 4))
    kal = {}
    for lo, hi in ((0.05, 0.20), (0.20, 0.50), (0.50, 0.80), (0.80, 0.95)):
        x = [r for r in s if lo <= r["ps_7d"] < hi]
        if x: kal[f"{lo:.2f}-{hi:.2f}"] = dict(n=len(x), model=round(float(np.mean([r["ps_7d"] for r in x])), 3), fakt=round(float(np.mean([r["y"] for r in x])), 3),
                                              polymarket=round(float(np.mean([r["p"] for r in x])), 3))
    res["kalibrovka_model_7d"] = kal
    def ok(kl):
        b = res["d_" + kl]; zn = [np.sign(b[k]["sred_c"]) for k in b if k[0].isdigit() and abs(b[k]["sred_c"]) >= 2]
        return max(zn.count(1.0), zn.count(-1.0)) >= 2 if zn else False
    res["reshenie"] = "K_PREREG_TENI" if ok("7d") and ok("30d") and res["brier"]["model_7d"] <= res["brier"]["polymarket"] + 0.005 else "NET_PREIMUSHCHESTVA_MODELI"
    Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1)); print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
