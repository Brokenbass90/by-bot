#!/usr/bin/env python3
"""Honest OHLC backtest for candidate strategies RMR1 / TPB1 / LSR1.

Rules (deliberately conservative):
  * signal computed on bar close -> entry at NEXT bar open (no look-ahead);
  * exits checked on bar high/low; if SL and TP both touch in one bar -> SL;
  * time stop (default 96 x 1h bars) exits at close;
  * costs: taker fee 6 bps + slippage 2 bps per side = 16 bps round trip;
  * one position at a time per symbol; returns measured per notional + R-multiple.

Outputs per-symbol metrics and per-month fold breakdown (median month PF is the
robustness signal — one fat month must not carry the verdict).

Usage:
  python3 scripts/backtest_candidates.py --strategy rmr1 --symbols BTCUSDT,ETHUSDT,SOLUSDT
  python3 scripts/backtest_candidates.py --strategy tpb1 --symbols BTCUSDT,ETHUSDT,SOLUSDT
  python3 scripts/backtest_candidates.py --strategy lsr1 --symbols LINKUSDT,ADAUSDT,LTCUSDT,SOLUSDT
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.range_mean_reversion_v1 import RangeMeanReversionV1
from strategies.trend_pullback_v1 import TrendPullbackV1
from bot.liquidity_map import LiquiditySweepReversalV1

_HOUR_MS = 3_600_000
WINDOW = 260  # bars of history passed to signal() (bounded => O(n) total)


def load_1h_ohlc(sym: str, cache_dir: str = "data_cache", input_json: str = ""):
    """Merge all 5m cache files, resample to 1h OHLC. Returns (ts, o, h, l, c) lists."""
    five: Dict[int, Tuple[float, float, float, float]] = {}
    source_files = [input_json] if input_json else sorted(glob.glob(f"{cache_dir}/{sym}_5_*.json"))
    for f in source_files:
        try:
            payload = json.load(open(f))
        except Exception:
            continue
        if input_json:
            if not isinstance(payload, dict) or payload.get("symbol") != sym:
                raise ValueError(f"explicit input symbol mismatch: requested={sym} payload={payload.get('symbol') if isinstance(payload, dict) else None}")
            rows = payload.get("records") or []
        else:
            rows = payload
        for r in rows:
            try:
                ts = int(r.get("ts", r.get("ts_ms")))
                five[ts] = (
                    float(r.get("o", r.get("open"))),
                    float(r.get("h", r.get("high"))),
                    float(r.get("l", r.get("low"))),
                    float(r.get("c", r.get("close"))),
                )
            except Exception:
                continue
    hours: Dict[int, List[Tuple[int, Tuple[float, float, float, float]]]] = defaultdict(list)
    for ts, bar in five.items():
        hours[ts - (ts % _HOUR_MS)].append((ts, bar))
    ts_l, o_l, h_l, l_l, c_l = [], [], [], [], []
    for hour in sorted(hours):
        bars = sorted(hours[hour])
        ts_l.append(hour)
        o_l.append(bars[0][1][0])
        h_l.append(max(b[1][1] for b in bars))
        l_l.append(min(b[1][2] for b in bars))
        c_l.append(bars[-1][1][3])
    return ts_l, o_l, h_l, l_l, c_l


def run_symbol(strategy, ts, o, h, l, c, fee_rt: float = 0.0016, time_stop: int = 96):
    trades: List[dict] = []
    n = len(ts)
    i = WINDOW
    while i < n - 1:
        sig = strategy.signal(h[max(0, i - WINDOW):i + 1],
                              l[max(0, i - WINDOW):i + 1],
                              c[max(0, i - WINDOW):i + 1])
        if not sig:
            i += 1
            continue
        side = sig["side"]
        entry = o[i + 1]  # next bar open — honest fill
        # re-anchor sl/tp distance to the actual fill (signal priced off close)
        sl = sig["sl"] + (entry - sig["entry"])
        tp = sig["tp"] + (entry - sig["entry"])
        stop_pct = abs(entry - sl) / entry
        if stop_pct <= 0:
            i += 1
            continue
        exit_px, exit_reason, j = None, "", i + 1
        while j < n:
            if side == "long":
                hit_sl = l[j] <= sl
                hit_tp = h[j] >= tp
            else:
                hit_sl = h[j] >= sl
                hit_tp = l[j] <= tp
            if hit_sl:                 # conservative: SL wins ties
                exit_px, exit_reason = sl, "SL"
                break
            if hit_tp:
                exit_px, exit_reason = tp, "TP"
                break
            if j - i >= time_stop:
                exit_px, exit_reason = c[j], "time"
                break
            j += 1
        if exit_px is None:
            exit_px, exit_reason, j = c[n - 1], "eod", n - 1
        raw = (exit_px - entry) / entry if side == "long" else (entry - exit_px) / entry
        net = raw - fee_rt
        trades.append({
            "month": datetime.fromtimestamp(ts[i] / 1000, tz=timezone.utc).strftime("%Y-%m"),
            "side": side, "pnl_pct": net * 100.0, "r_mult": net / stop_pct,
            "stop_pct": stop_pct * 100.0, "exit": exit_reason, "hold": j - i,
        })
        i = j + 1  # next entry only after exit
    return trades


def metrics(trades: List[dict]):
    if not trades:
        return {"trades": 0}
    wins = [t["pnl_pct"] for t in trades if t["pnl_pct"] > 0]
    losses = [-t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    pf = (sum(wins) / sum(losses)) if losses and sum(losses) > 0 else 99.0
    by_month = defaultdict(list)
    for t in trades:
        by_month[t["month"]].append(t["pnl_pct"])
    month_pf = {}
    for m, ps in sorted(by_month.items()):
        w = sum(p for p in ps if p > 0); lo = -sum(p for p in ps if p <= 0)
        month_pf[m] = round(w / lo, 2) if lo > 0 else 99.0
    mpfs = sorted(month_pf.values())
    return {
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades), 3),
        "profit_factor": round(min(pf, 99.0), 3),
        "expectancy_pct": round(sum(t["pnl_pct"] for t in trades) / len(trades), 4),
        "expectancy_R": round(sum(t["r_mult"] for t in trades) / len(trades), 3),
        "total_pct_on_notional": round(sum(t["pnl_pct"] for t in trades), 2),
        "median_month_pf": mpfs[len(mpfs) // 2] if mpfs else None,
        "months_positive": sum(1 for v in month_pf.values() if v > 1.0),
        "months_total": len(month_pf),
        "month_pf": month_pf,
        "exits": {k: sum(1 for t in trades if t["exit"] == k) for k in ("SL", "TP", "time", "eod")},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=("rmr1", "tpb1", "lsr1"), required=True)
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--fee-rt-bps", type=float, default=16.0)
    ap.add_argument("--time-stop", type=int, default=96)
    ap.add_argument("--input-json", default="", help="explicit single-symbol immutable M5 input")
    ap.add_argument("--input-root", default="", help="root containing SYMBOL/SYMBOL.json immutable inputs")
    ap.add_argument("--result-out", default="")
    args = ap.parse_args()
    symbols = [sym.strip() for sym in args.symbols.split(",") if sym.strip()]
    if args.input_json and args.input_root:
        ap.error("use only one of --input-json or --input-root")
    if args.input_json and len(symbols) != 1:
        ap.error("--input-json requires exactly one --symbols value")
    out = {}
    all_trades: List[dict] = []
    bar_ranges = {}
    input_files = {}
    for sym in symbols:
        if args.strategy == "rmr1":
            strat = RangeMeanReversionV1()
        elif args.strategy == "tpb1":
            strat = TrendPullbackV1()
        else:
            strat = LiquiditySweepReversalV1()
        explicit_input = args.input_json
        if args.input_root:
            explicit_input = str(Path(args.input_root) / sym / f"{sym}.json")
        ts, o, h, l, c = load_1h_ohlc(sym, input_json=explicit_input)
        if len(ts) < WINDOW + 100:
            out[sym] = {"error": f"not_enough_bars_{len(ts)}"}
            continue
        bar_ranges[sym] = {"bars_1h": len(ts), "first_ts_ms": ts[0], "last_ts_ms": ts[-1]}
        if explicit_input:
            input_files[sym] = explicit_input
        trades = run_symbol(strat, ts, o, h, l, c,
                            fee_rt=args.fee_rt_bps / 10000.0, time_stop=args.time_stop)
        for trade in trades:
            trade["symbol"] = sym
        all_trades.extend(trades)
        out[sym] = metrics(trades)
    result = {
        "schema_id": "candidate_hourly_next_open_replay_v1",
        "authority": "research_only_no_live_or_promotion",
        "strategy": args.strategy,
        "symbols": symbols,
        "input_json": args.input_json or None,
        "input_root": args.input_root or None,
        "input_files": input_files,
        "fee_round_trip_bps": args.fee_rt_bps,
        "time_stop_1h_bars": args.time_stop,
        "sealed_holdout_rows_decoded": 0 if (args.input_json or args.input_root) else None,
        "bar_ranges": bar_ranges,
        "aggregate": metrics(all_trades),
        "results": out,
    }
    rendered = json.dumps(result, indent=2)
    if args.result_out:
        path = Path(args.result_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
