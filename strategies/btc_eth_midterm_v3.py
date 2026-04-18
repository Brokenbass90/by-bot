from __future__ import annotations

"""
BTCETHMidtermV3
===============
Medium-term BTC/ETH pullback strategy — significantly improved over v1/v2.

Key improvements vs v1:
  1. MACD 4H MACRO FILTER — same as Elder/ASB1/HZBO1/IVB1.
     Blocks longs when 4h MACD hist ≤ 0. Blocks shorts when 4h MACD hist ≥ 0.
     This is the #1 fix: prevents trading against the macro trend.

  2. RSI 1H CONFIRMATION — longs only when 1h RSI < 62 (not overbought).
     Shorts only when 1h RSI > 38 (not oversold). Avoids chasing extensions.

  3. FRESH TOUCH REQUIREMENT — touch must be in last MTPB3_FRESH_TOUCH_BARS (3)
     bars, not 10 bars ago. Prevents stale setups from firing.

  4. REGIME ENV VARS — MTPB3_ALLOW_LONGS / MTPB3_ALLOW_SHORTS re-read on every
     signal call, so the Regime Orchestrator can toggle them in real-time via
     configs/regime_orchestrator_latest.env hot-reload.

  5. PER-DIRECTION COOLDOWN — separate long_cooldown / short_cooldown so one
     direction doesn't block the other for 7 hours.

  6. VOLUME SPIKE CONFIRM (optional) — enter only when 1h volume > avg_vol * mult.
     Defaults to ON. Filters low-conviction touches.

  7. BETTER RECLAIM CHECK — prev bar must have been strictly below/above EMA
     (not just within 0.3%). Tighter confirmation that a real cross happened.

  8. WEEKLY MACRO GATE (optional) — weekly EMA50/200 must agree with trade direction.
     Prevents trading against the bigger cycle.

ENV prefix: MTPB3_*
Strategy name: "btc_eth_midterm_v3"
"""

import math
import os
from dataclasses import dataclass, field
from typing import List, Optional

from .signals import TradeSignal


# ─── Helpers ─────────────────────────────────────────────────────────────────

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
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _ema_series(values: List[float], period: int) -> List[float]:
    """Return full EMA series (same length as values)."""
    if not values or period <= 0:
        return [float("nan")] * len(values)
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def _atr_from_rows(rows: List[list], period: int) -> float:
    if len(rows) < period + 1:
        return float("nan")
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
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


