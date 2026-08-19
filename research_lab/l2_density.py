#!/usr/bin/env python3
"""
l2_density.py — плиты в стакане: настоящие против спуферов.

ВОПРОС ВЛАДЕЛЬЦА, дословно: детектор плотностей не-спуфинговых, чтобы
их отторговывать; а если у плотности есть динамика — либо следим
и осторожничаем, либо записываем в спуферы.

КАК ОТЛИЧИТЬ. По судьбе заявки, а не по размеру:

    СЪЕДЕНА    цена дошла до уровня, объём уменьшался сделками ->
               плита настоящая, кто-то действительно хотел там купить
    СНЯТА      цена подошла близко, объём исчез БЕЗ торговли ->
               спуфер, заявку убрали перед подходом
    УШЛА       цена не подходила, объём просто исчез -> нейтрально
    СТОИТ      дожила до конца наблюдения

ЧТО МЕРЯЕТСЯ ПОТОМ. Что делает цена после появления крупной плиты:
разворачивается от неё (плита держит) или проходит насквозь.
И отдельно — отличается ли поведение после съеденных плит от поведения
после снятых. Если отличается, спуфинг несёт информацию сам по себе.

Плита = уровень, чей объём больше медианного объёма уровня в книге
в K раз. K объявлен заранее и не подбирается.
"""
from __future__ import annotations

import bisect
import csv
import json
import os
import statistics
import sys
from collections import defaultdict

SRC = sys.argv[1] if len(sys.argv) > 1 else "runtime/tape"
SYM = sys.argv[2] if len(sys.argv) > 2 else "BTCUSDT"
DAY = sys.argv[3] if len(sys.argv) > 3 else "20260812"
K_BIG = 8.0            # во сколько раз крупнее медианного уровня
NEAR_BPS = 3.0         # «цена подошла» — ближе этого к плите
# ГЛАВНЫЙ ВОПРОС ТОРГУЕМОСТИ: на каком горизонте живёт эффект.
# На минуте он 0.88 bps — меньше комиссии тейкера (6 bps). Если к 15
# минутам вырастет до 3-4 — переходит линию издержек. Если затухнет —
# остаётся инструментом исполнения, а не сигналом.
HORIZONS_MS = (10_000, 30_000, 60_000, 300_000, 900_000)
OUT = "research_lab/results/l2"


