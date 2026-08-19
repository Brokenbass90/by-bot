#!/usr/bin/env python3
"""
l2_reconstruct.py — восстановление стакана из ленты снапшот+дельты.

ЗАЧЕМ. Контур уровней закрыт на СВЕЧНЫХ данных: 43 013 событий,
72 конфигурации, ноль. Но свеча не видит, стоит ли на уровне крупная
плита. Стакан видит. Это единственная информация, которой у проекта
никогда не было.

И здесь наконец есть мощность. Сутки стакана по битку — около трёх
миллионов обновлений книги. Это больше наблюдений, чем 3.5 года часовых
свечей по всем 137 символам вместе.

ЧТО ДЕЛАЕТ. Проигрывает ленту, держит книгу в актуальном состоянии
и с заданной частотой пишет строку признаков:

    spread        спред в базисных пунктах
    mid           середина
    imb1/imb5/imb20   дисбаланс объёма bid против ask на 1/5/20 уровнях
    depth_bid/ask     суммарный объём в долларах на 20 уровнях
    slope         как быстро тает объём с удалением от середины

ЧЕСТНОСТЬ ВОССТАНОВЛЕНИЯ. Каждая дельта обязана продолжать
последовательность. Разрыв (`kind=gap`) обнуляет книгу до следующего
снапшота, и участок помечается как невалидный, а не склеивается молча.
Число разрывов печатается — если их много, признаки нельзя использовать.
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import sys
from collections import defaultdict

SRC = sys.argv[1] if len(sys.argv) > 1 else "runtime/tape"
SYM = sys.argv[2] if len(sys.argv) > 2 else "BTCUSDT"
DAY = sys.argv[3] if len(sys.argv) > 3 else "20260812"
STEP_MS = int(sys.argv[4]) if len(sys.argv) > 4 else 1000     # частота записи
OUT = "research_lab/results/l2"


class Book:
    """Стакан как два словаря цена->объём. Ноль означает снятие уровня."""

    def __init__(self):
        self.b = {}
        self.a = {}
        self.valid = False

    def snapshot(self, bids, asks):
        self.b = {float(p): float(s) for p, s in bids if float(s) > 0}
        self.a = {float(p): float(s) for p, s in asks if float(s) > 0}
        self.valid = True

    def delta(self, bids, asks):
        for side, upd in ((self.b, bids), (self.a, asks)):
            for p, s in upd:
                p, s = float(p), float(s)
                if s <= 0:
                    side.pop(p, None)
                else:
                    side[p] = s

    def features(self):
        if not self.valid or not self.b or not self.a:
            return None
        bp = sorted(self.b, reverse=True)
        ap = sorted(self.a)
        best_b, best_a = bp[0], ap[0]
        if best_a <= best_b:
            return None                       # перекрещенная книга — пропуск
        mid = (best_b + best_a) / 2
        out = dict(mid=mid, spread_bps=(best_a - best_b) / mid * 1e4)
        for n in (1, 5, 20):
            vb = sum(self.b[p] * p for p in bp[:n])
            va = sum(self.a[p] * p for p in ap[:n])
            out[f"imb{n}"] = (vb - va) / (vb + va) if (vb + va) > 0 else 0.0
            if n == 20:
                out["depth_bid"] = vb
                out["depth_ask"] = va
        # наклон: доля объёма первых 5 уровней от 20
        v5 = sum(self.b[p] * p for p in bp[:5]) + sum(self.a[p] * p for p in ap[:5])
        v20 = out["depth_bid"] + out["depth_ask"]
        out["slope"] = v5 / v20 if v20 > 0 else 0.0
        return out


def payload_levels(pl, key_b="b", key_a="a"):
    if not isinstance(pl, dict):
        return [], []
    d = pl.get("data", pl)
    return d.get(key_b) or d.get("bids") or [], d.get(key_a) or d.get("asks") or []


def main():
    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(SRC, SYM, f"{DAY}.book.jsonl")
    if not os.path.exists(fp):
        raise SystemExit(f"нет файла {fp}")

    book = Book()
    n_lines = n_snap = n_delta = n_gap = n_rows = n_skip = 0
    last_write = 0
    rows = []
    prev_seq = None

    with open(fp) as fh:
        for line in fh:
            n_lines += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            kind = r.get("kind")
            if kind == "gap":
                n_gap += 1
                book.valid = False            # НЕ склеиваем молча
                prev_seq = None
                continue
            pl = r.get("payload")
            b, a = payload_levels(pl)
            if kind == "snapshot":
                book.snapshot(b, a)
                n_snap += 1
                prev_seq = r.get("seq")
            elif kind == "delta":
                if not book.valid:
                    n_skip += 1
                    continue
                book.delta(b, a)
                n_delta += 1
                prev_seq = r.get("seq")
            else:
                continue

            ts = r.get("local_recv_ts_ms") or 0
            if ts - last_write >= STEP_MS:
                f = book.features()
                if f:
                    f["ts"] = ts
                    rows.append(f)
                    n_rows += 1
                last_write = ts

    print(f"строк {n_lines:,}  снапшотов {n_snap}  дельт {n_delta:,}  "
          f"разрывов {n_gap}  пропущено после разрыва {n_skip:,}")
    if not rows:
        raise SystemExit("книга не восстановилась — проверь формат payload")

    import csv
    out_fp = os.path.join(OUT, f"{SYM}_{DAY}_{STEP_MS}ms.csv")
    with open(out_fp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    span = (rows[-1]["ts"] - rows[0]["ts"]) / 3600000
    print(f"записей признаков {n_rows:,} за {span:.1f} ч -> {out_fp}")

    import statistics as st
    for k in ("spread_bps", "imb1", "imb5", "imb20", "slope"):
        v = [r[k] for r in rows if k in r]
        print(f"  {k:<11} медиана {st.median(v):+.4f}   "
              f"размах {min(v):+.3f} .. {max(v):+.3f}")


if __name__ == "__main__":
    main()
