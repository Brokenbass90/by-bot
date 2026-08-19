#!/usr/bin/env python3
"""
eld_v1.py — Элдер, «три экрана», собранный заново и проверенный честно.

ЗАЧЕМ ЗАНОВО. Элдера в проекте отвергли по замеру, где стоп мерился
в ATR пятиминутного бара при удержании сутки. Это давало винрейт
20-30% и отказ. С исправленным масштабом стопа винрейты у других ног
поднялись до 41-57%, значит отказ был сделан на сломанном замере.
Здесь классические правила Элдера собраны с нуля и прогоняются через
ту же машинку, что MPL: три руки, недельный блочный бутстрап,
критерии объявлены заранее.

ТРИ ЭКРАНА, как у автора, переведённые на наши данные:
  ПРИЛИВ   старший таймфрейм — дневной EMA13 растёт
           (то есть мы вообще смотрим только вверх)
  ВОЛНА    средний — Force Index за 2 дня отрицателен
           (то есть внутри роста сейчас откат; покупаем слабость)
  РЯБЬ     младший — часовой бар пробил максимум предыдущего часа
           (то есть откат кончился)

ОТЛИЧИЕ ОТ MPL. У MPL откат меряется геометрией (30-60% импульса)
и цель стоит на уровне. У Элдера откат меряется осциллятором, а цели
нет вообще — выход по времени или по стопу. Сравнение двух подходов
на одних данных и есть смысл этого прогона.

Правила объявлены ДО прогона и не подбираются.
Данные обрезаны 2025-09-30, запечатанный период не читается.
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

DIR = sys.argv[1] if len(sys.argv) > 1 else "h1/h1"
CUTOFF_MS = 1759190400000
DAY = 24

EMA_TIDE_D = 13          # дневная EMA прилива
FORCE_D = 2              # Force Index за 2 дня
# СТОП МАСШТАБИРУЕТСЯ ПОД ГОРИЗОНТ. ATR здесь — средний часовой ход.
# При удержании 24 часа цена успевает пройти примерно ATR*sqrt(24),
# поэтому стоп в один часовой ATR выбивает почти сразу. Это ровно тот
# дефект, из-за которого элдера отвергли в прошлый раз; повторять его
# нельзя. Ставим стоп в единицах суточной волатильности.
STOP_ATR = 1.0           # в единицах ATR*sqrt(часы удержания)
HOLD_H = 24
EXTEND_H = 24
CAP_H = 168
EMA_HOURS = 24
FEE_BPS = 6.0
SLIP_TIERS = ((100e6, 2.0), (20e6, 4.0), (0.0, 8.0))
FUND_PER_8H = 1.0
TIME_EXIT_SLIP = 2.0
TURN = {}


def atr(h, l, c, n=24):
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(tr), np.nan)
    if len(tr) > n:
        k = np.convolve(tr, np.ones(n) / n, mode="full")[: len(tr)]
        out[n:] = k[n:]
    return out


def ema(x, n):
    k = 2 / (n + 1); e = x[0]; out = np.empty(len(x))
    for i in range(len(x)):
        e = x[i] * k + e * (1 - k); out[i] = e
    return out


def load():
    data = {}
    for fp in sorted(glob.glob(os.path.join(DIR, "*.npz"))):
        s = os.path.basename(fp)[:-4]
        d = np.load(fp); ts, o = d["ts"], d["ohlcv"].astype(np.float64)
        m = ts <= CUTOFF_MS
        if m.sum() < 24 * 400:
            continue
        data[s] = dict(ts=ts[m], o=o[m, 0], h=o[m, 1], l=o[m, 2], c=o[m, 3], v=o[m, 4])
    return data


def prepare(d):
    c, h, l, v = d["c"], d["h"], d["l"], d["v"]
    d["atr"] = atr(h, l, c)
    n = len(c)
    # дневные закрытия и объёмы: берём каждый 24-й час, без заглядывания
    dc = c[::DAY]; dv = np.array([v[i:i + DAY].sum() for i in range(0, n, DAY)])
    tide = ema(dc, EMA_TIDE_D)
    tide_up = np.concatenate([[False], tide[1:] > tide[:-1]])
    # Force Index = (изменение дневного закрытия) * дневной объём, EMA(2)
    fi_raw = np.concatenate([[0.0], np.diff(dc)]) * dv
    fi = ema(fi_raw, FORCE_D)
    # разворачиваем дневное обратно в часы со сдвигом на сутки:
    # день k известен только начиная с часа (k+1)*24
    up = np.zeros(n, bool); force = np.full(n, np.nan)
    for k in range(len(dc)):
        a, b = (k + 1) * DAY, min((k + 2) * DAY, n)
        if a >= n:
            break
        up[a:b] = tide_up[k]; force[a:b] = fi[k]
    d["tide_up"] = up; d["force"] = force
    d["ema_h"] = ema(c, EMA_HOURS)
    return d


def signals(d):
    c, h = d["c"], d["h"]
    out = []
    i = DAY * (EMA_TIDE_D + 5)
    n = len(c)
    while i < n - CAP_H - 1:
        a = d["atr"][i]
        if not (np.isfinite(a) and a > 0 and np.isfinite(d["force"][i])):
            i += 1; continue
        if not d["tide_up"][i]:            # экран 1: прилив вверх
            i += 1; continue
        if d["force"][i] >= 0:             # экран 2: сейчас откат
            i += 1; continue
        if not (c[i] > h[i - 1]):           # экран 3: откат кончился
            i += 1; continue
        # ИСПОЛНИМЫЙ ВХОД: сигнал подтверждён закрытием бара i, значит
        # купить можно не раньше открытия бара i+1. Дефект «вход по тому
        # же закрытию» найден Codex в MPL и XSEC; здесь его нет с самого
        # начала.
        e_i = i + 1
        scale = a * (HOLD_H ** 0.5)
        entry = float(d["o"][e_i]); stop = entry - STOP_ATR * scale
        out.append((int(d["ts"][e_i]), e_i, entry, stop, a))
        i += HOLD_H
    return out


def simulate(d, sig, sym, short=False):
    h, l, c, v = d["h"], d["l"], d["c"], d["v"]
    res = []
    nxt = -1
    for ts, i, entry, stop, a in sig:
        if i < nxt:                      # без наложения сделок
            continue
        risk = entry - stop
        if risk <= 0:
            continue
        # ликвидность берётся ТОЛЬКО из прошлого: оборот за 24 часа до входа
        t_lo = max(0, i - 24)
        trailing = float(np.sum(c[t_lo:i] * v[t_lo:i]))
        slip = next(x for t, x in SLIP_TIERS if trailing >= t)
        rt = 2 * (FEE_BPS + slip)
        s_stop = entry + risk if short else stop
        limit = HOLD_H
        exitp, jend = None, i + limit
        j = i + 1
        while j < min(i + 1 + limit, len(h)):
            if (h[j] >= s_stop) if short else (l[j] <= s_stop):
                exitp, jend = s_stop, j; break
            if j == i + limit and limit < CAP_H:
                ok = (c[j] < entry and c[j] < d["ema_h"][j]) if short else \
                     (c[j] > entry and c[j] > d["ema_h"][j])
                if ok:
                    limit = min(CAP_H, limit + EXTEND_H)
            j += 1
        extra = 0.0
        if exitp is None:
            jend = min(i + limit, len(h) - 1); exitp = c[jend]; extra = TIME_EXIT_SLIP
        hours = jend - i
        cost = entry * (rt + extra + FUND_PER_8H * hours / 8) / 1e4
        pnl = (entry - exitp - cost) if short else (exitp - entry - cost)
        nxt = jend + 1
        res.append(dict(ts=ts, R=float(pnl / risk), hours=hours, slip=slip,
                        why="stop" if exitp == s_stop else "time"))
    return res


def week_boot(R, ts, n=2000, seed=5):
    wk = (np.array(ts) // (7 * 86400_000)).astype(np.int64)
    ub = np.unique(wk)
    if len(ub) < 4:
        return float("nan"), float("nan")
    idx = {b: np.flatnonzero(wk == b) for b in ub}
    rng = np.random.default_rng(seed); out = np.empty(n)
    for i in range(n):
        pick = rng.choice(ub, len(ub), replace=True)
        out[i] = R[np.concatenate([idx[b] for b in pick])].mean()
    return float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))


def rep(tag, res):
    R = np.array([r["R"] for r in res]); ts = np.array([r["ts"] for r in res])
    lo, hi = week_boot(R, ts)
    print(f"{tag:<26} n={len(R):>5}  R {R.mean():+.4f} [{lo:+.3f}..{hi:+.3f}]  "
          f"винрейт {(R>0).mean():.1%}  часов {np.mean([r['hours'] for r in res]):.0f}")
    return float(R.mean())


def main():
    global TURN
    data = load(); syms = sorted(data)
    TURN = {s: float(np.median(data[s]["c"] * data[s]["v"])) * 24 for s in syms}  # только для отчёта
    for s in syms:
        prepare(data[s])
    allsig = {s: signals(data[s]) for s in syms}
    tot = sum(len(v) for v in allsig.values())
    print(f"символов {len(syms)}, сигналов {tot:,} за 2.75 года "
          f"({tot/33:.0f} в месяц на портфель)\n")
    if tot < 100:
        print("сигналов слишком мало"); return

    rng = np.random.default_rng(3)
    L, S, C = [], [], []
    for s in syms:
        sig = allsig[s]
        if not sig:
            continue
        L += simulate(data[s], sig, s)
        S += simulate(data[s], sig, s, short=True)
        n = len(data[s]["c"]); fake = []
        for ts, i, e, st, a in sig:
            j = int(rng.integers(DAY * (EMA_TIDE_D + 5), n - CAP_H - 1))
            aj = data[s]["atr"][j]
            if not np.isfinite(aj):
                continue
            p = float(data[s]["o"][j])     # тоже вход по открытию, честно
            fake.append((int(data[s]["ts"][j]), j, p,
                         p - STOP_ATR * aj * (HOLD_H ** 0.5), aj))
        fake.sort(key=lambda t: t[1])       # иначе правило «без наложения» съест почти всё
        C += simulate(data[s], fake, s)

    a = rep("Элдер как задумано", L)
    b = rep("шорт по тем же сетапам", S)
    c = rep("случайный вход", C)
    print(f"\nпревышение над случайным входом: {a - c:+.4f} R")
    print(f"разница сторон (лонг минус шорт): {a - b:+.4f} R")
    print("\nПО ГОДАМ")
    ts = np.array([r["ts"] for r in L])
    for y, (lo, hi) in {"2023": (0, 1704067200000), "2024": (1704067200000, 1735689600000),
                        "2025": (1735689600000, 9e12)}.items():
        g = [r for r in L if lo <= r["ts"] < hi]
        if len(g) >= 30:
            rep(f"  {y}", g)
    json.dump(dict(n=tot, long=a, short=b, ctrl=c, excess=a - c, side=a - b),
              open("eld_v1_result.json", "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
