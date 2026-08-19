#!/usr/bin/env python3
"""ОТСКОК ИЛИ ПРОБОЙ: базовые частоты на часовых уровнях.

    python3 research_lab/level_bounce_vs_break.py
    python3 research_lab/level_bounce_vs_break.py SOLUSDT,ADAUSDT

Отвечает на вопрос владельца: «есть ли инструмент, который скажет, у чего
шанс больше — у отскока или у пробоя». Не было. Это он.

ЧТО СЧИТАЕТ
  Уровни ищутся на ЧАСОВЫХ барах (пивоты), исход меряется на 5-минутных —
  как владелец и описывает: «уровни на часу, торгуем на пяти минутах».

  Для каждого КАСАНИЯ уровня смотрим следующие HORIZON 5m баров:
      ОТСКОК  — цена ушла от уровня на >= RESOLVE_ATR ATR в сторону отбоя
                и НЕ закрылась за уровнем;
      ПРОБОЙ  — закрытие за уровнем дальше RESOLVE_ATR ATR;
      НИЧЬЯ   — ни то ни другое за горизонт.
  Что случилось раньше, то и засчитано.

  Базовые частоты разбиты по признакам, которые владелец называет важными:
      число предыдущих касаний уровня (1, 2, 3+)
      длина наторговки перед касанием (сколько 5m баров цена в узком диапазоне)
      волатильность (ATR% на момент касания)
      сопротивление против поддержки

ЭТО ОПИСАТЕЛЬНАЯ СТАТИСТИКА, А НЕ СТРАТЕГИЯ
  Здесь нет входов, стопов и издержек — только «что происходит чаще».
  Числа отсюда нельзя брать как доходность: чтобы отскок в 55% случаев
  приносил деньги, нужно ещё чтобы средний отскок был больше среднего
  пробоя после издержек. Для этого печатается медианный ход в ATR
  в каждую сторону — вот он уже сравним со стоимостью круга.

  Круг издержек = 12 bps. При типичном 5m ATR около 0.25% от цены это
  примерно 0.05 ATR. То есть движение меньше 0.1 ATR не отбивает вход.
"""
from __future__ import annotations

import collections
import glob
import json
import statistics as st
import sys
from pathlib import Path

CACHE = "data_cache"
HORIZON = 48          # 4 часа на 5m — «быстрый выход по импульсу»
RESOLVE_ATR = 0.8     # насколько уйти, чтобы считать исход состоявшимся
TOUCH_ATR = 0.35      # насколько близко к уровню, чтобы считать касанием
PIVOT_L, PIVOT_R = 3, 3
LEVEL_LIFE_H = 240    # уровень живёт 10 суток
FLAT_ATR = 0.6        # ширина «наторговки» в ATR


def load5(symbol: str) -> list:
    best, n = None, 0
    for p in glob.glob(f"{CACHE}/{symbol}_5_*.json"):
        try:
            rows = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        if len(rows) > n:
            best, n = rows, len(rows)
    if not best:
        return []
    out = []
    for x in best:
        if isinstance(x, dict):
            out.append((int(float(x["ts"])), float(x["o"]), float(x["h"]),
                        float(x["l"]), float(x["c"])))
        else:
            out.append((int(float(x[0])), float(x[1]), float(x[2]),
                        float(x[3]), float(x[4])))
    return out


def to_h1(b5: list) -> list:
    out, cur = [], None
    for ts, o, h, l, c in b5:
        k = ts - (ts % 3_600_000)
        if cur is None or cur[0] != k:
            if cur:
                out.append(tuple(cur))
            cur = [k, o, h, l, c]
        else:
            cur[2] = max(cur[2], h); cur[3] = min(cur[3], l); cur[4] = c
    if cur:
        out.append(tuple(cur))
    return out


def atr5(b5: list, period: int = 14) -> list:
    out = [0.0] * len(b5)
    tr = []
    for i, (_, o, h, l, c) in enumerate(b5):
        prev = b5[i - 1][4] if i else c
        tr.append(max(h - l, abs(h - prev), abs(l - prev)))
        if i >= period:
            out[i] = sum(tr[i - period + 1:i + 1]) / period
        elif i:
            out[i] = sum(tr[:i + 1]) / (i + 1)
    return out


def levels_from_h1(h1: list) -> list:
    """(ts_подтверждения, цена, 'res'|'sup')"""
    out = []
    for i in range(PIVOT_L, len(h1) - PIVOT_R):
        hi = h1[i][2]; lo = h1[i][3]
        if all(hi >= h1[j][2] for j in range(i - PIVOT_L, i + PIVOT_R + 1)):
            out.append((h1[i + PIVOT_R][0], hi, "res"))
        if all(lo <= h1[j][3] for j in range(i - PIVOT_L, i + PIVOT_R + 1)):
            out.append((h1[i + PIVOT_R][0], lo, "sup"))
    return out


