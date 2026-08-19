"""ОВЕРНАЙТ ПРОТИВ ВНУТРИДНЕВНОЙ — разложение доходности акций.

Гипотеза (хорошо документирована на индексах): почти вся доходность акций
накапливается МЕЖДУ закрытием и открытием, а не в основной сессии.

    овернайт      = открытие сегодня / закрытие вчера - 1
    внутридневная = закрытие сегодня / открытие сегодня - 1
    сумма         ~ обычная дневная доходность

Почему это интересно нам:
  * реализуется тривиально: вход на закрытии, выход на открытии;
  * издержки почти нулевые — два ордера в день, никакого удержания;
  * ёмкость огромная, ограничения по размеру нет;
  * корреляция с нашими крипто-ногами близка к нулю по построению.

Честно: если эффект есть, он в основном про ИНДЕКС, а не про отбор бумаг.
Поэтому смотрим и среднее по всем бумагам, и стабильность по годам.
"""
from __future__ import annotations

import csv
import datetime
import glob
import os
import statistics
import sys

DIR = "data_cache/equities_1h"


def day_bars(path: str):
    """Возвращает {дата: (open_первого_бара, close_последнего_бара)}."""
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


def decompose(path: str):
    day = day_bars(path)
    ds = sorted(day)
    on, intr = [], []
    for i in range(1, len(ds)):
        prev_c = day[ds[i - 1]][1]
        o, c = day[ds[i]]
        if prev_c <= 0 or o <= 0:
            continue
        # пропускаем разрывы больше 5 календарных дней (длинные праздники)
        if (ds[i] - ds[i - 1]).days > 5:
            continue
        on.append((ds[i], o / prev_c - 1.0))
        intr.append((ds[i], c / o - 1.0))
    return on, intr


def compound(vals) -> float:
    e = 1.0
    for v in vals:
        e *= (1.0 + v)
    return (e - 1.0) * 100


if __name__ == "__main__":
    files = sorted(glob.glob(f"{DIR}/*.csv"))
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if limit:
        files = files[:limit]
    print(f"РАЗЛОЖЕНИЕ ДОХОДНОСТИ — {len(files)} бумаг, часовые бары\n")
    print(f"{'тикер':<8}{'дней':>6}{'овернайт %':>13}{'внутри %':>12}{'всего %':>11}")
    agg_on, agg_in = {}, {}
    rows = []
    for f in files:
        t = os.path.basename(f)[:-4].replace("_M5", "")
        on, intr = decompose(f)
        if len(on) < 200:
            continue
        for d, v in on:
            agg_on.setdefault(d, []).append(v)
        for d, v in intr:
            agg_in.setdefault(d, []).append(v)
        co, ci = compound([v for _, v in on]), compound([v for _, v in intr])
        rows.append((t, len(on), co, ci))
    for t, n, co, ci in rows[:12]:
        print(f"{t:<8}{n:>6}{co:>+13.1f}{ci:>+12.1f}{co+ci:>+11.1f}")
    if len(rows) > 12:
        print(f"... ещё {len(rows)-12} бумаг")

    # равновзвешенный портфель по дням
    ds = sorted(set(agg_on) & set(agg_in))
    p_on = [statistics.fmean(agg_on[d]) for d in ds]
    p_in = [statistics.fmean(agg_in[d]) for d in ds]
    print(f"\n{'='*56}")
    print(f"РАВНОВЗВЕШЕННЫЙ ПОРТФЕЛЬ ({len(rows)} бумаг, {len(ds)} дней)")
    print(f"  овернайт      {compound(p_on):>+9.1f}%   ср. {statistics.fmean(p_on)*10000:>+6.1f} bps/день")
    print(f"  внутридневная {compound(p_in):>+9.1f}%   ср. {statistics.fmean(p_in)*10000:>+6.1f} bps/день")
    print(f"  вместе        {compound([a+b for a, b in zip(p_on, p_in)]):>+9.1f}%")
    pos = sum(1 for t, n, co, ci in rows if co > ci)
    print(f"\n  бумаг, где овернайт > внутридневной: {pos}/{len(rows)}")

    # по годам — стабильность
    print("\n  по годам:")
    yrs = sorted(set(d.year for d in ds))
    for y in yrs:
        idx = [i for i, d in enumerate(ds) if d.year == y]
        if len(idx) < 50:
            continue
        o = compound([p_on[i] for i in idx])
        n = compound([p_in[i] for i in idx])
        print(f"    {y}: овернайт {o:>+7.1f}%   внутри {n:>+7.1f}%")
