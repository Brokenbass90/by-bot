#!/usr/bin/env python3
"""
mpl_v3.py — Momentum Pullback to Level, версия 3.
Правила взяты из research_lab/prereg/PREREG_MPL_V3_2026_08_12.md
и здесь НЕ подбираются.

ГЛАВНАЯ ОСТОРОЖНОСТЬ ЭТОЙ ВЕРСИИ. Переход на 15-минутки меняет
только ТОЧКУ ВХОДА. Всё, что описывает обстановку — ATR, максимум
за сутки, уровень, объём, EMA — считается на ЧАСОВЫХ барах, ровно
как в V1. Иначе смена таймфрейма молча меняет смысл каждого порога:
«2 ATR» на 15-минутках это совсем другое расстояние, чем «2 ATR»
на часах, и сравнение V1 с V2 стало бы бессмысленным.

Часовой признак, посчитанный по бару часа H, становится доступен
15-минутному бару только начиная со следующего часа. Сдвиг явный.

ЭТО ОТЛАДОЧНЫЙ ПРОГОН. Данные 2023-01..2025-09 использованы при
выборе порогов, поэтому здесь считается ТОЛЬКО частота сигналов
и работоспособность кода. Эдж на этих данных не заявляется.
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

DIR = sys.argv[1] if len(sys.argv) > 1 else "m15/m15"
CUTOFF_MS = 1759190400000          # 2025-09-30
HOUR = 3_600_000
BAR = 900_000
PER_H = 4                          # 15-минуток в часе

# --- пороги из предрегистрации ---
# ВЕРНУЛИСЬ К ПОРОГАМ V1: они были объявлены ДО первого прогона и
# никогда не подбирались под результат. Ужесточения V2 (объём 2.5,
# расстояние 2.5-4.5) выбирались по увиденным корзинам — именно они
# и сделали ногу непроверяемой. Убраны.
VOL_MULT = 1.5
TOP_FRAC = 0.20
IMP_MIN_ATR = 2.0
IMP_MAX_AGE_H = 6
PB_LO, PB_HI = 0.30, 0.60
MAX_WAIT_H = 12
STOP_BUF = 0.25
TGT_BUF = 0.30
MIN_ROOM, MAX_ROOM = 1.0, 6.0
LVL_LOOKBACK_H = 720
LVL_GAP_H = 24
HOLD_H = 24
EXTEND_H = 24
CAP_H = 168
EMA_HOURS = 24
# --- издержки ---
FEE_BPS = 6.0
# три яруса проскальзывания по обороту, объявлены заранее
SLIP_TIERS = ((100e6, 2.0), (20e6, 4.0), (0.0, 8.0))
FUND_PER_8H = 1.0
TIME_EXIT_SLIP = 2.0
TURN = {}                           # legacy fallback; executable path uses trailing turnover


def to_hourly(ts, o, h, l, c, v):
    key = ts // HOUR
    idx = np.flatnonzero(np.concatenate([[True], key[1:] != key[:-1]]))
    end = np.concatenate([idx[1:], [len(ts)]])
    hh = np.array([h[a:b].max() for a, b in zip(idx, end)])
    ll = np.array([l[a:b].min() for a, b in zip(idx, end)])
    cc = c[end - 1]
    vv = np.array([v[a:b].sum() for a, b in zip(idx, end)])
    return key[idx] * HOUR, o[idx], hh, ll, cc, vv


def atr(h, l, c, n=24):
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(tr), np.nan)
    if len(tr) > n:
        k = np.convolve(tr, np.ones(n) / n, mode="full")[: len(tr)]
        out[n:] = k[n:]
    return out


def roll(a, n, fn):
    out = np.full(len(a), np.nan)
    for i in range(n, len(a)):
        out[i] = fn(a[i - n:i])
    return out


def load(symbols=None, *, cutoff_ms=None):
    """Load an explicit universe.

    ``symbols`` is optional for the development diagnostic, but the sealed
    holdout runner always supplies it.  This prevents an unrelated ``.npz``
    left in the directory from silently changing the tested universe.
    """
    data = {}
    available = {
        os.path.basename(fp)[:-4]: fp
        for fp in sorted(glob.glob(os.path.join(DIR, "*.npz")))
    }
    selected = sorted(set(symbols)) if symbols is not None else sorted(available)
    missing = [symbol for symbol in selected if symbol not in available]
    if missing:
        raise RuntimeError(f"missing MPL input files: {missing}")
    effective_cutoff = CUTOFF_MS if cutoff_ms is None else int(cutoff_ms)
    for sym in selected:
        fp = available[sym]
        d = np.load(fp)
        ts, o = d["ts"], d["ohlcv"].astype(np.float64)
        m = ts <= effective_cutoff
        if m.sum() < (LVL_LOOKBACK_H + 200) * PER_H:
            continue
        data[sym] = dict(ts=ts[m], o=o[m, 0], h=o[m, 1], l=o[m, 2], c=o[m, 3], v=o[m, 4])
    return data


def prepare(d):
    H = dict(zip(("ts", "o", "h", "l", "c", "v"),
                 to_hourly(d["ts"], d["o"], d["h"], d["l"], d["c"], d["v"])))
    H["atr"] = atr(H["h"], H["l"], H["c"])
    H["hi24"] = roll(H["h"], 24, np.max)
    H["lo24"] = roll(H["l"], 24, np.min)
    n = len(H["h"])
    lvl = np.full(n, np.nan)
    for i in range(LVL_LOOKBACK_H + LVL_GAP_H, n):
        lvl[i] = H["h"][i - LVL_LOOKBACK_H - LVL_GAP_H:i - LVL_GAP_H].max()
    H["lvl"] = lvl
    cv = np.convolve(H["v"], np.ones(24), mode="full")[:n]
    v24 = np.full(n, np.nan); v24[24:] = cv[24:]
    med = np.full(n, np.nan)
    for i in range(LVL_LOOKBACK_H, n):
        med[i] = np.median(v24[i - LVL_LOOKBACK_H:i])
    H["vratio"] = v24 / med
    H["ret24"] = np.concatenate([[np.nan] * 24, H["c"][24:] / H["c"][:-24] - 1])
    k = 2 / (EMA_HOURS + 1); e = H["c"][0]
    ema = np.empty(n)
    for i in range(n):
        e = H["c"][i] * k + e * (1 - k); ema[i] = e
    H["ema"] = ema
    d["H"] = H
    # карта: для каждого 15-минутного бара — индекс ПОСЛЕДНЕГО ЗАКРЫТОГО часа
    d["hidx"] = np.searchsorted(H["ts"], d["ts"] - HOUR, side="right") - 1
    return d


def cross_rank(data, syms):
    allt = np.unique(np.concatenate([data[s]["H"]["ts"] for s in syms]))
    pos = {t: i for i, t in enumerate(allt)}
    M = np.full((len(allt), len(syms)), np.nan)
    for j, s in enumerate(syms):
        M[[pos[t] for t in data[s]["H"]["ts"]], j] = data[s]["H"]["ret24"]
    rk = np.full(M.shape, np.nan)
    for i in range(M.shape[0]):
        ok = np.isfinite(M[i])
        if ok.sum() >= 10:
            rk[i, ok] = np.argsort(np.argsort(M[i][ok])) / (ok.sum() - 1)
    for j, s in enumerate(syms):
        data[s]["H"]["rank"] = rk[[pos[t] for t in data[s]["H"]["ts"]], j]
    return data


def signals(d, *, reserve_future_bars=None):
    H = d["H"]; hidx = d["hidx"]
    c15, h15, l15 = d["c"], d["h"], d["l"]
    out = []
    i = LVL_LOOKBACK_H * PER_H + 200
    n = len(c15)
    reserve = CAP_H * PER_H if reserve_future_bars is None else max(1, int(reserve_future_bars))
    while i < n - reserve:
        k = hidx[i]
        if k < LVL_LOOKBACK_H + LVL_GAP_H + 30:
            i += 1; continue
        a = H["atr"][k]
        if not (np.isfinite(a) and a > 0 and np.isfinite(H["lvl"][k])
                and np.isfinite(H["vratio"][k]) and np.isfinite(H["rank"][k])):
            i += 1; continue
        if H["vratio"][k] < VOL_MULT or H["rank"][k] < 1 - TOP_FRAC:
            i += 1; continue
        w = H["h"][k - 24:k]
        j = int(np.argmax(w)); age = 24 - j
        if age > IMP_MAX_AGE_H or age < 1:
            i += 1; continue
        imp_hi = w[j]
        imp_lo = H["l"][k - 24:k - 24 + j + 1].min()
        height = imp_hi - imp_lo
        if not np.isfinite(height) or height < IMP_MIN_ATR * a:
            i += 1; continue
        price = c15[i]
        room = H["lvl"][k] - price
        if not (MIN_ROOM * a <= room <= MAX_ROOM * a):
            i += 1; continue
        lo_p, hi_p = imp_hi - PB_HI * height, imp_hi - PB_LO * height
        # откат меряется ОТ ИМПУЛЬСНОГО МАКСИМУМА, как в V1, а не по
        # скользящему окну: иначе увеличение «времени ожидания» делает
        # условие строже, а не мягче — это была ошибка первой сборки V2
        back = int(np.searchsorted(d["ts"], H["ts"][k - 24 + j], side="left"))
        if i - back > MAX_WAIT_H * PER_H:
            i += 1; continue
        seg_lo = l15[back:i + 1].min()
        if not (lo_p <= seg_lo <= hi_p):
            i += 1; continue
        if not (c15[i] > h15[i - 1]):
            i += 1; continue
        stop = seg_lo - STOP_BUF * a
        # The setup is only known after bar i closes.  Same-close execution is
        # not available to live and overstated every earlier MPL replay.
        entry_i = i + 1
        price = float(d["o"][entry_i])
        if price <= stop:
            i += 1; continue
        target = float(H["lvl"][k]) - TGT_BUF * float(a)
        if target <= price:
            i += 1; continue
        out.append((int(d["ts"][entry_i]), entry_i, price, stop, float(H["lvl"][k]), float(a)))
        i += HOLD_H * PER_H
    return out


def simulate(d, sig, sym, *, enforce_no_overlap=True):
    H = d["H"]; hidx = d["hidx"]
    h15, l15, c15 = d["h"], d["l"], d["c"]
    res = []
    next_available_i = -1
    for ts, i, entry, stop, lvl, a in sig:
        if enforce_no_overlap and int(i) < next_available_i:
            continue
        tgt = lvl - TGT_BUF * a
        risk = entry - stop
        if risk <= 0 or tgt <= entry:
            continue
        turn_lo = max(0, int(i) - 96)
        trailing_turnover = float(np.sum(c15[turn_lo:int(i)] * d["v"][turn_lo:int(i)]))
        slip = next(v for threshold, v in SLIP_TIERS if trailing_turnover >= threshold)
        round_trip_bps = 2 * (FEE_BPS + slip)
        end_exclusive = int(i) + HOLD_H * PER_H
        exitp, why, jend = None, "time", end_exclusive - 1
        j = int(i)
        while j < min(end_exclusive, len(h15)):
            if l15[j] <= stop:
                exitp, why, jend = stop, "stop", j; break
            if h15[j] >= tgt:
                exitp, why, jend = tgt, "target", j; break
            if j == end_exclusive - 1 and (end_exclusive - int(i)) < CAP_H * PER_H:
                kk = hidx[j]
                if c15[j] > entry and c15[j] > H["ema"][kk]:
                    end_exclusive = min(
                        int(i) + CAP_H * PER_H,
                        end_exclusive + EXTEND_H * PER_H,
                    )
            j += 1
        extra = 0.0
        if exitp is None:
            jend = min(end_exclusive - 1, len(h15) - 1); exitp = c15[jend]; extra = TIME_EXIT_SLIP
        hours = (jend - int(i) + 1) / PER_H
        cost = entry * (round_trip_bps + extra + FUND_PER_8H * hours / 8) / 1e4
        next_available_i = int(jend) + 1
        res.append(dict(ts=ts, sym=sym, R=float((exitp - entry - cost) / risk),
                        why=why, hours=hours, entry_i=int(i), exit_i=int(jend),
                        entry=float(entry), stop=float(stop), target=float(tgt),
                        risk_pct=float(risk / entry), target_room=float(tgt - entry),
                        trailing_turnover_usd=trailing_turnover, slip_bps=float(slip)))
    return res


def main():
    global TURN
    data = load(); syms = sorted(data)
    TURN = {s: float(np.median(data[s]["c"] * data[s]["v"])) * 96 for s in syms}
    print(f"символов {len(syms)}, 15-минутные бары до 2025-09-30")
    for s in syms:
        prepare(data[s])
    cross_rank(data, syms)

    allsig = {s: signals(data[s]) for s in syms}
    tot = sum(len(v) for v in allsig.values())
    print(f"\nСИГНАЛОВ: {tot:,} на {sum(1 for v in allsig.values() if v)} символах "
          f"за 2.75 года")
    print(f"  это {tot/33:.1f} сигналов в месяц на весь портфель")

    res = []
    for s in syms:
        if allsig[s]:
            res += simulate(data[s], allsig[s], s)
    if not res:
        print("сделок нет"); return
    R = np.array([r["R"] for r in res])
    why = [r["why"] for r in res]
    hrs = np.array([r["hours"] for r in res])
    ext = float(np.mean(hrs > HOLD_H))
    print(f"\nОТЛАДОЧНЫЕ ЧИСЛА (эдж не заявляется, пороги выбраны на этих данных)")
    print(f"  сделок {len(R):,}   среднее время {hrs.mean():.0f} ч")
    print(f"  исходы: цель {np.mean([w=='target' for w in why]):.0%}, "
          f"стоп {np.mean([w=='stop' for w in why]):.0%}, "
          f"время {np.mean([w=='time' for w in why]):.0%}")
    print(f"  правило продления сработало в {ext:.0%} сделок "
          f"(коридор предрегистрации 5-50%)")
    print(f"  R/сделку {R.mean():+.4f}   винрейт {(R>0).mean():.1%}")
    json.dump(dict(n_signals=tot, n_trades=len(R), mean_R=float(R.mean()),
                   winrate=float((R > 0).mean()), extend_frac=ext,
                   mean_hours=float(hrs.mean())),
              open("mpl_v2_debug.json", "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
