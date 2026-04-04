"""
alt_inplay_breakdown_v2 — Improved breakdown strategy using 1h structure

Rewrite of alt_inplay_breakdown_v1, fixing the 4h delay issue by using
1h bars for structure detection instead of 4h.

Key improvements:
- Uses 1h bars (tf_break="60") for support detection: 1h delay instead of 4h
- Finds 24h low on 1h bars and enters on 5m bearish confirmation
- RSI(14) filter on 1h (must be < 50 for downtrend)
- Volume filter on trigger bar
- Optional regime check (EMA-based on 4h)

Typical env config:
    BREAKDOWN2_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT
    BREAKDOWN2_LOOKBACK_H=24
    BREAKDOWN2_MIN_BREAK_ATR=0.15
    BREAKDOWN2_MAX_DIST_ATR=2.0
    BREAKDOWN2_SL_ATR=1.5
    BREAKDOWN2_RR=2.0
    BREAKDOWN2_RSI_MAX=52.0
    BREAKDOWN2_REGIME_MODE=off
    BREAKDOWN2_ALLOW_LONGS=0
    BREAKDOWN2_VOL_MULT=1.0
    BREAKDOWN2_TP1_FRAC=0.50
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


def _sma(values: List[float], period: int) -> float:
    if len(values) < period:
        return float("nan")
    return sum(values[-period:]) / float(period)


def _std_dev(values: List[float], period: int) -> float:
    if len(values) < period:
        return float("nan")
    mean = _sma(values, period)
    var = sum((x - mean) ** 2 for x in values[-period:]) / float(period)
    return math.sqrt(var)


@dataclass
class AltInplayBreakdownV2Config:
    # Structure detection on 1h bars
    lookback_h: int = 24
    min_break_atr: float = 0.15
    max_dist_atr: float = 2.0
    sl_atr: float = 1.5
    rr: float = 2.0
    rsi_max: float = 52.0

    # Regime filter (off/ema)
    regime_mode: str = "off"
    regime_tf: str = "240"
    regime_ema_fast: int = 21
    regime_ema_slow: int = 55

    # Filters
    vol_mult: float = 1.0
    tp1_frac: float = 0.50

    # Exit management
    time_stop_bars_5m: int = 288
    cooldown_bars_5m: int = 48
    allow_longs: bool = False
    allow_shorts: bool = True


class AltInplayBreakdownV2Strategy:
    """1h-based short breakdown strategy with 5m confirmation."""

    def __init__(self, cfg: Optional[AltInplayBreakdownV2Config] = None):
        self.cfg = cfg or AltInplayBreakdownV2Config()

        self.cfg.lookback_h = _env_int("BREAKDOWN2_LOOKBACK_H", self.cfg.lookback_h)
        self.cfg.min_break_atr = _env_float("BREAKDOWN2_MIN_BREAK_ATR", self.cfg.min_break_atr)
        self.cfg.max_dist_atr = _env_float("BREAKDOWN2_MAX_DIST_ATR", self.cfg.max_dist_atr)
        self.cfg.sl_atr = _env_float("BREAKDOWN2_SL_ATR", self.cfg.sl_atr)
        self.cfg.rr = _env_float("BREAKDOWN2_RR", self.cfg.rr)
        self.cfg.rsi_max = _env_float("BREAKDOWN2_RSI_MAX", self.cfg.rsi_max)

        self.cfg.regime_mode = os.getenv("BREAKDOWN2_REGIME_MODE", self.cfg.regime_mode)
        self.cfg.regime_tf = os.getenv("BREAKDOWN2_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_ema_fast = _env_int("BREAKDOWN2_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("BREAKDOWN2_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)

        self.cfg.vol_mult = _env_float("BREAKDOWN2_VOL_MULT", self.cfg.vol_mult)
        self.cfg.tp1_frac = _env_float("BREAKDOWN2_TP1_FRAC", self.cfg.tp1_frac)

        self.cfg.time_stop_bars_5m = _env_int("BREAKDOWN2_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("BREAKDOWN2_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("BREAKDOWN2_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("BREAKDOWN2_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("BREAKDOWN2_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("BREAKDOWN2_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_1h_ts: Optional[int] = None
        self.last_no_signal_reason = ""

    def _refresh_runtime_allowlists(self) -> None:
        self._allow = _env_csv_set("BREAKDOWN2_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("BREAKDOWN2_SYMBOL_DENYLIST")

    def _regime_ok(self, store) -> bool:
        """Check if regime is bearish (EMA21 < EMA55 on 4h)."""
        if self.cfg.regime_mode.lower() != "ema":
            return True

        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, max(100, self.cfg.regime_ema_slow + 20)) or []
        if len(rows) < self.cfg.regime_ema_slow + 20:
            return False

        closes = [float(r[4]) for r in rows]
        ema_fast = _ema(closes, self.cfg.regime_ema_fast)
        ema_slow = _ema(closes, self.cfg.regime_ema_slow)

        if not all(math.isfinite(x) for x in (ema_fast, ema_slow)):
            return False

        # Bearish: fast EMA below slow EMA
        return ema_fast < ema_slow

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, v)
        self._refresh_runtime_allowlists()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None
        if not self.cfg.allow_shorts:
            return None

        # Regime filter
        if not self._regime_ok(store):
            self.last_no_signal_reason = "regime_not_bearish"
            return None

        # Fetch 1h bars (last 30 bars = ~30h of data)
        lookback_bars = max(30, self.cfg.lookback_h)
        rows_1h = store.fetch_klines(store.symbol, "60", lookback_bars) or []
        if len(rows_1h) < max(15, self.cfg.lookback_h):
            self.last_no_signal_reason = "not_enough_1h_bars"
            return None

        tf_ts = int(float(rows_1h[-1][0]))
        if self._last_1h_ts is not None and tf_ts == self._last_1h_ts:
            return None
        self._last_1h_ts = tf_ts

        # Find support (24h low on 1h bars)
        lows_1h = [float(r[3]) for r in rows_1h]
        highs_1h = [float(r[2]) for r in rows_1h]
        closes_1h = [float(r[4]) for r in rows_1h]

        lookback_idx = -min(self.cfg.lookback_h, len(rows_1h))
        support = min(lows_1h[lookback_idx:])
        resistance = max(highs_1h[lookback_idx:])

        # RSI on 1h (must be below threshold for downtrend)
        rsi_1h = _rsi(closes_1h, 14)
        if not math.isfinite(rsi_1h) or rsi_1h >= self.cfg.rsi_max:
            self.last_no_signal_reason = f"rsi_too_high_{rsi_1h:.1f}"
            return None

        # ATR on 1h
        atr_1h = _atr_from_rows(rows_1h, 14)
        if not math.isfinite(atr_1h) or atr_1h <= 0:
            self.last_no_signal_reason = "atr_invalid"
            return None

        # Check if price has broken below support
        cur_price = float(c)
        if cur_price >= support:
            self.last_no_signal_reason = f"price_above_support_{cur_price:.8f}_{support:.8f}"
            return None

        # Distance from entry to support must be reasonable
        dist_to_support = (support - cur_price) / max(1e-12, atr_1h)
        if dist_to_support > self.cfg.max_dist_atr:
            self.last_no_signal_reason = f"too_far_from_support_{dist_to_support:.2f}atr"
            return None

        # Break must be significant
        if dist_to_support < self.cfg.min_break_atr:
            self.last_no_signal_reason = f"break_too_small_{dist_to_support:.2f}atr"
            return None

        # Fetch 5m bars for confirmation + volume baseline (20 bars so baseline excludes current)
        rows_5m = store.fetch_klines(store.symbol, "5", 20) or []
        if len(rows_5m) < 3:
            self.last_no_signal_reason = "not_enough_5m_bars"
            return None

        # Current 5m bar must be bearish (close < open) with body > 25% of range
        open_5m = float(rows_5m[-1][1])
        close_5m = float(rows_5m[-1][4])
        high_5m = float(rows_5m[-1][2])
        low_5m = float(rows_5m[-1][3])
        vol_5m = float(rows_5m[-1][5])

        if close_5m >= open_5m:
            self.last_no_signal_reason = "5m_not_bearish"
            return None

        body = abs(close_5m - open_5m)
        bar_range = max(1e-12, high_5m - low_5m)
        body_frac = body / bar_range
        if body_frac < 0.25:
            self.last_no_signal_reason = f"5m_body_too_small_{body_frac:.2f}"
            return None

        # Volume check — baseline from 5 bars BEFORE current bar (exclude self-comparison)
        avg_vol_5m = sum(float(r[5]) for r in rows_5m[-6:-1]) / 5.0
        if self.cfg.vol_mult > 0 and vol_5m < self.cfg.vol_mult * avg_vol_5m:
            self.last_no_signal_reason = f"vol_too_low_{vol_5m:.0f}_{avg_vol_5m:.0f}"
            return None

        # Calculate targets
        entry_price = cur_price
        sl = support + self.cfg.sl_atr * atr_1h

        if sl <= entry_price:
            self.last_no_signal_reason = "sl_at_or_below_entry"  # SL must be above entry for shorts
            return None

        risk = sl - entry_price
        reward = risk * self.cfg.rr
        tp2 = entry_price - reward

        if tp2 >= entry_price:
            self.last_no_signal_reason = "tp_invalid"
            return None

        tp1 = entry_price - reward * self.cfg.tp1_frac

        # Set up multi-target
        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="alt_inplay_breakdown_v2",
            symbol=store.symbol,
            side="short",
            entry=entry_price,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[self.cfg.tp1_frac, 1.0 - self.cfg.tp1_frac],
            trailing_atr_mult=0.0,
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason="bd2_1h_support_break",
        )
        return sig if sig.validate() else None
