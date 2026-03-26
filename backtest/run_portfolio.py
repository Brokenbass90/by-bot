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
from collections import defaultdict
from importlib import import_module
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


from backtest.bybit_data import fetch_klines_public
from backtest.engine import BacktestParams, KlineStore, Candle
from backtest.metrics import summarize_trades
from backtest.portfolio_engine import run_portfolio_backtest
from news_filter import is_news_blocked, load_news_events, load_news_policy


def _import_strategy_class(module_name: str, class_name: str):
    for package_name in ("strategies", "archive.strategies_retired"):
        try:
            module = import_module(f"{package_name}.{module_name}")
            return getattr(module, class_name)
        except ModuleNotFoundError as exc:
            missing = str(getattr(exc, "name", "") or "")
            expected = {
                f"{package_name}.{module_name}",
                module_name,
            }
            if missing in expected:
                continue
            raise
        except AttributeError:
            continue
    raise ImportError(f"Cannot import {class_name} from strategies or archive for module '{module_name}'")


BounceBTStrategy = _import_strategy_class("bounce_bt", "BounceBTStrategy")
BounceBTV2Strategy = _import_strategy_class("bounce_bt_v2", "BounceBTV2Strategy")
RangeWrapper = _import_strategy_class("range_wrapper", "RangeWrapper")
InPlayWrapper = _import_strategy_class("inplay_wrapper", "InPlayWrapper")
RetestBacktestStrategy = _import_strategy_class("retest_backtest", "RetestBacktestStrategy")
InPlayBreakoutWrapper = _import_strategy_class("inplay_breakout", "InPlayBreakoutWrapper")
InPlayPullbackWrapper = _import_strategy_class("inplay_pullback", "InPlayPullbackWrapper")
PumpFadeStrategy = _import_strategy_class("pump_fade", "PumpFadeStrategy")
MomentumContinuationStrategy = _import_strategy_class("momentum_continuation", "MomentumContinuationStrategy")
TrendPullbackStrategy = _import_strategy_class("trend_pullback", "TrendPullbackStrategy")
TrendPullbackBETrailStrategy = _import_strategy_class("trend_pullback_be_trail", "TrendPullbackBETrailStrategy")
TrendRegimeBreakoutStrategy = _import_strategy_class("trend_regime_breakout", "TrendRegimeBreakoutStrategy")
VolatilityBreakoutStrategy = _import_strategy_class("vol_breakout", "VolatilityBreakoutStrategy")
AdaptiveRangeShortStrategy = _import_strategy_class("adaptive_range_short", "AdaptiveRangeShortStrategy")
SmartGridStrategy = _import_strategy_class("smart_grid", "SmartGridStrategy")
SmartGridV2Strategy = _import_strategy_class("smart_grid_v2", "SmartGridV2Strategy")
SmartGridV3Strategy = _import_strategy_class("smart_grid_v3", "SmartGridV3Strategy")
RangeBounceStrategy = _import_strategy_class("range_bounce", "RangeBounceStrategy")
DonchianBreakoutStrategy = _import_strategy_class("donchian_breakout", "DonchianBreakoutStrategy")
BTCETHMidtermPullbackStrategy = _import_strategy_class("btc_eth_midterm_pullback", "BTCETHMidtermPullbackStrategy")
BTCETHVolExpansionStrategy = _import_strategy_class("btc_eth_vol_expansion", "BTCETHVolExpansionStrategy")
BTCETHTrendRSIReentryStrategy = _import_strategy_class("btc_eth_trend_rsi_reentry", "BTCETHTrendRSIReentryStrategy")
TrendlineBreakRetestStrategy = _import_strategy_class("trendline_break_retest", "TrendlineBreakRetestStrategy")
BTCETHTrendFollowStrategy = _import_strategy_class("btc_eth_trend_follow", "BTCETHTrendFollowStrategy")
TrendlineBreakRetestV2Strategy = _import_strategy_class("trendline_break_retest_v2", "TrendlineBreakRetestV2Strategy")
FlatBounceV2Strategy = _import_strategy_class("flat_bounce_v2", "FlatBounceV2Strategy")
FlatBounceV3Strategy = _import_strategy_class("flat_bounce_v3", "FlatBounceV3Strategy")
BTCETHTrendFollowV2Strategy = _import_strategy_class("btc_eth_trend_follow_v2", "BTCETHTrendFollowV2Strategy")
TrendlineBreakRetestV3Strategy = _import_strategy_class("trendline_break_retest_v3", "TrendlineBreakRetestV3Strategy")
TrendlineBreakRetestV4Strategy = _import_strategy_class("trendline_break_retest_v4", "TrendlineBreakRetestV4Strategy")
StructureShiftV1Strategy = _import_strategy_class("structure_shift_v1", "StructureShiftV1Strategy")
StructureShiftV2Strategy = _import_strategy_class("structure_shift_v2", "StructureShiftV2Strategy")
TVATRTrendV1Strategy = _import_strategy_class("tv_atr_trend_v1", "TVATRTrendV1Strategy")
TVATRTrendV2Strategy = _import_strategy_class("tv_atr_trend_v2", "TVATRTrendV2Strategy")
TripleScreenV132Strategy = _import_strategy_class("triple_screen_v132", "TripleScreenV132Strategy")
TripleScreenV132BStrategy = _import_strategy_class("triple_screen_v132b", "TripleScreenV132BStrategy")
SRBreakRetestVolumeV1Strategy = _import_strategy_class("sr_break_retest_volume_v1", "SRBreakRetestVolumeV1Strategy")
BTCRegimeRetestV1Strategy = _import_strategy_class("btc_regime_retest_v1", "BTCRegimeRetestV1Strategy")
BTCCyclePullbackV1Strategy = _import_strategy_class("btc_cycle_pullback_v1", "BTCCyclePullbackV1Strategy")
BTCMacroCycleV1Strategy = _import_strategy_class("btc_macro_cycle_v1", "BTCMacroCycleV1Strategy")
BTCCycleContinuationV1Strategy = _import_strategy_class("btc_cycle_continuation_v1", "BTCCycleContinuationV1Strategy")
BTCCycleLevelTargetV2Strategy = _import_strategy_class("btc_cycle_level_target_v2", "BTCCycleLevelTargetV2Strategy")
BTCDailyLevelReclaimV1Strategy = _import_strategy_class("btc_daily_level_reclaim_v1", "BTCDailyLevelReclaimV1Strategy")
BTCSwingZoneReclaimV1Strategy = _import_strategy_class("btc_swing_zone_reclaim_v1", "BTCSwingZoneReclaimV1Strategy")
BTCWeeklyZoneReclaimV2Strategy = _import_strategy_class("btc_weekly_zone_reclaim_v2", "BTCWeeklyZoneReclaimV2Strategy")
BTCRegimeFlipContinuationV1Strategy = _import_strategy_class("btc_regime_flip_continuation_v1", "BTCRegimeFlipContinuationV1Strategy")
BTCSlopedReclaimV1Strategy = _import_strategy_class("btc_sloped_reclaim_v1", "BTCSlopedReclaimV1Strategy")
AltRangeReclaimV1Strategy = _import_strategy_class("alt_range_reclaim_v1", "AltRangeReclaimV1Strategy")
AltResistanceFadeV1Strategy = _import_strategy_class("alt_resistance_fade_v1", "AltResistanceFadeV1Strategy")
AltSlopedChannelV1Strategy = _import_strategy_class("alt_sloped_channel_v1", "AltSlopedChannelV1Strategy")
AltInplayBreakdownV1Strategy = _import_strategy_class("alt_inplay_breakdown_v1", "AltInplayBreakdownV1Strategy")
MicroScalperV1Strategy = _import_strategy_class("micro_scalper_v1", "MicroScalperV1Strategy")
AltSupportReclaimV1Strategy = _import_strategy_class("alt_support_reclaim_v1", "AltSupportReclaimV1Strategy")


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _atr_from_candles(c5: List[Candle], period: int = 14) -> float:
    if len(c5) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        h = float(c5[i].h)
        l = float(c5[i].l)
        pc = float(c5[i - 1].c)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / float(period) if trs else float("nan")


