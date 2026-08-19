"""Станция поиска: sloped break -> retest (64 комбо, тройной анти-overfit гейт).

Запуск (Mac, долгий, resumable):
    cd <repo> && PYTHONPATH=. python3 research_lab/station_sloped_v1.py sloped_v1
или через caffeinate-обёртку:
    bash research_lab/run_station.sh sloped_v1   # если run_station.sh параметризован

Смоук (быстрый, 1 комбо, укороченные данные):
    PYTHONPATH=. python3 research_lab/station_sloped_v1.py --smoke
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from search_station import run, load, _bt, _gate  # noqa: E402
from sloped_break_retest import SlopedBreakRetest  # noqa: E402

IS_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT",
              "LINKUSDT", "AVAXUSDT", "XRPUSDT", "DOGEUSDT"]
OOS_SYMBOLS = ["ATOMUSDT", "DOTUSDT", "LTCUSDT", "1000PEPEUSDT"]


def build_registry():
    def builder(p):
        def fac():
            return SlopedBreakRetest(**p)
        return fac

    grid = {
        "side": ["short", "long"],
        "pivot_lr": [2, 3],
        "lookback_1h": [180, 360],
        "retest_tol": [0.25, 0.40],
        "rr": [1.8, 2.5],
        "max_wait_h": [24.0, 48.0],
    }
    return [("sloped_break_retest", builder, grid)]


def smoke():
    """Быстрая проверка: логика生ит сделки и не падает. НЕ вердикт."""
    import search_station
    search_station._CACHE.clear()
    fac = lambda: SlopedBreakRetest(side="short", pivot_lr=2, lookback_1h=180,
                                    retest_tol=0.40, rr=1.8, max_wait_h=48.0)
    for sym in ("LINKUSDT", "SOLUSDT"):
        cs = load(sym, cap=40000)  # ~140 дней 5m
        if not cs:
            print(f"{sym}: нет кэша")
            continue
        search_station._CACHE[sym] = cs
        tr, by = _bt(fac, [sym], "all")
        net = round(sum(t["r"] for t in tr), 2)
        print(f"{sym}: trades={len(tr)} net={net}R")
    print("smoke done (это НЕ вердикт — вердикт только через полный гейт)")


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        smoke()
    else:
        run_id = sys.argv[1] if len(sys.argv) > 1 else "sloped_v1"
        run(run_id, build_registry(), IS_SYMBOLS, OOS_SYMBOLS)
