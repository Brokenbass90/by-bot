#!/usr/bin/env python3
"""
side_split.py — где на самом деле живёт эдж: в лонгах или в шортах.

ЗАЧЕМ ИМЕННО ЭТО. Самый вероятный рычаг винрейта. Прошлая книга проекта
оказалась одной направленной ставкой в четырёх файлах: обе лонговые ноги
были отрицательны на обоих периодах, а общий плюс давали шорты. Если у
кандидата одна сторона убыточна, отключение этой стороны поднимает и R,
и винрейт, ничего не ломая в логике.

Считается то же, что в path_sim: настоящий стоп по барам вперёд,
издержки 16 bps круг, стоп масштабирован под горизонт. Разница одна —
результат разбивается по стороне сделки.

Отдельно печатается ДОЛЯ шортов: если сторона одна, эдж мог возникнуть
просто из направления рынка в окне, и это надо видеть сразу.
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

OUT = "research_lab/results/side_split_v2.json"
PAIRS = [
    ("inplay_breakout", "ETHUSDT"),
    ("alt_elder_revived_v1", "ETHUSDT"),
    ("elder_triple_screen_v2", "ETHUSDT"),
    ("inplay_retest_v3", "BTCUSDT"),
    ("inplay_retest_v4", "ETHUSDT"),
    ("alt_volume_spike_momentum_v1", "ETHUSDT"),
    ("elder_crypto_v1", "ETHUSDT"),
    ("elder_triple_screen_v3", "ETHUSDT"),
]
WIN, N_WIN = 40000, 4
STOP_MULT, HOURS = (0.5, 0.75, 1.0), (12, 24)
COST_BPS, ATR_N, PER = 16.0, 24, 10.0
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


def sim_one(c, hi, lo, atr, j, s, stop_atr, hb):
    if j + hb >= len(c) or not np.isfinite(atr[j]) or atr[j] <= 0:
        return None
    risk = stop_atr * atr[j]
    entry = c[j]
    stop = entry - s * risk
    for k in range(j + 1, j + hb + 1):
        if (s > 0 and lo[k] <= stop) or (s < 0 and hi[k] >= stop):
            return -1.0 - (COST_BPS / 1e4) * entry / risk
    return s * (c[j + hb] - entry) / risk - (COST_BPS / 1e4) * entry / risk


def collect(name, sym, shift):
    h = A.open_strategy(name, symbol=sym, limit=WIN * (shift + 1))
    if not h.get("ok") or h["symbol"] != sym:
        return None
    full = h["candles"]
    if len(full) < WIN * (shift + 1) * 0.9:
        return None
    i0 = max(0, len(full) - WIN * (shift + 1))
    cs = full[i0:i0 + WIN]
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

    out = []
    for m in STOP_MULT:
        for hrs in HOURS:
            hb = hrs * 12
            st = m * math.sqrt(hb)
            for j, s in zip(idx, sides):
                r = sim_one(c, hi, lo, atr, j, s, st, hb)
                if r is not None:
                    out.append((m, hrs, s, r))
    return out


def main():
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    import time
    t0 = time.time()
    for name, sym in PAIRS:
        key = f"{name}|{sym}"
        if key in res:
            continue
        if time.time() - t0 > BUDGET:
            print("[бюджет] ещё раз", flush=True); break
        rows = []
        for sh in range(N_WIN):
            try:
                r = collect(name, sym, sh)
            except Exception:
                r = None
            if r:
                rows += r
        if not rows:
            res[key] = dict(status="НЕТ"); json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=2, default=float); continue
        df = pd.DataFrame(rows, columns=["mult", "hours", "side", "R"])
        share_short = float((df[df.mult == df.mult.iloc[0]][df.hours == df.hours.iloc[0]].side < 0).mean()) \
            if len(df) else 0.0
        g = {}
        for sd, lab in ((+1, "лонг"), (-1, "шорт")):
            d = df[df.side == sd]
            if len(d) < 30:
                g[lab] = None
                continue
            best = None
            for (m, hr), sub in d.groupby(["mult", "hours"]):
                cand = dict(mult=float(m), hours=int(hr), n=int(len(sub)),
                            R=round(float(sub.R.mean()), 4),
                            wr=round(float((sub.R > 0).mean()), 3))
                if best is None or cand["R"] > best["R"]:
                    best = cand
            g[lab] = best
        both = df.groupby(["mult", "hours"]).R.mean().max()
        res[key] = dict(status="ОК", доля_шортов=round(share_short, 2),
                        лучший_общий=round(float(both), 4), стороны=g)
        json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=2, default=float)
        L, S = g.get("лонг"), g.get("шорт")
        f = lambda x: f"{x['R']:+.3f}R WR {x['wr']:.0%} n={x['n']}" if x else "мало"
        print(f"{name:<30} {sym:<9} шортов {share_short:.0%}  ЛОНГ {f(L):<26} ШОРТ {f(S)}", flush=True)
    print(f"[сохранено] {len(res)}")


if __name__ == "__main__":
    main()
