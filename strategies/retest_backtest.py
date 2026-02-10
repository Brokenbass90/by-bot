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
    touch_atr: float = 0.20
    reclaim_atr: float = 0.30
    sl_atr: float = 0.80
    min_rr: float = 1.2
    rr: float = 1.5

    allow_longs: bool = True
    allow_shorts: bool = True

    # regime filter
    regime_enable: bool = False
    regime_tf: str = "60"
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_min_gap_pct: float = 0.0


class RetestBacktestStrategy:
    def __init__(self, store, cfg: Optional[RetestBTConfig] = None):
        self.store = store
        self.cfg = cfg or RetestBTConfig()

        # env overrides
        self.cfg.confirm_limit = _env_int("RETEST_CONFIRM_LIMIT", self.cfg.confirm_limit)
        self.cfg.touch_atr = _env_float("RETEST_TOUCH_ATR", self.cfg.touch_atr)
        self.cfg.reclaim_atr = _env_float("RETEST_RECLAIM_ATR", self.cfg.reclaim_atr)
        self.cfg.sl_atr = _env_float("RETEST_SL_ATR", self.cfg.sl_atr)
        self.cfg.min_rr = _env_float("RETEST_MIN_RR", self.cfg.min_rr)
        self.cfg.rr = _env_float("RETEST_RR", self.cfg.rr)
        self.cfg.allow_longs = _env_bool("RETEST_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("RETEST_ALLOW_SHORTS", self.cfg.allow_shorts)

        self.cfg.regime_enable = _env_bool("RETEST_REGIME", self.cfg.regime_enable)
        self.cfg.regime_tf = os.getenv("RETEST_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_ema_fast = _env_int("RETEST_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("RETEST_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_min_gap_pct = _env_float("RETEST_REGIME_MIN_GAP_PCT", self.cfg.regime_min_gap_pct)

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
        touch_buf = self.cfg.touch_atr * atr_abs
        reclaim_buf = self.cfg.reclaim_atr * atr_abs
        sl_buf = self.cfg.sl_atr * atr_abs

        # nearest level
        tol_pct = max(self.cfg.tol_1h_min, self.cfg.tol_4h_min)
        lv = LevelsService.best_near(levels, price, tol_pct=tol_pct, tf_prefer="4h")
        if not lv:
            return None

        last_o = o[-1]
        last_h = h[-1]
        last_l = l[-1]
        last_c = c[-1]

        bias = self._regime_bias()

        if self.cfg.allow_longs and lv.kind == "support" and price >= lv.price:
            if bias is None or bias in (1, 2):
                touched = last_l <= (lv.price + touch_buf)
                reclaimed = last_c >= (lv.price + reclaim_buf)
                if touched and reclaimed:
                    entry = price
                    sl = lv.price - sl_buf
                    risk = entry - sl
                    if risk <= 0:
                        return None
                    above = LevelsService.nearest_above(levels, entry, kind_filter="resistance")
                    tp = entry + self.cfg.rr * risk
                    if above:
                        rr_to_level = (above.price - entry) / risk
                        if rr_to_level >= self.cfg.min_rr:
                            tp = min(tp, above.price)
                    return TradeSignal("retest_levels", store.symbol, "long", entry, sl, tp, reason=f"retest_long {lv.tf}")

        if self.cfg.allow_shorts and lv.kind == "resistance" and price <= lv.price:
            if bias is None or bias in (0, 1):
                touched = last_h >= (lv.price - touch_buf)
                reclaimed = last_c <= (lv.price - reclaim_buf)
                if touched and reclaimed:
                    entry = price
                    sl = lv.price + sl_buf
                    risk = sl - entry
                    if risk <= 0:
                        return None
                    below = LevelsService.nearest_below(levels, entry, kind_filter="support")
                    tp = entry - self.cfg.rr * risk
                    if below:
                        rr_to_level = (entry - below.price) / risk
                        if rr_to_level >= self.cfg.min_rr:
                            tp = max(tp, below.price)
                    return TradeSignal("retest_levels", store.symbol, "short", entry, sl, tp, reason=f"retest_short {lv.tf}")

        return None
