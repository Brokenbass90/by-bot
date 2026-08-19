#!/usr/bin/env python3
"""
control_check.py — контроль случайным входом. Обязательный шаг.

ЗАЧЕМ. Обнаружено, что inplay_breakout даёт 0% шортов — нога чисто
лонговая. А path_sim считал СЫРОЙ ход, без вычета базы. На растущем
рынке любой лонг покажет плюс, и +0.127R могли быть не эджем, а
направлением эфира за 2025-2026.

Это прямое правило проекта: «Контроль обязателен. Любое окно покажет
плюс на растущем рынке». Здесь оно применяется к моей же цифре.

КОНТРОЛЬ: те же окна, тот же стоп, тот же горизонт, то же ЧИСЛО сделок,
та же сторона — но моменты входа выбираются случайно. 200 повторов.
Эдж = результат стратегии МИНУС средний результат случайного входа.
Значимость — доля случайных прогонов, побивших стратегию.
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
MULT = float(sys.argv[3]) if len(sys.argv) > 3 else 0.75
HRS = int(sys.argv[4]) if len(sys.argv) > 4 else 24
WIN, N_WIN = 40000, 4
COST_BPS, ATR_N, PER = 16.0, 24, 10.0
N_RAND = 200
OUT = "research_lab/results/control_check"


class _Slow(Exception):
    pass


signal.signal(signal.SIGALRM, lambda s, f: (_ for _ in ()).throw(_Slow()))


def side_of(sig):
    for a in ("side", "direction", "dir"):
        v = getattr(sig, a, None) or (sig.get(a) if isinstance(sig, dict) else None)
        if isinstance(v, str):
            u = v.lower()
            if u in ("sell", "short", "-1", "down"):
                return -1
            if u in ("buy", "long", "1", "up"):
                return +1
    for a in ("is_short", "short"):
        if isinstance(getattr(sig, a, None), bool):
            return -1 if getattr(sig, a) else +1
    return +1


def sim(c, hi, lo, atr, idx, sides, stop_atr, hb):
    out = []
    n = len(c)
    for j, s in zip(idx, sides):
        if j + hb >= n or not np.isfinite(atr[j]) or atr[j] <= 0:
            continue
        risk = stop_atr * atr[j]
        entry = c[j]
        stop = entry - s * risk
        res = None
        for k in range(j + 1, j + hb + 1):
            if (s > 0 and lo[k] <= stop) or (s < 0 and hi[k] >= stop):
                res = -1.0
                break
        if res is None:
            res = s * (c[j + hb] - entry) / risk
        out.append(res - (COST_BPS / 1e4) * entry / risk)
    return np.array(out, float)


def main():
    os.makedirs(OUT, exist_ok=True)
    hb = HRS * 12
    st = MULT * math.sqrt(hb)
    real_all, rand_all = [], []
    print(f"{NAME} на {SYM}: стоп ×{MULT} ({st:.1f} ATR), горизонт {HRS}ч\n", flush=True)

    for sh in range(N_WIN):
        h = A.open_strategy(NAME, symbol=SYM, limit=WIN * (sh + 1))
        if not h.get("ok") or h["symbol"] != SYM:
            continue
        full = h["candles"]
        if len(full) < WIN * (sh + 1) * 0.9:
            continue
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
            continue

        real = sim(c, hi, lo, atr, idx, sides, st, hb)
        rng = np.random.default_rng(100 + sh)
        lows = ATR_N + 5
        rnd = []
        for _ in range(N_RAND):
            j = rng.integers(lows, n - hb - 1, size=len(idx))
            rnd.append(sim(c, hi, lo, atr, j, np.array(sides, float), st, hb).mean())
        rnd = np.array(rnd)
        real_all.append(real.mean()); rand_all.append(rnd)
        print(f"  окно {sh}: стратегия {real.mean():+.3f}R   случайно {rnd.mean():+.3f}R "
              f"(±{rnd.std():.3f})   лучше случайного в {(real.mean() > rnd).mean():.0%} прогонов",
              flush=True)

    if len(real_all) >= 2:
        r = np.array(real_all)
        base = np.array([x.mean() for x in rand_all])
        beat = np.mean([(real_all[i] > rand_all[i]).mean() for i in range(len(real_all))])
        print(f"\n═══ ИТОГ ═══")
        print(f"  стратегия  {r.mean():+.3f}R  по окнам {[f'{x:+.3f}' for x in r]}")
        print(f"  случайно   {base.mean():+.3f}R  по окнам {[f'{x:+.3f}' for x in base]}")
        print(f"  ЧИСТЫЙ ЭДЖ {r.mean()-base.mean():+.3f}R")
        print(f"  бьёт случайный вход в {beat:.0%} прогонов (нужно >95%)")
        print(f"  ВЕРДИКТ: {'эдж есть' if beat > 0.95 and r.mean() > base.mean() else 'ЭДЖА НЕТ — это рынок, а не сигнал'}")
        json.dump(dict(name=NAME, symbol=SYM, mult=MULT, hours=HRS,
                       strategy=[float(x) for x in r], control=[float(x) for x in base],
                       beat_rate=float(beat)),
                  open(os.path.join(OUT, f"{NAME}__{SYM}.json"), "w"),
                  ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