def main():
    fp = os.path.join(SRC, SYM, f"{DAY}.book.jsonl")
    if not os.path.exists(fp):
        raise SystemExit(f"нет {fp}")

    bids, asks = {}, {}
    valid = False
    live = {}            # (side, price) -> запись о плите
    done = []
    mid_hist = []        # (ts, mid) для оценки хода после появления
    n_lines = 0

    def mid_now():
        if not bids or not asks:
            return None
        bb, ba = max(bids), min(asks)
        return (bb + ba) / 2 if ba > bb else None

    with open(fp) as fh:
        for line in fh:
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

            m = mid_now()
            if m is None:
                continue
            mid_hist.append((ts, m))

            sizes = [v for v in list(bids.values()) + list(asks.values()) if v > 0]
            if len(sizes) < 40:
                continue
            med = statistics.median(sizes)
            if med <= 0:
                continue
            thr = med * K_BIG

            # --- рождение плит ---
            for sgn, side in ((+1, asks), (-1, bids)):
                for p, s in list(side.items()):
                    key = (sgn, p)
                    if s >= thr and key not in live:
                        live[key] = dict(side=sgn, price=p, born_ts=ts, born_mid=m,
                                         max_size=s, dist_bps=abs(p - m) / m * 1e4,
                                         approached=False, traded_down=0.0, last_size=s)
                    elif key in live:
                        rec = live[key]
                        rec["max_size"] = max(rec["max_size"], s)
                        if s < rec["last_size"]:
                            rec["traded_down"] += rec["last_size"] - s
                        rec["last_size"] = s

            # --- судьба плит ---
            for key, rec in list(live.items()):
                sgn, p = key
                side = asks if sgn > 0 else bids
                if abs(p - m) / m * 1e4 <= NEAR_BPS:
                    rec["approached"] = True
                if p not in side:
                    eaten = rec["traded_down"] / rec["max_size"] if rec["max_size"] > 0 else 0
                    if rec["approached"] and eaten >= 0.5:
                        fate = "съедена"
                    elif rec["approached"]:
                        fate = "снята"
                    else:
                        fate = "ушла"
                    rec.update(fate=fate, died_ts=ts, life_ms=ts - rec["born_ts"],
                               eaten_frac=round(eaten, 3))
                    done.append(rec)
                    live.pop(key)

    for rec in live.values():
        rec.update(fate="стоит", died_ts=None, life_ms=None, eaten_frac=None)
        done.append(rec)

    print(f"строк {n_lines:,}, плит найдено {len(done):,}, порог x{K_BIG} от медианы")
    if not done:
        return

    # ход цены К ПЛИТЕ на нескольких горизонтах
    mh_ts = [t for t, _ in mid_hist]
    mh_m = [m for _, m in mid_hist]
    for rec in done:
        for H in HORIZONS_MS:
            i = bisect.bisect_left(mh_ts, rec["born_ts"] + H)
            key = f"fwd_{H//1000}s"
            rec[key] = ((mh_m[i] / rec["born_mid"] - 1) * 1e4 * rec["side"]
                        if i < len(mh_m) else None)
        rec["fwd_bps"] = rec.get("fwd_60s")

    from collections import Counter
    c = Counter(r["fate"] for r in done)
    print("\nсудьба плит:", dict(c))
    hdr = "".join(f"{str(H//1000)+'с':>10}" for H in HORIZONS_MS)
    print(f"\n{'судьба':<10}{'штук':>7}{'жизнь,с':>9}{'дист':>7}   ход к плите:{hdr}")
    res = {}
    for fate in ("съедена", "снята", "ушла", "стоит"):
        g = [r for r in done if r["fate"] == fate]
        if len(g) < 20:
            continue
        life = [r["life_ms"] / 1000 for r in g if r["life_ms"]]
        fwd = [r["fwd_bps"] for r in g if r["fwd_bps"] is not None]
        curve = {}
        for H in HORIZONS_MS:
            v = [r[f"fwd_{H//1000}s"] for r in g if r.get(f"fwd_{H//1000}s") is not None]
            curve[H] = round(statistics.mean(v), 3) if len(v) > 20 else None
        res[fate] = dict(n=len(g),
                         life_s=round(statistics.median(life), 1) if life else None,
                         dist=round(statistics.median([r["dist_bps"] for r in g]), 2),
                         fwd=curve.get(60_000), curve={str(k//1000): v for k, v in curve.items()})
        cells = "".join(f"{(curve[H] if curve[H] is not None else 0):>10.3f}" for H in HORIZONS_MS)
        print(f"{fate:<10}{len(g):>7}{(res[fate]['life_s'] or 0):>9.1f}"
              f"{res[fate]['dist']:>7.2f}              {cells}")

    if "съедена" in res and "снята" in res:
        d = res["съедена"]["fwd"] - res["снята"]["fwd"]
        print(f"\nРАЗНИЦА «съедена» минус «снята»: {d:+.3f} bps")
        print("   положительная разница означает: после НАСТОЯЩЕЙ плиты цена")
        print("   идёт к ней сильнее, чем после снятой. Это и был бы сигнал.")

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{SYM}_{DAY}_density.csv"), "w", newline="") as fh:
        keys = (["side", "price", "born_ts", "max_size", "dist_bps", "fate",
                 "life_ms", "eaten_frac", "fwd_bps"]
                + [f"fwd_{H//1000}s" for H in HORIZONS_MS])
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(done)
    print(f"\n[сохранено] {OUT}/{SYM}_{DAY}_density.csv")


if __name__ == "__main__":
    main()
