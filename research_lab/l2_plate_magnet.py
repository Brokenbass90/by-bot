#!/usr/bin/env python3
"""
l2_plate_magnet.py — притягивает ли уровень, где стояла плита.

ВОПРОС. Плита как СИГНАЛ НАПРАВЛЕНИЯ закрыта. Здесь другое: если
крупная заявка исчезла, а цена до неё не дошла, — возвращается ли
цена к этому уровню чаще, чем к произвольному уровню на том же
расстоянии. Если да, это правило выставления тейка, а не входа.
Для MPL это прямо полезно: там 11% сделок не доходят до цели.

ПОПРАВКА К ПРЕДРЕГИСТРАЦИИ, вносится до прогона и с объяснением.
В предрегистрации контроль был описан как «случайный уровень на том же
расстоянии от середины в ту же секунду с той же стороны» — это то же
самое число, контроль вырожденный. Исправляю: контроль берётся в
СЛУЧАЙНЫЙ ДРУГОЙ момент того же дня, на том же относительном
расстоянии и с той же стороны от тогдашней середины. Так измеряется
базовая частота касания на таком расстоянии.

Отбираются только события, где в момент исчезновения плиты цена была
не ближе 5 bps к уровню — иначе «касание» получается автоматически.
"""
from __future__ import annotations

import bisect
import json
import os
import statistics
import subprocess
import sys

import numpy as np

K_BIG = 8.0
NEAR_BPS = 3.0
MIN_LIFE_MS = 30_000
MIN_DIST_BPS = 5.0
HORIZONS_MS = (60_000, 300_000, 900_000, 3_600_000, 14_400_000)


def open_any(fp):
    if fp.endswith(".zst"):
        return subprocess.Popen(["zstd", "-dc", fp], stdout=subprocess.PIPE, text=True).stdout
    return open(fp)


