#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.data import load_m5_csv
from forex.engine import EngineConfig, run_backtest
from forex.strategies.breakout_continuation_session_v1 import (
    BreakoutContinuationSessionV1,
    Config as BreakoutContinuationConfig,
)
from forex.strategies.grid_reversion_session_v1 import GridReversionSessionV1, Config as GridReversionConfig
from forex.strategies.range_bounce_session_v1 import RangeBounceSessionV1, Config as RangeBounceConfig
from forex.strategies.trend_pullback_rebound_v1 import TrendPullbackReboundV1, Config as TrendPullbackConfig
from forex.strategies.trend_retest_session_v1 import Config as TrendRetestConfig
from forex.strategies.trend_retest_session_v1 import TrendRetestSessionV1
from forex.types import Trade


BASE_STRATEGIES = {
    "trend_retest_session_v1",
    "range_bounce_session_v1",
    "breakout_continuation_session_v1",
    "grid_reversion_session_v1",
    "trend_pullback_rebound_v1",
}

PRESETS: Dict[str, Dict[str, Dict[str, float | int]]] = {
    "trend_retest_session_v1": {
        "default": {
            "ema_fast": 55,
            "ema_slow": 220,
            "breakout_lookback": 42,
            "retest_window_bars": 8,
            "sl_atr_mult": 1.4,
            "rr": 2.5,
            "cooldown_bars": 32,
        },
        "conservative": {
            "ema_fast": 55,
            "ema_slow": 220,
            "breakout_lookback": 42,
            "retest_window_bars": 8,
            "sl_atr_mult": 1.4,
            "rr": 2.5,
            "cooldown_bars": 32,
        },
        "balanced": {
            "ema_fast": 48,
            "ema_slow": 200,
            "breakout_lookback": 36,
            "retest_window_bars": 6,
            "sl_atr_mult": 1.5,
            "rr": 2.2,
            "cooldown_bars": 24,
        },
        "active": {
            "ema_fast": 34,
            "ema_slow": 144,
            "breakout_lookback": 24,
            "retest_window_bars": 5,
            "sl_atr_mult": 1.6,
            "rr": 1.9,
            "cooldown_bars": 14,
        },
        "eurusd_canary": {
            "ema_fast": 40,
            "ema_slow": 180,
            "breakout_lookback": 36,
            "retest_window_bars": 8,
            "sl_atr_mult": 1.3,
            "rr": 2.5,
            "cooldown_bars": 32,
        },
        "winrate_plus": {
            "ema_fast": 55,
            "ema_slow": 220,
            "breakout_lookback": 30,
            "retest_window_bars": 10,
            "sl_atr_mult": 1.2,
            "rr": 1.4,
            "cooldown_bars": 24,
        },
        "gbpjpy_stability_a": {
            "ema_fast": 48,
            "ema_slow": 180,
            "breakout_lookback": 36,
            "retest_window_bars": 8,
            "sl_atr_mult": 1.3,
            "rr": 1.8,
            "cooldown_bars": 32,
        },
        "gbpjpy_stability_b": {
            "ema_fast": 48,
            "ema_slow": 220,
            "breakout_lookback": 36,
            "retest_window_bars": 8,
            "sl_atr_mult": 1.2,
            "rr": 1.8,
            "cooldown_bars": 24,
        },
        "stability_core": {
            "ema_fast": 64,
            "ema_slow": 220,
            "breakout_lookback": 48,
            "retest_window_bars": 10,
            "sl_atr_mult": 1.1,
            "rr": 1.3,
            "cooldown_bars": 36,
        },
        "stability_tight": {
            "ema_fast": 55,
            "ema_slow": 220,
            "breakout_lookback": 42,
            "retest_window_bars": 8,
            "sl_atr_mult": 1.0,
            "rr": 1.25,
            "cooldown_bars": 32,
        },
    },
    "range_bounce_session_v1": {
        "default": {
            "range_lookback": 48,
            "max_ema_gap_atr": 0.45,
            "min_range_width_atr": 1.0,
            "max_range_width_atr": 4.5,
            "zone_atr": 0.20,
            "reclaim_atr": 0.05,
            "min_reject_wick_atr": 0.08,
            "sl_pad_atr": 0.28,
            "rr": 1.6,
            "cooldown_bars": 18,
        },
        "loose": {
            "range_lookback": 40,
            "max_ema_gap_atr": 0.60,
            "min_range_width_atr": 0.8,
            "max_range_width_atr": 5.8,
            "zone_atr": 0.28,
            "reclaim_atr": 0.03,
            "min_reject_wick_atr": 0.06,
            "sl_pad_atr": 0.34,
            "rr": 1.45,
            "cooldown_bars": 12,
        },
    },
    "breakout_continuation_session_v1": {
        "default": {
            "breakout_lookback": 24,
            "breakout_atr": 0.10,
            "min_body_atr": 0.12,
            "max_chase_atr": 0.70,
            "sl_atr_mult": 1.3,
            "rr": 1.9,
            "cooldown_bars": 14,
        },
        "strict": {
            "breakout_lookback": 30,
            "breakout_atr": 0.14,
            "min_body_atr": 0.16,
            "max_chase_atr": 0.55,
            "sl_atr_mult": 1.2,
            "rr": 2.1,
            "cooldown_bars": 18,
        },
        "active": {
            "breakout_lookback": 20,
            "breakout_atr": 0.08,
            "min_body_atr": 0.10,
            "max_chase_atr": 0.85,
            "sl_atr_mult": 1.4,
            "rr": 1.7,
            "cooldown_bars": 10,
        },
    },
    "grid_reversion_session_v1": {
        "default": {
            "grid_step_atr": 1.0,
            "trend_guard_atr": 0.9,
            "rsi_long_max": 42.0,
            "rsi_short_min": 58.0,
            "tp_to_ema_buffer_atr": 0.08,
            "sl_atr_mult": 1.2,
            "rr_cap": 2.2,
            "cooldown_bars": 16,
        },
        "strict": {
            "grid_step_atr": 1.2,
            "trend_guard_atr": 0.7,
            "rsi_long_max": 38.0,
            "rsi_short_min": 62.0,
            "tp_to_ema_buffer_atr": 0.05,
            "sl_atr_mult": 1.1,
            "rr_cap": 2.0,
            "cooldown_bars": 20,
        },
        "active": {
            "grid_step_atr": 0.8,
            "trend_guard_atr": 1.1,
            "rsi_long_max": 45.0,
            "rsi_short_min": 55.0,
            "tp_to_ema_buffer_atr": 0.10,
            "sl_atr_mult": 1.3,
            "rr_cap": 2.3,
            "cooldown_bars": 12,
        },
        "eurjpy_canary": {
            "grid_step_atr": 1.0,
            "trend_guard_atr": 0.9,
            "rsi_long_max": 43.0,
            "rsi_short_min": 57.0,
            "tp_to_ema_buffer_atr": 0.05,
            "sl_atr_mult": 1.2,
            "rr_cap": 2.2,
            "cooldown_bars": 16,
        },
        "safe_winrate": {
            "grid_step_atr": 0.9,
            "trend_guard_atr": 0.8,
            "rsi_long_max": 40.0,
            "rsi_short_min": 60.0,
            "tp_to_ema_buffer_atr": 0.03,
            "sl_atr_mult": 1.15,
            "rr_cap": 1.5,
            "cooldown_bars": 14,
        },
        "stability_core": {
            "grid_step_atr": 1.1,
            "trend_guard_atr": 0.65,
            "rsi_long_max": 37.0,
            "rsi_short_min": 63.0,
            "tp_to_ema_buffer_atr": 0.02,
            "sl_atr_mult": 1.05,
            "rr_cap": 1.35,
            "cooldown_bars": 24,
        },
        "stability_tight": {
            "grid_step_atr": 1.0,
            "trend_guard_atr": 0.70,
            "rsi_long_max": 38.0,
            "rsi_short_min": 62.0,
            "tp_to_ema_buffer_atr": 0.02,
            "sl_atr_mult": 1.10,
            "rr_cap": 1.40,
            "cooldown_bars": 20,
        },
    },
    "trend_pullback_rebound_v1": {
        "default": {
            "pullback_zone_atr": 0.30,
            "reclaim_atr": 0.05,
            "rsi_long_max": 52.0,
            "rsi_short_min": 48.0,
            "sl_atr_mult": 1.35,
            "rr": 2.0,
            "cooldown_bars": 16,
        },
        "strict": {
            "pullback_zone_atr": 0.24,
            "reclaim_atr": 0.08,
            "rsi_long_max": 48.0,
            "rsi_short_min": 52.0,
            "sl_atr_mult": 1.25,
            "rr": 2.2,
            "cooldown_bars": 22,
        },
    },
}


