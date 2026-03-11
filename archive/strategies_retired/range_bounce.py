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


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


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
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / max(1, len(trs))


def _sma(values: List[float], n: int) -> float:
    if n <= 0 or len(values) < n:
        return float("nan")
    return sum(values[-n:]) / float(n)


@dataclass
class RangeBounceConfig:
    lookback_bars: int = 180
    atr_period: int = 14

    ema_fast: int = 20
    ema_slow: int = 50
    trend_max_gap_pct: float = 0.30
    trend_follow_only: bool = True

    touch_tolerance_pct: float = 0.10
    min_touches: int = 3
    touches_lookback: int = 200

    vol_short_n: int = 8
    vol_long_n: int = 34
    vol_confirm_mult: float = 0.95
    require_vol_decline: bool = True

    min_reject_body_frac: float = 0.20
    min_reject_wick_frac: float = 0.30

    min_atr_pct: float = 0.15
    max_atr_pct: float = 2.00

    breakout_kill_atr_mult: float = 0.7
    kill_cooldown_bars: int = 24

    sl_atr_mult: float = 1.0
    rr1: float = 1.25
    rr2: float = 2.2
    est_roundtrip_cost_pct: float = 0.26
    min_gross_move_pct: float = 0.40
    min_net_move_pct: float = 0.10
    min_net_rr: float = 1.15

    cooldown_bars: int = 10
    max_signals_per_day: int = 3

    allow_longs: bool = True
    allow_shorts: bool = True


