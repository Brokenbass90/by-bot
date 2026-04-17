from __future__ import annotations

"""BTC/ETH midterm SHORT-ONLY strategy (bear-market optimised).

Architecture
------------
* Trend timeframe : daily (1440 min) — EMA50/200 slope confirms macro downtrend
* Signal timeframe: 4h  (240  min)  — pullback to 4h EMA20, rejection entry
* Direction       : SHORT ONLY — never emits a long signal regardless of env

Why a separate file?
--------------------
The bidirectional ``btc_eth_midterm_pullback.py`` family (v1/v2/v3) uses
4h trend + 1h signal, which works well for bull cycles.  In a macro bear
market the relevant structure lives one TF higher: daily downtrend is the
primary anchor, 4h pullback is the entry vehicle.

This strategy is designed to:
  • Run independently alongside (or instead of) the long-biased midterm
    variants during ``bear_trend`` / ``bear_chop`` regimes.
  • Remain **permanently disabled** in bull regimes via the allocator sleeve
    (``bear_trend=0.9, bear_chop=0.65, bull_trend=0.0, bull_chop=0.0``).
  • Require WF-22 walk-forward validation before going live.

Env prefix: ``MTSV1_``  (Midterm Short V1)
Strategy name reported in signals: ``btc_eth_midterm_short_v1``
"""

import math
import os
from dataclasses import dataclass
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


# ─── config ───────────────────────────────────────────────────────────────────

@dataclass
class BTCETHMidtermShortV1Config:
    # Timeframes
    trend_tf: str = "1440"          # Daily — macro downtrend anchor
    signal_tf: str = "240"          # 4h   — pullback entry trigger
    eval_tf_min: int = 60           # Evaluate once per 1h bucket (daily TF moves slowly)

    # Trend detection (daily EMA)
    trend_ema_fast: int = 50
    trend_ema_slow: int = 200
    trend_slope_bars: int = 5       # Fewer bars needed — daily slope is decisive
    trend_slope_min_pct: float = 0.10  # Looser than 4h (daily moves are smoother)
    trend_min_gap_pct: float = 0.20  # EMA gap before treating as neutral

    # Signal detection (4h EMA20 pullback + rejection)
    signal_ema_period: int = 20
    atr_period: int = 14
    max_pullback_pct: float = 1.20  # Allow slightly deeper 4h pullbacks
    touch_tol_pct: float = 0.25    # ±0.25% tolerance to "touch" EMA
    reclaim_pct: float = 0.20      # Must reject 0.20% below EMA to confirm
    swing_lookback_bars: int = 8   # Look back 8 × 4h bars (= 32h) for swing high

    # Volatility filter — skip if 4h ATR% is too high (avoids chaotic entries)
    max_atr_pct_4h: float = 2.50   # Max 4h ATR as % of price (more generous than 1h)

    # Exit parameters — sized for daily-TF moves (larger swings, longer holds)
    sl_atr_mult: float = 1.30      # SL = swing_high + 1.3 × 4h_ATR
    swing_sl_buffer_atr: float = 0.20  # Extra buffer above swing high
    rr: float = 2.5                # Primary TP at 2.5R (no runner splits)
    use_runner_exits: bool = True  # Split: partial at 1.5R, runner to 3.0R
    tp1_rr: float = 1.5
    tp2_rr: float = 3.0
    tp1_frac: float = 0.50         # 50% off at TP1, 50% runs
    trail_atr_mult: float = 1.2
    time_stop_bars_5m: int = 144   # 12h time stop (= 144 × 5m) — shorts can extend

    # Throttling
    cooldown_bars_5m: int = 144    # 12h cooldown between signals per symbol
    max_signals_per_day: int = 1   # At most 1 short per symbol per day


# ─── strategy ─────────────────────────────────────────────────────────────────

