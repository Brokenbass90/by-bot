from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, List

from backtest.bt_types import TradeSignal
from indicators import atr_pct_from_ohlc, ema as ema_calc
from sr_levels import _pivots, _cluster_levels, _merge_1h_into_4h, LevelsService, Level


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


@dataclass
class RetestBTConfig:
    # level detection
    swing_n_1h: int = 2
    swing_n_4h: int = 3
    max_levels: int = 18
    tf_weight_4h: float = 1.25
    tol_mul_1h: float = 0.30
    tol_mul_4h: float = 0.22
    tol_1h_min: float = 0.20
    tol_1h_max: float = 0.90
    tol_4h_min: float = 0.25
    tol_4h_max: float = 0.80

    # retest logic
    confirm_limit: int = 60
    breakout_atr: float = 0.50
    touch_atr: float = 0.30
    reclaim_atr: float = 0.15
    sl_atr: float = 0.70
    max_dist_atr: float = 1.20
    min_break_bars: int = 2
    min_hold_bars: int = 0
    max_retest_bars: int = 30
    min_rr: float = 1.2
    rr: float = 1.5

    allow_longs: bool = True
    allow_shorts: bool = True

    # retest style controls
    trend_only: bool = True
    levels_only_4h: bool = True

    # regime filter
    regime_enable: bool = False
    regime_tf: str = "60"
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_min_gap_pct: float = 0.0

    # range (sideways) bounce mode
    range_enable: bool = True
    range_only_neutral: bool = True


