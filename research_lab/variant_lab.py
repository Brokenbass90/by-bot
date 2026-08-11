#!/usr/bin/env python3
"""
variant_lab.py — СОТНИ вариантов так, чтобы масштаб добавлял знание, а не убивал.

ПРОБЛЕМА МАСШТАБА. В backtest_runs/ лежит 53 467 прогонов. Лучший из
десяти тысяч — принципиально более слабое свидетельство, чем тот же
результат из десяти, потому что чем больше вариантов перебрано, тем
выше лучший результат ПРИ ПОЛНОМ ОТСУТСТВИИ ЭДЖА.

ПОЭТОМУ здесь три правила, вшитые в код:

  1. СЕТКА ОБЪЯВЛЯЕТСЯ ЦЕЛИКОМ до прогона. Число вариантов N известно.
  2. РЕЗУЛЬТАТ — ЭТО РАСПРЕДЕЛЕНИЕ, а не чемпион. Семейство, положительное
     в 36 случаях из 36, — свидетельство. Лучший из 1000 — нет.
  3. ПОРОГ РАСТЁТ С ЧИСЛОМ ВАРИАНТОВ. Под нулевой гипотезой максимум из N
     независимых |t| в среднем равен sqrt(2*ln N). Чемпион обязан бить
     этот порог, а не ноль.

        N=10  -> 2.15      N=100 -> 3.03      N=340 -> 3.41

     Варианты вложенные (соседние горизонты), поэтому эффективное N меньше
     и порог получается КОНСЕРВАТИВНЫМ. Это осознанно: лучше пропустить
     находку, чем принять шум.

ЧТО СЕЙЧАС МЕРЯЕТСЯ: горизонт удержания. Сигналы стратегии считаются
ОДИН раз, дальше сметается только момент выхода — поэтому сотни вариантов
стоят копейки. Гипотеза от inplay_breakout: +3.50 ATR на 6 часах против
-4.53 ATR на 72 — импульс реальный, но короткий.
"""
from __future__ import annotations

import json
import math
import os
import signal
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "research_lab")
import strategy_adapter as A

OUT = "research_lab/results/variant_lab"
CENSUS = "research_lab/results/strategy_census.json"
BARS = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
BUDGET = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
PER = float(sys.argv[3]) if len(sys.argv) > 3 else 12.0
ATR_N = 24

# ---- СЕТКА, объявленная до прогона ----
HOURS = (1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 30, 36, 48, 60, 72, 96)
N_GRID = len(HOURS)
BAR_T = math.sqrt(2 * math.log(N_GRID))     # порог для чемпиона внутри стратегии


class _Slow(Exception):
    pass


signal.signal(signal.SIGALRM, lambda s, f: (_ for _ in ()).throw(_Slow()))


def boot_t(v, weeks, n_boot=800, seed=5):
    v = np.asarray(v, float)
    ok = np.isfinite(v)
    v, w = v[ok], np.asarray(weeks)[ok]
    if len(v) < 20:
        return np.nan, np.nan, 0
    uw, inv = np.unique(w, return_inverse=True)
    k = len(uw)
    s = np.bincount(inv, weights=v, minlength=k)
    c = np.bincount(inv, minlength=k).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, k, size=(n_boot, k))
    bs = s[pick].sum(1) / np.maximum(c[pick].sum(1), 1)
    m, se = float(v.mean()), float(bs.std(ddof=1))
    return m, (m / se if se > 0 else np.nan), k


