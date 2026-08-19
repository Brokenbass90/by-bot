#!/usr/bin/env python3
"""
l2_density_edge.py — есть ли в плитах торгуемый эдж, честный ответ.

ПОРЯДОК, объявлен до просмотра чисел:

  1. ОТБОР идёт только на первом дне (11 августа). Границы корзин,
     выбор признаков, выбор корзины — всё там.
  2. ПОДТВЕРЖДЕНИЕ только на втором дне (12 августа). Это другой день,
     а не другая половина того же дня.
  3. ОШИБКА считается блочным бутстрапом по 30-минутным блокам.
     Наблюдения перекрываются (плит одновременно живёт много), поэтому
     обычная ошибка по числу строк завышена в разы. Блок длиннее
     горизонта, значит блоки почти независимы.
  4. ПЛАНКА поднята по числу проверенных гипотез: sqrt(2*ln N) —
     столько в среднем даёт лучшая из N пустышек.
  5. ЛИНИЯ ИЗДЕРЖЕК рисуется рядом всегда. Тейкер круг = 16 bps
     (6 комиссия + 2 проскальзывание на сторону). Мейкер-мейкер круг
     = 2 bps ребейта/комиссии плюс спред-риск. Эффект меньше линии
     не является стратегией, максимум — подсказка исполнению.

КРИТЕРИЙ СМЕРТИ, объявлен заранее: если ни одна гипотеза не даёт на
втором дне эффект, чей нижний край 95% доверительного интервала больше
нуля И больше 2 bps, плотности закрываются как источник сигнала
и остаются инструментом исполнения.
"""
from __future__ import annotations

import itertools
import json
import math
import sys

import numpy as np
import pandas as pd

FP = sys.argv[1] if len(sys.argv) > 1 else "density_obs.csv"
TARGET = sys.argv[2] if len(sys.argv) > 2 else "fwd_300s"
BLOCK_MS = 30 * 60_000
MIN_CELL = 300
FEATS = (sys.argv[3].split(",") if len(sys.argv) > 3 else
         ["dist_bps", "size_x", "grow", "eaten_now", "imb_toward", "spread_bps", "vol_bps"])
TAKER_BPS = 16.0
MAKER_BPS = 2.0
DEATH_BPS = 2.0


