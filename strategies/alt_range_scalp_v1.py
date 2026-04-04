"""
alt_range_scalp_v1 — 15-minute range scalper using Bollinger Bands + RSI

Scalps both sides of a defined range on 15m bars for choppy/bear markets.
Uses Bollinger Bands (20 SMA ± 2.0 std) to identify range edges and RSI
to confirm overbought/oversold conditions.

SHORT: close above upper band + RSI > 62 + bearish bar → enter short
LONG: close below lower band + RSI < 38 + bullish bar → enter long

SL: 0.8 ATR beyond the band extreme
TP1: 50% to midline, TP2: opposite band - 0.3 ATR buffer
Time stop: 216 5m bars (18 hours on 15m = 72 bars × 3)

Typical env config:
    ARS1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT
    ARS1_BB_PERIOD=20
    ARS1_BB_STD=2.0
    ARS1_RSI_LONG_MAX=38.0
    ARS1_RSI_SHORT_MIN=62.0
    ARS1_MIN_BAND_WIDTH_PCT=3.0
    ARS1_MAX_BAND_WIDTH_PCT=20.0
    ARS1_ALLOW_LONGS=1
    ARS1_ALLOW_SHORTS=1
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
class AltRangeScalpV1Config:
    bb_period: int = 20
    bb_std: float = 2.0
    rsi_long_max: float = 38.0
    rsi_short_min: float = 62.0
    rsi_period: int = 14
    atr_period: int = 14
    min_band_width_pct: float = 3.0
    max_band_width_pct: float = 20.0
    sl_atr_mult: float = 0.8
    tp1_frac: float = 0.55
    time_stop_bars_5m: int = 216
    cooldown_bars_5m: int = 48
    allow_longs: bool = True
    allow_shorts: bool = True


class AltRangeScalpV1Strategy:
    """15m range scalper using Bollinger Bands."""

    def __init__(self, cfg: Optional[AltRangeScalpV1Config] = None):
        self.cfg = cfg or AltRangeScalpV1Config()

        self.cfg.bb_period = _env_int("ARS1_BB_PERIOD", self.cfg.bb_period)
        self.cfg.bb_std = _env_float("ARS1_BB_STD", self.cfg.bb_std)
        self.cfg.rsi_long_max = _env_float("ARS1_RSI_LONG_MAX", self.cfg.rsi_long_max)
        self.cfg.rsi_short_min = _env_float("ARS1_RSI_SHORT_MIN", self.cfg.rsi_short_min)
        self.cfg.rsi_period = _env_int("ARS1_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.atr_period = _env_int("ARS1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.min_band_width_pct = _env_float("ARS1_MIN_BAND_WIDTH_PCT", self.cfg.min_band_width_pct)
        self.cfg.max_band_width_pct = _env_float("ARS1_MAX_BAND_WIDTH_PCT", self.cfg.max_band_width_pct)
        self.cfg.sl_atr_mult = _env_float("ARS1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_frac = _env_float("ARS1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.time_stop_bars_5m = _env_int("ARS1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("ARS1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("ARS1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("ARS1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("ARS1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("ARS1_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_15m_ts: Optional[int] = None
        self.last_no_signal_reason = ""

    def _refresh_runtime_allowlists(self) -> None:
        self._allow = _env_csv_set("ARS1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("ARS1_SYMBOL_DENYLIST")

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, v)
        self._refresh_runtime_allowlists()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        # Fetch 15m bars
        rows_15m = store.fetch_klines(store.symbol, "15", 50) or []
        if len(rows_15m) < max(self.cfg.bb_period + 5, 30):
            self.last_no_signal_reason = "not_enough_15m_bars"
            return None

        tf_ts = int(float(rows_15m[-1][0]))
        if self._last_15m_ts is not None and tf_ts == self._last_15m_ts:
            return None
        self._last_15m_ts = tf_ts

        # Extract data from 15m bars
        highs_15m = [float(r[2]) for r in rows_15m]
        lows_15m = [float(r[3]) for r in rows_15m]
        closes_15m = [float(r[4]) for r in rows_15m]
        opens_15m = [float(r[1]) for r in rows_15m]

        # Compute Bollinger Bands
        mid = _sma(closes_15m, self.cfg.bb_period)
        std = _std_dev(closes_15m, self.cfg.bb_period)
        if not all(math.isfinite(x) for x in (mid, std)) or std <= 0:
            self.last_no_signal_reason = "bb_invalid"
            return None

        upper = mid + self.cfg.bb_std * std
        lower = mid - self.cfg.bb_std * std
        band_width = (upper - lower) / max(1e-12, mid) * 100.0

        # Band width check
        if band_width < self.cfg.min_band_width_pct or band_width > self.cfg.max_band_width_pct:
            self.last_no_signal_reason = f"band_width_invalid_{band_width:.1f}pct"
            return None

        # Compute indicators on 15m bars
        rsi_15m = _rsi(closes_15m, self.cfg.rsi_period)
        atr_15m = _atr_from_rows(rows_15m, self.cfg.atr_period)
        if not all(math.isfinite(x) for x in (rsi_15m, atr_15m)) or atr_15m <= 0:
            self.last_no_signal_reason = "indicators_invalid"
            return None

        cur = closes_15m[-1]
        prev_close = closes_15m[-2]
        open_cur = opens_15m[-1]
        high_cur = highs_15m[-1]
        low_cur = lows_15m[-1]

        # Determine signal
        entry_price = float(c)
        side = None
        tp_other = None

        # SHORT: above upper band + high RSI + bearish bar
        if self.cfg.allow_shorts and cur > upper and rsi_15m > self.cfg.rsi_short_min and cur < open_cur:
            side = "short"
            tp_other = lower
            sl = upper + self.cfg.sl_atr_mult * atr_15m

            if sl <= entry_price:
                self.last_no_signal_reason = "short_sl_invalid"
                return None

        # LONG: below lower band + low RSI + bullish bar
        elif self.cfg.allow_longs and cur < lower and rsi_15m < self.cfg.rsi_long_max and cur > open_cur:
            side = "long"
            tp_other = upper
            sl = lower - self.cfg.sl_atr_mult * atr_15m

            if sl >= entry_price:
                self.last_no_signal_reason = "long_sl_invalid"
                return None

        if side is None:
            self.last_no_signal_reason = "no_signal_conditions"
            return None

        # Calculate targets
        if side == "short":
            # TP1 = 50% to mid, TP2 = lower band - 0.3 ATR buffer
            tp1 = entry_price - (entry_price - tp_other) * self.cfg.tp1_frac
            tp2 = tp_other - 0.3 * atr_15m
            if tp2 >= entry_price or tp1 >= entry_price or tp1 <= tp2:
                self.last_no_signal_reason = "short_tp_invalid"
                return None
        else:  # long
            # TP1 = 50% to mid, TP2 = upper band + 0.3 ATR buffer
            tp1 = entry_price + (tp_other - entry_price) * self.cfg.tp1_frac
            tp2 = tp_other + 0.3 * atr_15m
            if tp2 <= entry_price or tp1 <= entry_price or tp1 >= tp2:
                self.last_no_signal_reason = "long_tp_invalid"
                return None

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="alt_range_scalp_v1",
            symbol=store.symbol,
            side=side,
            entry=entry_price,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[self.cfg.tp1_frac, 1.0 - self.cfg.tp1_frac],
            trailing_atr_mult=0.0,
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason="ars1_bb_scalp",
        )
        return sig if sig.validate() else None
