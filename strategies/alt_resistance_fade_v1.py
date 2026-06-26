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
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


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
    min_rr: float = 1.15
    min_stop_pct: float = 0.0015
    max_stop_pct: float = 0.06
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
        c.min_rr                   = _env_float("ARF1_MIN_RR", c.min_rr)
        c.min_stop_pct             = _env_float("ARF1_MIN_STOP_PCT", c.min_stop_pct)
        c.max_stop_pct             = _env_float("ARF1_MAX_STOP_PCT", c.max_stop_pct)
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
        es_prev = _ema(closes[:-1], self.cfg.regime_ema_slow)
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
        entry_price = float(cur)      # keep geometry consistent with the closed signal bar
        sl  = resistance + self.cfg.sl_atr_mult * atr
        tp2 = support * (1.0 + self.cfg.tp2_buffer_pct / 100.0)

        if sl <= entry_price:
            self._no_signal("sl_below_entry")
            return None
        if tp2 >= entry_price:
            self._no_signal("tp_above_entry")
            return None

        risk = sl - entry_price
        reward = entry_price - tp2
        stop_pct = risk / max(1e-12, entry_price)
        rr = reward / max(1e-12, risk)
        if stop_pct < self.cfg.min_stop_pct:
            self._no_signal(f"stop_too_tight_{stop_pct:.4f}")
            return None
        if stop_pct > self.cfg.max_stop_pct:
            self._no_signal(f"stop_too_wide_{stop_pct:.4f}")
            return None
        if rr < self.cfg.min_rr:
            self._no_signal(f"rr_too_low_{rr:.2f}")
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
