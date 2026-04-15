"""
alt_slope_break_v1 (ASB1) — Trendline breakout with impulse momentum

Companion strategy to ATT1 (trendline touch/bounce). While ATT1 enters when
price RESPECTS a trendline (touch → rejection → entry), ASB1 enters when
price BREAKS THROUGH a trendline with a strong impulsive candle.

The two strategies are complementary:
  ATT1: price touches support → closes back above → LONG (bounce)
  ASB1: price breaks through support → closes below with impulse → SHORT (breakdown)

This mirrors how experienced traders trade trendline breaks manually:
1. Find an ascending support trendline (higher lows)
2. Watch for a decisive close BELOW the line with a large bearish candle
3. Enter short — broken support becomes new resistance
4. SL above the broken line, TP at 2-3R

Entry logic (SHORT — primary use case in bear markets)
────────────────────────────────────────────────────
  Find ascending support trendline (swing lows, ≥ min_pivots)
  → Current bar closes BELOW the line by ≥ break_atr × ATR  (confirmed break)
  → Candle is bearish (close < open)
  → Body fraction ≥ min_body_frac (impulse — not a weak doji)
  → RSI ≤ rsi_short_max (not already deeply oversold, avoid chase)
  → SL = trendline_level + sl_atr_mult × ATR (above broken line)

Entry logic (LONG — for bull market phases)
────────────────────────────────────────────
  Find descending resistance trendline (swing highs, ≥ min_pivots)
  → Current bar closes ABOVE the line by ≥ break_atr × ATR
  → Candle is bullish (close > open)
  → Body fraction ≥ min_body_frac
  → RSI ≥ rsi_long_min (not already deeply overbought)
  → SL = trendline_level − sl_atr_mult × ATR (below broken line)

Trendline validation (same criteria as ATT1)
───────────────────────────────────────────
  • ≥ min_pivots swing pivot points to form the line
  • Most recent pivot ≤ max_pivot_age bars ago (line isn't stale)
  • Slope within [min_slope_pct, max_slope_pct] pct/day
  • R² ≥ min_r2 (pivot colinearity, waived for 2-point lines)

Exit plan
─────────
  • TP1: tp1_rr × risk (partial: tp1_frac of position)
  • TP2: tp2_rr × risk (remainder)
  • Break-even: at be_trigger_rr × risk, lock in be_lock_rr × risk
  • Time stop: time_stop_bars_5m
  • Cooldown: cooldown_bars_5m after any trade

Environment variables (ASB1_ prefix)
─────────────────────────────────────
  ASB1_SYMBOL_ALLOWLIST     csv    symbols to trade
  ASB1_SIGNAL_TF            str    kline timeframe [60]
  ASB1_SIGNAL_LOOKBACK      int    bars to fetch [120]
  ASB1_ATR_PERIOD           int    ATR period [14]
  ASB1_RSI_PERIOD           int    RSI period [14]
  ASB1_PIVOT_LEFT           int    bars left of swing pivot [3]
  ASB1_PIVOT_RIGHT          int    bars right of swing pivot [3]
  ASB1_MIN_PIVOTS           int    min pivots to form trendline [2]
  ASB1_MAX_PIVOT_AGE        int    max bars since most recent pivot [16]
  ASB1_MIN_SLOPE_PCT        float  min abs slope pct/day [0.05]
  ASB1_MAX_SLOPE_PCT        float  max abs slope pct/day [5.0]
  ASB1_MIN_R2               float  pivot R² quality floor [0.75]
  ASB1_BREAK_ATR            float  close must be this far BEYOND trendline [0.30]
  ASB1_MIN_BODY_FRAC        float  impulse body/range ratio [0.45]
  ASB1_RSI_SHORT_MAX        float  max RSI for short entry [65.0]
  ASB1_RSI_LONG_MIN         float  min RSI for long entry [35.0]
  ASB1_SL_ATR_MULT          float  SL buffer beyond broken line [0.80]
  ASB1_TP1_RR               float  TP1 R-multiple [1.5]
  ASB1_TP2_RR               float  TP2 R-multiple [3.0]
  ASB1_TP1_FRAC             float  fraction closed at TP1 [0.50]
  ASB1_BE_TRIGGER_RR        float  break-even trigger R [1.00]
  ASB1_BE_LOCK_RR           float  break-even lock offset R [0.02]
  ASB1_TIME_STOP_BARS_5M    int    time stop in 5m bars [576]
  ASB1_COOLDOWN_BARS_5M     int    cooldown in 5m bars [72]
  ASB1_ALLOW_LONGS          bool   enable long entries [1]
  ASB1_ALLOW_SHORTS         bool   enable short entries [1]
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .signals import TradeSignal


# ---------------------------------------------------------------------------
# Env helpers (identical pattern to ATT1)
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


# ---------------------------------------------------------------------------
# Indicator helpers (reuse pivot + trendline logic from ATT1)
# ---------------------------------------------------------------------------

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
    gains = losses = 0.0
    for i in range(-period, 0):
        d = values[i] - values[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    if losses <= 1e-12:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


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


def _macd_hist_last(closes: List[float], fast: int, slow: int, signal: int) -> float:
    """Return the most recent MACD histogram value."""
    need = max(fast, slow, signal) + 5
    if len(closes) < need:
        return float("nan")
    fast_ema = _ema_series(closes, fast)
    slow_ema = _ema_series(closes, slow)
    macd = [f - s for f, s in zip(fast_ema, slow_ema)]
    sig = _ema_series(macd, signal)
    hist = [m - s for m, s in zip(macd, sig)]
    return hist[-1] if hist else float("nan")


def _find_swing_lows(lows: List[float], left: int, right: int) -> List[Tuple[int, float]]:
    """Return (bar_index, price) for swing lows (same as ATT1)."""
    pivots: List[Tuple[int, float]] = []
    n = len(lows)
    for i in range(left, n - right):
        val = lows[i]
        left_ok = all(val <= lows[i - k] for k in range(1, left + 1))
        right_ok = all(val <= lows[i + k] for k in range(1, right + 1))
        strict = (any(val < lows[i - k] for k in range(1, left + 1)) or
                  any(val < lows[i + k] for k in range(1, right + 1)))
        if left_ok and right_ok and strict:
            pivots.append((i, val))
    return pivots


def _find_swing_highs(highs: List[float], left: int, right: int) -> List[Tuple[int, float]]:
    """Return (bar_index, price) for swing highs (same as ATT1)."""
    pivots: List[Tuple[int, float]] = []
    n = len(highs)
    for i in range(left, n - right):
        val = highs[i]
        left_ok = all(val >= highs[i - k] for k in range(1, left + 1))
        right_ok = all(val >= highs[i + k] for k in range(1, right + 1))
        strict = (any(val > highs[i - k] for k in range(1, left + 1)) or
                  any(val > highs[i + k] for k in range(1, right + 1)))
        if left_ok and right_ok and strict:
            pivots.append((i, val))
    return pivots


def _fit_line_points(points: List[Tuple[int, float]]) -> Tuple[float, float, float]:
    """Fit line through pivot (x, y) points. Returns (slope, intercept, r²)."""
    n = len(points)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    if n == 2:
        dx = xs[1] - xs[0]
        if abs(dx) < 1e-12:
            return 0.0, (ys[0] + ys[1]) / 2.0, 1.0
        m = (ys[1] - ys[0]) / dx
        b = ys[0] - m * xs[0]
        return m, b, 1.0
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den <= 1e-12:
        return 0.0, y_mean, 0.0
    m = num / den
    b = y_mean - m * x_mean
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (m * x + b)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / max(1e-12, ss_tot) if ss_tot > 1e-12 else 1.0
    return m, b, r2


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class AltSlopeBreakV1Config:
    # Data
    signal_tf: str = "60"
    signal_lookback: int = 120
    atr_period: int = 14
    rsi_period: int = 14

    # Pivot detection
    pivot_left: int = 3
    pivot_right: int = 3
    min_pivots: int = 2
    max_pivot_age: int = 20       # last pivot must be within this many bars (WF opt: 20)

    # Slope constraints (pct/day)
    min_slope_pct: float = 0.05   # filter nearly-flat trendlines
    max_slope_pct: float = 5.0    # filter extreme/spike lines

    # Trendline quality
    min_r2: float = 0.70          # WF-22 optimal: 0.70 (macro_mid config). Slightly more
                                  # forgiving than ATT1's 0.80 — breakout validity is
                                  # confirmed by the break itself, not just pivot alignment.

    # Breakout confirmation
    break_atr: float = 0.30       # close must be ≥ break_atr × ATR beyond the line
                                  # prevents false breaks (doji touching line = not enough)
    min_body_frac: float = 0.40   # WF-22 optimal: 0.40 (was 0.45). Slightly relaxed to
                                  # avoid missing valid breaks with moderate-size candles.

    # RSI gate — avoid chasing deeply extended moves
    rsi_short_max: float = 65.0   # short: don't enter if RSI already very low
    rsi_long_min: float = 35.0    # long: don't enter if RSI already very high

    # Macro trend filter (same concept as Elder ETS2_TREND_REQUIRE_HIST_SIGN):
    # Check 4h MACD histogram before allowing a signal.
    # macro_require_bearish=True: only short when 4h hist < 0 (confirmed downtrend)
    #   This blocks short entries during bull markets (where ASB1 shorts fail badly).
    # macro_require_bullish=True: only long when 4h hist > 0 (confirmed uptrend)
    # Set macro_tf="" to disable the check (default off for backwards compat).
    macro_tf: str = "240"          # 4h MACD histogram check timeframe
    macro_require_bearish: bool = True   # enabled by default — blocks Nov-Dec 2025 bull shorts
    macro_require_bullish: bool = False  # disabled — longs off anyway in current regime
    macro_macd_fast: int = 12
    macro_macd_slow: int = 26
    macro_macd_signal: int = 9

    # Trade management
    sl_atr_mult: float = 0.80     # SL just beyond broken trendline (tight — line = new S/R)
    tp1_rr: float = 1.5           # TP1 at 1.5R (partial 50%)
    tp2_rr: float = 3.0           # TP2 at 3.0R (let runners run)
    tp1_frac: float = 0.50        # 50% at TP1
    be_trigger_rr: float = 1.00   # move SL to break-even after 1R profit
    be_lock_rr: float = 0.02      # lock in 0.02R above entry
    time_stop_bars_5m: int = 576  # 48h time stop (576 × 5m)
    cooldown_bars_5m: int = 72    # 6h cooldown between signals

    allow_longs: bool = True
    allow_shorts: bool = True


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class AltSlopeBreakV1Strategy:
    """Trendline breakout with impulse momentum.

    SHORT: ascending support broken down with impulsive bearish candle.
    LONG:  descending resistance broken up with impulsive bullish candle.
    The broken trendline becomes new resistance/support for SL placement.
    """

    def __init__(self, cfg: Optional[AltSlopeBreakV1Config] = None):
        self.cfg = cfg or AltSlopeBreakV1Config()
        self._load_env()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._allow: set = set()
        self._deny: set = set()
        self._refresh_lists()
        self.last_no_signal_reason = ""

    def _load_env(self) -> None:
        c = self.cfg
        c.signal_tf = os.getenv("ASB1_SIGNAL_TF", c.signal_tf)
        c.signal_lookback = _env_int("ASB1_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("ASB1_ATR_PERIOD", c.atr_period)
        c.rsi_period = _env_int("ASB1_RSI_PERIOD", c.rsi_period)
        c.pivot_left = _env_int("ASB1_PIVOT_LEFT", c.pivot_left)
        c.pivot_right = _env_int("ASB1_PIVOT_RIGHT", c.pivot_right)
        c.min_pivots = _env_int("ASB1_MIN_PIVOTS", c.min_pivots)
        c.max_pivot_age = _env_int("ASB1_MAX_PIVOT_AGE", c.max_pivot_age)
        c.min_slope_pct = _env_float("ASB1_MIN_SLOPE_PCT", c.min_slope_pct)
        c.max_slope_pct = _env_float("ASB1_MAX_SLOPE_PCT", c.max_slope_pct)
        c.min_r2 = _env_float("ASB1_MIN_R2", c.min_r2)
        c.break_atr = _env_float("ASB1_BREAK_ATR", c.break_atr)
        c.min_body_frac = _env_float("ASB1_MIN_BODY_FRAC", c.min_body_frac)
        c.rsi_short_max = _env_float("ASB1_RSI_SHORT_MAX", c.rsi_short_max)
        c.rsi_long_min = _env_float("ASB1_RSI_LONG_MIN", c.rsi_long_min)
        c.sl_atr_mult = _env_float("ASB1_SL_ATR_MULT", c.sl_atr_mult)
        c.tp1_rr = _env_float("ASB1_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("ASB1_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("ASB1_TP1_FRAC", c.tp1_frac)
        c.be_trigger_rr = _env_float("ASB1_BE_TRIGGER_RR", c.be_trigger_rr)
        c.be_lock_rr = _env_float("ASB1_BE_LOCK_RR", c.be_lock_rr)
        c.time_stop_bars_5m = _env_int("ASB1_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("ASB1_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_longs = _env_bool("ASB1_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("ASB1_ALLOW_SHORTS", c.allow_shorts)
        c.macro_tf = os.getenv("ASB1_MACRO_TF", c.macro_tf).strip()
        c.macro_require_bearish = _env_bool("ASB1_MACRO_REQUIRE_BEARISH", c.macro_require_bearish)
        c.macro_require_bullish = _env_bool("ASB1_MACRO_REQUIRE_BULLISH", c.macro_require_bullish)
        c.macro_macd_fast = _env_int("ASB1_MACRO_MACD_FAST", c.macro_macd_fast)
        c.macro_macd_slow = _env_int("ASB1_MACRO_MACD_SLOW", c.macro_macd_slow)
        c.macro_macd_signal = _env_int("ASB1_MACRO_MACD_SIGNAL", c.macro_macd_signal)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set(
            "ASB1_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT",
        )
        self._deny = _env_csv_set("ASB1_SYMBOL_DENYLIST")

    def _macro_trend_ok(self, store, side: str) -> bool:
        """Optional 4h MACD histogram macro filter.

        Returns True if the macro trend agrees with the intended trade direction.
        If macro_tf is empty or data unavailable, returns True (don't block).

        SHORT trades: require 4h MACD hist < 0 (macro downtrend confirmed).
        LONG  trades: require 4h MACD hist > 0 (macro uptrend confirmed).

        This blocks the worst losing periods (Nov-Dec 2025 bull run shorts,
        or early-2025 bear market longs), similar to Elder's REQUIRE_HIST_SIGN.
        """
        c = self.cfg
        if not c.macro_tf:
            return True  # filter disabled
        if side == "short" and not c.macro_require_bearish:
            return True
        if side == "long" and not c.macro_require_bullish:
            return True

        need = max(80, c.macro_macd_slow + c.macro_macd_signal + 10)
        rows = store.fetch_klines(store.symbol, c.macro_tf, need) or []
        if len(rows) < need // 2:
            return True  # not enough data — don't block
        closes = [float(r[4]) for r in rows]
        hist = _macd_hist_last(closes, c.macro_macd_fast, c.macro_macd_slow, c.macro_macd_signal)
        if not math.isfinite(hist):
            return True
        if side == "short" and c.macro_require_bearish:
            return hist < 0   # 4h histogram must be below zero for shorts
        if side == "long" and c.macro_require_bullish:
            return hist > 0   # 4h histogram must be above zero for longs
        return True

    def _slope_pct_per_day(self, slope: float, price_ref: float, bars_per_day: int = 24) -> float:
        return abs(slope) / max(1e-12, price_ref) * 100.0 * bars_per_day

    # ------------------------------------------------------------------
    # SHORT: ascending support broken to the downside
    # ------------------------------------------------------------------

    def _check_short_breakdown(
        self,
        lows: List[float],
        highs: List[float],
        closes: List[float],
        opens: List[float],
        atr: float,
        rsi: float,
    ) -> Optional[Tuple[float, float]]:
        """Detect breakdown of an ascending support trendline.

        Returns (trendline_level_at_current_bar, slope) if breakdown confirmed.

        Logic:
          1. Find swing LOWS forming an ascending support trendline
          2. Project the line to the current bar
          3. Current bar closes BELOW the line by ≥ break_atr × ATR
          4. Bar is bearish with significant body (impulse break, not a doji)
          5. RSI not already in deeply oversold territory (avoid chasing)
        """
        c = self.cfg
        n = len(lows)

        # Ascending support uses swing LOWS (same as ATT1 long trendline)
        pivots = _find_swing_lows(lows, c.pivot_left, c.pivot_right)
        if len(pivots) < c.min_pivots:
            return None

        recent = pivots[-max(c.min_pivots, 3):]
        if len(recent) < c.min_pivots:
            recent = pivots[-c.min_pivots:]

        last_pivot_age = n - 1 - recent[-1][0]
        if last_pivot_age > c.max_pivot_age:
            return None  # stale line

        slope, intercept, r2 = _fit_line_points(recent)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            return None

        price_ref = max(1e-12, closes[-1])
        slope_pct = self._slope_pct_per_day(slope, price_ref)

        # Only ascending support lines qualify for breakdown shorts
        # (a descending "support" line is already broken, not the same pattern)
        if slope <= 0:
            return None  # must be ascending support
        if slope_pct < c.min_slope_pct or slope_pct > c.max_slope_pct:
            return None
        if r2 < c.min_r2 and len(recent) > 2:
            return None

        tl_now = slope * (n - 1) + intercept

        cur_close = closes[-1]
        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range

        # BREAKOUT confirmation:
        # 1. Close is significantly BELOW the trendline (not just touching)
        broke_below = cur_close <= tl_now - c.break_atr * atr
        # 2. Bearish impulse candle
        is_bearish = cur_close < cur_open
        # 3. Strong body — filters dojis/indecision which are false breaks
        body_ok = body_frac >= c.min_body_frac
        # 4. RSI gate: don't short into deeply oversold (RSI < 30 → already extended)
        rsi_ok = rsi <= c.rsi_short_max

        if broke_below and is_bearish and body_ok and rsi_ok:
            return (tl_now, slope)
        return None

    # ------------------------------------------------------------------
    # LONG: descending resistance broken to the upside
    # ------------------------------------------------------------------

    def _check_long_breakout(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        opens: List[float],
        atr: float,
        rsi: float,
    ) -> Optional[Tuple[float, float]]:
        """Detect breakout of a descending resistance trendline.

        Returns (trendline_level_at_current_bar, slope) if breakout confirmed.

        Logic:
          1. Find swing HIGHS forming a descending resistance trendline
          2. Project the line to the current bar
          3. Current bar closes ABOVE the line by ≥ break_atr × ATR
          4. Bar is bullish with significant body (impulse break)
          5. RSI not already in deeply overbought territory
        """
        c = self.cfg
        n = len(highs)

        # Descending resistance uses swing HIGHS (same as ATT1 short trendline)
        pivots = _find_swing_highs(highs, c.pivot_left, c.pivot_right)
        if len(pivots) < c.min_pivots:
            return None

        recent = pivots[-max(c.min_pivots, 3):]
        if len(recent) < c.min_pivots:
            recent = pivots[-c.min_pivots:]

        last_pivot_age = n - 1 - recent[-1][0]
        if last_pivot_age > c.max_pivot_age:
            return None

        slope, intercept, r2 = _fit_line_points(recent)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            return None

        price_ref = max(1e-12, closes[-1])
        slope_pct = self._slope_pct_per_day(slope, price_ref)

        # Only descending resistance qualifies for breakout longs
        if slope >= 0:
            return None  # must be descending resistance
        if slope_pct < c.min_slope_pct or slope_pct > c.max_slope_pct:
            return None
        if r2 < c.min_r2 and len(recent) > 2:
            return None

        tl_now = slope * (n - 1) + intercept

        cur_close = closes[-1]
        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range

        # BREAKOUT confirmation:
        broke_above = cur_close >= tl_now + c.break_atr * atr
        is_bullish = cur_close > cur_open
        body_ok = body_frac >= c.min_body_frac
        rsi_ok = rsi >= c.rsi_long_min  # not already overbought

        if broke_above and is_bullish and body_ok and rsi_ok:
            return (tl_now, slope)
        return None

    # ------------------------------------------------------------------
    # Main signal method
    # ------------------------------------------------------------------

    def maybe_signal(
        self,
        store,
        ts_ms: int,
        o: float,
        h: float,
        l: float,
        c: float,
        v: float = 0.0,
    ) -> Optional[TradeSignal]:
        _ = (o, h, l, c, v)
        self.last_no_signal_reason = ""
        self._load_env()
        self._refresh_lists()

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

        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, self.cfg.signal_lookback) or []
        if len(rows) < self.cfg.signal_lookback:
            self.last_no_signal_reason = "not_enough_bars"
            return None

        # Bar-close gating: only check once per closed bar
        tf_ts = int(float(rows[-1][0]))
        if self._last_tf_ts is None:
            self._last_tf_ts = tf_ts
            return None
        if tf_ts == self._last_tf_ts:
            return None
        self._last_tf_ts = tf_ts

        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        opens = [float(r[1]) for r in rows]

        atr = _atr_from_rows(rows, self.cfg.atr_period)
        rsi = _rsi(closes, self.cfg.rsi_period)
        if not (math.isfinite(atr) and math.isfinite(rsi)) or atr <= 0:
            self.last_no_signal_reason = "invalid_atr_or_rsi"
            return None

        cur_price = closes[-1]
        if cur_price <= 0:
            return None

        # ── SHORT: ascending support breakdown ────────────────────────
        if self.cfg.allow_shorts and self._macro_trend_ok(store, "short"):
            result = self._check_short_breakdown(lows, highs, closes, opens, atr, rsi)
            if result is not None:
                tl_level, slope = result
                # SL above the broken support line (now acts as resistance)
                sl = tl_level + self.cfg.sl_atr_mult * atr
                risk = sl - cur_price
                if risk > 0 and cur_price > 0:
                    tp1 = cur_price - self.cfg.tp1_rr * risk
                    tp2 = cur_price - self.cfg.tp2_rr * risk
                    if tp2 > 0 and tp1 > tp2:
                        frac = min(0.90, max(0.10, self.cfg.tp1_frac))
                        sig = TradeSignal(
                            strategy="alt_slope_break_v1",
                            symbol=store.symbol,
                            side="short",
                            entry=float(cur_price),
                            sl=float(sl),
                            tp=float(tp2),
                            tps=[float(tp1), float(tp2)],
                            tp_fracs=[frac, max(0.05, 1.0 - frac)],
                            be_trigger_rr=max(0.0, self.cfg.be_trigger_rr),
                            be_lock_rr=max(0.0, self.cfg.be_lock_rr),
                            trailing_atr_mult=0.0,   # no trailing — BE + fixed TPs are cleaner
                            trailing_atr_period=self.cfg.atr_period,
                            trail_activate_rr=0.0,
                            time_stop_bars=max(0, self.cfg.time_stop_bars_5m),
                            reason=(
                                f"asb1_short_breakdown "
                                f"tl={tl_level:.4f} "
                                f"slope={slope * 24 / max(1e-12, cur_price) * 100:.3f}%/d "
                                f"rsi={rsi:.1f}"
                            ),
                        )
                        if sig.validate():
                            self._cooldown = max(0, self.cfg.cooldown_bars_5m)
                            return sig
                    else:
                        self.last_no_signal_reason = "short_tp_invalid"
                else:
                    self.last_no_signal_reason = "short_sl_invalid"

        # ── LONG: descending resistance breakout ──────────────────────
        if self.cfg.allow_longs and self._macro_trend_ok(store, "long"):
            result = self._check_long_breakout(highs, lows, closes, opens, atr, rsi)
            if result is not None:
                tl_level, slope = result
                # SL below the broken resistance line (now acts as support)
                sl = tl_level - self.cfg.sl_atr_mult * atr
                risk = cur_price - sl
                if risk > 0:
                    tp1 = cur_price + self.cfg.tp1_rr * risk
                    tp2 = cur_price + self.cfg.tp2_rr * risk
                    if tp2 > tp1 > cur_price:
                        frac = min(0.90, max(0.10, self.cfg.tp1_frac))
                        sig = TradeSignal(
                            strategy="alt_slope_break_v1",
                            symbol=store.symbol,
                            side="long",
                            entry=float(cur_price),
                            sl=float(sl),
                            tp=float(tp2),
                            tps=[float(tp1), float(tp2)],
                            tp_fracs=[frac, max(0.05, 1.0 - frac)],
                            be_trigger_rr=max(0.0, self.cfg.be_trigger_rr),
                            be_lock_rr=max(0.0, self.cfg.be_lock_rr),
                            trailing_atr_mult=0.0,
                            trailing_atr_period=self.cfg.atr_period,
                            trail_activate_rr=0.0,
                            time_stop_bars=max(0, self.cfg.time_stop_bars_5m),
                            reason=(
                                f"asb1_long_breakout "
                                f"tl={tl_level:.4f} "
                                f"slope={slope * 24 / max(1e-12, cur_price) * 100:.3f}%/d "
                                f"rsi={rsi:.1f}"
                            ),
                        )
                        if sig.validate():
                            self._cooldown = max(0, self.cfg.cooldown_bars_5m)
                            return sig
                    else:
                        self.last_no_signal_reason = "long_tp_invalid"
                else:
                    self.last_no_signal_reason = "long_sl_invalid"

        return None
