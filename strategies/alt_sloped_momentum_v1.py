"""
alt_sloped_momentum_v1 (ASM1) — Sloped channel breakout momentum rider

Detects when price cleanly breaks out of a well-defined sloped regression
channel and immediately enters in the breakout direction to capture the
subsequent multi-day momentum move.

Key design differences vs sloped_break_retest_v1:
  1. NO RETEST WAIT — enters on the breakout bar's close. Captures moves
     that never retest, which is typical of the strongest breakouts.
  2. CORRECT CHANNEL BANDS — upper band uses max(high residuals), lower
     band uses min(low residuals). This is how a human would draw the channel:
     the lines contain ALL price action including wicks, not just closes.
  3. MULTI-DAY HOLD — trailing stop is active from bar 1 with configurable
     activation. Default time_stop ~5 days to ride full momentum cycles.
  4. STRONGER VOLUME REQUIREMENT — vol_mult defaults to 1.5× average volume.

Channel construction
--------------------
  1. Fetch last signal_lookback bars of 1H data.
  2. Compute linear regression of CLOSES (centerline slope).
  3. Upper band = regression_line + max(high[i] - regression[i]) for all i.
  4. Lower band = regression_line + min(low[i]  - regression[i]) for all i.
  5. This envelope contains the full price range.

Entry logic
-----------
  LONG BREAKOUT:
    - Previous close ≤ upper band (was inside channel)
    - Current close  > upper band + breakout_ext_atr * ATR (clear break)
    - Breakout candle is bullish (close > open)
    - Body fraction ≥ min_body_frac
    - Volume ≥ vol_mult × moving average
    - R² ≥ min_r2 (channel is well-defined)
    - Channel slope within [min_slope_pct, max_slope_pct] pct/day
    - EMA trend filter: optional (ema_fast > ema_slow for longs)

  SHORT BREAKOUT:
    - Previous close ≥ lower band
    - Current close  < lower band - breakout_ext_atr * ATR
    - Candle bearish, body fraction OK, volume OK

Exit plan
---------
  - TP1: tp1_rr × risk (default 1.5R), close tp1_frac of position (40%)
  - TP2: tp2_rr × risk (default 3.5R), close remainder
  - Trailing stop: trail_atr_mult * ATR, arms after trail_activate_rr × risk
  - Break-even: at be_trigger_rr × risk (default 1.0R)
  - Time stop: time_stop_bars_5m 5m bars (default 1440 = ~5 days)
  - Cooldown: cooldown_bars_5m (default 72 = 6h to prevent re-entry)

Philosophy
----------
The breakout of a sloped channel signals that the market is breaking out
of an established trend structure — price was respecting the channel angle
for weeks and is now moving in a NEW direction with force. The best trades
here are the ones that never look back. A tight trailing stop lets winners run
while protecting against the false breakouts.

Environment variables (ASM1_ prefix)
--------------------------------------
  ASM1_SYMBOL_ALLOWLIST     csv    symbols to trade
  ASM1_SIGNAL_TF            str    kline timeframe [60]
  ASM1_SIGNAL_LOOKBACK      int    bars to fetch for channel [120]
  ASM1_ATR_PERIOD           int    ATR period [14]
  ASM1_VOL_PERIOD           int    volume average period [20]
  ASM1_MIN_CHANNEL_WIDTH_PCT float min channel width % of price [3.0]
  ASM1_MAX_CHANNEL_WIDTH_PCT float max channel width % of price [25.0]
  ASM1_MIN_SLOPE_PCT        float  min abs slope pct/day [0.05]
  ASM1_MAX_SLOPE_PCT        float  max abs slope pct/day [4.0]
  ASM1_MIN_R2               float  min R² of regression [0.30]
  ASM1_BREAKOUT_EXT_ATR     float  min close extension beyond band [0.15]
  ASM1_MIN_BODY_FRAC        float  min body fraction [0.35]
  ASM1_VOL_MULT             float  min volume vs avg [1.50]
  ASM1_USE_TREND_FILTER     bool   require EMA trend alignment [1]
  ASM1_TREND_EMA_FAST       int    fast EMA period [20]
  ASM1_TREND_EMA_SLOW       int    slow EMA period [50]
  ASM1_ALLOW_LONGS          bool   enable long breakouts [1]
  ASM1_ALLOW_SHORTS         bool   enable short breakouts [1]
  ASM1_SL_ATR_MULT          float  SL distance below breakout band [1.20]
  ASM1_TP1_RR               float  TP1 R-multiple [1.50]
  ASM1_TP2_RR               float  TP2 R-multiple [3.50]
  ASM1_TP1_FRAC             float  fraction closed at TP1 [0.40]
  ASM1_BE_TRIGGER_RR        float  break-even trigger R [1.00]
  ASM1_BE_LOCK_RR           float  lock-in R at BE [0.05]
  ASM1_TRAIL_ATR_MULT       float  trailing ATR multiplier [1.80]
  ASM1_TRAIL_ACTIVATE_RR    float  trailing activation R [1.00]
  ASM1_TIME_STOP_BARS_5M    int    time stop 5m bars [1440]
  ASM1_COOLDOWN_BARS_5M     int    cooldown 5m bars [72]
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
# Indicators
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


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _linear_regression(values: List[float]) -> Tuple[float, float]:
    """Return (slope, intercept) of OLS regression on values indexed 0..n-1."""
    n = len(values)
    if n < 2:
        return float("nan"), float("nan")
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / float(n)
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den <= 1e-12:
        return 0.0, y_mean
    m = num / den
    b = y_mean - m * x_mean
    return m, b


def _r_squared(values: List[float], slope: float, intercept: float) -> float:
    n = len(values)
    if n < 2:
        return float("nan")
    y_mean = sum(values) / float(n)
    ss_tot = sum((v - y_mean) ** 2 for v in values)
    if ss_tot <= 1e-12:
        return 1.0
    ss_res = sum((v - (slope * i + intercept)) ** 2 for i, v in enumerate(values))
    return max(0.0, 1.0 - ss_res / ss_tot)


def _channel_bands(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    slope: float,
    intercept: float,
) -> Tuple[float, float, float, float]:
    """Compute channel bands using high/low residuals (not close residuals).
    Returns (upper_off, lower_off, upper_now, lower_now) where:
      upper_off = max(high[i] - fit[i])   — max wick above regression
      lower_off = min(low[i]  - fit[i])   — min wick below regression
      upper_now / lower_now = projected to the last (current) bar index.
    """
    n = len(closes)
    fit = [slope * i + intercept for i in range(n)]
    upper_off = max(highs[i] - fit[i] for i in range(n))
    lower_off = min(lows[i] - fit[i] for i in range(n))
    upper_now = fit[-1] + upper_off
    lower_now = fit[-1] + lower_off
    return upper_off, lower_off, upper_now, lower_now


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class AltSlopedMomentumV1Config:
    signal_tf: str = "60"
    signal_lookback: int = 120
    atr_period: int = 14
    vol_period: int = 20

    # Channel quality
    min_channel_width_pct: float = 3.0
    max_channel_width_pct: float = 25.0
    min_slope_pct: float = 0.05   # pct/day — below this = horizontal (use ARF1)
    max_slope_pct: float = 4.0    # above this = too chaotic
    min_r2: float = 0.30          # R² of close regression (structure quality)

    # Entry confirmation
    breakout_ext_atr: float = 0.15  # close must exceed band by this many ATR
    min_body_frac: float = 0.35
    vol_mult: float = 1.50          # volume must be this × avg

    # Trend filter (EMA alignment)
    use_trend_filter: bool = True
    trend_ema_fast: int = 20
    trend_ema_slow: int = 50

    # Trade management
    sl_atr_mult: float = 1.20    # SL below upper band (long) / above lower band (short)
    tp1_rr: float = 1.50
    tp2_rr: float = 3.50
    tp1_frac: float = 0.40
    be_trigger_rr: float = 1.00
    be_lock_rr: float = 0.05
    trail_atr_mult: float = 1.80  # aggressive trailing for momentum
    trail_activate_rr: float = 1.00
    time_stop_bars_5m: int = 1440   # ~5 days
    cooldown_bars_5m: int = 72      # 6h cooldown

    allow_longs: bool = True
    allow_shorts: bool = True


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class AltSlopedMomentumV1Strategy:
    """Immediate breakout entry from sloped regression channel with trailing hold."""

    def __init__(self, cfg: Optional[AltSlopedMomentumV1Config] = None):
        self.cfg = cfg or AltSlopedMomentumV1Config()
        self._load_env()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._allow: set = set()
        self._deny: set = set()
        self._refresh_lists()

    def _load_env(self) -> None:
        c = self.cfg
        c.signal_tf = os.getenv("ASM1_SIGNAL_TF", c.signal_tf)
        c.signal_lookback = _env_int("ASM1_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("ASM1_ATR_PERIOD", c.atr_period)
        c.vol_period = _env_int("ASM1_VOL_PERIOD", c.vol_period)
        c.min_channel_width_pct = _env_float("ASM1_MIN_CHANNEL_WIDTH_PCT", c.min_channel_width_pct)
        c.max_channel_width_pct = _env_float("ASM1_MAX_CHANNEL_WIDTH_PCT", c.max_channel_width_pct)
        c.min_slope_pct = _env_float("ASM1_MIN_SLOPE_PCT", c.min_slope_pct)
        c.max_slope_pct = _env_float("ASM1_MAX_SLOPE_PCT", c.max_slope_pct)
        c.min_r2 = _env_float("ASM1_MIN_R2", c.min_r2)
        c.breakout_ext_atr = _env_float("ASM1_BREAKOUT_EXT_ATR", c.breakout_ext_atr)
        c.min_body_frac = _env_float("ASM1_MIN_BODY_FRAC", c.min_body_frac)
        c.vol_mult = _env_float("ASM1_VOL_MULT", c.vol_mult)
        c.use_trend_filter = _env_bool("ASM1_USE_TREND_FILTER", c.use_trend_filter)
        c.trend_ema_fast = _env_int("ASM1_TREND_EMA_FAST", c.trend_ema_fast)
        c.trend_ema_slow = _env_int("ASM1_TREND_EMA_SLOW", c.trend_ema_slow)
        c.sl_atr_mult = _env_float("ASM1_SL_ATR_MULT", c.sl_atr_mult)
        c.tp1_rr = _env_float("ASM1_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("ASM1_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("ASM1_TP1_FRAC", c.tp1_frac)
        c.be_trigger_rr = _env_float("ASM1_BE_TRIGGER_RR", c.be_trigger_rr)
        c.be_lock_rr = _env_float("ASM1_BE_LOCK_RR", c.be_lock_rr)
        c.trail_atr_mult = _env_float("ASM1_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_activate_rr = _env_float("ASM1_TRAIL_ACTIVATE_RR", c.trail_activate_rr)
        c.time_stop_bars_5m = _env_int("ASM1_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("ASM1_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_longs = _env_bool("ASM1_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("ASM1_ALLOW_SHORTS", c.allow_shorts)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set(
            "ASM1_SYMBOL_ALLOWLIST",
            "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT,XRPUSDT",
        )
        self._deny = _env_csv_set("ASM1_SYMBOL_DENYLIST")

    def _trend_ok_long(self, closes: List[float]) -> bool:
        """EMA fast > EMA slow = uptrend context for long breakout."""
        if not self.cfg.use_trend_filter:
            return True
        if len(closes) < self.cfg.trend_ema_slow + 5:
            return True  # not enough data → allow
        ef = _ema(closes, self.cfg.trend_ema_fast)
        es = _ema(closes, self.cfg.trend_ema_slow)
        return math.isfinite(ef) and math.isfinite(es) and ef >= es

    def _trend_ok_short(self, closes: List[float]) -> bool:
        """EMA fast < EMA slow = downtrend context for short breakout."""
        if not self.cfg.use_trend_filter:
            return True
        if len(closes) < self.cfg.trend_ema_slow + 5:
            return True
        ef = _ema(closes, self.cfg.trend_ema_fast)
        es = _ema(closes, self.cfg.trend_ema_slow)
        return math.isfinite(ef) and math.isfinite(es) and ef <= es

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
        vols = [float(r[5]) if len(r) > 5 and r[5] not in (None, "", "nan") else 0.0 for r in rows]

        atr = _atr_from_rows(rows, self.cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            return None

        cur = closes[-1]
        prev_close = closes[-2]
        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        if cur <= 0:
            return None

        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur - cur_open) / bar_range

        # ── Volume check ─────────────────────────────────────────────────────
        hist_vols = [x for x in vols[-self.cfg.vol_period - 1:-1] if math.isfinite(x) and x > 0]
        vol_avg = sum(hist_vols) / len(hist_vols) if hist_vols else 0.0
        vol_ok = vol_avg <= 0 or (math.isfinite(vols[-1]) and vols[-1] >= vol_avg * self.cfg.vol_mult)

        # ── Channel construction ──────────────────────────────────────────────
        # Use history EXCLUDING current bar to build channel structure
        hist_closes = closes[:-1]
        hist_highs = highs[:-1]
        hist_lows = lows[:-1]
        n_hist = len(hist_closes)
        if n_hist < max(20, self.cfg.signal_lookback - 5):
            return None

        slope, intercept = _linear_regression(hist_closes)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            return None

        r2 = _r_squared(hist_closes, slope, intercept)
        if r2 < self.cfg.min_r2:
            return None

        # Project channel to current bar (index = n_hist, since hist has n-1 bars)
        fit_hist = [slope * i + intercept for i in range(n_hist)]
        upper_off = max(hist_highs[i] - fit_hist[i] for i in range(n_hist))
        lower_off = min(hist_lows[i] - fit_hist[i] for i in range(n_hist))
        fit_cur = slope * n_hist + intercept
        upper_now = fit_cur + upper_off
        lower_now = fit_cur + lower_off

        width = upper_now - lower_now
        if width <= 0:
            return None
        width_pct = width / max(1e-12, cur) * 100.0

        # Slope in pct/day (24 1H bars per day)
        price_ref = max(1e-12, abs(fit_cur))
        slope_pct_day = abs(slope) / price_ref * 100.0 * 24.0

        if width_pct < self.cfg.min_channel_width_pct or width_pct > self.cfg.max_channel_width_pct:
            return None
        if slope_pct_day < self.cfg.min_slope_pct or slope_pct_day > self.cfg.max_slope_pct:
            return None

        # ── LONG BREAKOUT ────────────────────────────────────────────────────
        if self.cfg.allow_longs:
            # Previous bar was inside channel; current bar breaks above upper
            was_inside = prev_close <= upper_now
            broke_up = cur > upper_now + self.cfg.breakout_ext_atr * atr
            bullish_candle = cur > cur_open
            long_ok = (
                was_inside
                and broke_up
                and bullish_candle
                and body_frac >= self.cfg.min_body_frac
                and vol_ok
                and self._trend_ok_long(closes)
            )
            if long_ok:
                # SL: below the upper band (which should now act as support)
                sl = upper_now - self.cfg.sl_atr_mult * atr
                risk = cur - sl
                if risk > 0:
                    tp1 = cur + self.cfg.tp1_rr * risk
                    tp2 = cur + self.cfg.tp2_rr * risk
                    sig = TradeSignal(
                        strategy="alt_sloped_momentum_v1",
                        symbol=store.symbol,
                        side="long",
                        entry=float(cur),
                        sl=float(sl),
                        tp=float(tp2),
                        tps=[float(tp1), float(tp2)],
                        tp_fracs=[
                            min(0.85, max(0.15, self.cfg.tp1_frac)),
                            max(0.10, 1.0 - min(0.85, max(0.15, self.cfg.tp1_frac))),
                        ],
                        be_trigger_rr=max(0.0, self.cfg.be_trigger_rr),
                        be_lock_rr=max(0.0, self.cfg.be_lock_rr),
                        trailing_atr_mult=max(0.0, self.cfg.trail_atr_mult),
                        trailing_atr_period=self.cfg.atr_period,
                        trail_activate_rr=max(0.0, self.cfg.trail_activate_rr),
                        time_stop_bars=max(0, self.cfg.time_stop_bars_5m),
                        reason=(
                            f"asm1_long_breakout "
                            f"upper={upper_now:.4f} ext={cur - upper_now:.4f} "
                            f"r2={r2:.2f} slope={slope_pct_day:.2f}%/d "
                            f"vol={vols[-1] / max(1, vol_avg):.1f}x"
                        ),
                    )
                    if sig.validate():
                        self._cooldown = max(0, self.cfg.cooldown_bars_5m)
                        return sig

        # ── SHORT BREAKOUT ───────────────────────────────────────────────────
        if self.cfg.allow_shorts:
            was_inside = prev_close >= lower_now
            broke_down = cur < lower_now - self.cfg.breakout_ext_atr * atr
            bearish_candle = cur < cur_open
            short_ok = (
                was_inside
                and broke_down
                and bearish_candle
                and body_frac >= self.cfg.min_body_frac
                and vol_ok
                and self._trend_ok_short(closes)
            )
            if short_ok:
                # SL: above the lower band (which should now act as resistance)
                sl = lower_now + self.cfg.sl_atr_mult * atr
                risk = sl - cur
                if risk > 0:
                    tp1 = cur - self.cfg.tp1_rr * risk
                    tp2 = cur - self.cfg.tp2_rr * risk
                    if tp2 > 0:
                        sig = TradeSignal(
                            strategy="alt_sloped_momentum_v1",
                            symbol=store.symbol,
                            side="short",
                            entry=float(cur),
                            sl=float(sl),
                            tp=float(tp2),
                            tps=[float(tp1), float(tp2)],
                            tp_fracs=[
                                min(0.85, max(0.15, self.cfg.tp1_frac)),
                                max(0.10, 1.0 - min(0.85, max(0.15, self.cfg.tp1_frac))),
                            ],
                            be_trigger_rr=max(0.0, self.cfg.be_trigger_rr),
                            be_lock_rr=max(0.0, self.cfg.be_lock_rr),
                            trailing_atr_mult=max(0.0, self.cfg.trail_atr_mult),
                            trailing_atr_period=self.cfg.atr_period,
                            trail_activate_rr=max(0.0, self.cfg.trail_activate_rr),
                            time_stop_bars=max(0, self.cfg.time_stop_bars_5m),
                            reason=(
                                f"asm1_short_breakout "
                                f"lower={lower_now:.4f} ext={lower_now - cur:.4f} "
                                f"r2={r2:.2f} slope={slope_pct_day:.2f}%/d "
                                f"vol={vols[-1] / max(1, vol_avg):.1f}x"
                            ),
                        )
                        if sig.validate():
                            self._cooldown = max(0, self.cfg.cooldown_bars_5m)
                            return sig

        return None