def _macd_hist(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float:
    """Return the latest MACD histogram value (MACD line - Signal line)."""
    if len(closes) < slow + signal + 5:
        return float("nan")
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema_series(macd_line, signal)
    hist = macd_line[-1] - signal_line[-1]
    return hist


# ─── Config ──────────────────────────────────────────────────────────────────

@dataclass
class MidtermV3Config:
    # Timeframes
    trend_tf: str = "240"   # 4H — trend + MACD macro
    signal_tf: str = "60"   # 1H — entry timing
    eval_tf_min: int = 15   # evaluate every 15m

    # Trend: EMA50/200 on 4H
    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    trend_slope_bars: int = 10       # slope lookback (was 8)
    trend_slope_min_pct: float = 0.40
    trend_min_gap_pct: float = 0.20

    # MACD 4H macro filter (NEW — most important)
    # KEY INSIGHT: Asymmetric application!
    #   SHORTS: require MACD hist < 0 (confirms bearish macro) ← ALWAYS ON by default
    #   LONGS:  do NOT require MACD hist > 0 (during pullback in uptrend, MACD
    #           naturally goes negative — that's the entry! Filtering it would kill signals)
    macro_macd_fast: int = 12
    macro_macd_slow: int = 26
    macro_macd_signal: int = 9
    macro_require_hist_sign_shorts: bool = True   # MACD hist < 0 required for shorts
    macro_require_hist_sign_longs: bool = False   # MACD hist > 0 NOT required for longs
    macro_consec_bars: int = 1            # consecutive bars for shorts check

    # 1H entry
    signal_ema_period: int = 20
    atr_period: int = 14
    swing_lookback_bars: int = 10
    fresh_touch_bars: int = 3             # touch must be in last N bars (NEW)
    long_touch_tol_pct: float = 0.25
    short_touch_tol_pct: float = 0.25
    long_reclaim_pct: float = 0.20
    short_reclaim_pct: float = 0.20
    long_max_pullback_pct: float = 1.00
    short_max_pullback_pct: float = 1.00
    long_max_atr_pct_1h: float = 2.50
    short_max_atr_pct_1h: float = 2.50

    # RSI filter (NEW)
    rsi_period: int = 14
    rsi_long_max: float = 62.0   # long only when RSI < 62 (not overbought)
    rsi_short_min: float = 38.0  # short only when RSI > 38 (not oversold)
    use_rsi_filter: bool = True

    # Volume spike confirm (NEW)
    vol_period: int = 20          # average volume lookback
    vol_mult: float = 1.20        # current bar volume must be > avg * vol_mult
    use_vol_filter: bool = True

    # Weekly bias gate (optional, lighter gate)
    use_weekly_gate: bool = False  # can enable via env
    weekly_ema_fast: int = 50
    weekly_ema_slow: int = 200

    # Exits
    sl_atr_mult: float = 1.20
    swing_sl_buffer_atr: float = 0.10
    rr: float = 2.5               # was 2.2 in v1
    use_runner_exits: bool = True
    tp1_rr: float = 1.2
    tp1_frac: float = 0.50
    trail_atr_mult: float = 1.1
    # trail_atr_period_5m: number of 5m bars used for trailing ATR.
    # The initial SL uses 1H bars (atr_period × 60m), but the backtest engine
    # manages trailing stops on 5m bars.  Multiply by 12 to keep the same
    # ATR scale (14 × 60m = 14 × 12 × 5m = 168 bars of 5m data).
    trail_atr_period_5m: int = 168  # default = atr_period(14) × 12 ≈ 14h of 5m bars
    time_stop_bars_5m: int = 576   # 48h — midterm needs multi-day room (was 9h)

    # Flow control
    long_cooldown_bars: int = 72   # per-direction cooldown (NEW)
    short_cooldown_bars: int = 72
    max_signals_per_day: int = 2
    allow_longs: bool = True
    allow_shorts: bool = True


# ─── Strategy ────────────────────────────────────────────────────────────────

class BTCETHMidtermV3Strategy:
    """
    BTC/ETH medium-term pullback v3.
    4H trend (EMA50/200 + MACD macro) + 1H pullback/reclaim + RSI + volume.
    """

    def __init__(self, cfg: Optional[MidtermV3Config] = None):
        self.cfg = cfg or MidtermV3Config()
        self._load_env()
        self._allow = _env_csv_set("MTPB3_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("MTPB3_SYMBOL_DENYLIST")

        # Per-direction cooldowns
        self._long_cooldown = 0
        self._short_cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _load_env(self) -> None:
        c = self.cfg
        legacy_hist_sign = os.getenv("MTPB3_REQUIRE_HIST_SIGN")
        if legacy_hist_sign is not None and str(legacy_hist_sign).strip():
            hist_sign_default_shorts = _env_bool("MTPB3_REQUIRE_HIST_SIGN", c.macro_require_hist_sign_shorts)
            hist_sign_default_longs = _env_bool("MTPB3_REQUIRE_HIST_SIGN", c.macro_require_hist_sign_longs)
        else:
            hist_sign_default_shorts = c.macro_require_hist_sign_shorts
            hist_sign_default_longs = c.macro_require_hist_sign_longs

        c.trend_tf = os.getenv("MTPB3_TREND_TF", c.trend_tf)
        c.signal_tf = os.getenv("MTPB3_SIGNAL_TF", c.signal_tf)
        c.eval_tf_min = _env_int("MTPB3_EVAL_TF_MIN", c.eval_tf_min)
        c.trend_ema_fast = _env_int("MTPB3_TREND_EMA_FAST", c.trend_ema_fast)
        c.trend_ema_slow = _env_int("MTPB3_TREND_EMA_SLOW", c.trend_ema_slow)
        c.trend_slope_bars = _env_int("MTPB3_TREND_SLOPE_BARS", c.trend_slope_bars)
        c.trend_slope_min_pct = _env_float("MTPB3_TREND_SLOPE_MIN_PCT", c.trend_slope_min_pct)
        c.trend_min_gap_pct = _env_float("MTPB3_TREND_MIN_GAP_PCT", c.trend_min_gap_pct)
        c.macro_macd_fast = _env_int("MTPB3_MACD_FAST", c.macro_macd_fast)
        c.macro_macd_slow = _env_int("MTPB3_MACD_SLOW", c.macro_macd_slow)
        c.macro_macd_signal = _env_int("MTPB3_MACD_SIGNAL", c.macro_macd_signal)
        c.macro_require_hist_sign_shorts = _env_bool("MTPB3_REQUIRE_HIST_SIGN_SHORTS", hist_sign_default_shorts)
        c.macro_require_hist_sign_longs = _env_bool("MTPB3_REQUIRE_HIST_SIGN_LONGS", hist_sign_default_longs)
        c.macro_consec_bars = _env_int("MTPB3_MACD_CONSEC_BARS", c.macro_consec_bars)
        c.signal_ema_period = _env_int("MTPB3_SIGNAL_EMA_PERIOD", c.signal_ema_period)
        c.atr_period = _env_int("MTPB3_ATR_PERIOD", c.atr_period)
        c.swing_lookback_bars = _env_int("MTPB3_SWING_LOOKBACK_BARS", c.swing_lookback_bars)
        c.fresh_touch_bars = _env_int("MTPB3_FRESH_TOUCH_BARS", c.fresh_touch_bars)
        c.long_touch_tol_pct = _env_float("MTPB3_LONG_TOUCH_TOL_PCT", c.long_touch_tol_pct)
        c.short_touch_tol_pct = _env_float("MTPB3_SHORT_TOUCH_TOL_PCT", c.short_touch_tol_pct)
        c.long_reclaim_pct = _env_float("MTPB3_LONG_RECLAIM_PCT", c.long_reclaim_pct)
        c.short_reclaim_pct = _env_float("MTPB3_SHORT_RECLAIM_PCT", c.short_reclaim_pct)
        c.long_max_pullback_pct = _env_float("MTPB3_LONG_MAX_PULLBACK_PCT", c.long_max_pullback_pct)
        c.short_max_pullback_pct = _env_float("MTPB3_SHORT_MAX_PULLBACK_PCT", c.short_max_pullback_pct)
        c.long_max_atr_pct_1h = _env_float("MTPB3_LONG_MAX_ATR_PCT_1H", c.long_max_atr_pct_1h)
        c.short_max_atr_pct_1h = _env_float("MTPB3_SHORT_MAX_ATR_PCT_1H", c.short_max_atr_pct_1h)
        c.rsi_period = _env_int("MTPB3_RSI_PERIOD", c.rsi_period)
        c.rsi_long_max = _env_float("MTPB3_RSI_LONG_MAX", c.rsi_long_max)
        c.rsi_short_min = _env_float("MTPB3_RSI_SHORT_MIN", c.rsi_short_min)
        c.use_rsi_filter = _env_bool("MTPB3_USE_RSI_FILTER", c.use_rsi_filter)
        c.vol_period = _env_int("MTPB3_VOL_PERIOD", c.vol_period)
        c.vol_mult = _env_float("MTPB3_VOL_MULT", c.vol_mult)
        c.use_vol_filter = _env_bool("MTPB3_USE_VOL_FILTER", c.use_vol_filter)
        c.use_weekly_gate = _env_bool("MTPB3_USE_WEEKLY_GATE", c.use_weekly_gate)
        c.weekly_ema_fast = _env_int("MTPB3_WEEKLY_EMA_FAST", c.weekly_ema_fast)
        c.weekly_ema_slow = _env_int("MTPB3_WEEKLY_EMA_SLOW", c.weekly_ema_slow)
        c.sl_atr_mult = _env_float("MTPB3_SL_ATR_MULT", c.sl_atr_mult)
        c.swing_sl_buffer_atr = _env_float("MTPB3_SWING_SL_BUFFER_ATR", c.swing_sl_buffer_atr)
        c.rr = _env_float("MTPB3_RR", c.rr)
        c.use_runner_exits = _env_bool("MTPB3_USE_RUNNER_EXITS", c.use_runner_exits)
        c.tp1_rr = _env_float("MTPB3_TP1_RR", c.tp1_rr)
        c.tp1_frac = _env_float("MTPB3_TP1_FRAC", c.tp1_frac)
        c.trail_atr_mult = _env_float("MTPB3_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_atr_period_5m = _env_int("MTPB3_TRAIL_ATR_PERIOD_5M", c.trail_atr_period_5m)
        c.time_stop_bars_5m = _env_int("MTPB3_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.long_cooldown_bars = _env_int("MTPB3_LONG_COOLDOWN_BARS", c.long_cooldown_bars)
        c.short_cooldown_bars = _env_int("MTPB3_SHORT_COOLDOWN_BARS", c.short_cooldown_bars)
        c.max_signals_per_day = _env_int("MTPB3_MAX_SIGNALS_PER_DAY", c.max_signals_per_day)
        # Re-read every call so orchestrator hot-reload works
        # (don't store in cfg — read fresh in maybe_signal)

    # ─── Screen 1: 4H trend bias (EMA50/200) ─────────────────────────────────
    def _trend_bias(self, store) -> Optional[int]:
        """Returns 2=uptrend, 0=downtrend, 1=neutral, None=insufficient data."""
        lb = max(4, int(self.cfg.trend_slope_bars))
        need = max(self.cfg.trend_ema_slow + lb + 5, 260)
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, need) or []
        if len(rows) < self.cfg.trend_ema_slow + lb + 2:
            return None

        closes = [float(r[4]) for r in rows]
        ef = _ema(closes, self.cfg.trend_ema_fast)
        es = _ema(closes, self.cfg.trend_ema_slow)
        es_prev = _ema(closes[:-lb], self.cfg.trend_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)):
            return None
        if es_prev == 0:
            return None

        last_c = max(1e-12, abs(closes[-1]))
        gap_pct = abs(ef - es) / last_c * 100.0
        if gap_pct < self.cfg.trend_min_gap_pct:
            return 1  # EMAs too close — neutral

        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if ef > es and slope_pct >= self.cfg.trend_slope_min_pct:
            return 2  # uptrend
        if ef < es and slope_pct <= -self.cfg.trend_slope_min_pct:
            return 0  # downtrend
        return 1

    # ─── MACD 4H macro filter (NEW) ──────────────────────────────────────────
    def _macd_ok_for_short(self, store) -> bool:
        """True if 4H MACD histogram < 0 for consec_bars consecutive bars (bearish macro)."""
        if not self.cfg.macro_require_hist_sign_shorts:
            return True
        need = self.cfg.macro_macd_slow + self.cfg.macro_macd_signal + 20
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, need) or []
        if len(rows) < need:
            return False
        closes = [float(r[4]) for r in rows]
        consec = max(1, self.cfg.macro_consec_bars)
        for i in range(-consec, 0):
            cl_slice = closes[:len(closes) + i + 1] if i < -1 else closes
            hist = _macd_hist(cl_slice, self.cfg.macro_macd_fast,
                              self.cfg.macro_macd_slow, self.cfg.macro_macd_signal)
            if not math.isfinite(hist) or hist >= 0:
                return False
        return True

    def _macd_ok_for_long(self, store) -> bool:
        """True if 4H MACD histogram > 0 for consec_bars consecutive bars (bullish macro).
        Note: disabled by default (macro_require_hist_sign_longs=False) because during
        a healthy uptrend pullback, MACD naturally goes negative — blocking it would
        kill valid long signals. Only enable if you want strict confirmation."""
        if not self.cfg.macro_require_hist_sign_longs:
            return True
        need = self.cfg.macro_macd_slow + self.cfg.macro_macd_signal + 20
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, need) or []
        if len(rows) < need:
            return False
        closes = [float(r[4]) for r in rows]
        consec = max(1, self.cfg.macro_consec_bars)
        for i in range(-consec, 0):
            cl_slice = closes[:len(closes) + i + 1] if i < -1 else closes
            hist = _macd_hist(cl_slice, self.cfg.macro_macd_fast,
                              self.cfg.macro_macd_slow, self.cfg.macro_macd_signal)
            if not math.isfinite(hist) or hist <= 0:
                return False
        return True

    # ─── Weekly gate (optional) ───────────────────────────────────────────────
    def _weekly_bias(self, store) -> Optional[int]:
        """Weekly EMA50/200 bias. Returns 2/0/1. Uses 168-bar 1H as proxy for weekly."""
        if not self.cfg.use_weekly_gate:
            return 1  # gate disabled — neutral (pass through)
        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, 220) or []
        if len(rows) < 205:
            return 1
        closes = [float(r[4]) for r in rows]
        ef = _ema(closes, self.cfg.weekly_ema_fast)
        es = _ema(closes, self.cfg.weekly_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es)):
            return 1
        if ef > es:
            return 2
        if ef < es:
            return 0
        return 1

    # ─── Main signal ─────────────────────────────────────────────────────────
    def maybe_signal(
        self,
        store,
        ts_ms: int,
        o: float, h: float, l: float, c: float,
        v: float = 0.0,
    ) -> Optional[TradeSignal]:
        _ = (o, h, l, v)

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None

        # Regime env vars — re-read every call for hot-reload
        allow_longs = _env_bool("MTPB3_ALLOW_LONGS", self.cfg.allow_longs)
        allow_shorts = _env_bool("MTPB3_ALLOW_SHORTS", self.cfg.allow_shorts)
        if not allow_longs and not allow_shorts:
            return None

        # Per-direction cooldowns
        if self._long_cooldown > 0:
            self._long_cooldown -= 1
        if self._short_cooldown > 0:
            self._short_cooldown -= 1

        # Day signal cap
        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        # Evaluation bucket throttle
        bucket = ts_sec // max(1, int(self.cfg.eval_tf_min * 60))
        if self._last_eval_bucket == bucket:
            return None
        self._last_eval_bucket = bucket

        # ── Screen 1: 4H trend ────────────────────────────────────────────────
        bias = self._trend_bias(store)
        if bias is None or bias == 1:
            return None  # neutral / no data

        # ── Screen 2: weekly gate (optional) ─────────────────────────────────
        wb = self._weekly_bias(store)
        # Weekly must not be OPPOSITE to trade direction
        if bias == 2 and wb == 0:
            return None  # 4H bull but weekly bear — skip longs
        if bias == 0 and wb == 2:
            return None  # 4H bear but weekly bull — skip shorts

        # ── Screen 3: 1H data + ATR + EMA + RSI + Volume ─────────────────────
        need_1h = max(
            self.cfg.signal_ema_period + self.cfg.swing_lookback_bars + 10,
            max(self.cfg.vol_period, self.cfg.rsi_period) + 10,
        )
        rows_1h = store.fetch_klines(store.symbol, self.cfg.signal_tf, need_1h) or []
        min_bars = self.cfg.signal_ema_period + self.cfg.swing_lookback_bars + 3
        if len(rows_1h) < min_bars:
            return None

        highs_1h  = [float(r[2]) for r in rows_1h]
        lows_1h   = [float(r[3]) for r in rows_1h]
        closes_1h = [float(r[4]) for r in rows_1h]
        vols_1h   = [float(r[5]) for r in rows_1h] if len(rows_1h[0]) > 5 else []

        ema1h = _ema(closes_1h, self.cfg.signal_ema_period)
        atr1h = _atr_from_rows(rows_1h, self.cfg.atr_period)
        if not (math.isfinite(ema1h) and math.isfinite(atr1h) and atr1h > 0):
            return None

        cur_c  = closes_1h[-1]
        prev_c = closes_1h[-2]
        atr_pct_1h = (atr1h / max(1e-12, abs(cur_c))) * 100.0

        # RSI filter
        rsi_val = None
        if self.cfg.use_rsi_filter:
            rsi_val = _rsi(closes_1h, self.cfg.rsi_period)

        # Volume filter
        avg_vol = None
        cur_vol = None
        if self.cfg.use_vol_filter and vols_1h and len(vols_1h) >= self.cfg.vol_period:
            avg_vol = sum(vols_1h[-self.cfg.vol_period:-1]) / float(self.cfg.vol_period - 1)
            cur_vol = vols_1h[-1]

        # ── LONG SETUP ────────────────────────────────────────────────────────
        if allow_longs and bias == 2 and self._long_cooldown == 0:
            if atr_pct_1h > self.cfg.long_max_atr_pct_1h:
                return None

            # MACD macro filter: longs need MACD hist > 0
            if not self._macd_ok_for_long(store):
                return None

            # RSI gate
            if self.cfg.use_rsi_filter and rsi_val is not None:
                if not math.isfinite(rsi_val) or rsi_val > self.cfg.rsi_long_max:
                    return None  # overbought — skip

            # Volume gate
            if self.cfg.use_vol_filter and avg_vol and cur_vol:
                if cur_vol < self.cfg.vol_mult * avg_vol:
                    return None  # weak volume — skip

            # FRESH touch in last N bars (NEW)
            look = max(3, min(len(rows_1h), int(self.cfg.swing_lookback_bars)))
            fresh = max(1, min(look, int(self.cfg.fresh_touch_bars)))
            # Touch = any of the last 'look' bars had low near EMA
            recently_touched = any(
                lows_1h[i] <= ema1h * (1.0 + self.cfg.long_touch_tol_pct / 100.0)
                for i in range(-look, 0)
            )
            # Fresh = touch happened in last N bars (tighter recency check)
            fresh_touched = any(
                lows_1h[i] <= ema1h * (1.0 + self.cfg.long_touch_tol_pct / 100.0)
                for i in range(-fresh - 1, 0)
            )
            if not recently_touched or not fresh_touched:
                return None

            # Reclaim: prev bar BELOW EMA (strict), cur bar ABOVE EMA + reclaim_pct
            prev_was_below = prev_c <= ema1h * 1.001  # was below or at EMA
            cur_reclaimed = cur_c >= ema1h * (1.0 + self.cfg.long_reclaim_pct / 100.0)
            if not (prev_was_below and cur_reclaimed):
                return None

            # Max pullback check
            swing_low = min(lows_1h[-look:])
            pullback_pct = max(0.0, (ema1h - swing_low) / max(1e-12, ema1h) * 100.0)
            if pullback_pct > self.cfg.long_max_pullback_pct:
                return None

            # Build signal
            swing_sl = swing_low - self.cfg.swing_sl_buffer_atr * atr1h
            atr_sl   = float(c) - self.cfg.sl_atr_mult * atr1h
            sl = min(swing_sl, atr_sl)
            if sl >= float(c):
                return None
            risk = float(c) - sl
            tp   = float(c) + self.cfg.rr * risk
            tp1  = float(c) + self.cfg.tp1_rr * risk

            self._long_cooldown = max(0, int(self.cfg.long_cooldown_bars))
            self._day_signals += 1

            reason = (
                f"mtpb3_long 4h_ema={self.cfg.trend_ema_fast}/{self.cfg.trend_ema_slow} "
                f"rsi={rsi_val:.0f}" if rsi_val else "mtpb3_long"
            )
            sig = TradeSignal(
                strategy="btc_eth_midterm_v3",
                symbol=store.symbol,
                side="long",
                entry=float(c),
                sl=float(sl),
                tp=float(tp),
                reason=reason,
            )
            if self.cfg.use_runner_exits:
                frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
                sig.tps = [float(tp1), float(tp)]
                sig.tp_fracs = [frac, max(0.0, 1.0 - frac)]
                sig.trailing_atr_mult = max(0.0, float(self.cfg.trail_atr_mult))
                sig.trailing_atr_period = max(5, int(self.cfg.trail_atr_period_5m))
                sig.time_stop_bars = max(0, int(self.cfg.time_stop_bars_5m))
            return sig

        # ── SHORT SETUP ───────────────────────────────────────────────────────
        if allow_shorts and bias == 0 and self._short_cooldown == 0:
            if atr_pct_1h > self.cfg.short_max_atr_pct_1h:
                return None

            # MACD macro filter: shorts need MACD hist < 0
            if not self._macd_ok_for_short(store):
                return None

            # RSI gate
            if self.cfg.use_rsi_filter and rsi_val is not None:
                if not math.isfinite(rsi_val) or rsi_val < self.cfg.rsi_short_min:
                    return None  # oversold — skip

            # Volume gate
            if self.cfg.use_vol_filter and avg_vol and cur_vol:
                if cur_vol < self.cfg.vol_mult * avg_vol:
                    return None

            # FRESH touch at/above EMA in last N bars
            look = max(3, min(len(rows_1h), int(self.cfg.swing_lookback_bars)))
            fresh = max(1, min(look, int(self.cfg.fresh_touch_bars)))
            recently_touched = any(
                highs_1h[i] >= ema1h * (1.0 - self.cfg.short_touch_tol_pct / 100.0)
                for i in range(-look, 0)
            )
            fresh_touched = any(
                highs_1h[i] >= ema1h * (1.0 - self.cfg.short_touch_tol_pct / 100.0)
                for i in range(-fresh - 1, 0)
            )
            if not recently_touched or not fresh_touched:
                return None

            # Reclaim: prev bar ABOVE EMA (strict), cur bar BELOW EMA - reclaim_pct
            prev_was_above = prev_c >= ema1h * 0.999  # was above or at EMA
            cur_reclaimed = cur_c <= ema1h * (1.0 - self.cfg.short_reclaim_pct / 100.0)
            if not (prev_was_above and cur_reclaimed):
                return None

            # Max pullback check
            swing_high = max(highs_1h[-look:])
            pullback_pct = max(0.0, (swing_high - ema1h) / max(1e-12, ema1h) * 100.0)
            if pullback_pct > self.cfg.short_max_pullback_pct:
                return None

            # Build signal
            swing_sl = swing_high + self.cfg.swing_sl_buffer_atr * atr1h
            atr_sl   = float(c) + self.cfg.sl_atr_mult * atr1h
            sl = max(swing_sl, atr_sl)
            if sl <= float(c):
                return None
            risk = sl - float(c)
            tp   = float(c) - self.cfg.rr * risk
            tp1  = float(c) - self.cfg.tp1_rr * risk

            self._short_cooldown = max(0, int(self.cfg.short_cooldown_bars))
            self._day_signals += 1

            reason = (
                f"mtpb3_short 4h_ema={self.cfg.trend_ema_fast}/{self.cfg.trend_ema_slow} "
                f"rsi={rsi_val:.0f}" if rsi_val else "mtpb3_short"
            )
            sig = TradeSignal(
                strategy="btc_eth_midterm_v3",
                symbol=store.symbol,
                side="short",
                entry=float(c),
                sl=float(sl),
                tp=float(tp),
                reason=reason,
            )
            if self.cfg.use_runner_exits:
                frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
                sig.tps = [float(tp1), float(tp)]
                sig.tp_fracs = [frac, max(0.0, 1.0 - frac)]
                sig.trailing_atr_mult = max(0.0, float(self.cfg.trail_atr_mult))
                sig.trailing_atr_period = max(5, int(self.cfg.trail_atr_period_5m))
                sig.time_stop_bars = max(0, int(self.cfg.time_stop_bars_5m))
            return sig

        return None
