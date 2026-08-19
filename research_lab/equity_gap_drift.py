"""ДРЕЙФ ПОСЛЕ ГЭПА — проверка PEAD без дат отчётности.

Идея обхода. Дат отчётности у нас нет (Massive нужен ключ и сеть). Но крупный
гэп на открытии — это почти всегда реакция на новость или отчёт. PEAD
(post-earnings announcement drift) предсказывает, что после такого события
цена продолжает двигаться в сторону сюрприза ещё недели.

Значит гипотезу можно фальсифицировать на том, что есть:

    гэп = открытие сегодня / закрытие вчера - 1
    если |гэп| крупный -> считаем последующий дрейф от ОТКРЫТИЯ на N дней

PEAD ожидает: положительный гэп -> положительный дрейф, отрицательный ->
отрицательный. Противоположный результат = гэпы выкупаются (реверсия),
это тоже полезно знать.

Проверки, без которых цифра ничего не значит:
  * отдельно лонговая и шортовая сторона (иначе бета рынка всё замажет);
  * вычитается движение равновзвешенного рынка за тот же период;
  * разбивка по годам — эффект должен быть не только в одном.
"""
from __future__ import annotations

import csv
import datetime
import glob
import os
import statistics
import sys

DIR = "data_cache/equities_1h"


def day_series(path: str):
    rows = []
    for r in csv.DictReader(open(path)):
        try:
            rows.append((int(r["ts"]), float(r["o"]), float(r["c"])))
        except Exception:
            continue
    rows.sort()
    out = {}
    for ts, o, c in rows:
        d = datetime.datetime.utcfromtimestamp(ts).date()
        if d not in out:
            out[d] = [o, c]
        else:
            out[d][1] = c
    return {d: (v[0], v[1]) for d, v in out.items()}


def build():
    """{тикер: {дата: (open, close)}} + список общих дат."""
    data = {}
    for f in sorted(glob.glob(f"{DIR}/*.csv")):
        t = os.path.basename(f)[:-4].replace("_M5", "")
        d = day_series(f)
        if len(d) >= 400:
            data[t] = d
    dates = sorted(set().union(*[set(v) for v in data.values()]))
    return data, dates


def market_ret(data, dates, i, horizon):
    """Равновзвешенная доходность рынка от открытия дня i на horizon дней."""
    if i + horizon >= len(dates):
        return None
    d0, d1 = dates[i], dates[i + horizon]
    rs = []
    for t, s in data.items():
        if d0 in s and d1 in s and s[d0][0] > 0:
            rs.append(s[d1][1] / s[d0][0] - 1.0)
    return statistics.fmean(rs) if len(rs) >= 10 else None


if __name__ == "__main__":
    horizon = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    cut = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    data, dates = build()
    print(f"ДРЕЙФ ПОСЛЕ ГЭПА — {len(data)} бумаг, гэп |{cut}%|, "
          f"горизонт {horizon} дней, из открытия\n")

    mkt = {}
    for i in range(len(dates)):
        m = market_ret(data, dates, i, horizon)
        if m is not None:
            mkt[i] = m

    up, dn = [], []
    up_y, dn_y = {}, {}
    for t, s in data.items():
        ds = sorted(s)
        idx = {d: i for i, d in enumerate(dates)}
        for k in range(1, len(ds)):
            d_prev, d = ds[k - 1], ds[k]
            if (d - d_prev).days > 5:
                continue
            pc = s[d_prev][1]
            o = s[d][0]
            if pc <= 0 or o <= 0:
                continue
            gap = (o / pc - 1.0) * 100
            if abs(gap) < cut:
                continue
            i = idx.get(d)
            if i is None or i not in mkt:
                continue
            d1 = dates[i + horizon]
            if d1 not in s:
                continue
            fwd = s[d1][1] / o - 1.0
            resid = fwd - mkt[i]        # снимаем движение рынка
            (up if gap > 0 else dn).append(resid)
            (up_y if gap > 0 else dn_y).setdefault(d.year, []).append(resid)

    def show(name, arr):
        if len(arr) < 30:
            print(f"  {name}: мало наблюдений ({len(arr)})")
            return
        m = statistics.fmean(arr) * 100
        pos = sum(1 for x in arr if x > 0) / len(arr) * 100
        print(f"  {name:<28} {len(arr):>5} событий  {m:>+7.2f}%  доля плюсовых {pos:.0f}%")

    print("ИЗБЫТОЧНАЯ ДОХОДНОСТЬ (сверх рынка):")
    show("после гэпа ВВЕРХ", up)
    show("после гэпа ВНИЗ", dn)
    if len(up) >= 30 and len(dn) >= 30:
        spread = (statistics.fmean(up) - statistics.fmean(dn)) * 100
        print(f"\n  спред лонг-шорт: {spread:+.2f}% за {horizon} дней")
        print(f"  трактовка: {'ПРОДОЛЖЕНИЕ (PEAD)' if spread > 0 else 'РЕВЕРСИЯ — гэпы выкупаются'}")

    print("\nПО ГОДАМ (спред лонг минус шорт):")
    for y in sorted(set(up_y) | set(dn_y)):
        a, b = up_y.get(y, []), dn_y.get(y, [])
        if len(a) < 15 or len(b) < 15:
            continue
        print(f"  {y}: {(statistics.fmean(a)-statistics.fmean(b))*100:>+7.2f}%  "
              f"(вверх {len(a)}, вниз {len(b)})")
