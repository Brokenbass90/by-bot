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
        self.touch_atr = _env_float("RETEST_TOUCH_ATR", 0.20)
        self.reclaim_atr = _env_float("RETEST_RECLAIM_ATR", 0.30)
        self.sl_atr = _env_float("RETEST_SL_ATR", 0.80)
        self.min_rr = _env_float("RETEST_MIN_RR", 1.2)
        self.rr = _env_float("RETEST_RR", 1.5)

        self.regime_enable = _env_bool("RETEST_REGIME", False)
        self.regime_tf = os.getenv("RETEST_REGIME_TF", "60")
        self.regime_ema_fast = _env_int("RETEST_REGIME_EMA_FAST", 20)
        self.regime_ema_slow = _env_int("RETEST_REGIME_EMA_SLOW", 50)
        self.regime_min_gap_pct = _env_float("RETEST_REGIME_MIN_GAP_PCT", 0.0)

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
        touch_buf = float(self.touch_atr) * atr_abs
        reclaim_buf = float(self.reclaim_atr) * atr_abs
        sl_buf = float(self.sl_atr) * atr_abs

        # pick a nearby level
        tol_pct = max(float(meta.get("tol_1h_pct", 0.4)), float(meta.get("tol_4h_pct", 0.4)))
        lv = LevelsService.best_near(levels, price, tol_pct=tol_pct, tf_prefer="4h")
        if not lv:
            return None

        last_o = o[-1]
        last_h = h[-1]
        last_l = l[-1]
        last_c = c[-1]

        # regime filter
        if self.regime_enable:
            bias = self._get_ema_bias(symbol)
            if bias is None:
                return None
        else:
            bias = None

        # Long retest at support
        if self.allow_longs and lv.kind == "support" and price >= lv.price:
            if bias is None or bias in (1, 2):
                touched = last_l <= (lv.price + touch_buf)
                reclaimed = last_c >= (lv.price + reclaim_buf)
                if touched and reclaimed:
                    entry = float(price)
                    sl = float(lv.price - sl_buf)
                    risk = entry - sl
                    if risk <= 0:
                        return None
                    # try nearest resistance as TP
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

        # Short retest at resistance
        if self.allow_shorts and lv.kind == "resistance" and price <= lv.price:
            if bias is None or bias in (0, 1):
                touched = last_h >= (lv.price - touch_buf)
                reclaimed = last_c <= (lv.price - reclaim_buf)
                if touched and reclaimed:
                    entry = float(price)
                    sl = float(lv.price + sl_buf)
                    risk = sl - entry
                    if risk <= 0:
                        return None
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

        return None
