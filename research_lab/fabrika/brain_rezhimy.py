#!/usr/bin/env python3
"""brain_rezhimy.py — общая схема режимных меток Brain для ВСЕХ стратегий и рынков (v1, 18.10.2026).

Одна функция — одни и те же метки для крипты, золота, валют. Метка на баре i считается только по барам ≤ i
(причинность проверяется тестом обрезки). Метки — контекст, не сигнал: стратегия решает сама, Brain только сообщает.
  kanal  : VVERH / VNIZ / FLET / NET — канал регрессии закрытий 72 бара (R² ≥ 0.5, ширина 2–20 %), наклон ±0.05 %/бар
  vol    : NIZK / SRED / VYSOK — ATR20/цена против своих 500 баров (терцили)
  trend  : UP / DOWN — закрытие против EMA200 (для крипты Brain дополнительно даёт рыночный тренд по BTC — тот же расчёт на BTC)
Коды: kanal 0=NET 1=VVERH 2=VNIZ 3=FLET; vol 0=NIZK 1=SRED 2=VYSOK (−1 — не прогрет); trend 1=UP −1=DOWN 0=не прогрет.
"""
from __future__ import annotations
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

KANAL = {0: "NET", 1: "VVERH", 2: "VNIZ", 3: "FLET"}
VOL = {-1: "?", 0: "NIZK", 1: "SRED", 2: "VYSOK"}
TREND = {0: "?", 1: "UP", -1: "DOWN"}


def _ema(x, n):
    k = 2 / (n + 1); out = np.empty(len(x)); e = x[0]
    for i, v in enumerate(x):
        e = v * k + e * (1 - k); out[i] = e
    return out


def _atr(h, l, c, n=20):
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        cs = np.cumsum(np.insert(tr, 0, 0.0)); out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def metki(o, h, l, c):
    n = len(c); LB = 72
    kanal = np.zeros(n, np.int8); vol = np.full(n, -1, np.int8); trend = np.zeros(n, np.int8)
    if n > LB + 1:
        X = np.arange(LB, dtype=float); xm = X.mean(); den = ((X - xm) ** 2).sum()
        W = swv(c, LB)              # окно j = бары j..j+LB-1 → метка на баре j+LB-1 (включая i)
        ym = W.mean(1); m = ((W - ym[:, None]) * (X - xm)).sum(1) / den; b = ym - m * xm
        line = b[:, None] + m[:, None] * X
        Hh = swv(h, LB)[: n - LB + 1]; Ll = swv(l, LB)[: n - LB + 1]
        up = (Hh - line).max(1); lo = (Ll - line).min(1)
        ss_tot = ((W - ym[:, None]) ** 2).sum(1); ss_res = ((W - line) ** 2).sum(1)
        r2 = np.where(ss_tot > 1e-12, 1 - ss_res / np.maximum(ss_tot, 1e-12), 0.0)
        i = np.arange(LB - 1, n)
        width = (up - lo) / np.maximum(c[i], 1e-12); nakl = m / np.maximum(ym, 1e-12)
        ok = (r2 >= 0.5) & (width >= 0.02) & (width <= 0.20)
        k = np.where(~ok, 0, np.where(nakl >= 0.0005, 1, np.where(nakl <= -0.0005, 2, 3)))
        kanal[i] = k
    a = _atr(h, l, c) / np.maximum(c, 1e-12)
    if n > 520:
        Wa = swv(a[19:], 500)                                   # окно до бара включительно
        lo_t = np.nanpercentile(Wa, 33.3, axis=1); hi_t = np.nanpercentile(Wa, 66.7, axis=1)
        idx = np.arange(19 + 499, n)
        cur = a[idx]
        vol[idx] = np.where(cur <= lo_t, 0, np.where(cur >= hi_t, 2, 1))
    e = _ema(c, 200)
    trend[200:] = np.where(c[200:] > e[200:], 1, -1)
    return {"kanal": kanal, "vol": vol, "trend": trend}
