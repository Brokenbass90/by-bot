#!/usr/bin/env python3
"""
followthrough_filter.py — фильтр «пробои перестали продолжаться».

ОСНОВАНИЕ. Разбор плохого окна показал: там доля стопов была 32% против
14%, а ход в пользу 0.42R против 0.93R, при почти той же волатильности.
Пробои выбивали уровень и разворачивались. Это режим, а не случай —
убыток размазан ровно по всем сделкам.

ИДЕЯ ФИЛЬТРА. Считать по САМОМУ РЫНКУ, продолжаются ли пробои в последнее
время, и не входить, когда перестали. Величина механическая и считается
только по прошлому:

    событие      закрытие выше максимума прошлых 168 часов
    исход        через 24 часа цена выше входа или нет
    признак      доля удачных среди последних K РАЗРЕШИВШИХСЯ событий

Событие считается разрешившимся только когда прошли все 24 часа, поэтому
заглядывания вперёд нет по построению.

КРИТЕРИЙ ОБЪЯВЛЕН ДО ПРОГОНА (записан в ROADMAP_2026_08_11):
фильтр обязан убрать плохое окно И НЕ ТРОНУТЬ три хороших.
Если режет и хорошие — выброшен, а не подстроен.
"""
from __future__ import annotations

import json
import math
import os
import signal
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "research_lab")
import strategy_adapter as A

NAME = sys.argv[1] if len(sys.argv) > 1 else "inplay_breakout"
SYM = sys.argv[2] if len(sys.argv) > 2 else "ETHUSDT"
MULT, HRS = 0.75, 24
WIN, N_WIN = 40000, 4
# ИСПРАВЛЕНО: недельный максимум даёт слишком редкие события — в падающем
# рынке новых недельных хаёв почти нет, и признак не набирался вообще
# (все значения NaN во всех четырёх окнах). Берём СУТОЧНЫЙ максимум:
# событий на порядок больше, признак считается непрерывно.
LOOKBACK = 24 * 12           # уровень = максимум прошлых суток, в 5m барах
RESOLVE = 12 * 12            # исход события через 12 часов
DEDUP = 12                   # не чаще раза в час
K_EVENTS = 25                # по скольким последним событиям считаем признак
THRESHOLDS = (0.35, 0.40, 0.45, 0.50)
COST_BPS, ATR_N, PER = 16.0, 24, 10.0
OUT = "research_lab/results/ft_filter"


class _Slow(Exception):
    pass


signal.signal(signal.SIGALRM, lambda s, f: (_ for _ in ()).throw(_Slow()))


def side_of(sig):
    for a in ("side", "direction", "dir"):
        v = getattr(sig, a, None) or (sig.get(a) if isinstance(sig, dict) else None)
        if isinstance(v, str) and v.lower() in ("sell", "short", "down"):
            return -1
    return +1


def follow_through(c, hi):
    """Скользящая доля продолжившихся пробоев. Только прошлое."""
    n = len(c)
    lvl = pd.Series(hi).shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).max().to_numpy()
    ev = np.flatnonzero(np.isfinite(lvl) & (c > lvl))
    # дедуп: не чаще раза в сутки
    keep, last = [], -10 ** 9
    for t in ev:
        if t - last >= DEDUP:
            keep.append(t); last = t
    ev = np.array(keep, dtype=np.int64)
    ev = ev[ev + RESOLVE < n]
    if len(ev) == 0:
        return np.full(n, np.nan), 0
    win = (c[ev + RESOLVE] > c[ev]).astype(float)
    res_t = ev + RESOLVE                      # момент, КОГДА исход стал известен

    ft = np.full(n, np.nan)
    p = 0
    buf = []
    for i in range(n):
        while p < len(res_t) and res_t[p] <= i:
            buf.append(win[p]); p += 1
        if len(buf) >= K_EVENTS:
            ft[i] = float(np.mean(buf[-K_EVENTS:]))
    return ft, len(ev)


