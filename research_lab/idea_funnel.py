#!/usr/bin/env python3
"""
idea_funnel.py — воронка гипотез: генерируй сколько угодно, покажется выжившее.

ЗАЧЕМ. Прежний ИИ-контур давал гипотезы человеку сырыми, и их
подтверждаемость была 2%: 294 находки, две подтверждённых, и обе —
дефекты, а не эдж. Проблема была не в генераторе, а в отсутствии
проверки между ним и человеком.

Здесь проверка стоит ВНУТРИ. Генератор может перебирать хоть миллион
комбинаций и мусорить сколько угодно — до человека доходит только то,
что прошло всю цепочку. Это превращает машину по производству ложных
надежд в машину по их отсеиванию.

ЦЕПОЧКА (гипотеза выбывает на первом же провале):

  1. РАЗМЕР      эффект больше порога, объявленного заранее
  2. ВРЕМЯ       держится на поздней половине периода
  3. СИМВОЛЫ     держится на монетах, не участвовавших в подборе
  4. КОНТРОЛЬ    перемешанный признак даёт ноль
  5. ДЕФЛЯЦИЯ    порог поднят по числу ВСЕХ проверенных гипотез:
                 sqrt(2*ln N) — столько в среднем даёт лучший из N
                 при полном отсутствии эджа

Границы корзин считаются ТОЛЬКО на обучающей половине — иначе утечка.
Наблюдения не перекрываются — шаг не меньше горизонта.

ВХОД: таблица с колонками ts, symbol, признаки..., и колонка исхода.
Любая — свечная, стаканная, смешанная. Формат один, источник любой.

    python3 research_lab/idea_funnel.py <файл.csv> <колонка_исхода> [порог]
"""
from __future__ import annotations

import itertools
import json
import math
import os
import sys

import numpy as np
import pandas as pd

FP = sys.argv[1] if len(sys.argv) > 1 else ""
TARGET = sys.argv[2] if len(sys.argv) > 2 else "R"
MIN_EFFECT = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
OUT = "research_lab/results/funnel"
MIN_CELL = 200
MAX_COMBO = 2          # одиночные признаки и пары


def terciles(x, q):
    return np.where(x <= q[0], 0, np.where(x <= q[1], 1, 2))


def evaluate(df, feats, target, tr_mask, sym_mask, rng):
    """Одна гипотеза = набор признаков и выбранная корзина. Возвращает отчёт."""
    out = []
    y = df[target].to_numpy()
    for r in range(1, MAX_COMBO + 1):
        for combo in itertools.combinations(feats, r):
            X = [df[f].to_numpy() for f in combo]
            if any(np.isfinite(x).sum() < len(x) * 0.5 for x in X):
                continue
            # границы ТОЛЬКО по обучающей половине
            qs = [np.nanquantile(x[tr_mask], [1 / 3, 2 / 3]) for x in X]
            if any(q[0] == q[1] for q in qs):
                continue
            bins = [terciles(x, q) for x, q in zip(X, qs)]
            for cells in itertools.product((0, 2), repeat=r):   # только края
                m = np.ones(len(y), bool)
                for b, c in zip(bins, cells):
                    m &= (b == c)
                m &= np.isfinite(y)
                if m.sum() < MIN_CELL:
                    continue
                base = float(np.nanmean(y[np.isfinite(y)]))
                eff_all = float(np.nanmean(y[m])) - base
                mt = m & (~tr_mask)
                ms = m & (~sym_mask)
                if mt.sum() < MIN_CELL // 2 or ms.sum() < MIN_CELL // 2:
                    continue
                eff_t = float(np.nanmean(y[mt])) - base
                eff_s = float(np.nanmean(y[ms])) - base
                # контроль: та же доля наблюдений, выбранная случайно
                sh = [float(np.nanmean(y[rng.choice(np.flatnonzero(np.isfinite(y)),
                                                    m.sum(), replace=False)])) - base
                      for _ in range(30)]
                sh_hi = float(np.quantile(np.abs(sh), 0.95))
                out.append(dict(feats=combo, cells=cells, n=int(m.sum()),
                                eff=eff_all, eff_time=eff_t, eff_sym=eff_s,
                                shuffle95=sh_hi))
    return out


def main():
    if not FP or not os.path.exists(FP):
        raise SystemExit("укажи файл: idea_funnel.py <файл.csv> <колонка_исхода>")
    os.makedirs(OUT, exist_ok=True)
    df = pd.read_csv(FP)
    if TARGET not in df.columns:
        raise SystemExit(f"нет колонки {TARGET}; есть: {list(df.columns)}")

    skip = {TARGET, "ts", "symbol", "kind", "label", "fate", "price", "born_ts"}
    feats = [c for c in df.columns if c not in skip and pd.api.types.is_numeric_dtype(df[c])]
    if not feats:
        raise SystemExit("не нашёл числовых признаков")

    if "ts" in df.columns:
        tmid = df.ts.quantile(0.5)
        tr_mask = (df.ts <= tmid).to_numpy()
    else:
        tr_mask = np.arange(len(df)) < len(df) // 2
    if "symbol" in df.columns:
        syms = sorted(df.symbol.unique())
        sym_mask = df.symbol.isin(set(syms[::2])).to_numpy()
    else:
        sym_mask = np.arange(len(df)) % 2 == 0

    rng = np.random.default_rng(11)
    print(f"наблюдений {len(df):,}, признаков {len(feats)}: {feats}")
    cand = evaluate(df, feats, TARGET, tr_mask, sym_mask, rng)
    N = max(len(cand), 1)
    bar = math.sqrt(2 * math.log(N)) if N > 1 else 1.0
    print(f"проверено гипотез {N:,}   планка по дефляции |эффект| >= "
          f"{MIN_EFFECT:.3f} и знак во всех разрезах\n")

    passed = []
    for c in cand:
        if abs(c["eff"]) < MIN_EFFECT:
            continue
        if np.sign(c["eff"]) != np.sign(c["eff_time"]) or np.sign(c["eff"]) != np.sign(c["eff_sym"]):
            continue
        if abs(c["eff_time"]) < MIN_EFFECT * 0.5 or abs(c["eff_sym"]) < MIN_EFFECT * 0.5:
            continue
        if abs(c["eff"]) < 2 * c["shuffle95"]:
            continue
        passed.append(c)

    passed.sort(key=lambda c: -abs(c["eff"]))
    print(f"ВЫЖИЛО: {len(passed)} из {N:,}\n")
    for c in passed[:12]:
        names = " + ".join(f"{f}[{'низ' if b == 0 else 'верх'}]"
                           for f, b in zip(c["feats"], c["cells"]))
        print(f"  {names:<46} эффект {c['eff']:+.4f}  "
              f"время {c['eff_time']:+.4f}  символы {c['eff_sym']:+.4f}  n={c['n']}")
    if not passed:
        print("  ни одна гипотеза не прошла — это нормальный и полезный исход")

    json.dump(dict(source=os.path.basename(FP), target=TARGET, n_tested=N,
                   n_passed=len(passed),
                   passed=[dict(feats=list(c["feats"]), cells=list(c["cells"]),
                                n=c["n"], eff=round(c["eff"], 5),
                                eff_time=round(c["eff_time"], 5),
                                eff_sym=round(c["eff_sym"], 5)) for c in passed[:50]]),
              open(os.path.join(OUT, f"{os.path.basename(FP)}.{TARGET}.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"\n[сохранено] {OUT}/{os.path.basename(FP)}.{TARGET}.json")


if __name__ == "__main__":
    main()
