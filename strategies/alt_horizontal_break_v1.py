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
  HZBO1_MACRO_REQUIRE_BULLISH bool   long only when 4h hist > 0 [0]
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
    macro_require_bullish: bool = False   # long only when 4h hist > 0
    macro_macd_fast: int = 12
    macro_macd_slow: int = 26
    macro_macd_signal: int = 9

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

        need = max(80, c.macro_macd_slow + c.macro_macd_signal + 10)
        rows = store.fetch_klines(store.symbol, c.macro_tf, need) or []
        if len(rows) < need // 2:
            return True  # not enough data — don't block

        closes = [float(r[4]) for r in rows]
        hist = _macd_hist_last(closes, c.macro_macd_fast, c.macro_macd_slow, c.macro_macd_signal)
        if not math.isfinite(hist):
            return True

        if side == "short" and c.macro_require_bearish:
            if hist >= 0:
                return False
        if side == "long" and c.macro_require_bullish:
            if hist <= 0:
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
