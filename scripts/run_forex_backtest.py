#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Optional

# Ensure project root is importable when script is launched as "python scripts/..."
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv
from forex.engine import EngineConfig, run_backtest
from forex.types import Signal
from forex.strategies.breakout_continuation_session_v1 import BreakoutContinuationSessionV1
from forex.strategies.asia_range_reversion_session_v1 import AsiaRangeReversionSessionV1
from forex.strategies.failure_reclaim_session_v1 import FailureReclaimSessionV1
from forex.strategies.grid_reversion_session_v1 import GridReversionSessionV1
from forex.strategies.liquidity_sweep_bounce_session_v1 import LiquiditySweepBounceSessionV1
from forex.strategies.range_bounce_session_v1 import RangeBounceSessionV1
from forex.strategies.trend_pullback_rebound_v1 import TrendPullbackReboundV1
from forex.strategies.trend_retest_session_v2 import TrendRetestSessionV2
from forex.strategies.trend_retest_session_v1 import Config as TrendRetestConfig
from forex.strategies.trend_retest_session_v1 import TrendRetestSessionV1
from forex.strategies.london_open_breakout_v1 import Config as LobV1Config
from forex.strategies.london_open_breakout_v1 import LondonOpenBreakoutV1
from forex.strategies.london_open_breakout_v2 import Config as LobV2Config
from forex.strategies.london_open_breakout_v2 import LondonOpenBreakoutV2
from forex.strategies.bb_mean_reversion_v1 import Config as BbRevV1Config
from forex.strategies.bb_mean_reversion_v1 import BBMeanReversionV1
from forex.strategies.bb_mean_reversion_v2 import Config as BbRevV2Config
from forex.strategies.bb_mean_reversion_v2 import BBMeanReversionV2
from forex.strategies.adaptive_grid_range_v1 import Config as GridV1Config
from forex.strategies.adaptive_grid_range_v1 import AdaptiveGridRangeV1
from forex.strategies.bb_mean_reversion_v3 import Config as BbRevV3Config
from forex.strategies.bb_mean_reversion_v3 import BBMeanReversionV3
from forex.strategies.bb_mean_reversion_v2p import Config as BbRevV2PConfig
from forex.strategies.bb_mean_reversion_v2p import BBMeanReversionV2P
from forex.strategies.trendline_break_bounce_v1 import Config as TlbbV1Config
from forex.strategies.trendline_break_bounce_v1 import TrendlineBreakBounceV1
from news_filter import is_news_blocked, load_news_events, load_news_policy
from run_forex_multi_strategy_gate import _build_strategy as _build_preset_strategy


def _default_pip_size(symbol: str) -> float:
    s = symbol.upper()
    if s.endswith("JPY"):
        return 0.01
    return 0.0001


