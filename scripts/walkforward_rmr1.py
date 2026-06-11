#!/usr/bin/env python3
"""Walk-forward parameter selection for RMR1 (range mean-reversion) (2026-06-10).

Default RMR1 config loses money on majors (PF 0.6-0.7, see
scripts/backtest_candidates.py). Before discarding the idea, test honestly
whether SOME config region works when chosen WITHOUT look-ahead:
  * run a small grid over the full series, tag every trade with its month;
  * for each month M: pick the config with best total pnl over months M-2..M-1
    (need >= min_is_trades trades), then count ONLY month-M trades of that config
    as out-of-sample;
  * aggregate OOS months -> verdict by median month PF.

Usage: python3 scripts/walkforward_rmr1.py --symbol BTCUSDT
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.backtest_candidates as bc
from strategies.range_mean_reversion_v1 import RangeMeanReversionV1, RMRConfig

bc.WINDOW = 60  # RMR1 needs ~36 bars of history; small window = fast grid

GRID = {
    "sl_atr_mult": (1.2, 2.0, 3.0),
    "bb_k": (2.0, 2.5),
    "max_trend_slope_pct": (0.10, 0.20),
}


def month_pnl(trades, month):
    return [t for t in trades if t["month"] == month]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--time-stop", type=int, default=72)
    ap.add_argument("--min-is-trades", type=int, default=6)
    args = ap.parse_args()

    ts, o, h, l, c = bc.load_1h_ohlc(args.symbol)
    runs = {}
    for combo in itertools.product(*GRID.values()):
        cfg_kwargs = dict(zip(GRID.keys(), combo))
        strat = RangeMeanReversionV1(RMRConfig(**cfg_kwargs))
        trades = bc.run_symbol(strat, ts, o, h, l, c, time_stop=args.time_stop)
        runs[json.dumps(cfg_kwargs)] = trades

    months = sorted({t["month"] for tr in runs.values() for t in tr})
    oos_trades = []
    picks = defaultdict(int)
    rows = []
    for mi in range(2, len(months)):
        is_months = {months[mi - 2], months[mi - 1]}
        best_key, best_pnl = None, None
        for key, trades in runs.items():
            is_tr = [t for t in trades if t["month"] in is_months]
            if len(is_tr) < args.min_is_trades:
                continue
            pnl = sum(t["pnl_pct"] for t in is_tr)
            if best_pnl is None or pnl > best_pnl:
                best_key, best_pnl = key, pnl
        if best_key is None:
            rows.append({"month": months[mi], "note": "no_config_enough_IS_trades"})
            continue
        mt = month_pnl(runs[best_key], months[mi])
        oos_trades.extend(mt)
        picks[best_key] += 1
        w = sum(t["pnl_pct"] for t in mt if t["pnl_pct"] > 0)
        lo = -sum(t["pnl_pct"] for t in mt if t["pnl_pct"] <= 0)
        rows.append({"month": months[mi], "picked": json.loads(best_key),
                     "is_pnl": round(best_pnl, 2),
                     "oos_n": len(mt), "oos_pnl_pct": round(sum(t["pnl_pct"] for t in mt), 2),
                     "oos_pf": round(w / lo, 2) if lo > 0 else (99.0 if w > 0 else None)})

    pfs = [r["oos_pf"] for r in rows if r.get("oos_pf") is not None]
    pfs_sorted = sorted(pfs)
    out = {
        "symbol": args.symbol,
        "oos_months": len(pfs),
        "oos_trades": len(oos_trades),
        "oos_total_pnl_pct": round(sum(t["pnl_pct"] for t in oos_trades), 2),
        "oos_median_month_pf": pfs_sorted[len(pfs_sorted) // 2] if pfs_sorted else None,
        "oos_months_positive": sum(1 for r in rows if (r.get("oos_pnl_pct") or 0) > 0),
        "config_picks": {k: v for k, v in sorted(picks.items(), key=lambda kv: -kv[1])},
        "months": rows,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
