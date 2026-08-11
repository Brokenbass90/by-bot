#!/usr/bin/env python3
"""
leg_microscope.py — одна нога под микроскопом.

Порядок из роадмапа (фаза 2.2), шаг не пропускается:
    1. проба живости      -> сделано переписью
    2. МНОГО СИМВОЛОВ     <- здесь: находка на одной монете не находка
    3. сетка горизонтов   -> распределение, а не чемпион
    4. состояние битка    -> помогает ли поводырь
    5. издержки           -> переживает ли эдж круг
    6. карточка           -> запись для Codex

ГЛАВНОЕ ПРАВИЛО ОТЧЁТА: печатается доля плюсовых по семейству, а не лучший
вариант. Порог для чемпиона поднимается по числу ВСЕХ проверок разом
(sqrt(2*ln N)), а не по числу проверок внутри одного символа.

    python3 research_lab/leg_microscope.py <стратегия> [символы через запятую]
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


def side_of(sig):
    """Сторона сигнала. Копия из strategy_edge_probe — импортировать нельзя,
    там разбор argv на уровне модуля и он ломается о чужие аргументы."""
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

NAME = sys.argv[1] if len(sys.argv) > 1 else "alt_elder_revived_v1"
SYMS = (sys.argv[2].split(",") if len(sys.argv) > 2 else
        ["DOTUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT",
         "ADAUSDT", "ATOMUSDT", "XRPUSDT", "LTCUSDT", "INJUSDT"])
BARS = 40000
HOURS = (1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 48, 72)
PER = 11.0
ATR_N = 24
COST_ATR = 0.0            # заполняется ниже из реальной волатильности
OUT = "research_lab/results/microscope"


class _Slow(Exception):
    pass


signal.signal(signal.SIGALRM, lambda s, f: (_ for _ in ()).throw(_Slow()))


def boot_t(v, weeks, n_boot=800, seed=5):
    v = np.asarray(v, float); ok = np.isfinite(v)
    v, w = v[ok], np.asarray(weeks)[ok]
    if len(v) < 15:
        return np.nan, np.nan, 0
    uw, inv = np.unique(w, return_inverse=True); k = len(uw)
    s = np.bincount(inv, weights=v, minlength=k)
    c = np.bincount(inv, minlength=k).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, k, size=(n_boot, k))
    bs = s[pick].sum(1) / np.maximum(c[pick].sum(1), 1)
    m, se = float(v.mean()), float(bs.std(ddof=1))
    return m, (m / se if se > 0 else np.nan), k


def run_symbol(name, sym):
    h = A.open_strategy(name, symbol=sym, limit=BARS)
    if not h.get("ok"):
        return None, h.get("note", "")[:80]
    # аллоулист может увести пробу на другой символ — тогда результат не про sym
    if h["symbol"] != sym:
        return None, f"аллоулист увёл на {h['symbol']}"

    cs, store, call = h["candles"], h["store"], h["call"]
    n = len(cs)
    c = np.array([x.c for x in cs]); hi = np.array([x.h for x in cs]); lo = np.array([x.l for x in cs])
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([hi - lo, np.abs(hi - pc), np.abs(lo - pc)])
    atr = pd.Series(tr).ewm(alpha=1 / ATR_N, adjust=False, min_periods=ATR_N).mean().to_numpy()
    ts = pd.to_datetime([x.ts for x in cs], unit="ms", utc=True)
    iso = ts.isocalendar(); wk = iso.year.to_numpy() * 100 + iso.week.to_numpy()

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
                s_, _ = side_of(r); idx.append(i); sides.append(s_)
    except _Slow:
        timed_out = True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)

    if timed_out:
        return None, f"таймаут {PER:.0f}s: частичный набор из {len(idx)} сигналов запрещён"

    if len(idx) < 15:
        return None, f"сигналов {len(idx)}"
    idx = np.array(idx); sides = np.array(sides, float)
    # круг в единицах ATR: 16 bps издержек делим на типичный ATR/цена
    atr_pct = float(np.nanmedian(atr / c))
    cost_atr = (16e-4) / atr_pct if atr_pct > 0 else 0.0

    grid = []
    for hrs in HOURS:
        hb = hrs * 12
        ok = idx + hb < n
        if ok.sum() < 15:
            continue
        j = idx[ok]
        move = (c[j + hb] - c[j]) / atr[j] * sides[ok]
        bj = np.arange(0, n - hb, 288)
        base = float(np.nanmean((c[bj + hb] - c[bj]) / atr[bj]))
        m, t, k = boot_t(move - base, wk[j])
        grid.append(dict(hours=hrs, n=int(ok.sum()), weeks=k,
                         excess=round(float(m), 3),
                         net=round(float(m - cost_atr), 3),
                         t=round(float(t), 2) if np.isfinite(t) else None))
    return dict(symbol=sym, signals=len(idx), cost_atr=round(cost_atr, 3), grid=grid), ""


def main():
    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(OUT, f"{NAME}.json")
    acc = json.load(open(fp)) if os.path.exists(fp) else {}
    todo = [s for s in SYMS if s not in acc]
    print(f"нога: {NAME}\nсимволов осталось: {len(todo)} из {len(SYMS)}\n", flush=True)

    t0 = time.time()
    for sym in todo:
        if time.time() - t0 > 30:
            print("[бюджет] запусти ещё раз", flush=True)
            break
        try:
            r, err = run_symbol(NAME, sym)
        except Exception as e:
            r, err = None, f"{type(e).__name__}: {e}"[:80]
        acc[sym] = r if r else dict(symbol=sym, skipped=err)
        json.dump(acc, open(fp, "w"), ensure_ascii=False, indent=2)
        if r:
            pos = np.mean([g["excess"] > 0 for g in r["grid"]])
            med = np.median([g["excess"] for g in r["grid"]])
            best = max(r["grid"], key=lambda g: abs(g["t"] or 0))
            print(f"  {sym:<10} сиг={r['signals']:<5} плюсовых {pos:.0%}  медиана {med:+.2f}  "
                  f"чемпион {best['hours']}ч t={best['t']}  круг={r['cost_atr']:.2f} ATR", flush=True)
        else:
            print(f"  {sym:<10} пропуск: {err}", flush=True)

    ok = [v for v in acc.values() if v.get("grid")]
    if len(ok) >= 2:
        allg = [g for v in ok for g in v["grid"]]
        N = len(allg)
        bar = math.sqrt(2 * math.log(max(N, 2)))
        pos = np.mean([g["excess"] > 0 for g in allg])
        posnet = np.mean([g["net"] > 0 for g in allg])
        med = np.median([g["excess"] for g in allg])
        champ = max(allg, key=lambda g: abs(g["t"] or 0))
        by_sym = {v["symbol"]: round(float(np.median([g["excess"] for g in v["grid"]])), 2) for v in ok}
        print(f"\n═══ ИТОГ ПО {len(ok)} СИМВОЛАМ ═══")
        print(f"  всего вариантов        {N}")
        print(f"  плюсовых (до издержек) {pos:.0%}")
        print(f"  плюсовых (ПОСЛЕ круга) {posnet:.0%}")
        print(f"  медиана избытка        {med:+.2f} ATR")
        print(f"  медиана по символам    {by_sym}")
        print(f"  чемпион                {champ['hours']}ч  t={champ['t']}   порог |t|>={bar:.2f}")
        print(f"  ВЕРДИКТ: {'семейство держится' if pos >= 0.7 and posnet >= 0.5 else 'семейство не держится'}"
              f" | чемпион {'бьёт порог' if abs(champ['t'] or 0) >= bar else 'в пределах шума'}")
    print(f"\n[сохранено] {fp}")


if __name__ == "__main__":
    main()
