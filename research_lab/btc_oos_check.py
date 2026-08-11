#!/usr/bin/env python3
"""
btc_oos_check.py — гипотеза «работает на BTC» на НЕТРОНУТЫХ периодах.

ЗАЧЕМ. Нога дала 17 плюсовых горизонтов из 17 на BTC и развалилась на DOT.
Это может значить две разные вещи:
   а) подгонка — из четырёх монет одна случайно легла хорошо;
   б) нога действительно про BTC: самый ликвидный инструмент, самый узкий
      круг издержек, своя микроструктура. У владельца уже есть нога
      только по мажорам, так что гипотеза законная.

Отличить можно только одним способом: проверить BTC на периодах, которых
не было при получении результата. Исходный прогон брал ПОСЛЕДНИЕ 40 000
пятиминуток. Здесь берутся три более ранних непересекающихся окна.

Критерий объявлен ДО прогона:
   гипотеза «работает на BTC» ЖИВА, если доля плюсовых горизонтов
   >= 70% в КАЖДОМ из трёх окон и медиана избытка положительна везде.
   Иначе — подгонка под окно.
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

NAME = sys.argv[1] if len(sys.argv) > 1 else "alt_elder_revived_v1"
SYM = sys.argv[2] if len(sys.argv) > 2 else "BTCUSDT"
WIN = 40000                      # размер окна в 5-минутках (~139 дней)
N_WIN = 4                        # 0 = исходное (последнее), 1..3 — более ранние
HOURS = (1, 2, 3, 4, 6, 8, 12, 16, 24, 36, 48, 72)
ATR_N = 24
PER = 12.0


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


def boot_t(v, weeks, n_boot=600, seed=5):
    v = np.asarray(v, float); ok = np.isfinite(v)
    v, w = v[ok], np.asarray(weeks)[ok]
    if len(v) < 15:
        return np.nan, np.nan
    uw, inv = np.unique(w, return_inverse=True); k = len(uw)
    s = np.bincount(inv, weights=v, minlength=k)
    c = np.bincount(inv, minlength=k).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, k, size=(n_boot, k))
    bs = s[pick].sum(1) / np.maximum(c[pick].sum(1), 1)
    m, se = float(v.mean()), float(bs.std(ddof=1))
    return m, (m / se if se > 0 else np.nan)


def window(shift):
    """Окно со сдвигом назад: shift=0 — последнее (исходное), 1 — предыдущее."""
    h = A.open_strategy(NAME, symbol=SYM, limit=WIN * (shift + 1))
    if not h.get("ok") or h["symbol"] != SYM:
        return None, h.get("note", "не открылась")[:70]
    cs = h["candles"]
    if len(cs) < WIN * (shift + 1) * 0.9:
        return None, f"мало истории: {len(cs)} баров"
    cs = cs[:WIN] if shift else cs[-WIN:]
    if shift:
        # берём именно нужный кусок с конца
        full = h["candles"]
        lo = max(0, len(full) - WIN * (shift + 1))
        cs = full[lo:lo + WIN]
    from backtest.engine import KlineStore
    store = KlineStore(SYM, cs, base_interval_min=5)
    call = A.make_caller(h["conv"], h["obj"], SYM)

    n = len(cs)
    c = np.array([x.c for x in cs]); hi = np.array([x.h for x in cs]); lo_ = np.array([x.l for x in cs])
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum.reduce([hi - lo_, np.abs(hi - pc), np.abs(lo_ - pc)])
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
                idx.append(i); sides.append(side_of(r))
    except _Slow:
        timed_out = True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)

    if timed_out:
        return None, f"таймаут {PER:.0f}s: частичный набор из {len(idx)} сигналов запрещён"

    if len(idx) < 15:
        return None, f"сигналов {len(idx)}"
    idx = np.array(idx); sides = np.array(sides, float)
    atr_pct = float(np.nanmedian(atr / c))
    cost = (16e-4) / atr_pct if atr_pct > 0 else 0.0

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
        m, t = boot_t(move - base, wk[j])
        grid.append(dict(hours=hrs, n=int(ok.sum()), excess=round(float(m), 3),
                         net=round(float(m - cost), 3),
                         t=round(float(t), 2) if np.isfinite(t) else None))
    return dict(shift=shift, start=str(ts[0].date()), end=str(ts[-1].date()),
                signals=len(idx), cost_atr=round(cost, 2), grid=grid), ""


def main():
    out = "research_lab/results/microscope"
    os.makedirs(out, exist_ok=True)
    fp = os.path.join(out, f"{NAME}__{SYM}_oos.json")
    acc = json.load(open(fp)) if os.path.exists(fp) else {}
    print(f"{NAME} на {SYM}: {N_WIN} окна по {WIN} баров\n")
    for sh in range(N_WIN):
        k = str(sh)
        if k in acc:
            continue
        try:
            r, err = window(sh)
        except Exception as e:
            r, err = None, f"{type(e).__name__}: {e}"[:70]
        acc[k] = r if r else dict(shift=sh, skipped=err)
        json.dump(acc, open(fp, "w"), ensure_ascii=False, indent=2)
        if r:
            pos = np.mean([g["excess"] > 0 for g in r["grid"]])
            posn = np.mean([g["net"] > 0 for g in r["grid"]])
            med = np.median([g["excess"] for g in r["grid"]])
            tag = "ИСХОДНОЕ" if sh == 0 else "НЕТРОНУТОЕ"
            print(f"  окно {sh} [{tag:<10}] {r['start']}..{r['end']}  сиг={r['signals']:<4} "
                  f"плюсовых {pos:.0%}  после круга {posn:.0%}  медиана {med:+.2f}", flush=True)
        else:
            print(f"  окно {sh}: пропуск — {err}", flush=True)

    good = [v for v in acc.values() if v.get("grid")]
    oos = [v for v in good if v["shift"] > 0]
    if oos:
        print("\n═══ ВЕРДИКТ ═══")
        allpos = [np.mean([g["excess"] > 0 for g in v["grid"]]) for v in oos]
        allmed = [np.median([g["excess"] for g in v["grid"]]) for v in oos]
        ok = all(p >= 0.7 for p in allpos) and all(m > 0 for m in allmed)
        print(f"  нетронутых окон: {len(oos)}")
        print(f"  доля плюсовых по окнам: {[f'{p:.0%}' for p in allpos]}")
        print(f"  медианы по окнам:       {[f'{m:+.2f}' for m in allmed]}")
        print(f"  гипотеза «работает на {SYM}»: {'ЖИВА' if ok else 'НЕ ПОДТВЕРДИЛАСЬ'}")
    print(f"\n[сохранено] {fp}")


if __name__ == "__main__":
    main()