def _default_spread(pair: str) -> float:
    p = pair.upper()
    if p.endswith("JPY"):
        return 1.0
    if p in {"EURUSD", "USDCHF"}:
        return 1.0
    if p in {"GBPUSD", "GBPAUD", "GBPJPY", "GBPCHF", "GBPCAD"}:
        return 1.2
    if p in {"AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "AUDJPY", "CADJPY", "CHFJPY"}:
        return 1.3
    return 1.5


def _default_swap(pair: str) -> float:
    p = pair.upper()
    if p in {"EURUSD", "USDJPY", "USDCHF"}:
        return -0.3
    if p in {"GBPUSD", "GBPJPY", "GBPAUD", "GBPCHF", "GBPCAD"}:
        return -0.4
    return -0.35


def _default_pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


def _parse_strategy_name(strategy_name: str) -> Tuple[str, str]:
    raw = strategy_name.strip()
    if ":" in raw:
        base, preset = raw.split(":", 1)
        return base.strip(), preset.strip() or "default"
    return raw, "default"


def _build_strategy(name: str, session_start: int, session_end: int):
    base_name, preset_name = _parse_strategy_name(name)
    if base_name not in BASE_STRATEGIES:
        raise ValueError(f"Unsupported strategy: {base_name}")
    if preset_name not in PRESETS.get(base_name, {}):
        allowed = ",".join(sorted(PRESETS.get(base_name, {}).keys()))
        raise ValueError(f"Unsupported preset '{preset_name}' for {base_name}; allowed: {allowed}")
    p = PRESETS[base_name][preset_name]

    if base_name == "trend_retest_session_v1":
        return TrendRetestSessionV1(
            TrendRetestConfig(
                ema_fast=int(p["ema_fast"]),
                ema_slow=int(p["ema_slow"]),
                breakout_lookback=int(p["breakout_lookback"]),
                retest_window_bars=int(p["retest_window_bars"]),
                sl_atr_mult=float(p["sl_atr_mult"]),
                rr=float(p["rr"]),
                cooldown_bars=int(p["cooldown_bars"]),
                session_utc_start=session_start,
                session_utc_end=session_end,
            )
        )
    if base_name == "range_bounce_session_v1":
        return RangeBounceSessionV1(
            RangeBounceConfig(
                range_lookback=int(p["range_lookback"]),
                max_ema_gap_atr=float(p["max_ema_gap_atr"]),
                min_range_width_atr=float(p["min_range_width_atr"]),
                max_range_width_atr=float(p["max_range_width_atr"]),
                zone_atr=float(p["zone_atr"]),
                reclaim_atr=float(p["reclaim_atr"]),
                min_reject_wick_atr=float(p["min_reject_wick_atr"]),
                sl_pad_atr=float(p["sl_pad_atr"]),
                rr=float(p["rr"]),
                cooldown_bars=int(p["cooldown_bars"]),
                session_utc_start=session_start,
                session_utc_end=session_end,
            )
        )
    if base_name == "breakout_continuation_session_v1":
        return BreakoutContinuationSessionV1(
            BreakoutContinuationConfig(
                breakout_lookback=int(p["breakout_lookback"]),
                breakout_atr=float(p["breakout_atr"]),
                min_body_atr=float(p["min_body_atr"]),
                max_chase_atr=float(p["max_chase_atr"]),
                sl_atr_mult=float(p["sl_atr_mult"]),
                rr=float(p["rr"]),
                cooldown_bars=int(p["cooldown_bars"]),
                session_utc_start=session_start,
                session_utc_end=session_end,
            )
        )
    if base_name == "grid_reversion_session_v1":
        return GridReversionSessionV1(
            GridReversionConfig(
                grid_step_atr=float(p["grid_step_atr"]),
                trend_guard_atr=float(p["trend_guard_atr"]),
                rsi_long_max=float(p["rsi_long_max"]),
                rsi_short_min=float(p["rsi_short_min"]),
                tp_to_ema_buffer_atr=float(p["tp_to_ema_buffer_atr"]),
                sl_atr_mult=float(p["sl_atr_mult"]),
                rr_cap=float(p["rr_cap"]),
                cooldown_bars=int(p["cooldown_bars"]),
                session_utc_start=session_start,
                session_utc_end=session_end,
            )
        )
    if base_name == "trend_pullback_rebound_v1":
        return TrendPullbackReboundV1(
            TrendPullbackConfig(
                pullback_zone_atr=float(p["pullback_zone_atr"]),
                reclaim_atr=float(p["reclaim_atr"]),
                rsi_long_max=float(p["rsi_long_max"]),
                rsi_short_min=float(p["rsi_short_min"]),
                sl_atr_mult=float(p["sl_atr_mult"]),
                rr=float(p["rr"]),
                cooldown_bars=int(p["cooldown_bars"]),
                session_utc_start=session_start,
                session_utc_end=session_end,
            )
        )
    raise ValueError(f"Unsupported strategy: {base_name}")


@dataclass
class RunRow:
    pair: str
    strategy: str
    cost: str
    trades: int
    winrate: float
    net_pips: float
    gross_pips: float
    max_dd_pips: float
    recent_net_pips: float
    recent_trades: int
    recent_winrate: float
    sum_r: float
    return_pct_est: float
    return_pct_est_month: float
    status: str
    error: str


def _recent_stats(trades: Sequence[Trade], recent_days: int) -> Tuple[float, int, float]:
    if recent_days <= 0:
        return 0.0, 0, 0.0
    if not trades:
        return 0.0, 0, 0.0
    max_ts = max(t.entry_ts for t in trades)
    cutoff = max_ts - recent_days * 86400
    t2 = [t for t in trades if t.entry_ts >= cutoff]
    if not t2:
        return 0.0, 0, 0.0
    wins = sum(1 for t in t2 if t.net_pips > 0)
    return sum(t.net_pips for t in t2), len(t2), wins / len(t2)


def _monthly_pct_from_total(total_pct: float, span_days: float) -> float:
    if span_days <= 0:
        return 0.0
    months = span_days / 30.4375
    if months <= 0:
        return 0.0
    base = max(0.0, 1.0 + float(total_pct) / 100.0)
    if base <= 0:
        return -100.0
    return ((base ** (1.0 / months)) - 1.0) * 100.0


def _run_one(
    *,
    pair: str,
    strategy_name: str,
    candles,
    spread: float,
    swap: float,
    recent_days: int,
    session_start: int,
    session_end: int,
    risk_pct: float,
) -> RunRow:
    try:
        strategy = _build_strategy(strategy_name, session_start=session_start, session_end=session_end)
        cfg = EngineConfig(
            pip_size=_default_pip_size(pair),
            spread_pips=spread,
            swap_long_pips_per_day=swap,
            swap_short_pips_per_day=swap,
            risk_per_trade_pct=float(risk_pct) / 100.0,
        )
        trades, summary = run_backtest(candles, strategy, cfg)
        rnet, rtr, rwr = _recent_stats(trades, recent_days=recent_days)
        span_days = 0.0
        if candles:
            span_days = max(0.0, float(candles[-1].ts - candles[0].ts) / 86400.0)
        return RunRow(
            pair=pair,
            strategy=strategy_name,
            cost="",
            trades=summary.trades,
            winrate=summary.winrate,
            net_pips=summary.net_pips,
            gross_pips=summary.gross_pips,
            max_dd_pips=summary.max_dd_pips,
            recent_net_pips=rnet,
            recent_trades=rtr,
            recent_winrate=rwr,
            sum_r=summary.sum_r,
            return_pct_est=summary.return_pct_est,
            return_pct_est_month=_monthly_pct_from_total(summary.return_pct_est, span_days),
            status="ok",
            error="",
        )
    except Exception as e:
        return RunRow(
            pair=pair,
            strategy=strategy_name,
            cost="",
            trades=0,
            winrate=0.0,
            net_pips=0.0,
            gross_pips=0.0,
            max_dd_pips=0.0,
            recent_net_pips=0.0,
            recent_trades=0,
            recent_winrate=0.0,
            sum_r=0.0,
            return_pct_est=0.0,
            return_pct_est_month=0.0,
            status="fail",
            error=str(e).replace(",", ";"),
        )


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main() -> int:
    ap = argparse.ArgumentParser(description="Forex multi-strategy universe gate (pair + strategy).")
    ap.add_argument(
        "--pairs",
        default="EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY",
    )
    ap.add_argument(
        "--strategies",
        default="trend_retest_session_v1,range_bounce_session_v1,breakout_continuation_session_v1,grid_reversion_session_v1,trend_pullback_rebound_v1",
    )
    ap.add_argument("--data-dir", default="data_cache/forex")
    ap.add_argument("--session-start-utc", type=int, default=6)
    ap.add_argument("--session-end-utc", type=int, default=20)
    ap.add_argument("--max-bars", type=int, default=0, help="Use only latest N bars for faster scan; 0 = full history")
    ap.add_argument("--stress-spread-mult", type=float, default=1.5)
    ap.add_argument("--stress-swap-mult", type=float, default=1.5)
    ap.add_argument("--recent-days", type=int, default=28)
    ap.add_argument("--min-base-net", type=float, default=0.0)
    ap.add_argument("--min-stress-net", type=float, default=0.0)
    ap.add_argument(
        "--min-base-return-pct-est",
        type=float,
        default=-999.0,
        help="Optional gate on estimated base return percent; keep very low to disable.",
    )
    ap.add_argument(
        "--min-stress-return-pct-est",
        type=float,
        default=-999.0,
        help="Optional gate on estimated stress return percent; keep very low to disable.",
    )
    ap.add_argument(
        "--min-stress-return-pct-est-month",
        type=float,
        default=-999.0,
        help="Optional gate on estimated stress monthly return percent; keep very low to disable.",
    )
    ap.add_argument("--min-trades", type=int, default=40)
    ap.add_argument("--max-stress-dd", type=float, default=300.0)
    ap.add_argument("--min-recent-stress-net", type=float, default=0.0)
    ap.add_argument("--min-recent-trades", type=int, default=8)
    ap.add_argument("--top-n", type=int, default=12)
    ap.add_argument("--risk-pct", type=float, default=0.5, help="Risk per trade, percent (for estimated %% columns)")
    ap.add_argument("--tag", default="fx_multi_gate")
    args = ap.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    strategy_names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    for s in strategy_names:
        base_name, preset_name = _parse_strategy_name(s)
        if base_name not in BASE_STRATEGIES:
            raise SystemExit(f"Unsupported strategy: {base_name}")
        if preset_name not in PRESETS.get(base_name, {}):
            allowed = ",".join(sorted(PRESETS.get(base_name, {}).keys()))
            raise SystemExit(f"Unsupported preset '{preset_name}' for {base_name}; allowed: {allowed}")

    out_dir = ROOT / "backtest_runs" / f"forex_multi_strategy_gate_{args.tag}_{_utc_compact()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    data_dir = (ROOT / args.data_dir).resolve()
    print("forex multi strategy gate start")
    print(f"pairs={','.join(pairs)}")
    print(f"strategies={','.join(strategy_names)}")
    print(f"data_dir={data_dir}")
    print(f"recent_days={args.recent_days}")
    print(f"out_dir={out_dir}")

    rows: List[RunRow] = []
    candles_cache = {}
    for pair in pairs:
        csv_path = data_dir / f"{pair}_M5.csv"
        if not csv_path.exists():
            for s in strategy_names:
                rows.append(
                    RunRow(
                        pair=pair,
                        strategy=s,
                        cost="base",
                        trades=0,
                        winrate=0.0,
                        net_pips=0.0,
                        gross_pips=0.0,
                        max_dd_pips=0.0,
                        recent_net_pips=0.0,
                        recent_trades=0,
                        recent_winrate=0.0,
                        sum_r=0.0,
                        return_pct_est=0.0,
                        return_pct_est_month=0.0,
                        status="skip",
                        error="missing_csv",
                    )
                )
            continue
        candles_cache[pair] = load_m5_csv(str(csv_path))
        if int(args.max_bars) > 0 and len(candles_cache[pair]) > int(args.max_bars):
            candles_cache[pair] = candles_cache[pair][-int(args.max_bars) :]

    for pair, candles in candles_cache.items():
        base_spread = _default_spread(pair)
        base_swap = _default_swap(pair)
        for strategy_name in strategy_names:
            base = _run_one(
                pair=pair,
                strategy_name=strategy_name,
                candles=candles,
                spread=base_spread,
                swap=base_swap,
                recent_days=int(args.recent_days),
                session_start=int(args.session_start_utc),
                session_end=int(args.session_end_utc),
                risk_pct=float(args.risk_pct),
            )
            base.cost = "base"
            rows.append(base)

            stress = _run_one(
                pair=pair,
                strategy_name=strategy_name,
                candles=candles,
                spread=base_spread * float(args.stress_spread_mult),
                swap=base_swap * float(args.stress_swap_mult),
                recent_days=int(args.recent_days),
                session_start=int(args.session_start_utc),
                session_end=int(args.session_end_utc),
                risk_pct=float(args.risk_pct),
            )
            stress.cost = "stress"
            rows.append(stress)

    raw_csv = out_dir / "raw_runs.csv"
    with raw_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "pair",
                "strategy",
                "cost",
                "status",
                "trades",
                "winrate",
                "net_pips",
                "gross_pips",
                "max_dd_pips",
                "recent_net_pips",
                "recent_trades",
                "recent_winrate",
                "sum_r",
                "return_pct_est",
                "return_pct_est_month",
                "error",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.pair,
                    r.strategy,
                    r.cost,
                    r.status,
                    r.trades,
                    f"{r.winrate:.4f}",
                    f"{r.net_pips:.4f}",
                    f"{r.gross_pips:.4f}",
                    f"{r.max_dd_pips:.4f}",
                    f"{r.recent_net_pips:.4f}",
                    r.recent_trades,
                    f"{r.recent_winrate:.4f}",
                    f"{r.sum_r:.6f}",
                    f"{r.return_pct_est:.4f}",
                    f"{r.return_pct_est_month:.4f}",
                    r.error,
                ]
            )

    grouped: Dict[Tuple[str, str], Dict[str, RunRow]] = {}
    for r in rows:
        if r.status != "ok":
            continue
        grouped.setdefault((r.pair, r.strategy), {})[r.cost] = r

    gated = []
    for (pair, strategy_name), d in grouped.items():
        if "base" not in d or "stress" not in d:
            continue
        b = d["base"]
        s = d["stress"]
        ok = (
            b.net_pips >= float(args.min_base_net)
            and s.net_pips >= float(args.min_stress_net)
            and b.return_pct_est >= float(args.min_base_return_pct_est)
            and s.return_pct_est >= float(args.min_stress_return_pct_est)
            and s.return_pct_est_month >= float(args.min_stress_return_pct_est_month)
            and min(b.trades, s.trades) >= int(args.min_trades)
            and s.max_dd_pips <= float(args.max_stress_dd)
            and s.recent_net_pips >= float(args.min_recent_stress_net)
            and s.recent_trades >= int(args.min_recent_trades)
        )
        gated.append(
            {
                "pair": pair,
                "strategy": strategy_name,
                "base_net_pips": b.net_pips,
                "stress_net_pips": s.net_pips,
                "base_trades": b.trades,
                "stress_trades": s.trades,
                "base_dd_pips": b.max_dd_pips,
                "stress_dd_pips": s.max_dd_pips,
                "recent_stress_net_pips": s.recent_net_pips,
                "recent_stress_trades": s.recent_trades,
                "recent_stress_winrate": s.recent_winrate,
                "base_return_pct_est": b.return_pct_est,
                "stress_return_pct_est": s.return_pct_est,
                "stress_return_pct_est_month": s.return_pct_est_month,
                "pass_gate": 1 if ok else 0,
            }
        )

    gated.sort(key=lambda x: (x["pass_gate"], x["stress_net_pips"]), reverse=True)
    gated_csv = out_dir / "gated_summary.csv"
    with gated_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "pair",
                "strategy",
                "base_net_pips",
                "stress_net_pips",
                "base_trades",
                "stress_trades",
                "base_dd_pips",
                "stress_dd_pips",
                "recent_stress_net_pips",
                "recent_stress_trades",
                "recent_stress_winrate",
                "base_return_pct_est",
                "stress_return_pct_est",
                "stress_return_pct_est_month",
                "pass_gate",
            ]
        )
        for r in gated:
            w.writerow(
                [
                    r["pair"],
                    r["strategy"],
                    f"{r['base_net_pips']:.4f}",
                    f"{r['stress_net_pips']:.4f}",
                    r["base_trades"],
                    r["stress_trades"],
                    f"{r['base_dd_pips']:.4f}",
                    f"{r['stress_dd_pips']:.4f}",
                    f"{r['recent_stress_net_pips']:.4f}",
                    r["recent_stress_trades"],
                    f"{r['recent_stress_winrate']:.4f}",
                    f"{r['base_return_pct_est']:.4f}",
                    f"{r['stress_return_pct_est']:.4f}",
                    f"{r['stress_return_pct_est_month']:.4f}",
                    r["pass_gate"],
                ]
            )

    selected = [r for r in gated if r["pass_gate"] == 1][: max(1, int(args.top_n))]
    selected_csv = out_dir / "selected_combos.csv"
    selected_txt = out_dir / "selected_combos.txt"
    selected_pairs_txt = out_dir / "selected_pairs.txt"
    with selected_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "pair",
                "strategy",
                "stress_net_pips",
                "stress_trades",
                "stress_dd_pips",
                "recent_stress_net_pips",
                "recent_stress_trades",
                "recent_stress_winrate",
                "stress_return_pct_est",
                "stress_return_pct_est_month",
            ]
        )
        for r in selected:
            w.writerow(
                [
                    r["pair"],
                    r["strategy"],
                    f"{r['stress_net_pips']:.4f}",
                    r["stress_trades"],
                    f"{r['stress_dd_pips']:.4f}",
                    f"{r['recent_stress_net_pips']:.4f}",
                    r["recent_stress_trades"],
                    f"{r['recent_stress_winrate']:.4f}",
                    f"{r['stress_return_pct_est']:.4f}",
                    f"{r['stress_return_pct_est_month']:.4f}",
                ]
            )

    with selected_txt.open("w", encoding="utf-8") as f:
        f.write(",".join([f"{r['pair']}@{r['strategy']}" for r in selected]))

    selected_pairs = []
    for r in selected:
        if r["pair"] not in selected_pairs:
            selected_pairs.append(r["pair"])
    with selected_pairs_txt.open("w", encoding="utf-8") as f:
        f.write(",".join(selected_pairs))

    print("")
    print("=== GATE PASS (stress net desc) ===")
    for r in selected:
        print(
            f"{r['pair']:>8} {r['strategy']:>34} "
            f"base={r['base_net_pips']:.2f} stress={r['stress_net_pips']:.2f} "
            f"ret={r['stress_return_pct_est']:.2f}% ret_m={r['stress_return_pct_est_month']:.2f}% "
            f"recent={r['recent_stress_net_pips']:.2f} trades={r['stress_trades']} dd={r['stress_dd_pips']:.2f}"
        )
    if not selected:
        print("no pair+strategy passed current gate")

    print("")
    print(f"raw={raw_csv}")
    print(f"gated={gated_csv}")
    print(f"selected_csv={selected_csv}")
    print(f"selected_combos_txt={selected_txt}")
    print(f"selected_pairs_txt={selected_pairs_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