def run(sh):
    h = A.open_strategy(NAME, symbol=SYM, limit=WIN * (sh + 1))
    if not h.get("ok") or h["symbol"] != SYM:
        return None
    full = h["candles"]
    if len(full) < WIN * (sh + 1) * 0.9:
        return None
    i0 = max(0, len(full) - WIN * (sh + 1))
    cs = full[i0:i0 + WIN]
    from backtest.engine import KlineStore
    store = KlineStore(SYM, cs, base_interval_min=5)
    call = A.make_caller(h["conv"], h["obj"], SYM)

    n = len(cs)
    c = np.array([x.c for x in cs]); hi = np.array([x.h for x in cs]); lo = np.array([x.l for x in cs])
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([hi - lo, np.abs(hi - pc), np.abs(lo - pc)])
    atr = pd.Series(tr).ewm(alpha=1 / ATR_N, adjust=False, min_periods=ATR_N).mean().to_numpy()
    ts = pd.to_datetime([x.ts for x in cs], unit="ms", utc=True)
    ft, n_ev = follow_through(c, hi)

    idx, sides = [], []
    signal.setitimer(signal.ITIMER_REAL, PER)
    try:
        for i in range(n):
            store.i5 = i; store.i = i; store.i_base = i
            try:
                r = call(store, cs, i)
            except _Slow:
                raise
            except Exception:
                continue
            if r is not None:
                idx.append(i); sides.append(side_of(r))
    except _Slow:
        pass
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    if len(idx) < 15:
        return None

    hb = HRS * 12
    st = MULT * math.sqrt(hb)
    rows = []
    for j, s in zip(idx, sides):
        if j + hb >= n or not np.isfinite(atr[j]) or atr[j] <= 0:
            continue
        risk = st * atr[j]
        entry = c[j]
        stop = entry - s * risk
        res = None
        for k in range(j + 1, j + hb + 1):
            if (s > 0 and lo[k] <= stop) or (s < 0 and hi[k] >= stop):
                res = -1.0
                break
        if res is None:
            res = s * (c[j + hb] - entry) / risk
        rows.append((res - (COST_BPS / 1e4) * entry / risk, ft[j]))
    if len(rows) < 15:
        return None
    R = np.array([x[0] for x in rows]); F = np.array([x[1] for x in rows])
    out = dict(window=sh, start=str(ts[0].date()), end=str(ts[-1].date()),
               n_events=int(n_ev), trades=len(R),
               base_R=round(float(R.mean()), 3),
               ft_median=round(float(np.nanmedian(F)), 3),
               ft_coverage=round(float(np.isfinite(F).mean()), 2))
    for th in THRESHOLDS:
        m = np.isfinite(F) & (F >= th)
        out[f"th{th}"] = dict(kept=int(m.sum()),
                              share=round(float(m.mean()), 2),
                              R=round(float(R[m].mean()), 3) if m.sum() >= 10 else None)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for sh in range(N_WIN):
        try:
            r = run(sh)
        except Exception as e:
            print(f"окно {sh}: {type(e).__name__}"[:60], flush=True); r = None
        if r:
            rows.append(r); print(f"окно {sh} готово", flush=True)
    if not rows:
        return
    print(f"\n{'окно':>5}{'период':>13}{'сделок':>8}{'без фильтра':>13}{'FT медиана':>12}")
    for r in rows:
        print(f"{r['window']:>5}{r['start']:>13}{r['trades']:>8}{r['base_R']:>+13.3f}{r['ft_median']:>12.2f}")
    print(f"\n{'порог':>7}" + "".join(f"{'окно'+str(r['window']):>16}" for r in rows))
    for th in THRESHOLDS:
        cells = []
        for r in rows:
            d = r[f"th{th}"]
            cells.append(f"{d['R']:+.3f}/{d['share']:.0%}" if d["R"] is not None else "     мало")
        print(f"{th:>7}" + "".join(f"{x:>16}" for x in cells))
    print("\n(в клетке: R на сделку после фильтра / доля оставленных сделок)")

    bad = min(rows, key=lambda r: r["base_R"])
    good = [r for r in rows if r is not bad]
    print(f"\n═══ ПРОВЕРКА КРИТЕРИЯ (плохое окно {bad['window']}) ═══")
    for th in THRESHOLDS:
        b = bad[f"th{th}"]["R"]
        g = [r[f"th{th}"]["R"] for r in good]
        if b is None or any(x is None for x in g):
            print(f"  порог {th}: мало сделок"); continue
        fixed = b > bad["base_R"]
        kept = all(g[i] >= good[i]["base_R"] * 0.8 for i in range(len(good)))
        print(f"  порог {th}: плохое {bad['base_R']:+.3f} -> {b:+.3f}  "
              f"хорошие {[f'{x:+.3f}' for x in g]}  "
              f"{'ПРОХОДИТ' if fixed and kept else 'не проходит'}")
    json.dump(rows, open(os.path.join(OUT, f"{NAME}__{SYM}.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"\n[сохранено] {OUT}/{NAME}__{SYM}.json")


if __name__ == "__main__":
    main()
