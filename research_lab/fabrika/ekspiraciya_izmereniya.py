#!/usr/bin/env python3
"""Измерения PREREG_DERIBIT_EKSPIRACIYA_IZMERENIYA_2026_10_17."""
import calendar, datetime as dt, json
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; H = 3_600_000; UTC = dt.timezone.utc


def posl_pyatnica(g, m):
    d = dt.date(g, m, calendar.monthrange(g, m)[1])
    while d.weekday() != 4: d -= dt.timedelta(days=1)
    return d


def izmerit(fajl, s, e):
    z = np.load(LAB / fajl); ts = z["ts"].astype(np.int64); c = z["ohlcv"][:, 3].astype(float)
    idx = {int(t): i for i, t in enumerate(ts)}; lr = np.r_[np.nan, np.diff(np.log(c))]
    def sd(i, posle):
        a, b = (i, i + 24) if posle else (i - 24, i)
        if a < 1 or b > len(lr) or ts[b - 1] - ts[a] != 23 * H: return None
        return float(np.std(lr[a:b], ddof=1))
    eksp = set(); d = s
    while d < e:
        p = posl_pyatnica(d.year, d.month)
        if s <= p < e: eksp.add(p)
        d = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    def tochka(den): return idx.get(int(dt.datetime.combine(den, dt.time(8), UTC).timestamp() * 1000))
    kontrol_do, kontrol_po = [], []
    d = s
    while d < e:
        if d.weekday() == 4 and d not in eksp:
            i = tochka(d)
            if i is not None:
                a, b = sd(i, False), sd(i, True)
                if a and b: kontrol_do.append(a); kontrol_po.append(b)
        d += dt.timedelta(days=1)
    md, mp = float(np.median(kontrol_do)), float(np.median(kontrol_po))
    M1, M2, posle_bolshe = [], [], []
    for p in sorted(eksp):
        i = tochka(p)
        if i is None: continue
        a, b = sd(i, False), sd(i, True)
        if a and b: M1.append(a / md); M2.append(b / mp); posle_bolshe.append(b > a)
    m1, m2 = float(np.median(M1)), float(np.median(M2))
    return dict(n=len(M1), kontrolnyh=len(kontrol_do), M1_do=round(m1, 3), M2_posle=round(m2, 3), M2_k_M1=round(m2 / m1, 3),
                M3_dolya_posle_bolshe=round(float(np.mean(posle_bolshe)), 3))


rez = {"2021H2_2022": izmerit("data/h1/BTCUSDT_B21.npz", dt.date(2021, 7, 1), dt.date(2023, 1, 1)),
       "2023_2026Q3": izmerit("data/h1/BTCUSDT.npz", dt.date(2023, 1, 1), dt.date(2026, 10, 1))}
rez["verdikt"] = "PASS" if all(r["M2_k_M1"] >= 1.25 and r["M3_dolya_posle_bolshe"] >= 0.65 and r["M1_do"] <= 0.90
                               for r in rez.values()) else "FAIL"
(LAB / "data/factory_v3/EKSPIRACIYA_izmereniya.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
print(json.dumps(rez, ensure_ascii=False))
