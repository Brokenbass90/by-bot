#!/usr/bin/env python3
"""
window_forensics.py — почему нога потеряла именно в этом окне.

ЗАДАЧА. inplay_breakout на ETH бьёт случайный вход в трёх окнах из
четырёх (92-100%) и проваливается в одном. Направлением рынка это НЕ
объясняется: в окне 1 эфир упал на 36% и нога заработала, в окне 3 упал
на 27% и потеряла. Значит причина в другом, и она — путь к винрейту.

ЧТО ПРОВЕРЯЕТСЯ (пять гипотез, все сразу, чтобы не подгонять):

  H1 ВОЛАТИЛЬНОСТЬ   в плохом окне ATR/цена другой, и стоп неверного размера
  H2 ВЫБИВАНИЕ       доля сделок, закрытых стопом, а не по горизонту
  H3 ОДИН УБЫТОК     потеря сосредоточена в паре сделок или размазана
  H4 КУЧНОСТЬ        сигналы сбились в одну плохую полосу
  H5 ПИЛА            рынок ходил рвано: ATR большой, а чистый ход маленький

Печатается таблица по всем четырём окнам, чтобы плохое окно можно было
СРАВНИТЬ, а не описать. Ответ должен быть в виде «в окне 3 показатель X
отличается в N раз», иначе это не диагноз.
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
OUT = "research_lab/results/forensics"


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
    return +1


def analyse(sh):
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
    R, stopped, mfe_l = [], [], []
    for j, s in zip(idx, sides):
        if j + hb >= n or not np.isfinite(atr[j]) or atr[j] <= 0:
            continue
        risk = st * atr[j]
        entry = c[j]
        stop = entry - s * risk
        hit = False
        for k in range(j + 1, j + hb + 1):
            if (s > 0 and lo[k] <= stop) or (s < 0 and hi[k] >= stop):
                hit = True
                break
        r = -1.0 if hit else s * (c[j + hb] - entry) / risk
        r -= (COST_BPS / 1e4) * entry / risk
        R.append(r); stopped.append(hit)
        seg = slice(j + 1, j + hb + 1)
        mfe_l.append(s * (np.max(hi[seg]) if s > 0 else -np.min(lo[seg])) / risk
                     - s * entry / risk)
    R = np.array(R); stopped = np.array(stopped)
    if len(R) < 15:
        return None

    # H5 «пила»: сколько чистого хода на единицу пройденного пути
    step = np.abs(np.diff(c))
    eff = float(np.abs(c[-1] - c[0]) / step.sum()) if step.sum() > 0 else 0.0
    # вклад худших трёх сделок
    worst3 = float(np.sort(R)[:3].sum() / len(R))

    return dict(
        window=sh, start=str(ts[0].date()), end=str(ts[-1].date()),
        eth=round(float(c[-1] / c[0] - 1) * 100, 1),
        trades=len(R), R=round(float(R.mean()), 3), wr=round(float((R > 0).mean()), 3),
        atr_pct=round(float(np.nanmedian(atr / c)) * 100, 3),
        stop_rate=round(float(stopped.mean()), 3),
        worst3_share=round(worst3 / R.mean() if R.mean() != 0 else 0, 2),
        worst3_R=round(worst3, 3),
        mfe=round(float(np.mean(mfe_l)), 2),
        efficiency=round(eff * 100, 2),
        signals_per_1000bars=round(len(R) / n * 1000, 2),
    )


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for sh in range(N_WIN):
        try:
            r = analyse(sh)
        except Exception as e:
            print(f"окно {sh}: {type(e).__name__}: {e}"[:100], flush=True)
            r = None
        if r:
            rows.append(r)
            print(f"окно {sh} готово", flush=True)
    if not rows:
        return
    df = pd.DataFrame(rows).set_index("window")
    cols = ["start", "eth", "trades", "R", "wr", "atr_pct", "stop_rate",
            "worst3_R", "mfe", "efficiency", "signals_per_1000bars"]
    names = {"eth": "ETH%", "R": "R/сделку", "wr": "винрейт", "atr_pct": "ATR/цена%",
             "stop_rate": "доля стопов", "worst3_R": "3 худших", "mfe": "макс.ход",
             "efficiency": "прямота%", "signals_per_1000bars": "сигн/1000"}
    print("\n" + df[cols].rename(columns=names).to_string())
    bad = df["R"].idxmin()
    good = df.drop(index=bad)
    print(f"\n═══ ОКНО {bad} ПРОТИВ ОСТАЛЬНЫХ ═══")
    for k, lab in (("atr_pct", "H1 волатильность"), ("stop_rate", "H2 доля стопов"),
                   ("worst3_R", "H3 три худших сделки"), ("signals_per_1000bars", "H4 частота"),
                   ("efficiency", "H5 прямота хода"), ("mfe", "макс.ход в пользу")):
        b, g = float(df.loc[bad, k]), float(good[k].mean())
        ratio = b / g if g else float("nan")
        flag = "  <<< ОТЛИЧАЕТСЯ" if (ratio > 1.4 or ratio < 0.71) else ""
        print(f"  {lab:<22} плохое {b:>8.3f}   остальные {g:>8.3f}   x{ratio:.2f}{flag}")
    df.to_json(os.path.join(OUT, f"{NAME}__{SYM}.json"), orient="records",
               force_ascii=False, indent=2)
    print(f"\n[сохранено] {OUT}/{NAME}__{SYM}.json")


if __name__ == "__main__":
    main()
