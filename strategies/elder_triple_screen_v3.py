"""
elder_triple_screen_v3 — Correct Elder Three-Screen system.

Key differences from v2:
  - Screen 0 (NEW, DAILY): macro trend gate — only long in daily uptrend, only short
    in daily downtrend.  This is the outermost filter that v2 was missing entirely.
    Without it the system trades against the daily macro structure.
  - Screen 1 (4h): MACD hist SLOPE + mandatory SIGN (hist must be correct side of zero)
    + 3 consecutive bars minimum + magnitude threshold.  No more 1-tick signals.
  - Screen 2 (1h): Force Index turn PLUS RSI confirmation (dual requirement).
    RSI < 42 for longs (genuine pullback), RSI > 58 for shorts.  Both must pass.
  - Screen 3 (15m): entry candle body_frac raised 0.30 → 0.50.
  - ATR quality gate: skip if 4h ATR% < 0.35% (no trend) or > 4.0% (panic chaos).

All hardened parameters are still individually overridable via ETS3_ env vars.
Strategy name reported: "elder_triple_screen_v3"
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
    e = float(values[0])
    for v in values[1:]:
        e = float(v) * k + e * (1.0 - k)
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
    lows  = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    trs: List[float] = []
    for i in range(-period, 0):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    return sum(trs) / period if trs else float("nan")


def _rsi(values: List[float], period: int) -> float:
    if period <= 0 or len(values) < period + 1:
        return float("nan")
    gains = losses = 0.0
    for i in range(-period, 0):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses += -d
    if losses < 1e-12:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


def _macd_hist_series(values: List[float], fast: int, slow: int, signal: int) -> List[float]:
    if len(values) < max(fast, slow, signal) + 5:
        return []
    fast_ema = _ema_series(values, fast)
    slow_ema = _ema_series(values, slow)
    macd = [f - s for f, s in zip(fast_ema, slow_ema)]
    sig  = _ema_series(macd, signal)
    return [m - s for m, s in zip(macd, sig)]


def _force_index_ema(rows: List[list], period: int) -> float:
    if period <= 0 or len(rows) < period + 2:
        return float("nan")
    closes = [float(r[4]) for r in rows]
    vols   = [float(r[5]) if len(r) > 5 and str(r[5]).strip() else 0.0 for r in rows]
    raw    = [(closes[i] - closes[i-1]) * vols[i] for i in range(1, len(rows))]
    if len(raw) < period + 1:
        return float("nan")
    series = _ema_series(raw, period)
    return series[-1] if series else float("nan")


@dataclass
class ElderTripleScreenV3Config:
    # ── Screen 0: DAILY macro gate (NEW in v3) ────────────────────────────────
    # Outermost filter: only long if daily EMA50 > EMA200 (macro bull).
    # Only short if daily EMA50 < EMA200 (macro bear).
    # This prevents the strategy from fighting the daily macro trend.
    macro_tf: str = "1440"          # Daily timeframe
    macro_ema_fast: int = 50        # Daily EMA50
    macro_ema_slow: int = 200       # Daily EMA200
    macro_slope_bars: int = 3       # EMA200 slope check over N bars
    macro_slope_min_pct: float = 0.05  # Min slope % to call it a trend
    macro_gap_min_pct: float = 0.30    # EMAs must be ≥0.30% apart (not in convergence)
    macro_enabled: bool = True       # ETS3_MACRO_ENABLED=0 to disable for testing

    # ── Screen 1: 4h tide (hardened from v2) ──────────────────────────────────
    trend_tf: str = "240"
    trend_mode: str = "macd_hist"
    trend_ema: int = 13
    trend_slope_bars: int = 3        # Was 2 in v2 — now requires stronger slope
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    # These were OPTIONAL in v2 — now MANDATORY defaults:
    trend_require_hist_sign: bool = True   # Histogram MUST be correct side of zero
    trend_consec_bars: int = 3             # Require 3 consecutive confirming bars
    trend_ema_gate: bool = True            # Price must be on correct side of 4h EMA
    trend_min_hist_mag: float = 0.0        # Minimum |histogram| magnitude (price units)
    # Above 0 filters tiny flickers: set via ETS3_TREND_MIN_HIST_MAG=0.0002 for BTC

    # ── Market quality gate (4h ATR%) ─────────────────────────────────────────
    # Too quiet = no trend. Too volatile = panic/chop. Both are bad for Elder.
    atr_quality_min_pct: float = 0.35   # Skip if 4h ATR < 0.35% of price
    atr_quality_max_pct: float = 4.0    # Skip if 4h ATR > 4.0% of price

    # ── Screen 2: 1h wave — dual confirmation (new in v3) ─────────────────────
    wave_tf: str = "60"
    osc_period: int = 2             # Force Index EMA period (canonical = 2)
    wave_lookback: int = 2
    # NEW: dual confirmation — Force Index turn + RSI pullback zone
    wave_rsi_period: int = 14
    wave_rsi_os: float = 42.0       # Longs: 1h RSI < 42 (genuine pullback)
    wave_rsi_ob: float = 58.0       # Shorts: 1h RSI > 58 (rally into resistance)
    wave_require_rsi: bool = True   # Must pass BOTH Force Index and RSI

    # ── Screen 3: 15m entry ───────────────────────────────────────────────────
    entry_tf: str = "15"
    risk_tf: str = "60"
    entry_retest_bars: int = 3
    entry_touch_atr_mult: float = 0.25
    entry_min_body_frac: float = 0.50   # Was 0.30 in v2 — stronger candle required
    entry_break_atr_mult: float = 0.05

    # ── Exit management ───────────────────────────────────────────────────────
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 3.0
    tp1_atr_mult: float = 1.5
    tp1_frac: float = 0.50
    trail_atr_mult: float = 0.0
    trail_activate_rr: float = 0.0
    allow_longs: bool = True
    allow_shorts: bool = True
    time_stop_bars_5m: int = 288
    cooldown_bars_5m: int = 48          # 4h cooldown (was 3h in v2)
    max_signals_per_day: int = 4        # Was 6 in v2 — fewer but higher quality


class ElderTripleScreenV3Strategy:
    """Three-screen Elder system with correct timeframe hierarchy and hardened filters.

    Screen 0 (daily):   macro gate — only trade WITH the daily EMA50/200 trend
    Screen 1 (4h):      MACD hist slope + sign + 3 consec bars + magnitude
    Screen 2 (1h):      Force Index turn + RSI in pullback zone (BOTH required)
    Screen 3 (15m):     breakout candle with 50% body minimum
    ATR quality gate:   skip if market is too quiet or too chaotic
    """

    STRATEGY_NAME = "elder_triple_screen_v3"

    def __init__(self, cfg: Optional[ElderTripleScreenV3Config] = None):
        self.cfg = cfg or ElderTripleScreenV3Config()
        self._load_env()
        self._cooldown = 0
        self._last_entry_ts: Optional[int] = None
        self._signals_today = 0
        self._last_day: Optional[int] = None
        self.last_no_signal_reason = ""

    def _load_env(self) -> None:
        c = self.cfg
        c.macro_tf             = os.getenv("ETS3_MACRO_TF", c.macro_tf)
        c.macro_ema_fast       = _env_int("ETS3_MACRO_EMA_FAST", c.macro_ema_fast)
        c.macro_ema_slow       = _env_int("ETS3_MACRO_EMA_SLOW", c.macro_ema_slow)
        c.macro_slope_bars     = _env_int("ETS3_MACRO_SLOPE_BARS", c.macro_slope_bars)
        c.macro_slope_min_pct  = _env_float("ETS3_MACRO_SLOPE_MIN_PCT", c.macro_slope_min_pct)
        c.macro_gap_min_pct    = _env_float("ETS3_MACRO_GAP_MIN_PCT", c.macro_gap_min_pct)
        c.macro_enabled        = _env_bool("ETS3_MACRO_ENABLED", c.macro_enabled)

        c.trend_tf             = os.getenv("ETS3_TREND_TF", c.trend_tf)
        c.trend_ema            = _env_int("ETS3_TREND_EMA", c.trend_ema)
        c.trend_slope_bars     = _env_int("ETS3_TREND_SLOPE_BARS", c.trend_slope_bars)
        c.macd_fast            = _env_int("ETS3_MACD_FAST", c.macd_fast)
        c.macd_slow            = _env_int("ETS3_MACD_SLOW", c.macd_slow)
        c.macd_signal          = _env_int("ETS3_MACD_SIGNAL", c.macd_signal)
        c.trend_require_hist_sign = _env_bool("ETS3_TREND_REQUIRE_HIST_SIGN", c.trend_require_hist_sign)
        c.trend_consec_bars    = _env_int("ETS3_TREND_CONSEC_BARS", c.trend_consec_bars)
        c.trend_ema_gate       = _env_bool("ETS3_TREND_EMA_GATE", c.trend_ema_gate)
        c.trend_min_hist_mag   = _env_float("ETS3_TREND_MIN_HIST_MAG", c.trend_min_hist_mag)

        c.atr_quality_min_pct  = _env_float("ETS3_ATR_MIN_PCT", c.atr_quality_min_pct)
        c.atr_quality_max_pct  = _env_float("ETS3_ATR_MAX_PCT", c.atr_quality_max_pct)

        c.wave_tf              = os.getenv("ETS3_WAVE_TF", c.wave_tf)
        c.osc_period           = _env_int("ETS3_OSC_PERIOD", c.osc_period)
        c.wave_lookback        = _env_int("ETS3_WAVE_LOOKBACK", c.wave_lookback)
        c.wave_rsi_period      = _env_int("ETS3_WAVE_RSI_PERIOD", c.wave_rsi_period)
        c.wave_rsi_os          = _env_float("ETS3_WAVE_RSI_OS", c.wave_rsi_os)
        c.wave_rsi_ob          = _env_float("ETS3_WAVE_RSI_OB", c.wave_rsi_ob)
        c.wave_require_rsi     = _env_bool("ETS3_WAVE_REQUIRE_RSI", c.wave_require_rsi)

        c.entry_tf             = os.getenv("ETS3_ENTRY_TF", c.entry_tf)
        c.risk_tf              = os.getenv("ETS3_RISK_TF", c.risk_tf)
        c.entry_retest_bars    = _env_int("ETS3_ENTRY_RETEST_BARS", c.entry_retest_bars)
        c.entry_min_body_frac  = _env_float("ETS3_ENTRY_MIN_BODY_FRAC", c.entry_min_body_frac)
        c.entry_break_atr_mult = _env_float("ETS3_ENTRY_BREAK_ATR_MULT", c.entry_break_atr_mult)

        c.sl_atr_mult          = _env_float("ETS3_SL_ATR_MULT", c.sl_atr_mult)
        c.tp_atr_mult          = _env_float("ETS3_TP_ATR_MULT", c.tp_atr_mult)
        c.tp1_atr_mult         = _env_float("ETS3_TP1_ATR_MULT", c.tp1_atr_mult)
        c.tp1_frac             = _env_float("ETS3_TP1_FRAC", c.tp1_frac)
        c.trail_atr_mult       = _env_float("ETS3_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_activate_rr    = _env_float("ETS3_TRAIL_ACTIVATE_RR", c.trail_activate_rr)
        c.allow_longs          = _env_bool("ETS3_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts         = _env_bool("ETS3_ALLOW_SHORTS", c.allow_shorts)
        c.time_stop_bars_5m    = _env_int("ETS3_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m     = _env_int("ETS3_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.max_signals_per_day  = _env_int("ETS3_MAX_SIGNALS_PER_DAY", c.max_signals_per_day)

        self._allow = _env_csv_set("ETS3_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny  = _env_csv_set("ETS3_SYMBOL_DENYLIST")

    # ── Screen 0: Daily macro gate ─────────────────────────────────────────────

    def _screen0_macro(self, store) -> Optional[str]:
        """Daily EMA50 vs EMA200 — macro trend gate.

        Returns "bullish" / "bearish" / None (neutral/insufficient data).
        None means: do not trade.
        """
        if not self.cfg.macro_enabled:
            return "any"  # skip gate
        lb = max(3, self.cfg.macro_slope_bars)
        need = max(self.cfg.macro_ema_slow + lb + 10, 220)
        rows = store.fetch_klines(store.symbol, self.cfg.macro_tf, need) or []
        if len(rows) < self.cfg.macro_ema_slow + lb + 2:
            return None
        closes = [float(r[4]) for r in rows]
        ef = _ema(closes, self.cfg.macro_ema_fast)
        es = _ema(closes, self.cfg.macro_ema_slow)
        es_prev = _ema(closes[:-lb], self.cfg.macro_ema_slow)
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)):
            return None
        if es_prev == 0:
            return None
        last_c = max(1e-12, abs(closes[-1]))
        gap_pct = abs(ef - es) / last_c * 100.0
        if gap_pct < self.cfg.macro_gap_min_pct:
            return None  # EMAs converging — no clear macro trend
        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if ef > es and slope_pct >= self.cfg.macro_slope_min_pct:
            return "bullish"
        if ef < es and slope_pct <= -self.cfg.macro_slope_min_pct:
            return "bearish"
        return None  # Mixed — sit out

    # ── Screen 1: 4h MACD hist tide ───────────────────────────────────────────

    def _screen1_trend(self, store, macro: str) -> Optional[str]:
        """4h MACD histogram — tide direction, hardened."""
        consec = max(1, self.cfg.trend_consec_bars)
        ema_len = max(self.cfg.trend_ema, 13)
        need = max(80, self.cfg.macd_slow + self.cfg.macd_signal + self.cfg.trend_slope_bars + consec + ema_len + 10)
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, need) or []
        closes = [float(r[4]) for r in rows]
        hist = _macd_hist_series(closes, self.cfg.macd_fast, self.cfg.macd_slow, self.cfg.macd_signal)
        if len(hist) < self.cfg.trend_slope_bars + consec + 2:
            return None
        cur  = hist[-1]
        prev = hist[-1 - max(1, self.cfg.trend_slope_bars)]
        if not (math.isfinite(cur) and math.isfinite(prev)):
            return None
        slope = cur - prev
        if slope > 0:
            candidate = "bullish"
        elif slope < 0:
            candidate = "bearish"
        else:
            return None

        # Must agree with macro direction
        if macro != "any":
            if macro == "bullish" and candidate != "bullish":
                return None
            if macro == "bearish" and candidate != "bearish":
                return None

        # Histogram MUST be on correct side of zero (hardened — was optional in v2)
        if self.cfg.trend_require_hist_sign:
            if candidate == "bullish" and cur <= 0:
                return None
            if candidate == "bearish" and cur >= 0:
                return None

        # Magnitude filter: ignore tiny MACD flickers
        if self.cfg.trend_min_hist_mag > 0 and abs(cur) < self.cfg.trend_min_hist_mag:
            return None

        # N consecutive bars must agree (hardened: 3 bars minimum)
        if consec > 1:
            check_bars = hist[-consec:]
            if candidate == "bullish" and not all(v > 0 for v in check_bars):
                return None
            if candidate == "bearish" and not all(v < 0 for v in check_bars):
                return None

        # EMA gate: price on correct side of 4h EMA13
        if self.cfg.trend_ema_gate and len(closes) >= ema_len:
            cur_ema = _ema(closes, ema_len)
            if math.isfinite(cur_ema):
                if candidate == "bullish" and closes[-1] < cur_ema:
                    return None
                if candidate == "bearish" and closes[-1] > cur_ema:
                    return None

        return candidate

    # ── 4h ATR quality gate ────────────────────────────────────────────────────

    def _atr_quality_ok(self, store) -> bool:
        """Skip if market is too quiet (no trend) or too chaotic (panic)."""
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, 20) or []
        atr = _atr_from_rows(rows, 14)
        if not math.isfinite(atr) or atr <= 0:
            return False
        if not rows:
            return False
        cur_price = max(1e-12, abs(float(rows[-1][4])))
        atr_pct = atr / cur_price * 100.0
        return self.cfg.atr_quality_min_pct <= atr_pct <= self.cfg.atr_quality_max_pct

    # ── Screen 2: 1h wave — dual confirmation ─────────────────────────────────

    def _screen2_wave(self, store, trend: str) -> bool:
        """Force Index turn + RSI in pullback zone (BOTH required if wave_require_rsi)."""
        need = max(50, self.cfg.osc_period + self.cfg.wave_lookback + self.cfg.wave_rsi_period + 10)
        rows = store.fetch_klines(store.symbol, self.cfg.wave_tf, need) or []
        if len(rows) < self.cfg.osc_period + 3:
            return False
        closes = [float(r[4]) for r in rows]

        # Force Index: must have turned in the pullback direction
        fi_ok = False
        for offset in range(max(0, self.cfg.wave_lookback) + 1):
            sub = rows[:len(rows) - offset] if offset else rows
            fi = _force_index_ema(sub, self.cfg.osc_period)
            if not math.isfinite(fi):
                continue
            if trend == "bullish" and fi < 0:
                fi_ok = True
                break
            if trend == "bearish" and fi > 0:
                fi_ok = True
                break
        if not fi_ok:
            return False

        # RSI: must be in pullback zone (BOTH required by default)
        if self.cfg.wave_require_rsi and len(closes) >= self.cfg.wave_rsi_period + 1:
            rsi = _rsi(closes, self.cfg.wave_rsi_period)
            if math.isfinite(rsi):
                if trend == "bullish" and rsi >= self.cfg.wave_rsi_os:
                    return False   # Price hasn't pulled back far enough
                if trend == "bearish" and rsi <= self.cfg.wave_rsi_ob:
                    return False   # Price hasn't rallied far enough
        return True

    # ── Screen 3: 15m entry ───────────────────────────────────────────────────

    def _screen3_entry(self, store, trend: str) -> Optional[str]:
        """15m breakout candle with minimum 50% body requirement."""
        n_look = max(1, self.cfg.entry_retest_bars)
        rows = store.fetch_klines(store.symbol, self.cfg.entry_tf, max(16, n_look + 8)) or []
        if len(rows) < n_look + 3:
            return None
        opens  = [float(r[1]) for r in rows]
        highs  = [float(r[2]) for r in rows]
        lows   = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        entry_atr = _atr_from_rows(rows, 14)
        if not math.isfinite(entry_atr) or entry_atr <= 0:
            return None
        cur_range = max(1e-9, highs[-1] - lows[-1])
        cur_body  = abs(closes[-1] - opens[-1]) / cur_range
        if cur_body < self.cfg.entry_min_body_frac:
            return None  # Weak doji/indecision bar — reject
        break_buf = max(0.0, self.cfg.entry_break_atr_mult) * entry_atr
        prev_high = highs[-2]
        prev_low  = lows[-2]
        # Momentum confirmation: n_look-1 bars agree with trend
        ref_ok = sum(
            1 for j in range(-1 - n_look, -1)
            if (trend == "bullish" and closes[j] > opens[j])
            or (trend == "bearish" and closes[j] < opens[j])
        )
        if ref_ok < max(1, n_look - 2):
            return None
        close_rank = (closes[-1] - lows[-1]) / cur_range
        if trend == "bullish":
            if highs[-1] >= prev_high + break_buf and close_rank >= 0.40 and closes[-1] > opens[-1]:
                return "long"
        else:
            if lows[-1] <= prev_low - break_buf and close_rank <= 0.60 and closes[-1] < opens[-1]:
                return "short"
        return None

    # ── Main entry point ──────────────────────────────────────────────────────

    def maybe_signal(
        self, store, ts_ms: int,
        o: float, h: float, l: float, c: float, v: float = 0.0,
    ) -> Optional[TradeSignal]:
        _ = (o, v)
        self.last_no_signal_reason = ""
        self._load_env()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        ts_sec = ts_ms // 1000
        day = ts_sec // 86400
        if day != self._last_day:
            self._last_day = day
            self._signals_today = 0
        if self._signals_today >= self.cfg.max_signals_per_day:
            return None

        rows_entry = store.fetch_klines(store.symbol, self.cfg.entry_tf, 5) or []
        if len(rows_entry) < 2:
            return None
        tf_ts = int(float(rows_entry[-1][0]))
        if self._last_entry_ts is not None and tf_ts == self._last_entry_ts:
            return None
        self._last_entry_ts = tf_ts

        # ── Screen 0: daily macro gate ────────────────────────────────────────
        macro = self._screen0_macro(store)
        if macro is None:
            self.last_no_signal_reason = "screen0_macro_neutral"
            return None

        # ── ATR quality gate ──────────────────────────────────────────────────
        if not self._atr_quality_ok(store):
            self.last_no_signal_reason = "atr_quality_fail"
            return None

        # ── Screen 1: 4h tide ─────────────────────────────────────────────────
        trend = self._screen1_trend(store, macro)
        if trend is None:
            self.last_no_signal_reason = "screen1_no_trend"
            return None

        # ── Screen 2: 1h wave ─────────────────────────────────────────────────
        if not self._screen2_wave(store, trend):
            self.last_no_signal_reason = f"screen2_no_wave_{trend}"
            return None

        # ── Screen 3: 15m entry ───────────────────────────────────────────────
        side = self._screen3_entry(store, trend)
        if side is None:
            self.last_no_signal_reason = f"screen3_no_entry_{trend}"
            return None

        if side == "long" and not self.cfg.allow_longs:
            return None
        if side == "short" and not self.cfg.allow_shorts:
            return None

        # ── ATR for exits ─────────────────────────────────────────────────────
        rows_risk = store.fetch_klines(store.symbol, self.cfg.risk_tf or self.cfg.entry_tf, 50) or []
        atr = _atr_from_rows(rows_risk, 14)
        if not math.isfinite(atr) or atr <= 0:
            return None

        entry_price = float(rows_entry[-1][4])
        if side == "long":
            struct_sl = min(float(rows_entry[-2][3]), float(rows_entry[-1][3])) - 0.05 * atr
            sl = min(entry_price - self.cfg.sl_atr_mult * atr, struct_sl)
            if sl >= entry_price:
                return None
            tp1 = entry_price + self.cfg.tp1_atr_mult * atr
            tp2 = entry_price + self.cfg.tp_atr_mult * atr
            if tp2 <= entry_price or tp1 <= entry_price or tp1 >= tp2:
                return None
        else:
            struct_sl = max(float(rows_entry[-2][2]), float(rows_entry[-1][2])) + 0.05 * atr
            sl = max(entry_price + self.cfg.sl_atr_mult * atr, struct_sl)
            if sl <= entry_price:
                return None
            tp1 = entry_price - self.cfg.tp1_atr_mult * atr
            tp2 = entry_price - self.cfg.tp_atr_mult * atr
            if tp2 >= entry_price or tp1 >= entry_price or tp1 <= tp2:
                return None

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        self._signals_today += 1
        frac1 = min(0.99, max(0.01, float(self.cfg.tp1_frac)))
        sig = TradeSignal(
            strategy=self.STRATEGY_NAME,
            symbol=store.symbol,
            side=side,
            entry=entry_price,
            sl=sl,
            tp=tp2,
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=14,
            trail_activate_rr=max(0.0, float(self.cfg.trail_activate_rr)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"ets3_{macro}_{trend}_{side}",
        )
        sig.tps = [tp1, tp2]
        sig.tp_fracs = [frac1, 1.0 - frac1]
        return sig if sig.validate() else None
