#!/usr/bin/env python3
"""
Quick runner: test london_open_breakout_v1 and ema_trend_pullback_v2
across all available M5 CSVs and print a summary table.

Usage:
    python scripts/run_forex_new_strategies.py
    python scripts/run_forex_new_strategies.py --data-dir path/to/data_cache/forex
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv
from forex.engine import EngineConfig, run_backtest
from forex.strategies.london_open_breakout_v1 import Config as LobConfig, LondonOpenBreakoutV1
from forex.strategies.ema_trend_pullback_v2 import Config as EmaConfig, EmaTrendPullbackV2


PAIRS = [
    ("EURUSD", 0.0001, 1.2),
    ("GBPUSD", 0.0001, 1.5),
    ("USDJPY", 0.01,   1.2),
    ("AUDUSD", 0.0001, 1.5),
    ("USDCAD", 0.0001, 2.0),
    ("USDCHF", 0.0001, 2.0),
    ("NZDUSD", 0.0001, 2.0),
    ("GBPJPY", 0.01,   2.5),
    ("EURJPY", 0.01,   1.8),
    ("AUDJPY", 0.01,   2.0),
    ("CADJPY", 0.01,   2.0),
    ("EURGBP", 0.0001, 1.5),
]

def _fmt(v: float, decimals: int = 1) -> str:
    if v != v:
        return "nan"
    return f"{v:+.{decimals}f}"


def run_pair(symbol: str, pip_size: float, spread_pips: float, data_dir: Path):
    csv_path = data_dir / f"{symbol}_M5.csv"
    if not csv_path.exists():
        return None

    candles = load_m5_csv(str(csv_path))
    if len(candles) < 1000:
        return None

    results = []

    # ── Strategy 1: London Open Breakout ───────────────────────────────
    lob_cfg = LobConfig(pip_size=pip_size)
    # JPY pairs: different pip ranges
    if symbol.endswith("JPY"):
        lob_cfg.min_range_pips = 80.0
        lob_cfg.max_range_pips = 600.0
        lob_cfg.breakout_buffer_pips = 15.0
        lob_cfg.sl_buffer_pips = 30.0
        lob_cfg.min_atr_pips = 30.0

    eng_cfg = EngineConfig(
        pip_size=pip_size,
        spread_pips=spread_pips,
        swap_long_pips_per_day=-0.3,
        swap_short_pips_per_day=-0.3,
        risk_per_trade_pct=0.005,
    )
    lob = LondonOpenBreakoutV1(lob_cfg)
    _, s1 = run_backtest(candles, lob, eng_cfg)
    results.append(("lob_v1", s1))

    # ── Strategy 2: EMA Trend Pullback V2 ──────────────────────────────
    ema_cfg = EmaConfig(pip_size=pip_size)
    if symbol.endswith("JPY"):
        ema_cfg.min_atr_pips = 30.0

    ema_strat = EmaTrendPullbackV2(ema_cfg)
    _, s2 = run_backtest(candles, ema_strat, eng_cfg)
    results.append(("ema_pb_v2", s2))

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT / "data_cache" / "forex"))
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    print(f"\n{'─'*100}")
    print(f"  Forex New-Strategy Backtest — data: {data_dir}")
    print(f"{'─'*100}")
    hdr = f"{'Symbol':<10} {'Strategy':<16} {'Trades':>6} {'WR%':>6} {'NetPips':>9} {'MaxDD':>8} {'SumR':>7} {'RetPct%':>8}"
    print(hdr)
    print(f"{'─'*100}")

    totals: dict[str, list] = {}

    for symbol, pip_size, spread in PAIRS:
        res = run_pair(symbol, pip_size, spread, data_dir)
        if res is None:
            print(f"  {symbol:<10} — no data")
            continue
        for strat_name, s in res:
            tag = f"{symbol:<10} {strat_name:<16}"
            row = (
                f"  {tag}"
                f" {s.trades:>6}"
                f" {s.winrate:>6.1f}"
                f" {_fmt(s.net_pips, 1):>9}"
                f" {_fmt(s.max_dd_pips, 1):>8}"
                f" {_fmt(s.sum_r, 2):>7}"
                f" {_fmt(s.return_pct_est, 2):>8}"
            )
            print(row)
            totals.setdefault(strat_name, []).append(s)

    print(f"{'─'*100}")
    for strat_name, summaries in totals.items():
        total_trades = sum(s.trades for s in summaries)
        total_pips = sum(s.net_pips for s in summaries)
        total_r = sum(s.sum_r for s in summaries)
        avg_wr = sum(s.winrate for s in summaries) / max(1, len(summaries))
        print(f"  {'TOTAL':<10} {strat_name:<16} {total_trades:>6} {avg_wr:>6.1f} {_fmt(total_pips, 1):>9}  {'':>8} {_fmt(total_r, 2):>7}")
    print(f"{'─'*100}\n")


if __name__ == "__main__":
    main()
