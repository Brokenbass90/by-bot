#!/usr/bin/env python3
"""Сделки ASM1 на часовых барах по 36 клеткам выхода (PREREG_WFO_ASM1_2026_10_17, 0a352ab). Возобновляемо: кэш по монетам.
    python3 research_lab/fabrika/asm1_h1_sdelki.py [секунд_бюджета]"""
import glob, json, sys, time
from pathlib import Path
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv
LAB = Path(__file__).resolve().parents[1]; H = 3_600_000
OUT = LAB / "data/factory_v3/wfo_asm1"; OUT.mkdir(parents=True, exist_ok=True)
S_MS = 1672531200000; E_MS = 1790812800000            # 2023-01-01 … 2026-10-01 (конец окна 2026-09-30)
LB, ATRN, VOLN = 120, 14, 20
KS, HS = (1, 2, 4, 6), (24, 72, 168)
IZD, FUND8 = 16.0, 1.0


def ema(x, n):
    a = 2 / (n + 1); out = np.empty_like(x); e = x[0]
    for j, v in enumerate(x): e = v * a + e * (1 - a); out[j] = e
    return out


def signaly(ts, o, h, l, c, v):
    n = len(c); X = np.arange(LB, dtype=float); xm = X.mean(); den = ((X - xm) ** 2).sum()
    W = swv(c[:-1], LB)                                  # окно j: бары j … j+LB−1, решение на баре i = j+LB
    ym = W.mean(1); m = ((W - ym[:, None]) * (X - xm)).sum(1) / den; b = ym - m * xm
    line = b[:, None] + m[:, None] * X
    up_off = (swv(h[:-1], LB) - line).max(1); lo_off = (swv(l[:-1], LB) - line).min(1)
    ss_tot = ((W - ym[:, None]) ** 2).sum(1); ss_res = ((W - line) ** 2).sum(1)
    r2 = np.where(ss_tot > 1e-12, 1 - ss_res / np.maximum(ss_tot, 1e-12), 1.0)
    i = np.arange(LB, n)                                 # бар решения
    up_i = b + m * LB + up_off; lo_i = b + m * LB + lo_off
    up_p = b + m * (LB - 1) + up_off; lo_p = b + m * (LB - 1) + lo_off
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    atr = np.r_[np.full(ATRN - 1, np.nan), swv(tr, ATRN).mean(1)]
    vavg = np.r_[np.full(VOLN, np.nan), swv(v[:-1], VOLN).mean(1)]   # среднее объёма до бара
    e20, e50 = ema(c, 20), ema(c, 50)
    dif = np.abs(np.diff(c, prepend=c[0])); er = np.full(n, np.nan)
    er[80:] = np.abs(c[80:] - c[:-80]) / np.maximum(swv(dif[1:], 80).sum(1), 1e-12)
    rng = np.maximum(h - l, 1e-12); telo = np.abs(c - o) / rng
    pm = ym; slope_pct = np.abs(m * 24 / pm * 100); width = (up_i - lo_i) / c[i] * 100
    obsh = (r2 >= 0.30) & (width >= 3) & (width <= 25) & (slope_pct >= 0.05) & (slope_pct <= 4) & (telo[i] >= 0.35) \
        & (v[i] >= 1.5 * vavg[i]) & (er[i] >= 0.15) & np.isfinite(atr[i])
    dl = obsh & (c[i - 1] <= up_p) & (c[i] > up_i + 0.15 * atr[i]) & (c[i] > o[i]) & (e20[i] > e50[i])
    ds = obsh & (c[i - 1] >= lo_p) & (c[i] < lo_i - 0.15 * atr[i]) & (c[i] < o[i]) & (e20[i] < e50[i])
    out, posl = [], -10
    for j in np.flatnonzero(dl | ds):
        ib = int(i[j])
        if ib - posl < 6: continue                       # пауза 6 баров на монету
        posl = ib; out.append((ib, 1 if dl[j] else -1, float(atr[ib])))
    return out


def sdelki(ts, o, h, l, c, sig):
    rows = []                                            # (t_vhod, t_vyhod, storona, k, H, R)
    n = len(c)
    for ib, s, a in sig:
        e = ib + 1
        if e + max(HS) > n or ts[e] < S_MS or ts[e] >= E_MS or a <= 0: continue
        if ts[e + max(HS) - 1] - ts[e] != (max(HS) - 1) * H: continue    # дыры в барах — пропуск
        vh = o[e]
        for k in KS:
            risk = k * a; stop = vh - s * risk
            hit = (l[e:e + max(HS)] <= stop) if s > 0 else (h[e:e + max(HS)] >= stop)
            fh = int(np.argmax(hit)) if hit.any() else 10 ** 9
            for Hh in HS:
                if fh < Hh:
                    j = e + fh; px = min(o[j], stop) if s > 0 else max(o[j], stop)
                    if j == e: px = stop if (s > 0 and o[j] > stop) or (s < 0 and o[j] < stop) else px
                    vy, t_out, chas = px, ts[j] + H, fh + 1
                else:
                    vy, t_out, chas = c[e + Hh - 1], ts[e + Hh - 1] + H, Hh
                R = (s * (vy - vh) - (IZD + FUND8 * chas / 8) / 1e4 * vh) / risk
                rows.append((int(ts[e]), int(t_out), s, k, Hh, float(R)))
    return rows


if __name__ == "__main__":
    byudzhet = float(sys.argv[1]) if len(sys.argv) > 1 else 150; t0 = time.time(); sdelano = 0
    for f in sorted(glob.glob(str(LAB / "data/h1/*.npz"))):
        sym = Path(f).stem
        if sym.endswith("_B21"): continue
        p = OUT / f"{sym}.npy"
        if p.exists(): continue
        if time.time() - t0 > byudzhet: break
        z = np.load(f); ts = z["ts"].astype(np.int64); x = z["ohlcv"].astype(float)
        sel = (ts >= S_MS - 200 * 24 * H) & (ts < E_MS + 200 * H); ts, x = ts[sel], x[sel]
        rows = [] if len(ts) < LB + 300 else sdelki(ts, *[x[:, k] for k in range(4)], signaly(ts, *[x[:, k] for k in range(5)]))
        np.save(p, np.array(rows, dtype=float).reshape(-1, 6)); sdelano += 1
    print(json.dumps(dict(sdelano=sdelano, gotovo=len(list(OUT.glob('*.npy'))), sekund=round(time.time() - t0))))
