#!/usr/bin/env python3
"""Ложный пробой — измерения M1–M3 (PREREG_LOZHNYY_PROBOY_TEZIS_2026_10_12, коммит 709ecd0). БЕЗ доходностей:
никакая цена после входа (open бара f+1) не читается. Пишет data/lozhnyy_proboy/IZMERENIYA.json.
"""
import glob, json, statistics
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]
DEV13 = {"1000PEPEUSDT", "ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT", "ETHUSDT", "ONDOUSDT", "SOLUSDT", "SUIUSDT",
         "TAOUSDT", "WIFUSDT", "XRPUSDT"}
T0, T1 = 1719792000000, 1782864000000          # 2024-07-01, 2026-07-01 UTC
H = 3_600_000; OKNO, ISKL, BUF, K_PROVAL, PAUZA = 48, 3, 0.10, 3, 24
KOM_BPS, SPRED_BPS = 12.0, 5.0


def atr14(h, l, c):
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1]))); tr = np.r_[h[0] - l[0], tr]
    a = np.full(len(c), np.nan); a[13] = tr[:14].mean()
    for i in range(14, len(c)): a[i] = (a[i - 1] * 13 + tr[i]) / 14
    return a


def sobytiya(ts, o, h, l, c, v):
    a = atr14(h, l, c); out = []; posl = {+1: -10**18, -1: -10**18}
    n = len(c)
    for t in range(OKNO + ISKL + 1, n - K_PROVAL - 1):
        if not (T0 <= ts[t] < T1) or not np.isfinite(a[t]): continue
        if ts[t] - ts[t - OKNO - ISKL] != (OKNO + ISKL) * H: continue          # непрерывность окна
        lo_w, hi_w = l[t - OKNO - ISKL:t - ISKL], h[t - OKNO - ISKL:t - ISKL]
        for st, uroven, proboy in ((+1, hi_w.max(), c[t] > hi_w.max() + BUF * a[t]), (-1, lo_w.min(), c[t] < lo_w.min() - BUF * a[t])):
            if not proboy or ts[t] - posl[st] < PAUZA * H: continue
            f = next((j for j in range(t + 1, t + 1 + K_PROVAL) if (c[j] < uroven if st > 0 else c[j] > uroven)), None)
            if f is None or f + 1 >= n or ts[f + 1] - ts[f] != H: continue
            vhod = o[f + 1]
            stop = (h[t:f + 1].max() + BUF * a[f]) if st > 0 else (l[t:f + 1].min() - BUF * a[f])
            risk = (stop - vhod) if st > 0 else (vhod - stop)
            seredina = (hi_w.max() + lo_w.min()) / 2
            nagrada = (vhod - seredina) if st > 0 else (seredina - vhod)
            med_v = np.median(v[t - 24:t]) if t >= 24 else np.nan
            out.append(dict(storona="verh" if st > 0 else "niz", bar_provala=f - t, vol_ratio=float(v[t] / med_v) if med_v > 0 else None,
                            lev=float(vhod / risk) if risk > 0 else None, rr=float(nagrada / risk) if risk > 0 else None, ts=int(ts[t])))
            posl[st] = ts[f]
    return out


def main():
    vse, po_mon = [], {}
    for f in sorted(glob.glob(str(LAB / "data/h1/*.npz"))):
        s = Path(f).stem
        if s in DEV13: continue
        z = np.load(f); ts = z["ts"].astype(np.int64); x = z["ohlcv"].astype(float)
        if ts[-1] < T0: continue
        ev = sobytiya(ts, x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4])
        mes = max(1.0, (min(ts[-1], T1) - max(ts[0], T0)) / (30.44 * 24 * H))
        po_mon[s] = len(ev) / mes; vse += [dict(e, s=s) for e in ev]
    lev = [e["lev"] for e in vse if e["lev"]]; vr = [e["vol_ratio"] for e in vse if e["vol_ratio"]]; rr = [e["rr"] for e in vse if e["rr"] is not None]
    q = lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))] if xs else None
    rez = dict(monet=len(po_mon), sobytiy=len(vse),
               M1=dict(na_monetu_v_mes_med=round(statistics.median(po_mon.values()), 2), dolya_verh=round(sum(e["storona"] == "verh" for e in vse) / len(vse), 3),
                       bar_provala={k: round(sum(e["bar_provala"] == k for e in vse) / len(vse), 3) for k in (1, 2, 3)}),
               M2=dict(vol_ratio_p25_p50_p75=[round(q(vr, p), 2) for p in (.25, .5, .75)], dolya_ge_1_5=round(sum(x >= 1.5 for x in vr) / len(vr), 3)),
               M3=dict(lev_p50_p90_p99=[round(q(lev, p), 1) for p in (.5, .9, .99)], nevalidno_stop=sum(1 for e in vse if not e["lev"]),
                       dolya_lev_le_100=round(sum(x <= 100 for x in lev) / len(vse), 3),
                       dolya_izderzhki_le_0_25R=round(sum(x * (KOM_BPS + SPRED_BPS) / 1e4 <= 0.25 for x in lev) / len(vse), 3),
                       rr_do_seredina_p25_p50_p75=[round(q(rr, p), 2) for p in (.25, .5, .75)],
                       dolya_rr_le_0=round(sum(x <= 0 for x in rr) / len(vse), 3)))
    d = LAB / "data/lozhnyy_proboy"; d.mkdir(parents=True, exist_ok=True)
    (d / "IZMERENIYA.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(json.dumps(rez, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
