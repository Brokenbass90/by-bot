#!/usr/bin/env python3
"""
major_hunt.py — сито по живым стратегиям на BTC и ETH.

Что делает: гоняет каждую живую стратегию по двум мажорам, по сетке
«ширина стопа x горизонт», на нескольких непересекающихся окнах,
с настоящим стопом и издержками. Возвращает ОДНО число на стратегию:
медианный R на сделку у самого устойчивого варианта.

Стоп масштабируется под горизонт (ATR*sqrt(баров)), иначе на суточном
удержании стоп в пару пятиминутных ATR выбивает почти всегда — на этом
я уже один раз ошибся и получил ложный отказ.

Устойчивый = плюсовой в большинстве окон. Одиночный чемпион не считается:
при 30 вариантах и 4 окнах случайно проходит примерно каждый третий.

Запускать повторно: готовые пропускаются.
    python3 research_lab/major_hunt.py [бюджет_сек]
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

OUT = "research_lab/results/major_hunt.json"
CENSUS = "research_lab/results/strategy_census.json"
SYMS = ("BTCUSDT", "ETHUSDT")
WIN, N_WIN = 40000, 3
STOP_MULT = (0.5, 1.0, 2.0)
HOURS = (4, 8, 12, 24)
COST_BPS = 16.0
ATR_N, PER = 24, 9.0
BUDGET = float(sys.argv[1]) if len(sys.argv) > 1 else 32.0


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


def one(name, sym, shift):
    h = A.open_strategy(name, symbol=sym, limit=WIN * (shift + 1))
    if not h.get("ok") or h["symbol"] != sym:
        return None
    full = h["candles"]
    if len(full) < WIN * (shift + 1) * 0.9:
        return None
    lo_i = max(0, len(full) - WIN * (shift + 1))
    cs = full[lo_i:lo_i + WIN]
    from backtest.engine import KlineStore
    store = KlineStore(sym, cs, base_interval_min=5)
    call = A.make_caller(h["conv"], h["obj"], sym)

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
        return None
    g = {}
    for m in STOP_MULT:
        for hrs in HOURS:
            hb = hrs * 12
            R = sim(c, hi, lo, atr, idx, sides, m * math.sqrt(hb), hb)
            if len(R) >= 15:
                g[f"{m}_{hrs}"] = dict(R=round(float(R.mean()), 4),
                                       wr=round(float((R > 0).mean()), 3), n=len(R))
    return dict(signals=len(idx), grid=g)


def main():
    census = json.load(open(CENSUS)) if os.path.exists(CENSUS) else {}
    live = sorted([k for k, v in census.items() if v.get("status") == "ЖИВАЯ"],
                  key=lambda k: -(census[k].get("signals") or 0))
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    jobs = [(nm, sy) for nm in live for sy in SYMS if f"{nm}|{sy}" not in res]
    print(f"заданий осталось {len(jobs)}", flush=True)

    t0 = time.time()
    for nm, sy in jobs:
        if time.time() - t0 > BUDGET:
            print("[бюджет] ещё раз", flush=True)
            break
        wins = []
        for sh in range(N_WIN):
            try:
                r = one(nm, sy, sh)
            except Exception:
                r = None
            if r:
                wins.append(r)
        key = f"{nm}|{sy}"
        if len(wins) < 2:
            res[key] = dict(status="НЕТ")
        else:
            keys = set(wins[0]["grid"])
            for w in wins[1:]:
                keys &= set(w["grid"])
            rows = []
            for k in keys:
                rs = [w["grid"][k]["R"] for w in wins]
                rows.append((k, float(np.median(rs)), float(np.mean([x > 0 for x in rs])),
                             float(np.mean([w["grid"][k]["wr"] for w in wins]))))
            stable = [r for r in rows if r[2] >= 0.66 and r[1] > 0]
            stable.sort(key=lambda r: -r[1])
            res[key] = dict(status="ОК", windows=len(wins),
                            signals=int(np.mean([w["signals"] for w in wins])),
                            n_variants=len(rows), n_stable=len(stable),
                            best=(dict(variant=stable[0][0], R=round(stable[0][1], 4),
                                       wr=round(stable[0][3], 3)) if stable else None))
        json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=2)
        b = res[key].get("best")
        print(f"{nm:<32} {sy:<9} " +
              (f"устойч {res[key]['n_stable']}/{res[key]['n_variants']}  "
               f"лучший {b['variant']} {b['R']:+.3f}R WR {b['wr']:.0%}" if b else "нет устойчивых"),
              flush=True)
    print(f"[сохранено] {len(res)}", flush=True)


if __name__ == "__main__":
    main()