def _atr_from_rows(rows: List[list], period: int = 14) -> float:
    if len(rows) < period + 1:
        return float("nan")
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    trs: List[float] = []
    for i in range(-period, 0):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / float(period) if trs else float("nan")


def _rsi(values: List[float], period: int = 14) -> float:
    if period <= 0 or len(values) < period + 1:
        return float("nan")
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses += -d
    if losses <= 1e-12:
        return 100.0
    rs = (gains / float(period)) / (losses / float(period))
    return 100.0 - (100.0 / (1.0 + rs))


def _flat_score(c5: List[Candle]) -> tuple[float, dict]:
    """Compute a flat-regime score in [0..1] for symbol prefiltering."""
    if len(c5) < 1200:
        return 0.0, {"reason": "history_short"}

    # Use ~20+ days of 5m bars for stable regime classification.
    closes = [float(x.c) for x in c5[-6000:]]
    highs = [float(x.h) for x in c5[-6000:]]
    lows = [float(x.l) for x in c5[-6000:]]
    c_now = closes[-1]
    if c_now <= 0:
        return 0.0, {"reason": "invalid_price"}

    ef = _ema(closes[-80:], 20)
    es = _ema(closes[-110:], 50)
    atr = _atr_from_candles(c5[-120:], 14)
    if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(atr) and atr > 0):
        return 0.0, {"reason": "nan_indicators"}

    gap_pct = abs(ef - es) / c_now * 100.0
    atr_pct = atr / c_now * 100.0

    # Flatness from 4h proxy slope (using 5m series sampled every 48 bars).
    sampled = closes[::48]
    if len(sampled) < 12:
        return 0.0, {"reason": "sample_short"}
    ema_s = _ema(sampled, 10)
    ema_prev = _ema(sampled[:-4], 10)
    slope_pct = abs((ema_s - ema_prev) / max(1e-12, abs(ema_prev))) * 100.0 if math.isfinite(ema_prev) else 999.0

    rng_hi = max(highs[-180:])
    rng_lo = min(lows[-180:])
    range_pct = (rng_hi - rng_lo) / c_now * 100.0

    # Smooth normalization to avoid full-zero scores on trending symbols.
    s_gap = 1.0 / (1.0 + gap_pct / 0.70)
    s_slope = 1.0 / (1.0 + slope_pct / 0.80)
    # Prefer moderate ATR (too low dead, too high turbulent).
    s_atr = math.exp(-abs(atr_pct - 0.90) / 0.90)
    # Prefer moderate local range, not dead and not explosive.
    s_range = math.exp(-abs(range_pct - 7.0) / 6.0)

    score = 0.35 * s_gap + 0.30 * s_slope + 0.20 * s_atr + 0.15 * s_range
    return float(max(0.0, min(1.0, score))), {
        "gap_pct": gap_pct,
        "slope_pct": slope_pct,
        "atr_pct": atr_pct,
        "range_pct": range_pct,
    }


def _exp_score(value: float, target: float, width: float) -> float:
    if width <= 0:
        return 0.0
    return float(math.exp(-abs(value - target) / width))


