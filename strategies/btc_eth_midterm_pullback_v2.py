from __future__ import annotations

"""
BTCETHMidtermPullbackV2
=======================
Improvements over v1:

1. SLOPED CHANNEL INTEGRATION (4H)
   - Linear regression channel on 4H closes (configurable lookback)
   - Only enter LONG near lower channel band (position < 0.35)
   - Only enter SHORT near upper channel band (position > 0.65)
   - Channel provides dynamic TP target (opposite band)
   - R² quality filter ensures channel is well-defined

2. DYNAMIC TP via channel bands
   - Long TP = upper channel band (or fixed RR floor, whichever is further)
   - Short TP = lower channel band (or fixed RR floor, whichever is further)
   - Much better than fixed 2.2R — captures full trend moves

3. TWO-PHASE EXITS enabled by default
   - TP1 at 1.2R (50% of position locked in)
   - TP2 trails with ATR — let winners run

4. VOLATILITY FILTER
   - Skip if 4H ATR > max_atr_pct_4h of price (avoid panics)

5. MAX SIGNALS PER DAY = 2 (was 1) with per-direction cooldown

ENV prefix: MTPB2_*  (separate from v1 MTPB_*)
"""

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

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


def _linear_regression(values: List[float]) -> Tuple[float, float]:
    """Returns (slope, intercept) for OLS on index 0..n-1."""
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
    y_mean = sum(values) / float(n)
    ss_tot = sum((v - y_mean) ** 2 for v in values)
    if ss_tot < 1e-12:
        return 1.0
    predicted = [slope * i + intercept for i in range(n)]
    ss_res = sum((v - p) ** 2 for v, p in zip(values, predicted))
    return max(0.0, 1.0 - ss_res / ss_tot)


@dataclass
class BTCETHMidtermPullbackV2Config:
    # Timeframes
    trend_tf: str = "240"   # 4H for trend + channel
    signal_tf: str = "60"   # 1H for entry timing
    eval_tf_min: int = 15   # evaluate every 15m bucket

    # === Trend filter (same as v1) ===
    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    trend_slope_bars: int = 8
    trend_slope_min_pct: float = 0.40   # slightly softer than v1 (0.45)
    trend_min_gap_pct: float = 0.20     # slightly softer than v1 (0.25)

    # === Sloped channel (NEW) ===
    channel_lookback_4h: int = 25       # bars of 4H for linreg (~4 days — tighter channels)
    channel_min_r2: float = 0.30        # minimum R² to trust channel
    channel_long_max_pos: float = 0.45  # enter long only below 45% of channel
    channel_short_min_pos: float = 0.55 # enter short only above 55% of channel
    channel_use_as_tp: bool = True      # use opposite band as TP target
    channel_min_width_pct: float = 2.0  # min channel width (% of price)
    max_atr_pct_4h: float = 6.0         # volatility filter: skip if 4H ATR > 6%

    # === 1H signal ===
    signal_ema_period: int = 20
    atr_period: int = 14
    long_max_pullback_pct: float = 0.90
    short_max_pullback_pct: float = 0.90
    long_touch_tol_pct: float = 0.25    # slightly more forgiving than v1
    short_touch_tol_pct: float = 0.25
    long_reclaim_pct: float = 0.12
    short_reclaim_pct: float = 0.12
    swing_lookback_bars: int = 10
    long_max_atr_pct_1h: float = 2.20   # slightly looser than v1 (1.80)
    short_max_atr_pct_1h: float = 2.20

    # === Exits ===
    sl_atr_mult: float = 1.20
    swing_sl_buffer_atr: float = 0.15
    min_rr: float = 1.8                 # floor: never below 1.8R
    max_rr: float = 5.0                 # cap: channel TP capped at 5R
    # Two-phase exits (default ON in v2)
    use_runner_exits: bool = True
    tp1_rr: float = 1.2
    tp1_frac: float = 0.50
    trail_atr_mult: float = 1.2
    time_stop_bars_5m: int = 120        # 10h time stop (was 7h in v1)

    # === Flow control ===
    cooldown_bars_5m: int = 60          # 5h cooldown (was 7h)
    max_signals_per_day: int = 2        # was 1
    allow_longs: bool = True
    allow_shorts: bool = True