def main():
    os.makedirs(OUT, exist_ok=True)
    resfp = os.path.join(OUT, "horizon_sweep.json")
    census = json.load(open(CENSUS)) if os.path.exists(CENSUS) else {}
    live = [k for k, v in census.items() if v.get("status") == "ЖИВАЯ"
            and (v.get("signals") or 0) >= 25]
    res = json.load(open(resfp)) if os.path.exists(resfp) else {}
    todo = [n for n in live if n not in res]
    print(f"стратегий с >=25 сигналами: {len(live)}, осталось {len(todo)}")
    print(f"сетка: {N_GRID} горизонтов, порог для чемпиона |t| >= {BAR_T:.2f}\n", flush=True)

    t0 = time.time()
    for name in todo:
        if time.time() - t0 > BUDGET:
            print("[бюджет] запусти ещё раз", flush=True)
            break
        try:
            h = A.open_strategy(name, limit=BARS)
        except Exception as e:
            res[name] = dict(status="ОШИБКА", detail=str(e)[:100]); json.dump(res, open(resfp, "w"), ensure_ascii=False, indent=2); continue
        if not h.get("ok"):
            res[name] = dict(status="НЕ_ОТКРЫЛАСЬ"); json.dump(res, open(resfp, "w"), ensure_ascii=False, indent=2); continue

        cs, store, call = h["candles"], h["store"], h["call"]
        n = len(cs)
        c = np.array([x.c for x in cs]); hi = np.array([x.h for x in cs]); lo = np.array([x.l for x in cs])
        pc = np.r_[c[0], c[:-1]]
        tr = np.maximum.reduce([hi - lo, np.abs(hi - pc), np.abs(lo - pc)])
        atr = pd.Series(tr).ewm(alpha=1 / ATR_N, adjust=False, min_periods=ATR_N).mean().to_numpy()
        ts = pd.to_datetime([x.ts for x in cs], unit="ms", utc=True)
        iso = ts.isocalendar(); wk = iso.year.to_numpy() * 100 + iso.week.to_numpy()

        # сигналы считаются ОДИН раз — дальше сметается только выход
        idx, sides = [], []
        signal.setitimer(signal.ITIMER_REAL, PER)
        timed_out = False
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
                    from strategy_edge_probe import side_of
                    s_, _ = side_of(r)
                    idx.append(i); sides.append(s_)
        except _Slow:
            timed_out = True
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

        if timed_out:
            res[name] = dict(
                status="TIMEOUT_INCOMPLETE",
                symbol=h["symbol"],
                partial_signals=len(idx),
                timeout_seconds=PER,
                detail="частичный прогон запрещён к интерпретации",
            )
            json.dump(res, open(resfp, "w"), ensure_ascii=False, indent=2)
            continue

        if len(idx) < 25:
            res[name] = dict(status="МАЛО_СИГНАЛОВ", signals=len(idx))
            json.dump(res, open(resfp, "w"), ensure_ascii=False, indent=2); continue
        idx = np.array(idx); sides = np.array(sides, float)

        grid = []
        for hrs in HOURS:
            hb = hrs * 12                      # 5-минутные бары
            ok = idx + hb < n
            if ok.sum() < 20:
                continue
            j = idx[ok]
            move = (c[j + hb] - c[j]) / atr[j] * sides[ok]
            bj = np.arange(0, n - hb, 288)
            base = float(np.nanmean((c[bj + hb] - c[bj]) / atr[bj]))
            m, t, k = boot_t(move - base, wk[j])
            grid.append(dict(hours=hrs, n=int(ok.sum()), weeks=k,
                             excess=round(float(m), 3),
                             t=round(float(t), 2) if np.isfinite(t) else None))
        if not grid:
            res[name] = dict(status="НЕТ_СЕТКИ"); json.dump(res, open(resfp, "w"), ensure_ascii=False, indent=2); continue

        ts_ = [g["t"] for g in grid if g["t"] is not None]
        ex_ = [g["excess"] for g in grid]
        champ = max(grid, key=lambda g: abs(g["t"] or 0))
        res[name] = dict(status="ОК", symbol=h["symbol"], signals=len(idx),
                         n_variants=len(grid),
                         доля_плюсовых=round(float(np.mean([e > 0 for e in ex_])), 2),
                         медиана_excess=round(float(np.median(ex_)), 3),
                         чемпион=champ, порог=round(BAR_T, 2),
                         вердикт="выше порога" if abs(champ["t"] or 0) >= BAR_T else "в пределах шума",
                         сетка=grid)
        json.dump(res, open(resfp, "w"), ensure_ascii=False, indent=2)
        print(f"{name:<32} вариантов {len(grid):>3}  плюсовых {res[name]['доля_плюсовых']:.0%}  "
              f"медиана {res[name]['медиана_excess']:+.2f}  чемпион {champ['hours']}ч "
              f"t={champ['t']}  {res[name]['вердикт']}", flush=True)

    print(f"\n[сохранено] {resfp}")


if __name__ == "__main__":
    main()
