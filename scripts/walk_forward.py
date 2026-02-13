#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Walk-forward portfolio backtest with dynamic symbol exclusion.

Strategy:
1) Run a portfolio backtest on a window (trade_days).
2) Rank symbols by PnL within a lookback window (lookback_days).
3) Exclude worst N symbols for the next window.
4) Repeat. Excluded symbols can return because exclusions are recalculated
   each window from the latest trades.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backtest.bybit_data import DEFAULT_BYBIT_BASE, fetch_klines_public
from backtest.engine import BacktestParams, Candle, KlineStore
from backtest.metrics import summarize_trades
from backtest.portfolio_engine import run_portfolio_backtest
from strategies.bounce_bt import BounceBTStrategy
from strategies.bounce_bt_v2 import BounceBTV2Strategy
from strategies.inplay_wrapper import InPlayWrapper
from strategies.inplay_breakout import InPlayBreakoutWrapper
from strategies.inplay_pullback import InPlayPullbackWrapper
from strategies.pump_fade import PumpFadeStrategy
from strategies.range_wrapper import RangeWrapper
from strategies.retest_backtest import RetestBacktestStrategy
from strategies.momentum_continuation import MomentumContinuationStrategy
from strategies.trend_pullback import TrendPullbackStrategy
from strategies.trend_regime_breakout import TrendRegimeBreakoutStrategy
from strategies.vol_breakout import VolatilityBreakoutStrategy


def _parse_date(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)


