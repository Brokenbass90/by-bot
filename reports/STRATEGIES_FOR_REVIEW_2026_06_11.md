# All Strategies For External Review — 2026-06-11

Temporary handoff document. The reviewer can edit sections directly. Codex will split returned edits back into the original files and this document can then be deleted.

Important markers: do not rename `===== BEGIN FILE:` / `===== END FILE:` lines. Keep each file path unchanged if you want edits applied automatically.

## Index

1. `strategies/alt_trendline_touch_v1.py` — LIVE CORE / NEEDS RE-REVIEW. ATT1: current main crypto engine. Review notes: slope-sign logic, no-signal reset, has_wick, RSI/cooldown, regression-vs-pivot-line design.
2. `strategies/alt_inplay_breakdown_v1.py` — LIVE CORE / NEEDS RE-REVIEW. Inplay/Breakdown: support break / failed reclaim / continuation. Review notes: tp1_rr, regime reason preservation, async legacy wrapper.
3. `strategies/alt_resistance_fade_v1.py` — LIVE CORE / NEEDS RE-REVIEW. ARF1: resistance fade/range short. Review notes: es_prev, kline/live price consistency, _env_bool, TP2 buffer.
4. `strategies/elder_triple_screen_v2.py` — CANDIDATE / NEEDS DESIGN REVIEW. Elder: decide canonical stop-order entry vs modified close-confirmed entry; Force Index EMA; hist sign; Screen 3 filters.
5. `strategies/alt_support_bounce_v1.py` — CANDIDATE / NEEDS REVIEW. Support bounce: mirror/counterpart to ARF1; not yet externally reviewed.
6. `strategies/impulse_volume_breakout_v1.py` — CANDIDATE / NEEDS REVIEW. IVB1: impulse breakout, currently telemetry/no live risk; needs review for package additivity.
7. `strategies/btc_eth_midterm_pullback.py` — CANDIDATE / NEEDS REVIEW. BTC/ETH midterm pullback; currently telemetry/no live risk; needs review.
8. `bot/liquidity_map.py` — RESEARCH / BEST NEW CANDIDATE. LSR1 liquidity hunter: needs trend split, symbol-WF, pool-to-pool target review.
9. `strategies/pair_stat_arb_v1.py` — RESEARCH / PAIR ARB. Pair stat-arb signal/diagnostics; needs funding, frozen beta, beta gate, annual WF.
10. `strategies/pair_arb_executor_v1.py` — RESEARCH / PAIR ARB. Pair stat-arb executor/intent layer; review beta-weighted execution and PnL.
11. `scripts/validate_pair_arb.py` — RESEARCH / PAIR ARB. Pair stat-arb validator; review realized PnL, funding, fee/slippage assumptions.
12. `scripts/walkforward_pair_arb.py` — RESEARCH / PAIR ARB. Pair stat-arb walk-forward runner; review IS/OOS pair/parameter selection.
13. `scripts/fast_pair_research.py` — RESEARCH / PAIR ARB. Fast pair research; review p-hacking controls and WF criteria.
14. `strategies/equities_swing_active_v1.py` — ALPACA / ACTIVE SWING. Alpaca active trailing swing; needs RSI/input/metrics fixes and wide WF.
15. `configs/alpaca_v38_hybrid_top4_candidate.env` — ALPACA / V38 EXECUTION. v38 candidate config; review non-secret execution/protection settings.
16. `scripts/equities_alpaca_paper_bridge.py` — ALPACA / V38 EXECUTION. Alpaca paper bridge; review broker-side protection, trailing/stop, real-money gate.
17. `strategies/alt_slope_break_v1.py` — MEDIUM PRIORITY / NOT REVIEWED. ASB1 slope-break; off live, needs review if revived.
18. `strategies/alt_horizontal_break_v1.py` — MEDIUM PRIORITY / NOT REVIEWED. HZBO1 horizontal breakout; off live, needs review if revived.
19. `strategies/alt_bear_regime_continuation_v1.py` — MEDIUM PRIORITY / NOT REVIEWED. BRC1 bear continuation candidate; needs review.
20. `strategies/micro_scalper_v1.py` — MEDIUM PRIORITY / NOT REVIEWED. Micro scalper; fee-sensitive, needs review only after maker/fee plan.
21. `strategies/pump_fade_smart_v1.py` — MEDIUM PRIORITY / NOT REVIEWED. Pump fade smart; needs review if still considered.
22. `strategies/liquidation_cascade_entry_v1.py` — MEDIUM PRIORITY / NOT REVIEWED. Liquidation cascade; review after liquidation feed quality is proven.
23. `strategies/funding_rate_reversion_v1.py` — MEDIUM PRIORITY / NOT REVIEWED. Funding reversion/carry; must include realized funding in validation.


====================================================================================================
===== BEGIN FILE: strategies/alt_trendline_touch_v1.py =====
GROUP: LIVE CORE / NEEDS RE-REVIEW
REVIEW_FOCUS: ATT1: current main crypto engine. Review notes: slope-sign logic, no-signal reset, has_wick, RSI/cooldown, regression-vs-pivot-line design.
====================================================================================================

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
        self._last_no_signal_reason = ""
        self._refresh_lists()

    def _no_signal(self, reason: str) -> None:
        self._last_no_signal_reason = str(reason or "unknown")

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
            self._no_signal("long_pivots_short")
            return None

        # Use last min_pivots pivot points (most recent history)
        recent = pivots[-max(c.min_pivots, 3):]  # at most 3 most recent
        if len(recent) < c.min_pivots:
            recent = pivots[-c.min_pivots:]

        last_pivot_age = n - 1 - recent[-1][0]
        if last_pivot_age > c.max_pivot_age:
            self._no_signal("long_pivot_stale")
            return None  # trendline is stale

        slope, intercept, r2 = _fit_line_points(recent)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            self._no_signal("long_line_invalid")
            return None

        price_ref = max(1e-12, closes[-1])
        slope_pct = self._slope_pct_per_day(slope, price_ref)

        # Slope constraints
        if slope_pct < c.min_slope_pct or slope_pct > c.max_slope_pct:
            self._no_signal("long_slope_invalid")
            return None
        # Long trendline direction: support must be ascending or only slightly declining
        long_slope_min = -price_ref * c.long_max_neg_slope / 100.0 / 24.0
        if slope < long_slope_min:
            self._no_signal("long_slope_direction")
            return None  # declining too fast
        if r2 < c.min_r2 and len(recent) > 2:
            self._no_signal("long_r2_low")
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
        if not touched:
            self._no_signal("long_no_touch")
        elif not reclaimed:
            self._no_signal("long_no_reject")
        elif not bullish:
            self._no_signal("long_candle_not_bullish")
        elif not body_ok:
            self._no_signal("long_body_weak")
        elif rsi > c.rsi_long_max:
            self._no_signal("long_rsi_too_high")
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
            self._no_signal("short_pivots_short")
            return None

        recent = pivots[-max(c.min_pivots, 3):]
        if len(recent) < c.min_pivots:
            recent = pivots[-c.min_pivots:]

        last_pivot_age = n - 1 - recent[-1][0]
        if last_pivot_age > c.max_pivot_age:
            self._no_signal("short_pivot_stale")
            return None

        slope, intercept, r2 = _fit_line_points(recent)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            self._no_signal("short_line_invalid")
            return None

        price_ref = max(1e-12, closes[-1])
        slope_pct = self._slope_pct_per_day(slope, price_ref)

        if slope_pct < c.min_slope_pct or slope_pct > c.max_slope_pct:
            self._no_signal("short_slope_invalid")
            return None
        # Short trendline: resistance should be descending or only slightly rising
        short_slope_max = price_ref * c.short_max_pos_slope / 100.0 / 24.0
        if slope > short_slope_max:
            self._no_signal("short_slope_direction")
            return None  # rising too fast
        if r2 < c.min_r2 and len(recent) > 2:
            self._no_signal("short_r2_low")
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
        if not touched:
            self._no_signal("short_no_touch")
        elif not rejected:
            self._no_signal("short_no_reject")
        elif not bearish:
            self._no_signal("short_candle_not_bearish")
        elif not body_ok:
            self._no_signal("short_body_weak")
        elif rsi < c.rsi_short_min:
            self._no_signal("short_rsi_too_low")
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
        self._last_no_signal_reason = ""
        self._refresh_lists()
        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            self._no_signal("symbol_not_allowed")
            return None
        if sym in self._deny:
            self._no_signal("symbol_denied")
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            self._no_signal("cooldown")
            return None

        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, self.cfg.signal_lookback) or []
        if len(rows) < self.cfg.signal_lookback:
            self._no_signal("history_short")
            return None

        tf_ts = int(float(rows[-1][0]))
        if self._last_tf_ts is None:
            self._last_tf_ts = tf_ts
            self._no_signal("first_signal_bar")
            return None
        if tf_ts == self._last_tf_ts:
            self._no_signal("same_signal_bar")
            return None
        self._last_tf_ts = tf_ts

        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        opens = [float(r[1]) for r in rows]

        atr = _atr_from_rows(rows, self.cfg.atr_period)
        rsi = _rsi(closes, self.cfg.rsi_period)
        if not (math.isfinite(atr) and math.isfinite(rsi)) or atr <= 0:
            self._no_signal("atr_or_rsi_invalid")
            return None

        cur = closes[-1]
        if cur <= 0:
            self._no_signal("price_invalid")
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
                self._no_signal("long_invalid_risk")

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
                self._no_signal("short_invalid_risk")

        if not self._last_no_signal_reason:
            self._no_signal("no_setup")
        return None

===== END FILE: strategies/alt_trendline_touch_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/alt_inplay_breakdown_v1.py =====
GROUP: LIVE CORE / NEEDS RE-REVIEW
REVIEW_FOCUS: Inplay/Breakdown: support break / failed reclaim / continuation. Review notes: tp1_rr, regime reason preservation, async legacy wrapper.
====================================================================================================

"""
alt_inplay_breakdown_v1 — independent bearish continuation / failed-reclaim short

This is intentionally no longer a mirror of the long-side in-play breakout.
The short side in crypto behaves more like:
1) a real support break / dump on 1h structure,
2) a weak reclaim back into broken support, or
3) immediate continuation while price is still compressed under that level.

The strategy keeps the existing BREAKDOWN_* env namespace so the live bot and
portfolio harness do not need a config migration.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional

from .inplay_breakout import InPlayBreakoutConfig, InPlayBreakoutWrapper
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


@dataclass
class AltInplayBreakdownV1Config:
    structure_tf: str = "60"
    entry_tf: str = "5"
    lookback_h: int = 48
    atr_period: int = 14
    break_buffer_atr: float = 0.10
    min_break_atr: float = 0.20
    min_break_body_frac: float = 0.35
    retest_touch_atr: float = 0.35
    reclaim_atr: float = 0.12
    entry_body_min_frac: float = 0.18
    max_dist_atr: float = 2.0
    rsi_max: float = 55.0
    reject_vol_mult: float = 0.0
    reject_vol_avg_bars: int = 5

    allow_failed_reclaim: bool = True
    allow_continuation: bool = True
    allow_shorts: bool = True

    regime_mode: str = "off"
    regime_tf: str = "240"
    regime_ema_fast: int = 21
    regime_ema_slow: int = 55
    # Efficiency Ratio gate: require directional trend, not just bearish bias.
    # ER = abs(net_move) / sum(abs(bar_moves)) over regime_er_bars lookback.
    # bear_trend typically ER >= 0.12; bear_chop ER < 0.05.
    # Set to 0.0 to disable (default). Recommended: 0.12 to block bear_chop entries.
    regime_min_er: float = 0.0
    regime_er_bars: int = 20

    sl_atr: float = 1.8
    rr: float = 2.0
    tp1_frac: float = 0.50
    # Breakeven protection: after TP1 (≈1R), move SL to entry+lock so the runner
    # can't give back the win. Set be_trigger_rr=0 to disable.
    be_trigger_rr: float = 1.0        # arm BE when +1R reached (≈TP1 level)
    be_lock_rr: float = 0.1           # lock SL at entry + 0.1R
    next_level_tp_enable: bool = True
    next_level_lookback_mult: float = 2.0
    next_level_buffer_atr: float = 0.30
    time_stop_bars_5m: int = 288
    cooldown_bars_5m: int = 48
    max_wait_bars_5m: int = 30
    fresh_break_bars_5m: int = 18
    flat_filter_bars_5m: int = 6
    flat_filter_max_range_atr: float = 0.90
    flat_filter_level_band_atr: float = 0.35


def _find_next_support_below(
    lows: List[float],
    current_level: float,
    atr: float,
    min_gap_atr: float = 1.0,
) -> Optional[float]:
    if not lows or not math.isfinite(current_level) or not math.isfinite(atr) or atr <= 0:
        return None
    threshold = current_level - max(0.5, float(min_gap_atr)) * atr
    candidates = sorted((float(x) for x in lows if math.isfinite(float(x)) and float(x) < threshold), reverse=True)
    if not candidates:
        return None

    clusters: List[List[float]] = [[candidates[0]]]
    cluster_gap = 0.5 * atr
    for val in candidates[1:]:
        if clusters[-1][-1] - val <= cluster_gap:
            clusters[-1].append(val)
        else:
            clusters.append([val])

    ranked = sorted(
        (
            {
                "upper": max(cluster),
                "count": len(cluster),
            }
            for cluster in clusters
        ),
        key=lambda x: (x["count"], x["upper"]),
        reverse=True,
    )
    if not ranked:
        return None

    best_count = ranked[0]["count"]
    nearest = sorted((item for item in ranked if item["count"] >= max(2, best_count)), key=lambda x: x["upper"], reverse=True)
    chosen = nearest[0] if nearest else ranked[0]
    return float(chosen["upper"])


class AltInplayBreakdownV1Strategy:
    """
    Short-only setup built around bearish structure breaks.

    Entry families:
    - failed reclaim: 1h support breaks, 5m bounces back, fails under broken level
    - dump continuation: after a real 1h break, 5m keeps selling without meaningful reclaim
    """

    STRATEGY_NAME = "alt_inplay_breakdown_v1"

    def __init__(self, cfg: Optional[AltInplayBreakdownV1Config] = None):
        self._legacy_wrapper: Optional[InPlayBreakoutWrapper] = None
        engine = str(os.getenv("BREAKDOWN_ENGINE", "modern") or "modern").strip().lower()
        if engine in {"legacy", "legacy_wrapper", "wrapper", "inplay_wrapper"}:
            legacy_cfg = InPlayBreakoutConfig()
            legacy_cfg.allow_longs = False
            legacy_cfg.allow_shorts = True
            legacy_cfg.regime_mode = "ema"
            self._legacy_wrapper = InPlayBreakoutWrapper(cfg=legacy_cfg, env_prefix="BREAKDOWN")
            self.last_no_signal_reason = ""
            return

        self.cfg = cfg or AltInplayBreakdownV1Config()

        self.cfg.structure_tf = os.getenv("BREAKDOWN_TF_BREAK", self.cfg.structure_tf)
        self.cfg.entry_tf = os.getenv("BREAKDOWN_TF_ENTRY", self.cfg.entry_tf)
        self.cfg.lookback_h = _env_int("BREAKDOWN_LOOKBACK_H", self.cfg.lookback_h)
        self.cfg.atr_period = _env_int("BREAKDOWN_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.break_buffer_atr = _env_float("BREAKDOWN_BUFFER_ATR", self.cfg.break_buffer_atr)
        self.cfg.min_break_atr = _env_float("BREAKDOWN_MIN_BREAK_ATR", self.cfg.min_break_atr)
        self.cfg.min_break_body_frac = _env_float("BREAKDOWN_IMPULSE_BODY_MIN_FRAC", self.cfg.min_break_body_frac)
        self.cfg.retest_touch_atr = _env_float("BREAKDOWN_RETEST_TOUCH_ATR", self.cfg.retest_touch_atr)
        self.cfg.reclaim_atr = _env_float("BREAKDOWN_RECLAIM_ATR", self.cfg.reclaim_atr)
        self.cfg.entry_body_min_frac = _env_float("BREAKDOWN_ENTRY_BODY_MIN_FRAC", self.cfg.entry_body_min_frac)
        self.cfg.max_dist_atr = _env_float("BREAKDOWN_MAX_DIST_ATR", self.cfg.max_dist_atr)
        self.cfg.rsi_max = _env_float("BREAKDOWN_RSI_MAX", self.cfg.rsi_max)
        self.cfg.reject_vol_mult = _env_float(
            "BREAKDOWN_REJECT_VOL_MULT",
            _env_float("BREAKDOWN_IMPULSE_VOL_MULT", self.cfg.reject_vol_mult),
        )
        self.cfg.reject_vol_avg_bars = _env_int("BREAKDOWN_REJECT_VOL_AVG_BARS", self.cfg.reject_vol_avg_bars)
        self.cfg.allow_failed_reclaim = _env_bool("BREAKDOWN_ALLOW_FAILED_RECLAIM", self.cfg.allow_failed_reclaim)
        self.cfg.allow_continuation = _env_bool("BREAKDOWN_ALLOW_CONTINUATION", self.cfg.allow_continuation)
        self.cfg.allow_shorts = _env_bool("BREAKDOWN_ALLOW_SHORTS", self.cfg.allow_shorts)

        self.cfg.regime_mode = os.getenv("BREAKDOWN_REGIME_MODE", self.cfg.regime_mode)
        self.cfg.regime_tf = os.getenv("BREAKDOWN_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_ema_fast = _env_int("BREAKDOWN_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("BREAKDOWN_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_min_er = _env_float("BREAKDOWN_REGIME_MIN_ER", self.cfg.regime_min_er)
        self.cfg.regime_er_bars = _env_int("BREAKDOWN_REGIME_ER_BARS", self.cfg.regime_er_bars)

        self.cfg.sl_atr = _env_float("BREAKDOWN_SL_ATR", self.cfg.sl_atr)
        self.cfg.rr = _env_float("BREAKDOWN_RR", self.cfg.rr)
        self.cfg.tp1_frac = _env_float("BREAKDOWN_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.be_trigger_rr = _env_float("BREAKDOWN_BE_TRIGGER_RR", self.cfg.be_trigger_rr)
        self.cfg.be_lock_rr = _env_float("BREAKDOWN_BE_LOCK_RR", self.cfg.be_lock_rr)
        self.cfg.next_level_tp_enable = _env_bool("BREAKDOWN_NEXT_LEVEL_TP_ENABLE", self.cfg.next_level_tp_enable)
        self.cfg.next_level_lookback_mult = _env_float("BREAKDOWN_NEXT_LEVEL_LOOKBACK_MULT", self.cfg.next_level_lookback_mult)
        self.cfg.next_level_buffer_atr = _env_float("BREAKDOWN_NEXT_LEVEL_BUFFER_ATR", self.cfg.next_level_buffer_atr)
        self.cfg.time_stop_bars_5m = _env_int("BREAKDOWN_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("BREAKDOWN_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_wait_bars_5m = _env_int("BREAKDOWN_MAX_RETEST_BARS", self.cfg.max_wait_bars_5m)
        self.cfg.fresh_break_bars_5m = _env_int("BREAKDOWN_FRESH_BREAK_BARS_5M", self.cfg.fresh_break_bars_5m)
        self.cfg.flat_filter_bars_5m = _env_int("BREAKDOWN_FLAT_FILTER_BARS_5M", self.cfg.flat_filter_bars_5m)
        self.cfg.flat_filter_max_range_atr = _env_float(
            "BREAKDOWN_FLAT_FILTER_MAX_RANGE_ATR",
            self.cfg.flat_filter_max_range_atr,
        )
        self.cfg.flat_filter_level_band_atr = _env_float(
            "BREAKDOWN_FLAT_FILTER_LEVEL_BAND_ATR",
            self.cfg.flat_filter_level_band_atr,
        )

        self._allow = _env_csv_set("BREAKDOWN_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("BREAKDOWN_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_structure_ts: Optional[int] = None
        self._last_entry_ts: Optional[int] = None
        self._armed: Optional[dict] = None
        self.last_no_signal_reason = ""

    def _legacy_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        if self._legacy_wrapper is None:
            return None
        sig = self._legacy_wrapper.signal(store, ts_ms, last_price)
        self.last_no_signal_reason = self._legacy_wrapper.last_no_signal_reason
        if sig is not None:
            sig.strategy = self.STRATEGY_NAME
        return sig

    async def _legacy_maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        if self._legacy_wrapper is None:
            return None
        sig = await self._legacy_wrapper.maybe_signal(store, ts_ms, last_price)
        self.last_no_signal_reason = self._legacy_wrapper.last_no_signal_reason
        if sig is not None:
            sig.strategy = self.STRATEGY_NAME
        return sig

    def _refresh_runtime_allowlists(self) -> None:
        self._allow = _env_csv_set("BREAKDOWN_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("BREAKDOWN_SYMBOL_DENYLIST")

    def _regime_ok(self, store) -> bool:
        if str(self.cfg.regime_mode).strip().lower() != "ema":
            return True
        n_bars = max(100, self.cfg.regime_ema_slow + 20, self.cfg.regime_er_bars + 5)
        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, n_bars) or []
        if len(rows) < self.cfg.regime_ema_slow + 20:
            self.last_no_signal_reason = "regime_history_short"
            return False
        closes = [float(r[4]) for r in rows]
        ema_fast = _ema(closes, self.cfg.regime_ema_fast)
        ema_slow = _ema(closes, self.cfg.regime_ema_slow)
        if not all(math.isfinite(x) for x in (ema_fast, ema_slow)):
            self.last_no_signal_reason = "regime_invalid"
            return False
        if ema_fast >= ema_slow:
            self.last_no_signal_reason = "regime_not_bearish"
            return False
        # Optional Efficiency Ratio gate: distinguish bear_trend from bear_chop.
        # ER = abs(price_start - price_end) / sum(abs(bar_to_bar_moves))
        # bear_trend: ER >= 0.12; bear_chop: ER < 0.05.
        if self.cfg.regime_min_er > 0 and self.cfg.regime_er_bars >= 2:
            er_window = closes[-self.cfg.regime_er_bars:]
            net = abs(er_window[-1] - er_window[0])
            path = sum(abs(er_window[i] - er_window[i - 1]) for i in range(1, len(er_window)))
            er = (net / path) if path > 1e-12 else 0.0
            if er < self.cfg.regime_min_er:
                self.last_no_signal_reason = f"regime_er_low_{er:.3f}"
                return False
        return True

    def _arm_structure(self, store, entry_ts: int) -> None:
        lookback = max(24, int(self.cfg.lookback_h))
        rows = store.fetch_klines(store.symbol, self.cfg.structure_tf, lookback + 10) or []
        if len(rows) < lookback + 2:
            self.last_no_signal_reason = "structure_history_short"
            return

        structure_ts = int(float(rows[-1][0]))
        if self._last_structure_ts is not None and structure_ts == self._last_structure_ts:
            self.last_no_signal_reason = "structure_unchanged"
            return
        self._last_structure_ts = structure_ts

        closes = [float(r[4]) for r in rows]
        opens = [float(r[1]) for r in rows]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]

        atr = _atr_from_rows(rows, self.cfg.atr_period)
        rsi = _rsi(closes, 14)
        if not all(math.isfinite(x) for x in (atr, rsi)) or atr <= 0:
            self.last_no_signal_reason = "structure_invalid"
            return

        support = min(lows[-(lookback + 1):-1])
        last_open = opens[-1]
        last_close = closes[-1]
        last_high = highs[-1]
        last_low = lows[-1]
        last_range = max(1e-12, last_high - last_low)
        body_frac = abs(last_close - last_open) / last_range
        dist_atr = (support - last_close) / atr

        broke_support = last_close < support - self.cfg.break_buffer_atr * atr
        bearish_impulse = last_close < last_open and body_frac >= self.cfg.min_break_body_frac

        if not self.cfg.allow_shorts:
            self.last_no_signal_reason = "shorts_disabled"
            return
        if not self._regime_ok(store):
            self.last_no_signal_reason = "regime_not_bearish"
            return
        if rsi > self.cfg.rsi_max:
            self.last_no_signal_reason = f"rsi_too_high_{rsi:.1f}"
            return
        if not broke_support:
            self.last_no_signal_reason = "no_real_break"
            return
        if not bearish_impulse:
            self.last_no_signal_reason = f"weak_break_body_{body_frac:.2f}"
            return
        if dist_atr < self.cfg.min_break_atr:
            self.last_no_signal_reason = f"break_too_small_{dist_atr:.2f}atr"
            return
        if dist_atr > self.cfg.max_dist_atr * 1.5:
            self.last_no_signal_reason = f"break_too_extended_{dist_atr:.2f}atr"
            return

        next_support = None
        if self.cfg.next_level_tp_enable:
            wider_lookback = max(lookback + 10, int(math.ceil(float(lookback) * max(1.0, float(self.cfg.next_level_lookback_mult))))) 
            rows_wide = store.fetch_klines(store.symbol, self.cfg.structure_tf, wider_lookback + 10) or []
            if rows_wide:
                all_lows = [float(r[3]) for r in rows_wide[:-1]] if len(rows_wide) > 1 else [float(r[3]) for r in rows_wide]
                next_support = _find_next_support_below(all_lows, support, atr)

        self._armed = {
            "level": support,
            "next_support": next_support,
            "atr": atr,
            "break_close": last_close,
            "break_high": last_high,
            "entry_armed_ts": int(entry_ts),
            "structure_ts": structure_ts,
        }
        self.last_no_signal_reason = "armed_breakdown"

    def _signal_from_entry_bar(self, store, rows_5m: List[list]) -> Optional[TradeSignal]:
        if self._armed is None:
            return None

        level = float(self._armed["level"])
        atr = float(self._armed["atr"])
        break_close = float(self._armed["break_close"])
        armed_ts = int(self._armed.get("entry_armed_ts") or rows_5m[-1][0])

        open_5m = float(rows_5m[-1][1])
        high_5m = float(rows_5m[-1][2])
        low_5m = float(rows_5m[-1][3])
        close_5m = float(rows_5m[-1][4])
        prev_close = float(rows_5m[-2][4]) if len(rows_5m) >= 2 else close_5m

        age_bars = max(0, int((int(float(rows_5m[-1][0])) - armed_ts) // (5 * 60_000)))
        if age_bars > max(1, int(self.cfg.fresh_break_bars_5m)):
            self._armed = None
            self.last_no_signal_reason = f"stale_break_{age_bars}bars"
            return None

        body = abs(close_5m - open_5m)
        bar_range = max(1e-12, high_5m - low_5m)
        body_frac = body / bar_range
        bearish_body = close_5m < open_5m and body_frac >= self.cfg.entry_body_min_frac

        vol_ok = True
        if self.cfg.reject_vol_mult > 0 and len(rows_5m) >= self.cfg.reject_vol_avg_bars + 1:
            tail = rows_5m[-(self.cfg.reject_vol_avg_bars + 1):-1]
            base = sum(float(r[5]) for r in tail) / float(len(tail))
            cur_vol = float(rows_5m[-1][5])
            vol_ok = base > 0 and cur_vol >= self.cfg.reject_vol_mult * base

        flat_bars = max(0, int(self.cfg.flat_filter_bars_5m))
        if flat_bars > 1 and len(rows_5m) >= flat_bars:
            recent = rows_5m[-flat_bars:]
            recent_high = max(float(r[2]) for r in recent)
            recent_low = min(float(r[3]) for r in recent)
            recent_range_atr = (recent_high - recent_low) / max(1e-12, atr)
            recent_mid = 0.5 * (recent_high + recent_low)
            if (
                recent_range_atr <= max(0.1, float(self.cfg.flat_filter_max_range_atr))
                and abs(recent_mid - level) <= max(0.05, float(self.cfg.flat_filter_level_band_atr)) * atr
            ):
                self._armed = None
                self.last_no_signal_reason = f"flat_after_break_{recent_range_atr:.2f}atr"
                return None

        touched_reclaim_zone = high_5m >= level - self.cfg.retest_touch_atr * atr
        reclaimed_below = close_5m <= level - self.cfg.reclaim_atr * atr
        extension_atr = (level - close_5m) / max(1e-12, atr)

        if close_5m > level + self.cfg.reclaim_atr * atr:
            self._armed = None
            self.last_no_signal_reason = "reclaim_invalidated"
            return None
        if extension_atr > self.cfg.max_dist_atr * 1.5:
            self._armed = None
            self.last_no_signal_reason = f"entry_too_late_{extension_atr:.2f}atr"
            return None

        reason = ""
        if (
            self.cfg.allow_failed_reclaim
            and touched_reclaim_zone
            and reclaimed_below
            and bearish_body
            and vol_ok
        ):
            reason = "bd1_failed_reclaim"
        elif (
            self.cfg.allow_continuation
            and extension_atr >= self.cfg.min_break_atr
            and extension_atr <= self.cfg.max_dist_atr
            and bearish_body
            and vol_ok
            and close_5m < prev_close
            and close_5m <= break_close + 0.25 * atr
        ):
            reason = "bd1_dump_continuation"
        else:
            self.last_no_signal_reason = "entry_not_confirmed"
            return None

        entry = close_5m
        sl_base = max(high_5m, level + 0.10 * atr)
        sl = sl_base + max(0.10, self.cfg.sl_atr * 0.25) * atr
        if sl <= entry:
            self.last_no_signal_reason = "sl_invalid"
            return None

        risk = sl - entry
        atr_tp2 = entry - self.cfg.rr * risk
        tp2 = atr_tp2
        if tp2 >= entry:
            self.last_no_signal_reason = "tp_invalid"
            return None
        tp1_rr = max(0.8, float(self.cfg.rr) * min(0.8, max(0.1, float(self.cfg.tp1_frac))))
        tp1 = entry - tp1_rr * risk
        tp1_frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
        level_tp_applied = False

        next_support = self._armed.get("next_support") if self._armed else None
        if (
            self.cfg.next_level_tp_enable
            and next_support is not None
            and math.isfinite(float(next_support))
            and float(next_support) < entry
            and float(next_support) > atr_tp2
        ):
            level_tp = float(next_support) + max(0.05, float(self.cfg.next_level_buffer_atr)) * atr
            if atr_tp2 < level_tp < entry:
                tp2 = level_tp
                tp1 = entry - (entry - tp2) * 0.5
                level_tp_applied = True

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        self._armed = None
        sig = TradeSignal(
            strategy=self.STRATEGY_NAME,
            symbol=store.symbol,
            side="short",
            entry=entry,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            be_trigger_rr=max(0.0, float(self.cfg.be_trigger_rr)),
            be_lock_rr=max(0.0, float(self.cfg.be_lock_rr)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"{reason}+level_tp" if level_tp_applied else reason,
        )
        return sig if sig.validate() else None

    def signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        if self._legacy_wrapper is not None:
            return self._legacy_signal(store, ts_ms, last_price)
        return self._run(store, ts_ms, last_price)

    async def maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        if self._legacy_wrapper is not None:
            return await self._legacy_maybe_signal(store, ts_ms, last_price)
        return self._run(store, ts_ms, last_price)

    def _run(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        _ = last_price
        self._refresh_runtime_allowlists()

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

        rows_5m = store.fetch_klines(store.symbol, self.cfg.entry_tf, 32) or []
        if len(rows_5m) < max(6, self.cfg.reject_vol_avg_bars + 1):
            self.last_no_signal_reason = "entry_history_short"
            return None
        entry_ts = int(float(rows_5m[-1][0]))
        if self._last_entry_ts is not None and entry_ts == self._last_entry_ts:
            self.last_no_signal_reason = "same_entry_bar"
            return None
        self._last_entry_ts = entry_ts

        self._arm_structure(store, entry_ts)

        if self._armed is None:
            return None

        armed_ts = int(self._armed.get("entry_armed_ts", entry_ts))
        max_wait_ms = max(1, int(self.cfg.max_wait_bars_5m)) * 5 * 60_000
        if entry_ts - armed_ts > max_wait_ms:
            self._armed = None
            self.last_no_signal_reason = "setup_timeout"
            return None

        return self._signal_from_entry_bar(store, rows_5m)

===== END FILE: strategies/alt_inplay_breakdown_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/alt_resistance_fade_v1.py =====
GROUP: LIVE CORE / NEEDS RE-REVIEW
REVIEW_FOCUS: ARF1: resistance fade/range short. Review notes: es_prev, kline/live price consistency, _env_bool, TP2 buffer.
====================================================================================================

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
    v = os.getenv(name, "1" if default else "0").lower()
    return v in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


# ---------------------------------------------------------------------------
# Indicator helpers — all O(N)
# ---------------------------------------------------------------------------

def _ema(values: List[float], period: int) -> float:
    """EMA seeded on SMA of first `period` bars (avoids cold-start bias)."""
    n = len(values)
    if n < period or period <= 0:
        return float("nan")
    # Seed = SMA of first `period` values
    cur = sum(values[:period]) / period
    k = 2.0 / (period + 1.0)
    for v in values[period:]:
        cur = v * k + cur * (1.0 - k)
    return cur


def _ema_series(values: List[float], period: int) -> List[float]:
    """Full EMA series, seeded on SMA. Returns list of same length as values."""
    n = len(values)
    out = [float("nan")] * n
    if n < period or period <= 0:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1.0)
    cur = seed
    for i in range(period, n):
        cur = values[i] * k + cur * (1.0 - k)
        out[i] = cur
    return out


def _rsi_wilder(values: List[float], period: int) -> float:
    """
    Wilder-smoothed RSI (industry standard).
    Seed: simple average of first `period` gains/losses.
    Then applies Wilder smoothing: avg = (prev_avg * (period-1) + cur) / period.
    """
    need = period * 2 + 1      # enough bars to seed + smooth
    if len(values) < need or period <= 0:
        return float("nan")

    # Compute all deltas
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains  = [max(0.0, d) for d in deltas]
    losses = [max(0.0, -d) for d in deltas]

    # Seed averages on first `period` bars
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder smoothing for remaining bars
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss < 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_from_rows(rows: List[list], period: int) -> float:
    if len(rows) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(-period, 0):
        h = float(rows[i][2])
        lo = float(rows[i][3])
        pc = float(rows[i - 1][4])
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return sum(trs) / float(period) if trs else float("nan")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class AltResistanceFadeV1Config:
    regime_tf: str = "240"
    regime_lookback: int = 60
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_max_gap_pct: float = 3.2
    regime_max_slope_pct: float = 1.8
    regime_min_atr_pct: float = 0.8
    regime_max_atr_pct: float = 6.5
    max_rebound_from_low_pct: float = 65.0

    signal_tf: str = "60"
    signal_lookback: int = 48
    signal_ema_period: int = 20
    signal_atr_period: int = 14
    min_range_pct: float = 4.5
    max_range_pct: float = 30.0
    resistance_touch_buffer_atr: float = 0.35
    reject_below_res_atr: float = 0.12
    # If True, require close < previous close for rejection confirmation.
    # Setting False relaxes the filter (may increase false positives slightly).
    reject_require_lower_close: bool = True
    min_body_frac: float = 0.22
    max_dist_from_res_pct: float = 1.4
    rsi_period: int = 14
    min_rsi: float = 58.0
    max_close_vs_ema_pct: float = 1.2

    sl_atr_mult: float = 0.85
    tp1_frac: float = 0.60
    tp2_buffer_pct: float = 0.45
    # ATR trailing stop: 0.0 = disabled, e.g. 1.5 = trail at 1.5*ATR below peak
    trail_atr_mult: float = 0.0
    trail_atr_period: int = 14
    time_stop_bars_5m: int = 576
    cooldown_bars_5m: int = 48

    # Hot config refresh: re-read env vars every N bars (0 = every bar)
    config_refresh_bars: int = 50


class AltResistanceFadeV1Strategy:
    """Short-only resistance fade for liquid alts in weak/sideways regimes."""

    def __init__(self, cfg: Optional[AltResistanceFadeV1Config] = None):
        self.cfg = cfg or AltResistanceFadeV1Config()
        self._load_runtime_config()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._last_regime_tf_ts: Optional[int] = None
        self._last_regime_ok: Optional[bool] = None
        self._last_regime_reason: str = ""
        self._bar_count: int = 0
        # Expose via both naming conventions for diagnostic script compatibility
        self.last_no_signal_reason: str = ""

    @property
    def _last_no_signal_reason(self) -> str:
        return self.last_no_signal_reason

    @_last_no_signal_reason.setter
    def _last_no_signal_reason(self, v: str) -> None:
        self.last_no_signal_reason = v

    def _no_signal(self, reason: str) -> None:
        self.last_no_signal_reason = reason

    def _load_runtime_config(self) -> None:
        c = self.cfg
        c.regime_tf               = os.getenv("ARF1_REGIME_TF", c.regime_tf)
        c.regime_lookback         = _env_int("ARF1_REGIME_LOOKBACK", c.regime_lookback)
        c.regime_ema_fast         = _env_int("ARF1_REGIME_EMA_FAST", c.regime_ema_fast)
        c.regime_ema_slow         = _env_int("ARF1_REGIME_EMA_SLOW", c.regime_ema_slow)
        c.regime_max_gap_pct      = _env_float("ARF1_REGIME_MAX_GAP_PCT", c.regime_max_gap_pct)
        c.regime_max_slope_pct    = _env_float("ARF1_REGIME_MAX_SLOPE_PCT", c.regime_max_slope_pct)
        c.regime_min_atr_pct      = _env_float("ARF1_REGIME_MIN_ATR_PCT", c.regime_min_atr_pct)
        c.regime_max_atr_pct      = _env_float("ARF1_REGIME_MAX_ATR_PCT", c.regime_max_atr_pct)
        c.max_rebound_from_low_pct = _env_float("ARF1_MAX_REBOUND_FROM_LOW_PCT", c.max_rebound_from_low_pct)

        c.signal_tf                = os.getenv("ARF1_SIGNAL_TF", c.signal_tf)
        c.signal_lookback          = _env_int("ARF1_SIGNAL_LOOKBACK", c.signal_lookback)
        c.signal_ema_period        = _env_int("ARF1_SIGNAL_EMA_PERIOD", c.signal_ema_period)
        c.signal_atr_period        = _env_int("ARF1_SIGNAL_ATR_PERIOD", c.signal_atr_period)
        c.min_range_pct            = _env_float("ARF1_MIN_RANGE_PCT", c.min_range_pct)
        c.max_range_pct            = _env_float("ARF1_MAX_RANGE_PCT", c.max_range_pct)
        c.resistance_touch_buffer_atr = _env_float("ARF1_RES_TOUCH_BUFFER_ATR", c.resistance_touch_buffer_atr)
        c.reject_below_res_atr     = _env_float("ARF1_REJECT_BELOW_RES_ATR", c.reject_below_res_atr)
        c.reject_require_lower_close = _env_bool("ARF1_REJECT_REQUIRE_LOWER_CLOSE", c.reject_require_lower_close)
        c.min_body_frac            = _env_float("ARF1_MIN_BODY_FRAC", c.min_body_frac)
        c.max_dist_from_res_pct    = _env_float("ARF1_MAX_DIST_FROM_RES_PCT", c.max_dist_from_res_pct)
        c.rsi_period               = _env_int("ARF1_RSI_PERIOD", c.rsi_period)
        c.min_rsi                  = _env_float("ARF1_MIN_RSI", c.min_rsi)
        c.max_close_vs_ema_pct     = _env_float("ARF1_MAX_CLOSE_VS_EMA_PCT", c.max_close_vs_ema_pct)

        c.sl_atr_mult              = _env_float("ARF1_SL_ATR_MULT", c.sl_atr_mult)
        c.tp1_frac                 = _env_float("ARF1_TP1_FRAC", c.tp1_frac)
        c.tp2_buffer_pct           = _env_float("ARF1_TP2_BUFFER_PCT", c.tp2_buffer_pct)
        c.trail_atr_mult           = _env_float("ARF1_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_atr_period         = _env_int("ARF1_TRAIL_ATR_PERIOD", c.trail_atr_period)
        c.time_stop_bars_5m        = _env_int("ARF1_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m         = _env_int("ARF1_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.config_refresh_bars      = _env_int("ARF1_CONFIG_REFRESH_BARS", c.config_refresh_bars)

        # Empty allowlist means "use the routed universe"; a BCH-only default
        # made backtests silently diverge from live configs.
        self._allow = _env_csv_set("ARF1_SYMBOL_ALLOWLIST", "")
        self._deny  = _env_csv_set("ARF1_SYMBOL_DENYLIST")

    def _maybe_refresh_config(self) -> None:
        """Hot reload env vars every config_refresh_bars bars (not every bar)."""
        interval = max(1, self.cfg.config_refresh_bars)
        if self._bar_count % interval == 0:
            self._load_runtime_config()

    def _regime_ok(self, store) -> bool:
        need = max(self.cfg.regime_lookback, self.cfg.regime_ema_slow + 8)
        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, need) or []
        if len(rows) < self.cfg.regime_ema_slow + 8:
            self._no_signal("regime_history_short")
            self._last_regime_reason = self.last_no_signal_reason
            return False

        tf_ts = int(float(rows[-1][0]))
        if (self._last_regime_tf_ts is not None
                and tf_ts == self._last_regime_tf_ts
                and self._last_regime_ok is not None):
            self.last_no_signal_reason = self._last_regime_reason
            return bool(self._last_regime_ok)

        closes = [float(r[4]) for r in rows]
        lows   = [float(r[3]) for r in rows]
        cur    = closes[-1]
        if cur <= 0:
            return False

        # Use _ema() with proper SMA seed (no cold-start bias)
        ef      = _ema(closes, self.cfg.regime_ema_fast)
        es      = _ema(closes, self.cfg.regime_ema_slow)
        es_prev = _ema(closes[:-6], self.cfg.regime_ema_slow)
        atr     = _atr_from_rows(rows, 14)

        if not all(math.isfinite(x) for x in (ef, es, es_prev, atr)) or atr <= 0:
            self._no_signal("regime_invalid")
            self._last_regime_reason = self.last_no_signal_reason
            return False

        gap_pct          = abs(ef - es) / cur * 100.0
        slope_pct        = abs((es - es_prev) / max(1e-12, abs(es_prev))) * 100.0
        atr_pct          = atr / cur * 100.0
        low_lookback     = min(lows[-self.cfg.regime_lookback:])
        rebound_from_low = (cur - low_lookback) / max(1e-12, low_lookback) * 100.0

        ok = (
            gap_pct      <= self.cfg.regime_max_gap_pct
            and slope_pct    <= self.cfg.regime_max_slope_pct
            and self.cfg.regime_min_atr_pct <= atr_pct <= self.cfg.regime_max_atr_pct
            and rebound_from_low <= self.cfg.max_rebound_from_low_pct
        )

        if not ok:
            if gap_pct > self.cfg.regime_max_gap_pct:
                reason = f"regime_gap_high_{gap_pct:.2f}"
            elif slope_pct > self.cfg.regime_max_slope_pct:
                reason = f"regime_slope_high_{slope_pct:.2f}"
            elif atr_pct < self.cfg.regime_min_atr_pct:
                reason = f"regime_atr_low_{atr_pct:.2f}"
            elif atr_pct > self.cfg.regime_max_atr_pct:
                reason = f"regime_atr_high_{atr_pct:.2f}"
            else:
                reason = f"regime_rebound_high_{rebound_from_low:.2f}"
            self._no_signal(reason)
        else:
            self.last_no_signal_reason = ""

        self._last_regime_tf_ts = tf_ts
        self._last_regime_ok    = bool(ok)
        self._last_regime_reason = self.last_no_signal_reason
        return bool(ok)

    def maybe_signal(
        self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0
    ) -> Optional[TradeSignal]:
        _ = (o, h, l, v)
        self.last_no_signal_reason = ""
        self._bar_count += 1
        self._maybe_refresh_config()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            self._no_signal("symbol_not_allowed")
            return None
        if sym in self._deny:
            self._no_signal("symbol_denied")
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            self._no_signal("cooldown")
            return None
        if not self._regime_ok(store):
            return None

        need = max(
            self.cfg.signal_lookback,
            self.cfg.signal_ema_period + self.cfg.rsi_period * 2 + 5,
        )
        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, need) or []
        if len(rows) < need:
            self._no_signal("signal_history_short")
            return None

        tf_ts = int(float(rows[-1][0]))
        if self._last_tf_ts is None:
            self._last_tf_ts = tf_ts
            self._no_signal("first_signal_bar")
            return None
        if tf_ts == self._last_tf_ts:
            self._no_signal("same_signal_bar")
            return None
        self._last_tf_ts = tf_ts

        highs  = [float(r[2]) for r in rows]
        lows   = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        opens  = [float(r[1]) for r in rows]

        cur  = closes[-1]
        prev = closes[-2]
        ema  = _ema(closes, self.cfg.signal_ema_period)
        atr  = _atr_from_rows(rows, self.cfg.signal_atr_period)
        rsi  = _rsi_wilder(closes, self.cfg.rsi_period)   # Wilder RSI

        if not all(math.isfinite(x) for x in (ema, atr, rsi)) or cur <= 0 or atr <= 0:
            self._no_signal("signal_invalid")
            return None

        support    = min(lows[-self.cfg.signal_lookback:-1])
        resistance = max(highs[-self.cfg.signal_lookback:-1])
        range_pct  = (resistance - support) / max(1e-12, cur) * 100.0

        if range_pct < self.cfg.min_range_pct:
            self._no_signal(f"range_too_narrow_{range_pct:.2f}")
            return None
        if range_pct > self.cfg.max_range_pct:
            self._no_signal(f"range_too_wide_{range_pct:.2f}")
            return None

        high_now  = highs[-1]
        body      = abs(cur - opens[-1])
        bar_range = max(1e-12, high_now - lows[-1])
        body_frac = body / bar_range

        # ── Resistance touch ─────────────────────────────────────────────
        touched_res = high_now >= resistance - self.cfg.resistance_touch_buffer_atr * atr
        if not touched_res:
            dist_pct = (resistance - high_now) / max(1e-12, resistance) * 100.0
            self._no_signal(f"no_res_touch_{dist_pct:.2f}")
            return None

        # ── Rejection confirmation ────────────────────────────────────────
        # Primary: close below open (bearish bar) AND close below resistance margin
        bearish_bar  = cur < opens[-1]
        closed_below = cur <= resistance - self.cfg.reject_below_res_atr * atr
        # Secondary (configurable): additionally require close < previous close
        lower_close  = (cur < prev) if self.cfg.reject_require_lower_close else True

        if not (bearish_bar and closed_below and lower_close):
            if not bearish_bar:
                self._no_signal("no_reject_bullish_bar")
            elif not closed_below:
                self._no_signal("no_reject_back")
            else:
                self._no_signal("no_reject_lower_close")
            return None

        # ── Additional filters ────────────────────────────────────────────
        if body_frac < self.cfg.min_body_frac:
            self._no_signal(f"body_weak_{body_frac:.2f}")
            return None

        dist_from_res_pct = (resistance - cur) / max(1e-12, resistance) * 100.0
        if dist_from_res_pct > self.cfg.max_dist_from_res_pct:
            self._no_signal(f"dist_too_far_{dist_from_res_pct:.2f}")
            return None

        if rsi < self.cfg.min_rsi:
            self._no_signal(f"rsi_too_low_{rsi:.2f}")
            return None

        close_vs_ema_pct = (cur - ema) / max(1e-12, ema) * 100.0
        if close_vs_ema_pct > self.cfg.max_close_vs_ema_pct:
            self._no_signal(f"ema_extension_high_{close_vs_ema_pct:.2f}")
            return None

        # ── SL / TP geometry ─────────────────────────────────────────────
        entry_price = float(c)        # live tick price, not kline close
        sl  = resistance + self.cfg.sl_atr_mult * atr
        tp2 = support * (1.0 + self.cfg.tp2_buffer_pct / 100.0)

        if sl <= entry_price:
            self._no_signal("sl_below_entry")
            return None
        if tp2 >= entry_price:
            self._no_signal("tp_above_entry")
            return None

        # tp1 = 55% of the way from entry to tp2
        tp1      = entry_price - (entry_price - tp2) * 0.55
        tp1_frac = min(0.9, max(0.1, self.cfg.tp1_frac))

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="alt_resistance_fade_v1",
            symbol=store.symbol,
            side="short",
            entry=entry_price,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=max(5, int(self.cfg.trail_atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason="arf1_alt_resistance_fade",
        )
        if not sig.validate():
            self._no_signal("signal_invalid_post")
            return None
        return sig

===== END FILE: strategies/alt_resistance_fade_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/elder_triple_screen_v2.py =====
GROUP: CANDIDATE / NEEDS DESIGN REVIEW
REVIEW_FOCUS: Elder: decide canonical stop-order entry vs modified close-confirmed entry; Force Index EMA; hist sign; Screen 3 filters.
====================================================================================================

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
    # Breakeven protection — arm BE at TP1 hit (≈1R), lock small profit cushion.
    # Prevents TP1-then-full-stop-out losses; after TP1 the runner is free.
    # Set be_trigger_rr=0 to disable.
    be_trigger_rr: float = 1.0         # arm BE when +1R reached
    be_lock_rr: float = 0.1            # lock SL at entry + 0.1R


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
        self.cfg.be_trigger_rr = _env_float("ETS2_BE_TRIGGER_RR", self.cfg.be_trigger_rr)
        self.cfg.be_lock_rr = _env_float("ETS2_BE_LOCK_RR", self.cfg.be_lock_rr)

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
            be_trigger_rr=max(0.0, float(self.cfg.be_trigger_rr)),
            be_lock_rr=max(0.0, float(self.cfg.be_lock_rr)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"ets2_{trend}_{side}",
        )
        # Multi-TP: 50% at TP1 (1.5 ATR = 1R), 50% at TP2 (3.0 ATR = 2R)
        sig.tps = [tp1, tp2]
        sig.tp_fracs = [frac1, 1.0 - frac1]
        return sig if sig.validate() else None

===== END FILE: strategies/elder_triple_screen_v2.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/alt_support_bounce_v1.py =====
GROUP: CANDIDATE / NEEDS REVIEW
REVIEW_FOCUS: Support bounce: mirror/counterpart to ARF1; not yet externally reviewed.
====================================================================================================

"""
alt_support_bounce_v1 — Long counterpart of alt_resistance_fade_v1

