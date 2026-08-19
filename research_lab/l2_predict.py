#!/usr/bin/env python3
"""
l2_predict.py — предсказывает ли стакан ближайшее движение цены.

ЗАЧЕМ ИМЕННО ЭТОТ ВОПРОС ПЕРВЫМ. Все провалы этих исследований имеют
один корень: не хватало наблюдений. 426 сделок у лучшей ноги, 43 тысячи
событий у детектора уровней — на таких выборках маленький эдж
неотличим от шума. Стакан даёт наблюдение каждую секунду. Здесь
мощность впервые соответствует размеру искомого эффекта.

ВОПРОС. Дисбаланс книги (объём на покупку против объёма на продажу)
сдвигает ли середину в ближайшие секунды и минуты.

ПРОВЕРКА, с учётом трёх замечаний к прошлому детектору:
  * корзины строятся ТОЛЬКО на обучающей половине и применяются
    к проверочной — без утечки границ;
  * наблюдения не перекрываются: шаг между ними не меньше горизонта;
  * контроль — сдвиг признака во времени: если «предсказание»
    сохраняется при перемешанном признаке, это артефакт.

Результат в базисных пунктах. Рядом всегда стоит спред — движение
меньше спреда торговать нельзя.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

import numpy as np

SRC = sys.argv[1] if len(sys.argv) > 1 else "research_lab/results/l2"
HOR_S = (5, 15, 60, 300)          # горизонты в секундах
OUT = "research_lab/results/l2"


def load(fp):
    rows = []
    with open(fp) as fh:
        for r in csv.DictReader(fh):
            rows.append({k: float(v) for k, v in r.items()})
    return rows


def analyse(rows, step_ms=1000):
    ts = np.array([r["ts"] for r in rows])
    mid = np.array([r["mid"] for r in rows])
    spread = np.array([r["spread_bps"] for r in rows])
    feats = {k: np.array([r[k] for r in rows]) for k in ("imb1", "imb5", "imb20", "slope")}
    n = len(rows)
    print(f"наблюдений {n:,}, шаг {step_ms} мс, медианный спред {np.median(spread):.4f} bps\n")

    half = n // 2
    out = {}
    for hs in HOR_S:
        step = max(1, int(hs * 1000 / step_ms))          # неперекрывающиеся
        idx = np.arange(0, n - step, step)
        fwd = (mid[idx + step] / mid[idx] - 1.0) * 1e4    # bps
        tr_mask = idx < half                              # обучение = первая половина
        print(f"═══ горизонт {hs} с   наблюдений {len(idx):,}   "
              f"|ход| медиана {np.median(np.abs(fwd)):.2f} bps")
        for fname, arr in feats.items():
            x = arr[idx]
            if tr_mask.sum() < 200 or (~tr_mask).sum() < 200:
                continue
            # ГРАНИЦЫ ТОЛЬКО ПО ОБУЧАЮЩЕЙ ПОЛОВИНЕ — без утечки
            q = np.quantile(x[tr_mask], [1 / 3, 2 / 3])
            b = np.where(x <= q[0], 0, np.where(x <= q[1], 1, 2))
            tr = [float(np.mean(fwd[tr_mask & (b == k)])) for k in range(3)]
            te = [float(np.mean(fwd[(~tr_mask) & (b == k)])) for k in range(3)]
            gap_tr, gap_te = tr[2] - tr[0], te[2] - te[0]
            # КОНТРОЛЬ: тот же признак, но перемешанный
            rng = np.random.default_rng(7)
            xs = rng.permutation(x)
            bs = np.where(xs <= q[0], 0, np.where(xs <= q[1], 1, 2))
            gap_sh = float(np.mean(fwd[(~tr_mask) & (bs == 2)]) - np.mean(fwd[(~tr_mask) & (bs == 0)]))
            ok = abs(gap_te) > 2 * abs(gap_sh) and np.sign(gap_te) == np.sign(gap_tr) and abs(gap_te) > 0.05
            print(f"   {fname:<7} обучение {gap_tr:+7.3f}   ПРОВЕРКА {gap_te:+7.3f}   "
                  f"перемешано {gap_sh:+7.3f} bps{'   ЕСТЬ СИГНАЛ' if ok else ''}")
            out[f"{hs}s_{fname}"] = dict(train_gap=round(gap_tr, 4), test_gap=round(gap_te, 4),
                                         shuffled=round(gap_sh, 4), n=int(len(idx)), ok=bool(ok))
        print()
    return out


def main():
    files = sorted(glob.glob(os.path.join(SRC, "*_1000ms.csv")))
    if not files:
        raise SystemExit(f"нет файлов признаков в {SRC} — сначала l2_reconstruct.py")
    allout = {}
    for fp in files:
        print(f"───────── {os.path.basename(fp)}")
        allout[os.path.basename(fp)] = analyse(load(fp))
    json.dump(allout, open(os.path.join(OUT, "predict.json"), "w"),
              ensure_ascii=False, indent=2)
    hits = [k for f in allout.values() for k, v in f.items() if v["ok"]]
    print(f"КЛЕТОК С СИГНАЛОМ: {len(hits)}"
          + (f" -> {hits[:8]}" if hits else " — стакан не предсказывает на этих горизонтах"))


if __name__ == "__main__":
    main()
