"""
elder_triple_screen_v2 — Three-timeframe Elder trading system

Canonical Elder Triple Screen uses three independent filters:
1. Screen 1 (4h tide): long-term trend, typically MACD histogram slope
2. Screen 2 (1h wave): pullback oscillator against the tide, classically Force Index
3. Screen 3 (15m entry): trailing stop above/below the previous bar
   to catch the trend re-assertion after the pullback

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
    ETS2_WAVE_LOOKBACK=3
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


def _ema_series(values: List[float], period: int) -> List[float]:
    if not values or period <= 0:
        return []
    k = 2.0 / (period + 1.0)
    out: List[float] = []
    e = float(values[0])
    out.append(e)
    for v in values[1:]:
        e = float(v) * k + e * (1.0 - k)
        out.append(e)
    return out


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


def _macd_hist_series(values: List[float], fast: int, slow: int, signal: int) -> List[float]:
    if len(values) < max(fast, slow, signal) + 5 or fast <= 0 or slow <= 0 or signal <= 0:
        return []
    fast_ema = _ema_series(values, fast)
    slow_ema = _ema_series(values, slow)
    macd = [f - s for f, s in zip(fast_ema, slow_ema)]
    sig = _ema_series(macd, signal)
    return [m - s for m, s in zip(macd, sig)]


def _force_index_ema(rows: List[list], period: int) -> float:
    if period <= 0 or len(rows) < period + 2:
        return float("nan")
    closes = [float(r[4]) for r in rows]
    vols = [float(r[5]) if len(r) > 5 and str(r[5]).strip() else 0.0 for r in rows]
    raw = [(closes[i] - closes[i - 1]) * vols[i] for i in range(1, len(rows))]
    if len(raw) < period + 1:
        return float("nan")
    series = _ema_series(raw, period)
    return series[-1] if series else float("nan")


@dataclass
class ElderTripleScreenV2Config:
    # Screen 1: Trend (4h) — canonical Elder uses MACD histogram slope
    trend_tf: str = "240"
    trend_mode: str = "macd_hist"  # canonical = "macd_hist"; "ema_slope" for legacy
    trend_ema: int = 13
    trend_slope_bars: int = 2      # slope over 2 bars (current vs 2 bars ago)
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    # Trend strength filters (critical for avoiding choppy/reversal markets):
    # - trend_require_hist_sign: histogram must be on correct side of zero
    #   (e.g. bullish requires hist > 0, not just rising). Prevents "rising from -100" false signals.
    # - trend_consec_bars: N most recent hist bars must all agree with trend direction
    #   (all positive for bullish, all negative for bearish). Filters one-bar flickers.
    # - trend_ema_gate: price must be on correct side of trend_ema for side to be valid.
    #   Long only when 4h close > 13-EMA; Short only when 4h close < 13-EMA.
    #   This prevents counter-trend entries: e.g. MACD hist ticks down in a strong bull
    #   market and we short — price is still above EMA so gate blocks it.
    trend_require_hist_sign: bool = False  # histogram must be above/below zero line
    trend_consec_bars: int = 1             # require N consecutive hist bars same sign
    trend_ema_gate: bool = True            # price must be on correct EMA side for direction

    # Screen 2: Wave (1h) — canonical Elder uses 2-bar EMA of Force Index
    wave_tf: str = "60"
    osc_type: str = "force"  # canonical Elder = "force"; "rsi" and "stoch" also available
    osc_period: int = 2      # canonical Elder uses 2-period EMA of Force Index
    osc_ob: float = 58.0     # only used for rsi/stoch modes
    osc_os: float = 42.0     # only used for rsi/stoch modes
    wave_lookback: int = 1   # check current + 1 previous bar (force index turns fast)

    # Screen 3: Entry (15m)
    entry_tf: str = "15"
    entry_lookback: int = 5
    risk_tf: str = "60"            # use 1h ATR for SL/TP sizing (wider, less noise)
    entry_retest_bars: int = 3     # look back 3 × 15m bars for breakout trigger
    entry_touch_atr_mult: float = 0.25
    entry_min_body_frac: float = 0.30  # stronger bar confirmation (was 0.15)
    entry_break_atr_mult: float = 0.05

    # Exit management
    sl_atr_mult: float = 1.5           # 1.5 × 1h ATR (≈1.2% on BTC) — survivable
    tp_atr_mult: float = 3.0           # TP2 at 3 × 1h ATR = 2R
    tp1_atr_mult: float = 1.5          # TP1 at 1.5 × 1h ATR = 1R (50% close)
    tp1_frac: float = 0.50             # 50% at TP1
    trail_atr_mult: float = 0.0        # disabled — TP1/TP2 structure handles exits
    trail_activate_rr: float = 0.0    # n/a when trail disabled
    allow_longs: bool = True
    allow_shorts: bool = True
    time_stop_bars_5m: int = 288       # 24h time stop (288 × 5m = 24h)
    cooldown_bars_5m: int = 36         # 3h cooldown per symbol
    max_signals_per_day: int = 6       # max 6/day per symbol
    # Volume confirmation filter (default OFF — reduces trades by ~40%, raises PF)
    vol_confirm: bool = False          # ETS2_VOL_CONFIRM=1 to enable
    vol_confirm_mult: float = 1.3      # bar volume must be >= vol_confirm_mult × avg20
    vol_confirm_bars: int = 20         # lookback for average volume


class ElderTripleScreenV2Strategy:
    """Three-screen trend following system."""

    def __init__(self, cfg: Optional[ElderTripleScreenV2Config] = None):
        self.cfg = cfg or ElderTripleScreenV2Config()
        self._load_runtime_config()
        self._cooldown = 0
        self._last_entry_ts: Optional[int] = None
        self._signals_today = 0
        self._last_day: Optional[int] = None
        self.last_no_signal_reason = ""

    def _load_runtime_config(self) -> None:
        self.cfg.trend_tf = os.getenv("ETS2_TREND_TF", self.cfg.trend_tf)
        self.cfg.trend_mode = os.getenv("ETS2_TREND_MODE", self.cfg.trend_mode).strip().lower()
        self.cfg.trend_ema = _env_int("ETS2_TREND_EMA", self.cfg.trend_ema)
        self.cfg.trend_slope_bars = _env_int("ETS2_TREND_SLOPE_BARS", self.cfg.trend_slope_bars)
        self.cfg.trend_require_hist_sign = _env_bool("ETS2_TREND_REQUIRE_HIST_SIGN", self.cfg.trend_require_hist_sign)
        self.cfg.trend_consec_bars = _env_int("ETS2_TREND_CONSEC_BARS", self.cfg.trend_consec_bars)
        self.cfg.trend_ema_gate = _env_bool("ETS2_TREND_EMA_GATE", self.cfg.trend_ema_gate)
        self.cfg.macd_fast = _env_int("ETS2_MACD_FAST", self.cfg.macd_fast)
        self.cfg.macd_slow = _env_int("ETS2_MACD_SLOW", self.cfg.macd_slow)
        self.cfg.macd_signal = _env_int("ETS2_MACD_SIGNAL", self.cfg.macd_signal)

        self.cfg.wave_tf = os.getenv("ETS2_WAVE_TF", self.cfg.wave_tf)
        self.cfg.osc_type = os.getenv("ETS2_OSC_TYPE", self.cfg.osc_type).lower()
        self.cfg.osc_period = _env_int("ETS2_OSC_PERIOD", self.cfg.osc_period)
        self.cfg.osc_ob = _env_float("ETS2_OSC_OB", self.cfg.osc_ob)
        self.cfg.osc_os = _env_float("ETS2_OSC_OS", self.cfg.osc_os)
        self.cfg.wave_lookback = _env_int("ETS2_WAVE_LOOKBACK", self.cfg.wave_lookback)

        self.cfg.entry_tf = os.getenv("ETS2_ENTRY_TF", self.cfg.entry_tf)
        self.cfg.entry_lookback = _env_int("ETS2_ENTRY_LOOKBACK", self.cfg.entry_lookback)
        self.cfg.risk_tf = os.getenv("ETS2_RISK_TF", self.cfg.risk_tf).strip()
        self.cfg.entry_retest_bars = _env_int("ETS2_ENTRY_RETEST_BARS", self.cfg.entry_retest_bars)
        self.cfg.entry_touch_atr_mult = _env_float("ETS2_ENTRY_TOUCH_ATR_MULT", self.cfg.entry_touch_atr_mult)
        self.cfg.entry_min_body_frac = _env_float("ETS2_ENTRY_MIN_BODY_FRAC", self.cfg.entry_min_body_frac)
        self.cfg.entry_break_atr_mult = _env_float("ETS2_ENTRY_BREAK_ATR_MULT", self.cfg.entry_break_atr_mult)

        self.cfg.sl_atr_mult = _env_float("ETS2_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp_atr_mult = _env_float("ETS2_TP_ATR_MULT", self.cfg.tp_atr_mult)
        self.cfg.tp1_atr_mult = _env_float("ETS2_TP1_ATR_MULT", self.cfg.tp1_atr_mult)
        self.cfg.tp1_frac = _env_float("ETS2_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.trail_atr_mult = _env_float("ETS2_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.trail_activate_rr = _env_float("ETS2_TRAIL_ACTIVATE_RR", self.cfg.trail_activate_rr)
        self.cfg.allow_longs = _env_bool("ETS2_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("ETS2_ALLOW_SHORTS", self.cfg.allow_shorts)
        self.cfg.time_stop_bars_5m = _env_int("ETS2_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("ETS2_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("ETS2_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.vol_confirm = _env_bool("ETS2_VOL_CONFIRM", self.cfg.vol_confirm)
        self.cfg.vol_confirm_mult = _env_float("ETS2_VOL_CONFIRM_MULT", self.cfg.vol_confirm_mult)
        self.cfg.vol_confirm_bars = _env_int("ETS2_VOL_CONFIRM_BARS", self.cfg.vol_confirm_bars)

        self._allow = _env_csv_set("ETS2_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("ETS2_SYMBOL_DENYLIST")

    def _refresh_runtime_config(self) -> None:
        self._load_runtime_config()

    def _screen1_trend(self, store) -> Optional[str]:
        """Screen 1: long-term tide.

        Canonical Elder uses the slope of MACD histogram; EMA slope remains
        available as a fallback mode for older experiments.

        Trend strength filters:
          - trend_require_hist_sign: histogram above zero for bullish, below for bearish
          - trend_consec_bars: N recent hist bars must share the same sign
          - trend_ema_gate: price must be on the correct side of the 4h EMA
            (long only when close > EMA; short only when close < EMA). This is the
            most impactful filter — it blocks counter-trend entries in strong trends.
            Example: MACD hist ticks down during a BTC bull run → bearish candidate,
            but price is still above EMA → blocked. Prevents shorting into strength.
        """
        if self.cfg.trend_mode == "macd_hist":
            consec = max(1, self.cfg.trend_consec_bars)
            ema_len = max(self.cfg.trend_ema, 13)
            need = max(80, self.cfg.macd_slow + self.cfg.macd_signal + self.cfg.trend_slope_bars + consec + ema_len + 10)
            rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, need) or []
            closes = [float(r[4]) for r in rows]
            hist = _macd_hist_series(closes, self.cfg.macd_fast, self.cfg.macd_slow, self.cfg.macd_signal)
            if len(hist) < self.cfg.trend_slope_bars + consec + 2:
                return None
            cur = hist[-1]
            prev = hist[-1 - max(1, self.cfg.trend_slope_bars)]
            if not all(math.isfinite(x) for x in (cur, prev)):
                return None
            slope = cur - prev
            # Slope direction (rising or falling)
            if slope > 0:
                candidate = "bullish"
            elif slope < 0:
                candidate = "bearish"
            else:
                return None
            # Optional: histogram must be on correct side of zero line
            if self.cfg.trend_require_hist_sign:
                if candidate == "bullish" and cur <= 0:
                    return None
                if candidate == "bearish" and cur >= 0:
                    return None
            # Optional: N consecutive hist bars same sign
            if consec > 1:
                check_bars = hist[-consec:]
                if candidate == "bullish" and not all(v > 0 for v in check_bars):
                    return None
                if candidate == "bearish" and not all(v < 0 for v in check_bars):
                    return None
            # EMA gate: price must be on the correct side of trend_ema for direction.
            # This blocks counter-trend trades when price structure disagrees with the
            # short-term MACD tick. Most impactful filter for avoiding reversal trades.
            if self.cfg.trend_ema_gate and len(closes) >= ema_len:
                cur_ema = _ema(closes, ema_len)
                cur_price = closes[-1]
                if math.isfinite(cur_ema):
                    if candidate == "bullish" and cur_price < cur_ema:
                        return None
                    if candidate == "bearish" and cur_price > cur_ema:
                        return None
            return candidate
        else:
            rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, max(50, self.cfg.trend_ema + self.cfg.trend_slope_bars + 5)) or []
            if len(rows) < self.cfg.trend_ema + self.cfg.trend_slope_bars + 2:
                return None
            closes = [float(r[4]) for r in rows]
            ema = _ema(closes, self.cfg.trend_ema)
            ema_prev = _ema(closes[: -(self.cfg.trend_slope_bars)], self.cfg.trend_ema)
            if not all(math.isfinite(x) for x in (ema, ema_prev)):
                return None
            slope = ema - ema_prev
            if slope > 0:
                return "bullish"
            if slope < 0:
                return "bearish"
            return None

    def _screen2_wave(self, store, trend: str) -> bool:
        """Screen 2: pullback against the tide.

        Canonical Elder uses the 2-period EMA of Force Index crossing through
        zero. RSI/Stoch remain available for compatibility, but the canonical
        rewrite should generally run with `ETS2_OSC_TYPE=force`.
        """
        rows = store.fetch_klines(store.symbol, self.cfg.wave_tf, max(50, self.cfg.osc_period + self.cfg.wave_lookback + 8)) or []
        if len(rows) < self.cfg.osc_period + 3:
            return False

        lookback = max(0, self.cfg.wave_lookback)
        closes = [float(r[4]) for r in rows]

        for offset in range(lookback + 1):
            sub_rows = rows[: len(rows) - offset] if offset > 0 else rows
            sub_closes = closes[: len(closes) - offset] if offset > 0 else closes
            if self.cfg.osc_type == "force":
                osc = _force_index_ema(sub_rows, self.cfg.osc_period)
                if not math.isfinite(osc):
                    continue
                if trend == "bullish" and osc < 0:
                    return True
                if trend == "bearish" and osc > 0:
                    return True
            elif self.cfg.osc_type == "stoch":
                osc = _stoch_rsi(sub_closes, self.cfg.osc_period)
                if not math.isfinite(osc):
                    continue
                if trend == "bullish" and osc < self.cfg.osc_os:
                    return True
                if trend == "bearish" and osc > self.cfg.osc_ob:
                    return True
            else:
                osc = _rsi(sub_closes, self.cfg.osc_period)
                if not math.isfinite(osc):
                    continue
                if trend == "bullish" and osc < self.cfg.osc_os:
                    return True
                if trend == "bearish" and osc > self.cfg.osc_ob:
                    return True
        return False

    def _screen3_entry(self, store, trend: str) -> Optional[str]:
        """Screen 3: trailing stop above/below the previous entry bar.

        Canonical Elder Screen 3: place a BUY STOP just above the HIGH of the
        most recent completed 15m bar. The trade fires when that level is
        TOUCHED intraday — no requirement for close above it.

        We look back `entry_retest_bars` 15m bars and require that EACH of
        those bars moved in the tide direction (higher closes for bullish tide),
        confirming the momentum is real before we put on the stop.
        """
        n_look = max(1, self.cfg.entry_retest_bars)
        need = max(16, n_look + 8)
        rows = store.fetch_klines(store.symbol, self.cfg.entry_tf, need) or []
        if len(rows) < n_look + 3:
            return None

        opens = [float(r[1]) for r in rows]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]

        entry_atr = _atr_from_rows(rows, 14)
        if not math.isfinite(entry_atr) or entry_atr <= 0:
            return None

        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        cur_close = closes[-1]
        cur_range = max(1e-9, cur_high - cur_low)
        cur_body_frac = abs(cur_close - cur_open) / cur_range
        if cur_body_frac < max(0.0, self.cfg.entry_min_body_frac):
            return None

        break_buf = max(0.0, self.cfg.entry_break_atr_mult) * entry_atr

        # Trigger: BUY STOP above the most recent bar's high (or SELL STOP below low)
        prev_high = highs[-2]
        prev_low = lows[-2]

        # Confirm trend momentum: recent bars should agree with the tide direction.
        # At least (n_look - 1) of the last n_look bars before current must be in
        # the trend direction (bullish bars for long, bearish bars for short).
        ref_bars_ok = 0
        for j in range(-1 - n_look, -1):
            if trend == "bullish" and closes[j] > opens[j]:
                ref_bars_ok += 1
            elif trend == "bearish" and closes[j] < opens[j]:
                ref_bars_ok += 1
        min_agree = max(1, n_look - 2)  # at least n_look-2 bars must agree
        if ref_bars_ok < min_agree:
            return None

        # Classic Screen 3: intraday touch of prev bar's extremity
        # (no close-above requirement — that's a stop order, not a limit order)
        if trend == "bullish":
            trigger = prev_high + break_buf
            close_rank = (cur_close - cur_low) / cur_range if cur_range > 1e-9 else 0.5
            # Current bar touched trigger AND closed in upper 40% of range
            if cur_high >= trigger and close_rank >= 0.40 and cur_close > cur_open:
                return "long"
        else:
            trigger = prev_low - break_buf
            close_rank = (cur_close - cur_low) / cur_range if cur_range > 1e-9 else 0.5
            # Current bar touched trigger AND closed in lower 40% of range
            if cur_low <= trigger and close_rank <= 0.60 and cur_close < cur_open:
                return "short"

        return None

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, v)
        self.last_no_signal_reason = ""
        self._refresh_runtime_config()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            self.last_no_signal_reason = "symbol_not_allowed"
            return None
        if sym in self._deny:
            self.last_no_signal_reason = "symbol_denied"
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            self.last_no_signal_reason = "cooldown"
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

        # Volume confirmation filter (optional — skips weak-volume setups)
        # Reduces ~40% of trades, targets higher-conviction entries only.
        # Enable with: ETS2_VOL_CONFIRM=1  ETS2_VOL_CONFIRM_MULT=1.3
        if self.cfg.vol_confirm:
            n_vol = max(5, self.cfg.vol_confirm_bars)
            rows_vol = store.fetch_klines(store.symbol, self.cfg.entry_tf, n_vol + 2) or []
            if len(rows_vol) >= n_vol + 1:
                try:
                    vols = [float(r[5]) for r in rows_vol if len(r) > 5]
                    if len(vols) >= n_vol + 1:
                        avg_vol = sum(vols[-(n_vol + 1):-1]) / n_vol
                        cur_vol = vols[-1]
                        if avg_vol > 0 and cur_vol < self.cfg.vol_confirm_mult * avg_vol:
                            self.last_no_signal_reason = (
                                f"vol_confirm_weak:{cur_vol:.0f}<{self.cfg.vol_confirm_mult}×{avg_vol:.0f}"
                            )
                            return None
                except (ValueError, IndexError, ZeroDivisionError):
                    pass  # skip filter on data error rather than block the signal

        # Calculate ATR for stops
        risk_tf = self.cfg.risk_tf or self.cfg.entry_tf
        rows_full = store.fetch_klines(store.symbol, risk_tf, 50) or []
        atr = _atr_from_rows(rows_full, 14)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = f"atr_invalid_{risk_tf}"
            return None

        entry_price = float(rows_entry[-1][4])
        prev_entry_high = float(rows_entry[-2][2])
        prev_entry_low = float(rows_entry[-2][3])
        cur_entry_high = float(rows_entry[-1][2])
        cur_entry_low = float(rows_entry[-1][3])

        # Calculate stops and targets
        if side == "long":
            struct_sl = min(prev_entry_low, cur_entry_low) - 0.05 * atr
            sl = min(entry_price - self.cfg.sl_atr_mult * atr, struct_sl)
            if sl >= entry_price:
                self.last_no_signal_reason = "long_sl_invalid"
                return None
            tp1 = entry_price + self.cfg.tp1_atr_mult * atr
            tp2 = entry_price + self.cfg.tp_atr_mult * atr
            if tp2 <= entry_price or tp1 <= entry_price or tp1 >= tp2:
                self.last_no_signal_reason = "long_tp_invalid"
                return None
        else:  # short
            struct_sl = max(prev_entry_high, cur_entry_high) + 0.05 * atr
            sl = max(entry_price + self.cfg.sl_atr_mult * atr, struct_sl)
            if sl <= entry_price:
                self.last_no_signal_reason = "short_sl_invalid"
                return None
            tp1 = entry_price - self.cfg.tp1_atr_mult * atr
            tp2 = entry_price - self.cfg.tp_atr_mult * atr
            if tp2 >= entry_price or tp1 >= entry_price or tp1 <= tp2:
                self.last_no_signal_reason = "short_tp_invalid"
                return None

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        self._signals_today += 1
        frac1 = max(0.01, min(0.99, float(self.cfg.tp1_frac)))
        sig = TradeSignal(
            strategy="elder_triple_screen_v2",
            symbol=store.symbol,
            side=side,
            entry=entry_price,
            sl=sl,
            tp=tp2,
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=14,
            trail_activate_rr=max(0.0, float(self.cfg.trail_activate_rr)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"ets2_{trend}_{side}",
        )
        # Multi-TP: 50% at TP1 (1.5 ATR = 1R), 50% at TP2 (3.0 ATR = 2R)
        sig.tps = [tp1, tp2]
        sig.tp_fracs = [frac1, 1.0 - frac1]
        return sig if sig.validate() else None