class BTCETHMidtermShortV1Strategy:
    """Bear-market optimised SHORT-ONLY strategy.

    Entry logic:
      1. Daily EMA50 < EMA200  AND  daily EMA200 slope < -0.10%
         → confirmed macro downtrend (bias = 0)
      2. 4h price rallies back toward 4h EMA20 (touches within tol_pct)
      3. 4h candle closes back below EMA20 × (1 - reclaim_pct/100)
         → rejection confirmed → short entry
    SL  : above swing high (8-bar lookback) + buffer_atr + sl_atr_mult × ATR
    TP1 : entry - tp1_rr × risk  (50% of position)
    TP2 : entry - tp2_rr × risk  (50% runner, trailing stop behind)
    Time: auto-close after time_stop_bars_5m candles if not hit

    This strategy is SHORT ONLY.  No env override can enable longs.
    """

    STRATEGY_NAME = "btc_eth_midterm_short_v1"

    def __init__(self, cfg: Optional[BTCETHMidtermShortV1Config] = None):
        self.cfg = cfg or BTCETHMidtermShortV1Config()

        # Allow full hot-reload via MTSV1_ env prefix
        self.cfg.trend_tf = os.getenv("MTSV1_TREND_TF", self.cfg.trend_tf)
        self.cfg.signal_tf = os.getenv("MTSV1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.eval_tf_min = _env_int("MTSV1_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.trend_ema_fast = _env_int("MTSV1_TREND_EMA_FAST", self.cfg.trend_ema_fast)
        self.cfg.trend_ema_slow = _env_int("MTSV1_TREND_EMA_SLOW", self.cfg.trend_ema_slow)
        self.cfg.trend_slope_bars = _env_int("MTSV1_TREND_SLOPE_BARS", self.cfg.trend_slope_bars)
        self.cfg.trend_slope_min_pct = _env_float("MTSV1_TREND_SLOPE_MIN_PCT", self.cfg.trend_slope_min_pct)
        self.cfg.trend_min_gap_pct = _env_float("MTSV1_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)
        self.cfg.signal_ema_period = _env_int("MTSV1_SIGNAL_EMA_PERIOD", self.cfg.signal_ema_period)
        self.cfg.atr_period = _env_int("MTSV1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.max_pullback_pct = _env_float("MTSV1_MAX_PULLBACK_PCT", self.cfg.max_pullback_pct)
        self.cfg.touch_tol_pct = _env_float("MTSV1_TOUCH_TOL_PCT", self.cfg.touch_tol_pct)
        self.cfg.reclaim_pct = _env_float("MTSV1_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.swing_lookback_bars = _env_int("MTSV1_SWING_LOOKBACK_BARS", self.cfg.swing_lookback_bars)
        self.cfg.max_atr_pct_4h = _env_float("MTSV1_MAX_ATR_PCT_4H", self.cfg.max_atr_pct_4h)
        self.cfg.sl_atr_mult = _env_float("MTSV1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.swing_sl_buffer_atr = _env_float("MTSV1_SWING_SL_BUFFER_ATR", self.cfg.swing_sl_buffer_atr)
        self.cfg.rr = _env_float("MTSV1_RR", self.cfg.rr)
        self.cfg.use_runner_exits = _env_bool("MTSV1_USE_RUNNER_EXITS", self.cfg.use_runner_exits)
        self.cfg.tp1_rr = _env_float("MTSV1_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_rr = _env_float("MTSV1_TP2_RR", self.cfg.tp2_rr)
        self.cfg.tp1_frac = _env_float("MTSV1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.trail_atr_mult = _env_float("MTSV1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("MTSV1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("MTSV1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("MTSV1_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)

        # BTC+ETH only — the macro short logic is meaningless on small alts
        self._allow = _env_csv_set("MTSV1_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT")
        self._deny = _env_csv_set("MTSV1_SYMBOL_DENYLIST")

        self._cooldown = 0
        self._last_eval_bucket: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals = 0

    # ── trend ─────────────────────────────────────────────────────────────────

    def _trend_bias(self, store) -> Optional[int]:
        """Return 0 (downtrend), 1 (neutral), 2 (uptrend) from daily bars.

        Returns None when insufficient history is available.
        Bias == 0 is the ONLY condition that enables a short entry.
        """
        lb = max(3, int(self.cfg.trend_slope_bars))
        need = max(self.cfg.trend_ema_slow + lb + 5, 220)
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
            return 1  # EMAs too close → neutral

        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if ef > es and slope_pct >= self.cfg.trend_slope_min_pct:
            return 2  # daily uptrend
        if ef < es and slope_pct <= -self.cfg.trend_slope_min_pct:
            return 0  # daily downtrend ← target condition
        return 1  # neutral / mixed

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

        # Evaluation bucket throttle (1h on daily-TF strategy)
        bucket = ts_sec // max(1, int(self.cfg.eval_tf_min * 60))
        if self._last_eval_bucket == bucket:
            return None
        self._last_eval_bucket = bucket

        # ── 1. Daily trend: must be macro downtrend ──────────────────────────
        bias = self._trend_bias(store)
        if bias is None or bias != 0:
            return None  # Not in a confirmed daily downtrend → skip

        # ── 2. Fetch 4h bars for signal ──────────────────────────────────────
        need_4h = max(self.cfg.signal_ema_period + self.cfg.swing_lookback_bars + 5, 60)
        rows_4h = store.fetch_klines(store.symbol, self.cfg.signal_tf, need_4h) or []
        if len(rows_4h) < self.cfg.signal_ema_period + self.cfg.swing_lookback_bars + 2:
            return None

        highs = [float(r[2]) for r in rows_4h]
        lows = [float(r[3]) for r in rows_4h]
        closes = [float(r[4]) for r in rows_4h]
        ema4h = _ema(closes, self.cfg.signal_ema_period)
        atr4h = _atr_from_rows(rows_4h, self.cfg.atr_period)

        if not (math.isfinite(ema4h) and math.isfinite(atr4h) and atr4h > 0):
            return None

        cur_c = closes[-1]
        prev_c = closes[-2]
        atr_pct_4h = (atr4h / max(1e-12, abs(cur_c))) * 100.0

        # ── 3. Volatility filter: skip during excessively volatile 4h candles ─
        if atr_pct_4h > self.cfg.max_atr_pct_4h:
            return None  # Too volatile — spread + slippage will hurt entry quality

        # ── 4. SHORT signal conditions ────────────────────────────────────────
        look = max(3, min(len(rows_4h), int(self.cfg.swing_lookback_bars)))
        swing_high = max(highs[-look:])

        # Condition A: 4h pullback touched EMA20 from below (rally into EMA)
        touched = swing_high >= ema4h * (1.0 - self.cfg.touch_tol_pct / 100.0)

        # Condition B: current bar has rejected back below EMA20 (bearish reclaim)
        #   — prev bar was at/above EMA, current bar is clearly below
        reclaimed = (
            cur_c <= ema4h * (1.0 - self.cfg.reclaim_pct / 100.0)
            and prev_c >= ema4h * 0.997
        )

        # Condition C: pullback magnitude within allowable range
        pullback_pct = max(0.0, (swing_high - ema4h) / max(1e-12, ema4h) * 100.0)
        if not (touched and reclaimed and pullback_pct <= self.cfg.max_pullback_pct):
            return None

        # ── 5. Build SL/TP ───────────────────────────────────────────────────
        swing_sl = swing_high + self.cfg.swing_sl_buffer_atr * atr4h
        atr_sl = float(c) + self.cfg.sl_atr_mult * atr4h
        sl = max(swing_sl, atr_sl)  # SL above BOTH anchors

        if sl <= float(c):
            return None  # Degenerate — skip

        risk = sl - float(c)
        tp = float(c) - self.cfg.rr * risk

        # ── 6. Emit signal ───────────────────────────────────────────────────
        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        self._day_signals += 1

        reason = (
            f"mtsv1_short daily_dn ema4h={self.cfg.signal_ema_period} "
            f"atr4h%={atr_pct_4h:.2f} pullback%={pullback_pct:.2f}"
        )
        sig = TradeSignal(
            strategy=self.STRATEGY_NAME,
            symbol=store.symbol,
            side="short",
            entry=float(c),
            sl=float(sl),
            tp=float(tp),
            reason=reason,
        )

        if self.cfg.use_runner_exits:
            tp1 = float(c) - float(self.cfg.tp1_rr) * risk
            tp2 = float(c) - float(self.cfg.tp2_rr) * risk
            tp1_frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))
            sig.tps = [float(tp1), float(tp2)]
            sig.tp_fracs = [tp1_frac, max(0.0, 1.0 - tp1_frac)]
            sig.trailing_atr_mult = max(0.0, float(self.cfg.trail_atr_mult))
            sig.trailing_atr_period = max(5, int(self.cfg.atr_period))
            sig.time_stop_bars = max(0, int(self.cfg.time_stop_bars_5m))

        return sig