def analyse(symbol: str, acc: dict) -> int:
    b5 = load5(symbol)
    if len(b5) < 5000:
        return 0
    h1 = to_h1(b5)
    a5 = atr5(b5)
    levels = levels_from_h1(h1)
    if not levels:
        return 0
    idx5 = {b[0]: i for i, b in enumerate(b5)}
    ts5 = [b[0] for b in b5]

    def find5(ts):
        lo, hi = 0, len(ts5) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if ts5[mid] < ts:
                lo = mid + 1
            else:
                hi = mid
        return lo

    n_ev = 0
    for conf_ts, px, kind in levels:
        i0 = find5(conf_ts)
        i_end = min(len(b5) - HORIZON - 1, i0 + LEVEL_LIFE_H * 12)
        touches = 0
        i = i0 + 1
        while i < i_end:
            a = a5[i]
            if a <= 0:
                i += 1; continue
            _, o, h, l, c = b5[i]
            # КАСАНИЕ: цена подошла к уровню С ПРАВИЛЬНОЙ СТОРОНЫ.
            # Первая версия этого не требовала, и «отскок» засчитывался просто
            # потому, что цена и так была ниже сопротивления — выходило 81%
            # отскоков во всех разрезах без исключения. Это и был признак
            # сломанного измерения: если ни один признак не двигает число,
            # меряется артефакт, а не рынок.
            if kind == "res":
                near = (h >= px - TOUCH_ATR * a) and (c <= px + TOUCH_ATR * a) and (o < px)
            else:
                near = (l <= px + TOUCH_ATR * a) and (c >= px - TOUCH_ATR * a) and (o > px)
            if not near:
                i += 1; continue
            touches += 1

            # НАТОРГОВКА: доля из последних 48 баров, чьё закрытие держалось
            # в коридоре FLAT_ATR вокруг уровня. Считаем долей, а не серией
            # подряд — серия рвётся на первом же выбросе и всегда даёт ноль.
            lo_j = max(i0 + 1, i - 48)
            near_cnt = sum(1 for j in range(lo_j, i) if abs(b5[j][4] - px) <= FLAT_ATR * a)
            flat_frac = near_cnt / max(1, i - lo_j)

            # ИСХОД считается ОТ ЦЕНЫ КАСАНИЯ, а не от уровня.
            res, move = "draw", 0.0
            for j in range(i + 1, i + 1 + HORIZON):
                cj = b5[j][4]
                if kind == "res":
                    if cj > px + RESOLVE_ATR * a:
                        res, move = "break", (cj - px) / a; break
                    if cj < c - RESOLVE_ATR * a:
                        res, move = "bounce", (c - cj) / a; break
                else:
                    if cj < px - RESOLVE_ATR * a:
                        res, move = "break", (px - cj) / a; break
                    if cj > c + RESOLVE_ATR * a:
                        res, move = "bounce", (cj - c) / a; break

            tb = "1" if touches == 1 else ("2" if touches == 2 else "3+")
            fb = ("нет (<25%)" if flat_frac < 0.25 else
                  "средняя (25-60%)" if flat_frac < 0.60 else "плотная (60%+)")
            vb = "тихо" if a / c * 100 < 0.2 else ("средне" if a / c * 100 < 0.45 else "бурно")
            for key in (("касаний", tb), ("наторговка", fb),
                        ("волатильность", vb), ("тип", kind)):
                acc[key][res] += 1
            acc[("ход", res)].append(move)
            n_ev += 1
            i += HORIZON // 2
    return n_ev


def main() -> int:
    syms = (sys.argv[1].split(",") if len(sys.argv) > 1 else
            "BTCUSDT ETHUSDT SOLUSDT XRPUSDT ADAUSDT DOGEUSDT AVAXUSDT "
            "BNBUSDT SUIUSDT TAOUSDT ONDOUSDT WIFUSDT 1000PEPEUSDT".split())
    acc = collections.defaultdict(lambda: collections.Counter())
    acc[("ход", "bounce")] = []
    acc[("ход", "break")] = []
    acc[("ход", "draw")] = []
    total = 0
    for s in syms:
        n = analyse(s, acc)
        total += n
        print(f"  {s:<14} событий {n}")
    if not total:
        print("нет данных")
        return 1

    print(f"\nвсего касаний часовых уровней: {total}")
    print("исход меряется за 4 часа после касания\n")
    order = ["касаний", "наторговка", "волатильность", "тип"]
    names = {"res": "сопротивление", "sup": "поддержка"}
    for grp in order:
        print(f"── по признаку «{grp}»")
        keys = sorted({k[1] for k in acc if k[0] == grp})
        for kk in keys:
            c = acc[(grp, kk)]
            n = sum(c.values())
            if n < 30:
                continue
            b, br, d = c["bounce"], c["break"], c["draw"]
            res = n - d
            print(f"   {names.get(kk, kk):<18} n={n:>6}   отскок {b/n*100:>5.1f}%   "
                  f"пробой {br/n*100:>5.1f}%   ничья {d/n*100:>5.1f}%"
                  + (f"   отскок/пробой {b/br:.2f}" if br else ""))
        print()

    for k in ("bounce", "break"):
        v = acc[("ход", k)]
        if v:
            print(f"медианный ход при исходе «{k}»: {st.median(v):.2f} ATR "
                  f"(круг издержек ~0.05 ATR)")
    print("\nЭто базовые частоты, а не доходность: чтобы отскок приносил деньги,")
    print("нужно ещё, чтобы средний ход в его сторону покрывал издержки и стоп.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
