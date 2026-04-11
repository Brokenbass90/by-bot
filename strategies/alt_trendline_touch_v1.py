"""
alt_trendline_touch_v1 (ATT1) — Swing-pivot trendline bounce strategy

Detects genuine support/resistance trendlines by connecting ACTUAL SWING
PIVOTS (price extremes) and entering on the next confirmed touch of the line.
This mirrors how experienced traders actually draw trendlines — not via
regression of closes, but by connecting significant swing highs/lows.

Entry logic
-----------
LONG:  Last min_pivots+ swing LOWS define an ascending support trendline.
       Current bar's low touches the projected line (within touch_atr * ATR)
       and the bar CLOSES ABOVE the line (rejection confirmed).
SHORT: Last min_pivots+ swing HIGHS define a descending resistance trendline.
       Current bar's high touches the projected line and bar CLOSES BELOW.

Trendline validation
--------------------
  1. Minimum 2 pivot points to draw the line (configurable: min_pivots).
  2. Most recent pivot is ≤ max_pivot_age bars ago (line isn't stale).
  3. Slope within [min_slope_pct, max_slope_pct] per day (relative to price).
     - Prevents near-horizontal lines (use ARF1) and extreme spikes.
  4. For LONGS: ascending support (slope ≥ -long_max_neg_slope, can allow slight decline).
     For SHORTS: descending resistance (slope ≤ +short_max_pos_slope).
  5. R² of all pivot points on the fitted line ≥ min_r2 (pivots colinear enough).

Exit plan
---------
  - TP1: tp1_rr × risk (partial: tp1_frac of position)
  - TP2: tp2_rr × risk (remainder)
  - Trailing ATR stop: arms after trail_activate_rr × risk,
    trails at trail_atr_mult × ATR below peak (long) / above trough (short).
  - Break-even: moves SL to entry + be_lock_rr × risk after be_trigger_rr × risk.
  - Time stop: time_stop_bars_5m 5-minute bars (default 2016 = ~7 days).
  - Cooldown: cooldown_bars_5m 5-minute bars after any trade (default 96 = 8h).

Environment variables (ATT1_ prefix)
-------------------------------------
  ATT1_SYMBOL_ALLOWLIST      csv    symbols to trade
  ATT1_SIGNAL_TF             str    kline timeframe [60]
  ATT1_SIGNAL_LOOKBACK       int    bars to fetch [120]
  ATT1_ATR_PERIOD            int    ATR period [14]
  ATT1_RSI_PERIOD            int    RSI period [14]
  ATT1_PIVOT_LEFT            int    bars left of swing pivot [3]
  ATT1_PIVOT_RIGHT           int    bars right of swing pivot [3]
  ATT1_MIN_PIVOTS            int    min pivots to validate trendline [2]
  ATT1_MAX_PIVOT_AGE         int    max bars since last pivot [16]
  ATT1_MAX_SLOPE_PCT         float  max abs slope pct/day [4.0]
  ATT1_MIN_SLOPE_PCT         float  min abs slope pct/day [0.03]
  ATT1_LONG_MAX_NEG_SLOPE    float  allow descending support (pct/day) [0.5]
  ATT1_SHORT_MAX_POS_SLOPE   float  allow ascending resistance (pct/day) [0.5]
  ATT1_MIN_R2                float  min R² of pivot colinearity [0.80]
  ATT1_TOUCH_ATR             float  touch tolerance in ATR units [0.35]
  ATT1_REJECT_ATR            float  min close distance inside line [0.08]
  ATT1_MIN_BODY_FRAC         float  min body/range ratio [0.20]
  ATT1_RSI_LONG_MAX          float  max RSI for long [55.0]
  ATT1_RSI_SHORT_MIN         float  min RSI for short [45.0]
  ATT1_SL_ATR_MULT           float  SL buffer below/above trendline [1.10]
  ATT1_TP1_RR                float  TP1 R-multiple [1.20]
  ATT1_TP2_RR                float  TP2 R-multiple [2.50]
  ATT1_TP1_FRAC              float  fraction closed at TP1 [0.55]
  ATT1_BE_TRIGGER_RR         float  BE trigger R-multiple [1.00]
  ATT1_BE_LOCK_RR            float  BE lock-in R offset [0.02]
  ATT1_TRAIL_ATR_MULT        float  trailing ATR multiplier [1.50]
  ATT1_TRAIL_ACTIVATE_RR     float  trailing activation R [1.00]
  ATT1_TIME_STOP_BARS_5M     int    time stop in 5m bars [2016]
  ATT1_COOLDOWN_BARS_5M      int    cooldown in 5m bars [96]
  ATT1_ALLOW_LONGS           bool   enable long entries [1]
  ATT1_ALLOW_SHORTS          bool   enable short entries [1]
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .signals import TradeSignal


# ---------------------------------------------------------------------------
# Env helpers
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
# Indicator helpers
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


def _find_swing_lows(
    lows: List[float], left: int, right: int
) -> List[Tuple[int, float]]:
    """Return (bar_index, price) for all swing lows.
    A swing low at index i: lows[i] <= lows[j] for all j in [i-left, i+right]
    with strict inequality on at least one side to avoid flat bottoms.
    We scan the history excluding the last `right` bars (not yet confirmed).
    """
    pivots: List[Tuple[int, float]] = []
    n = len(lows)
    for i in range(left, n - right):
        val = lows[i]
        left_ok = all(val <= lows[i - k] for k in range(1, left + 1))
        right_ok = all(val <= lows[i + k] for k in range(1, right + 1))
        # Require at least one strict inequality to filter flat bottoms
        strict = any(val < lows[i - k] for k in range(1, left + 1)) or \
                 any(val < lows[i + k] for k in range(1, right + 1))
        if left_ok and right_ok and strict:
            pivots.append((i, val))
    return pivots


def _find_swing_highs(
    highs: List[float], left: int, right: int
) -> List[Tuple[int, float]]:
    """Return (bar_index, price) for all swing highs."""
    pivots: List[Tuple[int, float]] = []
    n = len(highs)
    for i in range(left, n - right):
        val = highs[i]
        left_ok = all(val >= highs[i - k] for k in range(1, left + 1))
        right_ok = all(val >= highs[i + k] for k in range(1, right + 1))
        strict = any(val > highs[i - k] for k in range(1, left + 1)) or \
                 any(val > highs[i + k] for k in range(1, right + 1))
        if left_ok and right_ok and strict:
            pivots.append((i, val))
    return pivots


def _fit_line_points(
    points: List[Tuple[int, float]]
) -> Tuple[float, float, float]:
    """Fit a line through (x, y) pivot points.
    Returns (slope, intercept, r_squared).
    """
    n = len(points)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]

    if n == 2:
        x0, y0 = xs[0], ys[0]
        x1, y1 = xs[1], ys[1]
        dx = x1 - x0
        if abs(dx) < 1e-12:
            return 0.0, (y0 + y1) / 2.0, 1.0
        m = (y1 - y0) / dx
        b = y0 - m * x0
        return m, b, 1.0  # 2 points always fit perfectly

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den <= 1e-12:
        return 0.0, y_mean, 0.0
    m = num / den
    b = y_mean - m * x_mean

    # R²
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (m * x + b)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / max(1e-12, ss_tot) if ss_tot > 1e-12 else 1.0
    return m, b, r2


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class AltTrendlineTouchV1Config:
    signal_tf: str = "60"
    signal_lookback: int = 120
    atr_period: int = 14
    rsi_period: int = 14

    # Pivot detection
    pivot_left: int = 3
    pivot_right: int = 3
    min_pivots: int = 2       # need at least this many pivots to form trendline
    max_pivot_age: int = 16   # last pivot must be within N bars of current bar

    # Slope constraints (pct per day, relative to price; 1H bars → 24 bars/day)
    min_slope_pct: float = 0.03   # too-flat lines are handled by ARF1
    max_slope_pct: float = 4.0    # too-steep lines are noise/reversals
    long_max_neg_slope: float = 0.5   # allow slight declining support (pct/day)
    short_max_pos_slope: float = 0.5  # allow slight rising resistance (pct/day)

    # Trendline quality
    min_r2: float = 0.80       # pivot colinearity (2 pts = 1.0 always)

    # Touch / rejection
    touch_atr: float = 0.35    # touch within this many ATR of trendline
    reject_atr: float = 0.08   # close must be this far ABOVE (long) / BELOW (short) line
    min_body_frac: float = 0.20

    # RSI filter
    rsi_long_max: float = 55.0
    rsi_short_min: float = 45.0

    # Trade management
    sl_atr_mult: float = 1.10
    tp1_rr: float = 1.20
    tp2_rr: float = 2.50
    tp1_frac: float = 0.55
    be_trigger_rr: float = 1.00
    be_lock_rr: float = 0.02
    trail_atr_mult: float = 1.50
    trail_activate_rr: float = 1.00
    time_stop_bars_5m: int = 2016   # ~7 days
    cooldown_bars_5m: int = 96      # ~8 hours

    allow_longs: bool = True
    allow_shorts: bool = True


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class AltTrendlineTouchV1Strategy:
    """Swing-pivot trendline bounce: enter on confirmed touch of a validated line."""

    def __init__(self, cfg: Optional[AltTrendlineTouchV1Config] = None):
        self.cfg = cfg or AltTrendlineTouchV1Config()
        self._load_env()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._allow: set = set()
        self._deny: set = set()
        self._refresh_lists()

    def _load_env(self) -> None:
        c = self.cfg
        c.signal_tf = os.getenv("ATT1_SIGNAL_TF", c.signal_tf)
        c.signal_lookback = _env_int("ATT1_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("ATT1_ATR_PERIOD", c.atr_period)
        c.rsi_period = _env_int("ATT1_RSI_PERIOD", c.rsi_period)
        c.pivot_left = _env_int("ATT1_PIVOT_LEFT", c.pivot_left)
        c.pivot_right = _env_int("ATT1_PIVOT_RIGHT", c.pivot_right)
        c.min_pivots = _env_int("ATT1_MIN_PIVOTS", c.min_pivots)
        c.max_pivot_age = _env_int("ATT1_MAX_PIVOT_AGE", c.max_pivot_age)
        c.min_slope_pct = _env_float("ATT1_MIN_SLOPE_PCT", c.min_slope_pct)
        c.max_slope_pct = _env_float("ATT1_MAX_SLOPE_PCT", c.max_slope_pct)
        c.long_max_neg_slope = _env_float("ATT1_LONG_MAX_NEG_SLOPE", c.long_max_neg_slope)
        c.short_max_pos_slope = _env_float("ATT1_SHORT_MAX_POS_SLOPE", c.short_max_pos_slope)
        c.min_r2 = _env_float("ATT1_MIN_R2", c.min_r2)
        c.touch_atr = _env_float("ATT1_TOUCH_ATR", c.touch_atr)
        c.reject_atr = _env_float("ATT1_REJECT_ATR", c.reject_atr)
        c.min_body_frac = _env_float("ATT1_MIN_BODY_FRAC", c.min_body_frac)
        c.rsi_long_max = _env_float("ATT1_RSI_LONG_MAX", c.rsi_long_max)
        c.rsi_short_min = _env_float("ATT1_RSI_SHORT_MIN", c.rsi_short_min)
        c.sl_atr_mult = _env_float("ATT1_SL_ATR_MULT", c.sl_atr_mult)
        c.tp1_rr = _env_float("ATT1_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("ATT1_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("ATT1_TP1_FRAC", c.tp1_frac)
        c.be_trigger_rr = _env_float("ATT1_BE_TRIGGER_RR", c.be_trigger_rr)
        c.be_lock_rr = _env_float("ATT1_BE_LOCK_RR", c.be_lock_rr)
        c.trail_atr_mult = _env_float("ATT1_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_activate_rr = _env_float("ATT1_TRAIL_ACTIVATE_RR", c.trail_activate_rr)
        c.time_stop_bars_5m = _env_int("ATT1_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("ATT1_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_longs = _env_bool("ATT1_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("ATT1_ALLOW_SHORTS", c.allow_shorts)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set(
            "ATT1_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT",
        )
        self._deny = _env_csv_set("ATT1_SYMBOL_DENYLIST")

    def _slope_pct_per_day(self, slope: float, price_ref: float, bars_per_day: int = 24) -> float:
        """Convert raw slope (price/bar) to pct/day."""
        return abs(slope) / max(1e-12, price_ref) * 100.0 * bars_per_day

    def _check_long_trendline(
        self,
        lows: List[float],
        closes: List[float],
        opens: List[float],
        highs: List[float],
        atr: float,
        rsi: float,
    ) -> Optional[Tuple[float, float]]:
        """Check ascending support trendline for long entry.
        Returns (trendline_level_at_cur, slope) if valid touch detected, else None.
        """
        c = self.cfg
        n = len(lows)

        pivots = _find_swing_lows(lows, c.pivot_left, c.pivot_right)
        if len(pivots) < c.min_pivots:
            return None

        # Use last min_pivots pivot points (most recent history)
        recent = pivots[-max(c.min_pivots, 3):]  # at most 3 most recent
        if len(recent) < c.min_pivots:
            recent = pivots[-c.min_pivots:]

        last_pivot_age = n - 1 - recent[-1][0]
        if last_pivot_age > c.max_pivot_age:
            return None  # trendline is stale

        slope, intercept, r2 = _fit_line_points(recent)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            return None

        price_ref = max(1e-12, closes[-1])
        slope_pct = self._slope_pct_per_day(slope, price_ref)

        # Slope constraints
        if slope_pct < c.min_slope_pct or slope_pct > c.max_slope_pct:
            return None
        # Long trendline direction: support must be ascending or only slightly declining
        long_slope_min = -price_ref * c.long_max_neg_slope / 100.0 / 24.0
        if slope < long_slope_min:
            return None  # declining too fast
        if r2 < c.min_r2 and len(recent) > 2:
            return None  # pivots not colinear enough (waived for 2-point line)

        tl_now = slope * (n - 1) + intercept

        # Touch check: current bar's low must be near the trendline
        cur_low = lows[-1]
        cur_close = closes[-1]
        cur_open = opens[-1]
        cur_high = highs[-1]
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range
        upper_wick = max(0.0, cur_high - max(cur_close, cur_open)) / bar_range

        touched = cur_low <= tl_now + c.touch_atr * atr
        reclaimed = cur_close >= tl_now + c.reject_atr * atr
        bullish = cur_close > cur_open
        body_ok = body_frac >= c.min_body_frac

        # The bar should have tested the trendline (low below or near) but closed above
        if touched and reclaimed and bullish and body_ok and rsi <= c.rsi_long_max:
            return (tl_now, slope)
        return None

    def _check_short_trendline(
        self,
        highs: List[float],
        closes: List[float],
        opens: List[float],
        lows: List[float],
        atr: float,
        rsi: float,
    ) -> Optional[Tuple[float, float]]:
        """Check descending resistance trendline for short entry.
        Returns (trendline_level_at_cur, slope) if valid touch detected, else None.
        """
        c = self.cfg
        n = len(highs)

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

        if slope_pct < c.min_slope_pct or slope_pct > c.max_slope_pct:
            return None
        # Short trendline: resistance should be descending or only slightly rising
        short_slope_max = price_ref * c.short_max_pos_slope / 100.0 / 24.0
        if slope > short_slope_max:
            return None  # rising too fast
        if r2 < c.min_r2 and len(recent) > 2:
            return None

        tl_now = slope * (n - 1) + intercept

        cur_high = highs[-1]
        cur_close = closes[-1]
        cur_open = opens[-1]
        cur_low = lows[-1]
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range
        upper_wick = max(0.0, cur_high - max(cur_close, cur_open)) / bar_range

        touched = cur_high >= tl_now - c.touch_atr * atr
        rejected = cur_close <= tl_now - c.reject_atr * atr
        bearish = cur_close < cur_open
        body_ok = body_frac >= c.min_body_frac
        # Bonus: upper wick confirms rejection from trendline
        has_wick = upper_wick >= 0.15

        if touched and rejected and bearish and body_ok and rsi >= c.rsi_short_min:
            return (tl_now, slope)
        return None

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
        self._refresh_lists()
        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, self.cfg.signal_lookback) or []
        if len(rows) < self.cfg.signal_lookback:
            return None

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
            return None

        cur = closes[-1]
        if cur <= 0:
            return None

        # ── LONG check ────────────────────────────────────────────────
        if self.cfg.allow_longs:
            result = self._check_long_trendline(lows, closes, opens, highs, atr, rsi)
            if result is not None:
                tl_level, slope = result
                sl = tl_level - self.cfg.sl_atr_mult * atr
                risk = cur - sl
                if risk > 0:
                    tp1 = cur + self.cfg.tp1_rr * risk
                    tp2 = cur + self.cfg.tp2_rr * risk
                    sig = TradeSignal(
                        strategy="alt_trendline_touch_v1",
                        symbol=store.symbol,
                        side="long",
                        entry=float(cur),
                        sl=float(sl),
                        tp=float(tp2),
                        tps=[float(tp1), float(tp2)],
                        tp_fracs=[
                            min(0.90, max(0.10, self.cfg.tp1_frac)),
                            max(0.05, 1.0 - min(0.90, max(0.10, self.cfg.tp1_frac))),
                        ],
                        be_trigger_rr=max(0.0, self.cfg.be_trigger_rr),
                        be_lock_rr=max(0.0, self.cfg.be_lock_rr),
                        trailing_atr_mult=max(0.0, self.cfg.trail_atr_mult),
                        trailing_atr_period=self.cfg.atr_period,
                        trail_activate_rr=max(0.0, self.cfg.trail_activate_rr),
                        time_stop_bars=max(0, self.cfg.time_stop_bars_5m),
                        reason=(
                            f"att1_long_trendline "
                            f"tl={tl_level:.4f} "
                            f"slope={slope * 24 / max(1e-12, cur) * 100:.3f}%/d "
                            f"rsi={rsi:.1f}"
                        ),
                    )
                    if sig.validate():
                        self._cooldown = max(0, self.cfg.cooldown_bars_5m)
                        return sig

        # ── SHORT check ───────────────────────────────────────────────
        if self.cfg.allow_shorts:
            result = self._check_short_trendline(highs, closes, opens, lows, atr, rsi)
            if result is not None:
                tl_level, slope = result
                sl = tl_level + self.cfg.sl_atr_mult * atr
                risk = sl - cur
                if risk > 0:
                    tp1 = cur - self.cfg.tp1_rr * risk
                    tp2 = cur - self.cfg.tp2_rr * risk
                    if tp2 > 0:
                        sig = TradeSignal(
                            strategy="alt_trendline_touch_v1",
                            symbol=store.symbol,
                            side="short",
                            entry=float(cur),
                            sl=float(sl),
                            tp=float(tp2),
                            tps=[float(tp1), float(tp2)],
                            tp_fracs=[
                                min(0.90, max(0.10, self.cfg.tp1_frac)),
                                max(0.05, 1.0 - min(0.90, max(0.10, self.cfg.tp1_frac))),
                            ],
                            be_trigger_rr=max(0.0, self.cfg.be_trigger_rr),
                            be_lock_rr=max(0.0, self.cfg.be_lock_rr),
                            trailing_atr_mult=max(0.0, self.cfg.trail_atr_mult),
                            trailing_atr_period=self.cfg.atr_period,
                            trail_activate_rr=max(0.0, self.cfg.trail_activate_rr),
                            time_stop_bars=max(0, self.cfg.time_stop_bars_5m),
                            reason=(
                                f"att1_short_trendline "
                                f"tl={tl_level:.4f} "
                                f"slope={slope * 24 / max(1e-12, cur) * 100:.3f}%/d "
                                f"rsi={rsi:.1f}"
                            ),
                        )
                        if sig.validate():
                            self._cooldown = max(0, self.cfg.cooldown_bars_5m)
                            return sig

        return None
