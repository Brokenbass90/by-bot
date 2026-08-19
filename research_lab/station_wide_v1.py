"""ШИРОКАЯ СТАНЦИЯ v1: sloped-retest варианты + horizontal break-retest (128 комбо).

Запуск на Mac (ночь, resumable, можно прерывать):
    cd <repo>
    nohup bash research_lab/run_station.sh wide_v1 station_wide_v1.py >/dev/null 2>&1 &
Прогресс: tail -5 research_lab/results/wide_v1.log  (готово = слово ГОТОВО)

Станция теперь пишет net КАЖДОГО комбо -> после прогона видно «живое ядро»
даже среди не-выживших, и лучшие семейства пойдут на holdout-экзамен как TSM.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from search_station import run
from sloped_break_retest import SlopedBreakRetest
from horizontal_break_retest import HorizontalBreakRetest

IS_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT",
              "LINKUSDT", "AVAXUSDT", "XRPUSDT", "DOGEUSDT"]
OOS_SYMBOLS = ["ATOMUSDT", "DOTUSDT", "LTCUSDT", "1000PEPEUSDT"]


def build_registry():
    def sb(p):
        def fac():
            return SlopedBreakRetest(**p)
        return fac

    def hb(p):
        def fac():
            return HorizontalBreakRetest(**p)
        return fac

    sloped_grid = {
        "side": ["short", "long"],
        "entry_style": ["reject", "touch"],
        "sl_mode": ["line", "tight"],
        "retest_tol": [0.25, 0.40],
        "rr": [1.8, 2.5],
        "max_wait_h": [24.0, 48.0],
    }
    horiz_grid = {
        "side": ["long", "short"],
        "min_touches": [2, 3],
        "retest_tol": [0.25, 0.40],
        "rr": [1.8, 2.5],
        "max_wait_h": [24.0, 48.0],
    }
    return [("sloped_v2", sb, sloped_grid), ("horizontal_br", hb, horiz_grid)]


if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else "wide_v1"
    run(run_id, build_registry(), IS_SYMBOLS, OOS_SYMBOLS)
