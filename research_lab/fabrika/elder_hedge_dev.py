#!/usr/bin/env python3
"""elder_hedge_dev.py — единственный прогон PREREG_ELDER_CRASH_HEDGE_2026_10_15.md. Пишет data/elder_hist_dev/HEDGE_ITOG.json."""
import bisect, datetime as dt, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB)); sys.path.insert(0, str(LAB / "factory_v3"))
OUT = LAB / "data" / "elder_hist_dev" / "HEDGE_ITOG.json"
H = 3_600_000; DEN = 86_400_000
D0, D1 = dt.date(2023, 1, 5), dt.date(2026, 8, 6)


def ms(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def kity_nedeli(nedeli):
    import ferma_shablony as F
    D = F._dannye(); K, M = D["K"], D["M"]; pr = F._priznak("m3_perp", D); out = {}
    for d in nedeli:
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        rows = []
        for _, s in oi:
            x = M[s]; i = int(np.searchsorted(x["ts"], ms(d)))
            if i >= len(x["ts"]) or x["ts"][i] != ms(d) or i < 60: continue
            v = pr(s, vch)
            if v is not None and np.isfinite(v): rows.append((v, s, i))
        if len(rows) < 30: continue
        rows.sort(); k = len(rows) // 10
        leg = [K.sdelka(M[s], i, 7, -1) for _, s, i in rows[:k]] + [K.sdelka(M[s], i, 7, +1) for _, s, i in rows[-k:]]
        leg = [r for r in leg if r is not None]
        if leg: out[d] = float(np.mean(leg))
    return out


def spy_nedeli(nedeli):
    b = json.loads((LAB / "data" / "etf_d1" / "SPY.json").read_text())["bary"]; dni = [x[0] for x in b]; c = [float(x[1]) for x in b]
    def cena(d):
        j = bisect.bisect_right(dni, d.isoformat()) - 1
        return c[j] if j >= 0 else None
    return {d: cena(d + dt.timedelta(days=7)) / cena(d) - 1 for d in nedeli if cena(d) and cena(d + dt.timedelta(days=7))}


def elder_nedeli(nedeli):
    out = {d: 0.0 for d in nedeli}; starts = [ms(d) for d in nedeli]
    for l in open(LAB / "data" / "elder_hist_dev" / "sdelki.jsonl"):
        x = json.loads(l)
        if not x.get("ispolnen") or x.get("nezaversheno"): continue
        t = x["ts"] + (1 + x["bar_CONTROL"]) * H; j = bisect.bisect_right(starts, t) - 1
        if 0 <= j and t < starts[j] + 7 * DEN: out[nedeli[j]] += x["R_CONTROL"]
    return out


def mdd(x):
    k = np.cumsum(x); p = np.maximum.accumulate(np.concatenate([[0.0], k]))[1:]; return float((p - k).max())


def metr(x):
    x = np.asarray(x); dd = mdd(x); hv = np.sort(x)[:max(1, int(np.ceil(0.05 * len(x))))]; vn = x[x < 0]
    k = np.cumsum(x); p = np.maximum.accumulate(np.concatenate([[0.0], k]))[1:]; pod, tek = 0, 0
    for v in p - k: tek = tek + 1 if v > 1e-12 else 0; pod = max(pod, tek)
    return dict(net=float(x.sum()), maxdd=dd, cvar95=float(hv.mean()), calmar=float(x.mean() * 52 / dd) if dd > 0 else None,
                sortino=float(x.mean() / np.sqrt(np.mean(vn ** 2)) * np.sqrt(52)) if len(vn) else None, nedel_pod_vodoy=int(pod))


def main():
    if OUT.exists(): sys.exit("HEDGE_ITOG.json уже есть — прогон один")
    import kity_sudya as K
    nedeli = [d for d in K.SETKA if D0 <= d <= D1]
    ky, sp, el = kity_nedeli(nedeli), spy_nedeli(nedeli), elder_nedeli(nedeli)
    obshchie = [d for d in nedeli if d in ky and d in sp]
    k, s, e = (np.array([z[d] for d in obshchie]) for z in (ky, sp, el))
    k, s, e = k / k.std() * 0.01, s / s.std() * 0.01, e / e.std() * 0.01
    B = (k + s) / 2; T = (k + s + e) / 3; B = B / B.std() * 0.01; T = T / T.std() * 0.01
    hudshie = B <= np.quantile(B, 0.10); pol = len(B) // 2
    rng = np.random.default_rng(20261015); n = len(B); blok = 8; pobed = 0
    for _ in range(2000):
        idx = np.concatenate([np.arange(st, st + blok) % n for st in rng.integers(0, n, size=int(np.ceil(n / blok)))])[:n]
        pobed += mdd(T[idx]) < mdd(B[idx])
    mB, mT = metr(B), metr(T)
    u = {"1_corr_elder_B<0": float(np.corrcoef(e, B)[0, 1]) < 0, "2_elder_v_hudshih_nedelyah_B>0": float(e[hudshie].mean()) > 0,
         "3_maxdd_T<B": mT["maxdd"] < mB["maxdd"], "4_cvar95_T>B": mT["cvar95"] > mB["cvar95"],
         "5_calmar_T>B_i_maxdd_v_polovinah": (mT["calmar"] or -9) > (mB["calmar"] or -9) and mdd(T[:pol]) <= mdd(B[:pol]) and mdd(T[pol:]) <= mdd(B[pol:]),
         "6_bootstrap_maxdd_T<B>=0.80": pobed / 2000 >= 0.80}
    itog = dict(prereg="PREREG_ELDER_CRASH_HEDGE_2026_10_15.md", nedel=len(obshchie), s=str(obshchie[0]), po=str(obshchie[-1]),
                corr_elder_B=float(np.corrcoef(e, B)[0, 1]), corr_elder_kity=float(np.corrcoef(e, k)[0, 1]), corr_elder_spy=float(np.corrcoef(e, s)[0, 1]),
                elder_v_hudshih_nedelyah_B=float(e[hudshie].mean()), B=mB, T=mT,
                polovinki_maxdd=dict(B=[mdd(B[:pol]), mdd(B[pol:])], T=[mdd(T[:pol]), mdd(T[pol:])]), bootstrap_dolya=pobed / 2000,
                uslovia=u, VERDIKT="ELDER_CRASH_HEDGE_DEV_PASS" if all(u.values()) else "ELDER_CRASH_HEDGE_DEV_KILL")
    OUT.write_text(json.dumps(itog, ensure_ascii=False, indent=1)); print(json.dumps(itog, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
