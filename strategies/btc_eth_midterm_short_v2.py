from __future__ import annotations

"""BTC/ETH midterm SHORT-ONLY strategy v2 — 3-TF hierarchy (bear-market hardened).

Architecture
------------
* Screen 0 — Weekly macro gate (10080 min)
    EMA20 < EMA50 AND EMA50 trending down → confirmed weekly downtrend
    If weekly is flat/bullish → strategy is SILENT (no signal emitted)

* Screen 1 — Daily trend filter (1440 min)
    EMA50 < EMA200, EMA200 slope < -0.10%, gap ≥ 0.20%
    MACD histogram (12/26/9) negative for ≥ 3 consecutive daily bars
    Daily RSI(14) < 55 (not in a strong bull thrust)
    All three must agree → "daily_dn" bias

* Screen 2 — 4h pullback entry (240 min)
    Price rallies to 4h EMA20 zone, then rejects back below
    4h ATR% within quality window (0.40% – 3.50%)
    4h RSI(14) > 50 on the bar that touched EMA (confirms it was a real rally)

Why v2 over v1?
    v1 used only 2 TFs and had no MACD histogram confirmation on the daily, which
    allowed bearish-EMA crossovers but still-rising MACD to generate false shorts
    during distributional topping phases.  WF-22 on 2022-2024 showed 23/22 periods
    failing the PF>1.20 promotion gate (PF 0.71-0.85 depending on year).

    v2 adds:
      • Weekly macro Screen 0 (silences during weekly upswings / consolidation)
      • Daily MACD histogram gate (3 consecutive negative bars)
      • Daily RSI < 55 guard (avoid shorting into bull thrusts)
      • 4h RSI > 50 on pullback (entry only into confirmed distribution rallies)
      • min_trend_days: require downtrend to be established ≥ N daily bars
      • Tighter entry: rejection must close below EMA20 × (1 - 0.35%)

Env prefix : MTSV2_
Strategy name : btc_eth_midterm_short_v2
"""

import math
import os
from dataclasses import dataclass, field
from typing import List, Optional

from .signals import TradeSignal


# ─── helpers ──────────────────────────────────────────────────────────────────

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
    """Standard exponential moving average."""
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _ema_series(values: List[float], period: int) -> List[float]:
    """Return full EMA series for all bars in *values*."""
    if not values or period <= 0:
        return [float("nan")] * len(values)
    k = 2.0 / (period + 1.0)
    out: List[float] = []
    e = values[0]
    for v in values:
        e = v * k + e * (1.0 - k)
        out.append(e)
    return out


def _macd_histogram_series(closes: List[float], fast=12, slow=26, sig=9) -> List[float]:
    """Return the MACD histogram (MACD-line − signal-line) for every bar."""
    if len(closes) < slow + sig + 5:
        return [float("nan")] * len(closes)
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    # Signal line is EMA of MACD-line; seed from bar `slow` onward
    sig_series = [float("nan")] * len(closes)
    k = 2.0 / (sig + 1.0)
    start = slow
    e = macd_line[start]
    for i in range(start, len(closes)):
        e = macd_line[i] * k + e * (1.0 - k)
        sig_series[i] = e
    hist = [float("nan")] * len(closes)
    for i in range(start, len(closes)):
        if math.isfinite(macd_line[i]) and math.isfinite(sig_series[i]):
            hist[i] = macd_line[i] - sig_series[i]
    return hist