LONG strategy that buys at key support levels when market is in uptrend
or range-bound. Mirror logic of ARF1 but for longs.

Key features:
- 4h regime check: EMA20/EMA50 gap small (flat) OR EMA20 > EMA50 (uptrend)
- 1h signal: price touches 72-bar low support, then bounces with bullish bar
- RSI(14) on 1h <= 42 (oversold area)
- Bullish confirmation: close > open, body >= 22% of range
- Close within 1.4% below 20-period EMA (not too extended)
- SL: below support - 0.85 × ATR
- TP1: 55% to resistance
- TP2: resistance - 0.45% buffer

Typical env config:
    ASB1_SYMBOL_ALLOWLIST=ETHUSDT,ADAUSDT,DOTUSDT
    ASB1_MIN_RSI=30.0
    ASB1_MAX_RSI=42.0
    ASB1_SL_ATR_MULT=0.85
    ASB1_TP1_FRAC=0.60
    ASB1_ALLOW_LONGS=1
    ASB1_ALLOW_SHORTS=0
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


@dataclass
class AltSupportBounceV1Config:
    # Regime check on 4h
    regime_tf: str = "240"
    regime_lookback: int = 60
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_max_gap_pct: float = 3.2
    regime_max_slope_pct: float = 1.8
    regime_min_atr_pct: float = 0.8
    regime_max_atr_pct: float = 6.5

    # Signal on 1h
    signal_tf: str = "60"
    signal_lookback: int = 72
    signal_ema_period: int = 20
    signal_atr_period: int = 14
    min_range_pct: float = 5.0
    max_range_pct: float = 30.0
    support_touch_buffer_atr: float = 0.35
    reclaim_above_supp_atr: float = 0.12
    min_body_frac: float = 0.22
    max_close_vs_ema_pct: float = 1.4
    rsi_period: int = 14
    min_rsi: float = 30.0
    max_rsi: float = 42.0

    # Exit management
    sl_atr_mult: float = 0.85
    tp1_frac: float = 0.60
    tp2_buffer_pct: float = 0.45
    trail_atr_mult: float = 0.0
    trail_atr_period: int = 14
    time_stop_bars_5m: int = 576
    cooldown_bars_5m: int = 72
    allow_longs: bool = True
    allow_shorts: bool = False


