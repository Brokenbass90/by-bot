#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Run a combined portfolio backtest (multi-strategy, multi-symbol).

Use this after you have at least a couple strategies that look OK in
isolation. It runs all selected strategies together on the same symbol universe
and period, sharing capital and `max_positions`.

Example:

  INPLAY_EXIT_MODE=runner \
  python3 backtest/run_portfolio.py \
    --symbols BTCUSDT,ETHUSDT \
    --strategies bounce,range,inplay \
    --days 60 --end 2026-02-01 \
    --starting_equity 100 \
    --risk_pct 0.01 --max_positions 5 \
    --cap_notional 30 --leverage 1 \
    --tag portfolio_try1
"""

from __future__ import annotations


import os
import sys

_THIS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.abspath(os.path.join(_THIS_DIR, '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import argparse
import csv
import json
import os
import time
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


from backtest.bybit_data import fetch_klines_public
from backtest.engine import BacktestParams, KlineStore, Candle
from backtest.metrics import summarize_trades
from backtest.portfolio_engine import run_portfolio_backtest
from strategies.bounce_bt import BounceBTStrategy
from strategies.bounce_bt_v2 import BounceBTV2Strategy
from strategies.range_wrapper import RangeWrapper
from strategies.inplay_wrapper import InPlayWrapper
from strategies.retest_backtest import RetestBacktestStrategy
from strategies.inplay_breakout import InPlayBreakoutWrapper
from strategies.inplay_pullback import InPlayPullbackWrapper
from strategies.pump_fade import PumpFadeStrategy
from strategies.momentum_continuation import MomentumContinuationStrategy
from strategies.trend_pullback import TrendPullbackStrategy
from strategies.trend_regime_breakout import TrendRegimeBreakoutStrategy
from strategies.vol_breakout import VolatilityBreakoutStrategy
from strategies.adaptive_range_short import AdaptiveRangeShortStrategy
from strategies.smart_grid import SmartGridStrategy
from strategies.range_bounce import RangeBounceStrategy
from strategies.donchian_breakout import DonchianBreakoutStrategy
from strategies.btc_eth_midterm_pullback import BTCETHMidtermPullbackStrategy
from strategies.btc_eth_vol_expansion import BTCETHVolExpansionStrategy
from strategies.btc_eth_trend_rsi_reentry import BTCETHTrendRSIReentryStrategy


def _parse_end(s: Optional[str]) -> int:
    if not s:
        return int(time.time())
    # Accept YYYY-MM-DD
    dt = datetime.strptime(s.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _load_symbol_5m(symbol: str, start_ts: int, end_ts: int, *, bybit_base: str, cache_dir: Path) -> List[Candle]:
    """Load 5m candles for [start_ts, end_ts) in *seconds*.

    NOTE: fetch_klines_public() works in milliseconds and returns a list[Kline].
    Portfolio backtest engine expects a list[Candle].

    We keep a simple JSON cache under --cache (default: .cache/klines) to avoid
    repeatedly hitting Bybit REST when iterating.
    """

    cache_dir.mkdir(parents=True, exist_ok=True)
    start_ms = int(start_ts) * 1000
    end_ms = int(end_ts) * 1000
    fname = cache_dir / f"{symbol}_5_{start_ms}_{end_ms}.json"

    rows: List[List[float]]
    if fname.exists():
        rows = json.loads(fname.read_text(encoding="utf-8"))
    else:
        kl = fetch_klines_public(symbol, interval="5", start_ms=start_ms, end_ms=end_ms, base=bybit_base, cache=True)
        # backtest.bybit_data.Kline uses `ts` (ms). Older/alternate Kline objects may use
        # `start_ms` / `startTime` / `start_time`. Be defensive.
        def _k_ts_ms(k):
            for attr in ("ts", "start_ms", "startTime", "start_time"):
                v = getattr(k, attr, None)
                if v is not None:
                    return int(v)
            raise AttributeError("Kline has no timestamp attribute (ts/start_ms/startTime/start_time)")

        rows = [[_k_ts_ms(k), k.o, k.h, k.l, k.c, k.v] for k in kl]
        fname.write_text(json.dumps(rows), encoding="utf-8")

    out: List[Candle] = []
    for r in rows:
        if not isinstance(r, (list, tuple)) or len(r) < 5:
            continue
        ts = int(float(r[0]))
        o = float(r[1]); h = float(r[2]); l = float(r[3]); c = float(r[4])
        v = float(r[5]) if len(r) > 5 else 0.0
        out.append(Candle(ts=ts, o=o, h=h, l=l, c=c, v=v))
    return out






def _session_name(ts_ms: int) -> str:
    ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
    hour = (ts_sec // 3600) % 24
    # UTC windows
    if 0 <= hour < 9:
        return "asia"
    if 8 <= hour < 17:
        return "europe"
    if 13 <= hour < 22:
        return "us"
    return "off"


def _csv_lower_set(name: str) -> set[str]:
    raw = os.getenv(name, "") or ""
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _session_allowed(strategy: str, ts_ms: int) -> bool:
    if str(os.getenv("SESSION_FILTER_ENABLE", "0")).strip().lower() not in {"1", "true", "yes", "on"}:
        return True
    sess = _session_name(ts_ms)
    if sess == "off":
        return False

    key = f"SESSION_ALLOWED_{str(strategy).upper()}"
    allow = _csv_lower_set(key)
    if not allow:
        allow = _csv_lower_set("SESSION_FILTER_ALLOWED")
    if not allow:
        return True
    return sess in allow


def _write_pump_fade_diagnostics(out_dir: Path, pump_fade: Dict[str, PumpFadeStrategy]) -> Optional[Path]:
    if not pump_fade:
        return None

    rows: List[List[object]] = []
    totals: Dict[str, int] = {}
    total_signals = 0
    for sym, strat in pump_fade.items():
        try:
            total_signals += int(strat.signals_emitted())
            stats = strat.skip_reason_stats()
        except Exception:
            continue
        for reason, cnt in stats.items():
            c = int(cnt or 0)
            if c <= 0:
                continue
            rows.append([sym, reason, c])
            totals[reason] = int(totals.get(reason, 0)) + c

    if not rows:
        return None

    rows.sort(key=lambda x: (x[0], -int(x[2]), str(x[1])))
    total_items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)

    out_path = out_dir / "pump_fade_skip_reasons.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "reason", "count"])
        for r in rows:
            w.writerow(r)
        w.writerow([])
        w.writerow(["TOTAL", "SIGNALS_EMITTED", total_signals])
        w.writerow(["TOTAL", "SKIPS", int(sum(totals.values()))])
        for reason, cnt in total_items:
            w.writerow(["TOTAL", reason, cnt])
    return out_path

def _select_auto_symbols(*, base: str, min_volume_usd: float, top_n: int, exclude: List[str]) -> List[str]:
    """Pick a universe from Bybit 24h tickers (linear USDT).

    We sort by 24h turnover and keep the top_n symbols above min_volume_usd.
    """
    try:
        import requests  # lazy import to avoid dependency unless auto-universe is used
    except Exception as e:
        raise RuntimeError("Auto symbol selection requires the 'requests' package") from e
    url = f"{base.rstrip('/')}/v5/market/tickers"
    params = {"category": "linear"}
    js = requests.get(url, params=params, timeout=20).json()
    if js.get("retCode") != 0:
        raise RuntimeError(f"Bybit tickers error {js.get('retCode')}: {js.get('retMsg')}")
    lst = (((js.get("result") or {}).get("list")) or [])

    ex = set(x.strip().upper() for x in exclude if x.strip())
    rows = []
    for it in lst:
        sym = str(it.get("symbol") or "").upper()
        if not sym or not sym.endswith("USDT"):
            continue
        if sym in ex:
            continue
        try:
            turn = float(it.get("turnover24h") or 0.0)
        except Exception:
            turn = 0.0
        if turn < float(min_volume_usd):
            continue
        rows.append((turn, sym))

    rows.sort(reverse=True)
    return [sym for _, sym in rows[: max(1, int(top_n))]]
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="", help="Comma-separated symbols")
    ap.add_argument("--auto_symbols", action="store_true",
                    help="If set (or if --symbols is empty), select a universe automatically from Bybit 24h tickers.")
    ap.add_argument("--min_volume_usd", type=float, default=20_000_000.0,
                    help="Universe filter: minimum 24h turnover (USD).")
    ap.add_argument("--top_n", type=int, default=15,
                    help="Universe: max number of symbols to include after filtering.")
    ap.add_argument("--exclude_symbols", type=str, default="",
                    help="Comma-separated symbols to exclude from the auto universe.")
    ap.add_argument(
        "--strategies",
        default="bounce,bounce_v2,range,inplay,inplay_breakout,pump_fade,retest_levels,momentum,trend_pullback,trend_breakout,vol_breakout,adaptive_range_short,smart_grid,range_bounce,donchian_breakout,btc_eth_midterm_pullback,btc_eth_vol_expansion,btc_eth_trend_rsi_reentry",
        help="Comma-separated strategies (priority order): bounce,bounce_v2,range,inplay,inplay_pullback,inplay_breakout,pump_fade,retest_levels,momentum,trend_pullback,trend_breakout,vol_breakout,adaptive_range_short,smart_grid,range_bounce,donchian_breakout,btc_eth_midterm_pullback,btc_eth_vol_expansion,btc_eth_trend_rsi_reentry",
    )
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--end", default="", help="YYYY-MM-DD (UTC)")
    ap.add_argument("--starting_equity", type=float, default=100.0)
    ap.add_argument("--risk_pct", type=float, default=0.01)
    ap.add_argument("--cap_notional", type=float, default=30.0)
    ap.add_argument("--leverage", type=float, default=1.0)
    ap.add_argument("--max_positions", type=int, default=5)
    ap.add_argument("--fee_bps", type=float, default=6.0)
    ap.add_argument("--slippage_bps", type=float, default=2.0)
    ap.add_argument("--bybit_base", default=os.getenv("BYBIT_BASE", "https://api.bybit.com"))
    ap.add_argument("--cache", default=".cache/klines")
    ap.add_argument("--tag", default="portfolio")
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    exclude = [s.strip() for s in (args.exclude_symbols or "").split(",") if s.strip()]
    if args.auto_symbols or not symbols:
        symbols = _select_auto_symbols(base=args.bybit_base, min_volume_usd=args.min_volume_usd, top_n=args.top_n, exclude=exclude)
    if not symbols:
        raise SystemExit("No symbols selected. Provide --symbols or relax --min_volume_usd/--top_n.")

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    allowed = {"bounce", "bounce_v2", "range", "inplay", "inplay_pullback", "inplay_breakout", "pump_fade", "retest_levels", "momentum", "trend_pullback", "trend_breakout", "vol_breakout", "adaptive_range_short", "smart_grid", "range_bounce", "donchian_breakout", "btc_eth_midterm_pullback", "btc_eth_vol_expansion", "btc_eth_trend_rsi_reentry"}
    for s in strategies:
        if s not in allowed:
            raise SystemExit(f"Unsupported strategy '{s}'. Allowed: {sorted(allowed)}")

    end_ts = _parse_end(args.end)
    start_ts = end_ts - int(args.days) * 86400

    cache_dir = Path(args.cache)
    stores: Dict[str, KlineStore] = {}
    for sym in symbols:
        c5 = _load_symbol_5m(sym, start_ts, end_ts, bybit_base=args.bybit_base, cache_dir=cache_dir)
        stores[sym] = KlineStore(sym, c5)

    # Build per-symbol strategy instances (avoid cross-symbol state bleed).
    bounce = {sym: BounceBTStrategy() for sym in symbols} if "bounce" in strategies else {}
    bounce_v2 = {sym: BounceBTV2Strategy() for sym in symbols} if "bounce_v2" in strategies else {}
    range_wrappers = {sym: RangeWrapper(fetch_klines=stores[sym].fetch_klines) for sym in symbols} if "range" in strategies else {}
    inplay = {sym: InPlayWrapper() for sym in symbols} if "inplay" in strategies else {}
    breakout = {sym: InPlayBreakoutWrapper() for sym in symbols} if "inplay_breakout" in strategies else {}
    pullback = {sym: InPlayPullbackWrapper() for sym in symbols} if "inplay_pullback" in strategies else {}
    pump_fade = {sym: PumpFadeStrategy() for sym in symbols} if "pump_fade" in strategies else {}
    retest = {sym: RetestBacktestStrategy(stores[sym]) for sym in symbols} if "retest_levels" in strategies else {}
    momentum = {sym: MomentumContinuationStrategy() for sym in symbols} if "momentum" in strategies else {}
    trend_pullback = {sym: TrendPullbackStrategy() for sym in symbols} if "trend_pullback" in strategies else {}
    trend_breakout = {sym: TrendRegimeBreakoutStrategy() for sym in symbols} if "trend_breakout" in strategies else {}
    vol_breakout = {sym: VolatilityBreakoutStrategy() for sym in symbols} if "vol_breakout" in strategies else {}
    adaptive_range_short = {sym: AdaptiveRangeShortStrategy() for sym in symbols} if "adaptive_range_short" in strategies else {}
    smart_grid = {sym: SmartGridStrategy() for sym in symbols} if "smart_grid" in strategies else {}
    range_bounce = {sym: RangeBounceStrategy() for sym in symbols} if "range_bounce" in strategies else {}
    donchian_breakout = {sym: DonchianBreakoutStrategy() for sym in symbols} if "donchian_breakout" in strategies else {}
    btc_eth_midterm_pullback = {sym: BTCETHMidtermPullbackStrategy() for sym in symbols} if "btc_eth_midterm_pullback" in strategies else {}
    btc_eth_vol_expansion = {sym: BTCETHVolExpansionStrategy() for sym in symbols} if "btc_eth_vol_expansion" in strategies else {}
    btc_eth_trend_rsi_reentry = {sym: BTCETHTrendRSIReentryStrategy() for sym in symbols} if "btc_eth_trend_rsi_reentry" in strategies else {}

    def selector(sym: str, store: KlineStore, ts_ms: int, last_price: float):
        # IMPORTANT: first-match wins (priority = order in --strategies)
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
                # PumpFadeStrategy expects OHLCV
                # PumpFadeStrategy expects OHLCV
                # KlineStore uses `i5` as the current 5m index (set by portfolio_engine).
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = pump_fade[sym].maybe_signal(sym, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "retest_levels":
                sig = retest[sym].signal(store, ts_ms, last_price)
            elif st == "momentum":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = momentum[sym].maybe_signal(sym, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "trend_pullback":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = trend_pullback[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "trend_breakout":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = trend_breakout[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "vol_breakout":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = vol_breakout[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "adaptive_range_short":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = adaptive_range_short[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "smart_grid":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = smart_grid[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "range_bounce":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = range_bounce[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "donchian_breakout":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = donchian_breakout[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_eth_midterm_pullback":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_eth_midterm_pullback[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_eth_vol_expansion":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_eth_vol_expansion[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_eth_trend_rsi_reentry":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_eth_trend_rsi_reentry[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            else:
                sig = None
            if sig is not None:
                st_name = str(getattr(sig, "strategy", st) or st)
                if not _session_allowed(st_name, ts_ms):
                    continue
                return sig
        return None

    cap_notional = float(args.cap_notional)
    if cap_notional <= 0:
        cap_notional = None

    params = BacktestParams(
        starting_equity=args.starting_equity,
        risk_pct=args.risk_pct,
        cap_notional_usd=cap_notional,
        leverage=args.leverage,
        max_positions=args.max_positions,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )

    out_dir = Path("backtest_runs") / f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{args.tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    res = run_portfolio_backtest(stores, selector, params=params, symbols_order=symbols)

    # Save trades
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

    # Save summary
    overall = summarize_trades(res.trades, res.equity_curve)
    summary_path = out_dir / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "tag","days","end_date_utc","symbols","strategies","starting_equity","ending_equity",
            "trades","net_pnl","profit_factor","winrate","avg_win","avg_loss","max_drawdown"
        ])
        # Compute avg win / avg loss in $ terms (not %)
        wins_ = [t.pnl for t in res.trades if getattr(t, "pnl", 0.0) > 0]
        losses_ = [t.pnl for t in res.trades if getattr(t, "pnl", 0.0) < 0]
        avg_win = (sum(wins_) / len(wins_)) if wins_ else 0.0
        avg_loss = (sum(losses_) / len(losses_)) if losses_ else 0.0
        pf_val = overall.profit_factor
        pf_str = (f"{pf_val:.3f}" if math.isfinite(pf_val) else "inf")

        w.writerow([
            args.tag,
            args.days,
            datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            ";".join(symbols),
            ";".join(strategies),
            f"{args.starting_equity:.2f}",
            f"{res.equity_curve[-1]:.2f}",
            overall.trades,
            f"{overall.net_pnl:.2f}",
            pf_str,
            f"{overall.winrate:.3f}",
            f"{avg_win:.4f}",
            f"{avg_loss:.4f}",
            f"{overall.max_drawdown:.4f}",
        ])

    print(f"Saved portfolio run to: {out_dir}")
    print(f"  trades:   {trades_path}")
    print(f"  summary:  {summary_path}")
    if "pump_fade" in strategies and pump_fade:
        pf_diag = _write_pump_fade_diagnostics(out_dir, pump_fade)
        if pf_diag is not None:
            print(f"  pf_diag:  {pf_diag}")


if __name__ == "__main__":
    main()