class RangeBounceStrategy:
    """Level bounce strategy with stricter regime and fakeout protection (v2)."""

    def __init__(self, cfg: Optional[RangeBounceConfig] = None):
        self.cfg = cfg or RangeBounceConfig()

        self.cfg.lookback_bars = _env_int("RB_LOOKBACK_BARS", self.cfg.lookback_bars)
        self.cfg.atr_period = _env_int("RB_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.ema_fast = _env_int("RB_EMA_FAST", self.cfg.ema_fast)
        self.cfg.ema_slow = _env_int("RB_EMA_SLOW", self.cfg.ema_slow)
        self.cfg.trend_max_gap_pct = _env_float("RB_TREND_MAX_GAP_PCT", self.cfg.trend_max_gap_pct)
        self.cfg.trend_follow_only = _env_bool("RB_TREND_FOLLOW_ONLY", self.cfg.trend_follow_only)

        self.cfg.touch_tolerance_pct = _env_float("RB_TOUCH_TOL_PCT", self.cfg.touch_tolerance_pct)
        self.cfg.min_touches = _env_int("RB_MIN_TOUCHES", self.cfg.min_touches)
        self.cfg.touches_lookback = _env_int("RB_TOUCHES_LOOKBACK", self.cfg.touches_lookback)

        self.cfg.vol_short_n = _env_int("RB_VOL_SHORT_N", self.cfg.vol_short_n)
        self.cfg.vol_long_n = _env_int("RB_VOL_LONG_N", self.cfg.vol_long_n)
        self.cfg.vol_confirm_mult = _env_float("RB_VOL_CONFIRM_MULT", self.cfg.vol_confirm_mult)
        self.cfg.require_vol_decline = _env_bool("RB_REQUIRE_VOL_DECLINE", self.cfg.require_vol_decline)

        self.cfg.min_reject_body_frac = _env_float("RB_MIN_REJECT_BODY_FRAC", self.cfg.min_reject_body_frac)
        self.cfg.min_reject_wick_frac = _env_float("RB_MIN_REJECT_WICK_FRAC", self.cfg.min_reject_wick_frac)

        self.cfg.min_atr_pct = _env_float("RB_MIN_ATR_PCT", self.cfg.min_atr_pct)
        self.cfg.max_atr_pct = _env_float("RB_MAX_ATR_PCT", self.cfg.max_atr_pct)

        self.cfg.breakout_kill_atr_mult = _env_float("RB_BREAKOUT_KILL_ATR_MULT", self.cfg.breakout_kill_atr_mult)
        self.cfg.kill_cooldown_bars = _env_int("RB_KILL_COOLDOWN_BARS", self.cfg.kill_cooldown_bars)

        self.cfg.sl_atr_mult = _env_float("RB_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr1 = _env_float("RB_RR1", self.cfg.rr1)
        self.cfg.rr2 = _env_float("RB_RR2", self.cfg.rr2)
        self.cfg.est_roundtrip_cost_pct = _env_float("RB_EST_ROUNDTRIP_COST_PCT", self.cfg.est_roundtrip_cost_pct)
        self.cfg.min_gross_move_pct = _env_float("RB_MIN_GROSS_MOVE_PCT", self.cfg.min_gross_move_pct)
        self.cfg.min_net_move_pct = _env_float("RB_MIN_NET_MOVE_PCT", self.cfg.min_net_move_pct)
        self.cfg.min_net_rr = _env_float("RB_MIN_NET_RR", self.cfg.min_net_rr)

        self.cfg.cooldown_bars = _env_int("RB_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.max_signals_per_day = _env_int("RB_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self.cfg.allow_longs = _env_bool("RB_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("RB_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._o5: List[float] = []
        self._h5: List[float] = []
        self._l5: List[float] = []
        self._c5: List[float] = []
        self._v5: List[float] = []

        self._cooldown = 0
        self._kill_cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _economics_ok(self, side: str, entry: float, tp: float, sl: float) -> bool:
        if entry <= 0 or tp <= 0 or sl <= 0:
            return False
        if side == "long":
            gross_move_pct = (tp - entry) / entry * 100.0
            risk_pct = (entry - sl) / entry * 100.0
        else:
            gross_move_pct = (entry - tp) / entry * 100.0
            risk_pct = (sl - entry) / entry * 100.0
        if gross_move_pct < self.cfg.min_gross_move_pct:
            return False
        net_move_pct = gross_move_pct - self.cfg.est_roundtrip_cost_pct
        if net_move_pct < self.cfg.min_net_move_pct:
            return False
        if risk_pct <= 0:
            return False
        net_rr = net_move_pct / max(1e-9, risk_pct)
        return net_rr >= self.cfg.min_net_rr

    def _touches(self, level: float, highs: List[float], lows: List[float]) -> int:
        if level <= 0:
            return 0
        tol = self.cfg.touch_tolerance_pct / 100.0
        cnt = 0
        for hh, ll in zip(highs, lows):
            if abs(hh - level) / level <= tol or abs(ll - level) / level <= tol:
                cnt += 1
        return cnt

    def _trend_bias(self) -> int:
        closes = self._c5[-(self.cfg.ema_slow + 12):]
        if len(closes) < self.cfg.ema_slow + 2:
            return 1
        ef = _ema(closes, self.cfg.ema_fast)
        es = _ema(closes, self.cfg.ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and closes[-1] > 0):
            return 1
        gap_pct = abs(ef - es) / closes[-1] * 100.0
        if gap_pct <= self.cfg.trend_max_gap_pct:
            return 1
        return 2 if ef > es else 0

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        self._o5.append(o)
        self._h5.append(h)
        self._l5.append(l)
        self._c5.append(c)
        self._v5.append(v)

        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        if self._kill_cooldown > 0:
            self._kill_cooldown -= 1
            return None

        need = max(
            self.cfg.lookback_bars + 2,
            self.cfg.atr_period + 2,
            self.cfg.touches_lookback + 2,
            self.cfg.vol_long_n + 2,
            self.cfg.ema_slow + 12,
        )
        if len(self._c5) < need:
            return None

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        highs_ref = self._h5[-(self.cfg.lookback_bars + 1):-1]
        lows_ref = self._l5[-(self.cfg.lookback_bars + 1):-1]
        if not highs_ref or not lows_ref:
            return None
        resistance = max(highs_ref)
        support = min(lows_ref)
        width = resistance - support
        if width <= 0:
            return None

        atr_now = _atr(self._h5, self._l5, self._c5, self.cfg.atr_period)
        if not math.isfinite(atr_now) or atr_now <= 0:
            return None

        atr_pct = atr_now / max(1e-12, c) * 100.0
        if atr_pct < self.cfg.min_atr_pct or atr_pct > self.cfg.max_atr_pct:
            return None

        # Kill-switch: recent close escaped range by too much => likely trend leg.
        prev_c = self._c5[-2]
        if prev_c > (resistance + self.cfg.breakout_kill_atr_mult * atr_now) or prev_c < (support - self.cfg.breakout_kill_atr_mult * atr_now):
            self._kill_cooldown = self.cfg.kill_cooldown_bars
            return None

        vol_short = _sma(self._v5, self.cfg.vol_short_n)
        vol_long = _sma(self._v5, self.cfg.vol_long_n)
        if not math.isfinite(vol_short) or not math.isfinite(vol_long) or vol_long <= 0:
            return None

        vol_decline = vol_short <= vol_long
        vol_confirm = v >= (vol_long * self.cfg.vol_confirm_mult)
        if self.cfg.require_vol_decline and not vol_decline:
            return None
        if not vol_confirm:
            return None

        rng = max(1e-12, h - l)
        body_frac = abs(c - o) / rng
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        upper_wick_frac = upper_wick / rng
        lower_wick_frac = lower_wick / rng

        bear_candle = c < o and body_frac >= self.cfg.min_reject_body_frac and upper_wick_frac >= self.cfg.min_reject_wick_frac
        bull_candle = c > o and body_frac >= self.cfg.min_reject_body_frac and lower_wick_frac >= self.cfg.min_reject_wick_frac

        touch_h = self._h5[-self.cfg.touches_lookback:]
        touch_l = self._l5[-self.cfg.touches_lookback:]
        touches_res = self._touches(resistance, touch_h, touch_l)
        touches_sup = self._touches(support, touch_h, touch_l)

        zone = max(atr_now * 0.30, c * (self.cfg.touch_tolerance_pct / 100.0))
        near_res = abs(c - resistance) <= zone
        near_sup = abs(c - support) <= zone

        trend_bias = self._trend_bias()  # 0 bear, 1 range, 2 bull

        allow_short = self.cfg.allow_shorts
        allow_long = self.cfg.allow_longs
        if self.cfg.trend_follow_only:
            allow_short = allow_short and (trend_bias in (0, 1))
            allow_long = allow_long and (trend_bias in (1, 2))

        if allow_short and near_res and touches_res >= self.cfg.min_touches and bear_candle:
            entry = c
            sl = max(h, resistance) + self.cfg.sl_atr_mult * atr_now
            risk = sl - entry
            if risk <= 0:
                return None

            tp1 = entry - self.cfg.rr1 * risk
            tp2 = entry - self.cfg.rr2 * risk
            # Do not place TP below hard support zone too aggressively.
            tp2 = max(tp2, support + 0.10 * width)
            if not (tp1 < entry and tp2 < tp1):
                return None
            if not self._economics_ok("short", entry, tp2, sl):
                return None

            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="range_bounce",
                symbol=store.symbol,
                side="short",
                entry=entry,
                sl=sl,
                tp=tp2,
                tps=[tp1, tp2],
                tp_fracs=[0.6, 0.4],
                trailing_atr_mult=0.0,
                trailing_atr_period=self.cfg.atr_period,
                time_stop_bars=72,
                reason="rbv2_short_resistance_bounce",
            )

        if allow_long and near_sup and touches_sup >= self.cfg.min_touches and bull_candle:
            entry = c
            sl = min(l, support) - self.cfg.sl_atr_mult * atr_now
            risk = entry - sl
            if risk <= 0:
                return None

            tp1 = entry + self.cfg.rr1 * risk
            tp2 = entry + self.cfg.rr2 * risk
            tp2 = min(tp2, resistance - 0.10 * width)
            if not (tp1 > entry and tp2 > tp1):
                return None
            if not self._economics_ok("long", entry, tp2, sl):
                return None

            self._cooldown = self.cfg.cooldown_bars
            self._day_signals += 1
            return TradeSignal(
                strategy="range_bounce",
                symbol=store.symbol,
                side="long",
                entry=entry,
                sl=sl,
                tp=tp2,
                tps=[tp1, tp2],
                tp_fracs=[0.6, 0.4],
                trailing_atr_mult=0.0,
                trailing_atr_period=self.cfg.atr_period,
                time_stop_bars=72,
                reason="rbv2_long_support_bounce",
            )

        return None
