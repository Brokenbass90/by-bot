"""micro_scalper_v1.py — 5m EMA Pullback Scalper

Strategy concept:
  1. Trend filter:  15m EMA20 slope determines direction (long/short/flat)
  2. Entry signal:  5m price pulls back to EMA9 zone, then closes with meaningful
                   body in trend direction (momentum reclaim)
  3. Volume guard:  optional — current 5m volume >= vol_mult × 20-bar avg
  4. Session guard: only trade 07:00–17:00 UTC (London + NY overlap)
  5. SL:            beyond the entry-bar low/high + small ATR buffer
  6. TP:            fixed rr multiple of risk
  7. Time stop:     16 bars (80 minutes max hold)
  8. Cooldown:      min 3 bars between signals per symbol

ENV prefix: MSCALP_*
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from .signals import TradeSignal

# Family-profile scaling (BTC_ETH tighter SL, MID_ALTS wider SL/TP/cooldown)
try:
    from bot.family_profiles import profiles as _fp
    _FP_ENABLED = True
except ImportError:
    _fp = None  # type: ignore[assignment]
    _FP_ENABLED = False


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

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


def _env_csv_set(name: str, default_csv: str = "") -> set:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _ema(values: List[float], period: int) -> float:
    """Exponential moving average of the last `period` values (or full list if shorter)."""
    n = len(values)
    if n < 1:
        return float("nan")
    p = min(period, n)
    seed_vals = values[:p]
    ema = sum(seed_vals) / float(p)
    alpha = 2.0 / (period + 1)
    for v in values[p:]:
        ema = alpha * v + (1.0 - alpha) * ema
    return ema


def _atr(rows: List[list], period: int) -> float:
    """ATR(period) from list-of-lists [[ts, o, h, l, c, v, ...], ...]."""
    if len(rows) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(1, len(rows)):
        h = float(rows[i][2])
        l = float(rows[i][3])
        pc = float(rows[i - 1][4])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return float("nan")
    # Wilder's smoothed ATR seeded by simple average
    atr = sum(trs[:period]) / float(period)
    alpha = 1.0 / float(period)
    for tr in trs[period:]:
        atr = (1.0 - alpha) * atr + alpha * tr
    return atr


def _utc_hour(ts_ms: int) -> int:
    """Return UTC hour from millisecond timestamp."""
    try:
        return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).hour
    except Exception:
        return -1


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class MicroScalperV1Config:
    # Trend timeframe and EMA period
    trend_tf: str = "15"          # "15" = 15m  (aggregated from 5m by KlineStore)
    trend_ema: int = 20           # EMA period for trend direction on trend_tf
    trend_lookback: int = 30      # bars to load on trend_tf
    trend_min_slope_pct: float = 0.04  # min |slope| % per bar to call a trend

    # Entry timeframe (5m = smallest available)
    entry_lookback: int = 50      # bars to load for 5m calculations
    entry_ema: int = 9            # EMA period on 5m to define pullback zone
    atr_period: int = 14          # ATR period on 5m

    # Entry filter thresholds
    pullback_atr: float = 0.35    # max distance (in ATR) from close to EMA9 to qualify as pullback
    min_body_atr: float = 0.22    # minimum body (in ATR) for entry candle
    vol_mult: float = 0.0         # volume filter (0 = disabled): current vol >= vol_mult * avg

    # Exit sizing
    rr: float = 1.5               # risk/reward (TP = entry +/- rr * risk)
    sl_buffer_atr: float = 0.15   # extra ATR buffer beyond bar extreme for SL

    # Position controls
    max_signals_per_day: int = 5
    cooldown_bars: int = 3        # min 5m bars between any two signals

    # Time filter (UTC hours, inclusive)
    session_start_utc: int = 7    # 07:00 UTC  (London open)
    session_end_utc: int = 22     # 22:00 UTC  (EU+NY, matches bounce/breakout)

    # Risk controls
    min_sl_atr: float = 0.15      # reject signal if SL dist < this * ATR (noise)
    max_sl_atr: float = 1.5       # reject signal if SL dist > this * ATR (too wide)
    time_stop_bars: int = 16      # max bars to hold (0 = disabled)

    # Direction
    allow_longs: bool = True
    allow_shorts: bool = True


# ---------------------------------------------------------------------------
# Strategy class
# ---------------------------------------------------------------------------

class MicroScalperV1Strategy:
    """5m EMA pullback scalper. Trend from 15m EMA20, entries on 5m EMA9 reclaim."""

    NAME = "micro_scalper_v1"

    def __init__(self, cfg: Optional[MicroScalperV1Config] = None):
        self.cfg = cfg or MicroScalperV1Config()

        # Override from ENV
        self.cfg.trend_tf = os.getenv("MSCALP_TREND_TF", self.cfg.trend_tf)
        self.cfg.trend_ema = _env_int("MSCALP_TREND_EMA", self.cfg.trend_ema)
        self.cfg.trend_lookback = _env_int("MSCALP_TREND_LOOKBACK", self.cfg.trend_lookback)
        self.cfg.trend_min_slope_pct = _env_float("MSCALP_TREND_MIN_SLOPE_PCT", self.cfg.trend_min_slope_pct)
        self.cfg.entry_lookback = _env_int("MSCALP_ENTRY_LOOKBACK", self.cfg.entry_lookback)
        self.cfg.entry_ema = _env_int("MSCALP_ENTRY_EMA", self.cfg.entry_ema)
        self.cfg.atr_period = _env_int("MSCALP_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.pullback_atr = _env_float("MSCALP_PULLBACK_ATR", self.cfg.pullback_atr)
        self.cfg.min_body_atr = _env_float("MSCALP_MIN_BODY_ATR", self.cfg.min_body_atr)
        self.cfg.vol_mult = _env_float("MSCALP_VOL_MULT", self.cfg.vol_mult)
        self.cfg.rr = _env_float("MSCALP_RR", self.cfg.rr)
        self.cfg.sl_buffer_atr = _env_float("MSCALP_SL_BUFFER_ATR", self.cfg.sl_buffer_atr)
        self.cfg.max_signals_per_day = _env_int("MSCALP_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.cooldown_bars = _env_int("MSCALP_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.session_start_utc = _env_int("MSCALP_SESSION_START_UTC", self.cfg.session_start_utc)
        self.cfg.session_end_utc = _env_int("MSCALP_SESSION_END_UTC", self.cfg.session_end_utc)
        self.cfg.min_sl_atr = _env_float("MSCALP_MIN_SL_ATR", self.cfg.min_sl_atr)
        self.cfg.max_sl_atr = _env_float("MSCALP_MAX_SL_ATR", self.cfg.max_sl_atr)
        self.cfg.time_stop_bars = _env_int("MSCALP_TIME_STOP_BARS", self.cfg.time_stop_bars)
        self.cfg.allow_longs = _env_bool("MSCALP_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("MSCALP_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("MSCALP_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("MSCALP_SYMBOL_DENYLIST")

        # Per-symbol state (populated lazily)
        self._cooldown: int = 0
        self._day_signals: int = 0
        self._last_day: int = -1
        self.last_no_signal_reason: str = ""

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def maybe_signal(
        self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0
    ) -> Optional[TradeSignal]:
        sym = str(getattr(store, "symbol", "")).upper()

        # Symbol filter
        if self._allow and sym not in self._allow:
            self.last_no_signal_reason = "symbol_allow"
            return None
        if sym in self._deny:
            self.last_no_signal_reason = "symbol_deny"
            return None

        # Cooldown
        if self._cooldown > 0:
            self._cooldown -= 1
            self.last_no_signal_reason = "cooldown"
            return None

        # Session filter (UTC hour)
        hour = _utc_hour(ts_ms)
        if hour < self.cfg.session_start_utc or hour >= self.cfg.session_end_utc:
            self.last_no_signal_reason = "session"
            return None

        # Daily signal cap
        day = ts_ms // 86_400_000
        if day != self._last_day:
            self._last_day = day
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            self.last_no_signal_reason = "daily_cap"
            return None

        # ------ Trend analysis on trend_tf ------
        trend_rows = store.fetch_klines(sym, self.cfg.trend_tf, self.cfg.trend_lookback)
        if not trend_rows or len(trend_rows) < max(self.cfg.trend_ema + 3, 10):
            self.last_no_signal_reason = "trend_data"
            return None

        trend_closes = [float(r[4]) for r in trend_rows]
        ema_now = _ema(trend_closes, self.cfg.trend_ema)
        ema_lag = _ema(trend_closes[:-3], self.cfg.trend_ema)  # 3 bars ago

        if not math.isfinite(ema_now) or not math.isfinite(ema_lag) or ema_lag <= 0:
            self.last_no_signal_reason = "trend_nan"
            return None

        slope_pct = (ema_now - ema_lag) / ema_lag * 100.0
        min_slope = self.cfg.trend_min_slope_pct

        if abs(slope_pct) < min_slope:
            self.last_no_signal_reason = "trend_flat"
            return None

        trend = "long" if slope_pct > 0 else "short"

        # Direction allowed?
        if trend == "long" and not self.cfg.allow_longs:
            self.last_no_signal_reason = "direction_longs_off"
            return None
        if trend == "short" and not self.cfg.allow_shorts:
            self.last_no_signal_reason = "direction_shorts_off"
            return None

        # ------ Entry signal on 5m ------
        entry_rows = store.fetch_klines(sym, "5", self.cfg.entry_lookback)
        if not entry_rows or len(entry_rows) < max(self.cfg.atr_period + 2, self.cfg.entry_ema + 2, 20):
            self.last_no_signal_reason = "entry_data"
            return None

        atr = _atr(entry_rows, self.cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = "atr_nan"
            return None

        entry_closes = [float(r[4]) for r in entry_rows]
        ema9 = _ema(entry_closes, self.cfg.entry_ema)
        if not math.isfinite(ema9) or ema9 <= 0:
            self.last_no_signal_reason = "ema9_nan"
            return None

        # Current bar provided by engine: o, h, l, c
        bar_o, bar_h, bar_l, bar_c = o, h, l, c

        # Pullback check: close must be near EMA9
        dist_to_ema = abs(bar_c - ema9)
        if dist_to_ema > self.cfg.pullback_atr * atr:
            self.last_no_signal_reason = "pullback_miss"
            return None

        # Body check: candle body must be meaningful in trend direction
        body = bar_c - bar_o  # positive = bullish, negative = bearish
        abs_body = abs(body)
        if abs_body < self.cfg.min_body_atr * atr:
            self.last_no_signal_reason = "body_weak"
            return None

        # Direction alignment
        if trend == "long" and body <= 0:
            self.last_no_signal_reason = "candle_wrong_dir"
            return None
        if trend == "short" and body >= 0:
            self.last_no_signal_reason = "candle_wrong_dir"
            return None

        # Volume check (optional)
        if self.cfg.vol_mult > 0 and v > 0:
            vols = [float(r[5]) for r in entry_rows[:-1] if float(r[5]) > 0]
            lookback_v = min(20, len(vols))
            if lookback_v >= 5:
                avg_vol = sum(vols[-lookback_v:]) / float(lookback_v)
                if avg_vol > 0 and v < self.cfg.vol_mult * avg_vol:
                    self.last_no_signal_reason = "vol_weak"
                    return None

        # ------ SL / TP calculation ------
        # Look at last 2 bars for swing extreme
        prev_row = entry_rows[-2] if len(entry_rows) >= 2 else entry_rows[-1]
        prev_l = float(prev_row[3])
        prev_h = float(prev_row[2])

        entry_price = bar_c

        # Family-profile param scaling (BTC/ETH tighter, MID_ALTS wider)
        fp_sl_mult  = _fp.scale(sym, "sl",      1.0) if _FP_ENABLED else 1.0
        fp_tp_mult  = _fp.scale(sym, "tp",      1.0) if _FP_ENABLED else 1.0
        fp_cd_mult  = _fp.scale(sym, "cooldown", 1.0) if _FP_ENABLED else 1.0
        sl_buf      = self.cfg.sl_buffer_atr * fp_sl_mult
        rr_scaled   = self.cfg.rr * fp_tp_mult

        if trend == "long":
            swing_low = min(bar_l, prev_l)
            sl = swing_low - sl_buf * atr
            sl_dist = entry_price - sl
        else:
            swing_high = max(bar_h, prev_h)
            sl = swing_high + sl_buf * atr
            sl_dist = sl - entry_price

        # Validate SL distance
        if sl_dist <= 0:
            self.last_no_signal_reason = "sl_invalid"
            return None
        sl_in_atr = sl_dist / atr
        if sl_in_atr < self.cfg.min_sl_atr:
            self.last_no_signal_reason = "sl_too_tight"
            return None
        if sl_in_atr > self.cfg.max_sl_atr:
            self.last_no_signal_reason = "sl_too_wide"
            return None

        if trend == "long":
            tp = entry_price + rr_scaled * sl_dist
        else:
            tp = entry_price - rr_scaled * sl_dist

        sig = TradeSignal(
            strategy=self.NAME,
            symbol=sym,
            side=trend,
            entry=entry_price,
            sl=sl,
            tp=tp,
            time_stop_bars=self.cfg.time_stop_bars,
            reason=(
                f"scalp_{trend}|ema9={ema9:.2f}|atr={atr:.4f}"
                f"|slope={slope_pct:+.3f}%|body_atr={abs_body/atr:.2f}"
                + (f"|fp={_fp.family_name(sym)}" if _FP_ENABLED else "")
            ),
        )

        if not sig.validate():
            self.last_no_signal_reason = "validate_fail"
            return None

        self._cooldown = max(1, round(self.cfg.cooldown_bars * fp_cd_mult))
        self._day_signals += 1
        self.last_no_signal_reason = ""
        return sig