def block_boot(y, blocks, n=2000, seed=7):
    """Средняя по блочному бутстрапу: 95% интервал."""
    ub = np.unique(blocks)
    if len(ub) < 4:
        return float(np.mean(y)), float("nan"), float("nan")
    idx = {b: np.flatnonzero(blocks == b) for b in ub}
    rng = np.random.default_rng(seed)
    means = np.empty(n)
    for i in range(n):
        pick = rng.choice(ub, len(ub), replace=True)
        sel = np.concatenate([idx[b] for b in pick])
        means[i] = y[sel].mean()
    return float(np.mean(y)), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def main():
    df = pd.read_csv(FP)
    df = df[np.isfinite(df[TARGET])].reset_index(drop=True)
    df["block"] = (df.ts // BLOCK_MS).astype(np.int64)
    print(f"наблюдений {len(df):,}   дней {df.day.nunique()}   "
          f"символов {df.symbol.nunique()}   блоков по 30 мин {df.block.nunique()}")

    days = sorted(df.day.unique())
    tr, te = df[df.day == days[0]], df[df.day == days[-1]]
    print(f"отбор на {days[0]} ({len(tr):,} набл.), проверка на {days[-1]} ({len(te):,} набл.)\n")

    for lag in sorted(df.lag_s.unique()):
        base_tr = tr[tr.lag_s == lag][TARGET].mean()
        base_te = te[te.lag_s == lag][TARGET].mean()
        print(f"лаг {lag:>2} с: средний ход к плите за {TARGET[4:]}  "
              f"отбор {base_tr:+.3f} bps   проверка {base_te:+.3f} bps")
    print()

    # ---- перебор гипотез на дне отбора ----
    cands = []
    for lag in sorted(df.lag_s.unique()):
        a, b = tr[tr.lag_s == lag], te[te.lag_s == lag]
        if len(a) < MIN_CELL * 3:
            continue
        qs = {f: np.nanquantile(a[f], [1 / 3, 2 / 3]) for f in FEATS}
        qs = {f: q for f, q in qs.items() if q[0] < q[1]}
        bins_a = {f: np.digitize(a[f], qs[f]) for f in qs}
        bins_b = {f: np.digitize(b[f], qs[f]) for f in qs}
        ya, yb = a[TARGET].to_numpy(), b[TARGET].to_numpy()
        base_a = ya.mean()
        for r in (1, 2):
            for combo in itertools.combinations(qs, r):
                for cells in itertools.product((0, 2), repeat=r):
                    ma = np.ones(len(a), bool)
                    mb = np.ones(len(b), bool)
                    for f, c in zip(combo, cells):
                        ma &= bins_a[f] == c
                        mb &= bins_b[f] == c
                    if ma.sum() < MIN_CELL or mb.sum() < MIN_CELL:
                        continue
                    cands.append(dict(lag=lag, feats=combo, cells=cells,
                                      eff_tr=float(ya[ma].mean() - base_a),
                                      n_tr=int(ma.sum()), n_te=int(mb.sum()),
                                      mask_te=mb, y_te=yb, blk_te=b.block.to_numpy(),
                                      base_te=float(yb.mean())))
    N = len(cands)
    bar = math.sqrt(2 * math.log(max(N, 2)))
    print(f"проверено гипотез {N}   дефляционная планка по t: {bar:.2f}\n")

    cands.sort(key=lambda c: -abs(c["eff_tr"]))
    print("ЛУЧШИЕ НА ДНЕ ОТБОРА, проверены на другом дне (bps, + = цена идёт к плите):\n")
    print(f"{'признак':<44}{'лаг':>4}{'отбор':>9}{'проверка':>10}{'95% интервал проверки':>26}{'n':>8}")
    rows = []
    for c in cands[:12]:
        y = c["y_te"][c["mask_te"]]
        blk = c["blk_te"][c["mask_te"]]
        m, lo, hi = block_boot(y - c["base_te"], blk)
        name = " + ".join(f"{f}[{'низ' if x == 0 else 'верх'}]" for f, x in zip(c["feats"], c["cells"]))
        print(f"{name:<44}{c['lag']:>4}{c['eff_tr']:>+9.3f}{m:>+10.3f}"
              f"{f'[{lo:+.3f} .. {hi:+.3f}]':>26}{c['n_te']:>8}")
        rows.append(dict(feats=list(c["feats"]), cells=list(c["cells"]), lag=int(c["lag"]),
                         eff_train=round(c["eff_tr"], 4), eff_test=round(m, 4),
                         lo=round(lo, 4), hi=round(hi, 4), n_test=int(c["n_te"])))

    alive = [r for r in rows if r["lo"] > 0 and r["lo"] > DEATH_BPS]
    print(f"\nЛИНИЯ ИЗДЕРЖЕК: тейкер круг {TAKER_BPS} bps, мейкер круг ~{MAKER_BPS} bps, "
          f"критерий смерти: нижний край > {DEATH_BPS} bps")
    if alive:
        print(f"ВЫЖИЛО: {len(alive)}")
    else:
        best = max((r for r in rows), key=lambda r: r["lo"], default=None)
        print("ВЫЖИЛО: 0 — плотности закрываются как источник сигнала.")
        if best:
            print(f"   лучший нижний край: {best['lo']:+.3f} bps "
                  f"({' + '.join(best['feats'])}, лаг {best['lag']} с)")
    json.dump(dict(target=TARGET, n_tested=N, rows=rows, alive=len(alive)),
              open(f"density_edge.{TARGET}.{len(FEATS)}f.json", "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
