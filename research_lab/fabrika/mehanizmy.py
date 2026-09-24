"""mehanizmy.py — библиотека механизмов фабрики.

У каждого механизма ОДИН канонический набор параметров (учебные значения).
Вариаций параметров нет и не будет: новый механизм = новая запись здесь
и новая версия предрегистрации каталога. Хеш этого файла пишется в каждый
вердикт.

Сигнал считается на закрытии бара i только по барам 0..i. Вход — открытие
бара i+1 (это делает прогонщик).
"""
from __future__ import annotations
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv


# ── помощники (все причинные: значение в i зависит только от 0..i) ────
def ema(x, n):
    k = 2 / (n + 1); out = np.empty(len(x)); e = x[0]
    for i, v in enumerate(x):
        e = v * k + e * (1 - k); out[i] = e
    return out


def sma(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x, 0, 0.0)); out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def rstd(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = swv(x, n).std(axis=1)
    return out


def atr(h, l, c, n=20):
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return sma(tr, n), tr


def prev_max(x, n):
    """максимум x[i-n..i-1] (без текущего бара)"""
    out = np.full(len(x), np.nan)
    if len(x) > n:
        out[n:] = swv(x, n).max(axis=1)[:-1]
    return out


def prev_min(x, n):
    out = np.full(len(x), np.nan)
    if len(x) > n:
        out[n:] = swv(x, n).min(axis=1)[:-1]
    return out


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    a = 1 / n; ru = np.empty(len(c)); rd = np.empty(len(c)); u = r = 0.0
    for i in range(len(c)):
        u = a * up[i] + (1 - a) * u; r = a * dn[i] + (1 - a) * r; ru[i] = u; rd[i] = r
    return 100 - 100 / (1 + ru / np.where(rd == 0, 1e-12, rd))


def f(x):
    return np.nan_to_num(x, nan=0.0)


def gt(x, porog):
    """x > porog; где порог ещё не определён (NaN) — всегда False"""
    return x > np.where(np.isnan(porog), np.inf, porog)


def lt(x, porog):
    return x < np.where(np.isnan(porog), -np.inf, porog)


# ── механизмы: fn(o,h,l,c,v) -> (long_bool, short_bool, atr_arr) ───────
def proboy_55(o, h, l, c, v):
    a, _ = atr(h, l, c, 20)
    return gt(c, prev_max(h, 55)), lt(c, prev_min(l, 55)), a


def szhatie_bb(o, h, l, c, v):
    a, _ = atr(h, l, c, 20); m = sma(c, 20); s = rstd(c, 20)
    bw = 4 * s / m
    p10 = np.full(len(c), np.nan)
    if len(c) > 520:
        p10[520:] = np.nanpercentile(swv(bw[19:], 500), 10, axis=1)[:len(c) - 520]
    sq = np.concatenate([[False], ~gt(bw[:-1], p10[:-1]) & ~np.isnan(p10[:-1])])
    return sq & gt(c, m + 2 * s), sq & lt(c, m - 2 * s), a


def otkat_v_trende(o, h, l, c, v):
    a, _ = atr(h, l, c, 20); e50, e200 = ema(c, 50), ema(c, 200); r = rsi(c, 14)
    rp = np.concatenate([[50.0], r[:-1]])
    up = (e50 > e200) & (c > e200); dn = (e50 < e200) & (c < e200)
    ok = np.arange(len(c)) >= 200                          # EMA200 прогрета
    return ok & up & (rp < 35) & (r >= 35), ok & dn & (rp > 65) & (r <= 65), a


def vozvrat_k_sredney(o, h, l, c, v):
    a, _ = atr(h, l, c, 20); z = (c - sma(c, 48)) / rstd(c, 48)
    return lt(z, np.full(len(z), -3.0)) & ~np.isnan(z), gt(z, np.full(len(z), 3.0)), a


def kapitulyaciya(o, h, l, c, v):
    a, tr = atr(h, l, c, 20)
    ap = np.concatenate([[np.nan, np.nan], a[:-2]])       # ATR до большого бара
    big = np.concatenate([[False], gt(tr[:-1], 4 * ap[1:])])
    mid = np.concatenate([[np.nan], (h[:-1] + l[:-1]) / 2])
    dn_prev = np.concatenate([[False], c[:-1] < o[:-1]]); up_prev = np.concatenate([[False], c[:-1] > o[:-1]])
    return big & dn_prev & gt(c, mid), big & up_prev & lt(c, mid), a


def obem_impuls(o, h, l, c, v):
    a, _ = atr(h, l, c, 20)
    med = np.full(len(v), np.nan)
    if len(v) > 48:
        med[48:] = np.median(swv(v, 48), axis=1)[:-1]
    rng = np.where(h - l > 0, h - l, np.nan); pos = (c - l) / rng
    spike = gt(v, 5 * med)
    return spike & (c > o) & (pos > 0.8), spike & (c < o) & (pos < 0.2), a


def momentum_30d(o, h, l, c, v):
    a, _ = atr(h, l, c, 20)
    r720 = np.full(len(c), np.nan); r720[720:] = c[720:] / c[:-720] - 1
    r120 = np.full(len(c), np.nan); r120[120:] = c[120:] / c[:-120] - 1
    pr = np.concatenate([[np.nan], r720[:-1]])
    ok = ~np.isnan(pr) & ~np.isnan(r720) & ~np.isnan(r120)
    return ok & (pr <= 0) & (r720 > 0) & (r120 > 0), ok & (pr >= 0) & (r720 < 0) & (r120 < 0), a


# ── пакет «золото»: механизмы структуры торгового дня, а не формы цены ──
# Предрегистрации: PREREG_ZOLOTO_*_2026_09_24.md. Этим механизмам нужны
# отметки времени баров, поэтому у них в описании стоит nuzhen_ts=True.
def _chas(ts):
    return (ts // 3600000) % 24


def _den(ts):
    return ts // 86400000


def london_proboy(o, h, l, c, v, ts):
    """ЛИКВИДНОСТЬ СЕССИИ. Азия (00:00-07:00 UTC) торгуется тонко и рисует
    узкий диапазон; Лондон приносит объём. Ставка: выход за азиатский
    диапазон в лондонские часы продолжается."""
    a, _ = atr(h, l, c, 20)
    n = len(c); L = np.zeros(n, bool); S = np.zeros(n, bool)
    ch = _chas(ts); dn = _den(ts)
    vrh = np.full(n, np.nan); niz = np.full(n, np.nan)
    tek_d = -1; vh = -np.inf; vl = np.inf
    for i in range(n):
        if dn[i] != tek_d:
            tek_d = dn[i]; vh = -np.inf; vl = np.inf
        if ch[i] < 7:
            vh = max(vh, h[i]); vl = min(vl, l[i])
        elif np.isfinite(vh) and vh > -np.inf and vl < np.inf:
            vrh[i] = vh; niz[i] = vl
    okno = (ch >= 7) & (ch < 12) & np.isfinite(vrh)
    L[okno] = c[okno] > vrh[okno]
    S[okno] = c[okno] < niz[okno]
    return L, S, a


def svip_urovnya(o, h, l, c, v, ts):
    """ОХОТА ЗА СТОПАМИ. Цена выносит вчерашний экстремум и закрывается
    обратно внутри дня. Ставка обратная пробою: пробой был ложным."""
    a, _ = atr(h, l, c, 20)
    n = len(c); dn = _den(ts)
    pdh = np.full(n, np.nan); pdl = np.full(n, np.nan)
    tek_d = dn[0]; vh = -np.inf; vl = np.inf; ph = np.nan; pl = np.nan
    for i in range(n):
        if dn[i] != tek_d:
            ph, pl = vh, vl; tek_d = dn[i]; vh = -np.inf; vl = np.inf
        pdh[i] = ph; pdl[i] = pl
        vh = max(vh, h[i]); vl = min(vl, l[i])
    ok = np.isfinite(pdh) & np.isfinite(pdl)
    S = ok & (h > pdh) & (c < pdh)
    L = ok & (l < pdl) & (c > pdl)
    return L, S, a


def gep_vyhodnyh(o, h, l, c, v, ts):
    """ПЕРЕОЦЕНКА ЗА ВЫХОДНЫЕ. Первый бар после перерыва больше 12 часов
    открывается с разрывом. Ставка: разрыв закрывается, вход против него."""
    a, _ = atr(h, l, c, 20)
    n = len(c); L = np.zeros(n, bool); S = np.zeros(n, bool)
    razryv = np.concatenate([[False], np.diff(ts) > 12 * 3600000])
    for i in np.flatnonzero(razryv):
        if i == 0 or not (a[i - 1] > 0):
            continue
        gep = o[i] - c[i - 1]
        if gep > 0.3 * a[i - 1]:
            S[i] = True
        elif gep < -0.3 * a[i - 1]:
            L[i] = True
    return L, S, a


def nochnoy_dreyf(o, h, l, c, v, ts):
    """ПРЕМИЯ ЗА ВРЕМЯ СУТОК. Безусловный вход в один и тот же час: после
    закрытия Нью-Йорка. Условий по цене нет вовсе — проверяется только
    время. Контроль случайным часом того же месяца отвечает ровно на это."""
    a, _ = atr(h, l, c, 20)
    ch = _chas(ts)
    v21 = ch == 21
    return v21.copy(), v21.copy(), a


# stop — в ATR, rr1/rr2 — цели в R, f1 — доля на первой цели, hold — часов
MEHANIZMY = {
    "PROBOY_55":        dict(fn=proboy_55, semya="breakout", stop=2.0, rr1=2.0, rr2=4.0, f1=0.5, hold=168,
                             opisanie="закрытие выше/ниже экстремума 55 баров (черепахи)"),
    "SZHATIE_BB":       dict(fn=szhatie_bb, semya="volatility_expansion", stop=1.5, rr1=1.5, rr2=3.0, f1=0.5, hold=72,
                             opisanie="ширина Боллинджера в нижних 10% за 500 баров, затем выход за полосу"),
    "OTKAT_V_TRENDE":   dict(fn=otkat_v_trende, semya="trend_pullback", stop=2.0, rr1=1.5, rr2=3.0, f1=0.5, hold=72,
                             opisanie="EMA50>EMA200, RSI14 возвращается выше 35 (зеркально для шорта)"),
    "VOZVRAT_K_SREDNEY": dict(fn=vozvrat_k_sredney, semya="mean_reversion", stop=1.5, rr1=1.0, rr2=2.0, f1=0.5, hold=24,
                             opisanie="отклонение от средней 48 баров больше 3σ — ставка на возврат"),
    "KAPITULYACIYA":    dict(fn=kapitulyaciya, semya="liquidation_reversal", stop=1.5, rr1=1.5, rr2=3.0, f1=0.5, hold=48,
                             opisanie="бар больше 4 ATR, следующий закрывается за его серединой — разворот"),
    "OBEM_IMPULS":      dict(fn=obem_impuls, semya="flow_continuation", stop=1.5, rr1=2.0, rr2=4.0, f1=0.5, hold=48,
                             opisanie="объём больше 5 медиан, закрытие у экстремума бара — продолжение"),
    "MOMENTUM_30D":     dict(fn=momentum_30d, semya="ts_momentum", stop=3.0, rr1=2.0, rr2=5.0, f1=0.5, hold=336,
                             opisanie="доходность 30 дней меняет знак, 5 дней в ту же сторону"),
    # пакет «золото»: структура торгового дня
    "LONDON_PROBOY":    dict(fn=london_proboy, semya="sessiya_proboy", stop=1.5, rr1=1.5, rr2=3.0, f1=0.5, hold=12,
                             nuzhen_ts=True,
                             opisanie="выход за диапазон азиатской сессии в лондонские часы 07-12 UTC"),
    "SVIP_UROVNYA":     dict(fn=svip_urovnya, semya="lozhnyy_proboy", stop=1.0, rr1=1.5, rr2=3.0, f1=0.5, hold=24,
                             nuzhen_ts=True,
                             opisanie="вынос вчерашнего экстремума с закрытием обратно внутрь — ставка против пробоя"),
    "GEP_VYHODNYH":     dict(fn=gep_vyhodnyh, semya="gep_pereocenka", stop=1.5, rr1=1.0, rr2=2.0, f1=0.5, hold=48,
                             nuzhen_ts=True,
                             opisanie="разрыв после перерыва больше 12 часов, вход против разрыва"),
    "NOCHNOY_DREYF":    dict(fn=nochnoy_dreyf, semya="premiya_za_chas", stop=2.0, rr1=1.0, rr2=2.0, f1=0.5, hold=10,
                             nuzhen_ts=True,
                             opisanie="безусловный вход в 21:00 UTC, держать 10 часов — премия за время суток"),
}

# рынки: где лежат данные, издержки на сторону, окна
RYNKI = {
    "crypto137": dict(papka="data/h1", fee_bps=6.0,
                      okna={"O1": (1709251200000, 1759276800000), "O2": (1672531200000, 1709251200000),
                            "O3": (1759276800000, 10**14)}),
    "fx7": dict(papka="data/fx_h1", fee_bps=1.0,
                okna={"O1": (1719792000000, 1759276800000), "O2": (1688169600000, 1719792000000)}),
    "gold": dict(papka="data/zoloto_h1", fee_bps=3.0,
                 okna={"O1": (1719792000000, 1759276800000), "O2": (1687392000000, 1719792000000)}),
}