def _build_strategy(args):
    s = args.strategy
    if ":" in s:
        return _build_preset_strategy(
            s,
            session_start=int(args.session_start_utc),
            session_end=int(args.session_end_utc),
        )
    if s == "trend_retest_session_v1":
        return TrendRetestSessionV1(
            TrendRetestConfig(
                ema_fast=int(args.ema_fast),
                ema_slow=int(args.ema_slow),
                breakout_lookback=int(args.breakout_lookback),
                retest_window_bars=int(args.retest_window_bars),
                sl_atr_mult=float(args.sl_atr_mult),
                rr=float(args.rr),
                cooldown_bars=int(args.cooldown_bars),
                session_utc_start=int(args.session_start_utc),
                session_utc_end=int(args.session_end_utc),
            )
        )
    if s == "trend_retest_session_v2":
        return TrendRetestSessionV2()
    if s == "range_bounce_session_v1":
        return RangeBounceSessionV1()
    if s == "breakout_continuation_session_v1":
        return BreakoutContinuationSessionV1()
    if s == "asia_range_reversion_session_v1":
        return AsiaRangeReversionSessionV1()
    if s == "failure_reclaim_session_v1":
        return FailureReclaimSessionV1()
    if s == "grid_reversion_session_v1":
        return GridReversionSessionV1()
    if s == "liquidity_sweep_bounce_session_v1":
        return LiquiditySweepBounceSessionV1()
    if s == "trend_pullback_rebound_v1":
        return TrendPullbackReboundV1()
    if s == "london_open_breakout_v1":
        is_jpy = args.symbol.upper().endswith("JPY")
        return LondonOpenBreakoutV1(LobV1Config(
            pip_size=float(args.pip_size) if float(args.pip_size) > 0 else (0.01 if is_jpy else 0.0001),
            min_range_pips=float(getattr(args, "min_range_pips", 40 if is_jpy else 6)),
            max_range_pips=float(getattr(args, "max_range_pips", 100 if is_jpy else 50)),
            breakout_buffer_pips=float(getattr(args, "breakout_buffer_pips", 5 if is_jpy else 1.5)),
            sl_buffer_pips=float(getattr(args, "sl_buffer_pips", 10 if is_jpy else 3)),
            rr=float(args.rr),
            london_start_utc=int(args.session_start_utc),
            london_end_utc=int(args.session_end_utc),
            min_atr_pips=float(getattr(args, "min_atr_pips", 10 if is_jpy else 2.5)),
        ))
    if s == "london_open_breakout_v2":
        is_jpy = args.symbol.upper().endswith("JPY")
        return LondonOpenBreakoutV2(LobV2Config(
            pip_size=float(args.pip_size) if float(args.pip_size) > 0 else (0.01 if is_jpy else 0.0001),
            rr=float(args.rr),
            london_start_utc=int(args.session_start_utc),
            london_end_utc=int(args.session_end_utc),
        ))
    if s == "bb_mean_reversion_v1":
        is_jpy = args.symbol.upper().endswith("JPY")
        ps = float(args.pip_size) if float(args.pip_size) > 0 else (0.01 if is_jpy else 0.0001)
        return BBMeanReversionV1(BbRevV1Config(
            pip_size=ps,
            min_band_width_pips=30.0 if is_jpy else 8.0,
        ))
    if s in ("bb_mean_reversion_v2", "bb_mean_reversion_v2p"):
        is_jpy = args.symbol.upper().endswith("JPY")
        is_crypto = args.symbol.upper().endswith("USDT") or args.symbol.upper() in ("BTCUSDT", "ETHUSDT")
        ps = float(args.pip_size) if float(args.pip_size) > 0 else (0.01 if is_jpy else 0.0001)
        use_v2p = (s == "bb_mean_reversion_v2p")
        Cls = BBMeanReversionV2P if use_v2p else BBMeanReversionV2
        Cfg = BbRevV2PConfig    if use_v2p else BbRevV2Config
        if is_crypto:
            return Cls(Cfg(
                pip_size=ps,
                min_band_width_pips=600.0,
                max_atr_pips=2500.0,
                rsi_long_max=28.0,
                rsi_short_min=72.0,
                atr_regime_mult=0.82,
                sl_atr_mult=1.0,
                rr_min=1.3,
                cooldown_bars=24,
            ))
        return Cls(Cfg(
            pip_size=ps,
            min_band_width_pips=60.0 if is_jpy else 20.0,
            max_atr_pips=250.0 if is_jpy else 25.0,
        ))
    if s == "adaptive_grid_range_v1":
        is_jpy = args.symbol.upper().endswith("JPY")
        is_crypto = args.symbol.upper().endswith("USDT") or args.symbol.upper().endswith("BTC")
        ps = float(args.pip_size) if float(args.pip_size) > 0 else (0.01 if is_jpy else 0.0001)
        return AdaptiveGridRangeV1(GridV1Config(
            pip_size=ps,
            min_range_pips=300.0 if is_crypto else (150.0 if is_jpy else 15.0),
            max_range_pips=5000.0 if is_crypto else (1000.0 if is_jpy else 200.0),
            max_atr_pips=1000.0 if is_crypto else (250.0 if is_jpy else 30.0),
            min_atr_pips=20.0 if is_crypto else (1.0 if is_jpy else 1.0),
            session_start_utc=0,
            session_end_utc=24,  # 24/7
        ))
    if s == "bb_mean_reversion_v3":
        is_jpy = args.symbol.upper().endswith("JPY")
        ps = float(args.pip_size) if float(args.pip_size) > 0 else (0.01 if is_jpy else 0.0001)
        return BBMeanReversionV3(BbRevV3Config(
            pip_size=ps,
            min_band_width_pips=60.0 if is_jpy else 20.0,
            max_atr_pips=250.0 if is_jpy else 25.0,
        ))
    if s == "trendline_break_bounce_v1":
        is_jpy = args.symbol.upper().endswith("JPY")
        ps = float(args.pip_size) if float(args.pip_size) > 0 else (0.01 if is_jpy else 0.0001)
        return TrendlineBreakBounceV1(TlbbV1Config(
            pip_size=ps,
            touch_zone_pips=5.0 if is_jpy else 3.0,
            breakout_confirm_pips=6.0 if is_jpy else 4.0,
        ))
    raise ValueError(f"Unsupported strategy: {s}")