def _flat_side_scores_from_bars(c5: List[Candle], bars_1h: List[Candle], bars_4h: List[Candle]) -> dict:
    flat_score, flat_meta = _flat_score(c5)
    rows_1h = [[str(c.ts), str(c.o), str(c.h), str(c.l), str(c.c), str(c.v), "0"] for c in bars_1h[-96:]]
    rows_4h = [[str(c.ts), str(c.o), str(c.h), str(c.l), str(c.c), str(c.v), "0"] for c in bars_4h[-72:]]
    if len(rows_1h) < 40 or len(rows_4h) < 30:
        return {
            "flat_score": flat_score,
            "long_score": 0.0,
            "short_score": 0.0,
            "reason": "history_short",
            **flat_meta,
        }

    closes_1h = [float(r[4]) for r in rows_1h]
    highs_1h = [float(r[2]) for r in rows_1h]
    lows_1h = [float(r[3]) for r in rows_1h]
    cur = closes_1h[-1]
    if cur <= 0:
        return {
            "flat_score": flat_score,
            "long_score": 0.0,
            "short_score": 0.0,
            "reason": "invalid_price",
            **flat_meta,
        }

    ema_1h = _ema(closes_1h[-24:], 20)
    atr_1h = _atr_from_rows(rows_1h, 14)
    rsi_1h = _rsi(closes_1h, 14)
    support = min(lows_1h[-72:-1])
    resistance = max(highs_1h[-72:-1])
    range_pct = (resistance - support) / max(1e-12, cur) * 100.0
    dist_from_support_pct = (cur - support) / max(1e-12, support) * 100.0
    dist_from_res_pct = (resistance - cur) / max(1e-12, resistance) * 100.0
    close_vs_ema_pct = (cur - ema_1h) / max(1e-12, ema_1h) * 100.0 if math.isfinite(ema_1h) else float("nan")
    atr_1h_pct = atr_1h / max(1e-12, cur) * 100.0 if math.isfinite(atr_1h) else float("nan")

    closes_4h = [float(r[4]) for r in rows_4h]
    cur_4h = closes_4h[-1]
    ema_fast_4h = _ema(closes_4h[-20:], 20)
    ema_slow_4h = _ema(closes_4h[-50:], 50)
    ema_slow_4h_prev = _ema(closes_4h[:-6][-50:], 50) if len(closes_4h) >= 56 else float("nan")
    gap_4h_pct = abs(ema_fast_4h - ema_slow_4h) / max(1e-12, cur_4h) * 100.0 if math.isfinite(ema_fast_4h) and math.isfinite(ema_slow_4h) else float("nan")
    signed_slope_4h_pct = ((ema_slow_4h - ema_slow_4h_prev) / max(1e-12, abs(ema_slow_4h_prev))) * 100.0 if math.isfinite(ema_slow_4h_prev) else float("nan")
    slope_4h_pct = abs(signed_slope_4h_pct) if math.isfinite(signed_slope_4h_pct) else float("nan")
    atr_4h = _atr_from_rows(rows_4h, 14)
    atr_4h_pct = atr_4h / max(1e-12, cur_4h) * 100.0 if math.isfinite(atr_4h) else float("nan")

    if not all(
        math.isfinite(x)
        for x in (ema_1h, atr_1h, rsi_1h, close_vs_ema_pct, gap_4h_pct, slope_4h_pct, atr_4h_pct)
    ):
        return {
            "flat_score": flat_score,
            "long_score": 0.0,
            "short_score": 0.0,
            "reason": "nan_indicators",
            **flat_meta,
        }

    s_flat = flat_score
    s_range = _exp_score(range_pct, 10.0, 6.0)
    s_1h_atr = _exp_score(atr_1h_pct, 1.10, 0.80)
    s_long_support = _exp_score(dist_from_support_pct, 0.90, 0.90)
    s_long_ema = _exp_score(close_vs_ema_pct, -1.40, 0.90)
    s_long_rsi = _exp_score(rsi_1h, 38.0, 9.0)
    s_short_res = _exp_score(dist_from_res_pct, 0.90, 0.90)
    s_short_ema = _exp_score(close_vs_ema_pct, 0.60, 0.80)
    s_short_rsi = _exp_score(rsi_1h, 62.0, 9.0)

    regime_penalty = 1.0
    if gap_4h_pct > 3.4 or slope_4h_pct > 2.0:
        regime_penalty *= 0.50
    if atr_4h_pct < 0.45 or atr_4h_pct > 6.5:
        regime_penalty *= 0.60

    long_score = (
        0.32 * s_flat
        + 0.24 * s_long_support
        + 0.18 * s_long_ema
        + 0.16 * s_long_rsi
        + 0.10 * s_range
    ) * regime_penalty * (0.85 + 0.15 * s_1h_atr)
    short_score = (
        0.32 * s_flat
        + 0.24 * s_short_res
        + 0.18 * s_short_ema
        + 0.16 * s_short_rsi
        + 0.10 * s_range
    ) * regime_penalty * (0.85 + 0.15 * s_1h_atr)

    if close_vs_ema_pct < -3.2:
        long_score *= 0.22
    if close_vs_ema_pct > 0.8:
        long_score *= 0.55
    if dist_from_support_pct > 2.6:
        long_score *= 0.55
    if rsi_1h > 50.0:
        long_score *= 0.50
    if signed_slope_4h_pct < -1.2:
        long_score *= 0.65
    elif signed_slope_4h_pct < -0.6:
        long_score *= 0.82

    if close_vs_ema_pct > 2.2:
        short_score *= 0.55
    if close_vs_ema_pct < -0.6:
        short_score *= 0.45
    if dist_from_res_pct > 2.0:
        short_score *= 0.55
    if rsi_1h < 50.0:
        short_score *= 0.45
    if signed_slope_4h_pct > 0.4:
        short_score *= 0.45
    elif signed_slope_4h_pct > 0.0:
        short_score *= 0.70
    elif signed_slope_4h_pct < -0.8:
        short_score *= 1.08

    return {
        "flat_score": float(max(0.0, min(1.0, s_flat))),
        "long_score": float(max(0.0, min(1.0, long_score))),
        "short_score": float(max(0.0, min(1.0, short_score))),
        "range_pct": range_pct,
        "dist_from_support_pct": dist_from_support_pct,
        "dist_from_res_pct": dist_from_res_pct,
        "close_vs_ema_pct": close_vs_ema_pct,
        "rsi_1h": rsi_1h,
        "gap_4h_pct": gap_4h_pct,
        "slope_4h_pct": slope_4h_pct,
        "signed_slope_4h_pct": signed_slope_4h_pct,
        "atr_4h_pct": atr_4h_pct,
        **flat_meta,
    }


def _flat_side_scores(store: KlineStore) -> dict:
    return _flat_side_scores_from_bars(store.c5, store.c1h, store.c4h)


def _flat_side_scores_at_bar(store: KlineStore, i5: int) -> dict:
    if i5 < 0:
        return {"flat_score": 0.0, "long_score": 0.0, "short_score": 0.0, "reason": "no_index"}
    i5 = min(i5, len(store.c5) - 1)
    i1h = min(len(store.c1h) - 1, i5 // 12)
    i4h = min(len(store.c4h) - 1, i5 // 48)
    if i1h < 0 or i4h < 0:
        return {"flat_score": 0.0, "long_score": 0.0, "short_score": 0.0, "reason": "history_short"}
    return _flat_side_scores_from_bars(store.c5[: i5 + 1], store.c1h[: i1h + 1], store.c4h[: i4h + 1])


def _csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip() for x in str(raw).split(",") if x.strip()}


def _regime_at_bar(store: KlineStore, i: int) -> str:
    """Classify regime at current bar index: 'flat' or 'trend'."""
    if i < 260:
        return "trend"
    c = [float(x.c) for x in store.c5[: i + 1]]
    h = [float(x.h) for x in store.c5[: i + 1]]
    l = [float(x.l) for x in store.c5[: i + 1]]
    cur = c[-1]
    if cur <= 0:
        return "trend"

    ef = _ema(c[-90:], 20)
    es = _ema(c[-140:], 50)
    atr = _atr_from_candles(store.c5[max(0, i - 180): i + 1], 14)
    if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(atr) and atr > 0):
        return "trend"

    gap_pct = abs(ef - es) / cur * 100.0
    atr_pct = atr / cur * 100.0
    es_prev = _ema(c[-190:-40], 50) if len(c) >= 190 else float("nan")
    slope_pct = abs((es - es_prev) / max(1e-12, abs(es_prev))) * 100.0 if math.isfinite(es_prev) else 999.0

    # Conservative flat definition; otherwise trend.
    is_flat = (gap_pct <= 0.55) and (slope_pct <= 0.55) and (0.20 <= atr_pct <= 2.40)
    return "flat" if is_flat else "trend"


def _allocator_risk_mult(strategy_name: str, regime: str) -> float:
    """Dynamic risk multiplier for regime allocator backtests."""
    st = str(strategy_name or "").strip().lower()
    rg = str(regime or "trend").strip().lower()
    if st in {"inplay_breakout"}:
        if rg == "flat":
            return float(os.getenv("ALLOC_BREAKOUT_FLAT_MULT", "0.85"))
        return float(os.getenv("ALLOC_BREAKOUT_TREND_MULT", "1.10"))
    if st in {"btc_eth_midterm_pullback"}:
        if rg == "flat":
            return float(os.getenv("ALLOC_MIDTERM_FLAT_MULT", "1.15"))
        return float(os.getenv("ALLOC_MIDTERM_TREND_MULT", "0.95"))
    return 1.0


