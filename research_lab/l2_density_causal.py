#!/usr/bin/env python3
"""
l2_density_causal.py — плиты, но только то, что видно В МОМЕНТ РЕШЕНИЯ.

ЗАЧЕМ ОТДЕЛЬНЫЙ СКРИПТ. Прошлый замер (l2_density.py) делил плиты по
СУДЬБЕ: съедена / снята / ушла. Судьба известна только после смерти
плиты, а медианная жизнь съеденной — 27-79 секунд, у хвоста больше
горизонта замера. Значит числа вида «после съеденной цена идёт к плите
на +1.16 bps» описывают прошлое, но торговать по ним нельзя: в момент
входа неизвестно, съедят её или снимут.

Здесь наблюдение фиксируется в момент, когда решение реально
принимается: плита прожила LAG секунд и ещё стоит. Всё, что записано
в строку, видно в этот момент:

    dist_bps      далеко ли плита от середины СЕЙЧАС
    size_x        во сколько раз она крупнее медианного уровня СЕЙЧАС
    grow          выросла или подтаяла с рождения
    eaten_now     какую долю уже съели к этому моменту
    imb_toward    дисбаланс книги в сторону плиты
    spread_bps    спред
    vol_bps       недавняя волатильность (60 с)

Исход меряется ОТ момента наблюдения, а не от рождения плиты, и
знаком «+ = цена пошла к плите».

Наблюдения перекрываются (плит одновременно живёт много), поэтому
значимость считать только блочным бутстрапом — см. l2_density_edge.py.
"""
from __future__ import annotations

import bisect
import csv
import json
import os
import statistics
import subprocess
import sys
from collections import deque

K_BIG = 8.0                      # плита = во столько раз крупнее медианного уровня
LAGS_MS = (10_000, 30_000)       # когда принимаем решение после рождения плиты
HORIZONS_MS = (60_000, 300_000, 900_000)
NEAR_LEVELS = 5                  # сколько уровней с каждой стороны в дисбалансе


def open_any(fp):
    if fp.endswith(".zst"):
        p = subprocess.Popen(["zstd", "-dc", fp], stdout=subprocess.PIPE, text=True)
        return p.stdout
    return open(fp)


