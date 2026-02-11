#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
from typing import Optional, Any, Dict, List

from backtest.bt_types import TradeSignal
from sr_levels import LevelsService
from indicators import atr_pct_from_ohlc, ema as ema_calc


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    try:
        return int(v.strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    try:
        return float(v.strip())
    except Exception:
        return default


class RetestEngine:
    def __init__(self, fetch_klines):
        self.fetch_klines = fetch_klines
        base = os.getenv("BYBIT_BASE", "https://api.bybit.com")
        self.levels = LevelsService(base_url=base)

        # Params
        self.allow_longs = _env_bool("RETEST_ALLOW_LONGS", True)
        self.allow_shorts = _env_bool("RETEST_ALLOW_SHORTS", True)

        self.confirm_limit = _env_int("RETEST_CONFIRM_LIMIT", 60)
        self.breakout_atr = _env_float("RETEST_BREAKOUT_ATR", 0.50)
        self.touch_atr = _env_float("RETEST_TOUCH_ATR", 0.30)
        self.reclaim_atr = _env_float("RETEST_RECLAIM_ATR", 0.15)
        self.sl_atr = _env_float("RETEST_SL_ATR", 0.70)
        self.max_dist_atr = _env_float("RETEST_MAX_DIST_ATR", 1.20)
        self.min_break_bars = _env_int("RETEST_MIN_BREAK_BARS", 2)
        self.min_hold_bars = _env_int("RETEST_MIN_HOLD_BARS", 0)
        self.max_retest_bars = _env_int("RETEST_MAX_RETEST_BARS", 30)
        self.min_rr = _env_float("RETEST_MIN_RR", 1.2)
        self.rr = _env_float("RETEST_RR", 1.5)

        self.regime_enable = _env_bool("RETEST_REGIME", False)
        self.regime_tf = os.getenv("RETEST_REGIME_TF", "60")
        self.regime_ema_fast = _env_int("RETEST_REGIME_EMA_FAST", 20)
        self.regime_ema_slow = _env_int("RETEST_REGIME_EMA_SLOW", 50)
        self.regime_min_gap_pct = _env_float("RETEST_REGIME_MIN_GAP_PCT", 0.0)
        self.range_enable = _env_bool("RETEST_RANGE_ENABLE", True)
        self.range_only_neutral = _env_bool("RETEST_RANGE_ONLY_NEUTRAL", True)

    def _get_ema_bias(self, symbol: str) -> Optional[int]:
        # 2 = bull, 0 = bear, 1 = neutral
        rows = self.fetch_klines(symbol, self.regime_tf, max(self.regime_ema_slow + 5, 80)) or []
        if len(rows) < self.regime_ema_slow + 2:
            return None
        closes = [float(x[4]) for x in rows]
        ef = ema_calc(closes, self.regime_ema_fast)
        es = ema_calc(closes, self.regime_ema_slow)
        if ef == 0 or es == 0:
            return None
        price = closes[-1]
        gap_pct = abs(ef - es) / max(1e-12, price) * 100.0
        if self.regime_min_gap_pct > 0 and gap_pct < self.regime_min_gap_pct:
            return 1
        return 2 if ef > es else 0

    def signal(self, symbol: str, price: float) -> Optional[TradeSignal]:
        levels, meta = self.levels.get(symbol)
        if not levels:
            return None

        # 5m candles for confirmation + ATR
        rows = self.fetch_klines(symbol, "5", int(self.confirm_limit)) or []
        if len(rows) < 20:
            return None
        o = [float(x[1]) for x in rows]
        h = [float(x[2]) for x in rows]
        l = [float(x[3]) for x in rows]
        c = [float(x[4]) for x in rows]

        atr_pct = atr_pct_from_ohlc(h, l, c, period=14, fallback=0.8)
        atr_abs = float(price) * atr_pct / 100.0
        break_buf = float(self.breakout_atr) * atr_abs
        touch_buf = float(self.touch_atr) * atr_abs
        reclaim_buf = float(self.reclaim_atr) * atr_abs
        sl_buf = float(self.sl_atr) * atr_abs
        max_dist = float(self.max_dist_atr) * atr_abs

        # pick a nearby level
        tol_pct = max(float(meta.get("tol_1h_pct", 0.4)), float(meta.get("tol_4h_pct", 0.4)))
        lv = LevelsService.best_near(levels, price, tol_pct=tol_pct, tf_prefer="4h")
        if not lv:
            return None

        # regime filter
        if self.regime_enable:
            bias = self._get_ema_bias(symbol)
            if bias is None:
                return None
        else:
            bias = None

        def _last_break_idx_long(level: float) -> Optional[int]:
            idx = None
            for i in range(1, len(c)):
                if c[i - 1] <= (level - break_buf) and c[i] >= (level + break_buf):
                    idx = i
            return idx

        def _last_break_idx_short(level: float) -> Optional[int]:
            idx = None
            for i in range(1, len(c)):
                if c[i - 1] >= (level + break_buf) and c[i] <= (level - break_buf):
                    idx = i
            return idx

        def _last_touch_idx_long(level: float, start: int) -> Optional[int]:
            idx = None
            for i in range(max(0, start), len(l)):
                if l[i] <= (level + touch_buf):
                    idx = i
            return idx

        def _last_touch_idx_short(level: float, start: int) -> Optional[int]:
            idx = None
            for i in range(max(0, start), len(h)):
                if h[i] >= (level - touch_buf):
                    idx = i
            return idx

        def _holds_above(level: float) -> bool:
            if self.min_hold_bars <= 0:
                return c[-1] >= (level + reclaim_buf)
            if len(c) < self.min_hold_bars:
                return False
            hold_start = len(c) - self.min_hold_bars
            return min(c[hold_start:]) >= (level + reclaim_buf)

        def _holds_below(level: float) -> bool:
            if self.min_hold_bars <= 0:
                return c[-1] <= (level - reclaim_buf)
            if len(c) < self.min_hold_bars:
                return False
            hold_start = len(c) - self.min_hold_bars
            return max(c[hold_start:]) <= (level - reclaim_buf)

        # Trend retest (breakout -> return -> reclaim/hold)
        if self.allow_longs and price >= lv.price:
            if bias is None or bias in (1, 2):
                if abs(price - lv.price) <= max_dist:
                    i_break = _last_break_idx_long(lv.price)
                    if i_break is not None and (len(c) - 1 - i_break) >= self.min_break_bars:
                        i_touch = _last_touch_idx_long(lv.price, i_break)
                        if i_touch is not None and (len(c) - 1 - i_touch) <= self.max_retest_bars:
                            hold_start = len(c) - max(1, self.min_hold_bars)
                            if i_touch <= hold_start and _holds_above(lv.price):
                                entry = float(price)
                                sl = float(lv.price - sl_buf)
                                risk = entry - sl
                                if risk > 0:
                                    above = LevelsService.nearest_above(levels, entry, kind_filter="resistance")
                                    tp = entry + self.rr * risk
                                    if above:
                                        rr_to_level = (above.price - entry) / risk
                                        if rr_to_level >= self.min_rr:
                                            tp = min(tp, above.price)
                                    return TradeSignal(
                                        strategy="retest_levels",
                                        symbol=symbol,
                                        side="long",
                                        entry=entry,
                                        sl=sl,
                                        tp=tp,
                                        reason=f"retest_long {lv.tf}",
                                    )

        if self.allow_shorts and price <= lv.price:
            if bias is None or bias in (0, 1):
                if abs(price - lv.price) <= max_dist:
                    i_break = _last_break_idx_short(lv.price)
                    if i_break is not None and (len(c) - 1 - i_break) >= self.min_break_bars:
                        i_touch = _last_touch_idx_short(lv.price, i_break)
                        if i_touch is not None and (len(c) - 1 - i_touch) <= self.max_retest_bars:
                            hold_start = len(c) - max(1, self.min_hold_bars)
                            if i_touch <= hold_start and _holds_below(lv.price):
                                entry = float(price)
                                sl = float(lv.price + sl_buf)
                                risk = sl - entry
                                if risk > 0:
                                    below = LevelsService.nearest_below(levels, entry, kind_filter="support")
                                    tp = entry - self.rr * risk
                                    if below:
                                        rr_to_level = (entry - below.price) / risk
                                        if rr_to_level >= self.min_rr:
                                            tp = max(tp, below.price)
                                    return TradeSignal(
                                        strategy="retest_levels",
                                        symbol=symbol,
                                        side="short",
                                        entry=entry,
                                        sl=sl,
                                        tp=tp,
                                        reason=f"retest_short {lv.tf}",
                                    )

        # Range bounce (sideways)
        if self.range_enable:
            if self.range_only_neutral and bias is not None and bias != 1:
                return None
            if self.allow_longs and lv.kind == "support" and price >= lv.price:
                if abs(price - lv.price) <= max_dist and _holds_above(lv.price):
                    i_touch = _last_touch_idx_long(lv.price, 0)
                    if i_touch is not None and (len(c) - 1 - i_touch) <= self.max_retest_bars:
                        entry = float(price)
                        sl = float(lv.price - sl_buf)
                        risk = entry - sl
                        if risk > 0:
                            above = LevelsService.nearest_above(levels, entry, kind_filter="resistance")
                            tp = entry + self.rr * risk
                            if above:
                                rr_to_level = (above.price - entry) / risk
                                if rr_to_level >= self.min_rr:
                                    tp = min(tp, above.price)
                            return TradeSignal(
                                strategy="retest_levels",
                                symbol=symbol,
                                side="long",
                                entry=entry,
                                sl=sl,
                                tp=tp,
                                reason=f"range_long {lv.tf}",
                            )

            if self.allow_shorts and lv.kind == "resistance" and price <= lv.price:
                if abs(price - lv.price) <= max_dist and _holds_below(lv.price):
                    i_touch = _last_touch_idx_short(lv.price, 0)
                    if i_touch is not None and (len(c) - 1 - i_touch) <= self.max_retest_bars:
                        entry = float(price)
                        sl = float(lv.price + sl_buf)
                        risk = sl - entry
                        if risk > 0:
                            below = LevelsService.nearest_below(levels, entry, kind_filter="support")
                            tp = entry - self.rr * risk
                            if below:
                                rr_to_level = (entry - below.price) / risk
                                if rr_to_level >= self.min_rr:
                                    tp = max(tp, below.price)
                            return TradeSignal(
                                strategy="retest_levels",
                                symbol=symbol,
                                side="short",
                                entry=entry,
                                sl=sl,
                                tp=tp,
                                reason=f"range_short {lv.tf}",
                            )

        return None
