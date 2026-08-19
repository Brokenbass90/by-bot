"""РАЗОГРЕТОСТЬ МОНЕТЫ КАК СЕЛЕКТОР ДЛЯ ОТБОЯ ОТ БАЗЫ.

Зачем. Владелец руками взял +13.92% на KAITO: заход от базы после отката
внутри сильного восходящего движения. Геометрия входа у нас уже закодирована
(BOUNCE1/ASB1). Чего у нас нет — **выбора монеты**: KAITO не было в универсуме.

Вопрос, который надо закрыть до того, как расширять универсум:

    отбой от базы в РАЗОГРЕТОЙ монете лучше, чем тот же отбой в холодной?

Если да — «разогретость» это признак для приоритизации слотов, и её надо
считать. Если нет — расширение универсума даст просто больше одинаковых
сделок, а выбирать между ними будет нечем.

Как меряем разогретость (два независимых признака):
  1. импульс   — доходность за 7 дней, РАНГ среди всех монет в этот день;
  2. объём     — объём за 3 дня к среднему за 30 дней.

Событие «отбой от базы»:
  * за последние 10 дней монета выросла (было восходящее движение);
  * цена откатилась и закрылась в пределах `--near` от минимума 5 дней;
  * вход по открытию следующего дня, удержание `--hold` дней.

Обязательный контроль: из результата вычитается равновзвешенная доходность
рынка за тот же период. Без этого на растущем рынке «разогретые» монеты
покажут плюс просто потому, что растёт всё.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import statistics
import sys

CACHE = "data_cache"


def load_daily(symbol: str):
    """Самый длинный 5m-кэш -> дневные бары {дата: (open, high, low, close, vol)}."""
    files = sorted(glob.glob(f"{CACHE}/{symbol}_5_*.json"),
                   key=os.path.getsize, reverse=True)
    if not files:
        return {}
    out = {}
    for b in json.load(open(files[0])):
        try:
            d = dt.datetime.utcfromtimestamp(b["ts"] / 1000).date()
            o, h, l, c = float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])
            v = float(b.get("v") or 0.0)
        except Exception:
            continue
        if d not in out:
            out[d] = [o, h, l, c, v]
        else:
            r = out[d]
            r[1] = max(r[1], h)
            r[2] = min(r[2], l)
            r[3] = c
            r[4] += v
    return {d: tuple(v) for d, v in out.items()}


def build(min_days: int = 400):
    data = {}
    for f in glob.glob(f"{CACHE}/*_5_*.json"):
        sym = os.path.basename(f).split("_5_")[0]
        if sym in data:
            continue
        d = load_daily(sym)
        if len(d) >= min_days:
            data[sym] = d
    dates = sorted(set().union(*[set(v) for v in data.values()])) if data else []
    return data, dates


def run(hold: int, near: float, upleg: int = 10, verbose: bool = True):
    data, dates = build()
    if len(data) < 6:
        print(f"мало символов с историей: {len(data)}")
        return
    idx = {d: i for i, d in enumerate(dates)}

    # рынок: равновзвешенная доходность на horizon=hold от открытия
    def market(i):
        if i + hold >= len(dates):
            return None
        d0, d1 = dates[i], dates[i + hold]
        rs = [s[d1][3] / s[d0][0] - 1.0
              for s in data.values() if d0 in s and d1 in s and s[d0][0] > 0]
        return statistics.fmean(rs) if len(rs) >= 5 else None

    mkt = {i: m for i in range(len(dates)) if (m := market(i)) is not None}

    events = []          # (импульс_ранг, объёмный_всплеск, избыточная_доходность)
    for sym, s in data.items():
        ds = sorted(s)
        for k in range(35, len(ds) - 1):
            d = ds[k]
            i = idx.get(d)
            if i is None or i not in mkt:
                continue
            win = ds[k - upleg:k + 1]
            if len(win) < upleg:
                continue
            c_now = s[d][3]
            c_then = s[win[0]][3]
            if c_then <= 0 or c_now <= c_then:      # восходящего движения не было
                continue
            low5 = min(s[x][2] for x in ds[k - 4:k + 1])
            if low5 <= 0 or (c_now / low5 - 1.0) > near:
                continue                             # не у базы
            # вход по открытию следующего дня
            d_in = ds[k + 1]
            i_in = idx.get(d_in)
            if i_in is None or i_in not in mkt or i_in + hold >= len(dates):
                continue
            d_out = dates[i_in + hold]
            if d_out not in s or s[d_in][0] <= 0:
                continue
            fwd = s[d_out][3] / s[d_in][0] - 1.0
            resid = fwd - mkt[i_in]

            mom = c_now / s[ds[k - 7]][3] - 1.0 if k >= 7 else 0.0
            v3 = statistics.fmean(s[x][4] for x in ds[k - 2:k + 1])
            v30 = statistics.fmean(s[x][4] for x in ds[k - 29:k + 1])
            vspike = (v3 / v30) if v30 > 0 else 1.0
            events.append((d, sym, mom, vspike, resid))

    if len(events) < 60:
        print(f"событий мало: {len(events)}")
        return

    # ранг импульса СРЕДИ монет в тот же день (иначе сравниваем разные эпохи)
    byday = {}
    for e in events:
        byday.setdefault(e[0], []).append(e)
    ranked = []
    for d, evs in byday.items():
        evs = sorted(evs, key=lambda x: x[2])
        n = len(evs)
        for r, e in enumerate(evs):
            ranked.append((r / max(1, n - 1) if n > 1 else 0.5, e[3], e[4]))

    print(f"РАЗОГРЕТОСТЬ КАК СЕЛЕКТОР — {len(data)} монет, {len(ranked)} событий")
    print(f"откат в пределах {near*100:.0f}% от минимума 5 дней, "
          f"удержание {hold} дн., избыточная доходность сверх рынка\n")

    def show(name, arr):
        if len(arr) < 25:
            print(f"  {name:<34} мало ({len(arr)})")
            return
        m = statistics.fmean(arr) * 100
        pos = sum(1 for x in arr if x > 0) / len(arr) * 100
        sd = statistics.pstdev(arr) * 100
        t = m / (sd / len(arr) ** 0.5) if sd > 0 else 0.0
        print(f"  {name:<34} {len(arr):>5} соб.  {m:>+7.2f}%  плюс {pos:>3.0f}%  t={t:>+5.2f}")

    print("ПО ИМПУЛЬСУ (ранг среди монет в тот же день):")
    show("холодные (нижняя треть)", [r for q, _, r in ranked if q < 0.33])
    show("средние", [r for q, _, r in ranked if 0.33 <= q < 0.67])
    show("РАЗОГРЕТЫЕ (верхняя треть)", [r for q, _, r in ranked if q >= 0.67])

    print("\nПО ОБЪЁМУ (объём 3д к среднему 30д):")
    show("объём обычный (<1.0)", [r for _, v, r in ranked if v < 1.0])
    show("объём повышен (1.0-1.5)", [r for _, v, r in ranked if 1.0 <= v < 1.5])
    show("объём ВСПЛЕСК (>1.5)", [r for _, v, r in ranked if v >= 1.5])

    print("\nОБА ПРИЗНАКА СРАЗУ:")
    show("разогрет И всплеск объёма", [r for q, v, r in ranked if q >= 0.67 and v >= 1.5])
    show("холодный И обычный объём", [r for q, v, r in ranked if q < 0.33 and v < 1.0])


if __name__ == "__main__":
    hold = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    near = float(sys.argv[2]) if len(sys.argv) > 2 else 0.04
    run(hold, near)