def run(fp, symbol, day, writer):
    bids, asks = {}, {}
    valid = False
    live = {}
    obs = []
    mid_hist = []
    mh_ts_run = []
    n_lines = 0
    med = 0.0
    med_ts = -10**9
    thr = float("inf")
    imb_ts = -1
    imb = vol_bps = spread_bps = 0.0

    for line in open_any(fp):
        n_lines += 1
        try:
            r = json.loads(line)
        except Exception:
            continue
        kind = r.get("kind")
        if kind == "gap":
            valid = False
            live.clear()
            continue
        pl = r.get("payload") or {}
        d = pl.get("data", pl)
        b_upd = d.get("b") or d.get("bids") or []
        a_upd = d.get("a") or d.get("asks") or []
        ts = r.get("local_recv_ts_ms") or 0

        if kind == "snapshot":
            bids = {float(p): float(s) for p, s in b_upd if float(s) > 0}
            asks = {float(p): float(s) for p, s in a_upd if float(s) > 0}
            valid = True
        elif kind == "delta":
            if not valid:
                continue
            for side, upd in ((bids, b_upd), (asks, a_upd)):
                for p, s in upd:
                    p, s = float(p), float(s)
                    if s <= 0:
                        side.pop(p, None)
                    else:
                        side[p] = s
        else:
            continue

        if not bids or not asks:
            continue
        bb, ba = max(bids), min(asks)
        if ba <= bb:
            continue
        m = (bb + ba) / 2
        mid_hist.append((ts, m))
        mh_ts_run.append(ts)

        # медиана уровня меняется медленно — пересчитываем раз в 2 с
        if ts - med_ts > 2_000 or med <= 0:
            sizes = sorted(v for v in bids.values() if v > 0)
            sizes += sorted(v for v in asks.values() if v > 0)
            if len(sizes) < 40:
                continue
            sizes.sort()
            med = sizes[len(sizes) // 2]
            med_ts = ts
            thr = med * K_BIG
        if med <= 0:
            continue

        # --- рождение плит: только среди уровней, изменённых этим сообщением ---
        if kind == "snapshot":
            scan = [(+1, p, s) for p, s in asks.items()] + [(-1, p, s) for p, s in bids.items()]
        else:
            scan = []
            for sgn, side, upd in ((+1, asks, a_upd), (-1, bids, b_upd)):
                for p, _ in upd:
                    p = float(p)
                    s = side.get(p)
                    if s is not None:
                        scan.append((sgn, p, s))
        for sgn, p, s in scan:
            key = (sgn, p)
            rec = live.get(key)
            if rec is None:
                if s >= thr:
                    live[key] = dict(born_ts=ts, born_size=s, max_size=s, done=set())
            elif s > rec["max_size"]:
                rec["max_size"] = s

        # --- наблюдения на фиксированных лагах ---
        for key, rec in list(live.items()):
            sgn, p = key
            side = asks if sgn > 0 else bids
            cur = side.get(p)
            if cur is None:                      # плита исчезла — наблюдений больше не будет
                live.pop(key)
                continue
            age = ts - rec["born_ts"]
            for L in LAGS_MS:
                if L in rec["done"] or age < L or age > L + 5_000:
                    continue
                rec["done"].add(L)
                if imb_ts != ts:                 # считаем дорогое только когда есть наблюдение
                    bt = sorted(bids.items(), key=lambda kv: -kv[0])[:NEAR_LEVELS]
                    at = sorted(asks.items(), key=lambda kv: kv[0])[:NEAR_LEVELS]
                    bv, av = sum(v for _, v in bt), sum(v for _, v in at)
                    imb = (bv - av) / (bv + av) if (bv + av) > 0 else 0.0
                    k0 = bisect.bisect_left(mh_ts_run, ts - 60_000)
                    vol_bps = (abs(m / mid_hist[k0][1] - 1) * 1e4) if k0 < len(mid_hist) else 0.0
                    spread_bps = (ba - bb) / m * 1e4
                    imb_ts = ts
                obs.append(dict(
                    ts=ts, symbol=symbol, day=day, lag_s=L // 1000, side=sgn,
                    dist_bps=round(abs(p - m) / m * 1e4, 4),
                    size_x=round(cur / med, 3),
                    grow=round(cur / rec["born_size"], 4) if rec["born_size"] else 1.0,
                    eaten_now=round(max(0.0, 1 - cur / rec["max_size"]), 4),
                    imb_toward=round(imb * sgn, 4),
                    spread_bps=round(spread_bps, 4),
                    vol_bps=round(vol_bps, 3),
                    _mid=m,
                ))

    # --- исходы от момента наблюдения ---
    mh_ts = [t for t, _ in mid_hist]
    mh_m = [m for _, m in mid_hist]
    for o in obs:
        for H in HORIZONS_MS:
            i = bisect.bisect_left(mh_ts, o["ts"] + H)
            o[f"fwd_{H//1000}s"] = (round((mh_m[i] / o["_mid"] - 1) * 1e4 * o["side"], 4)
                                    if i < len(mh_m) else "")
        o.pop("_mid")
        writer.writerow(o)
    span = (mh_ts[-1] - mh_ts[0]) / 3600_000 if mh_ts else 0
    print(f"{symbol} {day}: строк {n_lines:,}, покрытие {span:.1f} ч, наблюдений {len(obs):,}")
    return len(obs)


def main():
    out_fp = sys.argv[1] if len(sys.argv) > 1 else "density_obs.csv"
    jobs = []
    for arg in sys.argv[2:]:
        fp, symbol, day = arg.split(":")
        jobs.append((fp, symbol, day))
    keys = ["ts", "symbol", "day", "lag_s", "side", "dist_bps", "size_x", "grow",
            "eaten_now", "imb_toward", "spread_bps", "vol_bps"] + \
           [f"fwd_{H//1000}s" for H in HORIZONS_MS]
    with open(out_fp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        total = sum(run(fp, s, d, w) for fp, s, d in jobs)
    print(f"\n[сохранено] {out_fp}  всего наблюдений {total:,}")


if __name__ == "__main__":
    main()