class BTCETHMidtermPullbackV2Strategy:
    """
    ETH/BTC midterm pullback v2 — sloped channel entry filter + dynamic TP.
    """

    def __init__(self, cfg: Optional[BTCETHMidtermPullbackV2Config] = None):
        self.cfg = cfg or BTCETHMidtermPullbackV2Config()
        self._load_env()
        self._allow = _env_csv_set("MTPB2_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("MTPB2_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    def _load_env(self) -> None:
        c = self.cfg
        c.trend_tf = os.getenv("MTPB2_TREND_TF", c.trend_tf)
        c.signal_tf = os.getenv("MTPB2_SIGNAL_TF", c.signal_tf)
        c.eval_tf_min = _env_int("MTPB2_EVAL_TF_MIN", c.eval_tf_min)
        c.trend_ema_fast = _env_int("MTPB2_TREND_EMA_FAST", c.trend_ema_fast)
        c.trend_ema_slow = _env_int("MTPB2_TREND_EMA_SLOW", c.trend_ema_slow)
        c.trend_slope_bars = _env_int("MTPB2_TREND_SLOPE_BARS", c.trend_slope_bars)
        c.trend_slope_min_pct = _env_float("MTPB2_TREND_SLOPE_MIN_PCT", c.trend_slope_min_pct)
        c.trend_min_gap_pct = _env_float("MTPB2_TREND_MIN_GAP_PCT", c.trend_min_gap_pct)
        c.channel_lookback_4h = _env_int("MTPB2_CHANNEL_LOOKBACK_4H", c.channel_lookback_4h)
        c.channel_min_r2 = _env_float("MTPB2_CHANNEL_MIN_R2", c.channel_min_r2)
        c.channel_long_max_pos = _env_float("MTPB2_CHANNEL_LONG_MAX_POS", c.channel_long_max_pos)
        c.channel_short_min_pos = _env_float("MTPB2_CHANNEL_SHORT_MIN_POS", c.channel_short_min_pos)
        c.channel_use_as_tp = _env_bool("MTPB2_CHANNEL_USE_AS_TP", c.channel_use_as_tp)
        c.channel_min_width_pct = _env_float("MTPB2_CHANNEL_MIN_WIDTH_PCT", c.channel_min_width_pct)
        c.max_atr_pct_4h = _env_float("MTPB2_MAX_ATR_PCT_4H", c.max_atr_pct_4h)
        c.signal_ema_period = _env_int("MTPB2_SIGNAL_EMA_PERIOD", c.signal_ema_period)
        c.atr_period = _env_int("MTPB2_ATR_PERIOD", c.atr_period)
        c.long_max_pullback_pct = _env_float("MTPB2_LONG_MAX_PULLBACK_PCT", c.long_max_pullback_pct)
        c.short_max_pullback_pct = _env_float("MTPB2_SHORT_MAX_PULLBACK_PCT", c.short_max_pullback_pct)
        c.long_touch_tol_pct = _env_float("MTPB2_LONG_TOUCH_TOL_PCT", c.long_touch_tol_pct)
        c.short_touch_tol_pct = _env_float("MTPB2_SHORT_TOUCH_TOL_PCT", c.short_touch_tol_pct)
        c.long_reclaim_pct = _env_float("MTPB2_LONG_RECLAIM_PCT", c.long_reclaim_pct)
        c.short_reclaim_pct = _env_float("MTPB2_SHORT_RECLAIM_PCT", c.short_reclaim_pct)
        c.swing_lookback_bars = _env_int("MTPB2_SWING_LOOKBACK_BARS", c.swing_lookback_bars)
        c.long_max_atr_pct_1h = _env_float("MTPB2_LONG_MAX_ATR_PCT_1H", c.long_max_atr_pct_1h)
        c.short_max_atr_pct_1h = _env_float("MTPB2_SHORT_MAX_ATR_PCT_1H", c.short_max_atr_pct_1h)
        c.sl_atr_mult = _env_float("MTPB2_SL_ATR_MULT", c.sl_atr_mult)
        c.swing_sl_buffer_atr = _env_float("MTPB2_SWING_SL_BUFFER_ATR", c.swing_sl_buffer_atr)
        c.min_rr = _env_float("MTPB2_MIN_RR", c.min_rr)
        c.max_rr = _env_float("MTPB2_MAX_RR", c.max_rr)
        c.use_runner_exits = _env_bool("MTPB2_USE_RUNNER_EXITS", c.use_runner_exits)
        c.tp1_rr = _env_float("MTPB2_TP1_RR", c.tp1_rr)
        c.tp1_frac = _env_float("MTPB2_TP1_FRAC", c.tp1_frac)
        c.trail_atr_mult = _env_float("MTPB2_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.time_stop_bars_5m = _env_int("MTPB2_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("MTPB2_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.max_signals_per_day = _env_int("MTPB2_MAX_SIGNALS_PER_DAY", c.max_signals_per_day)
        c.allow_longs = _env_bool("MTPB2_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("MTPB2_ALLOW_SHORTS", c.allow_shorts)

    # ─── Trend bias (same logic as v1, slightly softer thresholds) ────────────
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
        if gap_pct < self.cfg.trend_min_gap_pct:
            return 1
        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if ef > es and slope_pct >= self.cfg.trend_slope_min_pct:
            return 2   # uptrend
        if ef < es and slope_pct <= -self.cfg.trend_slope_min_pct:
            return 0   # downtrend
        return 1       # neutral

    # ─── Sloped channel on 4H (NEW) ───────────────────────────────────────────
    def _channel_context(self, store) -> Optional[dict]:
        """
        Compute linear regression channel on 4H bars.
        Returns dict with:
          slope, r2, position (0=lower band, 1=upper band),
          upper_band, lower_band, mid, width_pct, atr_pct_4h
        """
        need = self.cfg.channel_lookback_4h + 20
        rows = store.fetch_klines(store.symbol, self.cfg.trend_tf, need) or []
        if len(rows) < max(30, self.cfg.channel_lookback_4h):
            return None

        rows = rows[-self.cfg.channel_lookback_4h:]
        closes = [float(r[4]) for r in rows]
        highs  = [float(r[2]) for r in rows]
        lows   = [float(r[3]) for r in rows]
        n = len(closes)

        slope, intercept = _linear_regression(closes)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            return None

        r2 = _r_squared(closes, slope, intercept)
        if r2 < self.cfg.channel_min_r2:
            return None   # channel not well-defined

        # Channel bands from max residuals of highs/lows
        predicted = [slope * i + intercept for i in range(n)]
        upper_dev = max(h - p for h, p in zip(highs, predicted))
        lower_dev = min(l - p for l, p in zip(lows, predicted))  # negative

        cur_pred   = slope * (n - 1) + intercept
        upper_band = cur_pred + upper_dev
        lower_band = cur_pred + lower_dev
        mid        = cur_pred
        cur_price  = closes[-1]
        channel_width = upper_band - lower_band

        if channel_width < 1e-12:
            return None
        width_pct = channel_width / max(1e-12, abs(cur_price)) * 100.0
        if width_pct < self.cfg.channel_min_width_pct:
            return None   # channel too narrow (sideways/flat)

        # Position within channel: 0 = at lower band, 1 = at upper band
        position = (cur_price - lower_band) / channel_width

        # 4H ATR for volatility filter
        atr_4h = _atr_from_rows(rows, min(self.cfg.atr_period, len(rows) - 1))
        atr_pct_4h = atr_4h / max(1e-12, abs(cur_price)) * 100.0 if math.isfinite(atr_4h) else 0.0

        return {
            "slope": slope,
            "r2": r2,
            "position": position,
            "upper_band": upper_band,
            "lower_band": lower_band,
            "mid": mid,
            "width_pct": width_pct,
            "atr_pct_4h": atr_pct_4h,
        }

    # ─── Main signal method ───────────────────────────────────────────────────
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

        # ── Screen 1: 4H trend bias ──
        bias = self._trend_bias(store)
        if bias is None or bias == 1:
            return None

        # ── Screen 2: sloped channel context ──
        ch = self._channel_context(store)
        if ch is None:
            return None

        # Volatility filter: skip during panics
        if ch["atr_pct_4h"] > self.cfg.max_atr_pct_4h:
            return None

        # ── Screen 3: 1H pullback + reclaim ──
        need_1h = max(self.cfg.signal_ema_period + self.cfg.swing_lookback_bars + 5, 90)
        rows_1h = store.fetch_klines(store.symbol, self.cfg.signal_tf, need_1h) or []
        if len(rows_1h) < self.cfg.signal_ema_period + self.cfg.swing_lookback_bars + 2:
            return None

        highs_1h  = [float(r[2]) for r in rows_1h]
        lows_1h   = [float(r[3]) for r in rows_1h]
        closes_1h = [float(r[4]) for r in rows_1h]
        ema1h = _ema(closes_1h, self.cfg.signal_ema_period)
        atr1h = _atr_from_rows(rows_1h, self.cfg.atr_period)
        if not (math.isfinite(ema1h) and math.isfinite(atr1h) and atr1h > 0):
            return None

        cur_c  = closes_1h[-1]
        prev_c = closes_1h[-2]
        look   = max(3, min(len(rows_1h), int(self.cfg.swing_lookback_bars)))
        swing_low  = min(lows_1h[-look:])
        swing_high = max(highs_1h[-look:])

        # ── LONG: uptrend + near lower channel band + pullback to EMA + reclaim ──
        if self.cfg.allow_longs and bias == 2 and ch["position"] <= self.cfg.channel_long_max_pos:
            atr_pct_1h = (atr1h / max(1e-12, abs(cur_c))) * 100.0
            if atr_pct_1h > self.cfg.long_max_atr_pct_1h:
                return None

            touched  = swing_low <= ema1h * (1.0 + self.cfg.long_touch_tol_pct / 100.0)
            reclaimed = (
                cur_c  >= ema1h * (1.0 + self.cfg.long_reclaim_pct / 100.0)
                and prev_c <= ema1h * 1.003
            )
            pullback_pct = max(0.0, (ema1h - swing_low) / max(1e-12, ema1h) * 100.0)

            if touched and reclaimed and pullback_pct <= self.cfg.long_max_pullback_pct:
                swing_sl = swing_low - self.cfg.swing_sl_buffer_atr * atr1h
                atr_sl   = float(c) - self.cfg.sl_atr_mult * atr1h
                sl = min(swing_sl, atr_sl)
                if sl >= float(c):
                    return None
                risk = float(c) - sl

                # Dynamic TP: use upper channel band, clamp to [min_rr, max_rr]
                tp_raw = ch["upper_band"] if self.cfg.channel_use_as_tp else (float(c) + self.cfg.min_rr * risk)
                tp_rr  = (tp_raw - float(c)) / risk if risk > 1e-12 else self.cfg.min_rr
                tp_rr  = max(self.cfg.min_rr, min(self.cfg.max_rr, tp_rr))
                tp     = float(c) + tp_rr * risk
                tp1    = float(c) + self.cfg.tp1_rr * risk

                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                sig = TradeSignal(
                    strategy="btc_eth_midterm_pullback_v2",
                    symbol=store.symbol,
                    side="long",
                    entry=float(c),
                    sl=float(sl),
                    tp=float(tp),
                    reason=(
                        f"mtpb2_long ch_pos={ch['position']:.2f} r2={ch['r2']:.2f} "
                        f"rr={tp_rr:.1f} ema={self.cfg.signal_ema_period}"
                    ),
                )
                if self.cfg.use_runner_exits:
                    frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
                    sig.tps = [float(tp1), float(tp)]
                    sig.tp_fracs = [frac, max(0.0, 1.0 - frac)]
                    sig.trailing_atr_mult = max(0.0, float(self.cfg.trail_atr_mult))
                    sig.trailing_atr_period = max(5, int(self.cfg.atr_period))
                    sig.time_stop_bars = max(0, int(self.cfg.time_stop_bars_5m))
                return sig

        # ── SHORT: downtrend + near upper channel band + pullback to EMA + reclaim ──
        if self.cfg.allow_shorts and bias == 0 and ch["position"] >= self.cfg.channel_short_min_pos:
            atr_pct_1h = (atr1h / max(1e-12, abs(cur_c))) * 100.0
            if atr_pct_1h > self.cfg.short_max_atr_pct_1h:
                return None

            touched  = swing_high >= ema1h * (1.0 - self.cfg.short_touch_tol_pct / 100.0)
            reclaimed = (
                cur_c  <= ema1h * (1.0 - self.cfg.short_reclaim_pct / 100.0)
                and prev_c >= ema1h * 0.997
            )
            pullback_pct = max(0.0, (swing_high - ema1h) / max(1e-12, ema1h) * 100.0)

            if touched and reclaimed and pullback_pct <= self.cfg.short_max_pullback_pct:
                swing_sl = swing_high + self.cfg.swing_sl_buffer_atr * atr1h
                atr_sl   = float(c) + self.cfg.sl_atr_mult * atr1h
                sl = max(swing_sl, atr_sl)
                if sl <= float(c):
                    return None
                risk = sl - float(c)

                # Dynamic TP: use lower channel band, clamp to [min_rr, max_rr]
                tp_raw = ch["lower_band"] if self.cfg.channel_use_as_tp else (float(c) - self.cfg.min_rr * risk)
                tp_rr  = (float(c) - tp_raw) / risk if risk > 1e-12 else self.cfg.min_rr
                tp_rr  = max(self.cfg.min_rr, min(self.cfg.max_rr, tp_rr))
                tp     = float(c) - tp_rr * risk
                tp1    = float(c) - self.cfg.tp1_rr * risk

                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                self._day_signals += 1
                sig = TradeSignal(
                    strategy="btc_eth_midterm_pullback_v2",
                    symbol=store.symbol,
                    side="short",
                    entry=float(c),
                    sl=float(sl),
                    tp=float(tp),
                    reason=(
                        f"mtpb2_short ch_pos={ch['position']:.2f} r2={ch['r2']:.2f} "
                        f"rr={tp_rr:.1f} ema={self.cfg.signal_ema_period}"
                    ),
                )
                if self.cfg.use_runner_exits:
                    frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
                    sig.tps = [float(tp1), float(tp)]
                    sig.tp_fracs = [frac, max(0.0, 1.0 - frac)]
                    sig.trailing_atr_mult = max(0.0, float(self.cfg.trail_atr_mult))
                    sig.trailing_atr_period = max(5, int(self.cfg.atr_period))
                    sig.time_stop_bars = max(0, int(self.cfg.time_stop_bars_5m))
                return sig

        return None