def _breakout_quality_score(
    *,
    chase_pct: float,
    late_pct: float,
    spread_pct: float,
    pullback_pct: float,
    max_chase_pct: float,
    max_late_pct: float,
    max_spread_pct: float,
    min_pullback_pct: float,
) -> float:
    chase_cap = max(0.01, float(max_chase_pct or 0.01))
    late_cap = max(0.01, float(max_late_pct or 0.01))
    spread_cap = max(0.01, float(max_spread_pct or 0.01))
    pull_thr = max(0.01, float(min_pullback_pct or 0.01))

    chase_score = max(0.0, min(1.0, 1.0 - (max(0.0, chase_pct) / chase_cap)))
    late_score = max(0.0, min(1.0, 1.0 - (max(0.0, late_pct) / late_cap)))
    spread_score = max(0.0, min(1.0, 1.0 - (max(0.0, spread_pct) / spread_cap)))
    pull_score = max(0.0, min(1.0, max(0.0, pullback_pct) / (pull_thr * 1.8)))
    return (
        0.30 * spread_score
        + 0.25 * chase_score
        + 0.25 * late_score
        + 0.20 * pull_score
    )


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

    def _pick_best_cached_rows() -> tuple[Optional[Path], Optional[list]]:
        candidates = sorted(
            cache_dir.glob(f"{symbol}_5_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return None, None
        best_path = None
        best_rows = None
        best_key = None
        for cand in candidates:
            try:
                cand_rows = json.loads(cand.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not cand_rows:
                continue

            def _row_ts_ms(item) -> int:
                if isinstance(item, dict):
                    return int(float(item.get("ts", 0)))
                if isinstance(item, (list, tuple)) and item:
                    return int(float(item[0]))
                return 0

            first_ts = _row_ts_ms(cand_rows[0])
            last_ts = _row_ts_ms(cand_rows[-1])
            if first_ts <= 0 or last_ts <= 0:
                continue
            overlap_ms = max(0, min(last_ts, end_ms) - max(first_ts, start_ms))
            coverage_ms = max(0, last_ts - first_ts)
            key = (overlap_ms, coverage_ms, len(cand_rows), cand.stat().st_mtime)
            if best_key is None or key > best_key:
                best_key = key
                best_path = cand
                best_rows = cand_rows
        return best_path, best_rows

    rows: List[List[float]]
    cache_only = str(os.getenv("BACKTEST_CACHE_ONLY", "0")).strip().lower() in {"1", "true", "yes", "on"}
    if fname.exists():
        rows = json.loads(fname.read_text(encoding="utf-8"))
    elif cache_only:
        best_path, best_rows = _pick_best_cached_rows()
        if best_path is None or best_rows is None:
            raise FileNotFoundError(f"No cached slice found for {symbol}")
        print(f"[cache-only] {symbol}: using cached slice {best_path.name}")
        rows = best_rows
    else:
        try:
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
        except Exception as e:
            use_cache_fallback = str(os.getenv("BACKTEST_CACHE_FALLBACK_ENABLE", "1")).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if not use_cache_fallback:
                raise
            best_path, best_rows = _pick_best_cached_rows()
            if best_path is None or best_rows is None:
                raise
            print(
                f"[cache-fallback] {symbol}: REST fetch failed ({e}); using cached slice {best_path.name}"
            )
            rows = best_rows

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


def _parse_symbol_csv(raw: str) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in (raw or "").split(","):
        sym = str(item or "").strip().upper()
        if not sym:
            continue
        if sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _fallback_auto_symbols(*, top_n: int, exclude: List[str]) -> List[str]:
    """
    Fallback for auto symbol selection when Bybit API is temporarily unavailable.

    Sources (priority):
    1) env AUTO_SYMBOLS_FALLBACK="BTCUSDT,ETHUSDT,..."
    2) file path from env AUTO_SYMBOLS_FALLBACK_FILE
    3) docs/auto_symbols_fallback.txt in repo root
    """
    ex = {x.strip().upper() for x in exclude if x.strip()}
    env_symbols = _parse_symbol_csv(os.getenv("AUTO_SYMBOLS_FALLBACK", ""))
    if env_symbols:
        return [s for s in env_symbols if s not in ex][: max(1, int(top_n))]

    fallback_file = Path(
        os.getenv("AUTO_SYMBOLS_FALLBACK_FILE", "docs/auto_symbols_fallback.txt")
    )
    try:
        if fallback_file.exists():
            txt = fallback_file.read_text(encoding="utf-8", errors="ignore")
            file_symbols = _parse_symbol_csv(txt.replace("\n", ","))
            if file_symbols:
                return [s for s in file_symbols if s not in ex][: max(1, int(top_n))]
    except Exception:
        pass
    return []


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
    fallback = _fallback_auto_symbols(top_n=top_n, exclude=exclude)
    try:
        js = requests.get(url, params=params, timeout=20).json()
    except Exception as e:
        if fallback:
            print(f"[auto-symbols] API unavailable, fallback used ({len(fallback)} symbols): {e}")
            return fallback
        raise
    if js.get("retCode") != 0:
        if fallback:
            print(
                f"[auto-symbols] API retCode={js.get('retCode')} fallback used ({len(fallback)} symbols)"
            )
            return fallback
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
    picked = [sym for _, sym in rows[: max(1, int(top_n))]]
    if picked:
        return picked
    if fallback:
        print(f"[auto-symbols] API returned empty universe, fallback used ({len(fallback)} symbols)")
        return fallback
    return []
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
        default="bounce,bounce_v2,range,inplay,inplay_breakout,pump_fade,retest_levels,momentum,trend_pullback,trend_pullback_be_trail,sr_break_retest_volume_v1,trend_breakout,vol_breakout,adaptive_range_short,smart_grid,smart_grid_v2,smart_grid_v3,range_bounce,donchian_breakout,btc_eth_midterm_pullback,btc_eth_vol_expansion,btc_eth_trend_rsi_reentry,trendline_break_retest,btc_eth_trend_follow,trendline_break_retest_v2,flat_bounce_v2,flat_bounce_v3,btc_eth_trend_follow_v2,trendline_break_retest_v3,trendline_break_retest_v4,structure_shift_v1,structure_shift_v2,tv_atr_trend_v1,tv_atr_trend_v2,triple_screen_v132,triple_screen_v132b,btc_regime_retest_v1,btc_cycle_pullback_v1,btc_macro_cycle_v1,btc_cycle_continuation_v1,btc_cycle_level_target_v2,btc_daily_level_reclaim_v1,btc_swing_zone_reclaim_v1,btc_weekly_zone_reclaim_v2,btc_regime_flip_continuation_v1,btc_sloped_reclaim_v1,alt_range_reclaim_v1,alt_resistance_fade_v1,alt_sloped_channel_v1,alt_inplay_breakdown_v1,micro_scalper_v1,alt_support_reclaim_v1",
        help="Comma-separated strategies (priority order): bounce,bounce_v2,range,inplay,inplay_pullback,inplay_breakout,pump_fade,retest_levels,momentum,trend_pullback,trend_pullback_be_trail,sr_break_retest_volume_v1,trend_breakout,vol_breakout,adaptive_range_short,smart_grid,smart_grid_v2,smart_grid_v3,range_bounce,donchian_breakout,btc_eth_midterm_pullback,btc_eth_vol_expansion,btc_eth_trend_rsi_reentry,trendline_break_retest,btc_eth_trend_follow,trendline_break_retest_v2,flat_bounce_v2,flat_bounce_v3,btc_eth_trend_follow_v2,trendline_break_retest_v3,trendline_break_retest_v4,structure_shift_v1,structure_shift_v2,tv_atr_trend_v1,tv_atr_trend_v2,triple_screen_v132,triple_screen_v132b,btc_regime_retest_v1,btc_cycle_pullback_v1,btc_macro_cycle_v1,btc_cycle_continuation_v1,btc_cycle_level_target_v2,btc_daily_level_reclaim_v1,btc_swing_zone_reclaim_v1,btc_weekly_zone_reclaim_v2,btc_regime_flip_continuation_v1,btc_sloped_reclaim_v1,alt_range_reclaim_v1,alt_resistance_fade_v1,alt_sloped_channel_v1",
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
    ap.add_argument("--news-events-csv", default="", help="Optional normalized news events CSV for deterministic macro blackout gating")
    ap.add_argument("--news-policy-json", default="", help="Optional news policy JSON")
    args = ap.parse_args()
    regime_router_enable = str(os.getenv("REGIME_ROUTER_ENABLE", "0")).strip().lower() in {"1", "true", "yes", "on"}
    regime_flat_set = _csv_set("REGIME_FLAT_STRATEGIES", "smart_grid,smart_grid_v2,smart_grid_v3,range_bounce")
    regime_trend_set = _csv_set(
        "REGIME_TREND_STRATEGIES",
        "inplay_breakout,btc_eth_midterm_pullback,trend_breakout,trend_pullback,trend_pullback_be_trail,sr_break_retest_volume_v1,btc_eth_trend_follow",
    )
    bt_breakout_quality_enable = str(os.getenv("BT_BREAKOUT_QUALITY_ENABLE", "0")).strip().lower() in {"1", "true", "yes", "on"}
    bt_breakout_quality_min_score = float(os.getenv("BT_BREAKOUT_QUALITY_MIN_SCORE", "0.58"))
    bt_breakout_max_chase_pct = float(os.getenv("BREAKOUT_MAX_CHASE_PCT", "0.15"))
    bt_breakout_max_late_pct = float(os.getenv("BREAKOUT_MAX_LATE_VS_REF_PCT", "0.35"))
    bt_breakout_max_spread_pct = float(os.getenv("BREAKOUT_MAX_SPREAD_PCT", "0.20"))
    bt_breakout_min_pullback_pct = float(os.getenv("BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT", "0.08"))
    bt_breakout_ref_lookback = max(5, int(os.getenv("BREAKOUT_REF_LOOKBACK_BARS", "20")))
    bt_quality_checked = 0
    bt_quality_skipped = 0
    allocator_enable = str(os.getenv("ALLOCATOR_ENABLE", "0")).strip().lower() in {"1", "true", "yes", "on"}
    allocator_mult_min = float(os.getenv("ALLOCATOR_MULT_MIN", "0.60"))
    allocator_mult_max = float(os.getenv("ALLOCATOR_MULT_MAX", "1.40"))
    news_events = load_news_events(args.news_events_csv) if args.news_events_csv else []
    news_policy = load_news_policy(args.news_policy_json) if args.news_policy_json else {}
    news_blocked_signals = 0
    news_blocked_by_strategy: Dict[str, int] = defaultdict(int)

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    exclude = [s.strip() for s in (args.exclude_symbols or "").split(",") if s.strip()]
    if args.auto_symbols or not symbols:
        symbols = _select_auto_symbols(base=args.bybit_base, min_volume_usd=args.min_volume_usd, top_n=args.top_n, exclude=exclude)
    if not symbols:
        raise SystemExit("No symbols selected. Provide --symbols or relax --min_volume_usd/--top_n.")

    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    allowed = {"bounce", "bounce_v2", "range", "inplay", "inplay_pullback", "inplay_breakout", "pump_fade", "retest_levels", "momentum", "trend_pullback", "trend_pullback_be_trail", "sr_break_retest_volume_v1", "trend_breakout", "vol_breakout", "adaptive_range_short", "smart_grid", "smart_grid_v2", "smart_grid_v3", "range_bounce", "donchian_breakout", "btc_eth_midterm_pullback", "btc_eth_vol_expansion", "btc_eth_trend_rsi_reentry", "trendline_break_retest", "btc_eth_trend_follow", "trendline_break_retest_v2", "flat_bounce_v2", "flat_bounce_v3", "btc_eth_trend_follow_v2", "trendline_break_retest_v3", "trendline_break_retest_v4", "structure_shift_v1", "structure_shift_v2", "tv_atr_trend_v1", "tv_atr_trend_v2", "triple_screen_v132", "triple_screen_v132b", "btc_regime_retest_v1", "btc_cycle_pullback_v1", "btc_macro_cycle_v1", "btc_cycle_continuation_v1", "btc_cycle_level_target_v2", "btc_daily_level_reclaim_v1", "btc_swing_zone_reclaim_v1", "btc_weekly_zone_reclaim_v2", "btc_regime_flip_continuation_v1", "btc_sloped_reclaim_v1", "alt_range_reclaim_v1", "alt_resistance_fade_v1", "alt_sloped_channel_v1", "alt_inplay_breakdown_v1", "micro_scalper_v1", "alt_support_reclaim_v1"}
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

    if any(s in strategies for s in ("alt_range_reclaim_v1", "alt_resistance_fade_v1", "alt_sloped_channel_v1")):
        min_cov_frac = float(os.getenv("FLAT_MIN_COVERAGE_FRAC", "0.85"))
        requested_span_ms = max(1, (end_ts - start_ts) * 1000)
        dropped: List[str] = []
        kept: List[str] = []
        for sym in symbols:
            c5 = stores[sym].c5
            if not c5:
                dropped.append(sym)
                continue
            coverage_ms = max(0, c5[-1].ts - c5[0].ts)
            cov_frac = coverage_ms / requested_span_ms
            if cov_frac + 1e-9 < min_cov_frac:
                dropped.append(sym)
            else:
                kept.append(sym)
        if kept and dropped:
            symbols = kept
            stores = {k: v for k, v in stores.items() if k in symbols}
            print(f"[flat-coverage] kept={len(symbols)} dropped={len(dropped)} min_cov_frac={min_cov_frac:.2f}")
            print(f"[flat-coverage] dropped_symbols={','.join(dropped)}")

    # Optional flat-regime symbol prefilter for mean-reversion arms.
    if str(os.getenv("FLAT_SYMBOL_FILTER_ENABLE", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        if any(s in strategies for s in ("smart_grid", "smart_grid_v2", "smart_grid_v3", "range_bounce")):
            min_score = float(os.getenv("FLAT_SYMBOL_MIN_SCORE", "0.58"))
            keep_top_n = max(1, int(os.getenv("FLAT_SYMBOL_KEEP_TOP_N", "3")))
            scored: List[tuple[str, float, dict]] = []
            keep: List[str] = []
            for sym in symbols:
                score, meta = _flat_score(stores[sym].c5)
                scored.append((sym, score, meta))
                if score >= min_score:
                    keep.append(sym)
            if keep:
                symbols = keep
                stores = {k: v for k, v in stores.items() if k in symbols}
                print(f"[flat-filter] kept={len(symbols)} min_score={min_score:.2f} symbols={','.join(symbols)}")
            else:
                scored.sort(key=lambda x: x[1], reverse=True)
                symbols = [s for s, _, _ in scored[:keep_top_n]]
                stores = {k: v for k, v in stores.items() if k in symbols}
                dbg = ", ".join(f"{s}:{sc:.3f}" for s, sc, _ in scored[: min(len(scored), 8)])
                print(f"[flat-filter] no symbols passed min_score={min_score:.2f}; keep_top_n={keep_top_n} => {','.join(symbols)}")
                print(f"[flat-filter] top_scores: {dbg}")

    if str(os.getenv("FLAT_ARCHETYPE_FILTER_ENABLE", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        if any(s in strategies for s in ("alt_range_reclaim_v1", "alt_resistance_fade_v1", "alt_sloped_channel_v1")):
            scored_meta: Dict[str, dict] = {sym: _flat_side_scores(stores[sym]) for sym in symbols}

            if "alt_range_reclaim_v1" in strategies:
                min_score = float(os.getenv("ARR1_DYNAMIC_MIN_SCORE", "0.42"))
                top_n = max(1, int(os.getenv("ARR1_DYNAMIC_TOP_N", "2")))
                keep_top_n = max(top_n, int(os.getenv("ARR1_DYNAMIC_KEEP_TOP_N", str(top_n))))
                ranked = sorted(symbols, key=lambda s: scored_meta[s]["long_score"], reverse=True)
                keep = [s for s in ranked if scored_meta[s]["long_score"] >= min_score][:top_n]
                if not keep:
                    keep = ranked[:keep_top_n]
                os.environ["ARR1_SYMBOL_ALLOWLIST"] = ",".join(keep)
                dbg = ", ".join(
                    f"{s}:{scored_meta[s]['long_score']:.3f}"
                    for s in ranked[: min(len(ranked), 8)]
                )
                print(f"[flat-archetype] ARR1 allow={','.join(keep)} min_score={min_score:.2f}")
                print(f"[flat-archetype] ARR1 top_long_scores: {dbg}")

            if "alt_resistance_fade_v1" in strategies:
                min_score = float(os.getenv("ARF1_DYNAMIC_MIN_SCORE", "0.42"))
                top_n = max(1, int(os.getenv("ARF1_DYNAMIC_TOP_N", "2")))
                keep_top_n = max(top_n, int(os.getenv("ARF1_DYNAMIC_KEEP_TOP_N", str(top_n))))
                ranked = sorted(symbols, key=lambda s: scored_meta[s]["short_score"], reverse=True)
                keep = [s for s in ranked if scored_meta[s]["short_score"] >= min_score][:top_n]
                if not keep:
                    keep = ranked[:keep_top_n]
                os.environ["ARF1_SYMBOL_ALLOWLIST"] = ",".join(keep)
                dbg = ", ".join(
                    f"{s}:{scored_meta[s]['short_score']:.3f}"
                    for s in ranked[: min(len(ranked), 8)]
                )
                print(f"[flat-archetype] ARF1 allow={','.join(keep)} min_score={min_score:.2f}")
                print(f"[flat-archetype] ARF1 top_short_scores: {dbg}")

            if "alt_sloped_channel_v1" in strategies:
                min_long = float(os.getenv("ASC1_DYNAMIC_LONG_MIN_SCORE", "0.34"))
                min_short = float(os.getenv("ASC1_DYNAMIC_SHORT_MIN_SCORE", "0.08"))
                top_long = max(1, int(os.getenv("ASC1_DYNAMIC_LONG_TOP_N", "3")))
                top_short = max(1, int(os.getenv("ASC1_DYNAMIC_SHORT_TOP_N", "2")))
                ranked_long = sorted(symbols, key=lambda s: scored_meta[s]["long_score"], reverse=True)
                ranked_short = sorted(symbols, key=lambda s: scored_meta[s]["short_score"], reverse=True)
                keep_long = [s for s in ranked_long if scored_meta[s]["long_score"] >= min_long][:top_long]
                keep_short = [s for s in ranked_short if scored_meta[s]["short_score"] >= min_short][:top_short]
                keep = []
                for s in keep_long + keep_short:
                    if s not in keep:
                        keep.append(s)
                if not keep:
                    keep = ranked_long[:top_long]
                os.environ["ASC1_SYMBOL_ALLOWLIST"] = ",".join(keep)
                dbg_long = ", ".join(f"{s}:{scored_meta[s]['long_score']:.3f}" for s in ranked_long[: min(len(ranked_long), 6)])
                dbg_short = ", ".join(f"{s}:{scored_meta[s]['short_score']:.3f}" for s in ranked_short[: min(len(ranked_short), 6)])
                print(f"[flat-archetype] ASC1 allow={','.join(keep)} long_min={min_long:.2f} short_min={min_short:.2f}")
                print(f"[flat-archetype] ASC1 top_long_scores: {dbg_long}")
                print(f"[flat-archetype] ASC1 top_short_scores: {dbg_short}")

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
    trend_pullback_be_trail = {sym: TrendPullbackBETrailStrategy() for sym in symbols} if "trend_pullback_be_trail" in strategies else {}
    sr_break_retest_volume_v1 = {sym: SRBreakRetestVolumeV1Strategy() for sym in symbols} if "sr_break_retest_volume_v1" in strategies else {}
    trend_breakout = {sym: TrendRegimeBreakoutStrategy() for sym in symbols} if "trend_breakout" in strategies else {}
    vol_breakout = {sym: VolatilityBreakoutStrategy() for sym in symbols} if "vol_breakout" in strategies else {}
    adaptive_range_short = {sym: AdaptiveRangeShortStrategy() for sym in symbols} if "adaptive_range_short" in strategies else {}
    smart_grid = {sym: SmartGridStrategy() for sym in symbols} if "smart_grid" in strategies else {}
    smart_grid_v2 = {sym: SmartGridV2Strategy() for sym in symbols} if "smart_grid_v2" in strategies else {}
    smart_grid_v3 = {sym: SmartGridV3Strategy() for sym in symbols} if "smart_grid_v3" in strategies else {}
    range_bounce = {sym: RangeBounceStrategy() for sym in symbols} if "range_bounce" in strategies else {}
    donchian_breakout = {sym: DonchianBreakoutStrategy() for sym in symbols} if "donchian_breakout" in strategies else {}
    btc_eth_midterm_pullback = {sym: BTCETHMidtermPullbackStrategy() for sym in symbols} if "btc_eth_midterm_pullback" in strategies else {}
    btc_eth_vol_expansion = {sym: BTCETHVolExpansionStrategy() for sym in symbols} if "btc_eth_vol_expansion" in strategies else {}
    btc_eth_trend_rsi_reentry = {sym: BTCETHTrendRSIReentryStrategy() for sym in symbols} if "btc_eth_trend_rsi_reentry" in strategies else {}
    trendline_break_retest = {sym: TrendlineBreakRetestStrategy() for sym in symbols} if "trendline_break_retest" in strategies else {}
    btc_eth_trend_follow = {sym: BTCETHTrendFollowStrategy() for sym in symbols} if "btc_eth_trend_follow" in strategies else {}
    trendline_break_retest_v2 = {sym: TrendlineBreakRetestV2Strategy() for sym in symbols} if "trendline_break_retest_v2" in strategies else {}
    flat_bounce_v2 = {sym: FlatBounceV2Strategy() for sym in symbols} if "flat_bounce_v2" in strategies else {}
    flat_bounce_v3 = {sym: FlatBounceV3Strategy() for sym in symbols} if "flat_bounce_v3" in strategies else {}
    btc_eth_trend_follow_v2 = {sym: BTCETHTrendFollowV2Strategy() for sym in symbols} if "btc_eth_trend_follow_v2" in strategies else {}
    trendline_break_retest_v3 = {sym: TrendlineBreakRetestV3Strategy() for sym in symbols} if "trendline_break_retest_v3" in strategies else {}
    trendline_break_retest_v4 = {sym: TrendlineBreakRetestV4Strategy() for sym in symbols} if "trendline_break_retest_v4" in strategies else {}
    structure_shift_v1 = {sym: StructureShiftV1Strategy() for sym in symbols} if "structure_shift_v1" in strategies else {}
    structure_shift_v2 = {sym: StructureShiftV2Strategy() for sym in symbols} if "structure_shift_v2" in strategies else {}
    tv_atr_trend_v1 = {sym: TVATRTrendV1Strategy() for sym in symbols} if "tv_atr_trend_v1" in strategies else {}
    tv_atr_trend_v2 = {sym: TVATRTrendV2Strategy() for sym in symbols} if "tv_atr_trend_v2" in strategies else {}
    triple_screen_v132 = {sym: TripleScreenV132Strategy() for sym in symbols} if "triple_screen_v132" in strategies else {}
    triple_screen_v132b = {sym: TripleScreenV132BStrategy() for sym in symbols} if "triple_screen_v132b" in strategies else {}
    btc_regime_retest_v1 = {sym: BTCRegimeRetestV1Strategy() for sym in symbols} if "btc_regime_retest_v1" in strategies else {}
    btc_cycle_pullback_v1 = {sym: BTCCyclePullbackV1Strategy() for sym in symbols} if "btc_cycle_pullback_v1" in strategies else {}
    btc_macro_cycle_v1 = {sym: BTCMacroCycleV1Strategy() for sym in symbols} if "btc_macro_cycle_v1" in strategies else {}
    btc_cycle_continuation_v1 = {sym: BTCCycleContinuationV1Strategy() for sym in symbols} if "btc_cycle_continuation_v1" in strategies else {}
    btc_cycle_level_target_v2 = {sym: BTCCycleLevelTargetV2Strategy() for sym in symbols} if "btc_cycle_level_target_v2" in strategies else {}
    btc_daily_level_reclaim_v1 = {sym: BTCDailyLevelReclaimV1Strategy() for sym in symbols} if "btc_daily_level_reclaim_v1" in strategies else {}
    btc_swing_zone_reclaim_v1 = {sym: BTCSwingZoneReclaimV1Strategy() for sym in symbols} if "btc_swing_zone_reclaim_v1" in strategies else {}
    btc_weekly_zone_reclaim_v2 = {sym: BTCWeeklyZoneReclaimV2Strategy() for sym in symbols} if "btc_weekly_zone_reclaim_v2" in strategies else {}
    btc_regime_flip_continuation_v1 = {sym: BTCRegimeFlipContinuationV1Strategy() for sym in symbols} if "btc_regime_flip_continuation_v1" in strategies else {}
    btc_sloped_reclaim_v1 = {sym: BTCSlopedReclaimV1Strategy() for sym in symbols} if "btc_sloped_reclaim_v1" in strategies else {}
    alt_range_reclaim_v1 = {sym: AltRangeReclaimV1Strategy() for sym in symbols} if "alt_range_reclaim_v1" in strategies else {}
    alt_resistance_fade_v1 = {sym: AltResistanceFadeV1Strategy() for sym in symbols} if "alt_resistance_fade_v1" in strategies else {}
    alt_sloped_channel_v1 = {sym: AltSlopedChannelV1Strategy() for sym in symbols} if "alt_sloped_channel_v1" in strategies else {}
    alt_inplay_breakdown_v1 = {sym: AltInplayBreakdownV1Strategy() for sym in symbols} if "alt_inplay_breakdown_v1" in strategies else {}
    micro_scalper_v1 = {sym: MicroScalperV1Strategy() for sym in symbols} if "micro_scalper_v1" in strategies else {}
    alt_support_reclaim_v1 = {sym: AltSupportReclaimV1Strategy() for sym in symbols} if "alt_support_reclaim_v1" in strategies else {}
    flat_archetype_router_enable = str(os.getenv("FLAT_ARCHETYPE_ROUTER_ENABLE", "0")).strip().lower() in {"1", "true", "yes", "on"}
    flat_archetype_long_min_score = float(os.getenv("ARR1_BAR_MIN_SCORE", "0.40"))
    flat_archetype_short_min_score = float(os.getenv("ARF1_BAR_MIN_SCORE", "0.08"))
    flat_archetype_long_top_n = max(1, int(os.getenv("ARR1_BAR_TOP_N", "2")))
    flat_archetype_short_top_n = max(1, int(os.getenv("ARF1_BAR_TOP_N", "1")))
    flat_archetype_cache: Dict[int, dict] = {}

    def selector(sym: str, store: KlineStore, ts_ms: int, last_price: float):
        # IMPORTANT: first-match wins (priority = order in --strategies)
        nonlocal bt_quality_checked, bt_quality_skipped, news_blocked_signals
        i_cur = getattr(store, 'i5', getattr(store, 'i', None))
        regime = "trend"
        if regime_router_enable and i_cur is not None:
            try:
                regime = _regime_at_bar(store, int(i_cur))
            except Exception:
                regime = "trend"
        flat_arch_state = None
        if flat_archetype_router_enable and i_cur is not None and any(st in strategies for st in ("alt_range_reclaim_v1", "alt_resistance_fade_v1", "alt_sloped_channel_v1")):
            bar_key = int(i_cur)
            flat_arch_state = flat_archetype_cache.get(bar_key)
            if flat_arch_state is None:
                metas = {s: _flat_side_scores_at_bar(stores[s], bar_key) for s in symbols}
                long_rank = sorted(symbols, key=lambda s: metas[s].get("long_score", 0.0), reverse=True)
                short_rank = sorted(symbols, key=lambda s: metas[s].get("short_score", 0.0), reverse=True)
                long_keep = [s for s in long_rank if metas[s].get("long_score", 0.0) >= flat_archetype_long_min_score][:flat_archetype_long_top_n]
                short_keep = [s for s in short_rank if metas[s].get("short_score", 0.0) >= flat_archetype_short_min_score][:flat_archetype_short_top_n]
                if not long_keep:
                    long_keep = long_rank[:flat_archetype_long_top_n]
                if not short_keep:
                    short_keep = short_rank[:flat_archetype_short_top_n]
                flat_arch_state = {
                    "long_keep": set(long_keep),
                    "short_keep": set(short_keep),
                }
                flat_archetype_cache[bar_key] = flat_arch_state
        for st in strategies:
            if regime_router_enable:
                if regime == "flat" and st not in regime_flat_set:
                    continue
                if regime == "trend" and st not in regime_trend_set:
                    continue
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
                if sig is not None and bt_breakout_quality_enable:
                    i = getattr(store, 'i5', getattr(store, 'i', None))
                    if i is not None and int(i) > 3:
                        i = int(i)
                        lo = max(0, i - bt_breakout_ref_lookback)
                        seg = list(store.c5[lo:i])
                        if seg:
                            highs = [float(b.h) for b in seg]
                            lows = [float(b.l) for b in seg]
                            ref_hi = max(highs) if highs else float(last_price)
                            ref_lo = min(lows) if lows else float(last_price)
                            entry = float(getattr(sig, "entry", last_price))
                            px = float(last_price)
                            chase_pct = abs((px - entry) / max(1e-12, entry)) * 100.0
                            if str(getattr(sig, "side", "")).lower() == "long":
                                base_px = max(entry, px)
                                late_pct = ((base_px - ref_hi) / max(1e-12, ref_hi)) * 100.0
                                pullback_pct = ((ref_hi - px) / max(1e-12, ref_hi)) * 100.0
                            else:
                                base_px = min(entry, px)
                                late_pct = ((ref_lo - base_px) / max(1e-12, ref_lo)) * 100.0
                                pullback_pct = ((px - ref_lo) / max(1e-12, ref_lo)) * 100.0
                            # Backtest does not model live spread directly; use slippage as conservative proxy.
                            spread_pct = float(args.slippage_bps) / 100.0
                            q_score = _breakout_quality_score(
                                chase_pct=chase_pct,
                                late_pct=late_pct,
                                spread_pct=spread_pct,
                                pullback_pct=pullback_pct,
                                max_chase_pct=bt_breakout_max_chase_pct,
                                max_late_pct=bt_breakout_max_late_pct,
                                max_spread_pct=bt_breakout_max_spread_pct,
                                min_pullback_pct=bt_breakout_min_pullback_pct,
                            )
                            bt_quality_checked += 1
                            if q_score < bt_breakout_quality_min_score:
                                bt_quality_skipped += 1
                                sig = None
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
            elif st == "trend_pullback_be_trail":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = trend_pullback_be_trail[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "sr_break_retest_volume_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = sr_break_retest_volume_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
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
            elif st == "smart_grid_v2":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = smart_grid_v2[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "smart_grid_v3":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = smart_grid_v3[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
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
            elif st == "btc_regime_retest_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_regime_retest_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_cycle_pullback_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_cycle_pullback_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_macro_cycle_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_macro_cycle_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_cycle_continuation_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_cycle_continuation_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_cycle_level_target_v2":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_cycle_level_target_v2[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_daily_level_reclaim_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_daily_level_reclaim_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_swing_zone_reclaim_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_swing_zone_reclaim_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_weekly_zone_reclaim_v2":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_weekly_zone_reclaim_v2[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_regime_flip_continuation_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_regime_flip_continuation_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_sloped_reclaim_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_sloped_reclaim_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "alt_range_reclaim_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                if flat_arch_state is not None and sym not in flat_arch_state["long_keep"]:
                    continue
                bar = store.c5[int(i)]
                sig = alt_range_reclaim_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "alt_resistance_fade_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                if flat_arch_state is not None and sym not in flat_arch_state["short_keep"]:
                    continue
                bar = store.c5[int(i)]
                sig = alt_resistance_fade_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "alt_sloped_channel_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                if flat_arch_state is not None and sym not in (flat_arch_state["long_keep"] | flat_arch_state["short_keep"]):
                    continue
                bar = store.c5[int(i)]
                sig = alt_sloped_channel_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "alt_inplay_breakdown_v1":
                sig = alt_inplay_breakdown_v1[sym].signal(store, ts_ms, last_price)
            elif st == "micro_scalper_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = micro_scalper_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "alt_support_reclaim_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = alt_support_reclaim_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
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
            elif st == "trendline_break_retest":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = trendline_break_retest[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_eth_trend_follow":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_eth_trend_follow[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "trendline_break_retest_v2":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = trendline_break_retest_v2[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "flat_bounce_v2":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = flat_bounce_v2[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "flat_bounce_v3":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = flat_bounce_v3[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "btc_eth_trend_follow_v2":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = btc_eth_trend_follow_v2[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "trendline_break_retest_v3":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = trendline_break_retest_v3[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "trendline_break_retest_v4":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = trendline_break_retest_v4[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "structure_shift_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = structure_shift_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "structure_shift_v2":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = structure_shift_v2[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "tv_atr_trend_v1":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = tv_atr_trend_v1[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "tv_atr_trend_v2":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = tv_atr_trend_v2[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "triple_screen_v132":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = triple_screen_v132[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            elif st == "triple_screen_v132b":
                i = getattr(store, 'i5', getattr(store, 'i', None))
                if i is None:
                    raise AttributeError('KlineStore missing current index (expected i5)')
                bar = store.c5[int(i)]
                sig = triple_screen_v132b[sym].maybe_signal(store, ts_ms, bar.o, bar.h, bar.l, bar.c, bar.v)
            else:
                sig = None
            if sig is not None:
                if allocator_enable:
                    try:
                        strategy_name = str(getattr(sig, "strategy", st) or st)
                        rm = _allocator_risk_mult(strategy_name, regime)
                        rm = max(float(allocator_mult_min), min(float(allocator_mult_max), float(rm)))
                        setattr(sig, "risk_mult", float(rm))
                    except Exception:
                        pass
                st_name = str(getattr(sig, "strategy", st) or st)
                if news_events:
                    blocked, _reason = is_news_blocked(
                        symbol=sym,
                        ts_utc=int(ts_ms // 1000),
                        strategy_name=st_name,
                        events=news_events,
                        policy=news_policy,
                    )
                    if blocked:
                        news_blocked_signals += 1
                        news_blocked_by_strategy[st_name] += 1
                        continue
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
            "trades","net_pnl","profit_factor","winrate","avg_win","avg_loss","max_drawdown","news_blocked_signals"
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
            news_blocked_signals,
        ])

    if news_events:
        news_stats_path = out_dir / "news_blocked_by_strategy.csv"
        with news_stats_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["strategy", "blocked_signals"])
            for strategy_name, count in sorted(news_blocked_by_strategy.items()):
                w.writerow([strategy_name, count])

    print(f"Saved portfolio run to: {out_dir}")
    print(f"  trades:   {trades_path}")
    print(f"  summary:  {summary_path}")
    if bt_breakout_quality_enable and bt_quality_checked > 0:
        print(
            f"  breakout_quality: checked={bt_quality_checked} "
            f"skipped={bt_quality_skipped} pass_rate={(100.0 * (bt_quality_checked - bt_quality_skipped) / max(1, bt_quality_checked)):.1f}% "
            f"min_score={bt_breakout_quality_min_score:.2f}"
        )
    if "pump_fade" in strategies and pump_fade:
        pf_diag = _write_pump_fade_diagnostics(out_dir, pump_fade)
        if pf_diag is not None:
            print(f"  pf_diag:  {pf_diag}")


if __name__ == "__main__":
    main()