class AltSupportBounceV1Strategy:
    """Long-only support bounce strategy for uptrend/range regimes."""

    def __init__(self, cfg: Optional[AltSupportBounceV1Config] = None):
        self.cfg = cfg or AltSupportBounceV1Config()

        self.cfg.regime_tf = os.getenv("ASB1_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_lookback = _env_int("ASB1_REGIME_LOOKBACK", self.cfg.regime_lookback)
        self.cfg.regime_ema_fast = _env_int("ASB1_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("ASB1_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_max_gap_pct = _env_float("ASB1_REGIME_MAX_GAP_PCT", self.cfg.regime_max_gap_pct)
        self.cfg.regime_max_slope_pct = _env_float("ASB1_REGIME_MAX_SLOPE_PCT", self.cfg.regime_max_slope_pct)
        self.cfg.regime_min_atr_pct = _env_float("ASB1_REGIME_MIN_ATR_PCT", self.cfg.regime_min_atr_pct)
        self.cfg.regime_max_atr_pct = _env_float("ASB1_REGIME_MAX_ATR_PCT", self.cfg.regime_max_atr_pct)

        self.cfg.signal_tf = os.getenv("ASB1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_lookback = _env_int("ASB1_SIGNAL_LOOKBACK", self.cfg.signal_lookback)
        self.cfg.signal_ema_period = _env_int("ASB1_SIGNAL_EMA_PERIOD", self.cfg.signal_ema_period)
        self.cfg.signal_atr_period = _env_int("ASB1_SIGNAL_ATR_PERIOD", self.cfg.signal_atr_period)
        self.cfg.min_range_pct = _env_float("ASB1_MIN_RANGE_PCT", self.cfg.min_range_pct)
        self.cfg.max_range_pct = _env_float("ASB1_MAX_RANGE_PCT", self.cfg.max_range_pct)
        self.cfg.support_touch_buffer_atr = _env_float("ASB1_SUPP_TOUCH_BUFFER_ATR", self.cfg.support_touch_buffer_atr)
        self.cfg.reclaim_above_supp_atr = _env_float("ASB1_RECLAIM_ABOVE_SUPP_ATR", self.cfg.reclaim_above_supp_atr)
        self.cfg.min_body_frac = _env_float("ASB1_MIN_BODY_FRAC", self.cfg.min_body_frac)
        self.cfg.max_close_vs_ema_pct = _env_float("ASB1_MAX_CLOSE_VS_EMA_PCT", self.cfg.max_close_vs_ema_pct)
        self.cfg.rsi_period = _env_int("ASB1_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.min_rsi = _env_float("ASB1_MIN_RSI", self.cfg.min_rsi)
        self.cfg.max_rsi = _env_float("ASB1_MAX_RSI", self.cfg.max_rsi)

        self.cfg.sl_atr_mult = _env_float("ASB1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_frac = _env_float("ASB1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.tp2_buffer_pct = _env_float("ASB1_TP2_BUFFER_PCT", self.cfg.tp2_buffer_pct)
        self.cfg.trail_atr_mult = _env_float("ASB1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.trail_atr_period = _env_int("ASB1_TRAIL_ATR_PERIOD", self.cfg.trail_atr_period)
        self.cfg.time_stop_bars_5m = _env_int("ASB1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("ASB1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("ASB1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("ASB1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("ASB1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("ASB1_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._last_regime_tf_ts: Optional[int] = None
        self._last_regime_ok: Optional[bool] = None
        self.last_no_signal_reason = ""

    def _refresh_runtime_allowlists(self) -> None:
        self._allow = _env_csv_set("ASB1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("ASB1_SYMBOL_DENYLIST")

    def _regime_ok(self, store) -> bool:
        """Check if regime is bullish/flat (EMA20 >= EMA50 or gap small on 4h)."""
        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, max(self.cfg.regime_lookback, self.cfg.regime_ema_slow + 8)) or []
        if len(rows) < self.cfg.regime_ema_slow + 8:
            return False

        tf_ts = int(float(rows[-1][0]))
        if self._last_regime_tf_ts is not None and tf_ts == self._last_regime_tf_ts and self._last_regime_ok is not None:
            return bool(self._last_regime_ok)

        closes = [float(r[4]) for r in rows]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        cur = closes[-1]
        if cur <= 0:
            return False

        ema_fast = _ema(closes, self.cfg.regime_ema_fast)
        ema_slow = _ema(closes, self.cfg.regime_ema_slow)
        ema_slow_prev = _ema(closes[:-6], self.cfg.regime_ema_slow)
        atr = _atr_from_rows(rows, 14)
        if not all(math.isfinite(x) for x in (ema_fast, ema_slow, ema_slow_prev, atr)) or atr <= 0:
            return False

        gap_pct = abs(ema_fast - ema_slow) / cur * 100.0
        slope_pct = abs((ema_slow - ema_slow_prev) / max(1e-12, abs(ema_slow_prev))) * 100.0
        atr_pct = atr / cur * 100.0

        # Bullish: EMA20 > EMA50 OR configured gap is small enough to treat as flat/early trend.
        ok = (
            (ema_fast >= ema_slow or gap_pct <= self.cfg.regime_max_gap_pct)
            and slope_pct <= self.cfg.regime_max_slope_pct
            and self.cfg.regime_min_atr_pct <= atr_pct <= self.cfg.regime_max_atr_pct
        )

        self._last_regime_tf_ts = tf_ts
        self._last_regime_ok = bool(ok)
        return bool(ok)

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, v)
        self._refresh_runtime_allowlists()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        if not self.cfg.allow_longs:
            return None

        if not self._regime_ok(store):
            self.last_no_signal_reason = "regime_not_bullish"
            return None

        need = max(self.cfg.signal_lookback, self.cfg.signal_ema_period + self.cfg.rsi_period + 5)
        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, need) or []
        if len(rows) < need:
            self.last_no_signal_reason = "not_enough_signal_bars"
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

        cur = closes[-1]
        prev = closes[-2]
        ema = _ema(closes, self.cfg.signal_ema_period)
        atr = _atr_from_rows(rows, self.cfg.signal_atr_period)
        rsi = _rsi(closes, self.cfg.rsi_period)
        if not all(math.isfinite(x) for x in (ema, atr, rsi)) or cur <= 0 or atr <= 0:
            self.last_no_signal_reason = "calc_error"
            return None

        support = min(lows[-self.cfg.signal_lookback:-1])
        resistance = max(highs[-self.cfg.signal_lookback:-1])
        range_pct = (resistance - support) / max(1e-12, cur) * 100.0
        if range_pct < self.cfg.min_range_pct or range_pct > self.cfg.max_range_pct:
            self.last_no_signal_reason = f"range_invalid_{range_pct:.1f}pct"
            return None

        # RSI must be in oversold region
        if rsi < self.cfg.min_rsi or rsi > self.cfg.max_rsi:
            self.last_no_signal_reason = f"rsi_invalid_{rsi:.1f}"
            return None

        low_now = lows[-1]
        body = abs(cur - opens[-1])
        bar_range = max(1e-12, highs[-1] - lows[-1])
        body_frac = body / bar_range

        # Touched support
        touched_supp = low_now <= support + self.cfg.support_touch_buffer_atr * atr
        # Reclaimed above support (bullish)
        reclaimed_above = cur >= support + self.cfg.reclaim_above_supp_atr * atr and cur > prev and cur > opens[-1]
        # Close vs EMA
        close_vs_ema_pct = (cur - ema) / max(1e-12, ema) * 100.0

        if not (
            touched_supp
            and reclaimed_above
            and body_frac >= self.cfg.min_body_frac
            and close_vs_ema_pct <= self.cfg.max_close_vs_ema_pct
        ):
            self.last_no_signal_reason = f"entry_conditions_not_met"
            return None

        # SL below support
        sl = support - self.cfg.sl_atr_mult * atr
        entry_price = float(c)

        if sl >= entry_price:
            self.last_no_signal_reason = "sl_above_entry"
            return None

        # TP2 at resistance with buffer
        tp2 = resistance * (1.0 - self.cfg.tp2_buffer_pct / 100.0)
        if tp2 <= entry_price:
            self.last_no_signal_reason = "tp_invalid"
            return None

        # TP1 at 55% to resistance
        tp1 = entry_price + (tp2 - entry_price) * 0.55
        tp1_frac = min(0.9, max(0.1, self.cfg.tp1_frac))

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="alt_support_bounce_v1",
            symbol=store.symbol,
            side="long",
            entry=entry_price,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=max(5, int(self.cfg.trail_atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason="asb1_support_bounce",
        )
        return sig if sig.validate() else None

===== END FILE: strategies/alt_support_bounce_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/impulse_volume_breakout_v1.py =====
GROUP: CANDIDATE / NEEDS REVIEW
REVIEW_FOCUS: IVB1: impulse breakout, currently telemetry/no live risk; needs review for package additivity.
====================================================================================================

"""
impulse_volume_breakout_v1 — 5m impulse breakout with shallow retrace entry.

This is intentionally a different family from the old breakout retest logic:
- not a slow 4h level reclaim,
- not a blind market chase into a pump,
- but a short-lived high-volume impulse, followed by a controlled retrace,
  and then a continuation entry while the breakout level is still defended.

Typical use:
  - current90 / mixed regime research on liquid pump-capable symbols,
  - future bull / momentum sleeve if the standalone edge proves real.
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
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


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


def _sma(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    tail = values[-period:] if len(values) >= period else values
    if not tail:
        return float("nan")
    return sum(tail) / float(len(tail))


@dataclass
class ImpulseVolumeBreakoutV1Config:
    entry_tf: str = "5"
    regime_tf: str = "60"
    atr_period: int = 14
    breakout_lookback_bars: int = 24
    impulse_lookback_bars: int = 18
    min_impulse_pct: float = 0.045
    min_vol_mult: float = 1.8
    vol_period: int = 20
    min_body_frac: float = 0.45
    min_bar_range_atr: float = 1.20
    breakout_buffer_atr: float = 0.10
    retrace_min_frac: float = 0.25
    retrace_max_frac: float = 0.60
    reclaim_atr: float = 0.08
    entry_body_min_frac: float = 0.25
    touch_below_breakout_atr: float = 0.20
    invalidation_close_atr: float = 0.35
    # RR tuned 2026-04-16: avg_win $0.39 < avg_loss $0.58 at RR=1.8.
    # Raised to 2.2 + tighter SL to fix the imbalance.
    # Must re-validate with WF-22 on server before enabling in bear stack.
    sl_atr: float = 0.75       # was 1.0 — tighter stop, smaller loss when wrong
    rr: float = 2.2            # was 1.8 — larger winner to fix avg_win < avg_loss
    tp1_rr: float = 1.1        # was 0.9 — partial TP proportional to new RR
    trail_atr_mult: float = 1.2
    trail_activate_rr: float = 1.1
    min_stop_pct: float = 0.008
    max_stop_pct: float = 0.060
    time_stop_bars_5m: int = 72
    cooldown_bars_5m: int = 12
    max_wait_bars_5m: int = 8
    allow_longs: bool = True
    regime_mode: str = "off"
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    # ── 4h MACD macro filter (added 2026-04-16) ──────────────────────────
    # IVB1 is a LONG-ONLY momentum strategy. In bear markets it has 0% WR
    # (Q1-2026: 9 trades, 0 wins, -5.71%). Adding a 4h MACD histogram check
    # blocks entries when macro is bearish.
    # IVB1_MACRO_REQUIRE_BULL=1 (default): only enter longs when 4h MACD hist > 0
    # IVB1_MACRO_REQUIRE_BULL=0: disable filter (old behaviour)
    macro_require_bull: bool = True   # block longs when 4h hist <= 0
    macro_tf: str = "240"             # timeframe for MACD check
    macro_macd_fast: int = 12
    macro_macd_slow: int = 26
    macro_macd_signal: int = 9
    # Breakeven protection — move SL to entry+lock after reaching be_trigger_rr.
    # Default: arm BE at 1R, lock at +0.1R (small profit cushion).
    # Set be_trigger_rr=0 to disable (old behaviour).
    be_trigger_rr: float = 1.0        # arm BE when price moves +1R in our direction
    be_lock_rr: float = 0.1           # lock SL at entry + 0.1R (not at exact entry)


class ImpulseVolumeBreakoutV1Strategy:
    STRATEGY_NAME = "impulse_volume_breakout_v1"

    def __init__(self, cfg: Optional[ImpulseVolumeBreakoutV1Config] = None):
        self.cfg = cfg or ImpulseVolumeBreakoutV1Config()
        self._load_runtime_config()
        self._cooldown = 0
        self._last_entry_ts: Optional[int] = None
        self._armed: Optional[dict] = None
        self.last_no_signal_reason = ""

    def _load_runtime_config(self) -> None:
        self.cfg.entry_tf = os.getenv("IVB1_ENTRY_TF", self.cfg.entry_tf)
        self.cfg.regime_tf = os.getenv("IVB1_REGIME_TF", self.cfg.regime_tf)
        self.cfg.atr_period = _env_int("IVB1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.breakout_lookback_bars = _env_int("IVB1_BREAKOUT_LOOKBACK_BARS", self.cfg.breakout_lookback_bars)
        self.cfg.impulse_lookback_bars = _env_int("IVB1_IMPULSE_LOOKBACK_BARS", self.cfg.impulse_lookback_bars)
        self.cfg.min_impulse_pct = _env_float("IVB1_MIN_IMPULSE_PCT", self.cfg.min_impulse_pct)
        self.cfg.min_vol_mult = _env_float("IVB1_MIN_VOL_MULT", self.cfg.min_vol_mult)
        self.cfg.vol_period = _env_int("IVB1_VOL_PERIOD", self.cfg.vol_period)
        self.cfg.min_body_frac = _env_float("IVB1_MIN_BODY_FRAC", self.cfg.min_body_frac)
        self.cfg.min_bar_range_atr = _env_float("IVB1_MIN_BAR_RANGE_ATR", self.cfg.min_bar_range_atr)
        self.cfg.breakout_buffer_atr = _env_float("IVB1_BREAKOUT_BUFFER_ATR", self.cfg.breakout_buffer_atr)
        self.cfg.retrace_min_frac = _env_float("IVB1_RETRACE_MIN_FRAC", self.cfg.retrace_min_frac)
        self.cfg.retrace_max_frac = _env_float("IVB1_RETRACE_MAX_FRAC", self.cfg.retrace_max_frac)
        self.cfg.reclaim_atr = _env_float("IVB1_RECLAIM_ATR", self.cfg.reclaim_atr)
        self.cfg.entry_body_min_frac = _env_float("IVB1_ENTRY_BODY_MIN_FRAC", self.cfg.entry_body_min_frac)
        self.cfg.touch_below_breakout_atr = _env_float("IVB1_TOUCH_BELOW_BREAKOUT_ATR", self.cfg.touch_below_breakout_atr)
        self.cfg.invalidation_close_atr = _env_float("IVB1_INVALIDATION_CLOSE_ATR", self.cfg.invalidation_close_atr)
        self.cfg.sl_atr = _env_float("IVB1_SL_ATR", self.cfg.sl_atr)
        self.cfg.rr = _env_float("IVB1_RR", self.cfg.rr)
        self.cfg.tp1_rr = _env_float("IVB1_TP1_RR", self.cfg.tp1_rr)
        self.cfg.trail_atr_mult = _env_float("IVB1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.trail_activate_rr = _env_float("IVB1_TRAIL_ACTIVATE_RR", self.cfg.trail_activate_rr)
        self.cfg.min_stop_pct = _env_float("IVB1_MIN_STOP_PCT", self.cfg.min_stop_pct)
        self.cfg.max_stop_pct = _env_float("IVB1_MAX_STOP_PCT", self.cfg.max_stop_pct)
        self.cfg.time_stop_bars_5m = _env_int("IVB1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("IVB1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_wait_bars_5m = _env_int("IVB1_MAX_WAIT_BARS_5M", self.cfg.max_wait_bars_5m)
        self.cfg.allow_longs = _env_bool("IVB1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.regime_mode = os.getenv("IVB1_REGIME_MODE", self.cfg.regime_mode)
        self.cfg.regime_ema_fast = _env_int("IVB1_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("IVB1_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.macro_require_bull = _env_bool("IVB1_MACRO_REQUIRE_BULL", self.cfg.macro_require_bull)
        self.cfg.macro_tf = os.getenv("IVB1_MACRO_TF", self.cfg.macro_tf)
        self.cfg.macro_macd_fast = _env_int("IVB1_MACRO_MACD_FAST", self.cfg.macro_macd_fast)
        self.cfg.macro_macd_slow = _env_int("IVB1_MACRO_MACD_SLOW", self.cfg.macro_macd_slow)
        self.cfg.macro_macd_signal = _env_int("IVB1_MACRO_MACD_SIGNAL", self.cfg.macro_macd_signal)
        self.cfg.be_trigger_rr = _env_float("IVB1_BE_TRIGGER_RR", self.cfg.be_trigger_rr)
        self.cfg.be_lock_rr = _env_float("IVB1_BE_LOCK_RR", self.cfg.be_lock_rr)

        self._allow = _env_csv_set("IVB1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("IVB1_SYMBOL_DENYLIST")

    def _refresh_runtime_config(self) -> None:
        self._load_runtime_config()

    def _macro_ok(self, store) -> bool:
        """4h MACD histogram check — block longs when macro is bearish.

        Returns True if longs are allowed:
          - macro_require_bull=False → always OK (old behaviour)
          - macro_require_bull=True  → only OK when 4h MACD hist > 0

        Uses standard MACD(12,26,9). Mirrors the filter in elder_triple_screen_v2
        so all momentum strategies share the same macro gate.
        """
        if not self.cfg.macro_require_bull:
            return True
        needed = self.cfg.macro_macd_slow + self.cfg.macro_macd_signal + 5
        rows_4h = store.fetch_klines(store.symbol, self.cfg.macro_tf, needed + 10) or []
        if len(rows_4h) < needed:
            self.last_no_signal_reason = "macro_history_short"
            return False
        closes = [float(r[4]) for r in rows_4h]
        # EMA helpers
        def _ema_seq(vals: List[float], period: int) -> List[float]:
            k = 2.0 / (period + 1.0)
            e = vals[0]
            out = [e]
            for v in vals[1:]:
                e = v * k + e * (1.0 - k)
                out.append(e)
            return out
        fast_seq = _ema_seq(closes, self.cfg.macro_macd_fast)
        slow_seq = _ema_seq(closes, self.cfg.macro_macd_slow)
        # align (fast_seq is longer, trim to slow length)
        offset = len(fast_seq) - len(slow_seq)
        macd_line = [fast_seq[i + offset] - slow_seq[i] for i in range(len(slow_seq))]
        signal_line = _ema_seq(macd_line, self.cfg.macro_macd_signal)
        hist = macd_line[-1] - signal_line[-1]
        if hist <= 0:
            self.last_no_signal_reason = f"macro_bearish_hist={hist:.6f}"
            return False
        return True

    def _regime_ok(self, store) -> bool:
        if str(self.cfg.regime_mode).strip().lower() != "ema":
            return True
        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, max(100, self.cfg.regime_ema_slow + 20)) or []
        if len(rows) < self.cfg.regime_ema_slow + 20:
            self.last_no_signal_reason = "regime_history_short"
            return False
        closes = [float(r[4]) for r in rows]
        ema_fast = _ema(closes, self.cfg.regime_ema_fast)
        ema_slow = _ema(closes, self.cfg.regime_ema_slow)
        if not all(math.isfinite(x) for x in (ema_fast, ema_slow)):
            self.last_no_signal_reason = "regime_invalid"
            return False
        return ema_fast > ema_slow

    def _arm_if_impulse(self, rows_5m: List[list], atr_5m: float, vol_base: float) -> None:
        if self._armed is not None:
            return
        if not self.cfg.allow_longs:
            self.last_no_signal_reason = "longs_disabled"
            return

        opens = [float(r[1]) for r in rows_5m]
        highs = [float(r[2]) for r in rows_5m]
        lows = [float(r[3]) for r in rows_5m]
        closes = [float(r[4]) for r in rows_5m]
        volumes = [float(r[5]) if len(r) > 5 else 0.0 for r in rows_5m]

        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        cur_close = closes[-1]
        cur_volume = volumes[-1]
        prior_high = max(highs[-(self.cfg.breakout_lookback_bars + 1):-1])
        recent_low = min(lows[-(self.cfg.impulse_lookback_bars + 1):-1])
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range
        impulse_pct = (cur_close - recent_low) / max(1e-12, recent_low)
        vol_mult = cur_volume / max(1e-12, vol_base) if vol_base > 0 else 0.0
        broke_out = cur_close > prior_high + self.cfg.breakout_buffer_atr * atr_5m
        bar_range_atr = bar_range / max(1e-12, atr_5m)

        if cur_close <= cur_open:
            self.last_no_signal_reason = "impulse_bar_not_bullish"
            return
        if not broke_out:
            self.last_no_signal_reason = "impulse_no_breakout"
            return
        if impulse_pct < self.cfg.min_impulse_pct:
            self.last_no_signal_reason = f"impulse_too_small_{impulse_pct:.3f}"
            return
        if vol_mult < self.cfg.min_vol_mult:
            self.last_no_signal_reason = f"impulse_vol_weak_{vol_mult:.2f}"
            return
        if body_frac < self.cfg.min_body_frac:
            self.last_no_signal_reason = f"impulse_body_weak_{body_frac:.2f}"
            return
        if bar_range_atr < self.cfg.min_bar_range_atr:
            self.last_no_signal_reason = f"impulse_range_weak_{bar_range_atr:.2f}"
            return

        self._armed = {
            "armed_ts": int(float(rows_5m[-1][0])),
            "breakout_level": float(prior_high),
            "impulse_high": float(cur_high),
            "impulse_low": float(max(prior_high, cur_low)),
            "impulse_range": float(max(cur_high - prior_high, atr_5m * 0.5)),
            "atr": float(atr_5m),
        }
        self.last_no_signal_reason = "armed_impulse_breakout"

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (ts_ms, o, h, l, c, v)
        self.last_no_signal_reason = ""
        self._refresh_runtime_config()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            self.last_no_signal_reason = "symbol_not_allowed"
            return None
        if sym in self._deny:
            self.last_no_signal_reason = "symbol_denied"
            return None

        rows_5m = store.fetch_klines(store.symbol, self.cfg.entry_tf, max(160, self.cfg.breakout_lookback_bars + self.cfg.impulse_lookback_bars + self.cfg.vol_period + self.cfg.atr_period + 20)) or []
        min_rows = max(self.cfg.breakout_lookback_bars + 3, self.cfg.impulse_lookback_bars + 3, self.cfg.vol_period + 3, self.cfg.atr_period + 3)
        if len(rows_5m) < min_rows:
            self.last_no_signal_reason = "not_enough_5m_bars"
            return None

        bar_ts = int(float(rows_5m[-1][0]))
        if self._last_entry_ts is not None and bar_ts == self._last_entry_ts:
            self.last_no_signal_reason = "same_entry_bar"
            return None
        self._last_entry_ts = bar_ts

        if self._cooldown > 0:
            self._cooldown -= 1
            self.last_no_signal_reason = "cooldown"
            return None
        if not self._macro_ok(store):
            return None
        if not self._regime_ok(store):
            return None

        closes = [float(r[4]) for r in rows_5m]
        opens = [float(r[1]) for r in rows_5m]
        highs = [float(r[2]) for r in rows_5m]
        lows = [float(r[3]) for r in rows_5m]
        volumes = [float(r[5]) if len(r) > 5 else 0.0 for r in rows_5m]
        atr_5m = _atr_from_rows(rows_5m, self.cfg.atr_period)
        vol_base = _sma(volumes[:-1], self.cfg.vol_period)

        if not math.isfinite(atr_5m) or atr_5m <= 0:
            self.last_no_signal_reason = "atr_invalid"
            return None
        if not math.isfinite(vol_base) or vol_base <= 0:
            self.last_no_signal_reason = "volume_baseline_invalid"
            return None

        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        cur_close = closes[-1]
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range

        armed = self._armed
        if armed is not None:
            wait_bars = max(1, int((bar_ts - int(armed["armed_ts"])) / (5 * 60 * 1000)))
            breakout_level = float(armed["breakout_level"])
            impulse_high = float(armed["impulse_high"])
            impulse_range = float(armed["impulse_range"])
            risk_atr = max(float(armed["atr"]) * 0.85, atr_5m)
            zone_top = impulse_high - self.cfg.retrace_min_frac * impulse_range
            zone_bot = impulse_high - self.cfg.retrace_max_frac * impulse_range

            if wait_bars > self.cfg.max_wait_bars_5m:
                self._armed = None
                self.last_no_signal_reason = "armed_expired"
            elif cur_close < breakout_level - self.cfg.invalidation_close_atr * risk_atr:
                self._armed = None
                self.last_no_signal_reason = "armed_lost_breakout_level"
            else:
                touched_retrace = cur_low <= zone_top
                not_too_deep = cur_low >= max(zone_bot, breakout_level - self.cfg.touch_below_breakout_atr * risk_atr)
                bullish_reclaim = cur_close > cur_open and cur_close > breakout_level + self.cfg.reclaim_atr * risk_atr
                if touched_retrace and not_too_deep and bullish_reclaim and body_frac >= self.cfg.entry_body_min_frac:
                    entry = float(cur_close)
                    sl = breakout_level - self.cfg.sl_atr * risk_atr
                    if sl >= entry:
                        self.last_no_signal_reason = "sl_at_or_above_entry"
                        return None
                    risk = entry - sl
                    stop_pct = risk / max(1e-12, entry)
                    if stop_pct < self.cfg.min_stop_pct:
                        self.last_no_signal_reason = f"stop_too_tight_{stop_pct:.4f}"
                        return None
                    if stop_pct > self.cfg.max_stop_pct:
                        self.last_no_signal_reason = f"stop_too_wide_{stop_pct:.4f}"
                        return None

                    tp1 = entry + self.cfg.tp1_rr * risk
                    tp2 = entry + self.cfg.rr * risk
                    if tp2 <= tp1:
                        tp2 = tp1 + 0.5 * risk
                    self._armed = None
                    self._cooldown = max(0, self.cfg.cooldown_bars_5m)
                    return TradeSignal(
                        strategy=self.STRATEGY_NAME,
                        symbol=sym,
                        side="long",
                        entry=entry,
                        sl=sl,
                        tp=tp2,
                        tps=[tp1, tp2],
                        tp_fracs=[0.5, 0.5],
                        trailing_atr_mult=self.cfg.trail_atr_mult,
                        trailing_atr_period=self.cfg.atr_period,
                        trail_activate_rr=self.cfg.trail_activate_rr,
                        be_trigger_rr=max(0.0, float(self.cfg.be_trigger_rr)),
                        be_lock_rr=max(0.0, float(self.cfg.be_lock_rr)),
                        time_stop_bars=self.cfg.time_stop_bars_5m,
                        reason="impulse_retrace_long",
                    )
                self.last_no_signal_reason = "armed_waiting_retrace"
                return None

        self._arm_if_impulse(rows_5m, atr_5m, vol_base)
        return None

===== END FILE: strategies/impulse_volume_breakout_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/btc_eth_midterm_pullback.py =====
GROUP: CANDIDATE / NEEDS REVIEW
REVIEW_FOCUS: BTC/ETH midterm pullback; currently telemetry/no live risk; needs review.
====================================================================================================

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


@dataclass
class BTCETHMidtermPullbackConfig:
    trend_tf: str = "240"  # 4h
    signal_tf: str = "60"  # 1h
    eval_tf_min: int = 15  # evaluate every 15m bucket

    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    trend_slope_bars: int = 8
    trend_slope_min_pct: float = 0.45
    trend_min_gap_pct: float = 0.25

    signal_ema_period: int = 20
    atr_period: int = 14
    max_pullback_pct: float = 0.90
    long_max_pullback_pct: float = 0.90
    short_max_pullback_pct: float = 0.90
    touch_tol_pct: float = 0.20
    long_touch_tol_pct: float = 0.20
    short_touch_tol_pct: float = 0.20
    reclaim_pct: float = 0.15
    long_reclaim_pct: float = 0.15
    short_reclaim_pct: float = 0.15
    swing_lookback_bars: int = 10
    max_atr_pct_1h: float = 1.80
    long_max_atr_pct_1h: float = 1.80
    short_max_atr_pct_1h: float = 1.80

    sl_atr_mult: float = 1.20
    swing_sl_buffer_atr: float = 0.15
    rr: float = 2.2
    use_runner_exits: bool = True   # enables TP ladder + time_stop in live runner
    tp1_rr: float = 1.2
    tp2_rr: float = 2.6
    tp1_frac: float = 0.50
    trail_atr_mult: float = 1.1
    time_stop_bars_5m: int = 84

    cooldown_bars_5m: int = 84
    max_signals_per_day: int = 1
    allow_longs: bool = True
    allow_shorts: bool = True


class BTCETHMidtermPullbackStrategy:
    """BTC/ETH medium-term pullback: 4h trend + 1h pullback/reclaim entry."""

    def __init__(self, cfg: Optional[BTCETHMidtermPullbackConfig] = None):
        self.cfg = cfg or BTCETHMidtermPullbackConfig()

        self.cfg.trend_tf = os.getenv("MTPB_TREND_TF", self.cfg.trend_tf)
        self.cfg.signal_tf = os.getenv("MTPB_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.eval_tf_min = _env_int("MTPB_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.trend_ema_fast = _env_int("MTPB_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("MTPB_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_slope_bars = _env_int("MTPB_TREND_SLOPE_BARS", self.cfg.trend_slope_bars)
        self.cfg.trend_slope_min_pct = _env_float("MTPB_TREND_SLOPE_MIN_PCT", self.cfg.trend_slope_min_pct)
        self.cfg.trend_min_gap_pct = _env_float("MTPB_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)
        self.cfg.signal_ema_period = _env_int("MTPB_SIGNAL_EMA_PERIOD", self.cfg.signal_ema_period)
        self.cfg.atr_period = _env_int("MTPB_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.max_pullback_pct = _env_float("MTPB_MAX_PULLBACK_PCT", self.cfg.max_pullback_pct)
        self.cfg.long_max_pullback_pct = _env_float("MTPB_LONG_MAX_PULLBACK_PCT", self.cfg.max_pullback_pct)
        self.cfg.short_max_pullback_pct = _env_float("MTPB_SHORT_MAX_PULLBACK_PCT", self.cfg.max_pullback_pct)
        self.cfg.touch_tol_pct = _env_float("MTPB_TOUCH_TOL_PCT", self.cfg.touch_tol_pct)
        self.cfg.long_touch_tol_pct = _env_float("MTPB_LONG_TOUCH_TOL_PCT", self.cfg.touch_tol_pct)
        self.cfg.short_touch_tol_pct = _env_float("MTPB_SHORT_TOUCH_TOL_PCT", self.cfg.touch_tol_pct)
        self.cfg.reclaim_pct = _env_float("MTPB_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.long_reclaim_pct = _env_float("MTPB_LONG_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.short_reclaim_pct = _env_float("MTPB_SHORT_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.swing_lookback_bars = _env_int("MTPB_SWING_LOOKBACK_BARS", self.cfg.swing_lookback_bars)
        self.cfg.max_atr_pct_1h = _env_float("MTPB_MAX_ATR_PCT_1H", self.cfg.max_atr_pct_1h)
        self.cfg.long_max_atr_pct_1h = _env_float("MTPB_LONG_MAX_ATR_PCT_1H", self.cfg.max_atr_pct_1h)
        self.cfg.short_max_atr_pct_1h = _env_float("MTPB_SHORT_MAX_ATR_PCT_1H", self.cfg.max_atr_pct_1h)
        self.cfg.sl_atr_mult = _env_float("MTPB_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.swing_sl_buffer_atr = _env_float("MTPB_SWING_SL_BUFFER_ATR", self.cfg.swing_sl_buffer_atr)
        self.cfg.rr = _env_float("MTPB_RR", self.cfg.rr)
        self.cfg.use_runner_exits = _env_bool("MTPB_USE_RUNNER_EXITS", self.cfg.use_runner_exits)
        self.cfg.tp1_rr = _env_float("MTPB_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_rr = _env_float("MTPB_TP2_RR", self.cfg.tp2_rr)
        self.cfg.tp1_frac = _env_float("MTPB_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.trail_atr_mult = _env_float("MTPB_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("MTPB_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("MTPB_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("MTPB_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.allow_longs = _env_bool("MTPB_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("MTPB_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("MTPB_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("MTPB_SYMBOL_DENYLIST")

        self._cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _trend_bias(self, store) -> Optional[int]:
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
        if gap_pct < float(self.cfg.trend_min_gap_pct):
            return 1

        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if ef > es and slope_pct >= self.cfg.trend_slope_min_pct:
            return 2  # uptrend
        if ef < es and slope_pct <= -self.cfg.trend_slope_min_pct:
            return 0  # downtrend
        return 1  # neutral

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, v)
        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None

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

        bucket = ts_sec // max(1, int(self.cfg.eval_tf_min * 60))
        if self._last_eval_bucket == bucket:
            return None
        self._last_eval_bucket = bucket

        bias = self._trend_bias(store)
        if bias is None or bias == 1:
            return None

        need_1h = max(self.cfg.signal_ema_period + self.cfg.swing_lookback_bars + 5, 90)
        rows_1h = store.fetch_klines(store.symbol, self.cfg.signal_tf, need_1h) or []
        if len(rows_1h) < self.cfg.signal_ema_period + self.cfg.swing_lookback_bars + 2:
            return None

        highs = [float(r[2]) for r in rows_1h]
        lows = [float(r[3]) for r in rows_1h]
        closes = [float(r[4]) for r in rows_1h]
        ema1h = _ema(closes, self.cfg.signal_ema_period)
        atr1h = _atr_from_rows(rows_1h, self.cfg.atr_period)
        if not (math.isfinite(ema1h) and math.isfinite(atr1h) and atr1h > 0):
            return None
        cur_c = closes[-1]
        atr_pct_1h = (atr1h / max(1e-12, abs(cur_c))) * 100.0
        max_atr_pct = max(
            float(self.cfg.long_max_atr_pct_1h),
            float(self.cfg.short_max_atr_pct_1h),
        )
        if atr_pct_1h > max_atr_pct:
            return None

        prev_c = closes[-2]
        look = max(3, min(len(rows_1h), int(self.cfg.swing_lookback_bars)))
        swing_low = min(lows[-look:])
        swing_high = max(highs[-look:])

        # Long: 4h uptrend + 1h pullback to EMA20 + reclaim.
        if self.cfg.allow_longs and bias == 2:
            if atr_pct_1h > float(self.cfg.long_max_atr_pct_1h):
                return None
            touched = swing_low <= ema1h * (1.0 + self.cfg.long_touch_tol_pct / 100.0)
            reclaimed = (cur_c >= ema1h * (1.0 + self.cfg.long_reclaim_pct / 100.0)) and (prev_c <= ema1h * 1.003)
            pullback_pct = max(0.0, (ema1h - swing_low) / max(1e-12, ema1h) * 100.0)
            if touched and reclaimed and pullback_pct <= self.cfg.long_max_pullback_pct:
                swing_sl = swing_low - self.cfg.swing_sl_buffer_atr * atr1h
                atr_sl = float(c) - self.cfg.sl_atr_mult * atr1h
                sl = min(swing_sl, atr_sl)
                if sl >= float(c):
                    return None
                risk = float(c) - sl
                tp1 = float(c) + float(self.cfg.tp1_rr) * risk
                tp2 = float(c) + float(self.cfg.tp2_rr) * risk
                tp = float(c) + self.cfg.rr * risk
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                sig = TradeSignal(
                    strategy="btc_eth_midterm_pullback",
                    symbol=store.symbol,
                    side="long",
                    entry=float(c),
                    sl=float(sl),
                    tp=float(tp),
                    reason=f"mtpb_long trend4h pullback1h ema={self.cfg.signal_ema_period}",
                )
                if self.cfg.use_runner_exits:
                    tp1_frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
                    sig.tps = [float(tp1), float(tp2)]
                    sig.tp_fracs = [tp1_frac, max(0.0, 1.0 - tp1_frac)]
                    sig.trailing_atr_mult = max(0.0, float(self.cfg.trail_atr_mult))
                    sig.trailing_atr_period = max(5, int(self.cfg.atr_period))
                    sig.time_stop_bars = max(0, int(self.cfg.time_stop_bars_5m))
                return sig

        # Short: 4h downtrend + 1h pullback to EMA20 + reclaim below EMA.
        if self.cfg.allow_shorts and bias == 0:
            if atr_pct_1h > float(self.cfg.short_max_atr_pct_1h):
                return None
            touched = swing_high >= ema1h * (1.0 - self.cfg.short_touch_tol_pct / 100.0)
            reclaimed = (cur_c <= ema1h * (1.0 - self.cfg.short_reclaim_pct / 100.0)) and (prev_c >= ema1h * 0.997)
            pullback_pct = max(0.0, (swing_high - ema1h) / max(1e-12, ema1h) * 100.0)
            if touched and reclaimed and pullback_pct <= self.cfg.short_max_pullback_pct:
                swing_sl = swing_high + self.cfg.swing_sl_buffer_atr * atr1h
                atr_sl = float(c) + self.cfg.sl_atr_mult * atr1h
                sl = max(swing_sl, atr_sl)
                if sl <= float(c):
                    return None
                risk = sl - float(c)
                tp1 = float(c) - float(self.cfg.tp1_rr) * risk
                tp2 = float(c) - float(self.cfg.tp2_rr) * risk
                tp = float(c) - self.cfg.rr * risk
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                sig = TradeSignal(
                    strategy="btc_eth_midterm_pullback",
                    symbol=store.symbol,
                    side="short",
                    entry=float(c),
                    sl=float(sl),
                    tp=float(tp),
                    reason=f"mtpb_short trend4h pullback1h ema={self.cfg.signal_ema_period}",
                )
                if self.cfg.use_runner_exits:
                    tp1_frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
                    sig.tps = [float(tp1), float(tp2)]
                    sig.tp_fracs = [tp1_frac, max(0.0, 1.0 - tp1_frac)]
                    sig.trailing_atr_mult = max(0.0, float(self.cfg.trail_atr_mult))
                    sig.trailing_atr_period = max(5, int(self.cfg.atr_period))
                    sig.time_stop_bars = max(0, int(self.cfg.time_stop_bars_5m))
                return sig

        return None

===== END FILE: strategies/btc_eth_midterm_pullback.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: bot/liquidity_map.py =====
GROUP: RESEARCH / BEST NEW CANDIDATE
REVIEW_FOCUS: LSR1 liquidity hunter: needs trend split, symbol-WF, pool-to-pool target review.
====================================================================================================

"""Liquidity map + sweep-reversal — охотник за ликвидностью без стакана (Claude 2026-06-11).

Идея: стопы толпы скапливаются за «равными» экстремумами (equal highs/lows)
и свинг-точками. Эти кластеры = пулы ликвидности. Крупный игрок «снимает» пул
(прокол фитилём) и разворачивает цену. Мы НЕ предсказываем — входим ПОСЛЕ
снятия, когда возврат подтверждён закрытием.

Всё из OHLC: пулы из пивотов, снятие из фитилей. L2/ликвидационный фид позже
усилят (фильтр «снятие совпало с каскадом ликвидаций»), но базовая геометрия
работает на свечах.

API:
    pools = LiquidityMap(cfg).build(highs, lows)          # карта пулов
    sig   = LiquiditySweepReversalV1().signal(h, l, c)    # сигнал для харнесса
Сигнал совместим с scripts/backtest_candidates.py (как RMR1/TPB1).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass
class LiqMapConfig:
    pivot_left: int = 3
    pivot_right: int = 3
    cluster_tol_pct: float = 0.25   # пивоты в пределах этого % = один пул
    min_touches: int = 2            # пул = минимум 2 касания (equal highs/lows)
    max_age_bars: int = 400         # пул протухает, если касаний давно не было
    atr_period: int = 14


@dataclass
class Pool:
    side: str                # "above" (buy-side liq, стопы шортов) | "below"
    price: float             # уровень пула (среднее касаний)
    touches: int
    last_touch_i: int
    strength: float          # touches с поправкой на свежесть

    def contains(self, px: float, tol: float) -> bool:
        return abs(px - self.price) <= tol


@dataclass
class SweepEvent:
    pool: Pool
    bar_i: int
    extreme: float           # экстремум фитиля, снявшего пул
    side: str                # "long" (снят нижний пул) | "short" (снят верхний)


def _ema_last(vals: Sequence[float], n: int) -> float:
    k = 2.0 / (n + 1)
    e = sum(vals[:n]) / n
    for x in vals[n:]:
        e = x * k + e * (1 - k)
    return e


def _atr(h: Sequence[float], l: Sequence[float], c: Sequence[float], p: int) -> float:
    n = len(c)
    if n < p + 1:
        return float("nan")
    trs = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
           for i in range(n - p, n)]
    return sum(trs) / len(trs)


def find_pivots(highs: Sequence[float], lows: Sequence[float],
                left: int, right: int):
    """Фрактальные свинг-точки: бар выше/ниже left соседей слева и right справа."""
    ph: List[tuple] = []
    pl: List[tuple] = []
    n = len(highs)
    for i in range(left, n - right):
        win_h = highs[i - left:i + right + 1]
        win_l = lows[i - left:i + right + 1]
        if highs[i] == max(win_h) and list(win_h).count(highs[i]) == 1:
            ph.append((i, highs[i]))
        if lows[i] == min(win_l) and list(win_l).count(lows[i]) == 1:
            pl.append((i, lows[i]))
    return ph, pl


def _cluster(pivots: List[tuple], tol_pct: float, min_touches: int,
             max_age_bars: int, now_i: int, side: str) -> List[Pool]:
    pools: List[Pool] = []
    used = [False] * len(pivots)
    for i, (bi, price) in enumerate(pivots):
        if used[i]:
            continue
        members = [(bi, price)]
        used[i] = True
        tol = price * tol_pct / 100.0
        for j in range(i + 1, len(pivots)):
            if used[j]:
                continue
            bj, pj = pivots[j]
            if abs(pj - price) <= tol:
                members.append((bj, pj))
                used[j] = True
        last_i = max(m[0] for m in members)
        if len(members) < min_touches:
            continue
        if now_i - last_i > max_age_bars:
            continue
        avg = sum(m[1] for m in members) / len(members)
        recency = max(0.25, 1.0 - (now_i - last_i) / max_age_bars)
        pools.append(Pool(side=side, price=avg, touches=len(members),
                          last_touch_i=last_i,
                          strength=round(len(members) * recency, 3)))
    pools.sort(key=lambda p: -p.strength)
    return pools


class LiquidityMap:
    def __init__(self, cfg: Optional[LiqMapConfig] = None):
        self.cfg = cfg or LiqMapConfig()

    def build(self, highs: Sequence[float], lows: Sequence[float]) -> Dict[str, List[Pool]]:
        c = self.cfg
        now_i = len(highs) - 1
        ph, pl = find_pivots(highs, lows, c.pivot_left, c.pivot_right)
        return {
            "above": _cluster(ph, c.cluster_tol_pct, c.min_touches, c.max_age_bars, now_i, "above"),
            "below": _cluster(pl, c.cluster_tol_pct, c.min_touches, c.max_age_bars, now_i, "below"),
        }


@dataclass
class LSRConfig:
    map: LiqMapConfig = field(default_factory=LiqMapConfig)
    atr_period: int = 14
    max_overshoot_atr: float = 1.5   # фитиль за пул не дальше этого (иначе это пробой, не снятие)
    sl_atr_mult: float = 1.0         # стоп за экстремум фитиля
    overshoot_min_atr: float = 0.2   # фитиль должен реально проколоть пул (не шум)
    min_pool_touches: int = 3        # только сильные пулы (толстая ликвидность)
    tp_rr: float = 2.0
    min_rr: float = 1.5
    max_pool_dist_atr: float = 3.0   # пул не дальше этого от цены (иначе не наш сетап)
    htf_factor: int = 4              # пулы строим на старшем ТФ (4×базовый, напр. 1h→4h).
                                     # 1 = пулы на базовом ТФ (шумно; PF~0.9 в матрице).
                                     # 4 = НАСТОЯЩИЕ кластеры стопов: 3/4 монет в плюсе.
    # Тренд-фильтр (данные 2026-06-11, разрез по тегам): контр-трендовые снятия
    # PF 1.60 (+34%), флэт PF 0.80, по-тренду PF 0.57. Терминальный вынос против
    # затяжного движения — вот где разворот. По умолчанию торгуем ТОЛЬКО их.
    trend_filter: str = "counter_only"  # "counter_only" | "off"
    trend_ema: int = 200             # EMA на базовом ТФ (1h EMA200 ≈ 4h EMA50)
    trend_slope_bars: int = 12       # наклон EMA за столько баров
    trend_slope_min: float = 0.001   # |наклон|/цена ниже порога = флэт (не торгуем)


class LiquiditySweepReversalV1:
    """Sweep-reversal: бар проколол пул фитилём и ЗАКРЫЛСЯ обратно — входим в реверс.

    long: лоу бара < нижний пул, close > пул (снятие sell-side ликвидности);
    short: хай бара > верхний пул, close < пул. SL за экстремум фитиля.
    """
    NAME = "liquidity_sweep_map_v1"

    def __init__(self, cfg: Optional[LSRConfig] = None):
        self.cfg = cfg or LSRConfig()
        self.lmap = LiquidityMap(self.cfg.map)
        self.last_reason = ""

    def signal(self, highs: Sequence[float], lows: Sequence[float],
               closes: Sequence[float]) -> Optional[Dict]:
        cfg = self.cfg
        need = cfg.map.pivot_left + cfg.map.pivot_right + cfg.atr_period + 20
        if len(closes) < need:
            self.last_reason = "history_short"
            return None
        atr = _atr(highs, lows, closes, cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_reason = "atr_nan"
            return None
        price = closes[-1]
        bar_h, bar_l = highs[-1], lows[-1]
        # пулы строим БЕЗ текущего бара (он — кандидат на снятие, не на касание).
        # htf_factor>1: агрегируем в старший ТФ — пулы из закрытых HTF-баров.
        f = max(1, int(cfg.htf_factor))
        if f > 1:
            n = len(highs)
            m = (n - 1) // f * f
            hh = [max(highs[i:i + f]) for i in range(0, m, f)]
            ll = [min(lows[i:i + f]) for i in range(0, m, f)]
            pools = self.lmap.build(hh, ll)
        else:
            pools = self.lmap.build(highs[:-1], lows[:-1])

        # long: снят ближайший нижний пул
        for p in pools["below"]:
            if p.touches < cfg.min_pool_touches:
                continue
            if p.price - price > 0:            # пул выше цены — не наш
                continue
            if price - p.price > cfg.max_pool_dist_atr * atr:
                continue
            swept = bar_l < p.price and price > p.price
            if not swept:
                continue
            overshoot = p.price - bar_l
            if overshoot > cfg.max_overshoot_atr * atr:
                self.last_reason = "overshoot_too_deep"   # это пробой, не снятие
                continue
            if overshoot < cfg.overshoot_min_atr * atr:
                self.last_reason = "overshoot_too_shallow"  # чирк, не снятие
                continue
            sl = bar_l - cfg.sl_atr_mult * atr
            risk = price - sl
            tp = price + cfg.tp_rr * risk
            rr = (tp - price) / risk if risk > 0 else 0.0
            if rr < cfg.min_rr:
                continue
            if not self._trend_ok("long", closes):
                self.last_reason = "trend_filter_long"
                continue
            self.last_reason = f"long_sweep_pool@{p.price:.4g}_t{p.touches}"
            return {"side": "long", "entry": price, "sl": sl, "tp": tp,
                    "rr": round(rr, 2), "reason": self.last_reason}

        # short: снят ближайший верхний пул
        for p in pools["above"]:
            if p.touches < cfg.min_pool_touches:
                continue
            if price - p.price > 0:
                continue
            if p.price - price > cfg.max_pool_dist_atr * atr:
                continue
            swept = bar_h > p.price and price < p.price
            if not swept:
                continue
            overshoot = bar_h - p.price
            if overshoot > cfg.max_overshoot_atr * atr:
                self.last_reason = "overshoot_too_deep"
                continue
            if overshoot < cfg.overshoot_min_atr * atr:
                self.last_reason = "overshoot_too_shallow"
                continue
            sl = bar_h + cfg.sl_atr_mult * atr
            risk = sl - price
            tp = price - cfg.tp_rr * risk
            rr = (price - tp) / risk if risk > 0 else 0.0
            if rr < cfg.min_rr:
                continue
            if not self._trend_ok("short", closes):
                self.last_reason = "trend_filter_short"
                continue
            self.last_reason = f"short_sweep_pool@{p.price:.4g}_t{p.touches}"
            return {"side": "short", "entry": price, "sl": sl, "tp": tp,
                    "rr": round(rr, 2), "reason": self.last_reason}

        self.last_reason = "no_sweep"
        return None

    def _trend_ok(self, side: str, closes: Sequence[float]) -> bool:
        """counter_only: лонг только против даунтренда, шорт — против аптренда.
        Недостаточно истории для EMA → пропускаем без фильтра (не наказываем)."""
        cfg = self.cfg
        if cfg.trend_filter != "counter_only":
            return True
        need = cfg.trend_ema + cfg.trend_slope_bars
        if len(closes) < need:
            return True
        e_now = _ema_last(list(closes), cfg.trend_ema)
        e_prev = _ema_last(list(closes[:-cfg.trend_slope_bars]), cfg.trend_ema)
        slope = (e_now - e_prev) / closes[-1]
        if side == "long":
            return slope < -cfg.trend_slope_min
        return slope > cfg.trend_slope_min

===== END FILE: bot/liquidity_map.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/pair_stat_arb_v1.py =====
GROUP: RESEARCH / PAIR ARB
REVIEW_FOCUS: Pair stat-arb signal/diagnostics; needs funding, frozen beta, beta gate, annual WF.
====================================================================================================

"""Market-neutral pair statistical arbitrage — ETH/BTC and similar (Opus 2026-06-08).

Idea: two correlated assets (e.g. ETHUSDT, BTCUSDT) move together. Their spread
(log A - beta*log B) is mean-reverting when the pair is cointegrated. When the
spread stretches far from its mean (high |z-score|) we LONG the underperformer
and SHORT the outperformer, betting the gap closes. Direction-neutral: profits
whether the market rises or falls, as long as the gap reverts.

Pure stdlib (no numpy/statsmodels) so it is portable and unit-testable offline.
This module produces PairSignals; live execution (two legs) and backtest
validation are wired separately (Codex). NOT a money guarantee — the edge is
thin and must pass walk-forward + fee modelling (see backtest/robustness.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

_LN2 = math.log(2.0)


@dataclass
class PairConfig:
    lookback: int = 168          # bars for beta + z-score window (e.g. 168 = 7d of 1h)
    entry_z: float = 2.0         # enter when |z| >= this
    exit_z: float = 0.5          # exit when |z| <= this (reverted)
    stop_z: float = 3.5          # bail when |z| >= this (gap keeps widening)
    max_half_life: float = 72.0  # bars; spread must mean-revert faster than this
    min_abs_corr: float = 0.6    # min |corr| of the two return series
    risk_pct_per_pair: float = 0.7


@dataclass
class PairSignal:
    long_symbol: str
    short_symbol: str
    z: float
    beta: float
    half_life: float
    corr: float
    reason: str


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _ols(y: Sequence[float], x: Sequence[float]) -> Tuple[float, float]:
    """Return (slope, intercept) for y = slope*x + intercept (least squares)."""
    n = len(x)
    if n < 2:
        return 0.0, 0.0
    mx, my = _mean(x), _mean(y)
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx <= 0:
        return 0.0, my
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    slope = sxy / sxx
    return slope, my - slope * mx


def _corr(a: Sequence[float], b: Sequence[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    a, b = a[-n:], b[-n:]
    sa, sb = _std(a), _std(b)
    if sa <= 0 or sb <= 0:
        return 0.0
    ma, mb = _mean(a), _mean(b)
    cov = sum((ai - ma) * (bi - mb) for ai, bi in zip(a, b)) / (n - 1)
    return cov / (sa * sb)


def compute_spread(prices_a: Sequence[float], prices_b: Sequence[float]) -> Tuple[float, float, List[float]]:
    """Hedge ratio beta and spread = log(A) - beta*log(B) - intercept."""
    la = [math.log(p) for p in prices_a]
    lb = [math.log(p) for p in prices_b]
    beta, intercept = _ols(la, lb)
    spread = [a - (beta * b + intercept) for a, b in zip(la, lb)]
    return beta, intercept, spread


def half_life(spread: Sequence[float]) -> float:
    """Ornstein-Uhlenbeck half-life of mean reversion, in bars.

    Regress dS_t on S_{t-1}: dS = lambda * S_{t-1} + c. Reverting => lambda < 0,
    half_life = ln(2)/-lambda. Returns +inf if not mean-reverting.
    """
    if len(spread) < 3:
        return math.inf
    s_prev = spread[:-1]
    ds = [spread[i] - spread[i - 1] for i in range(1, len(spread))]
    lam, _ = _ols(ds, s_prev)
    if lam >= 0:
        return math.inf
    return _LN2 / (-lam)


def returns(prices: Sequence[float]) -> List[float]:
    return [(prices[i] / prices[i - 1] - 1.0) for i in range(1, len(prices))]


class PairStatArbV1:
    """Stateless evaluator for one pair (A vs B)."""

    NAME = "pair_stat_arb_v1"

    def __init__(self, cfg: Optional[PairConfig] = None) -> None:
        self.cfg = cfg or PairConfig()
        self.last_reason: str = ""

    def diagnostics(self, prices_a: Sequence[float], prices_b: Sequence[float]) -> dict:
        cfg = self.cfg
        n = min(len(prices_a), len(prices_b))
        if n < cfg.lookback:
            return {"tradeable": False, "reason": f"history_short_{n}"}
        a = list(prices_a[-cfg.lookback:])
        b = list(prices_b[-cfg.lookback:])
        beta, _, spread = compute_spread(a, b)
        mu, sd = _mean(spread), _std(spread)
        z = (spread[-1] - mu) / sd if sd > 0 else 0.0
        hl = half_life(spread)
        corr = _corr(returns(a), returns(b))
        tradeable = (
            beta > 0
            and math.isfinite(hl) and 0 < hl <= cfg.max_half_life
            and abs(corr) >= cfg.min_abs_corr
            and sd > 0
        )
        return {
            "tradeable": tradeable, "beta": beta, "z": z, "half_life": hl,
            "corr": corr, "spread_std": sd, "reason": "ok" if tradeable else "not_cointegrated",
        }

    def signal(
        self,
        symbol_a: str,
        symbol_b: str,
        prices_a: Sequence[float],
        prices_b: Sequence[float],
    ) -> Optional[PairSignal]:
        d = self.diagnostics(prices_a, prices_b)
        if not d.get("tradeable"):
            self.last_reason = d.get("reason", "not_tradeable")
            return None
        z = d["z"]
        if abs(z) < self.cfg.entry_z:
            self.last_reason = f"z_small_{z:.2f}"
            return None
        if abs(z) >= self.cfg.stop_z:
            self.last_reason = f"z_blowout_{z:.2f}"
            return None
        # z>0: A rich vs B -> short A, long B. z<0: A cheap -> long A, short B.
        if z > 0:
            long_sym, short_sym = symbol_b, symbol_a
        else:
            long_sym, short_sym = symbol_a, symbol_b
        self.last_reason = f"entry_z_{z:.2f}"
        return PairSignal(
            long_symbol=long_sym, short_symbol=short_sym, z=z,
            beta=d["beta"], half_life=d["half_life"], corr=d["corr"],
            reason=self.last_reason,
        )

    def should_exit(self, z: float) -> Tuple[bool, str]:
        if abs(z) <= self.cfg.exit_z:
            return True, f"reverted_z_{z:.2f}"
        if abs(z) >= self.cfg.stop_z:
            return True, f"stop_z_{z:.2f}"
        return False, ""

===== END FILE: strategies/pair_stat_arb_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/pair_arb_executor_v1.py =====
GROUP: RESEARCH / PAIR ARB
REVIEW_FOCUS: Pair stat-arb executor/intent layer; review beta-weighted execution and PnL.
====================================================================================================

"""Two-leg executor for pair stat-arb — PAE1 (Opus 2026-06-09).

Turns a PairSignal (from pair_stat_arb_v1) into a concrete, market-neutral
two-leg plan: LONG the underperformer + SHORT the outperformer with equal notional
on ONE exchange (no cross-exchange transfers, no withdrawal keys). Pure planning +
position management + realized PnL — it returns ORDER INTENTS, it does NOT place
orders. Codex wires intents to the exchange (paper first). Risk is bounded by the
z-blowout stop.

Flow:
    plan_entry(signal, equity) -> (PairPosition, [OrderIntent x2])   # open
    plan_exit(position, px_long, px_short, cur_z) -> (reason, pnl, [OrderIntent x2]) or None
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

try:
    from strategies.pair_stat_arb_v1 import PairSignal, PairConfig
except Exception:  # standalone import for tests
    from pair_stat_arb_v1 import PairSignal, PairConfig  # type: ignore


@dataclass
class PairExecConfig:
    leg_frac_of_equity: float = 0.5    # notional per leg = equity * this (both legs ~equal)
    max_notional_per_leg: float = 100.0
    min_notional_per_leg: float = 10.0
    leverage: float = 1.0
    exit_z: float = 0.5                 # take profit: spread reverted
    stop_z: float = 3.5                 # bail: spread kept widening
    max_hold_bars: int = 96


@dataclass
class OrderIntent:
    symbol: str
    side: str          # "Buy" | "Sell"
    qty: float
    notional: float
    reduce_only: bool = False


@dataclass
class PairPosition:
    long_symbol: str
    short_symbol: str
    long_qty: float
    short_qty: float
    long_entry: float
    short_entry: float
    entry_z: float
    beta: float
    opened_bar: int = 0
    status: str = "PENDING"


def plan_entry(signal: PairSignal, equity: float, px_long: float, px_short: float,
               cfg: Optional[PairExecConfig] = None, opened_bar: int = 0):
    """Build the two opening legs (equal notional) + a PairPosition. Returns
    (position, [long_intent, short_intent]) or (None, []) if too small."""
    cfg = cfg or PairExecConfig()
    if px_long <= 0 or px_short <= 0 or equity <= 0:
        return None, []
    leg_notional = min(equity * cfg.leg_frac_of_equity * cfg.leverage, cfg.max_notional_per_leg)
    if leg_notional < cfg.min_notional_per_leg:
        return None, []
    long_qty = leg_notional / px_long
    short_qty = leg_notional / px_short
    pos = PairPosition(
        long_symbol=signal.long_symbol, short_symbol=signal.short_symbol,
        long_qty=long_qty, short_qty=short_qty, long_entry=px_long, short_entry=px_short,
        entry_z=signal.z, beta=signal.beta, opened_bar=opened_bar, status="OPEN",
    )
    intents = [
        OrderIntent(signal.long_symbol, "Buy", round(long_qty, 8), round(leg_notional, 4)),
        OrderIntent(signal.short_symbol, "Sell", round(short_qty, 8), round(leg_notional, 4)),
    ]
    return pos, intents


def pair_pnl(pos: PairPosition, px_long: float, px_short: float) -> float:
    """Realized/unrealized $ PnL of the pair = long leg + short leg."""
    long_pnl = (px_long - pos.long_entry) * pos.long_qty
    short_pnl = (pos.short_entry - px_short) * pos.short_qty
    return long_pnl + short_pnl


def plan_exit(pos: PairPosition, px_long: float, px_short: float, cur_z: float,
              cur_bar: int, cfg: Optional[PairExecConfig] = None):
    """Decide whether to close. Returns (reason, pnl, [close_intent x2]) or None."""
    cfg = cfg or PairExecConfig()
    if pos.status != "OPEN":
        return None
    reason = ""
    if abs(cur_z) <= cfg.exit_z:
        reason = f"reverted_z_{cur_z:.2f}"
    elif abs(cur_z) >= cfg.stop_z:
        reason = f"stop_z_{cur_z:.2f}"
    elif (cur_bar - pos.opened_bar) >= cfg.max_hold_bars:
        reason = "max_hold"
    if not reason:
        return None
    pnl = pair_pnl(pos, px_long, px_short)
    closes = [
        OrderIntent(pos.long_symbol, "Sell", round(pos.long_qty, 8), round(px_long * pos.long_qty, 4), reduce_only=True),
        OrderIntent(pos.short_symbol, "Buy", round(pos.short_qty, 8), round(px_short * pos.short_qty, 4), reduce_only=True),
    ]
    return reason, round(pnl, 6), closes

===== END FILE: strategies/pair_arb_executor_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: scripts/validate_pair_arb.py =====
GROUP: RESEARCH / PAIR ARB
REVIEW_FOCUS: Pair stat-arb validator; review realized PnL, funding, fee/slippage assumptions.
====================================================================================================

#!/usr/bin/env python3
"""Validate pair stat-arb (ETH/BTC etc.) through the Backtest Lab (Opus 2026-06-08).

Simulates the market-neutral pair strategy (strategies/pair_stat_arb_v1) on two
aligned close series and reports honest metrics via backtest.lab + a fee-sensitivity
sweep via backtest.robustness. This tells us whether the "calm arm" has any real
edge BEFORE any capital — net of trading costs on both legs.

Per-trade pair return approximation (market-neutral, equal notional per leg):
    profit ≈ sign(z_entry) * (entry_spread - exit_spread)  - round-trip fees(4 fills)
where spread = log(A) - beta*log(B) (≈ fractional pair return).

Run (Codex/server with data):
    python3 scripts/validate_pair_arb.py --a ETHUSDT --b BTCUSDT --interval 60
Offline self-test runs on synthetic cointegrated data.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.pair_stat_arb_v1 import PairStatArbV1, PairConfig, compute_spread
from backtest.lab import RunResult, report_from_result
from backtest.robustness import fee_sensitivity


def simulate_pair(prices_a: Sequence[float], prices_b: Sequence[float],
                  cfg: PairConfig | None = None, fee_bps: float = 6.0,
                  max_hold_bars: int = 168) -> List[Dict[str, float]]:
    """REWRITTEN 2026-06-10 (Claude audit): realizable P&L only.

    The original version booked profit as the change of a spread RE-FITTED with
    fresh beta/intercept at exit. That quantity is not realizable by the
    executor and inflated results massively (PF 4.78 fantasy on ETH/BTC; honest
    walk-forward of the same period: PF ~0.8, fee-fragile — see
    scripts/walkforward_pair_arb.py / scripts/fast_pair_research.py).

    Now: equal-notional legs, P&L = sign * (ret_long_leg - ret_short_leg) in
    log-returns per LEG notional, fees for 4 fills, plus a max-hold time stop
    (the executor has one; a sim without it can hold a divergence forever).
    """
    cfg = cfg or PairConfig()
    n = min(len(prices_a), len(prices_b))
    a, b = list(prices_a[:n]), list(prices_b[:n])
    eng = PairStatArbV1(cfg)
    trades: List[Dict[str, float]] = []
    in_pos = False
    entry_sign = 0  # +1: z>0 -> short A / long B; -1: long A / short B
    a_e = b_e = 0.0
    entry_i = 0
    fee_cost = 4.0 * fee_bps / 10000.0  # open 2 legs + close 2 legs
    lb = cfg.lookback

    def _book(i: int) -> None:
        nonlocal in_pos
        ret_a = math.log(a[i] / a_e)
        ret_b = math.log(b[i] / b_e)
        gross = entry_sign * (ret_b - ret_a)
        trades.append({"pnl": gross - fee_cost, "return_pct": gross - fee_cost,
                       "fees": fee_cost})
        in_pos = False

    for i in range(lb, n):
        wa, wb = a[: i + 1], b[: i + 1]
        d = eng.diagnostics(wa, wb)
        if not in_pos:
            if not d.get("tradeable"):
                continue
            z = d["z"]
            if abs(z) >= cfg.entry_z and abs(z) < cfg.stop_z:
                in_pos = True
                entry_sign = 1 if z > 0 else -1
                a_e, b_e = a[i], b[i]
                entry_i = i
        else:
            z = d.get("z", 0.0)
            exit_now, _ = eng.should_exit(z)
            if not d.get("tradeable"):
                exit_now = True  # lost cointegration mid-trade -> bail
            if not exit_now and (i - entry_i) >= max_hold_bars:
                exit_now = True
            if exit_now:
                _book(i)
    if in_pos:
        _book(n - 1)
    return trades


def _gen_cointegrated(n=400, beta=1.0, seed=0):
    import random
    rng = random.Random(seed)
    logb = [math.log(30000.0)]
    for _ in range(n - 1):
        logb.append(logb[-1] + rng.gauss(0, 0.01))
    s = [0.0]
    for _ in range(n - 1):
        s.append(0.8 * s[-1] + rng.gauss(0, 0.01))
    loga = [beta * lb + sp + math.log(0.05) for lb, sp in zip(logb, s)]
    return [math.exp(x) for x in loga], [math.exp(x) for x in logb]


def run_report(a, b, cfg=None, fee_bps=6.0, name="pair") -> Dict[str, Any]:
    trades = simulate_pair(a, b, cfg, fee_bps)
    rep = report_from_result(RunResult(trades=trades, meta={"name": name}))
    rets = [t["return_pct"] for t in trades]
    rep["fee_sensitivity"] = fee_sensitivity(rets, fee_bps_list=(6.0, 8.0, 10.0)) if rets else {"verdict": "no_trades"}
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=""); ap.add_argument("--b", default="")
    ap.add_argument("--interval", default="60")
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--lookback", type=int, default=168)
    args = ap.parse_args()
    cfg = PairConfig(lookback=args.lookback)
    if not args.a or not args.b:
        print("No --a/--b given → synthetic self-test (cointegrated pair):")
        a, b = _gen_cointegrated()
        import json
        print(json.dumps(run_report(a, b, cfg, args.fee_bps, "synthetic"), indent=2))
        return 0
    # real data: load aligned closes from cache (Codex/server)
    import glob, csv, json, os
    def load(sym):
        rows = {}
        for f in glob.glob(f"data_cache/{sym}_{args.interval}_*.json"):
            try:
                for r in json.load(open(f)):
                    rows[int(r["ts"])] = float(r["c"])
            except Exception:
                pass
        for f in glob.glob(f"data_cache/equities_1h/{sym}_*.csv") + glob.glob(f"data/equities_daily/{sym}*.csv"):
            try:
                for r in csv.DictReader(open(f)):
                    rows[int(r["ts"])] = float(r["c"])
            except Exception:
                pass
        return rows
    ra, rb = load(args.a), load(args.b)
    common = sorted(set(ra) & set(rb))
    a = [ra[t] for t in common]; b = [rb[t] for t in common]
    print(f"aligned bars: {len(a)}")
    if len(a) < cfg.lookback + 10:
        print("not enough aligned data (need cache); run on server with full data"); return 1
    import json
    print(json.dumps(run_report(a, b, cfg, args.fee_bps, f"{args.a}/{args.b}"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

===== END FILE: scripts/validate_pair_arb.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: scripts/walkforward_pair_arb.py =====
GROUP: RESEARCH / PAIR ARB
REVIEW_FOCUS: Pair stat-arb walk-forward runner; review IS/OOS pair/parameter selection.
====================================================================================================

#!/usr/bin/env python3
"""Walk-forward OOS validation of pair stat-arb on local kline cache (2026-06-10).

Builds 1h closes by resampling cached 5m bars (merging every cache file per
symbol), aligns the pair, then evaluates strategies/pair_stat_arb_v1 on rolling
out-of-sample folds (warmup = lookback bars before each fold, config FIXED — no
per-fold fitting, so every fold is honest OOS). Aggregates via
backtest.robustness.aggregate_oos + fee_sensitivity (4 fills per round trip).

Usage:
    python3 scripts/walkforward_pair_arb.py --a ETHUSDT --b BTCUSDT
    python3 scripts/walkforward_pair_arb.py --a SOLUSDT --b ETHUSDT --oos-days 30
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.pair_stat_arb_v1 import PairConfig, PairStatArbV1
from backtest.robustness import walk_forward_windows, aggregate_oos, fee_sensitivity

_HOUR_MS = 3_600_000

import math


def simulate_pair_realizable(prices_a, prices_b, cfg: PairConfig | None = None,
                             fee_bps: float = 6.0, max_hold_bars: int = 168) -> List[dict]:
    """Honest pair simulation: P&L = realizable log-returns of the two legs.

    Unlike scripts/validate_pair_arb.simulate_pair (which measures the change of
    a spread RE-FITTED with fresh beta/intercept at exit — not a realizable
    quantity), this books the trade exactly as the executor would: equal-notional
    LONG one leg + SHORT the other, P&L = ret(long) - ret(short) per leg notional.
    Includes a max-hold time stop (executor has one; the old sim did not).
    """
    cfg = cfg or PairConfig()
    n = min(len(prices_a), len(prices_b))
    a, b = list(prices_a[:n]), list(prices_b[:n])
    eng = PairStatArbV1(cfg)
    trades: List[dict] = []
    in_pos = False
    entry_sign = 0          # +1: z>0 -> short A long B ; -1: z<0 -> long A short B
    a_e = b_e = 0.0
    entry_i = 0
    fee_cost = 4.0 * fee_bps / 10000.0
    lb = cfg.lookback

    def book(i: int, reason: str) -> None:
        nonlocal in_pos
        ret_a = math.log(a[i] / a_e)
        ret_b = math.log(b[i] / b_e)
        gross = entry_sign * (ret_b - ret_a)
        trades.append({"pnl": gross - fee_cost, "return_pct": gross - fee_cost,
                       "fees": fee_cost, "hold_bars": i - entry_i, "exit_reason": reason})
        in_pos = False

    for i in range(lb, n):
        wa, wb = a[: i + 1], b[: i + 1]
        d = eng.diagnostics(wa, wb)
        if not in_pos:
            if not d.get("tradeable"):
                continue
            z = d["z"]
            if abs(z) >= cfg.entry_z and abs(z) < cfg.stop_z:
                in_pos = True
                entry_sign = 1 if z > 0 else -1
                a_e, b_e = a[i], b[i]
                entry_i = i
        else:
            z = d.get("z", 0.0)
            exit_now, why = eng.should_exit(z)
            if not d.get("tradeable"):
                # pair lost cointegration mid-trade -> bail (safety)
                exit_now, why = True, "lost_cointegration"
            if not exit_now and (i - entry_i) >= max_hold_bars:
                exit_now, why = True, "max_hold"
            if exit_now:
                book(i, why)
    if in_pos:
        book(n - 1, "end_of_data")
    return trades


def load_1h_closes(sym: str, cache_dir: str = "data_cache") -> Dict[int, float]:
    """Merge all 5m cache files for sym and resample to 1h closes.

    Bucket key = hour start (ms). Close = close of the LAST 5m bar in the hour.
    Merging overlapping files is safe: same ts -> same bar.
    """
    bars: Dict[int, Tuple[int, float]] = {}  # hour_start -> (bar_ts, close)
    for f in sorted(glob.glob(f"{cache_dir}/{sym}_5_*.json")):
        try:
            rows = json.load(open(f))
        except Exception:
            continue
        for r in rows:
            try:
                ts = int(r["ts"]); c = float(r["c"])
            except Exception:
                continue
            hour = ts - (ts % _HOUR_MS)
            prev = bars.get(hour)
            if prev is None or ts > prev[0]:
                bars[hour] = (ts, c)
    return {h: c for h, (_, c) in bars.items()}


def align(ra: Dict[int, float], rb: Dict[int, float]) -> Tuple[List[int], List[float], List[float]]:
    common = sorted(set(ra) & set(rb))
    return common, [ra[t] for t in common], [rb[t] for t in common]


def fold_metrics(trades: List[dict]) -> Dict[str, float]:
    if not trades:
        return {"profit_factor": 1.0, "return_pct": 0.0, "trades": 0,
                "win_rate": 0.0, "max_drawdown": 0.0}
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [-t["pnl"] for t in trades if t["pnl"] < 0]
    pf = (sum(wins) / sum(losses)) if losses else (99.0 if wins else 1.0)
    eq, peak, mdd = 1.0, 1.0, 0.0
    for t in trades:
        eq *= (1.0 + t["pnl"])
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    return {
        "profit_factor": round(min(pf, 99.0), 4),
        "return_pct": round((eq - 1.0) * 100.0, 4),
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades), 4),
        "max_drawdown": round(mdd * 100.0, 4),
    }


def run_walkforward(a_sym: str, b_sym: str, cfg: PairConfig, fee_bps: float,
                    oos_days: int, warmup_extra_bars: int = 24) -> dict:
    ts, a, b = align(load_1h_closes(a_sym), load_1h_closes(b_sym))
    if len(ts) < cfg.lookback + 200:
        return {"error": f"not_enough_aligned_bars_{len(ts)}"}
    warmup_bars = cfg.lookback + warmup_extra_bars
    warmup_days = max(1, (warmup_bars + 23) // 24)
    folds = walk_forward_windows(ts[0], ts[-1] + _HOUR_MS,
                                 is_days=warmup_days, oos_days=oos_days)
    per_fold: List[Dict[str, float]] = []
    all_trades: List[dict] = []
    fold_rows = []
    for fd in folds:
        idx = [i for i, t in enumerate(ts) if fd["is_start"] <= t < fd["oos_end"]]
        if len(idx) <= warmup_bars + 10:
            continue
        s, e = idx[0], idx[-1] + 1
        trades = simulate_pair_realizable(a[s:e], b[s:e], cfg, fee_bps)
        m = fold_metrics(trades)
        per_fold.append(m)
        all_trades.extend(trades)
        from datetime import datetime, timezone
        fold_rows.append({
            "oos_start": datetime.fromtimestamp(fd["oos_start"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            **m,
        })
    gross = [t["pnl"] + t.get("fees", 0.0) for t in all_trades]
    return {
        "pair": f"{a_sym}/{b_sym}",
        "aligned_bars_1h": len(ts),
        "config": vars(cfg),
        "fee_bps_per_fill": fee_bps,
        "folds_detail": fold_rows,
        "oos_aggregate": aggregate_oos(per_fold),
        "win_rate_all": round(sum(1 for t in all_trades if t["pnl"] > 0) / len(all_trades), 4) if all_trades else None,
        "total_oos_trades": len(all_trades),
        "fee_sensitivity": fee_sensitivity(gross, fee_bps_list=(6.0, 8.0, 10.0, 12.0), sides=4) if gross else {"verdict": "no_trades"},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="ETHUSDT")
    ap.add_argument("--b", default="BTCUSDT")
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--lookback", type=int, default=168)
    ap.add_argument("--oos-days", type=int, default=30)
    ap.add_argument("--entry-z", type=float, default=2.0)
    ap.add_argument("--exit-z", type=float, default=0.5)
    ap.add_argument("--stop-z", type=float, default=3.5)
    args = ap.parse_args()
    cfg = PairConfig(lookback=args.lookback, entry_z=args.entry_z,
                     exit_z=args.exit_z, stop_z=args.stop_z)
    out = run_walkforward(args.a, args.b, cfg, args.fee_bps, args.oos_days)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

===== END FILE: scripts/walkforward_pair_arb.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: scripts/fast_pair_research.py =====
GROUP: RESEARCH / PAIR ARB
REVIEW_FOCUS: Fast pair research; review p-hacking controls and WF criteria.
====================================================================================================

#!/usr/bin/env python3
"""Fast vectorized pair stat-arb research with honest walk-forward (2026-06-10).

Why this exists: scripts/validate_pair_arb.py measured P&L as the change of a
spread RE-FITTED at exit (fresh beta+intercept) — not realizable; it produced
PF 4.78 fantasies. Here:
  * P&L = realizable log-returns of the two legs as the executor would book them
    (equal-notional or beta-weighted), per unit TOTAL notional, fees on 4 fills;
  * rolling OLS (beta/intercept/z) vectorized via cumulative sums (numpy);
  * rolling |corr| gate of 1h returns, like PairStatArbV1;
  * honest walk-forward: pick config on IN-SAMPLE only, evaluate on OOS.

Usage:
  python3 scripts/fast_pair_research.py --a ETHUSDT --b BTCUSDT
  python3 scripts/fast_pair_research.py --a SOLUSDT --b ETHUSDT --is-days 90 --oos-days 30
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_HOUR_MS = 3_600_000


def load_1h_closes(sym: str, cache_dir: str = "data_cache") -> Dict[int, float]:
    bars: Dict[int, Tuple[int, float]] = {}
    for f in sorted(glob.glob(f"{cache_dir}/{sym}_5_*.json")):
        try:
            rows = json.load(open(f))
        except Exception:
            continue
        for r in rows:
            try:
                ts = int(r["ts"]); c = float(r["c"])
            except Exception:
                continue
            hour = ts - (ts % _HOUR_MS)
            prev = bars.get(hour)
            if prev is None or ts > prev[0]:
                bars[hour] = (ts, c)
    return {h: c for h, (_, c) in bars.items()}


def _rolling_sums(x: np.ndarray, L: int) -> np.ndarray:
    c = np.concatenate(([0.0], np.cumsum(x)))
    out = np.full(len(x), np.nan)
    out[L - 1:] = c[L:] - c[:-L]
    return out


def rolling_ols_z(la: np.ndarray, lb: np.ndarray, L: int):
    """Rolling OLS la = slope*lb + c over trailing L bars. Returns slope, z of
    the LAST residual in each window (z = resid / std(resid))."""
    Sx = _rolling_sums(lb, L); Sy = _rolling_sums(la, L)
    Sxx = _rolling_sums(lb * lb, L); Syy = _rolling_sums(la * la, L)
    Sxy = _rolling_sums(la * lb, L)
    with np.errstate(invalid="ignore", divide="ignore"):
        den = L * Sxx - Sx * Sx
        slope = (L * Sxy - Sx * Sy) / den
        intercept = (Sy - slope * Sx) / L
        resid_last = la - slope * lb - intercept
        ssr = (Syy - Sy * Sy / L) - slope * slope * (Sxx - Sx * Sx / L)
        ssr = np.maximum(ssr, 0.0)
        std = np.sqrt(ssr / max(L - 1, 1))
        z = np.where(std > 0, resid_last / std, 0.0)
    return slope, z


def rolling_corr_returns(la: np.ndarray, lb: np.ndarray, L: int) -> np.ndarray:
    ra = np.diff(la, prepend=la[0])
    rb = np.diff(lb, prepend=lb[0])
    Sa = _rolling_sums(ra, L); Sb = _rolling_sums(rb, L)
    Saa = _rolling_sums(ra * ra, L); Sbb = _rolling_sums(rb * rb, L)
    Sab = _rolling_sums(ra * rb, L)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = Sab - Sa * Sb / L
        va = Saa - Sa * Sa / L
        vb = Sbb - Sb * Sb / L
        corr = cov / np.sqrt(va * vb)
    return corr


def simulate(la: np.ndarray, lb: np.ndarray, slope: np.ndarray, z: np.ndarray,
             corr: np.ndarray, s: int, e: int, entry_z: float, exit_z: float,
             stop_z: float, max_hold: int, fee_bps: float, beta_weighted: bool,
             min_abs_corr: float = 0.6) -> List[dict]:
    """Event loop on precomputed arrays, trading only inside [s, e)."""
    fee = fee_bps / 10000.0
    trades: List[dict] = []
    in_pos = False
    sign = 0; ia = 0; beta_e = 1.0
    for i in range(s, e):
        zi = z[i]
        if not np.isfinite(zi):
            continue
        if not in_pos:
            if abs(corr[i]) < min_abs_corr or not np.isfinite(slope[i]) or slope[i] <= 0:
                continue
            if entry_z <= abs(zi) < stop_z:
                in_pos = True
                sign = 1 if zi > 0 else -1
                ia = i
                beta_e = float(np.clip(slope[i], 0.3, 3.0)) if beta_weighted else 1.0
        else:
            exit_now = abs(zi) <= exit_z or abs(zi) >= stop_z or (i - ia) >= max_hold
            if i == e - 1:
                exit_now = True
            if exit_now:
                ret_a = la[i] - la[ia]
                ret_b = lb[i] - lb[ia]
                # sign=+1: short A (1x), long B (beta x). per TOTAL notional:
                gross = sign * (beta_e * ret_b - ret_a) / (1.0 + beta_e)
                net = gross - 2.0 * fee  # 4 fills, each on half the total notional
                trades.append({"pnl": net, "hold": i - ia})
                in_pos = False
    return trades


def metrics(trades: List[dict]) -> Dict[str, float]:
    if not trades:
        return {"profit_factor": 1.0, "return_pct": 0.0, "trades": 0,
                "win_rate": 0.0, "max_drawdown": 0.0}
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [-t["pnl"] for t in trades if t["pnl"] < 0]
    pf = (sum(wins) / sum(losses)) if losses else (99.0 if wins else 1.0)
    eq, peak, mdd = 1.0, 1.0, 0.0
    for t in trades:
        eq *= (1.0 + t["pnl"])
        peak = max(peak, eq); mdd = max(mdd, (peak - eq) / peak)
    return {"profit_factor": round(min(pf, 99.0), 3),
            "return_pct": round((eq - 1.0) * 100.0, 3),
            "trades": len(trades),
            "win_rate": round(len(wins) / len(trades), 3),
            "max_drawdown": round(mdd * 100.0, 3)}


GRID = {
    "lookback": (120, 168, 240, 336),
    "entry_z": (1.5, 2.0, 2.5),
    "exit_z": (0.0, 0.5),
    "max_hold": (72, 168),
    "beta_weighted": (True, False),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="ETHUSDT")
    ap.add_argument("--b", default="BTCUSDT")
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--is-days", type=int, default=90)
    ap.add_argument("--oos-days", type=int, default=30)
    ap.add_argument("--stop-z", type=float, default=3.5)
    args = ap.parse_args()

    ra, rb = load_1h_closes(args.a), load_1h_closes(args.b)
    common = sorted(set(ra) & set(rb))
    la = np.log(np.array([ra[t] for t in common]))
    lb = np.log(np.array([rb[t] for t in common]))
    n = len(common)
    print(f"# {args.a}/{args.b}: aligned 1h bars = {n} "
          f"({(common[-1]-common[0])/86400000:.0f} days)", file=sys.stderr)

    # precompute per lookback
    pre = {}
    for L in GRID["lookback"]:
        slope, z = rolling_ols_z(la, lb, L)
        corr = rolling_corr_returns(la, lb, L)
        pre[L] = (slope, z, corr)

    is_bars = args.is_days * 24
    oos_bars = args.oos_days * 24
    folds = []
    cur = max(GRID["lookback"])  # leave warmup for largest lookback
    while cur + is_bars + oos_bars <= n:
        folds.append((cur, cur + is_bars, cur + is_bars + oos_bars))
        cur += oos_bars

    combos = list(itertools.product(*GRID.values()))
    keys = list(GRID.keys())
    fold_rows = []
    oos_all: List[dict] = []
    for (fs, fm, fe) in folds:
        best = None
        for combo in combos:
            cfg = dict(zip(keys, combo))
            slope, z, corr = pre[cfg["lookback"]]
            tr = simulate(la, lb, slope, z, corr, fs, fm, cfg["entry_z"],
                          cfg["exit_z"], args.stop_z, cfg["max_hold"],
                          args.fee_bps, cfg["beta_weighted"])
            m = metrics(tr)
            if m["trades"] < 5:
                continue
            score = m["return_pct"]
            if best is None or score > best[0]:
                best = (score, cfg, m)
        if best is None:
            fold_rows.append({"fold_start_bar": fs, "note": "no_config_with_5_trades_IS"})
            continue
        _, cfg, m_is = best
        slope, z, corr = pre[cfg["lookback"]]
        tr_oos = simulate(la, lb, slope, z, corr, fm, fe, cfg["entry_z"],
                          cfg["exit_z"], args.stop_z, cfg["max_hold"],
                          args.fee_bps, cfg["beta_weighted"])
        m_oos = metrics(tr_oos)
        oos_all.extend(tr_oos)
        from datetime import datetime, timezone
        fold_rows.append({
            "oos_start": datetime.fromtimestamp(common[fm] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            "picked": cfg, "is_return_pct": m_is["return_pct"],
            "oos": m_oos,
        })

    pfs = [r["oos"]["profit_factor"] for r in fold_rows if "oos" in r]
    rets = [r["oos"]["return_pct"] for r in fold_rows if "oos" in r]
    out = {
        "pair": f"{args.a}/{args.b}",
        "bars_1h": n,
        "folds": len(fold_rows),
        "oos_pf_median": round(float(np.median(pfs)), 3) if pfs else None,
        "oos_pf_min": round(min(pfs), 3) if pfs else None,
        "oos_ret_median_pct": round(float(np.median(rets)), 3) if rets else None,
        "oos_ret_total_pct": round(float((np.prod([1 + t["pnl"] for t in oos_all]) - 1) * 100), 3) if oos_all else None,
        "oos_trades": len(oos_all),
        "oos_win_rate": round(sum(1 for t in oos_all if t["pnl"] > 0) / len(oos_all), 3) if oos_all else None,
        "verdict": ("robust" if pfs and float(np.median(pfs)) > 1.0 and min(pfs) > 0.5 else "fragile"),
        "folds_detail": fold_rows,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

===== END FILE: scripts/fast_pair_research.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/equities_swing_active_v1.py =====
GROUP: ALPACA / ACTIVE SWING
REVIEW_FOCUS: Alpaca active trailing swing; needs RSI/input/metrics fixes and wide WF.
====================================================================================================

"""PDT-safe active swing selector for a small Alpaca account (Opus 2026-06-08).

Problem: a US equities account under $25k is capped at 3 day-trades / 5 days
(PDT rule). So "more active intraday" is regulatorily blocked at $500-1000.

Smart workaround: trade ACTIVE SWING instead of intraday — hold 2-10 days,
rotate a wider universe more often than the monthly sleeve, and never round-trip
the same name same-day. That is "more active" without tripping PDT.

Selection = blend of:
  - momentum (20d + 60d return, trend must be up: price > SMA50)
  - a pullback bonus (buy strength on a dip, not after it is overbought)
Pure stdlib, unit-tested offline. Wiring into the Alpaca bridge + real backtest
(walk-forward via backtest/robustness.py) is Codex's step before live.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple


@dataclass
class SwingConfig:
    mom_fast: int = 20
    mom_slow: int = 60
    sma_trend: int = 50
    rsi_period: int = 14
    rsi_max: float = 78.0        # skip already-overbought (chasing tops)
    rsi_pullback_lo: float = 40.0  # sweet spot: pullback within uptrend
    rsi_pullback_hi: float = 60.0
    top_n: int = 5
    max_positions: int = 4       # sized for $500-1000 (a few names, not 1)
    min_hold_days: int = 2       # PDT-safe: never same-day round trip
    market_sma: int = 50         # market-regime gate: skip longs if market < its SMA
    max_per_sector: int = 2      # diversification: cap picks per sector
    require_relative_strength: bool = False  # only names outperforming the market
    rs_lookback: int = 60        # window for relative-strength comparison
    w_mom: float = 0.6
    w_pullback: float = 0.4


def _sma(xs: Sequence[float], n: int) -> float:
    if len(xs) < n or n <= 0:
        return float("nan")
    return sum(xs[-n:]) / n


def _rsi(closes: Sequence[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    gains = losses = 0.0
    for i in range(-period, 0):
        ch = closes[i] - closes[i - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


def _ret(closes: Sequence[float], n: int) -> float:
    if len(closes) <= n or closes[-n - 1] <= 0:
        return float("nan")
    return closes[-1] / closes[-n - 1] - 1.0


def score_symbol(closes: Sequence[float], cfg: Optional[SwingConfig] = None) -> Dict[str, float]:
    cfg = cfg or SwingConfig()
    need = max(cfg.mom_slow, cfg.sma_trend, cfg.rsi_period) + 2
    if len(closes) < need:
        return {"eligible": False, "reason": "history_short", "score": 0.0}
    price = closes[-1]
    sma = _sma(closes, cfg.sma_trend)
    rsi = _rsi(closes, cfg.rsi_period)
    mom_f = _ret(closes, cfg.mom_fast)
    mom_s = _ret(closes, cfg.mom_slow)
    if not all(math.isfinite(x) for x in (sma, rsi, mom_f, mom_s)):
        return {"eligible": False, "reason": "nan", "score": 0.0}
    trend_ok = price > sma
    if not trend_ok:
        return {"eligible": False, "reason": "below_sma", "score": 0.0, "rsi": rsi}
    if rsi >= cfg.rsi_max:
        return {"eligible": False, "reason": "overbought", "score": 0.0, "rsi": rsi}
    momentum = 0.5 * mom_f + 0.5 * mom_s          # blended momentum
    # pullback bonus: peaks when RSI sits in the [lo,hi] band (dip within uptrend)
    mid = (cfg.rsi_pullback_lo + cfg.rsi_pullback_hi) / 2.0
    half = max(1e-9, (cfg.rsi_pullback_hi - cfg.rsi_pullback_lo) / 2.0)
    pullback = max(0.0, 1.0 - abs(rsi - mid) / half)
    score = cfg.w_mom * momentum + cfg.w_pullback * (pullback * 0.05)  # scale pullback to return-units
    return {
        "eligible": True, "reason": "ok", "score": round(score, 6),
        "momentum": round(momentum, 6), "pullback": round(pullback, 4),
        "rsi": round(rsi, 2), "trend_ok": True,
    }


def market_regime_ok(market_closes: Sequence[float], sma_period: int = 50) -> bool:
    """Safety gate: only go long when the market proxy is above its SMA (uptrend).
    Pass an index series (e.g. SPY, or an equal-weight basket of the universe)."""
    if not market_closes or len(market_closes) < sma_period:
        return True  # no data -> do not block
    return market_closes[-1] > _sma(market_closes, sma_period)


def select(
    universe_closes: Dict[str, Sequence[float]],
    cfg: Optional[SwingConfig] = None,
    market_closes: Optional[Sequence[float]] = None,
    sector_map: Optional[Dict[str, str]] = None,
    quality_scorer: Optional[Callable[[str, Dict[str, float], Sequence[float]], Optional[float]]] = None,
) -> List[Tuple[str, Dict[str, float]]]:
    """Return ranked [(symbol, score_dict)], best first, top_n.

    Safety: if market_closes is given and the market is below its SMA, return []
    (do not buy strength into a falling market). If sector_map is given, cap picks
    per sector (cfg.max_per_sector) for diversification.
    """
    cfg = cfg or SwingConfig()
    if market_closes is not None and not market_regime_ok(market_closes, cfg.market_sma):
        return []
    mkt_ret = _ret(market_closes, cfg.rs_lookback) if market_closes is not None else None
    scored = []
    for sym, closes in universe_closes.items():
        sc = score_symbol(closes, cfg)
        if not sc.get("eligible"):
            continue
        # relative strength: keep only names outperforming the market
        if cfg.require_relative_strength and mkt_ret is not None and math.isfinite(mkt_ret):
            sym_ret = _ret(closes, cfg.rs_lookback)
            if not (math.isfinite(sym_ret) and sym_ret > mkt_ret):
                continue
        # optional pluggable quality scorer (e.g. an AI/news filter) — multiplies
        # the base score; returning None or <=0 drops the candidate.
        if quality_scorer is not None:
            q = quality_scorer(sym, sc, closes)
            if q is None or q <= 0:
                continue
            sc = dict(sc); sc["score"] = sc["score"] * float(q); sc["quality_mult"] = float(q)
        scored.append((sym, sc))
    scored.sort(key=lambda kv: kv[1]["score"], reverse=True)
    if sector_map is None:
        return scored[: cfg.top_n]
    picked: List[Tuple[str, Dict[str, float]]] = []
    per_sector: Dict[str, int] = {}
    for sym, sc in scored:
        sect = sector_map.get(sym, "other")
        if per_sector.get(sect, 0) >= cfg.max_per_sector:
            continue
        picked.append((sym, sc))
        per_sector[sect] = per_sector.get(sect, 0) + 1
        if len(picked) >= cfg.top_n:
            break
    return picked


def is_day_trade_safe(entry_ts: int, now_ts: int, min_hold_days: int = 2) -> bool:
    """True if closing now would NOT be a same-day round trip (PDT-safe)."""
    return (now_ts - entry_ts) >= min_hold_days * 86400

===== END FILE: strategies/equities_swing_active_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: configs/alpaca_v38_hybrid_top4_candidate.env =====
GROUP: ALPACA / V38 EXECUTION
REVIEW_FOCUS: v38 candidate config; review non-secret execution/protection settings.
====================================================================================================

## Alpaca monthly v38 hybrid top4 candidate
## Created: 2026-04-28
##
## Purpose:
## - preserve the best bounded v38 hybrid found in the 2026-04-28 OOS probe
## - keep it separate from the currently deployed paper config until broker-side
##   protection and one fresh paper cycle are verified
##
## Evidence from local OOS probe:
## - full 2024-05..2026-04: +50.77%, annualized ~22.79%, PF 6.29,
##   WR 82.9%, trades 35, max monthly DD -2.28%, negative months 2/24
## - OOS 2025-05..2026-04: +27.95%, PF 7.85, WR 86.7%,
##   trades 15, max monthly DD -2.28%, negative months 1/12
##
## Backtest run dirs:
## - backtest_runs/equities_monthly_research_20260428_081347_codex_hybrid_hybrid_top4_t32_full_20260428
## - backtest_runs/equities_monthly_research_20260428_081350_codex_hybrid_hybrid_top4_t32_y2_oos_20260428

ALPACA_AUTOPILOT_REFRESH=1
ALPACA_AUTOPILOT_REFRESH_SCRIPT=scripts/run_equities_monthly_v36_refresh.sh
ALPACA_AUTOPILOT_RUNTIME_DIR=runtime/equities_monthly_v36
EQ_V36_RUNTIME_DIR=runtime/equities_monthly_v36

EQ_V36_TAG=equities_monthly_v38_hybrid_top4_t32
EQ_V36_SIM_START_MONTH=2024-05
EQ_V36_SIM_END_MONTH=2026-04
EQ_V36_SIM_MAX_HOLD_DAYS=22
EQ_V36_SIM_MIN_MOM_LOOKBACK_PCT=5.0
EQ_V36_SIM_STOP_ATR_MULT=2.0
EQ_V36_SIM_TARGET_ATR_MULT=3.2
EQ_V36_SIM_INTRAMONTH_PORTFOLIO_STOP_PCT=0.08
EQ_V36_SIM_BE_TRIGGER_R=0.8
EQ_V36_SIM_TRAIL_ATR_MULT=1.5

EQ_V36_CURRENT_TOP_N=4
EQ_V36_CURRENT_LOOKBACK_DAYS=28
EQ_V36_CURRENT_MIN_MOM_LOOKBACK_PCT=5.0
EQ_V36_CURRENT_UNIVERSE_TOP_K=18
EQ_V36_CURRENT_STOP_ATR_MULT=2.0
EQ_V36_CURRENT_TARGET_ATR_MULT=3.2

## Paper/live bridge sizing. Keep small until native broker-side protection is added.
ALPACA_MAX_POSITIONS=4
ALPACA_TARGET_ALLOC_PCT=0.70
ALPACA_MIN_DOLLAR_ORDER=25
ALPACA_CAPITAL_OVERRIDE_USD=500
ALPACA_CLOSE_STALE_POSITIONS=1

## Approximation of BE 0.8R + 1.5 ATR trailing in current bridge terms.
MONTHLY_SL_ENABLE=1
MONTHLY_SL_PCT=0.05
MONTHLY_TRAIL_ENABLE=1
MONTHLY_TRAIL_MIN_GAIN_PCT=3.5
MONTHLY_TRAIL_PCT=0.035

## Broker-side entry protection for the final paper gate.
## Alpaca rejects fractional bracket orders, so small-account mode uses a
## fractional market entry plus an immediate broker-hosted DAY stop order.
## If the stop cannot be placed, the bridge attempts to close the position.
## After a position gains enough, the bridge promotes whole-share positions to
## Alpaca native trailing_stop. Alpaca does not support fractional trailing_stop
## orders, so fractional small-account positions use software trailing: cancel
## fixed stop -> close position -> never immediately rebuy the same symbol.
ALPACA_BROKER_PROTECTION_ENABLE=1
ALPACA_BROKER_PROTECTION_REQUIRED=1
ALPACA_BROKER_PROTECTION_ORDER_CLASS=simple_stop
ALPACA_BROKER_PROTECTION_SIZE_MODE=qty
ALPACA_BROKER_PROTECTION_TIF=day
ALPACA_BROKER_PROTECTION_WAIT_FILL_SEC=20
ALPACA_NATIVE_TRAIL_ENABLE=1
ALPACA_NATIVE_TRAIL_REQUIRED=0
ALPACA_NATIVE_TRAIL_TIF=day
ALPACA_NATIVE_TRAIL_MIN_GAIN_PCT=3.5
ALPACA_NATIVE_TRAIL_PERCENT=3.5
ALPACA_NATIVE_TRAIL_CANCEL_EXISTING_STOPS=1
MONTHLY_REENTRY_BLOCK_ENABLE=1
MONTHLY_TRAIL_REENTRY_BLOCK_DAYS=21

===== END FILE: configs/alpaca_v38_hybrid_top4_candidate.env =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: scripts/equities_alpaca_paper_bridge.py =====
GROUP: ALPACA / V38 EXECUTION
REVIEW_FOCUS: Alpaca paper bridge; review broker-side protection, trailing/stop, real-money gate.
====================================================================================================

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

# Optional earnings filter (graceful fallback if import fails)
try:
    _scripts_dir = Path(__file__).resolve().parent
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))
    from equities_earnings_filter import filter_safe_picks as _filter_earnings
    _EARNINGS_FILTER_OK = True
except ImportError:
    _EARNINGS_FILTER_OK = False
    def _filter_earnings(symbols, **kw):  # type: ignore[misc]
        return {s: (True, "filter_unavailable") for s in symbols}


def _tg_send(token: str, chat_id: str, msg: str) -> None:
    """Send a message to Telegram. Silent on failure."""
    if not token or not chat_id:
        return
    import ssl as _ssl
    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "HTML",
    }).encode()
    req_tg = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    ctx = _ssl.create_default_context()
    try:
        with request.urlopen(req_tg, context=ctx, timeout=10):
            pass
    except Exception:
        pass


def _tg_dedupe_state_path() -> Path:
    raw = _env("ALPACA_TG_DEDUPE_STATE", "")
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent.parent / "runtime" / "alpaca_tg_dedupe.json"


def _is_actionable_equities_report(report: dict[str, Any]) -> bool:
    passive_actions = {"hold_existing", "hold_pending_buy"}
    results = report.get("results") or []
    if not results:
        return False
    return any(str(r.get("action") or "") not in passive_actions for r in results if isinstance(r, dict))


def _tg_send_equities_report(token: str, chat_id: str, msg: str, report: dict[str, Any]) -> None:
    """Suppress repeated HOLD-only reports while preserving BUY/CLOSE/STOP alerts."""
    if _is_actionable_equities_report(report) or not _env_bool("ALPACA_TG_DEDUPE_HOLD_ONLY", True):
        _tg_send(token, chat_id, msg)
        return

    window_sec = max(0, _env_int("ALPACA_TG_DEDUPE_HOLD_SEC", 21600))
    if window_sec <= 0:
        _tg_send(token, chat_id, msg)
        return

    digest = hashlib.sha256(msg.encode("utf-8", errors="replace")).hexdigest()
    path = _tg_dedupe_state_path()
    now = time.time()
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        state = {}
    previous = state.get("equities_hold_only") if isinstance(state, dict) else {}
    if (
        isinstance(previous, dict)
        and previous.get("digest") == digest
        and now - float(previous.get("ts") or 0.0) < window_sec
    ):
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    state["equities_hold_only"] = {"digest": digest, "ts": now}
    path.write_text(json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    _tg_send(token, chat_id, msg)


@dataclass
class Pick:
    month: str
    ticker: str
    entry_day: str
    score: float
    atr20_pct: float
    momentum20_pct: float
    momentum60_pct: float
    pullback60_pct: float
    universe_score: float | None
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    weight: float | None = None


def _env(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return str(val).strip() if val is not None else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _live_order_guard_errors(
    *,
    base_url: str,
    send_orders: bool,
    capital_override_usd: float,
) -> list[str]:
    """Fail closed before the paper bridge is allowed to touch a live account."""
    if not send_orders or "paper" in str(base_url).lower():
        return []

    errors: list[str] = []
    if _env("ALPACA_LIVE_ACCOUNT_ROLE").lower() != "monthly_v38":
        errors.append("ALPACA_LIVE_ACCOUNT_ROLE must be monthly_v38")
    if _env("ALPACA_LIVE_CONFIRM") != "MONTHLY_V38_LIVE":
        errors.append("ALPACA_LIVE_CONFIRM must be MONTHLY_V38_LIVE")

    max_capital = max(1.0, _env_float("ALPACA_LIVE_MAX_CAPITAL_USD", 500.0))
    if capital_override_usd <= 0:
        errors.append("ALPACA_CAPITAL_OVERRIDE_USD must be set for live orders")
    elif capital_override_usd > max_capital:
        errors.append(
            f"ALPACA_CAPITAL_OVERRIDE_USD={capital_override_usd:.2f} exceeds "
            f"ALPACA_LIVE_MAX_CAPITAL_USD={max_capital:.2f}"
        )
    return errors


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _optional_float(value: Any) -> float | None:
    try:
        text = str(value if value is not None else "").strip()
        if not text:
            return None
        parsed = float(text)
        return parsed if math.isfinite(parsed) else None
    except Exception:
        return None


def _format_price(price: float) -> str:
    if price < 1.0:
        return f"{price:.4f}"
    return f"{price:.2f}"


def _format_qty(qty: float) -> str:
    return f"{qty:.9f}".rstrip("0").rstrip(".")


def _is_fractional_qty(qty: float) -> bool:
    return abs(qty - round(qty)) > 1e-8


def _latest_summary_path(picks_csv: Path) -> Path | None:
    current_cycle_summary = _env("ALPACA_CURRENT_CYCLE_SUMMARY_CSV", "")
    if current_cycle_summary:
        path = Path(current_cycle_summary)
        if path.exists() and picks_csv.name == "current_cycle_picks.csv":
            return path
    env_path = _env("EQ_LATEST_SUMMARY_CSV", "")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path
    if picks_csv.name == "current_cycle_picks.csv":
        runtime_candidate = picks_csv.parent / "current_cycle_summary.csv"
        if runtime_candidate.exists():
            return runtime_candidate
    candidate = picks_csv.parent / "summary.csv"
    return candidate if candidate.exists() else None


def _load_summary_row(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    try:
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return rows[0] if rows else {}
    except Exception:
        return {}


def _deepseek_chat(system: str, user: str) -> str:
    api_key = _env("DEEPSEEK_API_KEY")
    if not api_key:
        return ""
    url = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/chat/completions"
    payload = {
        "model": _env("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 220,
    }
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, context=ssl.create_default_context(), timeout=float(_env("DEEPSEEK_TIMEOUT_SEC", "12") or 12)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw else {}
        choices = data.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", "")).strip()
    except Exception:
        return ""


def _extract_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _alpaca_advisory_path(picks_csv: Path) -> Path:
    raw = _env("ALPACA_DEEPSEEK_ADVISORY_PATH", "")
    if raw:
        return Path(raw)
    runtime_dir = (
        _env("ALPACA_AUTOPILOT_RUNTIME_DIR", "")
        or _env("EQ_V35_RUNTIME_DIR", "")
        or _env("EQ_BASELINE_RUNTIME_DIR", "")
    )
    if runtime_dir:
        return Path(runtime_dir) / "latest_advisory.json"
    return picks_csv.parent / "latest_advisory.json"


def _load_offline_snapshot(picks_csv: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    snapshot_raw = _env("ALPACA_OFFLINE_SNAPSHOT_JSON", "")
    candidates: list[Path] = []
    if snapshot_raw:
        candidates.append(Path(snapshot_raw))
    candidates.append(_alpaca_advisory_path(picks_csv))

    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        report = payload.get("report") if isinstance(payload, dict) else None
        report = report if isinstance(report, dict) else payload if isinstance(payload, dict) else {}
        buying_power = _safe_float(report.get("buying_power"), _env_float("ALPACA_OFFLINE_BUYING_POWER", 0.0))
        cash = _safe_float(report.get("cash"), _env_float("ALPACA_OFFLINE_CASH", buying_power))
        positions_raw = report.get("positions_before") or []
        positions: list[dict[str, Any]] = []
        if isinstance(positions_raw, list):
            for pos in positions_raw:
                if not isinstance(pos, dict):
                    continue
                positions.append(
                    {
                        "symbol": str(pos.get("ticker") or pos.get("symbol") or "").strip().upper(),
                        "qty": str(pos.get("qty") or ""),
                        "market_value": str(pos.get("market_value") or ""),
                    }
                )
        account = {
            "buying_power": buying_power,
            "cash": cash,
        }
        return account, positions, str(path)

    buying_power = _env_float("ALPACA_OFFLINE_BUYING_POWER", 0.0)
    cash = _env_float("ALPACA_OFFLINE_CASH", buying_power)
    return {"buying_power": buying_power, "cash": cash}, [], ""


def _alpaca_ai_advisory(
    *,
    report: dict[str, Any],
    summary_row: dict[str, str],
    picks_csv: Path,
) -> dict[str, Any]:
    enabled = _env_bool("ALPACA_DEEPSEEK_ADVISORY_ENABLE", _env_bool("ALPACA_DEEPSEEK_NOTE_ENABLE", False))
    if not enabled:
        return {}
    if not _env("DEEPSEEK_API_KEY"):
        return {}

    max_chars = max(240, _env_int("ALPACA_DEEPSEEK_ADVISORY_MAX_CHARS", _env_int("ALPACA_DEEPSEEK_NOTE_MAX_CHARS", 420)))
    positions = report.get("positions_before") or []
    selected = report.get("selected") or []
    pos_lines = []
    for pos in positions[:5]:
        sym = str(pos.get("ticker") or "?")
        mv = _safe_float(pos.get("market_value"))
        pos_lines.append(f"{sym}:${mv:.0f}")
    sel_lines = []
    for row in selected[:5]:
        sym = str(row.get("ticker") or "?")
        score = _safe_float(row.get("score"))
        mom60 = _safe_float(row.get("momentum60_pct"))
        pb60 = _safe_float(row.get("pullback60_pct"))
        sel_lines.append(f"{sym}(score={score:.3f},mom60={mom60:.1f},pb60={pb60:.1f})")

    cycle_reason = str(report.get("cycle_reason") or "")
    summary_bits = (
        f"ret={_safe_float(summary_row.get('compounded_return_pct')):.2f}% "
        f"trades={_safe_int(summary_row.get('trades'))} "
        f"pf={_safe_float(summary_row.get('profit_factor')):.3f} "
        f"winrate={_safe_float(summary_row.get('winrate_pct')):.1f}% "
        f"active_months={_safe_int(summary_row.get('months'))} "
        f"calendar_months={_safe_int(summary_row.get('calendar_months'))} "
        f"inactive_months={_safe_int(summary_row.get('inactive_months'))} "
        f"neg_months={_safe_int(summary_row.get('negative_months'))} "
        f"max_month_dd={_safe_float(summary_row.get('max_monthly_dd_pct')):.2f}%"
    )

    system = (
        "Ты аккуратный equities monthly sleeve advisor. "
        "Верни только JSON-объект с ключами verdict, next_action, note. "
        "verdict: one of hold_flat, close_stale, keep_positions, buy_selected, refresh_watch. "
        "next_action: one short snake_case phrase. "
        "note: short Russian explanation <= 220 chars, practical, no disclaimers."
    )
    user = (
        f"status={report.get('status')}\n"
        f"cycle_reason={cycle_reason}\n"
        f"month={report.get('month')}\n"
        f"picks_csv={picks_csv}\n"
        f"latest_entry_day={report.get('latest_entry_day')}\n"
        f"pick_age_days={report.get('pick_age_days')}\n"
        f"refresh_age_hours={report.get('refresh_age_hours')}\n"
        f"stale_positions={','.join(report.get('stale_positions') or []) or 'none'}\n"
        f"hold_positions={','.join(report.get('hold_positions') or []) or 'none'}\n"
        f"new_buy_symbols={','.join(report.get('new_buy_symbols') or []) or 'none'}\n"
        f"positions={'; '.join(pos_lines) or 'none'}\n"
        f"selected={'; '.join(sel_lines) or 'none'}\n"
        f"summary={summary_bits}\n"
        "Дай advisory verdict для paper monthly sleeve: что делать сейчас и почему."
    )
    raw = _deepseek_chat(system, user)
    if not raw:
        return {}
    parsed = _extract_json(raw)
    note = str(parsed.get("note") or raw).strip()
    if len(note) > max_chars:
        note = note[: max_chars - 1].rstrip() + "…"
    advisory = {
        "source": "deepseek",
        "verdict": str(parsed.get("verdict") or "refresh_watch").strip() or "refresh_watch",
        "next_action": str(parsed.get("next_action") or "manual_review").strip() or "manual_review",
        "note": note,
        "raw": raw[:1000],
    }
    return advisory


class AlpacaClient:
    def __init__(self, base_url: str, key_id: str, secret_key: str):
        self.base_url = base_url.rstrip("/")
        self.key_id = key_id
        self.secret_key = secret_key
        self._ssl_ctx = ssl.create_default_context()

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=body, headers=self._headers(), method=method)
        try:
            with request.urlopen(req, context=self._ssl_ctx, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc

    def get_account(self) -> dict[str, Any]:
        return self._request("GET", "/v2/account")

    def get_clock(self) -> dict[str, Any]:
        """Return Alpaca market clock: {is_open, next_open, next_close, timestamp}."""
        return self._request("GET", "/v2/clock")

    def list_positions(self) -> list[dict[str, Any]]:
        return list(self._request("GET", "/v2/positions"))

    def list_orders(self, *, status: str = "open", limit: int = 100) -> list[dict[str, Any]]:
        return list(self._request("GET", f"/v2/orders?status={status}&direction=desc&limit={int(limit)}"))

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/orders/{order_id}")

    def submit_market_buy(self, symbol: str, notional: float) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "notional": f"{notional:.2f}",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        }
        return self._request("POST", "/v2/orders", payload)

    def submit_market_buy_qty(self, symbol: str, qty: float) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "qty": _format_qty(qty),
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        }
        return self._request("POST", "/v2/orders", payload)

    def submit_bracket_buy(
        self,
        symbol: str,
        *,
        notional: float | None,
        qty: float | None,
        stop_loss_price: float,
        take_profit_price: float,
        time_in_force: str = "day",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": symbol,
            "side": "buy",
            "type": "market",
            "time_in_force": time_in_force,
            "order_class": "bracket",
            "take_profit": {"limit_price": _format_price(take_profit_price)},
            "stop_loss": {"stop_price": _format_price(stop_loss_price)},
        }
        if qty is not None and qty > 0:
            payload["qty"] = _format_qty(qty)
        elif notional is not None and notional > 0:
            payload["notional"] = f"{notional:.2f}"
        else:
            raise RuntimeError("bracket buy requires qty or notional")
        return self._request("POST", "/v2/orders", payload)

    def submit_stop_sell(self, symbol: str, *, qty: float, stop_price: float, time_in_force: str = "day") -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "qty": _format_qty(qty),
            "side": "sell",
            "type": "stop",
            "time_in_force": time_in_force,
            "stop_price": _format_price(stop_price),
        }
        return self._request("POST", "/v2/orders", payload)

    def submit_trailing_stop_sell(
        self,
        symbol: str,
        *,
        qty: float,
        trail_percent: float,
        time_in_force: str = "day",
    ) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "qty": _format_qty(qty),
            "side": "sell",
            "type": "trailing_stop",
            "time_in_force": time_in_force,
            "trail_percent": f"{trail_percent:.4f}".rstrip("0").rstrip("."),
        }
        return self._request("POST", "/v2/orders", payload)

    def close_position(self, symbol: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v2/positions/{symbol}")

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v2/orders/{order_id}")


def _load_picks(csv_path: Path, month: str | None) -> list[Pick]:
    out: list[Pick] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        rows = list(rd)
    if not rows:
        return out
    if not month:
        month = max((r.get("month") or "").strip() for r in rows)
    for row in rows:
        if (row.get("month") or "").strip() != month:
            continue
        universe_score = (row.get("universe_score") or "").strip()
        out.append(
            Pick(
                month=month,
                ticker=(row.get("ticker") or "").strip().upper(),
                entry_day=(row.get("entry_day") or "").strip(),
                score=float(row.get("score") or 0.0),
                atr20_pct=float(row.get("atr20_pct") or 0.0),
                momentum20_pct=float(row.get("momentum20_pct") or 0.0),
                momentum60_pct=float(row.get("momentum60_pct") or 0.0),
                pullback60_pct=float(row.get("pullback60_pct") or 0.0),
                universe_score=float(universe_score) if universe_score else None,
                entry_price=_optional_float(row.get("entry_price")),
                stop_price=_optional_float(row.get("stop_price")),
                target_price=_optional_float(row.get("target_price")),
                weight=_optional_float(row.get("weight")),
            )
        )
    out.sort(key=lambda x: x.score, reverse=True)
    return out


def _default_picks_csv() -> Path | None:
    root = Path(__file__).resolve().parent.parent
    runs = sorted(root.glob("backtest_runs/equities_monthly_research_*/picks.csv"))
    return runs[-1] if runs else None


def _monthly_runtime_dirs() -> list[Path]:
    root = Path(__file__).resolve().parent.parent
    candidates: list[Path] = []
    for raw in (
        _env("ALPACA_AUTOPILOT_RUNTIME_DIR", ""),
        _env("EQ_V35_RUNTIME_DIR", ""),
        _env("EQ_BASELINE_RUNTIME_DIR", ""),
    ):
        if not raw:
            continue
        path = Path(raw)
        if path.exists():
            candidates.append(path)
    runtime_root = root / "runtime"
    if runtime_root.exists():
        for path in sorted(runtime_root.glob("equities_monthly*")):
            if path.is_dir():
                candidates.append(path)
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _current_cycle_picks_path(picks_csv: Path) -> Path | None:
    raw = _env("ALPACA_CURRENT_CYCLE_PICKS_CSV", "")
    if raw:
        path = Path(raw)
        if path.exists():
            return path
    for runtime_dir in _monthly_runtime_dirs():
        path = runtime_dir / "current_cycle_picks.csv"
        if path.exists():
            return path
    candidate = picks_csv.parent / "current_cycle_picks.csv"
    return candidate if candidate.exists() else None


def _load_intraday_managed_symbols() -> set[str]:
    symbols: set[str] = set()
    raw = _env("ALPACA_INTRADAY_STATE_PATH", "")
    state_path = Path(raw) if raw else (Path(__file__).resolve().parent.parent / "configs" / "intraday_state.json")
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text())
        except Exception:
            data = {}
        if isinstance(data, dict):
            for sym in data.keys():
                token = str(sym or "").strip().upper()
                if token:
                    symbols.add(token)

    # Intraday removes owned state after submitting a close order, while the
    # remote paper position can remain open until Alpaca fills it. Treat those
    # in-flight closes as intraday-owned so monthly cleanup cannot close them.
    advisory_raw = _env("ALPACA_INTRADAY_ADVISORY_PATH", "")
    advisory_path = (
        Path(advisory_raw)
        if advisory_raw
        else Path(__file__).resolve().parent.parent
        / "runtime"
        / "equities_intraday_dynamic_v1"
        / "latest_advisory.json"
    )
    if advisory_path.exists():
        try:
            advisory = json.loads(advisory_path.read_text())
        except Exception:
            advisory = {}
        if isinstance(advisory, dict):
            for sym in advisory.get("pending_close_positions") or []:
                token = str(sym or "").strip().upper()
                if token:
                    symbols.add(token)
    return symbols


def _is_held_for_orders_conflict(exc: Exception) -> bool:
    text = str(exc).lower()
    return "held_for_orders" in text or "insufficient qty available for order" in text


def _parse_date_ymd(text: str) -> date | None:
    s = str(text or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _hwm_state_path(picks_csv: Path) -> Path:
    raw = _env("MONTHLY_HWM_STATE_PATH", "")
    if raw:
        return Path(raw)
    root = picks_csv.resolve().parent
    for _ in range(5):
        if (root / "runtime").is_dir():
            return root / "runtime" / "alpaca_monthly_hwm.json"
        root = root.parent
    return picks_csv.parent / "alpaca_monthly_hwm.json"


def _reentry_block_state_path(picks_csv: Path) -> Path:
    raw = _env("MONTHLY_REENTRY_BLOCK_STATE_PATH", "")
    if raw:
        return Path(raw)
    root = Path(__file__).resolve().parent.parent
    return root / "runtime" / "alpaca_monthly_reentry_block.json"


def _load_hwm_state(path: Path) -> dict[str, dict[str, Any]]:
    """Load {symbol: {hwm, entry_price, entry_date}} from disk."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_reentry_block_state(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict) and isinstance(data.get("symbols"), dict):
        return {str(k).upper(): v for k, v in data["symbols"].items() if isinstance(v, dict)}
    return {}


def _save_reentry_block_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"symbols": dict(sorted(state.items()))}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _active_reentry_blocks(
    state: dict[str, dict[str, Any]],
    now: datetime,
) -> dict[str, dict[str, Any]]:
    active: dict[str, dict[str, Any]] = {}
    for sym, rec in state.items():
        blocked_until = _parse_iso_utc(str(rec.get("blocked_until") or ""))
        if blocked_until is None or blocked_until <= now:
            continue
        active[sym.upper()] = rec
    return active


def _add_reentry_block(
    state: dict[str, dict[str, Any]],
    symbol: str,
    *,
    now: datetime,
    days: int,
    reason: str,
) -> None:
    if days <= 0:
        return
    sym = symbol.strip().upper()
    if not sym:
        return
    state[sym] = {
        "reason": reason,
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "blocked_until": (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _save_hwm_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _update_hwm(
    state: dict[str, dict[str, Any]],
    positions: dict[str, dict[str, Any]],
    now_str: str,
) -> dict[str, dict[str, Any]]:
    """Update high-water mark for every live position."""
    for sym, pos in positions.items():
        cur = _safe_float(pos.get("current_price"), 0.0)
        entry = _safe_float(pos.get("avg_entry_price"), 0.0)
        if cur <= 0:
            continue
        rec = state.get(sym, {})
        old_hwm = _safe_float(rec.get("hwm"), cur)
        state[sym] = {
            "hwm": max(old_hwm, cur),
            "entry_price": entry if entry > 0 else _safe_float(rec.get("entry_price"), cur),
            "entry_date": rec.get("entry_date") or now_str,
            "updated": now_str,
        }
    # Drop symbols no longer in positions
    for sym in list(state.keys()):
        if sym not in positions:
            del state[sym]
    return state


def _trail_stop_triggered(
    state: dict[str, dict[str, Any]],
    sym: str,
    pos: dict[str, Any],
    trail_pct: float,
    min_gain_pct: float,
) -> tuple[bool, float, float, float]:
    """Return (triggered, current_gain_pct, drop_from_hwm_pct, peak_gain_pct).

    The trail is armed by the recorded high-water mark, not the current mark.
    Otherwise a position can cross the trailing threshold between polling runs
    and become ineligible for the close once its remaining gain falls below
    ``min_gain_pct``.
    """
    rec = state.get(sym)
    if not rec:
        return False, 0.0, 0.0, 0.0
    cur = _safe_float(pos.get("current_price"), 0.0)
    entry = _safe_float(rec.get("entry_price"), 0.0)
    hwm = _safe_float(rec.get("hwm"), cur)
    if cur <= 0 or entry <= 0 or hwm <= 0:
        return False, 0.0, 0.0, 0.0
    gain_pct = (cur - entry) / entry * 100.0
    peak_gain_pct = (hwm - entry) / entry * 100.0
    drop_pct = (hwm - cur) / hwm * 100.0
    triggered = peak_gain_pct >= min_gain_pct and drop_pct >= trail_pct * 100.0
    return triggered, round(gain_pct, 2), round(drop_pct, 2), round(peak_gain_pct, 2)


def _position_loss_pct(pos: dict[str, Any]) -> float:
    """Return how far below entry a position is (positive = loss).

    Returns 0.0 when the position is flat or profitable.
    Uses ``unrealized_plpc`` from the Alpaca API when available,
    otherwise falls back to avg_entry_price vs current_price.
    """
    raw = pos.get("unrealized_plpc")
    if raw is not None:
        try:
            plpc = float(raw)
            return -plpc if plpc < 0 else 0.0
        except Exception:
            pass
    avg_entry = _safe_float(pos.get("avg_entry_price"), 0.0)
    cur = _safe_float(pos.get("current_price"), 0.0)
    if avg_entry > 0 and cur > 0:
        loss = (avg_entry - cur) / avg_entry
        return loss if loss > 0 else 0.0
    return 0.0


def _position_gain_pct(pos: dict[str, Any], hwm_state: dict[str, dict[str, Any]], sym: str) -> float:
    rec = hwm_state.get(sym, {})
    cur = _safe_float(pos.get("current_price"), 0.0)
    entry = _safe_float(rec.get("entry_price"), 0.0) or _safe_float(pos.get("avg_entry_price"), 0.0)
    if cur <= 0 or entry <= 0:
        return 0.0
    return max(0.0, (cur - entry) / entry * 100.0)


def _build_bracket_buy_spec(
    pick: Pick,
    *,
    notional: float,
    stop_loss_pct: float,
    target_pct: float,
    size_mode: str,
) -> tuple[dict[str, Any] | None, str]:
    entry = pick.entry_price
    stop = pick.stop_price
    target = pick.target_price
    if (stop is None or stop <= 0) and entry is not None and entry > 0:
        stop = entry * (1.0 - stop_loss_pct)
    if (target is None or target <= 0) and entry is not None and entry > 0 and target_pct > 0:
        target = entry * (1.0 + target_pct)

    if stop is None or stop <= 0:
        return None, "missing_stop_price"
    if target is None or target <= 0:
        return None, "missing_target_price"
    if target <= stop:
        return None, "target_must_be_above_stop"

    spec: dict[str, Any] = {
        "stop_loss_price": stop,
        "take_profit_price": target,
        "notional": notional,
        "qty": None,
        "size_mode": size_mode,
    }
    if size_mode == "qty":
        if entry is None or entry <= 0:
            return None, "missing_entry_price_for_qty"
        qty = notional / entry
        if qty <= 0:
            return None, "non_positive_qty"
        spec["qty"] = qty
        spec["notional"] = None
    elif size_mode != "notional":
        return None, f"unsupported_size_mode:{size_mode}"
    return spec, ""


def _wait_for_filled_qty(client: AlpacaClient, order: dict[str, Any], *, timeout_sec: float) -> tuple[float, str]:
    order_id = str(order.get("id") or "").strip()
    status = str(order.get("status") or "").strip().lower()
    filled_qty = _safe_float(order.get("filled_qty"), 0.0)
    deadline = time.time() + max(0.0, timeout_sec)
    while order_id and filled_qty <= 0 and status not in {"canceled", "expired", "rejected"} and time.time() < deadline:
        time.sleep(1.0)
        try:
            order = client.get_order(order_id)
        except RuntimeError:
            break
        status = str(order.get("status") or "").strip().lower()
        filled_qty = _safe_float(order.get("filled_qty"), 0.0)
    return filled_qty, status


def _pick_age_days(picks: list[Pick]) -> tuple[str, int | None]:
    latest_entry = ""
    latest_dt: date | None = None
    for p in picks:
        d = _parse_date_ymd(p.entry_day)
        if d is None:
            continue
        if latest_dt is None or d > latest_dt:
            latest_dt = d
            latest_entry = p.entry_day
    if latest_dt is None:
        return "", None
    now_utc = datetime.now(timezone.utc).date()
    return latest_entry, max(0, (now_utc - latest_dt).days)


def _parse_iso_utc(text: str) -> datetime | None:
    s = str(text or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Dry-run-first Alpaca paper bridge for monthly equities picks")
    ap.add_argument("--picks-csv", default=_env("ALPACA_PICKS_CSV", ""))
    ap.add_argument("--month", default=_env("ALPACA_PICKS_MONTH", ""))
    args = ap.parse_args()

    picks_csv = Path(args.picks_csv) if args.picks_csv else _default_picks_csv()
    if picks_csv is None or not picks_csv.exists():
        print("error=no_picks_csv", file=sys.stderr)
        return 2

    picks = _load_picks(picks_csv, args.month or None)
    if not picks:
        print("error=no_picks_for_month", file=sys.stderr)
        return 3

    max_positions = max(1, _env_int("ALPACA_MAX_POSITIONS", 3))
    target_alloc_pct = max(0.01, min(1.0, _env_float("ALPACA_TARGET_ALLOC_PCT", 0.45)))
    min_dollar_order = max(1.0, _env_float("ALPACA_MIN_DOLLAR_ORDER", 50.0))
    send_orders = _env_bool("ALPACA_SEND_ORDERS", False)
    close_stale_positions = _env_bool("ALPACA_CLOSE_STALE_POSITIONS", False)
    offline_dry_run = _env_bool("ALPACA_OFFLINE_DRY_RUN", False) and not send_orders
    capital_override_usd = max(0.0, _env_float("ALPACA_CAPITAL_OVERRIDE_USD", 0.0))
    allow_stale_picks = _env_bool("ALPACA_ALLOW_STALE_PICKS", False)
    max_pick_age_days = max(1, _env_int("ALPACA_MAX_PICK_AGE_DAYS", 45))
    refresh_grace_hours = max(1, _env_int("ALPACA_REFRESH_GRACE_HOURS", 48))
    refresh_utc_raw = _env("ALPACA_REFRESH_UTC") or _env("EQ_LATEST_REFRESH_UTC")
    refresh_utc = _parse_iso_utc(refresh_utc_raw)
    refresh_age_hours: float | None = None
    refreshed_recently = False
    if refresh_utc is not None:
        refresh_age_hours = max(0.0, (datetime.now(timezone.utc) - refresh_utc).total_seconds() / 3600.0)
        refreshed_recently = refresh_age_hours <= float(refresh_grace_hours)

    tg_token   = _env("TG_TOKEN")
    tg_chat_id = _env("TG_CHAT_ID")
    earnings_days = max(1, _env_int("EARNINGS_DAYS_GUARD", 5))
    use_earnings_filter = _env_bool("ALPACA_EARNINGS_FILTER", _EARNINGS_FILTER_OK)

    # ── Enhancement: trailing stop (high-water mark) ─────────────────────────
    # Once a position gains >= MONTHLY_TRAIL_MIN_GAIN_PCT, start trailing.
    # If it then drops MONTHLY_TRAIL_PCT% from its peak → close to lock profit.
    enable_trail_stop = _env_bool("MONTHLY_TRAIL_ENABLE", True)
    trail_pct = max(0.01, _env_float("MONTHLY_TRAIL_PCT", 0.06))       # 6% drop from peak
    trail_min_gain_pct = max(0.0, _env_float("MONTHLY_TRAIL_MIN_GAIN_PCT", 8.0))  # only trail after +8%
    hwm_path = _hwm_state_path(picks_csv)

    # ── Enhancement: ATR-adjusted position sizing ─────────────────────────────
    # Low-volatility picks get more capital; high-volatility picks get less.
    # Combined weight = score / sqrt(atr20_pct) so it balances momentum vs risk.
    atr_adjusted_sizing = _env_bool("MONTHLY_ATR_SIZING", True)

    # ── Enhancement: individual stop-loss per position ────────────────────────
    # Close any position down more than MONTHLY_SL_PCT from entry.
    # Works for both held picks and stale positions.
    enable_stop_loss = _env_bool("MONTHLY_SL_ENABLE", True)
    stop_loss_pct = max(0.01, _env_float("MONTHLY_SL_PCT", 0.08))   # default 8%

    # Broker-side entry protection. When enabled, new monthly buys use an
    # Alpaca bracket order so a broker-hosted stop and target are queued as
    # soon as the entry fills. The existing HWM trail remains software-managed.
    broker_protection_enable = _env_bool("ALPACA_BROKER_PROTECTION_ENABLE", False)
    broker_protection_required = _env_bool("ALPACA_BROKER_PROTECTION_REQUIRED", broker_protection_enable)
    broker_protection_order_class = _env("ALPACA_BROKER_PROTECTION_ORDER_CLASS", "bracket").lower()
    broker_protection_size_mode = _env("ALPACA_BROKER_PROTECTION_SIZE_MODE", "qty").lower()
    broker_protection_tif = _env("ALPACA_BROKER_PROTECTION_TIF", "day").lower()
    broker_target_pct = max(0.0, _env_float("ALPACA_BROKER_TARGET_PCT", 0.08))
    broker_wait_fill_sec = max(1.0, _env_float("ALPACA_BROKER_PROTECTION_WAIT_FILL_SEC", 20.0))
    native_trailing_enable = _env_bool("ALPACA_NATIVE_TRAIL_ENABLE", False)
    native_trailing_required = _env_bool("ALPACA_NATIVE_TRAIL_REQUIRED", False)
    native_trailing_tif = _env("ALPACA_NATIVE_TRAIL_TIF", broker_protection_tif).lower()
    native_trailing_min_gain_pct = max(
        0.0,
        _env_float("ALPACA_NATIVE_TRAIL_MIN_GAIN_PCT", trail_min_gain_pct),
    )
    native_trailing_percent = max(
        0.1,
        _env_float("ALPACA_NATIVE_TRAIL_PERCENT", trail_pct * 100.0),
    )
    native_trailing_cancel_existing = _env_bool("ALPACA_NATIVE_TRAIL_CANCEL_EXISTING_STOPS", True)
    reentry_block_enable = _env_bool("MONTHLY_REENTRY_BLOCK_ENABLE", True)
    trail_reentry_block_days = max(0, _env_int("MONTHLY_TRAIL_REENTRY_BLOCK_DAYS", 14))
    reentry_block_path = _reentry_block_state_path(picks_csv)

    # ── Enhancement: score-weighted position sizing ───────────────────────────
    # Higher-momentum picks get a larger slice of the allocation.
    weighted_sizing = _env_bool("MONTHLY_WEIGHTED_SIZING", True)

    # ── Enhancement: mid-month rotation ──────────────────────────────────────
    # After day N of the month, replace held picks that have lost momentum
    # (lost > MONTHLY_MIDMONTH_DD_PCT) with next best candidates.
    midmonth_rotation = _env_bool("MONTHLY_MIDMONTH_ROTATION", True)
    midmonth_day_threshold = max(1, _env_int("MONTHLY_MIDMONTH_DAY", 14))
    midmonth_dd_pct = max(0.01, _env_float("MONTHLY_MIDMONTH_DD_PCT", 0.05))  # 5%

    key_id = _env("ALPACA_API_KEY_ID")
    secret_key = _env("ALPACA_API_SECRET_KEY")
    base_url = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    live_guard_errors = _live_order_guard_errors(
        base_url=base_url,
        send_orders=send_orders,
        capital_override_usd=capital_override_usd,
    )
    if live_guard_errors:
        print(
            json.dumps(
                {
                    "error": "alpaca_live_order_guard",
                    "issues": live_guard_errors,
                    "hint": "use a monthly-v38-only live credential profile with a bounded capital override",
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 6
    if (not key_id or not secret_key) and not offline_dry_run:
        print("error=missing_alpaca_keys", file=sys.stderr)
        return 4

    snapshot_path = ""
    if offline_dry_run:
        account, positions, snapshot_path = _load_offline_snapshot(picks_csv)
        open_orders: list[dict[str, Any]] = []
        client = None
    else:
        client = AlpacaClient(base_url, key_id, secret_key)
        account = client.get_account()
        positions = client.list_positions()
        open_orders = client.list_orders(status="open", limit=100)
        # 2026-06-02: pre-flight market clock check.
        # New BUY orders submitted while market is closed end with
        # status=accepted and never fill within broker_wait_fill_sec,
        # causing every pick to be canceled. Skip submission if closed,
        # let next run during market hours actually fill.
        try:
            _clock = client.get_clock()
        except Exception as _exc:
            _clock = {"is_open": True, "_clock_error": str(_exc)}
        _market_is_open = bool(_clock.get("is_open"))
        if not _market_is_open:
            _next_open = _clock.get("next_open")
            print(
                f"[paper_bridge] market closed (next_open={_next_open}); skipping new BUY submissions this run",
                flush=True,
            )
    buying_power = float(account.get("buying_power") or account.get("cash") or 0.0)
    cash = float(account.get("cash") or 0.0)
    effective_capital = min(buying_power, capital_override_usd) if capital_override_usd > 0 else buying_power
    current_positions = {str(p.get("symbol") or "").strip().upper(): p for p in positions if str(p.get("symbol") or "").strip()}
    pending_buy_orders: dict[str, list[dict[str, Any]]] = {}
    open_sell_orders: dict[str, list[dict[str, Any]]] = {}
    open_stop_sell_orders: dict[str, list[dict[str, Any]]] = {}
    open_trailing_sell_orders: dict[str, list[dict[str, Any]]] = {}
    for order in open_orders:
        symbol = str(order.get("symbol") or "").strip().upper()
        side = str(order.get("side") or "").strip().lower()
        status = str(order.get("status") or "").strip().lower()
        order_type = str(order.get("type") or "").strip().lower()
        if not symbol:
            continue
        if status in {"accepted", "new", "pending_new", "partially_filled", "accepted_for_bidding"}:
            if side == "buy":
                pending_buy_orders.setdefault(symbol, []).append(order)
            elif side == "sell":
                open_sell_orders.setdefault(symbol, []).append(order)
                if order_type in {"stop", "stop_limit", "trailing_stop"}:
                    open_stop_sell_orders.setdefault(symbol, []).append(order)
                if order_type == "trailing_stop":
                    open_trailing_sell_orders.setdefault(symbol, []).append(order)
    occupied_symbols = set(current_positions.keys()) | set(pending_buy_orders.keys())
    now_utc = datetime.now(timezone.utc)
    reentry_block_state: dict[str, dict[str, Any]] = {}
    active_reentry_blocks: dict[str, dict[str, Any]] = {}
    blocked_reentry_symbols: set[str] = set()
    if reentry_block_enable:
        reentry_block_state = _active_reentry_blocks(_load_reentry_block_state(reentry_block_path), now_utc)
        blocked_reentry_symbols = set(reentry_block_state) - occupied_symbols
        active_reentry_blocks = {
            sym: rec for sym, rec in reentry_block_state.items()
            if sym in blocked_reentry_symbols
        }
    latest_entry_day, pick_age_days = _pick_age_days(picks)
    current_cycle_csv = _current_cycle_picks_path(picks_csv)
    current_cycle_picks: list[Pick] = []
    current_entry_day = ""
    current_pick_age_days: int | None = None
    if current_cycle_csv is not None:
        current_cycle_picks = _load_picks(current_cycle_csv, None)
        current_entry_day, current_pick_age_days = _pick_age_days(current_cycle_picks)
        current_cycle_is_fresh = bool(
            current_cycle_picks
            and current_pick_age_days is not None
            and current_pick_age_days <= max_pick_age_days
        )
        if current_cycle_is_fresh:
            picks_csv = current_cycle_csv
            picks = current_cycle_picks
            latest_entry_day = current_entry_day
            pick_age_days = current_pick_age_days

    stale_guard_triggered = (
        pick_age_days is not None
        and pick_age_days > max_pick_age_days
        and not allow_stale_picks
    )
    if stale_guard_triggered and refreshed_recently:
        if current_cycle_picks and current_pick_age_days is not None and current_pick_age_days <= max_pick_age_days:
            picks_csv = current_cycle_csv if current_cycle_csv is not None else picks_csv
            picks = current_cycle_picks
            latest_entry_day = current_entry_day
            pick_age_days = current_pick_age_days
            stale_guard_triggered = False
    if stale_guard_triggered and not refreshed_recently:
        print(
            json.dumps(
                {
                    "error": "stale_picks_guard",
                    "picks_csv": str(picks_csv),
                    "month": picks[0].month,
                    "latest_entry_day": latest_entry_day,
                    "pick_age_days": pick_age_days,
                    "max_pick_age_days": max_pick_age_days,
                    "refresh_utc": refresh_utc_raw,
                    "refresh_age_hours": None if refresh_age_hours is None else round(refresh_age_hours, 2),
                    "hint": "refresh equities research or set ALPACA_ALLOW_STALE_PICKS=1 explicitly",
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 5
    # ── Earnings filter ──────────────────────────────────────────────────────
    earnings_blocked: dict[str, str] = {}
    if use_earnings_filter:
        candidate_tickers = [p.ticker for p in picks[:max_positions * 2]]
        ek = _filter_earnings(candidate_tickers, days_guard=earnings_days)
        for sym, (safe, reason) in ek.items():
            if not safe:
                earnings_blocked[sym] = reason
    # If a fresh refresh still leaves only stale picks, interpret it as
    # "no current cycle candidates" instead of buying old names.
    no_current_cycle = bool(stale_guard_triggered and refreshed_recently)

    # Select only picks not blocked by earnings, up to max_positions
    selected = [] if no_current_cycle else [
        p for p in picks
        if p.ticker not in earnings_blocked and p.ticker not in blocked_reentry_symbols
    ][:max_positions]
    selected_symbols = {p.ticker for p in selected}
    intraday_managed_symbols = _load_intraday_managed_symbols()
    protected_intraday_symbols = sorted(sym for sym in current_positions.keys() if sym in intraday_managed_symbols)
    protected_intraday_orders = sorted(sym for sym in pending_buy_orders.keys() if sym in intraday_managed_symbols)
    stale_symbols = sorted(
        sym for sym in current_positions.keys()
        if sym not in selected_symbols and sym not in intraday_managed_symbols
    )
    stale_order_symbols = sorted(
        sym for sym in pending_buy_orders.keys()
        if sym not in selected_symbols and sym not in intraday_managed_symbols
    )
    hold_symbols = sorted(sym for sym in occupied_symbols if sym in selected_symbols)
    new_buy_symbols = [p.ticker for p in selected if p.ticker not in occupied_symbols]

    # ── Stop-loss detection ───────────────────────────────────────────────────
    # Any position (held or stale) that is down >= stop_loss_pct → force close.
    sl_triggered_symbols: list[str] = []
    sl_details: dict[str, float] = {}
    if enable_stop_loss and not offline_dry_run:
        for sym, pos in current_positions.items():
            if sym in intraday_managed_symbols:
                continue  # Never touch intraday-managed positions
            loss = _position_loss_pct(pos)
            if loss >= stop_loss_pct:
                sl_triggered_symbols.append(sym)
                sl_details[sym] = round(loss * 100, 2)

    # ── Trailing stop detection ───────────────────────────────────────────────
    # Load/update HWM state BEFORE checking trailing stops
    hwm_state: dict[str, dict[str, Any]] = {}
    trail_triggered_symbols: list[str] = []
    trail_details: dict[str, dict[str, float]] = {}
    native_trailing_candidates: list[str] = []
    native_trailing_details: dict[str, dict[str, float]] = {}
    native_trailing_fractional_skips: list[str] = []
    now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if (enable_trail_stop or native_trailing_enable) and not offline_dry_run:
        hwm_state = _load_hwm_state(hwm_path)
        hwm_state = _update_hwm(hwm_state, current_positions, now_utc_str)
        for sym in list(current_positions.keys()):
            if sym in intraday_managed_symbols:
                continue
            if sym in sl_triggered_symbols:
                continue  # SL already handles this one
            if native_trailing_enable and open_trailing_sell_orders.get(sym):
                continue  # Broker-hosted trailing stop already owns this exit.
            pos = current_positions[sym]
            if native_trailing_enable:
                qty = abs(_safe_float(pos.get("qty"), 0.0))
                if qty > 0 and _is_fractional_qty(qty):
                    native_trailing_fractional_skips.append(sym)
                else:
                    gain = _position_gain_pct(pos, hwm_state, sym)
                    if gain >= native_trailing_min_gain_pct:
                        native_trailing_candidates.append(sym)
                        native_trailing_details[sym] = {
                            "gain_pct": round(gain, 2),
                            "trail_percent": round(native_trailing_percent, 4),
                        }
                        continue
            if enable_trail_stop:
                fired, gain, drop, peak_gain = _trail_stop_triggered(
                    hwm_state, sym, pos, trail_pct, trail_min_gain_pct
                )
                if fired:
                    trail_triggered_symbols.append(sym)
                    trail_details[sym] = {
                        "gain_pct": gain,
                        "peak_gain_pct": peak_gain,
                        "drop_from_hwm_pct": drop,
                    }
                    continue

    # Symbols freed by stop-loss may become new buy candidates
    # (we'll try to fill with next-best picks after closing)
    sl_freed_slots = len(sl_triggered_symbols)

    # ── Mid-month rotation detection ─────────────────────────────────────────
    today_day = datetime.now(timezone.utc).day
    rotation_symbols: list[str] = []
    rotation_details: dict[str, float] = {}
    if midmonth_rotation and today_day > midmonth_day_threshold and not offline_dry_run:
        for sym in list(hold_symbols):
            if sym in sl_triggered_symbols:
                continue  # Already being closed by SL
            if sym in intraday_managed_symbols:
                continue
            pos = current_positions.get(sym, {})
            loss = _position_loss_pct(pos)
            if loss >= midmonth_dd_pct:
                rotation_symbols.append(sym)
                rotation_details[sym] = round(loss * 100, 2)

    # Symbols being rotated out are treated as stale for buy purposes
    rotated_out = set(rotation_symbols)
    trail_out = set(trail_triggered_symbols)
    closed_out = set(sl_triggered_symbols) | rotated_out | trail_out

    # Extend new_buy_symbols: after SL + rotation + trail closes, fill with next picks
    extended_candidates = [
        p.ticker for p in picks
        if p.ticker not in earnings_blocked and p.ticker not in blocked_reentry_symbols
    ]
    already_handled = (
        (set(hold_symbols) - closed_out)
        | set(new_buy_symbols)
        | closed_out
    )
    replacement_picks = [t for t in extended_candidates if t not in already_handled]
    replacement_slots = len(closed_out) - len([s for s in closed_out if s not in current_positions])
    replacement_buys = replacement_picks[:replacement_slots] if replacement_slots > 0 else []

    # ── Score-weighted + ATR-adjusted position sizing ─────────────────────────
    # Combined weight = score × (1 / sqrt(atr20_pct)) so high-volatility picks
    # get less capital automatically.  Fallback: equal weight.
    all_buy_tickers = new_buy_symbols + replacement_buys
    all_buy_set = set(all_buy_tickers)
    all_active = [p for p in picks if p.ticker in (selected_symbols | all_buy_set)]

    def _raw_weight(p: Pick) -> float:
        base = max(0.001, p.score)
        if atr_adjusted_sizing and p.atr20_pct > 0:
            base = base / max(0.5, math.sqrt(p.atr20_pct))
        return base

    if (weighted_sizing or atr_adjusted_sizing) and all_active:
        raw = {p.ticker: _raw_weight(p) for p in all_active}
        total_raw = sum(raw.values()) or 1.0
        score_weights = {t: w / total_raw for t, w in raw.items()}
        # Clamp: no single position > 60% of allocation
        max_w = min(0.60, max(score_weights.values()) if score_weights else 0.60)
        score_weights = {t: min(w, max_w) for t, w in score_weights.items()}
        sw_total = sum(score_weights.values()) or 1.0
        score_weights = {t: w / sw_total for t, w in score_weights.items()}
        per_ticker_notional: dict[str, float] = {
            t: max(min_dollar_order, effective_capital * target_alloc_pct * w)
            for t, w in score_weights.items()
        }
        per_position_notional = max(
            min_dollar_order,
            effective_capital * target_alloc_pct / max(1, len(all_active)),
        )
    else:
        per_position_notional = (
            max(min_dollar_order, effective_capital * target_alloc_pct / max(1, len(selected)))
            if selected
            else 0.0
        )
        per_ticker_notional = {p.ticker: per_position_notional for p in all_active}
        score_weights = {}
    summary_path = _latest_summary_path(picks_csv)
    summary_row = _load_summary_row(summary_path)
    cycle_reason = (
        "no_current_cycle_after_refresh" if no_current_cycle
        else "selected_current_cycle" if selected
        else "filtered_to_zero_candidates"
    )

    report = {
        "status": (
            "offline_dry_run_no_current_cycle" if (no_current_cycle and offline_dry_run)
            else "offline_dry_run" if offline_dry_run
            else "dry_run_no_current_cycle" if (no_current_cycle and not send_orders)
            else "send_orders_no_current_cycle" if no_current_cycle
            else "dry_run" if not send_orders
            else "send_orders"
        ),
        "month": selected[0].month if selected else (picks[0].month if picks else ""),
        "earnings_blocked": earnings_blocked,
        "picks_csv": str(picks_csv),
        "buying_power": round(buying_power, 2),
        "cash": round(cash, 2),
        "effective_capital": round(effective_capital, 2),
        "per_position_notional": round(per_position_notional, 2),
        "close_stale_positions": bool(close_stale_positions),
        "latest_entry_day": latest_entry_day,
        "pick_age_days": pick_age_days,
        "max_pick_age_days": max_pick_age_days,
        "refresh_utc": refresh_utc_raw,
        "refresh_age_hours": None if refresh_age_hours is None else round(refresh_age_hours, 2),
        "offline_snapshot_path": snapshot_path,
        "no_current_cycle": no_current_cycle,
        "cycle_reason": cycle_reason,
        "summary_csv": str(summary_path) if summary_path else "",
        "summary_metrics": {
            "compounded_return_pct": round(_safe_float(summary_row.get("compounded_return_pct")), 4),
            "trades": _safe_int(summary_row.get("trades")),
            "profit_factor": round(_safe_float(summary_row.get("profit_factor")), 4),
            "winrate_pct": round(_safe_float(summary_row.get("winrate_pct")), 4),
            "months": _safe_int(summary_row.get("months")),
            "calendar_months": _safe_int(summary_row.get("calendar_months")),
            "inactive_months": _safe_int(summary_row.get("inactive_months")),
            "negative_months": _safe_int(summary_row.get("negative_months")),
            "max_monthly_dd_pct": round(_safe_float(summary_row.get("max_monthly_dd_pct")), 4),
        },
        "positions_before": [
            {
                "ticker": sym,
                "qty": str(pos.get("qty") or ""),
                "market_value": str(pos.get("market_value") or ""),
            }
            for sym, pos in sorted(current_positions.items())
        ],
        "intraday_managed_symbols": sorted(intraday_managed_symbols),
        "protected_intraday_positions": protected_intraday_symbols,
        "protected_intraday_pending_orders": protected_intraday_orders,
        "stale_positions": stale_symbols,
        "stale_pending_orders": stale_order_symbols,
        "hold_positions": hold_symbols,
        "stop_loss_pct": round(stop_loss_pct * 100, 2),
        "stop_loss_enabled": enable_stop_loss,
        "sl_triggered": sl_triggered_symbols,
        "sl_loss_pct": sl_details,
        "trail_stop_enabled": enable_trail_stop,
        "trail_pct": round(trail_pct * 100, 2),
        "trail_min_gain_pct": trail_min_gain_pct,
        "trail_triggered": trail_triggered_symbols,
        "trail_details": trail_details,
        "native_trailing_enabled": native_trailing_enable,
        "native_trailing_required": native_trailing_required,
        "native_trailing_tif": native_trailing_tif,
        "native_trailing_min_gain_pct": native_trailing_min_gain_pct,
        "native_trailing_percent": round(native_trailing_percent, 4),
        "native_trailing_candidates": native_trailing_candidates,
        "native_trailing_details": native_trailing_details,
        "native_trailing_fractional_skips": native_trailing_fractional_skips,
        "reentry_block_enabled": reentry_block_enable,
        "trail_reentry_block_days": trail_reentry_block_days,
        "reentry_blocked_symbols": sorted(active_reentry_blocks),
        "reentry_block_details": active_reentry_blocks,
        "broker_protection_enabled": broker_protection_enable,
        "broker_protection_required": broker_protection_required,
        "broker_protection_order_class": broker_protection_order_class,
        "broker_protection_size_mode": broker_protection_size_mode,
        "broker_protection_tif": broker_protection_tif,
        "broker_target_pct": round(broker_target_pct * 100, 2),
        "broker_wait_fill_sec": broker_wait_fill_sec,
        "midmonth_rotation_enabled": midmonth_rotation,
        "midmonth_day_threshold": midmonth_day_threshold,
        "midmonth_dd_pct": round(midmonth_dd_pct * 100, 2),
        "rotation_triggered": rotation_symbols,
        "rotation_loss_pct": rotation_details,
        "replacement_buys": replacement_buys,
        "weighted_sizing": weighted_sizing,
        "atr_adjusted_sizing": atr_adjusted_sizing,
        "score_weights": {t: round(w, 4) for t, w in score_weights.items()},
        "pending_buy_orders": [
            {
                "ticker": sym,
                "count": len(orders),
                "order_ids": [str(o.get("id") or "") for o in orders if str(o.get("id") or "").strip()],
                "notionals": [str(o.get("notional") or "") for o in orders],
            }
            for sym, orders in sorted(pending_buy_orders.items())
        ],
        "open_stop_sell_orders": [
            {
                "ticker": sym,
                "count": len(orders),
                "order_ids": [str(o.get("id") or "") for o in orders if str(o.get("id") or "").strip()],
                "stop_prices": [str(o.get("stop_price") or "") for o in orders],
            }
            for sym, orders in sorted(open_stop_sell_orders.items())
        ],
        "open_trailing_sell_orders": [
            {
                "ticker": sym,
                "count": len(orders),
                "order_ids": [str(o.get("id") or "") for o in orders if str(o.get("id") or "").strip()],
                "trail_percents": [str(o.get("trail_percent") or "") for o in orders],
            }
            for sym, orders in sorted(open_trailing_sell_orders.items())
        ],
        "new_buy_symbols": new_buy_symbols,
        "selected": [
            {
                "ticker": p.ticker,
                "score": round(p.score, 6),
                "atr20_pct": round(p.atr20_pct, 3),
                "momentum60_pct": round(p.momentum60_pct, 3),
                "pullback60_pct": round(p.pullback60_pct, 3),
                "universe_score": None if p.universe_score is None else round(p.universe_score, 6),
                "entry_price": None if p.entry_price is None else round(p.entry_price, 4),
                "stop_price": None if p.stop_price is None else round(p.stop_price, 4),
                "target_price": None if p.target_price is None else round(p.target_price, 4),
            }
            for p in selected
        ],
        "planned_broker_orders": [],
        "results": [],
    }
    picks_by_ticker = {p.ticker: p for p in picks}
    for ticker in all_buy_tickers:
        pick = picks_by_ticker.get(ticker)
        if pick is None:
            continue
        notional = per_ticker_notional.get(ticker, per_position_notional)
        spec, reason = _build_bracket_buy_spec(
            pick,
            notional=notional,
            stop_loss_pct=stop_loss_pct,
            target_pct=broker_target_pct,
            size_mode=broker_protection_size_mode,
        )
        report["planned_broker_orders"].append(
            {
                "ticker": ticker,
                "order_class": broker_protection_order_class if broker_protection_enable else "market",
                "status": "ok" if (not broker_protection_enable or spec is not None) else "invalid",
                "reason": reason,
                "notional": round(notional, 2),
                "qty": None if spec is None or spec.get("qty") is None else _format_qty(float(spec["qty"])),
                "stop_price": None if spec is None else round(float(spec["stop_loss_price"]), 4),
                "target_price": None if spec is None else round(float(spec["take_profit_price"]), 4),
            }
        )

    def _submit_buy_action(pick: Pick, *, action: str, notional: float) -> None:
        score_weight = round(score_weights.get(pick.ticker, 0.0), 4)
        # 2026-06-02: skip BUY submissions while market is closed.
        if not offline_dry_run and not _market_is_open:
            report["results"].append(
                {
                    "ticker": pick.ticker,
                    "action": action,
                    "status": "skipped_market_closed",
                    "error": "alpaca_clock_is_open_false",
                    "notional": round(notional, 2),
                    "score_weight": score_weight,
                }
            )
            return
        if broker_protection_enable:
            if broker_protection_order_class not in {"bracket", "simple_stop"}:
                reason = f"unsupported_broker_protection_order_class:{broker_protection_order_class}"
                if broker_protection_required:
                    report["results"].append(
                        {
                            "ticker": pick.ticker,
                            "action": action,
                            "status": "skipped_unprotected",
                            "error": reason,
                            "notional": round(notional, 2),
                            "score_weight": score_weight,
                        }
                    )
                    return

            spec, reason = _build_bracket_buy_spec(
                pick,
                notional=notional,
                stop_loss_pct=stop_loss_pct,
                target_pct=broker_target_pct,
                size_mode=broker_protection_size_mode,
            )
            if spec is None:
                if broker_protection_required:
                    report["results"].append(
                        {
                            "ticker": pick.ticker,
                            "action": action,
                            "status": "skipped_unprotected",
                            "error": reason,
                            "notional": round(notional, 2),
                            "score_weight": score_weight,
                        }
                    )
                    return
            elif broker_protection_order_class == "simple_stop":
                try:
                    qty = float(spec.get("qty") or 0.0)
                    if qty <= 0:
                        raise RuntimeError("simple_stop requires qty sizing")
                    entry_order = client.submit_market_buy_qty(pick.ticker, qty)  # type: ignore[union-attr]
                    filled_qty, entry_status = _wait_for_filled_qty(
                        client,  # type: ignore[arg-type]
                        entry_order,
                        timeout_sec=broker_wait_fill_sec,
                    )
                    if filled_qty <= 0:
                        order_id = str(entry_order.get("id") or "").strip()
                        if order_id:
                            try:
                                client.cancel_order(order_id)  # type: ignore[union-attr]
                            except RuntimeError:
                                pass
                        raise RuntimeError(f"entry_not_filled_before_stop status={entry_status}")
                    stop_order = client.submit_stop_sell(  # type: ignore[union-attr]
                        pick.ticker,
                        qty=filled_qty,
                        stop_price=float(spec["stop_loss_price"]),
                        time_in_force=broker_protection_tif,
                    )
                    report["results"].append(
                        {
                            "ticker": pick.ticker,
                            "action": "protected_market_buy" if action == "market_buy" else "replacement_protected_market_buy",
                            "entry_order_id": entry_order.get("id"),
                            "entry_status": entry_status,
                            "stop_order_id": stop_order.get("id"),
                            "stop_status": stop_order.get("status"),
                            "notional": round(notional, 2),
                            "qty": _format_qty(filled_qty),
                            "stop_price": round(float(spec["stop_loss_price"]), 4),
                            "target_price": round(float(spec["take_profit_price"]), 4),
                            "score_weight": score_weight,
                        }
                    )
                    return
                except RuntimeError as exc:
                    if broker_protection_required:
                        try:
                            client.close_position(pick.ticker)  # type: ignore[union-attr]
                        except RuntimeError:
                            pass
                        report["results"].append(
                            {
                                "ticker": pick.ticker,
                                "action": "protected_market_buy" if action == "market_buy" else "replacement_protected_market_buy",
                                "status": "error_closed_if_needed",
                                "error": str(exc),
                                "notional": round(notional, 2),
                                "score_weight": score_weight,
                            }
                        )
                        return
            else:
                try:
                    result = client.submit_bracket_buy(  # type: ignore[union-attr]
                        pick.ticker,
                        notional=spec.get("notional"),
                        qty=spec.get("qty"),
                        stop_loss_price=float(spec["stop_loss_price"]),
                        take_profit_price=float(spec["take_profit_price"]),
                        time_in_force=broker_protection_tif,
                    )
                    report["results"].append(
                        {
                            "ticker": pick.ticker,
                            "action": "bracket_buy" if action == "market_buy" else "replacement_bracket_buy",
                            "order_id": result.get("id"),
                            "status": result.get("status"),
                            "notional": round(notional, 2),
                            "qty": None if spec.get("qty") is None else _format_qty(float(spec["qty"])),
                            "stop_price": round(float(spec["stop_loss_price"]), 4),
                            "target_price": round(float(spec["take_profit_price"]), 4),
                            "score_weight": score_weight,
                        }
                    )
                    return
                except RuntimeError as exc:
                    if broker_protection_required:
                        report["results"].append(
                            {
                                "ticker": pick.ticker,
                                "action": "bracket_buy" if action == "market_buy" else "replacement_bracket_buy",
                                "status": "error",
                                "error": str(exc),
                                "notional": round(notional, 2),
                                "score_weight": score_weight,
                            }
                        )
                        return

        result = client.submit_market_buy(pick.ticker, notional)  # type: ignore[union-attr]
        report["results"].append(
            {
                "ticker": pick.ticker,
                "action": action,
                "order_id": result.get("id"),
                "status": result.get("status"),
                "notional": round(notional, 2),
                "score_weight": score_weight,
                "broker_protection": False,
            }
        )

    def _cancel_open_sell_orders(symbol: str, *, action: str) -> bool:
        """Cancel existing protective sell orders so Alpaca releases held qty."""
        cancel_failed = False
        for order in open_sell_orders.get(symbol, []):
            order_id = str(order.get("id") or "").strip()
            if not order_id:
                continue
            try:
                result = client.cancel_order(order_id)
                report["results"].append(
                    {
                        "ticker": symbol,
                        "action": action,
                        "order_id": order_id,
                        "status": result.get("status", "canceled"),
                    }
                )
            except RuntimeError as exc:
                cancel_failed = True
                report["results"].append(
                    {
                        "ticker": symbol,
                        "action": action,
                        "order_id": order_id,
                        "status": "error",
                        "error": str(exc),
                    }
                )
        return not cancel_failed

    if send_orders:
        # ── 1. Stop-loss closes (highest priority) ────────────────────────────
        if enable_stop_loss:
            for symbol in sl_triggered_symbols:
                if symbol not in current_positions:
                    continue
                if not _cancel_open_sell_orders(symbol, action="stop_loss_cancel_sell_order"):
                    continue
                try:
                    result = client.close_position(symbol)
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "stop_loss_close",
                            "loss_pct": sl_details.get(symbol, 0.0),
                            "order_id": result.get("id"),
                            "status": result.get("status"),
                        }
                    )
                except RuntimeError as exc:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "stop_loss_close",
                            "status": "error",
                            "error": str(exc),
                        }
                    )

        # ── 1b. Trailing stop closes (lock-in profits) ────────────────────────
        if enable_trail_stop:
            for symbol in trail_triggered_symbols:
                if symbol not in current_positions:
                    continue
                det = trail_details.get(symbol, {})
                if not _cancel_open_sell_orders(symbol, action="trail_stop_cancel_sell_order"):
                    continue
                try:
                    result = client.close_position(symbol)
                    if reentry_block_enable:
                        _add_reentry_block(
                            reentry_block_state,
                            symbol,
                            now=now_utc,
                            days=trail_reentry_block_days,
                            reason="trail_stop_close",
                        )
                    report["results"].append({
                        "ticker": symbol,
                        "action": "trail_stop_close",
                        "gain_pct": det.get("gain_pct", 0.0),
                        "drop_from_hwm_pct": det.get("drop_from_hwm_pct", 0.0),
                        "order_id": result.get("id"),
                        "status": result.get("status"),
                    })
                except RuntimeError as exc:
                    report["results"].append({
                        "ticker": symbol,
                        "action": "trail_stop_close",
                        "status": "error",
                        "error": str(exc),
                    })
                    pick = picks_by_ticker.get(symbol)
                    if not pick:
                        continue
                    notional = per_ticker_notional.get(symbol, per_position_notional)
                    spec, reason = _build_bracket_buy_spec(
                        pick,
                        notional=notional,
                        stop_loss_pct=stop_loss_pct,
                        target_pct=broker_target_pct,
                        size_mode="qty",
                    )
                    if spec is None:
                        report["results"].append({
                            "ticker": symbol,
                            "action": "trail_stop_fallback_stop",
                            "status": "skipped",
                            "error": reason,
                        })
                        continue
                    qty = abs(_safe_float(current_positions.get(symbol, {}).get("qty"), 0.0))
                    if qty <= 0:
                        continue
                    try:
                        fallback = client.submit_stop_sell(
                            symbol,
                            qty=qty,
                            stop_price=float(spec["stop_loss_price"]),
                            time_in_force=broker_protection_tif,
                        )
                        report["results"].append({
                            "ticker": symbol,
                            "action": "trail_stop_fallback_stop",
                            "order_id": fallback.get("id"),
                            "status": fallback.get("status"),
                            "qty": _format_qty(qty),
                            "stop_price": round(float(spec["stop_loss_price"]), 4),
                        })
                    except RuntimeError as fallback_exc:
                        report["results"].append({
                            "ticker": symbol,
                            "action": "trail_stop_fallback_stop",
                            "status": "error",
                            "error": str(fallback_exc),
                        })
            # Persist updated HWM state
            _save_hwm_state(hwm_path, hwm_state)
            if reentry_block_enable:
                _save_reentry_block_state(reentry_block_path, reentry_block_state)

        # ── 2. Mid-month rotation closes ──────────────────────────────────────
        if midmonth_rotation and rotation_symbols:
            for symbol in rotation_symbols:
                if symbol not in current_positions:
                    continue
                try:
                    result = client.close_position(symbol)
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "rotation_close",
                            "loss_pct": rotation_details.get(symbol, 0.0),
                            "order_id": result.get("id"),
                            "status": result.get("status"),
                        }
                    )
                except RuntimeError as exc:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "rotation_close",
                            "status": "error",
                            "error": str(exc),
                        }
                    )

        # ── 2b. Promote profitable monthly positions to broker-native trail ──
        if native_trailing_enable:
            for symbol in native_trailing_candidates:
                if symbol not in current_positions:
                    continue
                if symbol in closed_out:
                    continue
                if symbol in intraday_managed_symbols:
                    continue
                if open_trailing_sell_orders.get(symbol):
                    continue
                pos = current_positions.get(symbol, {})
                qty = abs(_safe_float(pos.get("qty"), 0.0))
                if qty <= 0:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "native_trailing_stop_sell",
                            "status": "skipped",
                            "error": "missing_qty",
                        }
                    )
                    continue

                cancel_failed = False
                if native_trailing_cancel_existing:
                    for order in open_sell_orders.get(symbol, []):
                        order_id = str(order.get("id") or "").strip()
                        if not order_id:
                            continue
                        try:
                            result = client.cancel_order(order_id)
                            report["results"].append(
                                {
                                    "ticker": symbol,
                                    "action": "native_trailing_cancel_sell_order",
                                    "order_id": order_id,
                                    "status": result.get("status", "canceled"),
                                }
                            )
                        except RuntimeError as exc:
                            cancel_failed = True
                            report["results"].append(
                                {
                                    "ticker": symbol,
                                    "action": "native_trailing_cancel_sell_order",
                                    "order_id": order_id,
                                    "status": "error",
                                    "error": str(exc),
                                }
                            )
                    if cancel_failed and native_trailing_required:
                        continue

                try:
                    result = client.submit_trailing_stop_sell(
                        symbol,
                        qty=qty,
                        trail_percent=native_trailing_percent,
                        time_in_force=native_trailing_tif,
                    )
                    det = native_trailing_details.get(symbol, {})
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "native_trailing_stop_sell",
                            "order_id": result.get("id"),
                            "status": result.get("status"),
                            "qty": _format_qty(qty),
                            "gain_pct": det.get("gain_pct", 0.0),
                            "trail_percent": native_trailing_percent,
                        }
                    )
                except RuntimeError as exc:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "native_trailing_stop_sell",
                            "status": "error",
                            "error": str(exc),
                            "qty": _format_qty(qty),
                            "trail_percent": native_trailing_percent,
                        }
                    )
                    pick = picks_by_ticker.get(symbol)
                    if not pick:
                        continue
                    notional = per_ticker_notional.get(symbol, per_position_notional)
                    spec, reason = _build_bracket_buy_spec(
                        pick,
                        notional=notional,
                        stop_loss_pct=stop_loss_pct,
                        target_pct=broker_target_pct,
                        size_mode="qty",
                    )
                    if spec is None:
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "native_trailing_fallback_stop",
                                "status": "skipped",
                                "error": reason,
                            }
                        )
                        continue
                    try:
                        fallback = client.submit_stop_sell(
                            symbol,
                            qty=qty,
                            stop_price=float(spec["stop_loss_price"]),
                            time_in_force=broker_protection_tif,
                        )
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "native_trailing_fallback_stop",
                                "order_id": fallback.get("id"),
                                "status": fallback.get("status"),
                                "qty": _format_qty(qty),
                                "stop_price": round(float(spec["stop_loss_price"]), 4),
                            }
                        )
                    except RuntimeError as fallback_exc:
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "native_trailing_fallback_stop",
                                "status": "error",
                                "error": str(fallback_exc),
                            }
                        )

        # ── 3. Close stale positions (classic month-end rotation) ─────────────
        if close_stale_positions:
            for symbol in stale_symbols:
                if symbol in sl_triggered_symbols or symbol in rotation_symbols:
                    continue  # Already handled above
                if not _cancel_open_sell_orders(symbol, action="close_position_cancel_sell_order"):
                    continue
                try:
                    result = client.close_position(symbol)
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "close_position",
                            "order_id": result.get("id"),
                            "status": result.get("status"),
                        }
                    )
                except RuntimeError as exc:
                    if _is_held_for_orders_conflict(exc):
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "close_position",
                                "status": "deferred_held_for_orders",
                                "error": str(exc),
                            }
                        )
                        continue
                    raise
            for symbol in stale_order_symbols:
                for order in pending_buy_orders.get(symbol, []):
                    order_id = str(order.get("id") or "").strip()
                    if not order_id:
                        continue
                    result = client.cancel_order(order_id)
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "cancel_pending_buy",
                            "order_id": order_id,
                            "status": result.get("status", "canceled"),
                        }
                    )

        # ── 3b. Re-arm broker stop for existing monthly fractional positions ─
        if broker_protection_enable and broker_protection_order_class == "simple_stop":
            for symbol in hold_symbols:
                if symbol in intraday_managed_symbols:
                    continue
                if symbol in closed_out:
                    continue
                if open_stop_sell_orders.get(symbol):
                    continue
                pos = current_positions.get(symbol)
                pick = picks_by_ticker.get(symbol)
                if not pos or not pick:
                    continue
                notional = per_ticker_notional.get(symbol, per_position_notional)
                spec, reason = _build_bracket_buy_spec(
                    pick,
                    notional=notional,
                    stop_loss_pct=stop_loss_pct,
                    target_pct=broker_target_pct,
                    size_mode="qty",
                )
                qty = abs(_safe_float(pos.get("qty"), 0.0))
                if spec is None or qty <= 0:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "rearm_stop_sell",
                            "status": "skipped",
                            "error": reason or "missing_qty",
                        }
                    )
                    continue
                stop_price = float(spec["stop_loss_price"])
                cur = _safe_float(pos.get("current_price"), 0.0)
                try:
                    if cur > 0 and cur <= stop_price:
                        result = client.close_position(symbol)
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "rearm_close_below_stop",
                                "order_id": result.get("id"),
                                "status": result.get("status"),
                                "current_price": round(cur, 4),
                                "stop_price": round(stop_price, 4),
                            }
                        )
                    else:
                        result = client.submit_stop_sell(symbol, qty=qty, stop_price=stop_price, time_in_force=broker_protection_tif)
                        report["results"].append(
                            {
                                "ticker": symbol,
                                "action": "rearm_stop_sell",
                                "order_id": result.get("id"),
                                "status": result.get("status"),
                                "qty": _format_qty(qty),
                                "stop_price": round(stop_price, 4),
                            }
                        )
                except RuntimeError as exc:
                    report["results"].append(
                        {
                            "ticker": symbol,
                            "action": "rearm_stop_sell",
                            "status": "error",
                            "error": str(exc),
                        }
                    )

        # ── 4. Buy new picks (main cycle) ─────────────────────────────────────
        for pick in selected:
            if pick.ticker in current_positions and pick.ticker not in sl_triggered_symbols and pick.ticker not in rotation_symbols:
                report["results"].append(
                    {
                        "ticker": pick.ticker,
                        "action": "hold_existing",
                        "status": "skipped_existing_position",
                        "score_weight": round(score_weights.get(pick.ticker, 0.0), 4),
                    }
                )
                continue
            if pick.ticker in pending_buy_orders and pick.ticker not in sl_triggered_symbols:
                report["results"].append(
                    {
                        "ticker": pick.ticker,
                        "action": "hold_pending_buy",
                        "status": "skipped_existing_open_order",
                    }
                )
                continue
            notional = per_ticker_notional.get(pick.ticker, per_position_notional)
            _submit_buy_action(pick, action="market_buy", notional=notional)

        # ── 5. Buy replacement picks (after SL/rotation freed slots) ──────────
        for ticker in replacement_buys:
            if ticker in current_positions or ticker in pending_buy_orders:
                continue
            if ticker in earnings_blocked:
                continue
            notional = per_ticker_notional.get(ticker, per_position_notional)
            try:
                pick = picks_by_ticker.get(ticker)
                if pick is None:
                    report["results"].append(
                        {
                            "ticker": ticker,
                            "action": "replacement_buy",
                            "status": "error",
                            "error": "missing_pick_details",
                            "notional": round(notional, 2),
                        }
                    )
                    continue
                _submit_buy_action(pick, action="replacement_buy", notional=notional)
            except RuntimeError as exc:
                report["results"].append(
                    {
                        "ticker": ticker,
                        "action": "replacement_buy",
                        "status": "error",
                        "error": str(exc),
                    }
                )

    advisory = _alpaca_ai_advisory(report=report, summary_row=summary_row, picks_csv=picks_csv)
    if advisory:
        report["advisory"] = advisory
        advisory_path = _alpaca_advisory_path(picks_csv)
        advisory_path.parent.mkdir(parents=True, exist_ok=True)
        advisory_payload = {
            "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "picks_csv": str(picks_csv),
            "summary_csv": str(summary_path) if summary_path else "",
            "report": report,
        }
        advisory_path.write_text(
            json.dumps(advisory_payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        report["advisory_path"] = str(advisory_path)

    print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))

    # ── Telegram notification ─────────────────────────────────────────────────
    if tg_token and tg_chat_id:
        mode = "📄 PAPER" if "paper" in base_url.lower() else "💰 LIVE"
        month_label = report.get("month", "?")
        lines = [f"📊 <b>Equities {mode} — {month_label}</b>"]
        if not send_orders:
            lines.append("⚠️ DRY RUN — no real orders placed")
        if no_current_cycle:
            lines.append("🟡 No current monthly picks after fresh refresh; staying flat")
        lines += [
            f"💼 Capital: ${round(effective_capital,2):,}",
            f"📋 Per position: ${round(per_position_notional,2):,}",
        ]
        if earnings_blocked:
            lines.append(f"🚫 Earnings blocked: {', '.join(sorted(earnings_blocked))}")
        lines.append(f"🧭 Cycle: {cycle_reason}")
        for r in report["results"]:
            ticker = r.get("ticker", "?")
            action = r.get("action", "?")
            if action == "market_buy":
                notional = r.get("notional", per_position_notional)
                sw = r.get("score_weight", 0.0)
                sw_str = f" w={sw:.2f}" if weighted_sizing and sw > 0 else ""
                lines.append(f"  🟢 BUY {ticker} ${round(notional,0):.0f}{sw_str} — {r.get('status','?')}")
            elif action == "bracket_buy":
                notional = r.get("notional", per_position_notional)
                sw = r.get("score_weight", 0.0)
                sw_str = f" w={sw:.2f}" if weighted_sizing and sw > 0 else ""
                lines.append(
                    f"  🟢 BRACKET {ticker} ${round(notional,0):.0f}{sw_str} "
                    f"SL {r.get('stop_price','?')} TP {r.get('target_price','?')} — {r.get('status','?')}"
                )
            elif action == "replacement_buy":
                notional = r.get("notional", per_position_notional)
                lines.append(f"  🔄 REPLACE-BUY {ticker} ${round(notional,0):.0f} — {r.get('status','?')}")
            elif action == "replacement_bracket_buy":
                notional = r.get("notional", per_position_notional)
                lines.append(
                    f"  🔄 REPLACE-BRACKET {ticker} ${round(notional,0):.0f} "
                    f"SL {r.get('stop_price','?')} TP {r.get('target_price','?')} — {r.get('status','?')}"
                )
            elif action == "protected_market_buy":
                notional = r.get("notional", per_position_notional)
                sw = r.get("score_weight", 0.0)
                sw_str = f" w={sw:.2f}" if weighted_sizing and sw > 0 else ""
                lines.append(
                    f"  🟢 BUY+STOP {ticker} ${round(notional,0):.0f}{sw_str} "
                    f"SL {r.get('stop_price','?')} — {r.get('stop_status', r.get('status','?'))}"
                )
            elif action == "replacement_protected_market_buy":
                notional = r.get("notional", per_position_notional)
                lines.append(
                    f"  🔄 REPLACE BUY+STOP {ticker} ${round(notional,0):.0f} "
                    f"SL {r.get('stop_price','?')} — {r.get('stop_status', r.get('status','?'))}"
                )
            elif action == "trail_stop_close":
                gain = r.get("gain_pct", 0.0)
                drop = r.get("drop_from_hwm_pct", 0.0)
                lines.append(f"  🔒 TRAIL-CLOSE {ticker} +{gain:.1f}% from entry, -{drop:.1f}% from peak")
            elif action == "stop_loss_close":
                loss = r.get("loss_pct", 0.0)
                lines.append(f"  🛑 STOP-LOSS {ticker} -{loss:.1f}% — {r.get('status','?')}")
            elif action == "rotation_close":
                loss = r.get("loss_pct", 0.0)
                lines.append(f"  🔁 ROTATE-OUT {ticker} -{loss:.1f}% (mid-month)")
            elif action == "close_position":
                lines.append(f"  🔴 CLOSE {ticker}")
            elif action == "cancel_pending_buy":
                lines.append(f"  🟠 CANCEL pending {ticker}")
            elif action == "rearm_stop_sell":
                lines.append(f"  🛡️ REARM STOP {ticker} SL {r.get('stop_price','?')} — {r.get('status','?')}")
            elif action == "rearm_close_below_stop":
                lines.append(f"  🛑 CLOSE {ticker}: current <= broker stop — {r.get('status','?')}")
            elif action == "native_trailing_cancel_sell_order":
                lines.append(f"  🟠 CANCEL fixed sell {ticker} before native trail — {r.get('status','?')}")
            elif action == "native_trailing_stop_sell":
                lines.append(
                    f"  🧷 NATIVE TRAIL {ticker} trail {r.get('trail_percent','?')}% "
                    f"after +{r.get('gain_pct', 0.0):.1f}% — {r.get('status','?')}"
                )
            elif action == "native_trailing_fallback_stop":
                lines.append(f"  🛡️ FALLBACK STOP {ticker} SL {r.get('stop_price','?')} — {r.get('status','?')}")
            elif action == "hold_existing":
                sw = r.get("score_weight", 0.0)
                sw_str = f" w={sw:.2f}" if weighted_sizing and sw > 0 else ""
                lines.append(f"  🟡 HOLD {ticker}{sw_str}")
            elif action == "hold_pending_buy":
                lines.append(f"  🟡 HOLD pending {ticker}")
        if not report["results"]:
            lines.append("  — No actions taken —")
        if advisory:
            lines += ["", "🧠 <b>AI advisory</b>", str(advisory.get("note") or "").strip()]
        _tg_send_equities_report(tg_token, tg_chat_id, "\n".join(lines), report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

===== END FILE: scripts/equities_alpaca_paper_bridge.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/alt_slope_break_v1.py =====
GROUP: MEDIUM PRIORITY / NOT REVIEWED
REVIEW_FOCUS: ASB1 slope-break; off live, needs review if revived.
====================================================================================================

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
  ASB1_MACRO_REQUIRE_BULLISH bool  long only when 4h MACD hist > 0 [1]
  ASB1_MACRO_REQUIRE_BEARISH bool  short only when 4h MACD hist < 0 [1]
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
    min_r2: float = 0.80          # raised 0.70→0.80 (2026-04-16): tighter trendline fit
                                  # required. Q3-2025 analysis: weak trendlines (R²=0.7-0.8)
                                  # in bull markets produce false breakdowns that reverse
                                  # immediately. Requiring R²≥0.80 filters out low-quality
                                  # ascending lines that aren't true trendlines.

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
    macro_require_bullish: bool = True   # enabled by default — longs only when 4h MACD hist > 0
                                         # Override with ASB1_MACRO_REQUIRE_BULLISH=0 to disable
    macro_macd_fast: int = 12
    macro_macd_slow: int = 26
    macro_macd_signal: int = 9
    macro_consec_bars: int = 1     # require N consecutive bars with hist same sign
                                   # 1 = standard (just last bar). Override with
                                   # ASB1_MACRO_CONSEC_BARS=2 for stricter filter.

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
        c.macro_consec_bars = _env_int("ASB1_MACRO_CONSEC_BARS", c.macro_consec_bars)

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

        consec = max(1, c.macro_consec_bars)
        need = max(80, c.macro_macd_slow + c.macro_macd_signal + consec + 10)
        rows = store.fetch_klines(store.symbol, c.macro_tf, need) or []
        if len(rows) < need // 2:
            return True  # not enough data — don't block
        closes = [float(r[4]) for r in rows]

        # Build last `consec` histogram values to check stability
        def _hist_series(closes_: list, n: int) -> list:
            """Return last n MACD histogram values."""
            hists = []
            for offset in range(n, 0, -1):
                sub = closes_[:-offset] if offset > 0 else closes_
                h = _macd_hist_last(sub, c.macro_macd_fast, c.macro_macd_slow, c.macro_macd_signal)
                hists.append(h)
            return hists

        if consec <= 1:
            hist = _macd_hist_last(closes, c.macro_macd_fast, c.macro_macd_slow, c.macro_macd_signal)
            if not math.isfinite(hist):
                return True
            if side == "short" and c.macro_require_bearish:
                return hist < 0
            if side == "long" and c.macro_require_bullish:
                return hist > 0
        else:
            hists = _hist_series(closes, consec)
            if not all(math.isfinite(h) for h in hists):
                return True
            if side == "short" and c.macro_require_bearish:
                return all(h < 0 for h in hists)   # ALL last N bars must be bearish
            if side == "long" and c.macro_require_bullish:
                return all(h > 0 for h in hists)   # ALL last N bars must be bullish
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

===== END FILE: strategies/alt_slope_break_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/alt_horizontal_break_v1.py =====
GROUP: MEDIUM PRIORITY / NOT REVIEWED
REVIEW_FOCUS: HZBO1 horizontal breakout; off live, needs review if revived.
====================================================================================================

"""
alt_horizontal_break_v1 (HZBO1) — Horizontal support/resistance zone breakout

Detects HORIZONTAL price zones formed by clusters of swing pivots at similar
price levels. Enters when price breaks through such a zone with an impulsive
candle. This is the horizontal complement to ASB1 (sloped trendline breakout):

  ATT1:  SLOPED trendline → BOUNCE (touch → rejection → entry)
  ASB1:  SLOPED trendline → BREAKOUT (close through line with impulse)
  HZBO1: HORIZONTAL zone  → BREAKOUT (close through level cluster with impulse)

Horizontal levels are among the most reliable in technical analysis because
traders cluster orders around the same price — the more touches, the stronger
the level, and the more explosive the break when it finally gives way.

Entry logic (SHORT — primary use in bear markets)
─────────────────────────────────────────────────
  Find horizontal SUPPORT zone: cluster of swing LOWS within zone_atr_width ATR
  → Zone has ≥ min_touches pivots (validated by multiple respect events)
  → Most recent touch is within max_zone_age bars (zone is still relevant)
  → Current bar CLOSES BELOW the zone bottom by ≥ break_atr × ATR
  → Candle is bearish with body_frac ≥ min_body_frac (impulse, not a doji)
  → RSI ≤ rsi_short_max (not in deeply oversold territory)
  → Optional: volume ≥ vol_mult × recent average (volume confirms the break)
  → SL = zone_top + sl_atr_mult × ATR (above the broken zone)

Entry logic (LONG — for bull market phases)
───────────────────────────────────────────
  Find horizontal RESISTANCE zone: cluster of swing HIGHS within zone_atr_width ATR
  → Zone has ≥ min_touches pivots
  → Most recent touch within max_zone_age bars
  → Current bar CLOSES ABOVE zone top by ≥ break_atr × ATR
  → Bullish impulse candle with significant body
  → RSI ≥ rsi_long_min
  → SL = zone_bottom − sl_atr_mult × ATR (below the broken zone)

Zone detection algorithm
────────────────────────
  1. Collect all swing highs (resistance) or swing lows (support)
  2. Group nearby pivots: any pivot within zone_atr_width ATR of another
     belongs to the same cluster
  3. A valid zone requires ≥ min_touches pivots in the cluster
  4. Zone boundaries: [min(cluster_prices), max(cluster_prices)]
  5. Zone is active if most recent pivot is ≤ max_zone_age bars ago

Break-versus-zone logic:
  SHORT: close ≤ zone_bottom − break_atr × ATR  (below the support floor)
  LONG:  close ≥ zone_top   + break_atr × ATR  (above the resistance ceiling)

Exit plan
─────────
  • TP1: tp1_rr × risk (partial: tp1_frac of position)
  • TP2: tp2_rr × risk (remainder)
  • Break-even: at be_trigger_rr × risk, lock in be_lock_rr × risk
  • Time stop: time_stop_bars_5m 5-minute bars
  • Cooldown: cooldown_bars_5m after any trade

Macro filter
────────────
  Same 4h MACD histogram direction filter as Elder and ASB1.
  HZBO1_MACRO_REQUIRE_BEARISH=1: only short when 4h hist < 0 (bear macro).
  HZBO1_MACRO_REQUIRE_BULLISH=1: only long when 4h hist > 0 (bull macro).

Environment variables (HZBO1_ prefix)
──────────────────────────────────────
  HZBO1_SYMBOL_ALLOWLIST      csv    symbols to trade
  HZBO1_SIGNAL_TF             str    kline timeframe [60]
  HZBO1_SIGNAL_LOOKBACK       int    bars to fetch [150]
  HZBO1_ATR_PERIOD            int    ATR period [14]
  HZBO1_RSI_PERIOD            int    RSI period [14]
  HZBO1_VOL_PERIOD            int    volume MA period for vol_mult [20]
  HZBO1_PIVOT_LEFT            int    bars left of swing pivot [3]
  HZBO1_PIVOT_RIGHT           int    bars right of swing pivot [3]
  HZBO1_MIN_TOUCHES           int    min zone touches to validate [2]
  HZBO1_MAX_ZONE_AGE          int    max bars since most recent touch [25]
  HZBO1_ZONE_ATR_WIDTH        float  ATR units to cluster pivots into a zone [0.50]
  HZBO1_BREAK_ATR             float  close must be this far BEYOND zone [0.25]
  HZBO1_MIN_BODY_FRAC         float  impulse candle body/range ratio [0.35]
  HZBO1_RSI_SHORT_MAX         float  max RSI for short entry [68.0]
  HZBO1_RSI_LONG_MIN          float  min RSI for long entry [32.0]
  HZBO1_VOL_MULT              float  min volume vs average (0 = disabled) [0.0]
  HZBO1_SL_ATR_MULT           float  SL buffer beyond zone edge [0.50]
  HZBO1_TP1_RR                float  TP1 R-multiple [1.50]
  HZBO1_TP2_RR                float  TP2 R-multiple [3.00]
  HZBO1_TP1_FRAC              float  fraction closed at TP1 [0.50]
  HZBO1_BE_TRIGGER_RR         float  break-even trigger R [1.00]
  HZBO1_BE_LOCK_RR            float  break-even lock offset R [0.02]
  HZBO1_TIME_STOP_BARS_5M     int    time stop in 5m bars [576]
  HZBO1_COOLDOWN_BARS_5M      int    cooldown in 5m bars [60]
  HZBO1_ALLOW_LONGS           bool   enable long entries [0]
  HZBO1_ALLOW_SHORTS          bool   enable short entries [1]
  HZBO1_MACRO_TF              str    macro filter timeframe [240]
  HZBO1_MACRO_REQUIRE_BEARISH bool   short only when 4h hist < 0 [1]
  HZBO1_MACRO_REQUIRE_BULLISH bool   long only when 4h hist > 0 [1]
  HZBO1_MACRO_MACD_FAST       int    [12]
  HZBO1_MACRO_MACD_SLOW       int    [26]
  HZBO1_MACRO_MACD_SIGNAL     int    [9]
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .signals import TradeSignal


# ---------------------------------------------------------------------------
# Env helpers (same pattern as ATT1/ASB1)
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


def _vol_sma(volumes: List[float], period: int) -> float:
    if len(volumes) < period:
        return float("nan")
    return sum(volumes[-period:]) / float(period)


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
    """Return (bar_index, price) for swing lows."""
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
    """Return (bar_index, price) for swing highs."""
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


# ---------------------------------------------------------------------------
# Horizontal zone detection
# ---------------------------------------------------------------------------

def _cluster_pivots(
    pivots: List[Tuple[int, float]],
    atr: float,
    zone_atr_width: float,
    min_touches: int,
    max_zone_age: int,
    n_bars: int,
) -> List[Tuple[float, float, int, int]]:
    """Group pivot points into horizontal zones.

    Returns list of (zone_low, zone_high, most_recent_age, touch_count) for
    zones that pass the min_touches and max_zone_age filters.

    Algorithm:
      1. Sort pivots by price
      2. Greedily merge pivots within zone_atr_width ATR of the cluster midpoint
      3. Each pivot can belong to at most one cluster (earliest wins on tie)
      4. Filter: cluster must have ≥ min_touches and most recent touch ≤ max_zone_age

    Returns zones sorted by most_recent_age ascending (freshest first).
    """
    if not pivots or atr <= 0 or zone_atr_width <= 0:
        return []

    zone_width = zone_atr_width * atr

    # Sort by price for greedy sweep
    sorted_pivots = sorted(pivots, key=lambda p: p[1])

    used = [False] * len(sorted_pivots)
    zones: List[Tuple[float, float, int, int]] = []

    for i in range(len(sorted_pivots)):
        if used[i]:
            continue
        # Start a new cluster at pivot i
        cluster_indices = [i]
        cluster_prices = [sorted_pivots[i][1]]
        cluster_bar_indices = [sorted_pivots[i][0]]

        for j in range(i + 1, len(sorted_pivots)):
            if used[j]:
                continue
            candidate_price = sorted_pivots[j][1]
            cluster_mid = (min(cluster_prices) + max(cluster_prices)) / 2.0
            # Merge if within zone_width of cluster midpoint AND within zone_width total span
            price_span = max(cluster_prices) - min(cluster_prices) + abs(candidate_price - cluster_mid)
            if abs(candidate_price - cluster_mid) <= zone_width and price_span <= zone_width * 2.0:
                cluster_indices.append(j)
                cluster_prices.append(candidate_price)
                cluster_bar_indices.append(sorted_pivots[j][0])

        if len(cluster_indices) >= min_touches:
            zone_low = min(cluster_prices)
            zone_high = max(cluster_prices)
            most_recent_bar = max(cluster_bar_indices)
            age = n_bars - 1 - most_recent_bar
            if age <= max_zone_age:
                zones.append((zone_low, zone_high, age, len(cluster_indices)))
            # Mark all cluster members as used regardless of age
            for idx in cluster_indices:
                used[idx] = True

    # Sort freshest zones first
    zones.sort(key=lambda z: z[2])
    return zones


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class AltHorizontalBreakV1Config:
    # Data
    signal_tf: str = "60"
    signal_lookback: int = 150
    atr_period: int = 14
    rsi_period: int = 14
    vol_period: int = 20

    # Pivot detection
    pivot_left: int = 3
    pivot_right: int = 3

    # Zone detection
    min_touches: int = 2        # minimum pivot cluster size to form a valid zone
    max_zone_age: int = 25      # most recent zone touch must be within this many bars
    zone_atr_width: float = 0.50  # ATR units: pivots within this range cluster into a zone
                                  # 0.50 ATR is ~50% of average bar range — catches price zones
                                  # not just exact levels, accounting for wicks and slippage

    # Breakout confirmation
    break_atr: float = 0.25     # close must be ≥ break_atr × ATR beyond the zone boundary
                                # tighter than ASB1 (0.30) because horizontal levels are
                                # cleaner — a 0.25 ATR break is already decisive
    min_body_frac: float = 0.35  # impulse body fraction — slightly relaxed vs ASB1

    # RSI gate — avoid chasing
    rsi_short_max: float = 68.0  # short: RSI cap (not deeply oversold already)
    rsi_long_min: float = 32.0   # long: RSI floor (not deeply overbought already)

    # Volume confirmation (optional)
    vol_mult: float = 0.0        # 0 = disabled; >0 requires breakout vol >= vol_mult × avg vol

    # Macro trend filter (4h MACD histogram)
    macro_tf: str = "240"
    macro_require_bearish: bool = True    # short only when 4h hist < 0
    macro_require_bullish: bool = True    # long only when 4h hist > 0 (ON by default)
                                          # Override with HZBO1_MACRO_REQUIRE_BULLISH=0 to disable
    macro_macd_fast: int = 12
    macro_macd_slow: int = 26
    macro_macd_signal: int = 9
    macro_consec_bars: int = 1     # require N consecutive 4h bars with hist same sign
                                   # 1=standard (default). Override with
                                   # HZBO1_MACRO_CONSEC_BARS=2 if needed.

    # EMA trend gate (4h price position filter)
    # Horizontal breakouts are unreliable in choppy/ranging markets.
    # Adding a 4h EMA gate ensures we only short when price is in a
    # confirmed downtrend on the higher timeframe.
    # macro_ema_gate=True: price must be BELOW macro_ema_period EMA on macro_tf
    # (for shorts); or ABOVE EMA (for longs). This filters choppy ranges.
    macro_ema_gate: bool = False   # disabled by default, enable in bearish regime
    macro_ema_period: int = 50     # 50-period EMA on 4h = ~200 4h bars of context

    # Signal TF EMA gate (local trend check on 1h)
    # For shorts: 1h price must be below signal_ema_period EMA (local downtrend)
    # Blocks entries when price is in a local bounce on the signal timeframe,
    # reducing false breakdowns during mean-reversions.
    signal_ema_gate: bool = False  # disabled by default
    signal_ema_period: int = 20    # 20-period EMA on 1h = local trend

    # Trade management
    sl_atr_mult: float = 0.50   # SL just beyond the broken zone (tight — zone = new S/R)
                                # tighter than ASB1 (0.80) because the zone itself provides
                                # clear invalidation — if price re-enters the zone, we're wrong
    tp1_rr: float = 1.50
    tp2_rr: float = 3.00
    tp1_frac: float = 0.50
    be_trigger_rr: float = 1.00
    be_lock_rr: float = 0.02
    time_stop_bars_5m: int = 576   # 48h
    cooldown_bars_5m: int = 60     # 5h cooldown between signals

    allow_longs: bool = False   # disabled until bull market
    allow_shorts: bool = True


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class AltHorizontalBreakV1Strategy:
    """Horizontal support/resistance zone breakout.

    SHORT: price breaks below a validated horizontal support zone with impulse.
    LONG:  price breaks above a validated horizontal resistance zone with impulse.
    The broken zone becomes new resistance/support for SL placement.

    Complements sloped trendline strategies (ATT1/ASB1) by catching breakouts
    at horizontal levels — the most common level type traders focus on.
    """

    def __init__(self, cfg: Optional[AltHorizontalBreakV1Config] = None):
        self.cfg = cfg or AltHorizontalBreakV1Config()
        self._load_env()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._allow: set = set()
        self._deny: set = set()
        self._refresh_lists()
        self.last_no_signal_reason = ""

    def _load_env(self) -> None:
        c = self.cfg
        c.signal_tf = os.getenv("HZBO1_SIGNAL_TF", c.signal_tf)
        c.signal_lookback = _env_int("HZBO1_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("HZBO1_ATR_PERIOD", c.atr_period)
        c.rsi_period = _env_int("HZBO1_RSI_PERIOD", c.rsi_period)
        c.vol_period = _env_int("HZBO1_VOL_PERIOD", c.vol_period)
        c.pivot_left = _env_int("HZBO1_PIVOT_LEFT", c.pivot_left)
        c.pivot_right = _env_int("HZBO1_PIVOT_RIGHT", c.pivot_right)
        c.min_touches = _env_int("HZBO1_MIN_TOUCHES", c.min_touches)
        c.max_zone_age = _env_int("HZBO1_MAX_ZONE_AGE", c.max_zone_age)
        c.zone_atr_width = _env_float("HZBO1_ZONE_ATR_WIDTH", c.zone_atr_width)
        c.break_atr = _env_float("HZBO1_BREAK_ATR", c.break_atr)
        c.min_body_frac = _env_float("HZBO1_MIN_BODY_FRAC", c.min_body_frac)
        c.rsi_short_max = _env_float("HZBO1_RSI_SHORT_MAX", c.rsi_short_max)
        c.rsi_long_min = _env_float("HZBO1_RSI_LONG_MIN", c.rsi_long_min)
        c.vol_mult = _env_float("HZBO1_VOL_MULT", c.vol_mult)
        c.sl_atr_mult = _env_float("HZBO1_SL_ATR_MULT", c.sl_atr_mult)
        c.tp1_rr = _env_float("HZBO1_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("HZBO1_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("HZBO1_TP1_FRAC", c.tp1_frac)
        c.be_trigger_rr = _env_float("HZBO1_BE_TRIGGER_RR", c.be_trigger_rr)
        c.be_lock_rr = _env_float("HZBO1_BE_LOCK_RR", c.be_lock_rr)
        c.time_stop_bars_5m = _env_int("HZBO1_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("HZBO1_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_longs = _env_bool("HZBO1_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("HZBO1_ALLOW_SHORTS", c.allow_shorts)
        c.macro_tf = os.getenv("HZBO1_MACRO_TF", c.macro_tf).strip()
        c.macro_require_bearish = _env_bool("HZBO1_MACRO_REQUIRE_BEARISH", c.macro_require_bearish)
        c.macro_require_bullish = _env_bool("HZBO1_MACRO_REQUIRE_BULLISH", c.macro_require_bullish)
        c.macro_macd_fast = _env_int("HZBO1_MACRO_MACD_FAST", c.macro_macd_fast)
        c.macro_macd_slow = _env_int("HZBO1_MACRO_MACD_SLOW", c.macro_macd_slow)
        c.macro_macd_signal = _env_int("HZBO1_MACRO_MACD_SIGNAL", c.macro_macd_signal)
        c.macro_consec_bars = _env_int("HZBO1_MACRO_CONSEC_BARS", c.macro_consec_bars)
        c.macro_ema_gate = _env_bool("HZBO1_MACRO_EMA_GATE", c.macro_ema_gate)
        c.macro_ema_period = _env_int("HZBO1_MACRO_EMA_PERIOD", c.macro_ema_period)
        c.signal_ema_gate = _env_bool("HZBO1_SIGNAL_EMA_GATE", c.signal_ema_gate)
        c.signal_ema_period = _env_int("HZBO1_SIGNAL_EMA_PERIOD", c.signal_ema_period)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set(
            "HZBO1_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT",
        )
        self._deny = _env_csv_set("HZBO1_SYMBOL_DENYLIST")

    def _macro_trend_ok(self, store, side: str) -> bool:
        """4h MACD histogram macro filter.

        Same logic as Elder v2 ETS2_TREND_REQUIRE_HIST_SIGN and ASB1:
        - SHORT: require 4h hist < 0 (confirmed downtrend)
        - LONG:  require 4h hist > 0 (confirmed uptrend)
        Returns True if condition satisfied or filter disabled.
        """
        c = self.cfg
        if not c.macro_tf:
            return True
        if side == "short" and not c.macro_require_bearish:
            return True
        if side == "long" and not c.macro_require_bullish:
            return True

        consec = max(1, c.macro_consec_bars)
        need = max(80, c.macro_macd_slow + c.macro_macd_signal + consec + 10)
        rows = store.fetch_klines(store.symbol, c.macro_tf, need) or []
        if len(rows) < need // 2:
            return True  # not enough data — don't block

        closes = [float(r[4]) for r in rows]

        # Check last `consec` histogram bars — all must agree with direction
        def _last_hists(n: int) -> list:
            hists = []
            for offset in range(n, 0, -1):
                sub = closes[:-offset] if offset > 0 else closes
                h = _macd_hist_last(sub, c.macro_macd_fast, c.macro_macd_slow, c.macro_macd_signal)
                hists.append(h)
            return hists

        hists = _last_hists(consec)
        if not all(math.isfinite(h) for h in hists):
            return True

        if side == "short" and c.macro_require_bearish:
            if not all(h < 0 for h in hists):
                return False
        if side == "long" and c.macro_require_bullish:
            if not all(h > 0 for h in hists):
                return False

        # Optional EMA gate: price must be on correct side of trend EMA
        if c.macro_ema_gate and c.macro_ema_period > 0:
            ema_need = c.macro_ema_period + 10
            ema_rows = rows if len(rows) >= ema_need else (
                store.fetch_klines(store.symbol, c.macro_tf, ema_need) or []
            )
            if len(ema_rows) >= c.macro_ema_period:
                ema_closes = [float(r[4]) for r in ema_rows]
                ema_vals = _ema_series(ema_closes, c.macro_ema_period)
                if ema_vals and math.isfinite(ema_vals[-1]):
                    cur_price = ema_closes[-1]
                    ema_now = ema_vals[-1]
                    if side == "short" and cur_price > ema_now:
                        return False   # price above 4h EMA → not in downtrend → block short
                    if side == "long" and cur_price < ema_now:
                        return False   # price below 4h EMA → not in uptrend → block long

        return True

    # ------------------------------------------------------------------
    # SHORT: horizontal support zone broken to the downside
    # ------------------------------------------------------------------

    def _check_short_breakdown(
        self,
        lows: List[float],
        highs: List[float],
        closes: List[float],
        opens: List[float],
        volumes: List[float],
        atr: float,
        rsi: float,
    ) -> Optional[Tuple[float, float, int]]:
        """Detect breakdown of a horizontal support zone.

        Returns (zone_low, zone_high, touch_count) if breakdown confirmed.

        Logic:
          1. Find swing LOWS and cluster them into horizontal support zones
          2. For each valid zone, check if current bar closes well below the zone
          3. Confirm bearish impulse candle + RSI gate + optional volume
        """
        c = self.cfg
        n = len(lows)

        support_pivots = _find_swing_lows(lows, c.pivot_left, c.pivot_right)
        if not support_pivots:
            return None

        zones = _cluster_pivots(
            support_pivots, atr, c.zone_atr_width, c.min_touches, c.max_zone_age, n
        )
        if not zones:
            return None

        cur_close = closes[-1]
        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        cur_vol = volumes[-1] if volumes else 0.0
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range

        is_bearish = cur_close < cur_open
        body_ok = body_frac >= c.min_body_frac
        rsi_ok = rsi <= c.rsi_short_max

        if not (is_bearish and body_ok and rsi_ok):
            return None

        # Volume check (optional): current bar volume must exceed average
        if c.vol_mult > 0 and len(volumes) >= c.vol_period:
            avg_vol = _vol_sma(volumes[:-1], c.vol_period)  # exclude current bar
            if math.isfinite(avg_vol) and avg_vol > 0:
                if cur_vol < c.vol_mult * avg_vol:
                    return None

        # Find the freshest valid zone that the current bar is breaking below
        for zone_low, zone_high, age, touches in zones:
            # Break: close is at least break_atr below the zone FLOOR
            broke_below = cur_close <= zone_low - c.break_atr * atr
            # Guard: current bar should not have been inside the zone too deeply
            # (avoids catching moves that originated from inside the zone)
            entered_from_above = cur_high >= zone_low  # bar touched or was near zone
            if broke_below and entered_from_above:
                return (zone_low, zone_high, touches)

        return None

    # ------------------------------------------------------------------
    # LONG: horizontal resistance zone broken to the upside
    # ------------------------------------------------------------------

    def _check_long_breakout(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        opens: List[float],
        volumes: List[float],
        atr: float,
        rsi: float,
    ) -> Optional[Tuple[float, float, int]]:
        """Detect breakout above a horizontal resistance zone.

        Returns (zone_low, zone_high, touch_count) if breakout confirmed.
        """
        c = self.cfg
        n = len(highs)

        resistance_pivots = _find_swing_highs(highs, c.pivot_left, c.pivot_right)
        if not resistance_pivots:
            return None

        zones = _cluster_pivots(
            resistance_pivots, atr, c.zone_atr_width, c.min_touches, c.max_zone_age, n
        )
        if not zones:
            return None

        cur_close = closes[-1]
        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        cur_vol = volumes[-1] if volumes else 0.0
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range

        is_bullish = cur_close > cur_open
        body_ok = body_frac >= c.min_body_frac
        rsi_ok = rsi >= c.rsi_long_min

        if not (is_bullish and body_ok and rsi_ok):
            return None

        if c.vol_mult > 0 and len(volumes) >= c.vol_period:
            avg_vol = _vol_sma(volumes[:-1], c.vol_period)
            if math.isfinite(avg_vol) and avg_vol > 0:
                if cur_vol < c.vol_mult * avg_vol:
                    return None

        for zone_low, zone_high, age, touches in zones:
            broke_above = cur_close >= zone_high + c.break_atr * atr
            entered_from_below = cur_low <= zone_high  # bar touched or was near zone
            if broke_above and entered_from_below:
                return (zone_low, zone_high, touches)

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
        volumes = [float(r[5]) for r in rows] if len(rows[0]) > 5 else []

        atr = _atr_from_rows(rows, self.cfg.atr_period)
        rsi = _rsi(closes, self.cfg.rsi_period)
        if not (math.isfinite(atr) and math.isfinite(rsi)) or atr <= 0:
            self.last_no_signal_reason = "invalid_atr_or_rsi"
            return None

        cur_price = closes[-1]
        if cur_price <= 0:
            return None

        # ── Signal TF EMA gate (local trend filter) ────────────────────
        # Compute once, reuse for both short and long checks.
        signal_ema_val: Optional[float] = None
        if self.cfg.signal_ema_gate and self.cfg.signal_ema_period > 0:
            if len(closes) >= self.cfg.signal_ema_period:
                ema_vals = _ema_series(closes, self.cfg.signal_ema_period)
                if ema_vals and math.isfinite(ema_vals[-1]):
                    signal_ema_val = ema_vals[-1]

        # ── SHORT: horizontal support zone breakdown ───────────────────
        # Signal EMA gate for short: price must be below signal-TF EMA
        short_ema_ok = True
        if self.cfg.signal_ema_gate and signal_ema_val is not None:
            short_ema_ok = cur_price < signal_ema_val

        if self.cfg.allow_shorts and short_ema_ok and self._macro_trend_ok(store, "short"):
            result = self._check_short_breakdown(lows, highs, closes, opens, volumes, atr, rsi)
            if result is not None:
                zone_low, zone_high, touches = result
                # SL above the zone TOP (entire zone is now resistance)
                sl = zone_high + self.cfg.sl_atr_mult * atr
                risk = sl - cur_price
                if risk > 0 and cur_price > 0:
                    tp1 = cur_price - self.cfg.tp1_rr * risk
                    tp2 = cur_price - self.cfg.tp2_rr * risk
                    if tp2 > 0 and tp1 > tp2:
                        frac = min(0.90, max(0.10, self.cfg.tp1_frac))
                        sig = TradeSignal(
                            strategy="alt_horizontal_break_v1",
                            symbol=store.symbol,
                            side="short",
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
                                f"hzbo1_short "
                                f"zone=[{zone_low:.4f},{zone_high:.4f}] "
                                f"touches={touches} "
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

        # ── LONG: horizontal resistance zone breakout ──────────────────
        # Signal EMA gate for long: price must be above signal-TF EMA
        long_ema_ok = True
        if self.cfg.signal_ema_gate and signal_ema_val is not None:
            long_ema_ok = cur_price > signal_ema_val

        if self.cfg.allow_longs and long_ema_ok and self._macro_trend_ok(store, "long"):
            result = self._check_long_breakout(highs, lows, closes, opens, volumes, atr, rsi)
            if result is not None:
                zone_low, zone_high, touches = result
                # SL below the zone BOTTOM (entire zone is now support)
                sl = zone_low - self.cfg.sl_atr_mult * atr
                risk = cur_price - sl
                if risk > 0:
                    tp1 = cur_price + self.cfg.tp1_rr * risk
                    tp2 = cur_price + self.cfg.tp2_rr * risk
                    if tp2 > tp1 > cur_price:
                        frac = min(0.90, max(0.10, self.cfg.tp1_frac))
                        sig = TradeSignal(
                            strategy="alt_horizontal_break_v1",
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
                                f"hzbo1_long "
                                f"zone=[{zone_low:.4f},{zone_high:.4f}] "
                                f"touches={touches} "
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

===== END FILE: strategies/alt_horizontal_break_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/alt_bear_regime_continuation_v1.py =====
GROUP: MEDIUM PRIORITY / NOT REVIEWED
REVIEW_FOCUS: BRC1 bear continuation candidate; needs review.
====================================================================================================

"""alt_bear_regime_continuation_v1 — short trend-follow для bear / dead market.

ПОЛЬЗОВАТЕЛЬСКАЯ ИДЕЯ:
  «Когда медвежка — открываем шорт в продолжение тренда, ловим маленькие
   корректировки в pullback к EMA. Когда рынок развернётся в бычку —
   автоматически отключаемся и ждём.»

Логика:

Регим-gate (КРИТИЧНО):
  Активна ТОЛЬКО если regime ∈ {bear_chop, bear_trend}.
  В bull-режимах signal() сразу возвращает None.

Trend confirmation:
  • EMA20 на 1H ниже EMA50 (downtrend на хайтайме)
  • close < EMA20 на 5m (текущая цена ниже краткосрочной EMA)
  • НЕ требуем strong slope — работаем и в chop с слегка нисходящим bias

Pullback entry (SHORT):
  • Был ралли вверх в течение N последних 5m баров (3-6)
  • Текущая свеча показывает rejection: upper_wick ≥ body_floor × 1.2
  • RSI(14) на 5m в зоне 50-70 (overbought отскок, готов идти вниз)
  • close в нижней половине свечи (closer to lows)
  • Объём НЕ должен быть сильно выше среднего (это pullback, не breakdown)

Exit:
  • SL = swing_high recent + sl_pad×ATR (короткий стоп)
  • TP = entry - rr × risk (default RR=1.6 — short hold, мелкие движения)
  • Time stop = TIME_STOP_BARS_5M (default 96 = 8h)
  • Breakeven после TP1 (0.7R)

Symbol allowlist:
  По умолчанию топ ALT'ы (где медвежка наиболее видима): SOLUSDT, ADAUSDT, DOTUSDT, LINKUSDT, AVAXUSDT, SUIUSDT
  Не торгуем BTC/ETH (для них есть btc_eth_midterm).

Env vars (BRC1_):
  BRC1_HTF                   ("60")  — таймфрейм для тренд-фильтра
  BRC1_EMA_FAST              (20)
  BRC1_EMA_SLOW              (50)
  BRC1_PULLBACK_BARS         (4)     — количество восходящих 5m баров для pullback
  BRC1_PULLBACK_MIN_PCT      (0.4)   — pullback должен быть ≥ N% от ATR
  BRC1_RSI_PERIOD            (14)
  BRC1_RSI_MIN               (50)
  BRC1_RSI_MAX               (70)
  BRC1_MIN_REJECT_WICK_RATIO (1.2)
  BRC1_MAX_VOL_MULT          (1.6)   — pullback не должен быть с большим объёмом
  BRC1_VOL_AVG_BARS          (20)
  BRC1_SL_PAD_ATR            (0.20)
  BRC1_RR                    (1.6)
  BRC1_TP1_RR                (0.7)
  BRC1_TP1_FRAC              (0.50)
  BRC1_TIME_STOP_BARS_5M     (96)
  BRC1_COOLDOWN_BARS_5M      (36)    — 3h cooldown per symbol
  BRC1_ATR_PERIOD            (14)
  BRC1_SYMBOL_ALLOWLIST      (SOLUSDT,ADAUSDT,DOTUSDT,LINKUSDT,AVAXUSDT,SUIUSDT)
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from .signals import TradeSignal
except ImportError:
    from strategies.signals import TradeSignal


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip(): return default
    try: return float(str(raw).strip())
    except: return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip(): return default
    try: return int(float(str(raw).strip()))
    except: return default


def _env_str(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or default_csv
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _candles_5m(store, symbol: str) -> list:
    if hasattr(store, "c5"):
        return getattr(store, "c5") or []
    if hasattr(store, "candles"):
        return store.candles(symbol)
    return getattr(store, "rows", [])


def _atr(candles: list, period: int) -> float:
    if len(candles) < period + 1: return float("nan")
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i].h); l = float(candles[i].l); pc = float(candles[i - 1].c)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    recent = trs[-period:]
    return sum(recent) / float(len(recent)) if recent else float("nan")


def _ema(values: list[float], period: int) -> float:
    """EMA seeded on SMA of first `period` bars (avoids cold-start bias)."""
    if len(values) < period or period <= 0: return float("nan")
    cur = sum(float(x) for x in values[:period]) / period
    k = 2.0 / (period + 1.0)
    for v in values[period:]:
        cur = float(v) * k + cur * (1.0 - k)
    return cur


def _rsi(closes: list[float], period: int) -> float:
    """Wilder-smoothed RSI. Seed = simple avg of first period gains/losses."""
    need = period * 2 + 1
    if len(closes) < need or period <= 0: return float("nan")
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [max(0.0, d) for d in deltas]
    losses = [max(0.0, -d) for d in deltas]
    avg_g  = sum(gains[:period]) / period
    avg_l  = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l < 1e-12: return 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


@dataclass
class BRC1Config:
    htf: str = field(default_factory=lambda: _env_str("BRC1_HTF", "60"))
    ema_fast: int = field(default_factory=lambda: _env_int("BRC1_EMA_FAST", 20))
    ema_slow: int = field(default_factory=lambda: _env_int("BRC1_EMA_SLOW", 50))
    pullback_bars: int = field(default_factory=lambda: _env_int("BRC1_PULLBACK_BARS", 4))
    pullback_min_pct: float = field(default_factory=lambda: _env_float("BRC1_PULLBACK_MIN_PCT", 0.4))
    rsi_period: int = field(default_factory=lambda: _env_int("BRC1_RSI_PERIOD", 14))
    rsi_min: float = field(default_factory=lambda: _env_float("BRC1_RSI_MIN", 50))
    rsi_max: float = field(default_factory=lambda: _env_float("BRC1_RSI_MAX", 70))
    min_reject_wick_ratio: float = field(default_factory=lambda: _env_float("BRC1_MIN_REJECT_WICK_RATIO", 1.2))
    max_vol_mult: float = field(default_factory=lambda: _env_float("BRC1_MAX_VOL_MULT", 1.6))
    vol_avg_bars: int = field(default_factory=lambda: _env_int("BRC1_VOL_AVG_BARS", 20))
    sl_pad_atr: float = field(default_factory=lambda: _env_float("BRC1_SL_PAD_ATR", 0.20))
    rr: float = field(default_factory=lambda: _env_float("BRC1_RR", 1.6))
    tp1_rr: float = field(default_factory=lambda: _env_float("BRC1_TP1_RR", 0.7))
    tp1_frac: float = field(default_factory=lambda: _env_float("BRC1_TP1_FRAC", 0.50))
    time_stop_bars: int = field(default_factory=lambda: _env_int("BRC1_TIME_STOP_BARS_5M", 96))
    cooldown_bars: int = field(default_factory=lambda: _env_int("BRC1_COOLDOWN_BARS_5M", 36))
    atr_period: int = field(default_factory=lambda: _env_int("BRC1_ATR_PERIOD", 14))
    symbol_allowlist: set[str] = field(
        default_factory=lambda: _env_csv_set("BRC1_SYMBOL_ALLOWLIST", "SOLUSDT,ADAUSDT,DOTUSDT,LINKUSDT,AVAXUSDT,SUIUSDT")
    )


class AltBearRegimeContinuationV1Strategy:
    NAME = "alt_bear_regime_continuation_v1"

    def __init__(self):
        self.cfg = BRC1Config()
        self._last_signal_i: dict[str, int] = {}
        self._htf_downtrend_cache: dict[tuple[str, str, int, int, int], bool] = {}
        self.last_no_signal_reason = ""

    def signal(self, store, symbol: str, i: int, regime: Optional[str] = None) -> Optional[TradeSignal]:
        cfg = self.cfg

        # ── HARD REGIME GATE — only bear regimes ─────────────────────────────
        if regime is None or regime.upper() not in {"BEAR_CHOP", "BEAR_TREND"}:
            self.last_no_signal_reason = f"regime_not_bear:{regime}"
            return None

        if cfg.symbol_allowlist and symbol.upper() not in cfg.symbol_allowlist:
            self.last_no_signal_reason = "symbol_blocked"
            return None

        candles = _candles_5m(store, symbol)
        need = max(
            cfg.atr_period + 5,
            cfg.rsi_period * 2 + 1,
            cfg.vol_avg_bars + 2,
            cfg.pullback_bars + 5,
        )
        if i < need:
            self.last_no_signal_reason = "not_enough_bars"
            return None

        # Per-symbol cooldown
        last_i = self._last_signal_i.get(symbol, -10**9)
        if i - last_i < cfg.cooldown_bars:
            self.last_no_signal_reason = f"cooldown:{symbol}"
            return None

        atr = _atr(candles[max(0, i - cfg.atr_period - 2): i + 1], cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = "bad_atr"
            return None

        # ── HTF trend filter — EMA20 < EMA50 на 1H (downtrend) ───────────────
        htf_rows = []
        htf_ok_cached = None
        try:
            htf_min = max(5, int(float(str(cfg.htf))))
            htf_bucket = max(0, i // max(1, htf_min // 5))
        except Exception:
            htf_bucket = i
        htf_cache_key = (symbol.upper(), str(cfg.htf), int(htf_bucket), int(cfg.ema_fast), int(cfg.ema_slow))
        if htf_cache_key in self._htf_downtrend_cache:
            htf_ok_cached = self._htf_downtrend_cache[htf_cache_key]
        else:
            htf_rows = store.fetch_klines(symbol, cfg.htf, max(cfg.ema_slow + 10, 80)) if hasattr(store, "fetch_klines") else []
            if htf_rows and len(htf_rows) >= cfg.ema_slow + 5:
                htf_closes = [float(r[4]) for r in htf_rows]  # bybit kline format
                ema_fast_htf = _ema(htf_closes, cfg.ema_fast)
                ema_slow_htf = _ema(htf_closes, cfg.ema_slow)
                if math.isfinite(ema_fast_htf) and math.isfinite(ema_slow_htf):
                    htf_ok_cached = bool(ema_fast_htf < ema_slow_htf)
                    self._htf_downtrend_cache[htf_cache_key] = htf_ok_cached
        if htf_ok_cached is not None:
            if not htf_ok_cached:
                self.last_no_signal_reason = "htf_not_downtrend"
                return None
        elif htf_rows and len(htf_rows) >= cfg.ema_slow + 5:
            # Defensive fallback for malformed HTF rows: fail closed instead of
            # silently treating an unusable high-timeframe filter as permissive.
            self.last_no_signal_reason = "bad_htf"
            return None
        # Если нет HTF данных — fallback на 5m EMA
        else:
            closes_5m = [float(x.c) for x in candles[max(0, i - cfg.ema_slow - 5): i + 1]]
            ema_fast_5m = _ema(closes_5m, cfg.ema_fast)
            ema_slow_5m = _ema(closes_5m, cfg.ema_slow)
            if not (math.isfinite(ema_fast_5m) and math.isfinite(ema_slow_5m) and ema_fast_5m < ema_slow_5m):
                self.last_no_signal_reason = "5m_not_downtrend"
                return None

        # ── 5m close < 5m EMA20 (current below local trend) ──────────────────
        closes_5m = [float(x.c) for x in candles[max(0, i - cfg.ema_fast - 5): i + 1]]
        ema_fast_5m_now = _ema(closes_5m, cfg.ema_fast)
        if not math.isfinite(ema_fast_5m_now):
            self.last_no_signal_reason = "bad_ema"
            return None

        cur = candles[i]
        o, h, l, c, v = float(cur.o), float(cur.h), float(cur.l), float(cur.c), float(cur.v)

        # Pullback detection — было N восходящих свечей перед текущей?
        recent = candles[i - cfg.pullback_bars: i]
        if not recent:
            self.last_no_signal_reason = "no_recent"
            return None
        rally_size = (max(float(x.h) for x in recent) - min(float(x.l) for x in recent))
        if rally_size < cfg.pullback_min_pct * atr:
            self.last_no_signal_reason = "no_pullback"
            return None

        # Текущая свеча уже выше локальной EMA20 (это и есть pullback к EMA)?
        # Логика: цена упала с пика, оттолкнулась от EMA20 снизу, или сейчас на ней
        if c > ema_fast_5m_now * 1.005:  # выше EMA на > 0.5% — слишком далеко
            self.last_no_signal_reason = "too_far_from_ema"
            return None

        # RSI зона 50-70 (overbought minor pullback)
        # Wilder RSI needs the seed window plus smoothing observations.
        rsi_closes = [float(x.c) for x in candles[max(0, i - cfg.rsi_period * 2): i + 1]]
        rsi = _rsi(rsi_closes, cfg.rsi_period)
        if not math.isfinite(rsi):
            self.last_no_signal_reason = "bad_rsi"
            return None
        if not (cfg.rsi_min <= rsi <= cfg.rsi_max):
            self.last_no_signal_reason = f"rsi_out_of_zone:{rsi:.1f}"
            return None

        # Rejection: upper wick > body * ratio
        body = abs(c - o)
        body_floor = max(body, 0.05 * atr)
        upper_wick = h - max(o, c)
        if upper_wick < cfg.min_reject_wick_ratio * body_floor:
            self.last_no_signal_reason = "no_rejection_wick"
            return None

        # Close in lower half of bar
        bar_range = max(h - l, 1e-9)
        close_pos = (c - l) / bar_range
        if close_pos > 0.55:
            self.last_no_signal_reason = "close_too_high"
            return None

        # Volume должен быть умеренным (не breakdown spike)
        avg_vol = sum(float(candles[j].v) * float(candles[j].c) for j in range(i - cfg.vol_avg_bars, i)) / float(cfg.vol_avg_bars)
        cur_vol = v * c
        if avg_vol > 0 and cur_vol > cfg.max_vol_mult * avg_vol:
            self.last_no_signal_reason = "volume_too_high"
            return None

        # ── ENTRY SHORT ──────────────────────────────────────────────────────
        sl = max(h, max(float(x.h) for x in recent)) + cfg.sl_pad_atr * atr
        risk = sl - c
        if risk <= 0:
            self.last_no_signal_reason = "bad_risk"
            return None
        tp = c - cfg.rr * risk

        self._last_signal_i[symbol] = i
        sig = TradeSignal(
            strategy=self.NAME,
            symbol=symbol,
            side="short",
            entry=c,
            sl=sl,
            tp=tp,
            time_stop_bars=cfg.time_stop_bars,
            reason=f"BRC1_SHORT regime={regime} rsi={rsi:.1f} pullback={cfg.pullback_bars}b vol_ratio={cur_vol/max(avg_vol,1e-9):.2f}",
        )
        if hasattr(sig, "tps") and cfg.tp1_frac > 0:
            tp1 = c - cfg.tp1_rr * risk
            sig.tps = [float(tp1), float(tp)]
            sig.tp_fracs = [cfg.tp1_frac, max(0.0, 1.0 - cfg.tp1_frac)]
        return sig

    def maybe_signal(
        self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0
    ) -> "Optional[TradeSignal]":
        """
        Standard live-runner interface. Bridges the index-based signal() to
        the timestamp-based maybe_signal(). Reads regime from store if available.
        """
        # Regime from store (main bot sets store.regime) or env fallback
        regime = str(getattr(store, "regime", "") or "").upper()
        if not regime:
            regime = str(os.getenv("LIVE_REGIME", "bear_trend")).upper()

        # Fetch recent 5m rows and convert to minimal Candle-like objects
        need = max(self.cfg.atr_period + 5, self.cfg.rsi_period + 5,
                   self.cfg.vol_avg_bars + 2, self.cfg.pullback_bars + 10, 80)
        raw_rows = []
        if hasattr(store, "fetch_klines"):
            raw_rows = store.fetch_klines(getattr(store, "symbol", ""), "5", need) or []

        if not raw_rows:
            self.last_no_signal_reason = "no_5m_data"
            return None

        class _C:
            """Minimal candle object matching BRC1's _atr/_rsi access pattern."""
            __slots__ = ("o", "h", "l", "c", "v")
            def __init__(self, r):
                self.o = float(r[1]); self.h = float(r[2])
                self.l = float(r[3]); self.c = float(r[4])
                self.v = float(r[5]) if len(r) > 5 else 0.0

        candles_local = [_C(r) for r in raw_rows]

        # Patch/append the live tick as the current bar
        live_bar = _C([0, o, h, l, c, v])
        bar_ms = (ts_ms // 300_000) * 300_000  # 5m bucket
        last_bar_ms = int(float(raw_rows[-1][0]))
        same_bucket = abs(bar_ms - last_bar_ms) < 300_000
        if same_bucket:
            candles_local[-1] = live_bar
        else:
            candles_local.append(live_bar)

        i = len(candles_local) - 1

        # Temporarily inject candles into store.c5 for signal()
        orig_c5 = getattr(store, "c5", None)
        store.c5 = candles_local
        try:
            sig = self.signal(store, getattr(store, "symbol", ""), i, regime=regime)
        finally:
            if orig_c5 is not None:
                store.c5 = orig_c5
            else:
                try:
                    del store.c5
                except AttributeError:
                    pass

        return sig

===== END FILE: strategies/alt_bear_regime_continuation_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/micro_scalper_v1.py =====
GROUP: MEDIUM PRIORITY / NOT REVIEWED
REVIEW_FOCUS: Micro scalper; fee-sensitive, needs review only after maker/fee plan.
====================================================================================================

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

===== END FILE: strategies/micro_scalper_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/pump_fade_smart_v1.py =====
GROUP: MEDIUM PRIORITY / NOT REVIEWED
REVIEW_FOCUS: Pump fade smart; needs review if still considered.
====================================================================================================

"""
pump_fade_smart_v1 (PFS1) — Quality-gated pump fade strategy.

Идея простая, но дисциплинированная: ловим неустойчивые pump'ы на perpetual
futures и шортим только на подтверждённой rejection-свече после exhaustion'а.
В отличие от наивных pump-fade'ов, PFS1 НЕ входит «потому что выросло» —
у нас стек фильтров, который снимает 80% ложных сигналов.

Структура входа (SHORT)
-----------------------
1. **Liquidity gate.** Символ должен быть в `PFS1_SYMBOL_ALLOWLIST` (default —
   крупнейшие альты + BTC/ETH). Микрокапы → reject (manipulation risk).
2. **Pump detection (5m).** За `PFS1_PUMP_LOOKBACK_BARS` 5m-баров суммарное
   движение вверх ≥ `PFS1_PUMP_MIN_PCT`. Volume Z-score последних 3 баров
   относительно 60-баров среднего ≥ `PFS1_VOL_Z_MIN`.
3. **Macro overbought (1H).** RSI(14) на 1H > `PFS1_RSI_H1_MIN_OB`. Сама
   высокая RSI не вход, но без неё мы тушим зажигалкой.
4. **Funding crowding.** Funding rate (8h) ≥ `PFS1_FUNDING_THRESHOLD`
   (например 0.05%). Большой positive funding = лонги-крауд платит шортам,
   classic exhaustion signal.
5. **Rejection candle.** Текущая 5m-свеча: bearish body ≥ `PFS1_REJECT_BODY_FRAC`
   от полной свечи, upper wick ≥ `PFS1_REJECT_WICK_FRAC` от свечи.
   Закрытие < open of pump-первого бара (т.е. отдают весь рост).
6. **Risk constraint.** ATR(14)-нормализованная дистанция до entry не больше
   `PFS1_MAX_DIST_ATR`.

Stop / Target
-------------
- **SL** = high of pump + `PFS1_SL_ATR_BUFFER * ATR` (защита от sweep'а).
- **TP1** = entry − `PFS1_TP1_RR * risk` (закрываем `PFS1_TP1_FRAC` позиции).
- **TP2** = entry − `PFS1_TP2_RR * risk` (остаток).
- **Break-even** при достижении `PFS1_BE_TRIGGER_RR * risk`.
- **Trailing ATR** после `PFS1_TRAIL_ACTIVATE_RR * risk` (необязательно — env).
- **Time stop**: `PFS1_TIME_STOP_BARS_5M` баров (default 144 = 12h).
- **Cooldown**: `PFS1_COOLDOWN_BARS_5M` после любой сделки (default 96 = 8h).

Env vars (префикс PFS1_)
------------------------
  PFS1_SYMBOL_ALLOWLIST              csv     default: BTCUSDT,ETHUSDT,SOLUSDT,...
  PFS1_SIGNAL_TF                     str     5  (5-минутный TF)
  PFS1_MACRO_TF                      str     60 (1-часовой для RSI)
  PFS1_SIGNAL_LOOKBACK               int     200
  PFS1_ATR_PERIOD                    int     14
  PFS1_RSI_PERIOD                    int     14
  PFS1_PUMP_LOOKBACK_BARS            int     6      (30 минут)
  PFS1_PUMP_MIN_PCT                  float   3.0
  PFS1_VOL_Z_MIN                     float   2.0
  PFS1_RSI_H1_MIN_OB                 float   65
  PFS1_FUNDING_THRESHOLD             float   0.05   (% per 8h)
  PFS1_REJECT_BODY_FRAC              float   0.45
  PFS1_REJECT_WICK_FRAC              float   0.30
  PFS1_MAX_DIST_ATR                  float   2.5
  PFS1_SL_ATR_BUFFER                 float   0.5
  PFS1_TP1_RR                        float   1.2
  PFS1_TP2_RR                        float   2.5
  PFS1_TP1_FRAC                      float   0.55
  PFS1_BE_TRIGGER_RR                 float   1.0
  PFS1_BE_LOCK_RR                    float   0.05
  PFS1_TRAIL_ATR_MULT                float   0.0    (0 = off)
  PFS1_TRAIL_ACTIVATE_RR             float   1.5
  PFS1_TIME_STOP_BARS_5M             int     144
  PFS1_COOLDOWN_BARS_5M              int     96
  PFS1_ALLOW_SHORTS                  bool    1
  PFS1_ALLOW_LONGS                   bool    0      (symmetric long-fade-dump optional)

Author: Claude Opus, 2026-06-03. Quality-first pump fade, не «short на любое движение».
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
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def _ema(values: List[float], period: int) -> float:
    if len(values) < period:
        return values[-1] if values else 0.0
    k = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1.0 - k)
    return ema


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses += -diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return sum(trs[-period:]) / period


def _vol_zscore(volumes: List[float], baseline_period: int = 60, recent_period: int = 3) -> float:
    if len(volumes) < baseline_period + recent_period:
        return 0.0
    base = volumes[-baseline_period - recent_period:-recent_period]
    recent = volumes[-recent_period:]
    if not base or not recent:
        return 0.0
    mean = sum(base) / len(base)
    var = sum((v - mean) ** 2 for v in base) / max(1, len(base) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std <= 0:
        return 0.0
    recent_avg = sum(recent) / len(recent)
    return (recent_avg - mean) / std


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

@dataclass
class PFS1Config:
    signal_tf: str = "5"
    macro_tf: str = "60"
    signal_lookback: int = 200
    atr_period: int = 14
    rsi_period: int = 14
    pump_lookback_bars: int = 6
    pump_min_pct: float = 3.0
    vol_z_min: float = 2.0
    rsi_h1_min_ob: float = 65.0
    funding_threshold: float = 0.05
    require_funding_data: bool = False
    reject_body_frac: float = 0.45
    reject_wick_frac: float = 0.30
    max_dist_atr: float = 2.5
    sl_atr_buffer: float = 0.5
    tp1_rr: float = 1.2
    tp2_rr: float = 2.5
    tp1_frac: float = 0.55
    be_trigger_rr: float = 1.0
    be_lock_rr: float = 0.05
    trail_atr_mult: float = 0.0
    trail_activate_rr: float = 1.5
    time_stop_bars_5m: int = 144
    cooldown_bars_5m: int = 96
    allow_shorts: bool = True
    allow_longs: bool = False


class PumpFadeSmartV1Strategy:
    """Quality-gated pump fade strategy."""

    def __init__(self) -> None:
        self.cfg = PFS1Config()
        self._load_env()
        self._cooldown_bars = 0
        self._last_tf_ts: Optional[int] = None
        self._allow: set = set()
        self._deny: set = set()
        self.last_no_signal_reason: str = ""
        self._refresh_lists()

    def _no_signal(self, reason: str) -> None:
        self.last_no_signal_reason = str(reason or "unknown")

    def _load_env(self) -> None:
        c = self.cfg
        c.signal_tf = os.getenv("PFS1_SIGNAL_TF", c.signal_tf)
        c.macro_tf = os.getenv("PFS1_MACRO_TF", c.macro_tf)
        c.signal_lookback = _env_int("PFS1_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("PFS1_ATR_PERIOD", c.atr_period)
        c.rsi_period = _env_int("PFS1_RSI_PERIOD", c.rsi_period)
        c.pump_lookback_bars = _env_int("PFS1_PUMP_LOOKBACK_BARS", c.pump_lookback_bars)
        c.pump_min_pct = _env_float("PFS1_PUMP_MIN_PCT", c.pump_min_pct)
        c.vol_z_min = _env_float("PFS1_VOL_Z_MIN", c.vol_z_min)
        c.rsi_h1_min_ob = _env_float("PFS1_RSI_H1_MIN_OB", c.rsi_h1_min_ob)
        c.funding_threshold = _env_float("PFS1_FUNDING_THRESHOLD", c.funding_threshold)
        c.require_funding_data = _env_bool("PFS1_REQUIRE_FUNDING_DATA", c.require_funding_data)
        c.reject_body_frac = _env_float("PFS1_REJECT_BODY_FRAC", c.reject_body_frac)
        c.reject_wick_frac = _env_float("PFS1_REJECT_WICK_FRAC", c.reject_wick_frac)
        c.max_dist_atr = _env_float("PFS1_MAX_DIST_ATR", c.max_dist_atr)
        c.sl_atr_buffer = _env_float("PFS1_SL_ATR_BUFFER", c.sl_atr_buffer)
        c.tp1_rr = _env_float("PFS1_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("PFS1_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("PFS1_TP1_FRAC", c.tp1_frac)
        c.be_trigger_rr = _env_float("PFS1_BE_TRIGGER_RR", c.be_trigger_rr)
        c.be_lock_rr = _env_float("PFS1_BE_LOCK_RR", c.be_lock_rr)
        c.trail_atr_mult = _env_float("PFS1_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_activate_rr = _env_float("PFS1_TRAIL_ACTIVATE_RR", c.trail_activate_rr)
        c.time_stop_bars_5m = _env_int("PFS1_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("PFS1_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_shorts = _env_bool("PFS1_ALLOW_SHORTS", c.allow_shorts)
        c.allow_longs = _env_bool("PFS1_ALLOW_LONGS", c.allow_longs)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set(
            "PFS1_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT,AVAXUSDT",
        )
        self._deny = _env_csv_set("PFS1_SYMBOL_DENYLIST")

    # ------------------------------------------------------------------
    # Pump detection
    # ------------------------------------------------------------------

    def _detect_pump(
        self,
        closes: List[float],
        volumes: List[float],
    ) -> Tuple[bool, float, int, float]:
        """Detect the completed pump immediately before the rejection bar."""
        c = self.cfg
        if len(closes) < c.pump_lookback_bars + 2:
            return False, 0.0, 0, 0.0
        start = closes[-c.pump_lookback_bars - 1]
        # The latest bar is the rejection candidate. Including it in the pump
        # return made the pump and full-giveback conditions contradictory.
        end = closes[-2]
        if start <= 0:
            return False, 0.0, 0, 0.0
        pct = (end - start) / start * 100.0
        vol_z = _vol_zscore(volumes, baseline_period=60, recent_period=3)
        is_pump = pct >= c.pump_min_pct and vol_z >= c.vol_z_min
        return is_pump, pct, c.pump_lookback_bars, vol_z

    def _check_rejection(
        self,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        pump_start_open: float,
    ) -> bool:
        """Текущая свеча: bearish, тело >= reject_body_frac, верхний фитиль >= reject_wick_frac."""
        c = self.cfg
        o, h, l, cl = opens[-1], highs[-1], lows[-1], closes[-1]
        rng = h - l
        if rng <= 0:
            return False
        body = abs(cl - o)
        is_bearish = cl < o
        body_frac = body / rng
        upper_wick = h - max(o, cl)
        wick_frac = upper_wick / rng
        # Закрытие должно вернуться ниже open первого pump-бара (отдали почти весь рост)
        gave_back = cl < pump_start_open * 1.005  # 0.5% толерантность
        return is_bearish and body_frac >= c.reject_body_frac and wick_frac >= c.reject_wick_frac and gave_back

    # ------------------------------------------------------------------
    # Main signal API
    # ------------------------------------------------------------------

    def maybe_signal(
        self,
        store,
        ts_ms: int,
        o: float,
        h: float,
        l: float,
        cl: float,
        v: float = 0.0,
    ) -> Optional[TradeSignal]:
        """Возвращает TradeSignal или None. store должен иметь fetch_klines(symbol, interval, limit)."""
        self.last_no_signal_reason = ""
        symbol = getattr(store, "symbol", "")
        c = self.cfg

        # Symbol gate
        if self._allow and symbol.upper() not in self._allow:
            self._no_signal("symbol_not_allowed")
            return None
        if self._deny and symbol.upper() in self._deny:
            self._no_signal("symbol_denied")
            return None

        # Direction gate
        if not c.allow_shorts and not c.allow_longs:
            self._no_signal("shorts_and_longs_disabled")
            return None

        # Bar dedupe (one signal per closed bar)
        if self._last_tf_ts is not None and ts_ms <= self._last_tf_ts:
            self._no_signal("same_signal_bar")
            return None

        # Cooldown
        if self._cooldown_bars > 0:
            self._cooldown_bars -= 1
            self._no_signal("cooldown")
            return None

        # Fetch klines
        try:
            rows_5m = store.fetch_klines(symbol, c.signal_tf, c.signal_lookback) or []
            rows_h1 = store.fetch_klines(symbol, c.macro_tf, 80) or []
        except Exception:
            self._no_signal("history_short")
            return None

        if len(rows_5m) < max(c.pump_lookback_bars + 60, c.atr_period + 30):
            self._no_signal("history_short")
            return None
        if len(rows_h1) < c.rsi_period + 5:
            self._no_signal("macro_history_short")
            return None

        opens5 = [float(r[1]) for r in rows_5m]
        highs5 = [float(r[2]) for r in rows_5m]
        lows5 = [float(r[3]) for r in rows_5m]
        closes5 = [float(r[4]) for r in rows_5m]
        volumes5 = [float(r[5]) for r in rows_5m]
        closes_h1 = [float(r[4]) for r in rows_h1]

        # Pump detection
        is_pump, pump_pct, look_n, vol_z = self._detect_pump(closes5, volumes5)
        if not is_pump:
            self._no_signal(f"no_pump_pct={pump_pct:.2f}_volz={vol_z:.2f}")
            return None

        # Macro overbought (RSI on 1H)
        rsi_h1 = _rsi(closes_h1, c.rsi_period)
        if rsi_h1 < c.rsi_h1_min_ob:
            self._no_signal(f"macro_not_overbought_rsi={rsi_h1:.1f}")
            return None

        # Funding may be optional in live, but research can require it so a
        # price-only backtest cannot masquerade as a validated funding setup.
        funding_pct: float | None = None
        try:
            f = getattr(store, "fetch_funding_rate", None)
            if callable(f):
                funding_pct = float(f(symbol)) * 100.0  # rate is decimal, convert to %
        except Exception:
            funding_pct = None
        if funding_pct is None and c.require_funding_data:
            self._no_signal("funding_missing")
            return None
        if funding_pct is not None and funding_pct < c.funding_threshold:
            self._no_signal(f"funding_low={funding_pct:.4f}")
            return None

        # Pump start open (start of lookback window)
        pump_start_open = opens5[-look_n - 1] if len(opens5) >= look_n + 1 else opens5[-look_n]

        # Rejection candle on the latest closed bar
        if not self._check_rejection(opens5, highs5, lows5, closes5, pump_start_open):
            self._no_signal("no_rejection_candle")
            return None

        # ATR + risk math
        atr = _atr(highs5, lows5, closes5, c.atr_period)
        if atr <= 0:
            self._no_signal("atr_invalid")
            return None

        entry = closes5[-1]
        pump_high = max(highs5[-look_n - 1:])
        sl = pump_high + c.sl_atr_buffer * atr
        risk = sl - entry
        if risk <= 0:
            self._no_signal("invalid_risk")
            return None

        # Distance to entry constraint
        dist_atr = (pump_high - entry) / atr
        if dist_atr > c.max_dist_atr:
            self._no_signal(f"too_extended_dist_atr={dist_atr:.2f}")
            return None

        # Take profits (short — TP below entry)
        tp1 = entry - c.tp1_rr * risk
        tp2 = entry - c.tp2_rr * risk

        # Update state for cooldown / bar dedupe (caller fills cooldown after entry)
        self._last_tf_ts = ts_ms
        self._cooldown_bars = c.cooldown_bars_5m

        return TradeSignal(
            strategy="pump_fade_smart_v1",
            symbol=symbol,
            side="Sell",
            entry=entry,
            sl=sl,
            tp=tp1,  # TP1 only; runner handles TP2/trail
            reason=f"pfs1_pump_fade pump={pump_pct:.2f}% volz={vol_z:.2f} rsih1={rsi_h1:.1f}"
                   + (f" funding={funding_pct:.4f}" if funding_pct is not None else " funding=na"),
        )


# ---------------------------------------------------------------------------
# Selector helper for portfolio backtest integration
# ---------------------------------------------------------------------------

class PFS1Selector:
    """Per-symbol PumpFadeSmartV1 instances. Mirrors ATT1/breakdown selector pattern."""

    def __init__(self):
        self._strategies: dict[str, PumpFadeSmartV1Strategy] = {}

    def get(self, symbol: str) -> PumpFadeSmartV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = PumpFadeSmartV1Strategy()
        return self._strategies[symbol]

    def reset(self, symbol: str) -> None:
        self._strategies.pop(symbol, None)

===== END FILE: strategies/pump_fade_smart_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/liquidation_cascade_entry_v1.py =====
GROUP: MEDIUM PRIORITY / NOT REVIEWED
REVIEW_FOCUS: Liquidation cascade; review after liquidation feed quality is proven.
====================================================================================================

"""
strategies/liquidation_cascade_entry_v1.py — Liquidation Cascade Entry v1
==========================================================================
Edge: When a rapid cascade of liquidations fires (large market-driven stop hunts),
price briefly overshoots fair value. We enter a counter-trend position as the panic
exhausts itself.

LOGIC:
  LONG (buy the panic dip):
    - Price dropped > LC_DROP_PCT % in last LC_LOOKBACK_BARS × 5m bars
    - RSI(14) dropped below LC_RSI_OVERSOLD (≤ 25 indicates true panic)
    - Volume spike: last bar volume ≥ LC_VOL_SPIKE_X × avg volume (capitulation candle)
    - Price is ≥ LC_BELOW_EMA_PCT % below EMA(LC_EMA_PERIOD)
    - Optional: only enter if OI (open interest) dropped → confirms long liquidations hit

  SHORT (fade the squeeze):
    - Price rallied > LC_DROP_PCT % in last LC_LOOKBACK_BARS × 5m bars
    - RSI(14) > LC_RSI_OVERBOUGHT (≥ 75 = shorts being squeezed)
    - Volume spike AND price ≥ LC_BELOW_EMA_PCT % ABOVE EMA
    - Controlled via LC_ALLOW_SHORTS env var

EXIT:
    - SL = LC_SL_ATR_MULT × ATR(14) (tight, cascade can resume)
    - TP = LC_TP_ATR_MULT × ATR(14)
    - Time stop = LC_TIME_STOP_BARS_5M bars (≈ 4h default = 48 bars)
    - Breakeven at LC_BE_PCT % profit
    - Cooldown = LC_COOLDOWN_BARS after any signal (prevents re-entry during sustained move)

WHY IT WORKS:
    Liquidation cascades on Bybit perpetuals create predictable overshoots because:
    1. Liquidation engines are mechanical — they dump at market regardless of level
    2. After the cascade, no more forced sellers → price snaps back
    3. Edge window is SHORT (minutes), so intraday timeframe (5m) is ideal
    4. Most effective on high-OI alt coins (AVAX, SOL, BNB) where small cascades = big moves

CONFIG (env vars):
    LC_ALLOW_LONGS=1             Enable long entries (default: 1)
    LC_ALLOW_SHORTS=0            Enable short entries (default: 0, shorts are riskier)
    LC_LOOKBACK_BARS=6           How many 5m bars to look back for the cascade (30 min)
    LC_DROP_PCT=3.0              Minimum % drop/rally to qualify as cascade (3%)
    LC_EMA_PERIOD=55             EMA period for dislocation check
    LC_BELOW_EMA_PCT=2.0         Must be ≥ this % below/above EMA
    LC_RSI_OVERSOLD=28.0         RSI threshold for longs
    LC_RSI_OVERBOUGHT=72.0       RSI threshold for shorts
    LC_VOL_SPIKE_X=2.5           Volume of entry bar vs avg (N bars) must be ≥ this
    LC_VOL_AVG_BARS=20           Bars to average volume over
    LC_SL_ATR_MULT=1.2           SL tightness (cascades: tight stop, fast TP)
    LC_TP_ATR_MULT=2.0           TP target
    LC_BE_PCT=0.8                Move to breakeven after 0.8% profit
    LC_TIME_STOP_BARS_5M=48      Max hold = 48 × 5min = 4 hours
    LC_COOLDOWN_BARS=12          Cooldown after signal = 1 hour (12 × 5min)
    LC_MIN_VOLUME_USDT=2000000   Min bar volume in USDT (filter thin coins)
    LC_ATR_PERIOD=14             ATR lookback

AUTORESEARCH:
    nohup python3 scripts/run_strategy_autoresearch.py \
        --spec configs/autoresearch/liquidation_cascade_v1_grid.json \
        > /tmp/lc_v1.log 2>&1 &
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

# ── shared types (match the pattern used by other strategies in this repo) ──
try:
    from .signals import TradeSignal  # package import (backtest / live)
except ImportError:
    try:
        from strategies.signals import TradeSignal  # absolute import fallback
    except ImportError:
        try:
            from backtest.engine import TradeSignal  # legacy engine fallback
        except ImportError:
            from typing import Any
            TradeSignal = Any  # type: ignore[assignment,misc]

try:
    from backtest.engine import KlineStore
except ImportError:
    from typing import Any
    KlineStore = Any  # type: ignore[assignment,misc]


# ── Config ──────────────────────────────────────────────────────────────────

@dataclass
class LiquidationCascadeConfig:
    allow_longs:         bool  = field(default_factory=lambda: os.getenv("LC_ALLOW_LONGS", "1") == "1")
    allow_shorts:        bool  = field(default_factory=lambda: os.getenv("LC_ALLOW_SHORTS", "0") == "1")
    lookback_bars:       int   = field(default_factory=lambda: int(os.getenv("LC_LOOKBACK_BARS", "6")))
    drop_pct:            float = field(default_factory=lambda: float(os.getenv("LC_DROP_PCT", "3.0")))
    ema_period:          int   = field(default_factory=lambda: int(os.getenv("LC_EMA_PERIOD", "55")))
    below_ema_pct:       float = field(default_factory=lambda: float(os.getenv("LC_BELOW_EMA_PCT", "2.0")))
    rsi_oversold:        float = field(default_factory=lambda: float(os.getenv("LC_RSI_OVERSOLD", "28.0")))
    rsi_overbought:      float = field(default_factory=lambda: float(os.getenv("LC_RSI_OVERBOUGHT", "72.0")))
    vol_spike_x:         float = field(default_factory=lambda: float(os.getenv("LC_VOL_SPIKE_X", "2.5")))
    vol_avg_bars:        int   = field(default_factory=lambda: int(os.getenv("LC_VOL_AVG_BARS", "20")))
    sl_atr_mult:         float = field(default_factory=lambda: float(os.getenv("LC_SL_ATR_MULT", "1.2")))
    tp_atr_mult:         float = field(default_factory=lambda: float(os.getenv("LC_TP_ATR_MULT", "2.0")))
    be_pct:              float = field(default_factory=lambda: float(os.getenv("LC_BE_PCT", "0.8")))
    time_stop_bars:      int   = field(default_factory=lambda: int(os.getenv("LC_TIME_STOP_BARS_5M", "48")))
    cooldown_bars:       int   = field(default_factory=lambda: int(os.getenv("LC_COOLDOWN_BARS", "12")))
    min_volume_usdt:     float = field(default_factory=lambda: float(os.getenv("LC_MIN_VOLUME_USDT", "2000000")))
    atr_period:          int   = field(default_factory=lambda: int(os.getenv("LC_ATR_PERIOD", "14")))


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ema(values: list, period: int) -> float:
    if len(values) < period:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = float(values[0])
    for v in values[1:]:
        e = float(v) * k + e * (1.0 - k)
    return e


def _rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = float(closes[i]) - float(closes[i - 1])
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(candles: list, period: int = 14) -> float:
    """candles: list of objects with .h .l .c attributes"""
    if len(candles) < period + 1:
        return float("nan")
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i].h)
        l = float(candles[i].l)
        pc = float(candles[i - 1].c)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    recent = trs[-period:]
    return sum(recent) / len(recent)


# ── Strategy ─────────────────────────────────────────────────────────────────

class LiquidationCascadeEntryV1:
    """
    Counter-trend entry after liquidation cascade exhaustion.
    Compatible with run_portfolio.py backtest (KlineStore) and live bot integration.
    """

    def __init__(self) -> None:
        self.cfg = LiquidationCascadeConfig()
        self._last_signal_bar: int = -9999  # bar index of last signal (cooldown)

    def _reload_cfg(self) -> None:
        """Re-read env vars each call (allows live parameter tweaks)."""
        self.cfg = LiquidationCascadeConfig()

    def maybe_signal(
        self,
        store: KlineStore,
        ts_ms: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> Optional[TradeSignal]:
        self._reload_cfg()
        cfg = self.cfg

        # ── 1. Gather candles ────────────────────────────────────────────────
        try:
            i = int(getattr(store, "i5", getattr(store, "i", None)))
            candles = store.c5
        except (AttributeError, TypeError):
            return None

        min_bars = max(cfg.lookback_bars, cfg.ema_period, cfg.vol_avg_bars, cfg.atr_period) + 5
        if i < min_bars:
            return None

        # ── 2. Cooldown ──────────────────────────────────────────────────────
        if i - self._last_signal_bar < cfg.cooldown_bars:
            return None

        # ── 3. Volume filter ─────────────────────────────────────────────────
        bar_vol_usdt = volume * close
        if bar_vol_usdt < cfg.min_volume_usdt:
            return None

        # ── 4. ATR ──────────────────────────────────────────────────────────
        atr = _atr(candles[i - cfg.atr_period - 1: i + 1], cfg.atr_period)
        if not atr or atr != atr:  # nan guard
            return None

        # ── 5. EMA for dislocation check ─────────────────────────────────────
        ema_src = [float(candles[j].c) for j in range(i - cfg.ema_period + 1, i + 1)]
        ema = _ema(ema_src, cfg.ema_period)
        if not ema or ema != ema:
            return None

        # ── 6. RSI ──────────────────────────────────────────────────────────
        rsi_period = 14
        rsi_src = [float(candles[j].c) for j in range(i - rsi_period - 1, i + 1)]
        rsi = _rsi(rsi_src, rsi_period)
        if rsi != rsi:
            return None

        # ── 7. Cascade detection (price move over lookback) ──────────────────
        lookback_start = candles[i - cfg.lookback_bars]
        cascade_high = max(float(candles[j].h) for j in range(i - cfg.lookback_bars, i + 1))
        cascade_low  = min(float(candles[j].l) for j in range(i - cfg.lookback_bars, i + 1))
        lookback_open = float(lookback_start.o)

        drop_pct_actual   = (lookback_open - close) / lookback_open * 100.0   # positive = dropped
        rally_pct_actual  = (close - lookback_open) / lookback_open * 100.0   # positive = rallied

        # ── 8. Volume spike check ────────────────────────────────────────────
        avg_vol = sum(
            float(candles[j].v) * float(candles[j].c)
            for j in range(i - cfg.vol_avg_bars, i)
        ) / cfg.vol_avg_bars
        vol_spike = bar_vol_usdt / avg_vol if avg_vol > 0 else 0.0

        # ── 9. Entry conditions ───────────────────────────────────────────────
        direction: Optional[str] = None
        entry_reason = ""

        if cfg.allow_longs:
            dislocation_below = (ema - close) / ema * 100.0  # positive = below EMA
            if (
                drop_pct_actual >= cfg.drop_pct
                and rsi <= cfg.rsi_oversold
                and vol_spike >= cfg.vol_spike_x
                and dislocation_below >= cfg.below_ema_pct
            ):
                direction = "long"
                entry_reason = (
                    f"LC_LONG drop={drop_pct_actual:.1f}% RSI={rsi:.1f} "
                    f"vol_x={vol_spike:.1f} ema_dis={dislocation_below:.1f}%"
                )

        if direction is None and cfg.allow_shorts:
            dislocation_above = (close - ema) / ema * 100.0  # positive = above EMA
            if (
                rally_pct_actual >= cfg.drop_pct
                and rsi >= cfg.rsi_overbought
                and vol_spike >= cfg.vol_spike_x
                and dislocation_above >= cfg.below_ema_pct
            ):
                direction = "short"
                entry_reason = (
                    f"LC_SHORT rally={rally_pct_actual:.1f}% RSI={rsi:.1f} "
                    f"vol_x={vol_spike:.1f} ema_dis={dislocation_above:.1f}%"
                )

        if direction is None:
            return None

        # ── 10. Build signal ──────────────────────────────────────────────────
        self._last_signal_bar = i

        # Get symbol from store (same pattern as funding_rate_reversion_v1)
        symbol = str(getattr(store, "symbol", "") or "").upper()

        sl_dist = atr * cfg.sl_atr_mult
        tp_dist = atr * cfg.tp_atr_mult

        if direction == "long":
            sl_price = close - sl_dist
            tp_price = close + tp_dist
        else:
            sl_price = close + sl_dist
            tp_price = close - tp_dist

        be_trigger_rr = cfg.be_pct / (sl_dist / close * 100.0) if sl_dist > 0 else 0.0

        try:
            return TradeSignal(
                strategy="liquidation_cascade_entry_v1",
                symbol=symbol,
                side=direction,           # TradeSignal uses "side", not "direction"
                entry=close,
                sl=sl_price,
                tp=tp_price,
                be_trigger_rr=be_trigger_rr,
                trailing_atr_mult=0.0,
                time_stop_bars=cfg.time_stop_bars,
                reason=entry_reason,
            )
        except Exception:
            return None

===== END FILE: strategies/liquidation_cascade_entry_v1.py =====
====================================================================================================


====================================================================================================
===== BEGIN FILE: strategies/funding_rate_reversion_v1.py =====
GROUP: MEDIUM PRIORITY / NOT REVIEWED
REVIEW_FOCUS: Funding reversion/carry; must include realized funding in validation.
====================================================================================================

"""
Funding Rate Reversion v1 — Bybit Perpetuals Edge
==================================================
Edge rationale:
  Bybit perpetual futures pay/receive funding every 8 hours (00:00, 08:00, 16:00 UTC).
  When funding rate is extreme (|rate| > threshold):
    • Positive extreme (+0.06%+) → longs are overpaying → market is overextended long
      → Mean reversion SHORT: market tends to sell off or stall after funding
    • Negative extreme (-0.06%+) → shorts are overpaying → oversold condition
      → Mean reversion LONG: snapback rally likely after funding

  This is a Bybit-specific edge not available on spot exchanges.
  Typical duration: 1-6 hours (1-72 5m bars). Fast reversal then exit.

Entry conditions (confluence required):
  1. Funding rate extreme at last 8h window (|rate| ≥ FR_THRESHOLD)
  2. Price extended from EMA (EMA_FAST): price > EMA * (1 + EXT_PCT) for short
  3. RSI confirms overbought/oversold (RSI ≥ RSI_OB for short, ≤ RSI_OS for long)
  4. No cooldown from recent trade
  5. Within trading session (session_utc_start → session_utc_end)

Exit:
  • Fixed SL: SL_ATR_MULT × ATR14 from entry
  • TP: TP_ATR_MULT × ATR14 from entry (mean reversion target)
  • Time stop: TIME_STOP_BARS_5M bars after entry

Funding rate source:
  • Injected via store.funding_rate (float, e.g. 0.0008 = 0.08%)
  • OR via environment variable FR_LATEST_{SYMBOL} for testing
  • See scripts/funding_rate_fetcher.py for live data injection

Config env vars:
  FR_THRESHOLD=0.0006         # 0.06% default (bybit typical extreme)
  FR_EMA_PERIOD=55            # trend EMA period
  FR_EXT_PCT=0.005            # price extension from EMA (0.5%)
  FR_RSI_PERIOD=14
  FR_RSI_OB=65.0              # RSI overbought threshold for shorts
  FR_RSI_OS=35.0              # RSI oversold threshold for longs
  FR_SL_ATR_MULT=1.5
  FR_TP_ATR_MULT=2.5
  FR_TIME_STOP_BARS_5M=72     # 6 hours max hold
  FR_COOLDOWN_BARS=24         # 2h cooldown between trades
  FR_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,AVAXUSDT
  FR_MIN_VOLUME_USDT=1000000  # min bar volume for liquid market check
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from .signals import TradeSignal

_ROOT = Path(__file__).resolve().parent.parent
_FUNDING_LATEST_PATH = _ROOT / "configs" / "funding_rates_latest.json"
_FUNDING_JSON_CACHE_TS = 0.0
_FUNDING_JSON_CACHE: Dict[str, float] = {}
_FUNDING_JSON_TTL_SEC = 30.0


def _read_latest_funding_file() -> Dict[str, float]:
    global _FUNDING_JSON_CACHE_TS, _FUNDING_JSON_CACHE
    now = time.time()
    if now - _FUNDING_JSON_CACHE_TS < _FUNDING_JSON_TTL_SEC:
        return _FUNDING_JSON_CACHE
    rates: Dict[str, float] = {}
    try:
        payload = json.loads(_FUNDING_LATEST_PATH.read_text())
        raw_rates = dict(payload.get("rates") or {})
        for sym, val in raw_rates.items():
            try:
                rates[str(sym).upper()] = float(val)
            except Exception:
                continue
    except Exception:
        rates = {}
    _FUNDING_JSON_CACHE = rates
    _FUNDING_JSON_CACHE_TS = now
    return rates


# ── Helpers ────────────────────────────────────────────────────────────────────
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


def _env_csv_set(name: str, default: str = "") -> set:
    raw = os.getenv(name, default) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    if period <= 0 or len(closes) < period + 1:
        return float("nan")
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
    gains, losses = 0.0, 0.0
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


# ── Config ─────────────────────────────────────────────────────────────────────
@dataclass
class FundingRateReversionConfig:
    fr_threshold: float = 0.0006        # |funding rate| trigger (0.06%)
    ema_period: int = 55                # trend EMA
    ext_pct: float = 0.005             # price extension from EMA (0.5%)
    rsi_period: int = 14
    rsi_ob: float = 65.0               # overbought → short candidate
    rsi_os: float = 35.0               # oversold → long candidate
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.5
    time_stop_bars: int = 72           # 6h max hold at 5m bars
    cooldown_bars: int = 24            # 2h cooldown
    session_utc_start: int = 0         # 24h market, no session filter by default
    session_utc_end: int = 24
    min_volume_usdt: float = 1_000_000 # min bar volume filter
    allow_longs: bool = True
    allow_shorts: bool = True


# ── Strategy ───────────────────────────────────────────────────────────────────
class FundingRateReversionV1:
    """
    Funding rate mean reversion strategy for Bybit perpetual futures.
    Works on 5m bars. Reads funding rate from store.funding_rate or env.
    """

    name = "funding_rate_reversion_v1"

    def __init__(self, cfg: Optional[FundingRateReversionConfig] = None) -> None:
        self.cfg = cfg or FundingRateReversionConfig()
        self._reload_config()

        self._closes: List[float] = []
        self._highs:  List[float] = []
        self._lows:   List[float] = []
        self._vols:   List[float] = []
        self._cooldown: int = 0
        self._last_funding_rate: float = 0.0  # cached from store
        self._last_funding_ts: int = 0

    def _reload_config(self) -> None:
        c = self.cfg
        c.fr_threshold    = _env_float("FR_THRESHOLD",          c.fr_threshold)
        c.ema_period      = _env_int("FR_EMA_PERIOD",           c.ema_period)
        c.ext_pct         = _env_float("FR_EXT_PCT",            c.ext_pct)
        c.rsi_period      = _env_int("FR_RSI_PERIOD",           c.rsi_period)
        c.rsi_ob          = _env_float("FR_RSI_OB",             c.rsi_ob)
        c.rsi_os          = _env_float("FR_RSI_OS",             c.rsi_os)
        c.sl_atr_mult     = _env_float("FR_SL_ATR_MULT",        c.sl_atr_mult)
        c.tp_atr_mult     = _env_float("FR_TP_ATR_MULT",        c.tp_atr_mult)
        c.time_stop_bars  = _env_int("FR_TIME_STOP_BARS_5M",    c.time_stop_bars)
        c.cooldown_bars   = _env_int("FR_COOLDOWN_BARS",        c.cooldown_bars)
        c.min_volume_usdt = _env_float("FR_MIN_VOLUME_USDT",    c.min_volume_usdt)
        c.allow_longs     = os.getenv("FR_ALLOW_LONGS", "1").strip() in {"1","true","yes"}
        c.allow_shorts    = os.getenv("FR_ALLOW_SHORTS", "1").strip() in {"1","true","yes"}

        self._allow = _env_csv_set(
            "FR_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,AVAXUSDT"
        )

    def _in_session(self, ts_ms: int) -> bool:
        h = ((ts_ms // 1000) // 3600) % 24
        if self.cfg.session_utc_start <= self.cfg.session_utc_end:
            return self.cfg.session_utc_start <= h < self.cfg.session_utc_end
        return h >= self.cfg.session_utc_start or h < self.cfg.session_utc_end

    def _get_funding_rate(self, store, symbol: str) -> Optional[float]:
        """
        Try to get funding rate from:
        1. store.funding_rate (injected by live bot's funding fetcher)
        2. Environment variable FR_LATEST_{SYMBOL} (for testing/override)
        3. configs/funding_rates_latest.json (cron / sidecar process fallback)
        Returns None if unavailable.
        """
        # Priority 1: store attribute
        fr = getattr(store, "funding_rate", None)
        if fr is not None:
            try:
                return float(fr)
            except Exception:
                pass
        # Priority 2: env var override (useful for testing)
        env_key = f"FR_LATEST_{symbol.upper()}"
        env_val = os.getenv(env_key, "")
        if env_val:
            try:
                return float(env_val)
            except Exception:
                pass
        # Priority 3: latest JSON snapshot written by funding_rate_fetcher cron/sidecar
        try:
            rates = _read_latest_funding_file()
            if symbol.upper() in rates:
                return float(rates[symbol.upper()])
        except Exception:
            pass
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
        _ = o
        sym = str(getattr(store, "symbol", "")).upper()

        # ── Guards ─────────────────────────────────────────────────────────────
        if self._allow and sym not in self._allow:
            return None
        if not self._in_session(ts_ms):
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        # Accumulate bars
        self._closes.append(float(c))
        self._highs.append(float(h))
        self._lows.append(float(l))
        self._vols.append(float(v))

        min_bars = max(self.cfg.ema_period + 5, self.cfg.rsi_period + 5)
        if len(self._closes) < min_bars:
            return None

        # ── Funding rate check ─────────────────────────────────────────────────
        funding_rate = self._get_funding_rate(store, sym)
        if funding_rate is None:
            return None   # No funding data — skip

        abs_fr = abs(funding_rate)
        if abs_fr < self.cfg.fr_threshold:
            return None   # Funding not extreme enough

        # ── Indicators ────────────────────────────────────────────────────────
        ema_val = _ema(self._closes[-(self.cfg.ema_period * 2):], self.cfg.ema_period)
        atr_val = _atr(self._highs, self._lows, self._closes, 14)
        rsi_val = _rsi(self._closes, self.cfg.rsi_period)
        vol_usdt = float(v) * c

        if not (math.isfinite(ema_val) and math.isfinite(atr_val)
                and math.isfinite(rsi_val) and atr_val > 0):
            return None

        # Volume filter
        if self.cfg.min_volume_usdt > 0 and vol_usdt < self.cfg.min_volume_usdt:
            return None

        # ── Signal logic ───────────────────────────────────────────────────────
        # SHORT signal: extreme positive funding + price extended above EMA + RSI overbought
        if (self.cfg.allow_shorts
                and funding_rate >= self.cfg.fr_threshold
                and c > ema_val * (1.0 + self.cfg.ext_pct)
                and rsi_val >= self.cfg.rsi_ob):

            entry = c
            sl    = entry + self.cfg.sl_atr_mult * atr_val
            tp    = entry - self.cfg.tp_atr_mult * atr_val
            if tp <= 0:
                return None

            self._cooldown = self.cfg.cooldown_bars
            reason = (
                f"funding_short|FR={funding_rate*100:.4f}%"
                f"|RSI={rsi_val:.1f}|ext={(c/ema_val-1)*100:.2f}%"
            )
            return TradeSignal(
                strategy=self.name,
                symbol=sym,
                side="short",
                entry=entry,
                sl=sl,
                tp=tp,
                be_trigger_rr=0.0,
                trailing_atr_mult=0.0,
                time_stop_bars=self.cfg.time_stop_bars,
                reason=reason,
            )

        # LONG signal: extreme negative funding + price below EMA + RSI oversold
        if (self.cfg.allow_longs
                and funding_rate <= -self.cfg.fr_threshold
                and c < ema_val * (1.0 - self.cfg.ext_pct)
                and rsi_val <= self.cfg.rsi_os):

            entry = c
            sl    = entry - self.cfg.sl_atr_mult * atr_val
            tp    = entry + self.cfg.tp_atr_mult * atr_val
            if sl <= 0:
                return None

            self._cooldown = self.cfg.cooldown_bars
            reason = (
                f"funding_long|FR={funding_rate*100:.4f}%"
                f"|RSI={rsi_val:.1f}|ext={(c/ema_val-1)*100:.2f}%"
            )
            return TradeSignal(
                strategy=self.name,
                symbol=sym,
                side="long",
                entry=entry,
                sl=sl,
                tp=tp,
                be_trigger_rr=0.0,
                trailing_atr_mult=0.0,
                time_stop_bars=self.cfg.time_stop_bars,
                reason=reason,
            )

        return None

===== END FILE: strategies/funding_rate_reversion_v1.py =====
====================================================================================================
