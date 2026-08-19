#!/usr/bin/env python3
"""alt_limit_entry.py — сколько экономит лимитный вход на 24 альтах.

ЗАЧЕМ. Единственный измеренный рычаг проекта — цена доступа. На BTC и ETH
лимитный вход давал +1.1 и +2.1 bps после учёта неисполнения и
неблагоприятного отбора. У альтов спред шире, значит экономия должна быть
больше. И, главное, здесь хватает наблюдений: 800+ тысяч против сотен
сделок у стратегий.

ПРАВИЛА ОБЪЯВЛЕНЫ ДО ПРОГОНА.
  решения           каждые 60 секунд, не перекрываются
  покупка           лимит на текущем лучшем биде P
  исполнено         только если лучший бид ОПУСТИЛСЯ НИЖЕ P за время
                    ожидания (очередь на уровне выбита целиком).
                    Это заведомо занижает долю исполнения.
  не исполнено      догоняем по рынку по ask на конец ожидания
  комиссии          мейкер 2.0 bps, тейкер 5.5 bps (реальные Bybit)
  сравнение         обе руки меряются до ОДНОГО момента: середина через
                    5 минут после конца ожидания
  критерий смерти   объявлен заранее: если разница положительна меньше
                    чем у 2/3 символов ИЛИ нижняя граница блочного
                    бутстрапа <= 0 — лимитный вход не даёт преимущества
"""
from __future__ import annotations

import bisect
import json
import math
import sys
from collections import defaultdict

import numpy as np

SRC = sys.argv[1] if len(sys.argv) > 1 else \
    "runtime/orderbook/alt24_density_v2/observations.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else "reports/research/ALT_LIMIT_ENTRY.json"

TAKER_BPS = 5.5
MAKER_BPS = 2.0
WAITS_S = (15, 30, 60)
STEP_S = 60
FWD_S = 300


def load():
    ser = defaultdict(lambda: dict(ts=[], bid=[], ask=[]))
    bad = 0
    with open(SRC, "r", errors="ignore") as fh:
        for line in fh:
            try:
                r = json.loads(line)
                s = r["symbol"]
                b, a, t = float(r["best_bid"]), float(r["best_ask"]), int(r["ts_ms"])
            except Exception:
                bad += 1
                continue
            if not (b > 0 and a > b):
                continue
            d = ser[s]
            if d["ts"] and t <= d["ts"][-1]:
                continue
            d["ts"].append(t); d["bid"].append(b); d["ask"].append(a)
    print(f"символов {len(ser)}, битых строк {bad:,}", flush=True)
    return ser


def run_symbol(sym, d):
    ts = np.array(d["ts"]); bid = np.array(d["bid"]); ask = np.array(d["ask"])
    if len(ts) < 2000:
        return None
    mid = (bid + ask) / 2
    tl = ts.tolist()
    rows = []
    t = ts[0]
    horizon = (max(WAITS_S) + FWD_S) * 1000
    while t < ts[-1] - horizon:
        i = bisect.bisect_left(tl, t)
        t += STEP_S * 1000
        if i >= len(ts) - 5:
            break
        m0, p_lim, ask0 = mid[i], bid[i], ask[i]
        row = dict(ts=int(ts[i]), spread=float((ask[i] - bid[i]) / m0 * 1e4))
        for W in WAITS_S:
            j = min(bisect.bisect_left(tl, ts[i] + W * 1000), len(ts) - 1)
            if j <= i:
                row = None
                break
            seg = bid[i + 1:j + 1]
            filled = bool(seg.size and seg.min() < p_lim)
            entry = p_lim if filled else ask[j]
            k = min(bisect.bisect_left(tl, ts[i] + (W + FWD_S) * 1000), len(ts) - 1)
            row[f"fill{W}"] = filled
            row[f"mk{W}"] = float((mid[k] / entry - 1) * 1e4 - (MAKER_BPS if filled else TAKER_BPS))
            row[f"tk{W}"] = float((mid[k] / ask0 - 1) * 1e4 - TAKER_BPS)
        if row:
            rows.append(row)
    if len(rows) < 200:
        return None
    return rows


def boot(x, ts, n=2000, seed=5):
    """блочный бутстрап 30-минутными блоками — соседние решения зависимы"""
    blk = (np.array(ts) // (30 * 60 * 1000)).astype(np.int64)
    ub = np.unique(blk)
    if len(ub) < 8:
        return float("nan"), float("nan")
    idx = {b: np.flatnonzero(blk == b) for b in ub}
    g = np.random.default_rng(seed)
    out = np.empty(n)
    for i in range(n):
        p = g.choice(ub, len(ub), replace=True)
        out[i] = x[np.concatenate([idx[b] for b in p])].mean()
    return float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))


def main():
    ser = load()
    res, pooled = {}, defaultdict(list)
    print(f"\n{'символ':<12}{'спред':>8}{'решений':>10}" +
          "".join(f"{'налив ' + str(W) + 'с':>13}{'разница':>10}" for W in WAITS_S), flush=True)
    for sym in sorted(ser):
        rows = run_symbol(sym, ser[sym])
        if not rows:
            continue
        line = f"{sym:<12}{np.median([r['spread'] for r in rows]):>8.2f}{len(rows):>10,}"
        res[sym] = dict(n=len(rows), spread=float(np.median([r["spread"] for r in rows])))
        for W in WAITS_S:
            mk = np.array([r[f"mk{W}"] for r in rows])
            tk = np.array([r[f"tk{W}"] for r in rows])
            fill = float(np.mean([r[f"fill{W}"] for r in rows]))
            diff = mk - tk
            res[sym][f"w{W}"] = dict(fill=fill, diff=float(diff.mean()))
            pooled[W].append((sym, diff, np.array([r["ts"] for r in rows])))
            line += f"{fill:>12.0%}{diff.mean():>+10.2f}"
        print(line, flush=True)

    print("\n" + "=" * 70)
    print("ИТОГ: разница = мейкер минус тейкер, в базисных пунктах. Больше нуля — лимит выгоднее.")
    verdict = {}
    for W in WAITS_S:
        allD = np.concatenate([d for _, d, _ in pooled[W]])
        allT = np.concatenate([t for _, _, t in pooled[W]])
        pos = sum(1 for _, d, _ in pooled[W] if d.mean() > 0)
        tot = len(pooled[W])
        lo, hi = boot(allD, allT)
        dead = (pos < math.ceil(2 * tot / 3)) or (lo <= 0)
        verdict[W] = dict(mean=float(allD.mean()), lo=lo, hi=hi, pos=pos, total=tot, dead=bool(dead))
        print(f"ожидание {W:>2} с: разница {allD.mean():+.2f} bps  "
              f"интервал [{lo:+.2f} .. {hi:+.2f}]  "
              f"символов в плюсе {pos}/{tot}  ->  {'МЕРТВО' if dead else 'ЖИВО'}")
    json.dump(dict(symbols=res, verdict={str(k): v for k, v in verdict.items()}),
              open(OUT, "w"), ensure_ascii=False, indent=2)
    print(f"\nсохранено: {OUT}")


if __name__ == "__main__":
    main()
