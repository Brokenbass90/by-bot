"""ЭКСПИРАЦИЯ ОПЦИОНОВ — проверка по КАЛЕНДАРЮ, без опционных данных.

Идея обхода. Опционных цепочек и открытого интереса по страйкам у нас нет,
и добывать их дорого. Но даты экспираций Deribit детерминированы:
**каждая пятница 08:00 UTC**, месячная — последняя пятница месяца,
квартальная — последняя пятница марта/июня/сентября/декабря.

Значит календарную часть гипотезы можно фальсифицировать прямо сейчас.
Если эффекта нет даже в виде «в дни экспираций рынок ведёт себя иначе»,
то покупать опционные данные незачем — это экономит недели.

Что проверяется:
  1. ДРЕЙФ до экспирации (T-3д -> T) и после (T -> T+3д);
  2. ПИННИНГ: подавлена ли реализованная волатильность перед экспирацией;
  3. каждая гипотеза сравнивается с КОНТРОЛЕМ — теми же окнами, сдвинутыми
     на неделю. Без контроля мы измерили бы общий дрейф рынка, а не эффект.

Почему контроль обязателен. За 2023-2026 крипта в среднем росла. Любое
окно «за 3 дня до чего угодно» покажет плюс. Разница с контролем — это
единственное, что может быть эффектом события.

Единицы: всё в bps (1 bps = 0.01%). Круговая комиссия у нас ~4-8 bps,
поэтому эффект меньше ~15 bps не оправдывает ногу.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os
import statistics
import sys

CACHE = "data_cache"
BAR_MS = 5 * 60 * 1000


def load(symbol: str):
    """Самый длинный 5m-кэш по символу -> отсортированный список баров."""
    files = sorted(glob.glob(f"{CACHE}/{symbol}_5_*.json"),
                   key=os.path.getsize, reverse=True)
    if not files:
        return []
    rows = json.load(open(files[0]))
    rows = [r for r in rows if r.get("o") and r.get("c")]
    rows.sort(key=lambda r: r["ts"])
    return rows


def index_by_ts(bars):
    return {b["ts"]: i for i, b in enumerate(bars)}


def expiries(bars):
    """Все пятницы 08:00 UTC, покрытые данными. Помечаются месячные."""
    if not bars:
        return []
    t0 = dt.datetime.utcfromtimestamp(bars[0]["ts"] / 1000).date()
    t1 = dt.datetime.utcfromtimestamp(bars[-1]["ts"] / 1000).date()
    out = []
    d = t0
    while d <= t1:
        if d.weekday() == 4:  # пятница
            # месячная = следующей пятницы уже нет в этом месяце
            nxt = d + dt.timedelta(days=7)
            out.append((d, nxt.month != d.month))
        d += dt.timedelta(days=1)
    return out


def ts_of(day: dt.date, hour: int = 8) -> int:
    return int(dt.datetime(day.year, day.month, day.day, hour,
                           tzinfo=dt.timezone.utc).timestamp() * 1000)


def ret_bps(bars, idx, t_from: int, t_to: int):
    i, j = idx.get(t_from), idx.get(t_to)
    if i is None or j is None or j <= i:
        return None
    a, b = bars[i]["o"], bars[j]["o"]
    return (b / a - 1.0) * 10000 if a > 0 else None


def realized_vol_bps(bars, idx, t_from: int, t_to: int):
    """Реализованная волатильность 5m-доходностей в окне, в bps."""
    i, j = idx.get(t_from), idx.get(t_to)
    if i is None or j is None or j - i < 30:
        return None
    rs = []
    for k in range(i + 1, j + 1):
        p0, p1 = bars[k - 1]["c"], bars[k]["c"]
        if p0 > 0 and p1 > 0:
            rs.append(math.log(p1 / p0))
    if len(rs) < 30:
        return None
    return statistics.pstdev(rs) * 10000


def collect(symbol: str, days: int, monthly_only: bool):
    bars = load(symbol)
    if not bars:
        return None
    idx = index_by_ts(bars)
    span = days * 24 * 60 * 60 * 1000

    res = {k: [] for k in ("pre", "post", "pre_ctrl", "post_ctrl",
                           "vol_pre", "vol_ctrl")}
    n_ev = 0
    for day, is_monthly in expiries(bars):
        if monthly_only and not is_monthly:
            continue
        t = ts_of(day)
        # контроль: то же окно неделей раньше (пятница, тот же час, НЕ экспирация
        # для месячного теста; для недельного — сдвиг на 3.5 дня, вторник 08:00)
        tc = t - (7 if monthly_only else 3) * 24 * 60 * 60 * 1000 \
             - (0 if monthly_only else 12 * 60 * 60 * 1000)

        vals = {
            "pre":       ret_bps(bars, idx, t - span, t),
            "post":      ret_bps(bars, idx, t, t + span),
            "pre_ctrl":  ret_bps(bars, idx, tc - span, tc),
            "post_ctrl": ret_bps(bars, idx, tc, tc + span),
            "vol_pre":   realized_vol_bps(bars, idx, t - span, t),
            "vol_ctrl":  realized_vol_bps(bars, idx, tc - span, tc),
        }
        if any(v is None for v in vals.values()):
            continue
        for k, v in vals.items():
            res[k].append(v)
        n_ev += 1
    res["n"] = n_ev
    return res


def t_stat(a, b):
    """Двухвыборочный t (Welch) — есть ли вообще разница со случайностью."""
    if len(a) < 5 or len(b) < 5:
        return 0.0
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va = statistics.variance(a) / len(a)
    vb = statistics.variance(b) / len(b)
    s = math.sqrt(va + vb)
    return (ma - mb) / s if s > 0 else 0.0


def report(symbol: str, days: int, monthly_only: bool):
    r = collect(symbol, days, monthly_only)
    if not r or r["n"] < 5:
        print(f"{symbol}: недостаточно событий")
        return
    kind = "МЕСЯЧНЫЕ" if monthly_only else "все недельные"
    print(f"\n{symbol} — {kind}, окно ±{days}д, {r['n']} событий")

    for label, key, ckey in (("дрейф ДО экспирации", "pre", "pre_ctrl"),
                             ("дрейф ПОСЛЕ экспирации", "post", "post_ctrl")):
        m = statistics.fmean(r[key])
        c = statistics.fmean(r[ckey])
        t = t_stat(r[key], r[ckey])
        pos = sum(1 for x in r[key] if x > 0) / len(r[key]) * 100
        print(f"  {label:<24} {m:>+8.1f} bps   контроль {c:>+8.1f}   "
              f"разница {m-c:>+8.1f}   t={t:>+5.2f}   плюсовых {pos:.0f}%")

    vp = statistics.fmean(r["vol_pre"])
    vc = statistics.fmean(r["vol_ctrl"])
    tv = t_stat(r["vol_pre"], r["vol_ctrl"])
    print(f"  {'волатильность ДО':<24} {vp:>8.1f} bps   контроль {vc:>8.1f}   "
          f"отношение {vp/vc if vc else 0:>7.3f}   t={tv:>+5.2f}")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print("ЭКСПИРАЦИЯ ОПЦИОНОВ — календарный тест, контроль = сдвиг на неделю")
    print("Порог осмысленности: разница с контролем > ~15 bps (круг 4-8 bps).")
    for sym in ("BTCUSDT", "ETHUSDT"):
        for mo in (True, False):
            report(sym, days, mo)
