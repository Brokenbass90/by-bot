"""
elder_triple_screen_v2 — Three-timeframe Elder trading system

Classic Elder Triple Screen using three independent filters:
1. Screen 1 (4h tide): EMA(13) slope on 4h bars determines direction
2. Screen 2 (1h wave): RSI(8) oscillator on 1h bars (pullback levels)
3. Screen 3 (15m entry): Breakout signal on 15m bars in direction of tide

All three must agree for entry. Proper timeframe hierarchy (4h → 1h → 15m)
ensures multiple confirmations before committing capital.

Typical env config:
    ETS2_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,BNBUSDT
    ETS2_TREND_TF=240
    ETS2_WAVE_TF=60
    ETS2_ENTRY_TF=15
    ETS2_RISK_TF=60
    ETS2_TREND_EMA=13
    ETS2_OSC_PERIOD=8
    ETS2_OSC_OB=58
    ETS2_OSC_OS=42
    ETS2_ENTRY_RETEST_BARS=5
    ETS2_SL_ATR_MULT=2.0
    ETS2_TP_ATR_MULT=2.5
    ETS2_ALLOW_LONGS=1
    ETS2_ALLOW_SHORTS=1
"""
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
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _atr_from_rows(rows: List[list], period: int) -> float:
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


def _stoch_rsi(values: List[float], rsi_period: int = 14, stoch_period: int = 14) -> float:
    """Stochastic RSI: RSI value normalized over a stoch_period lookback (0–100)."""
    need = rsi_period + stoch_period + 1
    if len(values) < need:
        return float("nan")
    rsi_series: List[float] = []
    for offset in range(stoch_period, -1, -1):
        end = len(values) - offset
        sub = values[end - rsi_period - 1 : end]
        if len(sub) >= rsi_period + 1:
            rsi_series.append(_rsi(sub, rsi_period))
    if len(rsi_series) < 2 or any(not math.isfinite(x) for x in rsi_series):
        return float("nan")
    cur = rsi_series[-1]
    lo = min(rsi_series)
    hi = max(rsi_series)
    if hi - lo < 1e-9:
        return 50.0
    return 100.0 * (cur - lo) / (hi - lo)


@dataclass
class ElderTripleScreenV2Config:
    # Screen 1: Trend (4h)
    trend_tf: str = "240"
    trend_ema: int = 13
    trend_slope_bars: int = 3

    # Screen 2: Wave (1h)
    wave_tf: str = "60"
    osc_type: str = "rsi"  # "rsi" or "stoch"
    osc_period: int = 8
    osc_ob: float = 58.0
    osc_os: float = 42.0

    # Screen 3: Entry (15m)
    entry_tf: str = "15"
    entry_lookback: int = 5
    risk_tf: str = ""
    entry_retest_bars: int = 5
    entry_touch_atr_mult: float = 0.25
    entry_min_body_frac: float = 0.30

    # Exit management
    sl_atr_mult: float = 2.0
    tp_atr_mult: float = 2.5
    trail_atr_mult: float = 1.0
    allow_longs: bool = True
    allow_shorts: bool = True
    time_stop_bars_5m: int = 576
    cooldown_bars_5m: int = 18
    max_signals_per_day: int = 20


