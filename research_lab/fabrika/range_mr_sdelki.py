#!/usr/bin/env python3
"""Сделки RANGE_MR по 36 клеткам (PREREG_WFO_RANGE_MR_2026_10_17, be60be3). Возобновляемо по монетам."""
import glob, json, sys, time
from pathlib import Path
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv
LAB = Path(__file__).resolve().parents[1]; H = 3_600_000
OUT = LAB / "data/factory_v3/wfo_range_mr"; OUT.mkdir(parents=True, exist_ok=True)
S_MS, E_MS = 1672531200000, 1790812800000
N, ATRN = 48, 14; ZS, KS, HS = (2.0, 2.5), (1.5, 3.0), (6, 12, 24); IZD, FUND8 = 16.0, 1.0


def priznaki(o, h, l, c):
    n = len(c); sma = np.full(n, np.nan); sd = np.full(n, np.nan)
    W = swv(c, N); sma[N - 1:] = W.mean(1); sd[N - 1:] = W.std(1, ddof=1)
    z = (c - sma) / np.where(sd > 0, sd, np.nan)
    dif = np.abs(np.diff(c, prepend=c[0])); er = np.full(n, np.nan)
    er[N:] = np.abs(c[N:] - c[:-N]) / np.maximum(swv(dif[1:], N).sum(1), 1e-12)
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    atr = np.full(n, np.nan); atr[ATRN - 1:] = swv(tr, ATRN).mean(1)
    return sma, z, er, atr


def sdelki(ts, o, h, l, c):
    sma, z, er, atr = priznaki(o, h, l, c); n = len(c); rows = []
    for Z in ZS:
        dl = (z[1:] <= -Z) & (z[:-1] > -Z); ds = (z[1:] >= Z) & (z[:-1] < Z)
        posl = -10
        for i in np.flatnonzero((dl | ds)) + 1:
            if i - posl < 6 or not (er[i] < 0.30) or not np.isfinite(atr[i]) or atr[i] <= 0: continue
            posl = i; s = 1 if dl[i - 1] else -1; e = i + 1
            if e + max(HS) + 1 >= n or ts[e] < S_MS or ts[e] >= E_MS: continue
            if ts[e + max(HS)] - ts[e] != max(HS) * H: continue
            vh = o[e]
            for k in KS:
                risk = k * atr[i]; stop = vh - s * risk
                for Hh in HS:
                    vy, j_out = None, None
                    for j in range(e, e + Hh):
                        if (s > 0 and l[j] <= stop) or (s < 0 and h[j] >= stop):
                            vy = (min(o[j], stop) if s > 0 else max(o[j], stop)); j_out = j; break
                        if (s > 0 and c[j] >= sma[j]) or (s < 0 and c[j] <= sma[j]):
                            vy = o[j + 1]; j_out = j + 1; break
                    if vy is None: j_out = e + Hh - 1; vy = c[j_out]
                    chas = j_out - e + 1
                    R = (s * (vy - vh) - (IZD + FUND8 * chas / 8) / 1e4 * vh) / risk
                    rows.append((int(ts[e]), int(ts[j_out]) + H, s, Z, k, Hh, float(R)))
    return rows


if __name__ == "__main__":
    byudzhet = float(sys.argv[1]) if len(sys.argv) > 1 else 150; t0 = time.time(); sd = 0
    for f in sorted(glob.glob(str(LAB / "data/h1/*.npz"))):
        sym = Path(f).stem
        if sym.endswith("_B21") or (OUT / f"{sym}.npy").exists(): continue
        if time.time() - t0 > byudzhet: break
        zz = np.load(f); ts = zz["ts"].astype(np.int64); x = zz["ohlcv"].astype(float)
        sel = (ts >= S_MS - 30 * 24 * H) & (ts < E_MS + 100 * H); ts, x = ts[sel], x[sel]
        rows = [] if len(ts) < 300 else sdelki(ts, *[x[:, k] for k in range(4)])
        np.save(OUT / f"{sym}.npy", np.array(rows, dtype=float).reshape(-1, 7)); sd += 1
    print(json.dumps(dict(sdelano=sd, gotovo=len(list(OUT.glob("*.npy"))), sekund=round(time.time() - t0))))