def _fmt_date(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%d")


def _parse_ts_ms(v: str) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def _score_symbols(
    trades_csv: str,
    *,
    lookback_days: int,
    min_trades: int,
    end_ts_utc: float,
) -> Dict[str, Tuple[float, int]]:
    cutoff = None
    if lookback_days and lookback_days > 0:
        cutoff = float(end_ts_utc) - lookback_days * 86400

    per: Dict[str, Dict[str, float]] = defaultdict(lambda: {"pnl": 0.0, "trades": 0.0})
    with open(trades_csv, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            ts = _parse_ts_ms(row.get("exit_ts", "0"))
            if cutoff is not None and (ts / 1000.0) < cutoff:
                continue
            sym = row.get("symbol", "")
            if not sym:
                continue
            pnl = float(row.get("pnl", 0.0) or 0.0)
            per[sym]["pnl"] += pnl
            per[sym]["trades"] += 1

    scored: Dict[str, Tuple[float, int]] = {}
    for sym, v in per.items():
        trades = int(v["trades"])
        if trades >= int(min_trades):
            scored[sym] = (float(v["pnl"]), trades)
    return scored


def _pick_worst(scored: Dict[str, Tuple[float, int]], exclude_worst: int) -> List[str]:
    rows = [(sym, pnl, trades) for sym, (pnl, trades) in scored.items()]
    rows.sort(key=lambda x: x[1])  # ascending pnl
    return [sym for sym, _, _ in rows[: max(0, int(exclude_worst))]]


def _load_full_candles(
    symbols: List[str],
    *,
    start_ms: int,
    end_ms: int,
    bybit_base: str,
    polite_sleep_sec: float,
) -> Dict[str, List[Candle]]:
    out: Dict[str, List[Candle]] = {}
    for sym in symbols:
        kl = fetch_klines_public(
            sym,
            interval="5",
            start_ms=start_ms,
            end_ms=end_ms,
            base=bybit_base,
            cache=True,
            polite_sleep_sec=polite_sleep_sec,
        )
        candles = [Candle(ts=k.ts, o=k.o, h=k.h, l=k.l, c=k.c, v=k.v) for k in kl]
        out[sym] = candles
    return out


def _slice_candles(candles: List[Candle], start_ms: int, end_ms: int) -> List[Candle]:
    return [c for c in candles if start_ms <= int(c.ts) < end_ms]


def _run_portfolio_local(
    *,
    symbols: List[str],
    strategies: List[str],
    candles_by_sym: Dict[str, List[Candle]],
    start_ms: int,
    end_ms: int,
    params: BacktestParams,
    out_dir: Path,
    tag: str,
) -> Tuple[str, str]:
    stores: Dict[str, KlineStore] = {}
    for sym in symbols:
        c5 = _slice_candles(candles_by_sym.get(sym, []), start_ms, end_ms)
        if not c5:
            continue
        stores[sym] = KlineStore(sym, c5)

    if not stores:
        raise RuntimeError("No candles available for the selected window.")

    syms = list(stores.keys())

    bounce = {sym: BounceBTStrategy() for sym in syms} if "bounce" in strategies else {}
    bounce_v2 = {sym: BounceBTV2Strategy() for sym in syms} if "bounce_v2" in strategies else {}
    range_wrappers = {sym: RangeWrapper(fetch_klines=stores[sym].fetch_klines) for sym in syms} if "range" in strategies else {}
    inplay = {sym: InPlayWrapper() for sym in syms} if "inplay" in strategies else {}
    breakout = {sym: InPlayBreakoutWrapper() for sym in syms} if "inplay_breakout" in strategies else {}
    pullback = {sym: InPlayPullbackWrapper() for sym in syms} if "inplay_pullback" in strategies else {}
    pump_fade = {sym: PumpFadeStrategy() for sym in syms} if "pump_fade" in strategies else {}
    retest = {sym: RetestBacktestStrategy(stores[sym]) for sym in syms} if "retest_levels" in strategies else {}
    momentum = {sym: MomentumContinuationStrategy() for sym in syms} if "momentum" in strategies else {}
    trend_pullback = {sym: TrendPullbackStrategy() for sym in syms} if "trend_pullback" in strategies else {}
    trend_breakout = {sym: TrendRegimeBreakoutStrategy() for sym in syms} if "trend_breakout" in strategies else {}
    vol_breakout = {sym: VolatilityBreakoutStrategy() for sym in syms} if "vol_breakout" in strategies else {}

    def selector(sym: str, store: KlineStore, ts_ms: int, last_price: float):
        for st in strategies:
            if st == "bounce":
                sig = bounce[sym].maybe_signal(store, ts_ms, last_price)
            elif st == "bounce_v2":
                sig = bounce_v2[sym].maybe_signal(store, ts_ms, last_price)
            elif st == "range":
                sig = range_wrappers[sym].signal(store, ts_ms, last_price)
            elif st == "inplay":
                sig = inplay[sym].signal(store, ts_ms, last_price)
            elif st == "inplay_breakout":
                sig = breakout[sym].signal(store, ts_ms, last_price)
            elif st == "inplay_pullback":
                sig = pullback[sym].signal(store, ts_ms, last_price)
            elif st == "pump_fade":
                i = getattr(store, "i5", getattr(store, "i", None))
                if i is None:
                    raise AttributeError("KlineStore missing current index (expected i5)")
                bar = store.c5[int(i)]
                sig = pump_fade[sym].maybe_signal(sym, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "retest_levels":
                sig = retest[sym].signal(store, ts_ms, last_price)
            elif st == "momentum":
                i = getattr(store, "i5", getattr(store, "i", None))
                if i is None:
                    raise AttributeError("KlineStore missing current index (expected i5)")
                bar = store.c5[int(i)]
                sig = momentum[sym].maybe_signal(sym, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "trend_pullback":
                i = getattr(store, "i5", getattr(store, "i", None))
                if i is None:
                    raise AttributeError("KlineStore missing current index (expected i5)")
                bar = store.c5[int(i)]
                sig = trend_pullback[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "trend_breakout":
                i = getattr(store, "i5", getattr(store, "i", None))
                if i is None:
                    raise AttributeError("KlineStore missing current index (expected i5)")
                bar = store.c5[int(i)]
                sig = trend_breakout[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "vol_breakout":
                i = getattr(store, "i5", getattr(store, "i", None))
                if i is None:
                    raise AttributeError("KlineStore missing current index (expected i5)")
                bar = store.c5[int(i)]
                sig = vol_breakout[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            else:
                sig = None
            if sig is not None:
                return sig
        return None

    res = run_portfolio_backtest(stores, selector, params=params, symbols_order=syms)

    out_dir.mkdir(parents=True, exist_ok=True)
    trades_path = out_dir / "trades.csv"
    with trades_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "strategy","symbol","side","entry_ts","exit_ts","entry_price","exit_price","qty","pnl","pnl_pct_equity","fees","outcome","reason"
        ])
        for t in res.trades:
            w.writerow([
                t.strategy, t.symbol, t.side, t.entry_ts, t.exit_ts,
                f"{t.entry_price:.8f}", f"{t.exit_price:.8f}", f"{t.qty:.8f}",
                f"{t.pnl:.8f}", f"{t.pnl_pct_equity:.6f}", f"{t.fees:.8f}", t.outcome, t.reason
            ])

    overall = summarize_trades(res.trades, res.equity_curve)
    summary_path = out_dir / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "tag","days","end_date_utc","symbols","strategies","starting_equity","ending_equity",
            "trades","net_pnl","profit_factor","winrate","avg_win","avg_loss","max_drawdown"
        ])
        wins_ = [t.pnl for t in res.trades if getattr(t, "pnl", 0.0) > 0]
        losses_ = [t.pnl for t in res.trades if getattr(t, "pnl", 0.0) < 0]
        avg_win = (sum(wins_) / len(wins_)) if wins_ else 0.0
        avg_loss = (sum(losses_) / len(losses_)) if losses_ else 0.0
        pf_val = overall.profit_factor
        pf_str = (f"{pf_val:.3f}" if math.isfinite(pf_val) else "inf")

        w.writerow([
            tag,
            int((end_ms - start_ms) / 86400000),
            dt.datetime.utcfromtimestamp(end_ms / 1000.0).strftime("%Y-%m-%d"),
            ";".join(syms),
            ";".join(strategies),
            f"{params.starting_equity:.2f}",
            f"{res.equity_curve[-1]:.2f}",
            overall.trades,
            f"{overall.net_pnl:.2f}",
            pf_str,
            f"{overall.winrate:.3f}",
            f"{avg_win:.4f}",
            f"{avg_loss:.4f}",
            f"{overall.max_drawdown:.4f}",
        ])

    return str(trades_path), str(summary_path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", required=True, help="Comma-separated base symbols.")
    ap.add_argument("--strategies", required=True, help="Comma-separated strategies.")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD UTC (inclusive).")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD UTC (exclusive).")
    ap.add_argument("--trade_days", type=int, default=30, help="Trade window size (days).")
    ap.add_argument("--lookback_days", type=int, default=30, help="Lookback window for scoring.")
    ap.add_argument("--exclude_worst", type=int, default=8, help="Exclude N worst symbols each step.")
    ap.add_argument("--min_trades", type=int, default=8, help="Min trades per symbol to be considered.")
    ap.add_argument("--starting_equity", type=float, default=100.0)
    ap.add_argument("--risk_pct", type=float, default=0.01)
    ap.add_argument("--leverage", type=float, default=3.0)
    ap.add_argument("--max_positions", type=int, default=3)
    ap.add_argument("--cap_notional", type=float, default=0.0)
    ap.add_argument("--fee_bps", type=float, default=6.0)
    ap.add_argument("--slippage_bps", type=float, default=2.0)
    ap.add_argument("--polite_sleep_sec", type=float, default=1.2)
    ap.add_argument("--bybit_base", type=str, default=DEFAULT_BYBIT_BASE)
    ap.add_argument("--tag", type=str, default="walkforward")
    ap.add_argument("--out_dir", type=str, default="", help="Output dir (default: backtest_runs/walkforward_<tag>).")
    args = ap.parse_args()

    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    base_symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]

    start_dt = _parse_date(args.start)
    end_dt = _parse_date(args.end)
    if start_dt >= end_dt:
        raise SystemExit("start must be < end")

    out_dir = args.out_dir or os.path.join(repo_dir, "backtest_runs", f"walkforward_{args.tag}")
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    windows = []
    current_start = start_dt
    current_symbols = list(base_symbols)
    step = 0

    # Load full candles once to avoid repeated API calls per window.
    full_start_ms = int(start_dt.timestamp() * 1000)
    full_end_ms = int(end_dt.timestamp() * 1000)
    candles_by_sym = _load_full_candles(
        base_symbols,
        start_ms=full_start_ms,
        end_ms=full_end_ms,
        bybit_base=args.bybit_base,
        polite_sleep_sec=args.polite_sleep_sec,
    )

    params = BacktestParams(
        starting_equity=args.starting_equity,
        risk_pct=args.risk_pct,
        cap_notional_usd=args.cap_notional,
        leverage=args.leverage,
        max_positions=args.max_positions,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )

    while current_start < end_dt:
        current_end = min(end_dt, current_start + dt.timedelta(days=int(args.trade_days)))
        step += 1
        tag = f"{args.tag}_step{step}_{_fmt_date(current_end)}"

        window_dir = Path(out_dir) / f"step{step}_{_fmt_date(current_end)}"
        trades_csv, summary_csv = _run_portfolio_local(
            symbols=current_symbols,
            strategies=strategies,
            candles_by_sym=candles_by_sym,
            start_ms=int(current_start.timestamp() * 1000),
            end_ms=int(current_end.timestamp() * 1000),
            params=params,
            out_dir=window_dir,
            tag=tag,
        )

        scored = _score_symbols(
            trades_csv,
            lookback_days=args.lookback_days,
            min_trades=args.min_trades,
            end_ts_utc=current_end.timestamp(),
        )
        worst = _pick_worst(scored, args.exclude_worst)
        next_symbols = [s for s in base_symbols if s not in set(worst)]

        windows.append({
            "step": step,
            "start": _fmt_date(current_start),
            "end": _fmt_date(current_end),
            "run_dir": str(window_dir),
            "symbols_in": ",".join(current_symbols),
            "excluded": ",".join(worst),
            "symbols_next": ",".join(next_symbols),
            "summary_csv": summary_csv,
            "trades_csv": trades_csv,
        })

        current_symbols = next_symbols
        current_start = current_end

    # Write report CSV
    report_csv = os.path.join(out_dir, "walkforward_windows.csv")
    with open(report_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(windows[0].keys()))
        w.writeheader()
        for row in windows:
            w.writerow(row)

    # Aggregate monthly PnL across all windows
    monthly = defaultdict(float)
    for w in windows:
        with open(w["trades_csv"], newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                ts_ms = float(row["exit_ts"])
                pnl = float(row["pnl"])
                d = dt.datetime.utcfromtimestamp(ts_ms / 1000.0)
                key = f"{d.year}-{d.month:02d}"
                monthly[key] += pnl

    report_md = os.path.join(out_dir, "walkforward_report.md")
    with open(report_md, "w", encoding="utf-8") as f:
        f.write("# Walk-forward Report\n\n")
        f.write(f"- tag: `{args.tag}`\n")
        f.write(f"- strategies: `{','.join(strategies)}`\n")
        f.write(f"- base symbols: `{','.join(base_symbols)}`\n")
        f.write(f"- trade_days: {args.trade_days}\n")
        f.write(f"- lookback_days: {args.lookback_days}\n")
        f.write(f"- exclude_worst: {args.exclude_worst}\n")
        f.write(f"- min_trades: {args.min_trades}\n\n")

        f.write("## Windows\n")
        for w in windows:
            f.write(f"- step {w['step']}: {w['start']} → {w['end']} | run `{w['run_dir']}`\n")
            f.write(f"  excluded: {w['excluded']}\n")

        f.write("\n## Monthly PnL (USD)\n")
        for m in sorted(monthly.keys()):
            f.write(f"- {m}: {monthly[m]:.2f}\n")

    print(f"Wrote: {report_csv}")
    print(f"Wrote: {report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