class ElderTripleScreenV2Strategy:
    """Three-screen trend following system."""

    def __init__(self, cfg: Optional[ElderTripleScreenV2Config] = None):
        self.cfg = cfg or ElderTripleScreenV2Config()

        self.cfg.trend_tf = os.getenv("ETS2_TREND_TF", self.cfg.trend_tf)
        self.cfg.trend_ema = _env_int("ETS2_TREND_EMA", self.cfg.trend_ema)
        self.cfg.trend_slope_bars = _env_int("ETS2_TREND_SLOPE_BARS", self.cfg.trend_slope_bars)

        self.cfg.wave_tf = os.getenv("ETS2_WAVE_TF", self.cfg.wave_tf)
        self.cfg.osc_type = os.getenv("ETS2_OSC_TYPE", self.cfg.osc_type).lower()
        self.cfg.osc_period = _env_int("ETS2_OSC_PERIOD", self.cfg.osc_period)
        self.cfg.osc_ob = _env_float("ETS2_OSC_OB", self.cfg.osc_ob)
        self.cfg.osc_os = _env_float("ETS2_OSC_OS", self.cfg.osc_os)

        self.cfg.entry_tf = os.getenv("ETS2_ENTRY_TF", self.cfg.entry_tf)
        self.cfg.entry_lookback = _env_int("ETS2_ENTRY_LOOKBACK", self.cfg.entry_lookback)
        self.cfg.risk_tf = os.getenv("ETS2_RISK_TF", self.cfg.risk_tf).strip()
        self.cfg.entry_retest_bars = _env_int("ETS2_ENTRY_RETEST_BARS", self.cfg.entry_retest_bars)
        self.cfg.entry_touch_atr_mult = _env_float("ETS2_ENTRY_TOUCH_ATR_MULT", self.cfg.entry_touch_atr_mult)
        self.cfg.entry_min_body_frac = _env_float("ETS2_ENTRY_MIN_BODY_FRAC", self.cfg.entry_min_body_frac)

        self.cfg.sl_atr_mult = _env_float("ETS2_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp_atr_mult = _env_float("ETS2_TP_ATR_MULT", self.cfg.tp_atr_mult)
        self.cfg.trail_atr_mult = _env_float("ETS2_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.allow_longs = _env_bool("ETS2_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("ETS2_ALLOW_SHORTS", self.cfg.allow_shorts)
        self.cfg.time_stop_bars_5m = _env_int("ETS2_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("ETS2_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("ETS2_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        self._allow = _env_csv_set("ETS2_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("ETS2_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_entry_ts: Optional[int] = None
        self._signals_today = 0
        self._last_day: Optional[int] = None
        self.last_no_signal_reason = ""

    def _refresh_runtime_allowlists(self) -> None:
        self._allow = _env_csv_set("ETS2_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("ETS2_SYMBOL_DENYLIST")

    def _screen1_trend(self, store) -> Optional[str]:
        """Screen 1: Trend determination via EMA slope on trend TF.
        Returns: "bullish", "bearish", or None if indeterminate."""
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(50, self.cfg.trend_ema + self.cfg.trend_slope_bars + 5)) or []
        if len(rows) < self.cfg.trend_ema + self.cfg.trend_slope_bars + 2:
            return None

        closes = [float(r[4]) for r in rows]
        ema = _ema(closes, self.cfg.trend_ema)
        ema_prev = _ema(closes[: -(self.cfg.trend_slope_bars)], self.cfg.trend_ema)

        if not all(math.isfinite(x) for x in (ema, ema_prev)):
            return None

        # Slope > 0 = bullish, < 0 = bearish
        slope = ema - ema_prev
        if slope > 0:
            return "bullish"
        elif slope < 0:
            return "bearish"
        return None

    def _screen2_wave(self, store, trend: str) -> bool:
        """Screen 2: Oscillator pullback check on wave TF.
        Returns True if oscillator is in pullback zone for the trend."""
        rows = store.fetch_klines(store.symbol, self.cfg.wave_tf, max(50, self.cfg.osc_period + 5)) or []
        if len(rows) < self.cfg.osc_period + 2:
            return False

        closes = [float(r[4]) for r in rows]
        if self.cfg.osc_type == "stoch":
            osc = _stoch_rsi(closes, self.cfg.osc_period)
        else:  # default: rsi
            osc = _rsi(closes, self.cfg.osc_period)

        if not math.isfinite(osc):
            return False

        # In bullish trend: want RSI < OS (pullback)
        # In bearish trend: want RSI > OB (pullback)
        if trend == "bullish":
            return osc < self.cfg.osc_os
        else:  # bearish
            return osc > self.cfg.osc_ob

    def _screen3_entry(self, store, trend: str) -> Optional[str]:
        """Screen 3: entry via retest/reclaim, not raw breakout.

        Classic crypto failure mode for Elder here was entering on the first poke
        through a local high/low. We now require a recent touch back into the level
        zone and a directional reclaim candle with acceptable body quality.
        """
        need = max(12, self.cfg.entry_lookback + self.cfg.entry_retest_bars + 4)
        rows = store.fetch_klines(store.symbol, self.cfg.entry_tf, need) or []
        if len(rows) < need:
            return None

        opens = [float(r[1]) for r in rows]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]

        entry_atr = _atr_from_rows(rows, 14)
        if not math.isfinite(entry_atr) or entry_atr <= 0:
            return None

        lookback = max(2, self.cfg.entry_lookback)
        retest_bars = max(1, self.cfg.entry_retest_bars)
        touch_buf = max(0.0, self.cfg.entry_touch_atr_mult) * entry_atr

        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        cur_close = closes[-1]
        cur_range = max(1e-9, cur_high - cur_low)
        cur_body_frac = abs(cur_close - cur_open) / cur_range
        if cur_body_frac < max(0.0, self.cfg.entry_min_body_frac):
            return None

        if trend == "bullish":
            # Wave pullback is already asking for weakness inside an uptrend.
            # Entry should therefore come from reclaiming a recent support zone,
            # not from re-breaking a local resistance shelf from below.
            level = min(lows[-(lookback + retest_bars + 1):-retest_bars-1])
            recent_touch = min(lows[-(retest_bars + 1):-1]) <= (level + touch_buf)
            reclaimed = (
                cur_close > (level + touch_buf)
                and cur_close > cur_open
                and cur_low >= (level - touch_buf)
            )
            if recent_touch and reclaimed:
                return "long"
        else:
            # Mirror logic for bearish pullbacks: rally back into resistance,
            # then fail and reclaim below that resistance zone.
            level = max(highs[-(lookback + retest_bars + 1):-retest_bars-1])
            recent_touch = max(highs[-(retest_bars + 1):-1]) >= (level - touch_buf)
            reclaimed = (
                cur_close < (level - touch_buf)
                and cur_close < cur_open
                and cur_high <= (level + touch_buf)
            )
            if recent_touch and reclaimed:
                return "short"

        return None

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, v)
        self._refresh_runtime_allowlists()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        # Check daily signal limit
        ts_sec = ts_ms // 1000
        day = ts_sec // 86400
        if day != self._last_day:
            self._last_day = day
            self._signals_today = 0
        if self._signals_today >= self.cfg.max_signals_per_day:
            self.last_no_signal_reason = "max_signals_per_day_reached"
            return None

        # Fetch entry TF for timing gate
        rows_entry = store.fetch_klines(store.symbol, self.cfg.entry_tf, 5) or []
        if len(rows_entry) < 2:
            self.last_no_signal_reason = "not_enough_entry_bars"
            return None

        tf_ts = int(float(rows_entry[-1][0]))
        if self._last_entry_ts is not None and tf_ts == self._last_entry_ts:
            return None
        self._last_entry_ts = tf_ts

        # Screen 1: Trend
        trend = self._screen1_trend(store)
        if trend is None:
            self.last_no_signal_reason = "screen1_trend_invalid"
            return None

        # Screen 2: Wave
        if not self._screen2_wave(store, trend):
            self.last_no_signal_reason = f"screen2_wave_no_pullback_{trend}"
            return None

        # Screen 3: Entry
        side = self._screen3_entry(store, trend)
        if side is None:
            self.last_no_signal_reason = f"screen3_no_breakout_{trend}"
            return None

        # Check side allowlist
        if side == "long" and not self.cfg.allow_longs:
            return None
        if side == "short" and not self.cfg.allow_shorts:
            return None

        # Calculate ATR for stops
        risk_tf = self.cfg.risk_tf or self.cfg.entry_tf
        rows_full = store.fetch_klines(store.symbol, risk_tf, 50) or []
        atr = _atr_from_rows(rows_full, 14)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = f"atr_invalid_{risk_tf}"
            return None

        entry_price = float(c)

        # Calculate stops and targets
        if side == "long":
            sl = entry_price - self.cfg.sl_atr_mult * atr
            if sl >= entry_price:
                self.last_no_signal_reason = "long_sl_invalid"
                return None
            tp = entry_price + self.cfg.tp_atr_mult * atr
            if tp <= entry_price:
                self.last_no_signal_reason = "long_tp_invalid"
                return None
        else:  # short
            sl = entry_price + self.cfg.sl_atr_mult * atr
            if sl <= entry_price:
                self.last_no_signal_reason = "short_sl_invalid"
                return None
            tp = entry_price - self.cfg.tp_atr_mult * atr
            if tp >= entry_price:
                self.last_no_signal_reason = "short_tp_invalid"
                return None

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        self._signals_today += 1
        sig = TradeSignal(
            strategy="elder_triple_screen_v2",
            symbol=store.symbol,
            side=side,
            entry=entry_price,
            sl=sl,
            tp=tp,
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=14,
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"ets2_{trend}_{side}",
        )
        return sig if sig.validate() else None
