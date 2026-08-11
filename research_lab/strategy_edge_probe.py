#!/usr/bin/env python3
"""
strategy_edge_probe.py — есть ли у сигнала предсказательная сила.

«Стреляет» и «попадает» — разные вопросы. Перепись ответила на первый.
Этот скрипт отвечает на второй, самым дешёвым способом из возможных.

КАК. Не воспроизводим выходы стратегии (у каждой свои, и там своя куча
багов). Берём только МОМЕНТ и СТОРОНУ сигнала и смотрим, куда пошла цена
через 6 / 24 / 72 часа, в единицах ATR. Если сигнал ничего не предсказывает,
никакие выходы его не спасут — а если предсказывает, дальше уже имеет смысл
чинить вход и выход.

Рядом всегда стоит БАЗА — тот же символ, случайные моменты. Без неё число
нечитаемо: на растущем рынке любой лонг покажет плюс.

Значимость — блочный бутстрап по неделям (окна пересекаются, наивный t врёт).

Запускать повторно: готовые пропускаются.
    python3 research_lab/strategy_edge_probe.py [баров] [бюджет_сек] [лимит_на_стратегию]
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "research_lab")
import strategy_adapter as A

OUT = "research_lab/results/strategy_edge.json"
CENSUS = "research_lab/results/strategy_census.json"
BARS = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
BUDGET = float(sys.argv[2]) if len(sys.argv) > 2 else 32.0
PER = float(sys.argv[3]) if len(sys.argv) > 3 else 14.0
HOR_BARS = {"6ч": 72, "24ч": 288, "72ч": 864}     # в 5-минутных барах
ATR_N = 24


class _Slow(Exception):
    pass


signal.signal(signal.SIGALRM, lambda s, f: (_ for _ in ()).throw(_Slow()))


def _save(d):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(d, open(OUT, "w"), indent=2, ensure_ascii=False)


def side_of(sig):
    """Сторона сигнала. Формы объектов разные, поэтому ищем широко.
    Если понять нельзя — считаем лонгом и ПОМЕЧАЕМ это, а не молчим."""
    for a in ("side", "direction", "dir"):
        v = getattr(sig, a, None) or (sig.get(a) if isinstance(sig, dict) else None)
        if isinstance(v, str):
            u = v.lower()
            if u in ("sell", "short", "-1", "down"):
                return -1, True
            if u in ("buy", "long", "1", "up"):
                return +1, True
    for a in ("is_short", "short"):
        v = getattr(sig, a, None)
        if isinstance(v, bool):
            return (-1 if v else +1), True
    for a in ("is_long", "long"):
        v = getattr(sig, a, None)
        if isinstance(v, bool):
            return (+1 if v else -1), True
    return +1, False


def boot_t(vals, weeks, n_boot=1000, seed=3):
    v = np.asarray(vals, float)
    ok = np.isfinite(v)
    v, w = v[ok], np.asarray(weeks)[ok]
    if len(v) < 20:
        return np.nan, np.nan, len(v), 0
    uw, inv = np.unique(w, return_inverse=True)
    k = len(uw)
    s = np.bincount(inv, weights=v, minlength=k)
    c = np.bincount(inv, minlength=k).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, k, size=(n_boot, k))
    bs = s[pick].sum(1) / np.maximum(c[pick].sum(1), 1)
    m, se = float(v.mean()), float(bs.std(ddof=1))
    return m, (m / se if se > 0 else np.nan), len(v), k


def main():
    census = json.load(open(CENSUS)) if os.path.exists(CENSUS) else {}
    live = [k for k, v in census.items() if v.get("status") == "ЖИВАЯ"]
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    todo = [n for n in live if n not in res]
    print(f"живых {len(live)}, осталось {len(todo)}", flush=True)

    t0 = time.time()
    for name in todo:
        if time.time() - t0 > BUDGET:
            print("[бюджет] запусти ещё раз", flush=True)
            break
        try:
            h = A.open_strategy(name, limit=BARS)
        except Exception as e:
            res[name] = dict(status="ОШИБКА", detail=str(e)[:120]); _save(res); continue
        if not h.get("ok"):
            res[name] = dict(status="НЕ_ОТКРЫЛАСЬ", detail=h.get("note", "")[:120]); _save(res); continue

        cs, store, call = h["candles"], h["store"], h["call"]
        n = len(cs)
        c = np.array([x.c for x in cs]); hi = np.array([x.h for x in cs]); lo = np.array([x.l for x in cs])
        pc = np.r_[c[0], c[:-1]]
        tr = np.maximum.reduce([hi - lo, np.abs(hi - pc), np.abs(lo - pc)])
        atr = pd.Series(tr).ewm(alpha=1 / ATR_N, adjust=False, min_periods=ATR_N).mean().to_numpy()
        ts = pd.to_datetime([x.ts for x in cs], unit="ms", utc=True)
        iso = ts.isocalendar()
        wk = iso.year.to_numpy() * 100 + iso.week.to_numpy()

        idx, sides, known = [], [], 0
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
                    s_, ok_ = side_of(r)
                    idx.append(i); sides.append(s_); known += int(ok_)
            slow = False
        except _Slow:
            slow = True
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

        if slow:
            res[name] = dict(
                status="TIMEOUT_INCOMPLETE",
                symbol=h["symbol"],
                partial_signals=len(idx),
                timeout_seconds=PER,
                detail="частичный прогон запрещён к интерпретации",
            )
            _save(res)
            continue
        if not idx:
            res[name] = dict(status="НЕТ_СИГНАЛОВ", slow=slow); _save(res); continue
        idx = np.array(idx); sides = np.array(sides, float)

        row = dict(status="ОК", symbol=h["symbol"], conv=h["conv"], bars=n,
                   signals=len(idx), side_known=round(known / len(idx), 2), slow=slow)
        base_idx = np.arange(0, n, 288)
        for lab, hb in HOR_BARS.items():
            ok = idx + hb < n
            if ok.sum() < 20:
                continue
            j = idx[ok]
            move = (c[j + hb] - c[j]) / atr[j] * sides[ok]
            bj = base_idx[base_idx + hb < n]
            bmove = (c[bj + hb] - c[bj]) / atr[bj]
            m, t, nn, kk = boot_t(move, wk[j])
            row[lab] = dict(n=nn, weeks=kk, atr=round(float(m), 3),
                            t=round(float(t), 2) if np.isfinite(t) else None,
                            base_atr=round(float(np.nanmean(bmove)), 3),
                            excess=round(float(m - np.nanmean(bmove)), 3))
        res[name] = row
        _save(res)
        e24 = row.get("24ч", {})
        print(f"{name:<34} сиг={len(idx):<5} стороны={row['side_known']:.0%}  "
              f"24ч: {e24.get('excess')} ATR  t={e24.get('t')}", flush=True)

    _save(res)
    print(f"[сохранено] {len(res)} -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