class RetestBacktestStrategy:
    def __init__(self, store, cfg: Optional[RetestBTConfig] = None):
        self.store = store
        self.cfg = cfg or RetestBTConfig()

        # env overrides
        self.cfg.confirm_limit = _env_int("RETEST_CONFIRM_LIMIT", self.cfg.confirm_limit)
        self.cfg.breakout_atr = _env_float("RETEST_BREAKOUT_ATR", self.cfg.breakout_atr)
        self.cfg.touch_atr = _env_float("RETEST_TOUCH_ATR", self.cfg.touch_atr)
        self.cfg.reclaim_atr = _env_float("RETEST_RECLAIM_ATR", self.cfg.reclaim_atr)
        self.cfg.sl_atr = _env_float("RETEST_SL_ATR", self.cfg.sl_atr)
        self.cfg.max_dist_atr = _env_float("RETEST_MAX_DIST_ATR", self.cfg.max_dist_atr)
        self.cfg.min_break_bars = _env_int("RETEST_MIN_BREAK_BARS", self.cfg.min_break_bars)
        self.cfg.min_hold_bars = _env_int("RETEST_MIN_HOLD_BARS", self.cfg.min_hold_bars)
        self.cfg.max_retest_bars = _env_int("RETEST_MAX_RETEST_BARS", self.cfg.max_retest_bars)
        self.cfg.min_rr = _env_float("RETEST_MIN_RR", self.cfg.min_rr)
        self.cfg.rr = _env_float("RETEST_RR", self.cfg.rr)
        self.cfg.allow_longs = _env_bool("RETEST_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("RETEST_ALLOW_SHORTS", self.cfg.allow_shorts)
        self.cfg.trend_only = _env_bool("RETEST_TREND_ONLY", self.cfg.trend_only)
        self.cfg.levels_only_4h = _env_bool("RETEST_LEVELS_ONLY_4H", self.cfg.levels_only_4h)

        self.cfg.regime_enable = _env_bool("RETEST_REGIME", self.cfg.regime_enable)
        self.cfg.regime_tf = os.getenv("RETEST_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_ema_fast = _env_int("RETEST_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("RETEST_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_min_gap_pct = _env_float("RETEST_REGIME_MIN_GAP_PCT", self.cfg.regime_min_gap_pct)

        self.cfg.range_enable = _env_bool("RETEST_RANGE_ENABLE", self.cfg.range_enable)
        self.cfg.range_only_neutral = _env_bool("RETEST_RANGE_ONLY_NEUTRAL", self.cfg.range_only_neutral)

    def _levels_from_store(self) -> List[Level]:
        # use aggregated candles already in store
        c1h = self.store._slice("60", 10**9)
        c4h = self.store._slice("240", 10**9)
        if len(c1h) < 50 or len(c4h) < 30:
            return []

        t1 = [int(c.ts // 1000) for c in c1h]
        h1 = [float(c.h) for c in c1h]
        l1 = [float(c.l) for c in c1h]
        c1 = [float(c.c) for c in c1h]

        t4 = [int(c.ts // 1000) for c in c4h]
        h4 = [float(c.h) for c in c4h]
        l4 = [float(c.l) for c in c4h]
        c4 = [float(c.c) for c in c4h]

        atr1 = atr_pct_from_ohlc(h1, l1, c1, period=14, fallback=0.8)
        atr4 = atr_pct_from_ohlc(h4, l4, c4, period=14, fallback=0.8)

        tol1 = max(self.cfg.tol_1h_min, min(self.cfg.tol_1h_max, self.cfg.tol_mul_1h * atr1))
        tol4 = max(self.cfg.tol_4h_min, min(self.cfg.tol_4h_max, self.cfg.tol_mul_4h * atr4))

        cands1 = _pivots(t1, h1, l1, swing_n=self.cfg.swing_n_1h)
        cands4 = _pivots(t4, h4, l4, swing_n=self.cfg.swing_n_4h)

        lv1 = _cluster_levels(cands1, tol_pct=tol1, tf="1h", tf_weight=1.0)
        lv4 = _cluster_levels(cands4, tol_pct=tol4, tf="4h", tf_weight=self.cfg.tf_weight_4h)

        levels = _merge_1h_into_4h(lv4, lv1, tol4_pct=tol4)
        return levels[: max(1, int(self.cfg.max_levels))]

    def _regime_bias(self) -> Optional[int]:
        if not self.cfg.regime_enable:
            return None
        rows = self.store.fetch_klines(self.store.symbol, self.cfg.regime_tf, max(self.cfg.regime_ema_slow + 5, 80)) or []
        if len(rows) < self.cfg.regime_ema_slow + 2:
            return None
        closes = [float(x[4]) for x in rows]
        ef = ema_calc(closes, self.cfg.regime_ema_fast)
        es = ema_calc(closes, self.cfg.regime_ema_slow)
        if ef == 0 or es == 0:
            return None
        price = closes[-1]
        gap_pct = abs(ef - es) / max(1e-12, price) * 100.0
        if self.cfg.regime_min_gap_pct > 0 and gap_pct < self.cfg.regime_min_gap_pct:
            return 1
        return 2 if ef > es else 0

    def signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        levels = self._levels_from_store()
        if not levels:
            return None

        rows = store.fetch_klines(store.symbol, "5", int(self.cfg.confirm_limit)) or []
        if len(rows) < 20:
            return None
        o = [float(x[1]) for x in rows]
        h = [float(x[2]) for x in rows]
        l = [float(x[3]) for x in rows]
        c = [float(x[4]) for x in rows]

        price = float(last_price)
        atr_pct = atr_pct_from_ohlc(h, l, c, period=14, fallback=0.8)
        atr_abs = price * atr_pct / 100.0
        break_buf = self.cfg.breakout_atr * atr_abs
        touch_buf = self.cfg.touch_atr * atr_abs
        reclaim_buf = self.cfg.reclaim_atr * atr_abs
        sl_buf = self.cfg.sl_atr * atr_abs
        max_dist = self.cfg.max_dist_atr * atr_abs

        # nearest level
        tol_pct = max(self.cfg.tol_1h_min, self.cfg.tol_4h_min)
        lv = LevelsService.best_near(levels, price, tol_pct=tol_pct, tf_prefer="4h")
        if not lv:
            return None
        if self.cfg.levels_only_4h and str(getattr(lv, "tf", "")) != "4h":
            return None

        bias = self._regime_bias()

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
            if self.cfg.min_hold_bars <= 0:
                return c[-1] >= (level + reclaim_buf)
            if len(c) < self.cfg.min_hold_bars:
                return False
            hold_start = len(c) - self.cfg.min_hold_bars
            return min(c[hold_start:]) >= (level + reclaim_buf)

        def _holds_below(level: float) -> bool:
            if self.cfg.min_hold_bars <= 0:
                return c[-1] <= (level - reclaim_buf)
            if len(c) < self.cfg.min_hold_bars:
                return False
            hold_start = len(c) - self.cfg.min_hold_bars
            return max(c[hold_start:]) <= (level - reclaim_buf)

        # Trend retest (breakout -> return -> reclaim/hold)
        if self.cfg.allow_longs and price >= lv.price:
            if bias is None or bias in (1, 2):
                if abs(price - lv.price) <= max_dist:
                    i_break = _last_break_idx_long(lv.price)
                    if i_break is not None and (len(c) - 1 - i_break) >= self.cfg.min_break_bars:
                        i_touch = _last_touch_idx_long(lv.price, i_break)
                        if i_touch is not None and (len(c) - 1 - i_touch) <= self.cfg.max_retest_bars:
                            hold_start = len(c) - max(1, self.cfg.min_hold_bars)
                            if i_touch <= hold_start and _holds_above(lv.price):
                                entry = price
                                sl = lv.price - sl_buf
                                risk = entry - sl
                                if risk > 0:
                                    above = LevelsService.nearest_above(levels, entry, kind_filter="resistance")
                                    tp = entry + self.cfg.rr * risk
                                    if above:
                                        rr_to_level = (above.price - entry) / risk
                                        if rr_to_level >= self.cfg.min_rr:
                                            tp = min(tp, above.price)
                                    return TradeSignal("retest_levels", store.symbol, "long", entry, sl, tp, reason=f"retest_long {lv.tf}")

        if self.cfg.allow_shorts and price <= lv.price:
            if bias is None or bias in (0, 1):
                if abs(price - lv.price) <= max_dist:
                    i_break = _last_break_idx_short(lv.price)
                    if i_break is not None and (len(c) - 1 - i_break) >= self.cfg.min_break_bars:
                        i_touch = _last_touch_idx_short(lv.price, i_break)
                        if i_touch is not None and (len(c) - 1 - i_touch) <= self.cfg.max_retest_bars:
                            hold_start = len(c) - max(1, self.cfg.min_hold_bars)
                            if i_touch <= hold_start and _holds_below(lv.price):
                                entry = price
                                sl = lv.price + sl_buf
                                risk = sl - entry
                                if risk > 0:
                                    below = LevelsService.nearest_below(levels, entry, kind_filter="support")
                                    tp = entry - self.cfg.rr * risk
                                    if below:
                                        rr_to_level = (entry - below.price) / risk
                                        if rr_to_level >= self.cfg.min_rr:
                                            tp = max(tp, below.price)
                                    return TradeSignal("retest_levels", store.symbol, "short", entry, sl, tp, reason=f"retest_short {lv.tf}")

        # Range bounce (sideways)
        if (not self.cfg.trend_only) and self.cfg.range_enable:
            if self.cfg.range_only_neutral and bias is not None and bias != 1:
                return None
            if self.cfg.allow_longs and lv.kind == "support" and price >= lv.price:
                if abs(price - lv.price) <= max_dist and _holds_above(lv.price):
                    i_touch = _last_touch_idx_long(lv.price, 0)
                    if i_touch is not None and (len(c) - 1 - i_touch) <= self.cfg.max_retest_bars:
                        entry = price
                        sl = lv.price - sl_buf
                        risk = entry - sl
                        if risk > 0:
                            above = LevelsService.nearest_above(levels, entry, kind_filter="resistance")
                            tp = entry + self.cfg.rr * risk
                            if above:
                                rr_to_level = (above.price - entry) / risk
                                if rr_to_level >= self.cfg.min_rr:
                                    tp = min(tp, above.price)
                            return TradeSignal("retest_levels", store.symbol, "long", entry, sl, tp, reason=f"range_long {lv.tf}")

            if self.cfg.allow_shorts and lv.kind == "resistance" and price <= lv.price:
                if abs(price - lv.price) <= max_dist and _holds_below(lv.price):
                    i_touch = _last_touch_idx_short(lv.price, 0)
                    if i_touch is not None and (len(c) - 1 - i_touch) <= self.cfg.max_retest_bars:
                        entry = price
                        sl = lv.price + sl_buf
                        risk = sl - entry
                        if risk > 0:
                            below = LevelsService.nearest_below(levels, entry, kind_filter="support")
                            tp = entry - self.cfg.rr * risk
                            if below:
                                rr_to_level = (entry - below.price) / risk
                                if rr_to_level >= self.cfg.min_rr:
                                    tp = max(tp, below.price)
                            return TradeSignal("retest_levels", store.symbol, "short", entry, sl, tp, reason=f"range_short {lv.tf}")

        return None
