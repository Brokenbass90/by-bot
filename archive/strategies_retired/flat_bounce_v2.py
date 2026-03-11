from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional

from .signals import TradeSignal


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    out = values[0]
    for x in values[1:]:
        out = x * k + out * (1.0 - k)
    return out


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    if len(closes) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return sum(trs) / float(period) if trs else float("nan")


def _rsi(values: List[float], period: int) -> float:
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


@dataclass
class FlatBounceV2Config:
    lookback_bars: int = 180
    atr_period: int = 14
    ema_fast: int = 20
    ema_slow: int = 50
    max_ema_gap_pct: float = 0.50
    max_ema_slope_pct: float = 0.55
    min_atr_pct: float = 0.20
    max_atr_pct: float = 2.20
    min_range_width_atr: float = 2.4
    max_range_width_atr: float = 10.0

    zone_atr_mult: float = 0.50
    min_reject_wick_frac: float = 0.35
    min_reject_body_frac: float = 0.18
    min_touches: int = 2
    touches_lookback: int = 120
    rsi_period: int = 14
    rsi_oversold: float = 36.0
    rsi_overbought: float = 64.0

    sl_atr_mult: float = 1.05
    rr1: float = 1.15
    rr2: float = 2.0
    cooldown_bars: int = 14
    max_signals_per_day: int = 2


