#!/usr/bin/env python3
"""
setup_features.py — какой признак САМОГО СЕТАПА отделяет удачные пробои.

ОСНОВАНИЕ. Фильтр по режиму рынка провалился: доля продолжившихся пробоев
в плохом окне была 0.44 — ровно как в хорошем. Рынок пробивал нормально,
а нога брала не те пробои. Значит искать надо не режим, а признак сделки.

ПРИЗНАКИ (все считаются на момент входа, только по прошлому):

    ext        насколько вход выше пробитого суточного максимума, в ATR
    runup      сколько цена уже прошла за сутки до входа, в ATR
    vol_rel    объём последнего часа к медиане за сутки
    atr_rel    текущий ATR к своей медиане за неделю
    dist_ma    расстояние до суточной средней, в ATR
    hour       час входа UTC

МЕТОД. Сделки делятся по каждому признаку на три равные корзины, и
считается R в каждой. Признак полезен, только если направление эффекта
ОДИНАКОВО во всех четырёх окнах — иначе это подгонка под окно.

КРИТЕРИЙ ОБЪЯВЛЕН ДО ПРОГОНА:
признак принимается, если разрыв между лучшей и худшей корзиной >= 0.3R
на объединённых данных И знак разрыва одинаков во всех 4 окнах.
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
COST_BPS, ATR_N, PER = 16.0, 24, 10.0
DAY = 288          # 5m баров в сутках
OUT = "research_lab/results/setup_features"
GAP_MIN = 0.3      # объявленный порог разрыва между корзинами


class _Slow(Exception):
    pass


signal.signal(signal.SIGALRM, lambda s, f: (_ for _ in ()).throw(_Slow()))


def side_of(sig):
    for a in ("side", "direction", "dir"):
        v = getattr(sig, a, None) or (sig.get(a) if isinstance(sig, dict) else None)
        if isinstance(v, str) and v.lower() in ("sell", "short", "down"):
            return -1
    return +1


def window_trades(sh):
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
    c = np.array([x.c for x in cs]); hi = np.array([x.h for x in cs])
    lo = np.array([x.l for x in cs]); vol = np.array([x.v for x in cs])
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([hi - lo, np.abs(hi - pc), np.abs(lo - pc)])
    atr = pd.Series(tr).ewm(alpha=1 / ATR_N, adjust=False, min_periods=ATR_N).mean().to_numpy()
    ts = pd.to_datetime([x.ts for x in cs], unit="ms", utc=True)

    lvl = pd.Series(hi).shift(1).rolling(DAY, min_periods=DAY).max().to_numpy()
    sma = pd.Series(c).rolling(DAY, min_periods=DAY).mean().to_numpy()
    vol_h = pd.Series(vol).rolling(12, min_periods=6).sum().to_numpy()
    vol_med = pd.Series(vol).rolling(DAY, min_periods=DAY // 2).median().to_numpy() * 12
    atr_med = pd.Series(atr).rolling(DAY * 7, min_periods=DAY).median().to_numpy()

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
    if len(idx) < 20:
        return None

    hb = HRS * 12
    st = MULT * math.sqrt(hb)
    rows = []
    for j, s in zip(idx, sides):
        if j + hb >= n or j < DAY * 7 or not np.isfinite(atr[j]) or atr[j] <= 0:
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
        res -= (COST_BPS / 1e4) * entry / risk
        rows.append(dict(
            window=sh, R=res,
            ext=(entry - lvl[j]) / atr[j] if np.isfinite(lvl[j]) else np.nan,
            runup=(entry - c[j - DAY]) / atr[j],
            vol_rel=vol_h[j] / vol_med[j] if np.isfinite(vol_med[j]) and vol_med[j] > 0 else np.nan,
            atr_rel=atr[j] / atr_med[j] if np.isfinite(atr_med[j]) and atr_med[j] > 0 else np.nan,
            dist_ma=(entry - sma[j]) / atr[j] if np.isfinite(sma[j]) else np.nan,
            hour=int(ts[j].hour),
        ))
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    allrows = []
    for sh in range(N_WIN):
        try:
            r = window_trades(sh)
        except Exception as e:
            print(f"окно {sh}: {type(e).__name__}"[:60], flush=True); r = None
        if r:
            allrows += r
            print(f"окно {sh}: {len(r)} сделок", flush=True)
    if not allrows:
        return
    df = pd.DataFrame(allrows)
    print(f"\nвсего сделок {len(df)}, окон {df.window.nunique()}, средний R {df.R.mean():+.3f}\n")

    feats = ["ext", "runup", "vol_rel", "atr_rel", "dist_ma"]
    verdict = []
    for f in feats:
        d = df[np.isfinite(df[f])]
        if len(d) < 80:
            print(f"{f:<9} мало данных"); continue
        q = d[f].quantile([1 / 3, 2 / 3]).values
        d = d.assign(bin=np.where(d[f] <= q[0], "низ", np.where(d[f] <= q[1], "сред", "верх")))
        pooled = d.groupby("bin").R.agg(["mean", "size"])
        gap = float(pooled["mean"].max() - pooled["mean"].min())
        best = pooled["mean"].idxmax()
        # знак эффекта по окнам: везде ли лучшая корзина остаётся лучшей половины
        per_win = []
        for w, sub in d.groupby("window"):
            g = sub.groupby("bin").R.mean()
            if best in g.index and len(g) >= 2:
                per_win.append(bool(g[best] >= g.mean()))
        consistent = len(per_win) == df.window.nunique() and all(per_win)
        ok = gap >= GAP_MIN and consistent
        cells = "  ".join(f"{b}:{pooled.loc[b,'mean']:+.2f}({int(pooled.loc[b,'size'])})"
                          for b in ("низ", "сред", "верх") if b in pooled.index)
        print(f"{f:<9} {cells}   разрыв {gap:.2f}  лучшая «{best}»  "
              f"во всех окнах {'да' if consistent else 'НЕТ'}  {'ПРИНЯТ' if ok else ''}")
        verdict.append(dict(feature=f, gap=round(gap, 3), best=best,
                            consistent=consistent, accepted=ok))

    d = df.assign(bin=pd.cut(df.hour, [-1, 5, 11, 17, 23],
                             labels=["00-05", "06-11", "12-17", "18-23"]))
    g = d.groupby("bin", observed=True).R.agg(["mean", "size"])
    print("\nчас входа UTC: " + "  ".join(f"{b}:{g.loc[b,'mean']:+.2f}({int(g.loc[b,'size'])})"
                                          for b in g.index))
    json.dump(verdict, open(os.path.join(OUT, f"{NAME}__{SYM}.json"), "w"),
              ensure_ascii=False, indent=2)
    acc = [v for v in verdict if v["accepted"]]
    print(f"\nПРИНЯТО ПРИЗНАКОВ: {len(acc)} из {len(verdict)}"
          + (f" -> {[v['feature'] for v in acc]}" if acc else " — рычага в сетапе не найдено"))


if __name__ == "__main__":
    main()