def _rsi(closes: List[float], period: int = 14) -> float:
    """Wilder RSI of the last *period* change bars."""
    if len(closes) < period + 2:
        return float("nan")
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(0.0, c) for c in changes[-period:]]
    losses = [max(0.0, -c) for c in changes[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _atr_from_rows(rows: List[list], period: int) -> float:
    if len(rows) < period + 1:
        return float("nan")
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    trs: List[float] = []
    for i in range(-period, 0):
        h = highs[i]
        lv = lows[i]
        pc = closes[i - 1]
        trs.append(max(h - lv, abs(h - pc), abs(lv - pc)))
    return sum(trs) / float(period) if trs else float("nan")


# ─── config ───────────────────────────────────────────────────────────────────

@dataclass
class BTCETHMidtermShortV2Config:
    # ── Screen 0: weekly macro gate ───────────────────────────────────────────
    weekly_tf: str = "10080"          # 1 week in minutes
    weekly_ema_fast: int = 20
    weekly_ema_slow: int = 50
    weekly_slope_bars: int = 3        # Bars to measure EMA50 slope
    weekly_slope_min_pct: float = 0.15  # |slope| < this → weekly is flat → abort
    weekly_enabled: bool = True       # Set MTSV2_WEEKLY_ENABLED=0 to bypass in debug

    # ── Screen 1: daily trend filter ──────────────────────────────────────────
    daily_tf: str = "1440"
    daily_ema_fast: int = 50
    daily_ema_slow: int = 200
    daily_slope_bars: int = 5
    daily_slope_min_pct: float = 0.10
    daily_min_gap_pct: float = 0.20   # EMA50/200 must be at least this far apart

    daily_macd_fast: int = 12
    daily_macd_slow: int = 26
    daily_macd_sig: int = 9
    daily_macd_consec_neg: int = 3    # Need ≥ 3 consecutive negative histogram bars

    daily_rsi_period: int = 14
    daily_rsi_max: float = 55.0       # Don't short if daily RSI is > 55 (bull thrust)

    min_trend_days: int = 5           # Downtrend must exist for ≥ N daily bars
                                      # (EMA50 continuously < EMA200)

    # ── Screen 2: 4h pullback / rejection entry ───────────────────────────────
    signal_tf: str = "240"            # 4h
    signal_ema_period: int = 20       # 4h EMA20 = the pullback target
    atr_period: int = 14

    # Entry quality window (4h ATR%)
    min_atr_pct_4h: float = 0.40     # Skip if market is too dead
    max_atr_pct_4h: float = 3.50     # Skip if market is too chaotic

    # Pullback / rejection geometry
    touch_tol_pct: float = 0.25      # ±0.25% zone around EMA20 counts as "touch"
    max_pullback_pct: float = 1.50   # Pullback above EMA by more than this → too extended
    reclaim_pct: float = 0.35        # Must close at least 0.35% BELOW EMA20 to confirm rejection
    swing_lookback_bars: int = 8     # Recent swing high lookback (in 4h bars)

    # 4h RSI filter
    signal_rsi_period: int = 14
    signal_rsi_min: float = 50.0     # 4h RSI must be > 50 on the touch bar (confirms rally)

    # ── Exit parameters ───────────────────────────────────────────────────────
    sl_atr_mult: float = 1.30        # SL = max(swing_high_with_buffer, entry + sl_atr_mult×ATR)
    swing_sl_buffer_atr: float = 0.20
    use_runner_exits: bool = True
    tp1_rr: float = 1.5
    tp2_rr: float = 3.0
    tp1_frac: float = 0.50
    trail_atr_mult: float = 1.20
    time_stop_bars_5m: int = 144     # 12h time stop

    # ── Throttling ────────────────────────────────────────────────────────────
    eval_tf_min: int = 60            # Re-evaluate at most once per hour
    cooldown_bars_5m: int = 144      # 12h cooldown per symbol
    max_signals_per_day: int = 1     # At most 1 short per symbol per day


# ─── strategy ─────────────────────────────────────────────────────────────────

class BTCETHMidtermShortV2Strategy:
    """Bear-market SHORT-ONLY with 3-TF hierarchy.

    Signal flow:
      Screen 0 (weekly) → Screen 1 (daily) → Screen 2 (4h) → emit SHORT

    Screen 0: weekly EMA20 < EMA50 AND EMA50 still sloping down (bear macro).
    Screen 1: daily EMA50/200 crossunder, EMA200 falling slope, MACD histogram
              negative ≥3 bars, daily RSI < 55, downtrend ≥ min_trend_days.
    Screen 2: 4h price touches EMA20 (short-term rally), then rejects with a
              close ≥0.35% below EMA20, 4h RSI>50 on touch (confirms rally),
              ATR% quality gate.
    """

    STRATEGY_NAME = "btc_eth_midterm_short_v2"

    def __init__(self, cfg: Optional[BTCETHMidtermShortV2Config] = None):
        self.cfg = cfg or BTCETHMidtermShortV2Config()
        self._load_env()

        self._allow = _env_csv_set("MTSV2_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("MTSV2_SYMBOL_DENYLIST")

        self._cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    # ── env loader ────────────────────────────────────────────────────────────

    def _load_env(self) -> None:
        c = self.cfg
        c.weekly_tf = os.getenv("MTSV2_WEEKLY_TF", c.weekly_tf)
        c.weekly_ema_fast = _env_int("MTSV2_WEEKLY_EMA_FAST", c.weekly_ema_fast)
        c.weekly_ema_slow = _env_int("MTSV2_WEEKLY_EMA_SLOW", c.weekly_ema_slow)
        c.weekly_slope_bars = _env_int("MTSV2_WEEKLY_SLOPE_BARS", c.weekly_slope_bars)
        c.weekly_slope_min_pct = _env_float("MTSV2_WEEKLY_SLOPE_MIN_PCT", c.weekly_slope_min_pct)
        c.weekly_enabled = _env_bool("MTSV2_WEEKLY_ENABLED", c.weekly_enabled)

        c.daily_tf = os.getenv("MTSV2_DAILY_TF", c.daily_tf)
        c.daily_ema_fast = _env_int("MTSV2_DAILY_EMA_FAST", c.daily_ema_fast)
        c.daily_ema_slow = _env_int("MTSV2_DAILY_EMA_SLOW", c.daily_ema_slow)
        c.daily_slope_bars = _env_int("MTSV2_DAILY_SLOPE_BARS", c.daily_slope_bars)
        c.daily_slope_min_pct = _env_float("MTSV2_DAILY_SLOPE_MIN_PCT", c.daily_slope_min_pct)
        c.daily_min_gap_pct = _env_float("MTSV2_DAILY_MIN_GAP_PCT", c.daily_min_gap_pct)
        c.daily_macd_fast = _env_int("MTSV2_DAILY_MACD_FAST", c.daily_macd_fast)
        c.daily_macd_slow = _env_int("MTSV2_DAILY_MACD_SLOW", c.daily_macd_slow)
        c.daily_macd_sig = _env_int("MTSV2_DAILY_MACD_SIG", c.daily_macd_sig)
        c.daily_macd_consec_neg = _env_int("MTSV2_DAILY_MACD_CONSEC_NEG", c.daily_macd_consec_neg)
        c.daily_rsi_period = _env_int("MTSV2_DAILY_RSI_PERIOD", c.daily_rsi_period)
        c.daily_rsi_max = _env_float("MTSV2_DAILY_RSI_MAX", c.daily_rsi_max)
        c.min_trend_days = _env_int("MTSV2_MIN_TREND_DAYS", c.min_trend_days)

        c.signal_tf = os.getenv("MTSV2_SIGNAL_TF", c.signal_tf)
        c.signal_ema_period = _env_int("MTSV2_SIGNAL_EMA_PERIOD", c.signal_ema_period)
        c.atr_period = _env_int("MTSV2_ATR_PERIOD", c.atr_period)
        c.min_atr_pct_4h = _env_float("MTSV2_MIN_ATR_PCT_4H", c.min_atr_pct_4h)
        c.max_atr_pct_4h = _env_float("MTSV2_MAX_ATR_PCT_4H", c.max_atr_pct_4h)
        c.touch_tol_pct = _env_float("MTSV2_TOUCH_TOL_PCT", c.touch_tol_pct)
        c.max_pullback_pct = _env_float("MTSV2_MAX_PULLBACK_PCT", c.max_pullback_pct)
        c.reclaim_pct = _env_float("MTSV2_RECLAIM_PCT", c.reclaim_pct)
        c.swing_lookback_bars = _env_int("MTSV2_SWING_LOOKBACK_BARS", c.swing_lookback_bars)
        c.signal_rsi_period = _env_int("MTSV2_SIGNAL_RSI_PERIOD", c.signal_rsi_period)
        c.signal_rsi_min = _env_float("MTSV2_SIGNAL_RSI_MIN", c.signal_rsi_min)

        c.sl_atr_mult = _env_float("MTSV2_SL_ATR_MULT", c.sl_atr_mult)
        c.swing_sl_buffer_atr = _env_float("MTSV2_SWING_SL_BUFFER_ATR", c.swing_sl_buffer_atr)
        c.use_runner_exits = _env_bool("MTSV2_USE_RUNNER_EXITS", c.use_runner_exits)
        c.tp1_rr = _env_float("MTSV2_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("MTSV2_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("MTSV2_TP1_FRAC", c.tp1_frac)
        c.trail_atr_mult = _env_float("MTSV2_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.time_stop_bars_5m = _env_int("MTSV2_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.eval_tf_min = _env_int("MTSV2_EVAL_TF_MIN", c.eval_tf_min)
        c.cooldown_bars_5m = _env_int("MTSV2_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.max_signals_per_day = _env_int("MTSV2_MAX_SIGNALS_PER_DAY", c.max_signals_per_day)

    # ── Screen 0: weekly macro gate ───────────────────────────────────────────

    def _screen0_weekly(self, store) -> bool:
        """Return True if weekly macro is bearish (permits further checks)."""
        if not self.cfg.weekly_enabled:
            return True  # Bypass: debug / research mode

        need = max(self.cfg.weekly_ema_slow + self.cfg.weekly_slope_bars + 5, 60)
        rows = store.fetch_klines(store.symbol, self.cfg.weekly_tf, need) or []
        if len(rows) < self.cfg.weekly_ema_slow + self.cfg.weekly_slope_bars + 2:
            return False

        closes = [float(r[4]) for r in rows]
        ef = _ema(closes, self.cfg.weekly_ema_fast)
        es = _ema(closes, self.cfg.weekly_ema_slow)
        es_prev = _ema(closes[:-self.cfg.weekly_slope_bars], self.cfg.weekly_ema_slow)

        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev)):
            return False
        if es_prev == 0:
            return False

        # Weekly EMA20 must be BELOW weekly EMA50 (bearish structure)
        if ef >= es:
            return False  # Weekly still bullish — silence

        # EMA50 must be trending DOWN (not flat/recovering)
        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if slope_pct > -self.cfg.weekly_slope_min_pct:
            return False  # Slope too flat or turning up — silence

        return True  # Weekly macro is bearish

    # ── Screen 1: daily trend filter ─────────────────────────────────────────

    def _screen1_daily(self, store) -> bool:
        """Return True when daily is in a confirmed, quality downtrend."""
        c = self.cfg
        need = max(c.daily_ema_slow + c.daily_slope_bars + c.daily_macd_slow + 20,
                   c.daily_ema_slow + c.min_trend_days + 10)
        rows = store.fetch_klines(store.symbol, c.daily_tf, need) or []
        min_required = c.daily_ema_slow + max(c.daily_macd_consec_neg, c.min_trend_days) + 5
        if len(rows) < min_required:
            return False

        closes = [float(r[4]) for r in rows]

        # 1a. EMA50 < EMA200 (bearish crossunder maintained)
        ema50_series = _ema_series(closes, c.daily_ema_fast)
        ema200_series = _ema_series(closes, c.daily_ema_slow)
        cur_ema50 = ema50_series[-1]
        cur_ema200 = ema200_series[-1]

        if not (math.isfinite(cur_ema50) and math.isfinite(cur_ema200)):
            return False
        if cur_ema50 >= cur_ema200:
            return False  # Bullish EMA structure — abort

        # 1b. EMA gap check
        last_c = max(1e-12, abs(closes[-1]))
        gap_pct = abs(cur_ema50 - cur_ema200) / last_c * 100.0
        if gap_pct < c.daily_min_gap_pct:
            return False  # EMAs too close → transitional noise

        # 1c. EMA200 slope must be negative
        ema200_prev = _ema(closes[:-c.daily_slope_bars], c.daily_ema_slow)
        if not math.isfinite(ema200_prev) or ema200_prev == 0:
            return False
        slope_pct = (cur_ema200 - ema200_prev) / abs(ema200_prev) * 100.0
        if slope_pct > -c.daily_slope_min_pct:
            return False  # EMA200 not falling fast enough

        # 1d. min_trend_days: confirm EMA50 has been continuously below EMA200
        for i in range(-c.min_trend_days, 0):
            if ema50_series[i] >= ema200_series[i]:
                return False  # Break in the downtrend within window — abort

        # 1e. MACD histogram: need consec_neg consecutive negative bars
        hist = _macd_histogram_series(closes, c.daily_macd_fast,
                                      c.daily_macd_slow, c.daily_macd_sig)
        neg_count = 0
        for i in range(-c.daily_macd_consec_neg - 2, 0):
            h = hist[i]
            if math.isfinite(h) and h < 0:
                neg_count += 1
        if neg_count < c.daily_macd_consec_neg:
            return False  # Not enough consecutive negative histogram

        # 1f. Daily RSI < rsi_max (not in a bull thrust)
        rsi_val = _rsi(closes, c.daily_rsi_period)
        if not math.isfinite(rsi_val):
            return False
        if rsi_val > c.daily_rsi_max:
            return False  # Daily RSI too high — bullish momentum still present

        return True  # Daily filter passed

    # ── Screen 2: 4h pullback/rejection entry ────────────────────────────────

    def _screen2_signal(self, store) -> Optional[dict]:
        """Check 4h for pullback-to-EMA20 + rejection.

        Returns a dict with entry geometry, or None if no signal.
        """
        c = self.cfg
        need = max(c.signal_ema_period + c.swing_lookback_bars + c.atr_period + 5,
                   c.signal_ema_period + c.signal_rsi_period + 10)
        rows = store.fetch_klines(store.symbol, c.signal_tf, need) or []
        min_req = c.signal_ema_period + max(c.swing_lookback_bars, c.atr_period) + 2
        if len(rows) < min_req:
            return None

        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]

        ema20 = _ema(closes, c.signal_ema_period)
        atr4h = _atr_from_rows(rows, c.atr_period)
        rsi4h = _rsi(closes, c.signal_rsi_period)

        if not all(math.isfinite(x) and x > 0 for x in [ema20, atr4h]):
            return None

        cur_c = closes[-1]
        prev_c = closes[-2]
        atr_pct = atr4h / max(1e-12, abs(cur_c)) * 100.0

        # Quality gate: ATR% must be within [min, max]
        if not (c.min_atr_pct_4h <= atr_pct <= c.max_atr_pct_4h):
            return None

        # Swing high: highest in recent lookback
        look = max(3, min(len(rows), c.swing_lookback_bars))
        swing_high = max(highs[-look:])

        # ── Touch check: did the recent swing high reach EMA20 zone? ────────
        ema20_upper = ema20 * (1.0 + c.touch_tol_pct / 100.0)
        ema20_lower = ema20 * (1.0 - c.touch_tol_pct / 100.0)
        touched = (ema20_lower <= swing_high <= ema20_upper) or (
            swing_high >= ema20_lower  # swing came from below and pierced EMA
        )
        if not touched:
            return None

        # Pullback magnitude: swing high must not overshoot EMA20 by too much
        overshoot_pct = max(0.0, (swing_high - ema20) / max(1e-12, ema20) * 100.0)
        if overshoot_pct > c.max_pullback_pct:
            return None  # Too extended above EMA — late entry

        # ── Rejection: current bar closes below EMA20 × (1 - reclaim_pct%) ──
        reclaim_level = ema20 * (1.0 - c.reclaim_pct / 100.0)
        prev_touched_ema = prev_c >= ema20 * 0.998  # prev bar was at/above EMA
        cur_rejected = cur_c <= reclaim_level
        if not (prev_touched_ema and cur_rejected):
            return None

        # ── 4h RSI check: must have been > rsi_min on the touch bar ──────────
        if math.isfinite(rsi4h) and rsi4h < c.signal_rsi_min:
            return None  # 4h wasn't overbought enough — weak rally, skip

        # ── Build SL/TP ───────────────────────────────────────────────────────
        swing_sl = swing_high + c.swing_sl_buffer_atr * atr4h
        atr_sl = cur_c + c.sl_atr_mult * atr4h
        sl = max(swing_sl, atr_sl)

        if sl <= cur_c:
            return None  # Degenerate

        risk = sl - cur_c

        return {
            "entry": cur_c,
            "sl": sl,
            "risk": risk,
            "atr4h": atr4h,
            "atr_pct": atr_pct,
            "rsi4h": rsi4h if math.isfinite(rsi4h) else 0.0,
            "overshoot_pct": overshoot_pct,
        }

    # ── main entry point ──────────────────────────────────────────────────────

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

        # Cooldown gate
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        # Daily signal cap
        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        # Evaluation bucket throttle (once per hour on this slow strategy)
        bucket = ts_sec // max(1, self.cfg.eval_tf_min * 60)
        if self._last_eval_bucket == bucket:
            return None
        self._last_eval_bucket = bucket

        # ── Screen 0: weekly macro gate ───────────────────────────────────────
        if not self._screen0_weekly(store):
            return None

        # ── Screen 1: daily trend filter ─────────────────────────────────────
        if not self._screen1_daily(store):
            return None

        # ── Screen 2: 4h pullback/rejection signal ────────────────────────────
        geo = self._screen2_signal(store)
        if geo is None:
            return None

        # ── Emit SHORT signal ─────────────────────────────────────────────────
        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        self._day_signals += 1

        entry = geo["entry"]
        sl = geo["sl"]
        risk = geo["risk"]
        cfg = self.cfg

        reason = (
            f"mtsv2_short weekly_dn+daily_dn+4h_reject "
            f"atr4h%={geo['atr_pct']:.2f} rsi4h={geo['rsi4h']:.1f} "
            f"overshoot%={geo['overshoot_pct']:.2f}"
        )

        sig = TradeSignal(
            strategy=self.STRATEGY_NAME,
            symbol=store.symbol,
            side="short",
            entry=float(entry),
            sl=float(sl),
            tp=float(entry) - cfg.tp1_rr * risk,  # default TP (overridden below if runners)
            reason=reason,
        )

        if cfg.use_runner_exits:
            tp1 = entry - cfg.tp1_rr * risk
            tp2 = entry - cfg.tp2_rr * risk
            tp1_frac = min(0.9, max(0.1, float(cfg.tp1_frac)))
            sig.tps = [float(tp1), float(tp2)]
            sig.tp_fracs = [tp1_frac, max(0.0, 1.0 - tp1_frac)]
            sig.trailing_atr_mult = max(0.0, float(cfg.trail_atr_mult))
            sig.trailing_atr_period = max(5, int(cfg.atr_period))
            sig.time_stop_bars = max(0, int(cfg.time_stop_bars_5m))

        return sig
