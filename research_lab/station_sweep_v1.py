"""Станция sweep-reclaim: 64 комбо, тройной гейт + net всех комбо.
Запуск на Mac (можно ПАРАЛЛЕЛЬНО wide_v1):
    nohup bash research_lab/run_station.sh sweep_v1 station_sweep_v1.py >/dev/null 2>&1 &
"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
from search_station import run
from sweep_reclaim import SweepReclaim

IS_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT",
              "LINKUSDT", "AVAXUSDT", "XRPUSDT", "DOGEUSDT"]
OOS_SYMBOLS = ["ATOMUSDT", "DOTUSDT", "LTCUSDT", "1000PEPEUSDT"]


def build_registry():
    def b(p):
        def fac():
            return SweepReclaim(**p)
        return fac
    grid = {
        "side": ["long", "short"],
        "min_touches": [2, 3],
        "sweep_atr": [0.30, 0.50],
        "rr": [1.5, 2.0],
        "confirm_close": [True, False],
        "time_stop_bars": [96, 192],
    }
    return [("sweep_reclaim", b, grid)]


if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else "sweep_v1"
    run(run_id, build_registry(), IS_SYMBOLS, OOS_SYMBOLS)
