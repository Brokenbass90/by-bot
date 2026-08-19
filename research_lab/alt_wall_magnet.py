#!/usr/bin/env python3
"""alt_wall_magnet.py — притягивает ли уровень, где стояла крупная заявка.

ВОПРОС. Плита как сигнал НАПРАВЛЕНИЯ закрыта (52 гипотезы, 0 выжило).
Здесь другое: если в стакане стоит крупная заявка, возвращается ли цена
к этому уровню ЧАЩЕ, чем к произвольному уровню на том же расстоянии.
Если да — это правило выставления цели, а не входа.

ПРАВИЛА ОБЪЯВЛЕНЫ ДО ПРОГОНА.
  плита         размер >= 8 медиан книги (поле mult_vs_median)
  отступ        не ближе 0.05% от середины (иначе касание автоматическое)
  наблюдения    не перекрываются: одно решение в 60 секунд на символ
  контроль      тот же символ, то же относительное расстояние и та же
                сторона, но СЛУЧАЙНЫЙ другой момент того же дня.
                Так меряется базовая частота касания на таком расстоянии.
  горизонты     15, 30, 60 минут
  критерий      объявлен заранее: превышение над контролем меньше
                5 процентных пунктов -> магнита нет
"""
from __future__ import annotations

import bisect
import json
import sys
from collections import defaultdict

import numpy as np

SRC = sys.argv[1] if len(sys.argv) > 1 else \
    "runtime/orderbook/alt24_density_v2/observations.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else "reports/research/ALT_WALL_MAGNET.json"

K_BIG = 8.0
MIN_DIST_PCT = 0.05
STEP_MS = 60_000
HORIZONS = (15, 30, 60)


def main():
    ser = defaultdict(lambda: dict(ts=[], mid=[], hi=[], lo=[]))
    walls = defaultdict(list)
    with open(SRC, errors="ignore") as fh:
        for line in fh:
            try:
                r = json.loads(line)
                s = r["symbol"]; t = int(r["ts_ms"])
                b = float(r["best_bid"]); a = float(r["best_ask"])
            except Exception:
                continue
            if not (b > 0 and a > b):
                continue
            d = ser[s]
            if d["ts"] and t <= d["ts"][-1]:
                continue
            d["ts"].append(t); d["mid"].append((a + b) / 2)
            d["hi"].append(a); d["lo"].append(b)
            for w in (r.get("walls") or []):
                try:
                    if float(w.get("mult_vs_median", 0)) < K_BIG:
                        continue
                    if float(w.get("dist_pct", 0)) < MIN_DIST_PCT:
                        continue
                    walls[s].append((t, float(w["price"]),
                                     1 if w.get("side") == "ask" else -1,
                                     float(w["dist_pct"])))
                except Exception:
                    continue
    print(f"символов {len(ser)}, плит найдено {sum(len(v) for v in walls.values()):,}", flush=True)

    rng = np.random.default_rng(11)
    rows = []
    for s, d in ser.items():
        ts = np.array(d["ts"]); hi = np.array(d["hi"]); lo = np.array(d["lo"])
        mid = np.array(d["mid"])
        if len(ts) < 2000 or not walls[s]:
            continue
        tl = ts.tolist()

        def touched(t0, level, sgn, mins):
            i = bisect.bisect_left(tl, t0)
            j = bisect.bisect_left(tl, t0 + mins * 60_000)
            if i >= len(ts) or j <= i:
                return None
            return bool(hi[i:j].max() >= level) if sgn > 0 else bool(lo[i:j].min() <= level)

        last = -10 ** 9
        for t, price, sgn, dist in sorted(walls[s]):
            if t - last < STEP_MS:          # решения не перекрываются
                continue
            last = t
            k = int(rng.integers(0, max(1, len(ts) - 1)))
            ctrl_t = int(ts[k])
            ctrl_lvl = mid[k] * (1 + sgn * dist / 100)
            row = dict(sym=s, dist=dist)
            ok = True
            for hz in HORIZONS:
                p = touched(t, price, sgn, hz)
                c = touched(ctrl_t, ctrl_lvl, sgn, hz)
                if p is None or c is None:
                    ok = False
                    break
                row[f"p{hz}"] = p
                row[f"c{hz}"] = c
            if ok:
                rows.append(row)
    if len(rows) < 200:
        print("наблюдений мало:", len(rows))
        return
    print(f"\nсравнимых событий {len(rows):,}\n")
    print(f"{'горизонт':<12}{'плита':>10}{'контроль':>11}{'разница':>11}{'вердикт':>12}")
    res = {}
    for hz in HORIZONS:
        p = np.mean([r[f"p{hz}"] for r in rows])
        c = np.mean([r[f"c{hz}"] for r in rows])
        d = (p - c) * 100
        res[hz] = dict(plate=float(p), ctrl=float(c), diff_pp=float(d), n=len(rows))
        print(f"{str(hz)+' мин':<12}{p:>9.1%}{c:>11.1%}{d:>+10.1f}пп"
              f"{('МАГНИТ' if d >= 5 else 'нет'):>12}")
    print("\nкритерий смерти объявлен заранее: превышение меньше 5 пп -> магнита нет")

    print("\nПО РАССТОЯНИЮ ДО ПЛИТЫ (горизонт 60 мин)")
    for lo_, hi_ in ((0.05, 0.15), (0.15, 0.3), (0.3, 0.6), (0.6, 99)):
        g = [r for r in rows if lo_ <= r["dist"] < hi_]
        if len(g) < 200:
            continue
        p = np.mean([r["p60"] for r in g]); c = np.mean([r["c60"] for r in g])
        print(f"  {lo_}–{hi_}%   n={len(g):>6}  плита {p:.1%}  контроль {c:.1%}  "
              f"разница {(p-c)*100:+.1f}пп")
    json.dump(dict(n=len(rows), horizons=res), open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"\nсохранено: {OUT}")


if __name__ == "__main__":
    main()
