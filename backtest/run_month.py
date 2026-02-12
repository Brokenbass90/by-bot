#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Backtest runner: compare strategies over ~1 month.

Example:
  python3 backtest/run_month.py --symbols SOLUSDT,ADAUSDT --days 30 --strategies range,bounce,pump_fade,inplay

Outputs:
  - ./backtest_results/summary.csv
  - ./backtest_results/trades_<strategy>.csv

This script uses public Bybit endpoints (no API keys required).
"""

import os
import sys

# Ensure repo root is on sys.path when executed as a script
_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.abspath(os.path.join(_THIS_DIR, '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import traceback


import argparse
import csv
import json
import re
import os
import time
import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional

import requests

from backtest.bybit_data import DEFAULT_BYBIT_BASE, fetch_klines_public
from backtest.engine import Candle, KlineStore, BacktestParams, run_symbol_backtest
from backtest.metrics import PerformanceSummary, summarize_trades

from strategies.bounce_bt import BounceBTConfig, BounceBTStrategy
from strategies.bounce_bt_v2 import BounceBTV2Config, BounceBTV2Strategy
from strategies.inplay_wrapper import InPlayWrapper, InPlayWrapperConfig
from strategies.retest_backtest import RetestBacktestStrategy, RetestBTConfig
from strategies.inplay_breakout import InPlayBreakoutWrapper, InPlayBreakoutConfig
from strategies.inplay_pullback import InPlayPullbackWrapper, InPlayPullbackConfig
from strategies.pump_fade import PumpFadeConfig, PumpFadeStrategy
from strategies.range_wrapper import RangeWrapper, RangeWrapperConfig


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _write_trades_csv(path: str, trades) -> None:
    fields = [
        "strategy",
        "symbol",
        "side",
        "entry_ts",
        "exit_ts",
        "entry_price",
        "exit_price",
        "qty",
        "pnl",
        "pnl_pct_equity",
        "reason",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in trades:
            w.writerow({
                "strategy": t.strategy,
                "symbol": t.symbol,
                "side": t.side,
                "entry_ts": t.entry_ts,
                "exit_ts": t.exit_ts,
                "entry_price": f"{t.entry_price:.10g}",
                "exit_price": f"{t.exit_price:.10g}",
                "qty": f"{t.qty:.10g}",
                "pnl": f"{t.pnl:.10g}",
                "pnl_pct_equity": f"{t.pnl_pct_equity:.10g}",
                "reason": t.reason,
            })



def _write_equity_curve_csv(path: str, candles_5m: List[Candle], curve: List[float]) -> None:
    # curve is per 5m bar; length typically equals len(candles_5m)
    n = min(len(candles_5m), len(curve))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "iso", "equity"])
        w.writeheader()
        for i in range(n):
            ts = int(candles_5m[i].ts)
            iso = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat()
            w.writerow({"ts": ts, "iso": iso, "equity": f"{float(curve[i]):.10g}"})

def _fmt_summary(s: PerformanceSummary) -> str:
    return (
        f"trades={s.trades}  winrate={s.winrate_pct:.1f}%  "
        f"netPnL={s.net_pnl:.2f}  PF={s.profit_factor:.2f}  "
        f"maxDD={s.max_drawdown_pct:.1f}%"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Comma-separated Bybit linear symbols, e.g. SOLUSDT,ADAUSDT",
    )
    ap.add_argument(
        "--auto_symbols",
        action="store_true",
        help="If set (or if --symbols is empty), select a universe automatically from Bybit 24h tickers.",
    )
    ap.add_argument("--min_volume_usd", type=float, default=20_000_000.0,
                    help="Universe filter: minimum 24h turnover (USD).")
    ap.add_argument("--top_n", type=int, default=15,
                    help="Universe: max number of symbols to include after filtering.")
    ap.add_argument("--exclude_symbols", type=str, default="",
                    help="Comma-separated symbols to exclude from the auto universe.")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument(
        "--end",
        type=str,
        default="",
        help="End time (UTC) in YYYY-MM-DD or YYYY-MM-DDTHH:MM format. Default: now.",
    )
    ap.add_argument(
        "--strategies",
        type=str,
        default="range,bounce,bounce_v2,pump_fade,inplay,inplay_pullback,inplay_breakout,retest_levels",
        help="Comma-separated: range,bounce,bounce_v2,pump_fade,inplay,inplay_pullback,inplay_breakout,retest_levels",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Fail fast on any strategy error (default: continue and report the error)",
    )
    ap.add_argument("--starting_equity", type=float, default=100.0)
    ap.add_argument("--risk_pct", type=float, default=0.01)
    ap.add_argument(
        "--leverage",
        type=float,
        default=3.0,
        help="Leverage used to derive an auto per-trade notional cap when --cap_notional is 0.",
    )
    ap.add_argument(
        "--max_positions",
        type=int,
        default=3,
        help="Used with leverage to derive an auto per-trade notional cap (equity*leverage/max_positions).",
    )
    ap.add_argument(
        "--cap_notional",
        type=float,
        default=0.0,
        help="Per-trade notional cap (USD). Use 0 to auto-derive from equity/leverage/max_positions.",
    )
    ap.add_argument(
        "--fee_model",
        type=str,
        default="bybit",
        choices=["bybit", "binance", "custom"],
        help="Fee preset. If not custom, used as the default if --fee_bps is not provided.",
    )
    ap.add_argument(
        "--fee_bps",
        type=float,
        default=-1.0,
        help="Fees per side in bps. Use -1 to take the default from --fee_model.",
    )
    ap.add_argument("--slippage_bps", type=float, default=2.0)
    ap.add_argument(
        "--no_save",
        action="store_true",
        help="If set, do not write CSV files; print summaries to terminal only.",
    )
    ap.add_argument(
        "--out_dir",
        type=str,
        default="",
        help="Base output directory for this run. Default: ./backtest_runs/<timestamp>[_<tag>]/",
    )
    ap.add_argument(
        "--tag",
        type=str,
        default="",
        help="Optional run tag appended to the output folder name (e.g. exp1, jan27).",
    )
    ap.add_argument(
        "--save_equity_curve",
        action="store_true",
        help="If set, save per-symbol equity curves to CSV under equity_curves/.",
    )
    ap.add_argument("--bybit_base", type=str, default=DEFAULT_BYBIT_BASE)
    ap.add_argument("--cache", action="store_true", default=True)
    args = ap.parse_args()

    # Many strategy components were originally written as async (they fetch klines via REST).
    # The backtest engine is synchronous, so we resolve awaitables using a single, dedicated
    # event loop to avoid per-bar asyncio.run() overhead.
    bt_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(bt_loop)

    def _resolve(res):
        if inspect.isawaitable(res):
            return bt_loop.run_until_complete(res)
        return res

    def _select_symbols_auto(
        base: str,
        min_volume_usd: float,
        top_n: int,
        exclude_csv: str,
    ) -> List[str]:
        exclude = {x.strip().upper() for x in (exclude_csv or "").split(",") if x.strip()}
        url = f"{base.rstrip('/')}/v5/market/tickers"
        r = requests.get(url, params={"category": "linear"}, timeout=20)
        r.raise_for_status()
        data = r.json() or {}
        items = ((data.get("result") or {}).get("list") or [])

        rows: List[Tuple[str, float]] = []
        for it in items:
            sym = str(it.get("symbol", "")).upper()
            if not sym or not sym.endswith("USDT"):
                continue
            if sym in exclude:
                continue
            # Bybit returns strings
            turn = it.get("turnover24h") or it.get("turnover24H") or it.get("turnover") or "0"
            try:
                turn_f = float(turn)
            except Exception:
                continue
            if turn_f < float(min_volume_usd):
                continue
            rows.append((sym, turn_f))

        rows.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in rows[: max(1, int(top_n))]]

    symbols = [s.strip().upper() for s in (args.symbols or "").split(",") if s.strip()]
    if args.auto_symbols or not symbols:
        symbols = _select_symbols_auto(
            args.bybit_base,
            args.min_volume_usd,
            args.top_n,
            args.exclude_symbols,
        )
        if not symbols:
            raise SystemExit(
                "AUTO universe is empty (check --min_volume_usd / --exclude_symbols or Bybit availability)."
            )

    strategies = [s.strip().lower() for s in args.strategies.split(",") if s.strip()]

    end_dt = _utc_now()
    if args.end:
        txt = args.end.strip()
        try:
            if "T" in txt:
                end_dt = datetime.fromisoformat(txt).replace(tzinfo=timezone.utc)
            else:
                end_dt = datetime.strptime(txt, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            raise SystemExit("Bad --end format. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM")

    start_dt = end_dt - timedelta(days=max(1, int(args.days)))

    start_ms = _ms(start_dt)
    end_ms = _ms(end_dt)

    print(f"Backtest window (UTC): {start_dt.isoformat()}  ->  {end_dt.isoformat()}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Strategies: {', '.join(strategies)}")

    # Output directory is created later (after run folder resolution)

    # Preload 5m klines per symbol
    candles_5m: Dict[str, List[Candle]] = {}
    for sym in symbols:
        kl = fetch_klines_public(
            sym,
            interval="5",
            start_ms=start_ms,
            end_ms=end_ms,
            base=args.bybit_base,
            cache=args.cache,
        )
        candles_5m[sym] = [Candle(ts=k.ts, o=k.o, h=k.h, l=k.l, c=k.c, v=k.v) for k in kl]
        print(f"  {sym}: {len(candles_5m[sym])} x 5m candles")

    results_rows: List[Tuple[str, PerformanceSummary]] = []

    # Strategy factories
    def make_range():
        return RangeWrapper(RangeWrapperConfig())

    def make_bounce():
        return BounceBTStrategy(BounceBTConfig())

    def make_bounce_v2():
        return BounceBTV2Strategy(BounceBTV2Config())

    def make_pump_fade():
        return PumpFadeStrategy(PumpFadeConfig())

    def make_inplay():
        return InPlayWrapper(InPlayWrapperConfig())

    def make_inplay_pullback():
        return InPlayPullbackWrapper(InPlayPullbackConfig())

    def make_inplay_breakout():
        return InPlayBreakoutWrapper(InPlayBreakoutConfig())

    def make_retest_levels():
        return RetestBacktestStrategy(None, RetestBTConfig())

    factories = {
        "range": make_range,
        "bounce": make_bounce,
        "bounce_v2": make_bounce_v2,
        "pump_fade": make_pump_fade,
        "inplay": make_inplay,
        "inplay_pullback": make_inplay_pullback,
        "inplay_breakout": make_inplay_breakout,
        "retest_levels": make_retest_levels,
    }


    def _safe_tag(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        # keep it filesystem-friendly
        s = re.sub(r"[^A-Za-z0-9_\-]+", "-", s)
        return s.strip("-")

    # Output directory (per-run). Default: ./backtest_runs/<timestamp>[_<tag>]/
    run_ts = _utc_now().strftime("%Y%m%d_%H%M%S")
    tag = _safe_tag(getattr(args, "tag", ""))
    base_out = (getattr(args, "out_dir", "") or "").strip()
    if base_out:
        out_dir = os.path.join(base_out, run_ts + (f"_{tag}" if tag else ""))
    else:
        out_dir = os.path.join("backtest_runs", run_ts + (f"_{tag}" if tag else ""))

    summary_csv = os.path.join(out_dir, "summary.csv")

    sf = None
    wsum = None
    if not args.no_save:
        os.makedirs(out_dir, exist_ok=True)

        # Persist run metadata/parameters for reproducibility
        try:
            meta = {
                "generated_at_utc": _utc_now().isoformat(),
                "start_utc": start_dt.isoformat(),
                "end_utc": end_dt.isoformat(),
                "symbols": symbols,
                "strategies": strategies,
                "args": vars(args),
                "env": {k: v for k, v in os.environ.items()
                        if k.startswith(("INPLAY_", "PULLBACK_", "RANGE_", "BOUNCE_",
                                         "MIN_NOTIONAL_", "FEE_", "SLIPPAGE_"))},
            }
            with open(os.path.join(out_dir, "params.json"), "w", encoding="utf-8") as pf:
                json.dump(meta, pf, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"WARNING: failed to write params.json: {e}")

        sf = open(summary_csv, "w", newline="", encoding="utf-8")
        wsum = csv.DictWriter(
            sf,
            fieldnames=[
                "strategy",
                "symbol",
                "trades",
                "winrate_pct",
                "net_pnl",
                "avg_pnl",
                "profit_factor",
                "max_drawdown_pct",
            ],
        )
        wsum.writeheader()

    try:
        for strat_name in strategies:
            if strat_name not in factories:
                print(f"Skip unknown strategy: {strat_name}")
                continue

            all_trades = []
            per_symbol_summaries: List[PerformanceSummary] = []

            for sym in symbols:
                c5 = candles_5m.get(sym) or []
                if len(c5) < 300:
                    continue

                store = KlineStore(sym, c5)
                try:
                    if strat_name == "range":
                        strat = RangeWrapper(store.fetch_klines, RangeWrapperConfig())
                    elif strat_name == "retest_levels":
                        strat = RetestBacktestStrategy(store, RetestBTConfig())
                    else:
                        strat = factories[strat_name]()
                except Exception as e:
                    print(f"ERROR: failed to construct strategy '{strat_name}' for {sym}: {e}")
                    if args.strict:
                        raise
                    continue

                # signal function per strategy type
                def signal_fn(ts_ms: int, last_price: float) -> "TradeSignal|None":
                    if strat_name == "range":
                        return _resolve(strat.maybe_signal(store, ts_ms, last_price))
                    if strat_name == "inplay":
                        return _resolve(strat.maybe_signal(store, ts_ms, last_price))
                    if strat_name == "inplay_pullback":
                        return _resolve(strat.maybe_signal(store, ts_ms, last_price))
                    if strat_name == "inplay_breakout":
                        return _resolve(strat.maybe_signal(store, ts_ms, last_price))
                    if strat_name == "retest_levels":
                        return _resolve(strat.signal(store, ts_ms, last_price))
                    if strat_name == "bounce":
                        return _resolve(strat.maybe_signal(store, ts_ms, last_price))
                    if strat_name == "bounce_v2":
                        return _resolve(strat.maybe_signal(store, ts_ms, last_price))
                    if strat_name == "pump_fade":
                        # pump_fade uses 5m bar features
                        # pass latest 5m candle
                        idx = store.i5
                        cur = store.c5[idx]
                        return strat.maybe_signal(sym, ts_ms, cur.o, cur.h, cur.l, cur.c, cur.v)
                    return None

                # fees: if not explicitly provided, select a reasonable default per venue
                if float(args.fee_bps) < 0:
                    fee_bps = 6.0 if str(args.fee_model).lower() == "bybit" else 4.0
                else:
                    fee_bps = float(args.fee_bps)

                cap_notional: Optional[float] = float(args.cap_notional)
                if cap_notional <= 0:
                    cap_notional = None

                params = BacktestParams(
                    starting_equity=float(args.starting_equity),
                    risk_pct=float(args.risk_pct),
                    cap_notional_usd=cap_notional,
                    leverage=float(args.leverage),
                    max_positions=int(args.max_positions),
                    fee_bps=float(fee_bps),
                    slippage_bps=float(args.slippage_bps),
                )

                try:
                    trades, equity_curve = run_symbol_backtest(
                        store,
                        strategy_name=strat_name,
                        signal_fn=signal_fn,
                        params=params,
                    )
                except Exception as e:
                    print(f"ERROR: backtest failed for strategy '{strat_name}' on {sym}: {e}")
                    if os.environ.get('BT_TRACE','0').lower() in ('1','true','yes'):
                        traceback.print_exc()
                    if args.strict:
                        raise
                    continue

                all_trades.extend(trades)
                summ = summarize_trades(trades, equity_curve, strategy=strat_name)
                if (not args.no_save) and getattr(args, "save_equity_curve", False):
                    eq_dir = os.path.join(out_dir, "equity_curves")
                    os.makedirs(eq_dir, exist_ok=True)
                    eq_path = os.path.join(eq_dir, f"equity_{strat_name}_{sym}.csv")
                    try:
                        _write_equity_curve_csv(eq_path, c5, equity_curve)
                    except Exception as e:
                        print(f"WARNING: failed to write equity curve for {strat_name}/{sym}: {e}")

                per_symbol_summaries.append(summ)

                if wsum is not None:
                    wsum.writerow(
                        {
                            "strategy": strat_name,
                            "symbol": sym,
                            "trades": summ.trades,
                            "winrate_pct": f"{summ.winrate_pct:.2f}",
                            "net_pnl": f"{summ.net_pnl:.4f}",
                            "avg_pnl": f"{summ.avg_pnl:.6f}",
                            "profit_factor": f"{summ.profit_factor:.4f}",
                            "max_drawdown_pct": f"{summ.max_drawdown_pct:.4f}",
                        }
                    )

                print(f"{strat_name:10s} {sym:10s}  {_fmt_summary(summ)}")

            # Strategy aggregate (simple sum of pnl across independent symbol runs)
            agg = summarize_trades(all_trades)
            if wsum is not None:
                wsum.writerow(
                    {
                        "strategy": strat_name,
                        "symbol": "ALL",
                        "trades": agg.trades,
                        "winrate_pct": f"{agg.winrate_pct:.2f}",
                        "net_pnl": f"{agg.net_pnl:.4f}",
                        "avg_pnl": f"{agg.avg_pnl:.6f}",
                        "profit_factor": f"{agg.profit_factor:.4f}",
                        "max_drawdown_pct": f"{agg.max_drawdown_pct:.4f}",
                    }
                )

            results_rows.append((strat_name, agg))

            trades_path = os.path.join(out_dir, f"trades_{strat_name}.csv")
            if not args.no_save:
                _write_trades_csv(trades_path, all_trades)
            print(f"{strat_name:10s} ALL         {_fmt_summary(agg)}")
            # Approximate "portfolio on $100" normalization:
            # In this runner each symbol is simulated independently with starting_equity.
            # If you want a single $100 split equally across N symbols, divide total net_pnl by N.
            try:
                n_syms = max(1, len(symbols))
                start_eq = float(getattr(args, "starting_equity", 0.0) or 0.0)
                if start_eq > 0:
                    port_pnl = agg.net_pnl / n_syms
                    port_roi = (port_pnl / start_eq) * 100.0
                    print(f"{strat_name:10s} PORTFOLIO(100)  pnl={port_pnl:.2f}  roi={port_roi:.2f}%  (n_symbols={n_syms}, period={start_dt.date()}..{end_dt.date()} UTC)")
            except Exception:
                pass

            if not args.no_save:
                print(f"  trades saved: {trades_path}")

    finally:
        if sf is not None:
            sf.close()

    # Print a compact leaderboard
    print("\n=== Strategy Leaderboard (aggregate across symbols) ===")
    results_rows.sort(key=lambda x: x[1].net_pnl, reverse=True)
    for name, summ in results_rows:
        print(f"{name:10s}  {_fmt_summary(summ)}")

    if not args.no_save:
        print(f"\nSummary saved: {summary_csv}")
    else:
        print("\n--no_save enabled: CSV output disabled")

    # Cleanly close the loop used for resolving async strategy calls.
    bt_loop.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