class _NewsFilteredStrategy:
    def __init__(self, inner, *, symbol: str, strategy_name: str, events, policy):
        self.inner = inner
        self.symbol = symbol
        self.strategy_name = strategy_name
        self.events = list(events)
        self.policy = dict(policy or {})
        self.blocked_signals = 0

    def maybe_signal(self, candles, i: int) -> Optional[Signal]:
        sig = self.inner.maybe_signal(candles, i)
        if sig is None:
            return None
        ts_utc = int(candles[i].ts)
        blocked, _reason = is_news_blocked(
            symbol=self.symbol,
            ts_utc=ts_utc,
            strategy_name=self.strategy_name,
            events=self.events,
            policy=self.policy,
        )
        if blocked:
            self.blocked_signals += 1
            return None
        return sig


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--csv", required=True, help="Path to M5 CSV")
    ap.add_argument("--tag", default="forex_pilot")
    ap.add_argument(
        "--strategy",
        default="trend_retest_session_v1",
        help="Format: strategy or strategy:preset",
    )
    ap.add_argument("--spread_pips", type=float, default=1.2)
    ap.add_argument("--swap_long", type=float, default=-0.2, help="pips/day")
    ap.add_argument("--swap_short", type=float, default=-0.2, help="pips/day")
    ap.add_argument("--risk_pct", type=float, default=0.5, help="Risk per trade, percent (for estimated %% equity stats)")
    ap.add_argument("--pip_size", type=float, default=0.0, help="Override pip size; <=0 uses symbol default")
    ap.add_argument("--session_start_utc", type=int, default=6, help="UTC hour inclusive")
    ap.add_argument("--session_end_utc", type=int, default=20, help="UTC hour exclusive")
    ap.add_argument("--ema_fast", type=int, default=48)
    ap.add_argument("--ema_slow", type=int, default=200)
    ap.add_argument("--breakout_lookback", type=int, default=36)
    ap.add_argument("--retest_window_bars", type=int, default=6)
    ap.add_argument("--sl_atr_mult", type=float, default=1.5)
    ap.add_argument("--rr", type=float, default=2.2)
    ap.add_argument("--cooldown_bars", type=int, default=24)
    ap.add_argument("--news-events-csv", default="", help="Optional normalized news events CSV for deterministic blackout gating")
    ap.add_argument("--news-policy-json", default="", help="Optional news policy JSON")
    args = ap.parse_args()

    candles = load_m5_csv(args.csv)
    if not candles:
        raise SystemExit(f"No candles loaded from {args.csv}")

    pip_size = float(args.pip_size) if float(args.pip_size) > 0 else _default_pip_size(args.symbol)
    cfg = EngineConfig(
        pip_size=pip_size,
        spread_pips=float(args.spread_pips),
        swap_long_pips_per_day=float(args.swap_long),
        swap_short_pips_per_day=float(args.swap_short),
        risk_per_trade_pct=float(args.risk_pct) / 100.0,
    )
    strat = _build_strategy(args)
    news_blocked_signals = 0
    if args.news_events_csv:
        events = load_news_events(args.news_events_csv)
        policy = load_news_policy(args.news_policy_json) if args.news_policy_json else {}
        strat = _NewsFilteredStrategy(
            strat,
            symbol=args.symbol.upper(),
            strategy_name=args.strategy.split(":", 1)[0],
            events=events,
            policy=policy,
        )
    trades, summary = run_backtest(candles, strat, cfg)
    if isinstance(strat, _NewsFilteredStrategy):
        news_blocked_signals = int(strat.blocked_signals)

    out_dir = Path("backtest_runs") / f"forex_{args.tag}_{args.symbol.upper()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    trades_csv = out_dir / "trades.csv"
    with trades_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "side",
                "entry_ts",
                "exit_ts",
                "entry_price",
                "exit_price",
                "pnl_pips",
                "net_pips",
                "risk_pips",
                "r_multiple",
                "reason",
            ]
        )
        for t in trades:
            w.writerow(
                [
                    t.side,
                    t.entry_ts,
                    t.exit_ts,
                    f"{t.entry_price:.6f}",
                    f"{t.exit_price:.6f}",
                    f"{t.pnl_pips:.4f}",
                    f"{t.net_pips:.4f}",
                    f"{t.risk_pips:.4f}",
                    f"{t.r_multiple:.6f}",
                    t.reason,
                ]
            )

    summary_csv = out_dir / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "symbol",
                "strategy",
                "pip_size",
                "risk_pct",
                "trades",
                "winrate",
                "net_pips",
                "gross_pips",
                "max_dd_pips",
                "avg_win_pips",
                "avg_loss_pips",
                "last_equity_pips",
                "sum_r",
                "return_pct_est",
                "news_blocked_signals",
            ]
        )
        w.writerow([
            args.symbol.upper(),
            args.strategy,
            f"{pip_size:.8f}",
            f"{float(args.risk_pct):.4f}",
            summary.trades,
            f"{summary.winrate:.2f}",
            f"{summary.net_pips:.4f}",
            f"{summary.gross_pips:.4f}",
            f"{summary.max_dd_pips:.4f}",
            f"{summary.avg_win_pips:.4f}",
            f"{summary.avg_loss_pips:.4f}",
            f"{summary.last_equity_pips:.4f}",
            f"{summary.sum_r:.6f}",
            f"{summary.return_pct_est:.4f}",
            news_blocked_signals,
        ])

    print(f"saved={out_dir}")
    print(summary_csv.read_text(encoding="utf-8").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