class FlatBounceV2Strategy:
    """Pure flat bounce (no grid averaging)."""

    def __init__(self, cfg: Optional[FlatBounceV2Config] = None):
        self.cfg = cfg or FlatBounceV2Config()
        self.cfg.lookback_bars = _env_int("FB2_LOOKBACK_BARS", self.cfg.lookback_bars)
        self.cfg.atr_period = _env_int("FB2_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.ema_fast = _env_int("FB2_EMA_FAST", self.cfg.ema_fast)
        self.cfg.ema_slow = _env_int("FB2_EMA_SLOW", self.cfg.ema_slow)
        self.cfg.max_ema_gap_pct = _env_float("FB2_MAX_EMA_GAP_PCT", self.cfg.max_ema_gap_pct)
        self.cfg.max_ema_slope_pct = _env_float("FB2_MAX_EMA_SLOPE_PCT", self.cfg.max_ema_slope_pct)
        self.cfg.min_atr_pct = _env_float("FB2_MIN_ATR_PCT", self.cfg.min_atr_pct)
        self.cfg.max_atr_pct = _env_float("FB2_MAX_ATR_PCT", self.cfg.max_atr_pct)
        self.cfg.min_range_width_atr = _env_float("FB2_MIN_RANGE_WIDTH_ATR", self.cfg.min_range_width_atr)
        self.cfg.max_range_width_atr = _env_float("FB2_MAX_RANGE_WIDTH_ATR", self.cfg.max_range_width_atr)
        self.cfg.zone_atr_mult = _env_float("FB2_ZONE_ATR_MULT", self.cfg.zone_atr_mult)
        self.cfg.min_reject_wick_frac = _env_float("FB2_MIN_REJECT_WICK_FRAC", self.cfg.min_reject_wick_frac)
        self.cfg.min_reject_body_frac = _env_float("FB2_MIN_REJECT_BODY_FRAC", self.cfg.min_reject_body_frac)
        self.cfg.min_touches = _env_int("FB2_MIN_TOUCHES", self.cfg.min_touches)
        self.cfg.touches_lookback = _env_int("FB2_TOUCHES_LOOKBACK", self.cfg.touches_lookback)
        self.cfg.rsi_period = _env_int("FB2_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.rsi_oversold = _env_float("FB2_RSI_OVERSOLD", self.cfg.rsi_oversold)
        self.cfg.rsi_overbought = _env_float("FB2_RSI_OVERBOUGHT", self.cfg.rsi_overbought)
        self.cfg.sl_atr_mult = _env_float("FB2_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr1 = _env_float("FB2_RR1", self.cfg.rr1)
        self.cfg.rr2 = _env_float("FB2_RR2", self.cfg.rr2)
        self.cfg.cooldown_bars = _env_int("FB2_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("FB2_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._o: List[float] = []
        self._h: List[float] = []
        self._l: List[float] = []
        self._c: List[float] = []
        self._cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _is_flat_regime(self, atr_now: float) -> bool:
        need = max(self.cfg.ema_slow + 10, self.cfg.lookback_bars + 5)
        if len(self._c) < need:
            return False
        closes = self._c[-(self.cfg.ema_slow + 20):]
        ef = _ema(closes, self.cfg.ema_fast)
        es = _ema(closes, self.cfg.ema_slow)
        es_prev = _ema(closes[:-8], self.cfg.ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)) or closes[-1] <= 0:
            return False
        gap_pct = abs(ef - es) / closes[-1] * 100.0
        slope_pct = abs((es - es_prev) / max(1e-12, abs(es_prev))) * 100.0
        atr_pct = atr_now / closes[-1] * 100.0
        return (
            gap_pct <= self.cfg.max_ema_gap_pct
            and slope_pct <= self.cfg.max_ema_slope_pct
            and self.cfg.min_atr_pct <= atr_pct <= self.cfg.max_atr_pct
        )

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (store, v)
        self._o.append(o)
        self._h.append(h)
        self._l.append(l)
        self._c.append(c)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        need = max(self.cfg.lookback_bars + 5, self.cfg.atr_period + 5, self.cfg.touches_lookback + 5)
        if len(self._c) < need:
            return None

        atr_now = _atr(self._h, self._l, self._c, self.cfg.atr_period)
        if not math.isfinite(atr_now) or atr_now <= 0:
            return None
        if not self._is_flat_regime(atr_now):
            return None

        hh = self._h[-(self.cfg.lookback_bars + 1):-1]
        ll = self._l[-(self.cfg.lookback_bars + 1):-1]
        res = max(hh)
        sup = min(ll)
        if res <= sup:
            return None
        range_w_atr = (res - sup) / atr_now
        if range_w_atr < self.cfg.min_range_width_atr or range_w_atr > self.cfg.max_range_width_atr:
            return None

        zone = self.cfg.zone_atr_mult * atr_now
        near_res = abs(c - res) <= zone
        near_sup = abs(c - sup) <= zone

        # touches maturity
        tlook_h = self._h[-self.cfg.touches_lookback:]
        tlook_l = self._l[-self.cfg.touches_lookback:]
        touch_tol = zone
        t_res = sum(1 for x in tlook_h if abs(x - res) <= touch_tol)
        t_sup = sum(1 for x in tlook_l if abs(x - sup) <= touch_tol)
        if t_res < self.cfg.min_touches or t_sup < self.cfg.min_touches:
            return None

        rng = max(1e-12, h - l)
        body_frac = abs(c - o) / rng
        upper_wick_frac = (h - max(o, c)) / rng
        lower_wick_frac = (min(o, c) - l) / rng
        bear_reject = c < o and body_frac >= self.cfg.min_reject_body_frac and upper_wick_frac >= self.cfg.min_reject_wick_frac
        bull_reject = c > o and body_frac >= self.cfg.min_reject_body_frac and lower_wick_frac >= self.cfg.min_reject_wick_frac
        rsi_now = _rsi(self._c, self.cfg.rsi_period)
        if not math.isfinite(rsi_now):
            return None

        mid = (res + sup) * 0.5
        dist_from_mid = abs(c - mid) / max(1e-12, (res - sup))
        if dist_from_mid < 0.28:
            return None

        if near_res and bear_reject and rsi_now >= self.cfg.rsi_overbought and h > res and c < res:
            entry = c
            sl = max(h, res) + self.cfg.sl_atr_mult * atr_now
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = min(mid, entry - self.cfg.rr1 * risk)
            tp2 = min(entry - self.cfg.rr2 * risk, res - 0.15 * (res - sup))
            if not (tp2 < tp1 < entry):
                return None
            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="flat_bounce_v2",
                symbol=store.symbol,
                side="short",
                entry=entry,
                sl=sl,
                tp=tp2,
                tps=[tp1, tp2],
                tp_fracs=[0.6, 0.4],
                reason="fb2_short_res_bounce",
            )

        if near_sup and bull_reject and rsi_now <= self.cfg.rsi_oversold and l < sup and c > sup:
            entry = c
            sl = min(l, sup) - self.cfg.sl_atr_mult * atr_now
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = max(mid, entry + self.cfg.rr1 * risk)
            tp2 = max(entry + self.cfg.rr2 * risk, sup + 0.15 * (res - sup))
            if not (tp2 > tp1 > entry):
                return None
            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="flat_bounce_v2",
                symbol=store.symbol,
                side="long",
                entry=entry,
                sl=sl,
                tp=tp2,
                tps=[tp1, tp2],
                tp_fracs=[0.6, 0.4],
                reason="fb2_long_sup_bounce",
            )
        return None