def collect(fp, symbol, day):
    bids, asks, live = {}, {}, {}
    valid = False
    mid_ts, mid_px, hi_px, lo_px = [], [], [], []
    events = []
    med, med_ts, thr = 0.0, -10**9, float("inf")
    for line in open_any(fp):
        try:
            r = json.loads(line)
        except Exception:
            continue
        kind = r.get("kind")
        if kind == "gap":
            valid = False; live.clear(); continue
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
                    if s <= 0: side.pop(p, None)
                    else: side[p] = s
        else:
            continue
        if not bids or not asks: continue
        bb, ba = max(bids), min(asks)
        if ba <= bb: continue
        mm = (bb + ba) / 2
        mid_ts.append(ts); mid_px.append(mm); hi_px.append(ba); lo_px.append(bb)
        if ts - med_ts > 2_000 or med <= 0:
            sizes = sorted([v for v in bids.values() if v > 0] + [v for v in asks.values() if v > 0])
            if len(sizes) < 40: continue
            med = sizes[len(sizes) // 2]; med_ts = ts; thr = med * K_BIG
        if med <= 0: continue
        scan = ([(+1, p, s) for p, s in asks.items()] + [(-1, p, s) for p, s in bids.items()]
                if kind == "snapshot" else
                [(sg, float(p), sd.get(float(p)))
                 for sg, sd, upd in ((+1, asks, a_upd), (-1, bids, b_upd)) for p, _ in upd
                 if sd.get(float(p)) is not None])
        for sgn, p, s in scan:
            key = (sgn, p); rec = live.get(key)
            if rec is None:
                if s >= thr:
                    live[key] = dict(born=ts, maxs=s, approached=False, traded=0.0, last=s)
            else:
                if s > rec["maxs"]: rec["maxs"] = s
                if s < rec["last"]: rec["traded"] += rec["last"] - s
                rec["last"] = s
        for key, rec in list(live.items()):
            sgn, p = key
            side = asks if sgn > 0 else bids
            if abs(p - mm) / mm * 1e4 <= NEAR_BPS: rec["approached"] = True
            if p not in side:
                life = ts - rec["born"]
                eaten = rec["traded"] / rec["maxs"] if rec["maxs"] > 0 else 0
                fate = ("съедена" if rec["approached"] and eaten >= 0.5
                        else "снята" if rec["approached"] else "ушла")
                dist = abs(p - mm) / mm * 1e4
                if life >= MIN_LIFE_MS and dist >= MIN_DIST_BPS:
                    # ЗЕРКАЛО: тот же отступ, но в другую сторону. Это и есть
                    # различающий контроль — расстояние совпадает точно,
                    # а плиты там нет. Отдельно помечаем, ходила ли цена
                    # туда за последние 10 минут (сопоставимость «недавно
                    # проторгован») и не стоит ли там своя крупная заявка.
                    mir = mm * (1 - sgn * dist / 1e4)
                    i10 = bisect.bisect_left(mid_ts, ts - 600_000)
                    seg = mid_px[i10:]
                    mir_traded = bool(seg and min(seg) <= mir <= max(seg))
                    mir_side = bids if sgn > 0 else asks
                    mir_big = any(sz >= thr for pr, sz in mir_side.items()
                                  if abs(pr - mir) / mir * 1e4 <= 1.0)
                    events.append(dict(ts=ts, sym=symbol, day=day, side=sgn, level=p,
                                       mid=mm, dist=dist, fate=fate, life_s=life / 1000,
                                       mirror=mir, mir_traded=mir_traded, mir_big=mir_big))
                live.pop(key)
    return events, np.array(mid_ts), np.array(mid_px), np.array(hi_px), np.array(lo_px)


def touched(mts, hi, lo, t0, level, sgn, H):
    i = bisect.bisect_left(mts, t0)
    j = bisect.bisect_left(mts, t0 + H)
    if i >= len(mts) or j <= i:
        return None
    if sgn > 0:
        return bool(hi[i:j].max() >= level)
    return bool(lo[i:j].min() <= level)


def main():
    jobs = [a.split(":") for a in sys.argv[1:]]
    rng = np.random.default_rng(3)
    rows = []
    for fp, sym, day in jobs:
        ev, mts, mpx, hi, lo = collect(fp, sym, day)
        mts_l = mts.tolist()
        for e in ev:
            r = dict(e)
            k = int(rng.integers(0, max(1, len(mts) - 1)))
            ctrl_t = int(mts[k])
            ctrl_lvl = mpx[k] * (1 + e["side"] * e["dist"] / 1e4)
            for H in HORIZONS_MS:
                r[f"p{H//1000}"] = touched(mts_l, hi, lo, e["ts"], e["level"], e["side"], H)
                r[f"c{H//1000}"] = touched(mts_l, hi, lo, ctrl_t, ctrl_lvl, e["side"], H)
                r[f"m{H//1000}"] = touched(mts_l, hi, lo, e["ts"], e["mirror"], -e["side"], H)
            rows.append(r)
        print(f"{sym} {day}: событий {len(ev):,}")

    days = sorted({r["day"] for r in rows})
    print(f"\nвсего событий {len(rows):,}; отбор на {days[0]}, проверка на {days[-1]}")
    print(f"условие отбора: плита прожила >= {MIN_LIFE_MS/1000:.0f} с и умерла "
          f"дальше {MIN_DIST_BPS} bps от цены\n")
    out = {}
    for day in days:
        print(f"═══ день {day}")
        print(f"{'судьба':<10}{'n':>7}" + "".join(f"{str(H//1000)+'с':>18}" for H in HORIZONS_MS))
        for fate in ("съедена", "снята", "ушла"):
            g = [r for r in rows if r["fate"] == fate and r["day"] == day]
            if len(g) < 100:
                continue
            cells = []
            for H in HORIZONS_MS:
                p = [r[f"p{H//1000}"] for r in g if r[f"p{H//1000}"] is not None]
                c = [r[f"c{H//1000}"] for r in g if r[f"c{H//1000}"] is not None]
                if len(p) < 100 or len(c) < 100:
                    cells.append("     —"); continue
                d = np.mean(p) - np.mean(c)
                cells.append(f"{np.mean(p):.0%}/{np.mean(c):.0%} {d*100:+.0f}пп")
                out[f"{day}|{fate}|{H//1000}"] = dict(plate=float(np.mean(p)),
                                                      ctrl=float(np.mean(c)),
                                                      diff=float(d), n=len(p))
            print(f"{fate:<10}{len(g):>7}" + "".join(f"{c:>18}" for c in cells))
        print()
    print("═══ РАЗЛИЧАЮЩИЙ КОНТРОЛЬ: зеркальный уровень, то же расстояние,")
    print("    цена туда тоже недавно ходила, но плиты там нет\n")
    print(f"{'день':<12}{'n':>7}" + "".join(f"{str(H//1000)+'с':>18}" for H in HORIZONS_MS))
    for day in days:
        g = [r for r in rows if r["fate"] == "съедена" and r["day"] == day
             and r["mir_traded"] and not r["mir_big"]]
        if len(g) < 100:
            print(f"{day:<12}{len(g):>7}   мало сопоставимых случаев"); continue
        cells = []
        for H in HORIZONS_MS:
            a = [r[f"p{H//1000}"] for r in g if r[f"p{H//1000}"] is not None]
            b = [r[f"m{H//1000}"] for r in g if r[f"m{H//1000}"] is not None]
            if len(a) < 100 or len(b) < 100:
                cells.append("     —"); continue
            cells.append(f"{np.mean(a):.0%}/{np.mean(b):.0%} {(np.mean(a)-np.mean(b))*100:+.0f}пп")
            out[f"{day}|зеркало|{H//1000}"] = dict(plate=float(np.mean(a)),
                                                   mirror=float(np.mean(b)),
                                                   diff=float(np.mean(a) - np.mean(b)), n=len(a))
        print(f"{day:<12}{len(g):>7}" + "".join(f"{c:>18}" for c in cells))
    print()
    print("формат клетки: частота касания плиты / контроля, и разница в пунктах")
    print("критерий смерти объявлен заранее: превышение меньше 5 пп -> магнита нет")
    json.dump(out, open("plate_magnet.json", "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
