"""
pump_fade_v2 — Improved pump fade with multi-bar confirmation

Fades pumps (shorts) and bounces dumps (longs) using:
- Pump detection: 7-45% move in 12 bars (60m window)
- RSI(14) extremes: overbought (72) for fade, oversold (28) for bounce
- Consecutive reversal bars: price pulling back with bearish/bullish bars
- Volume exhaustion filter (optional)
- ATR-based stops
- Both directions: shorts fade pumps, longs bounce dumps

Typical env config:
    PF2_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT
    PF2_PUMP_WINDOW_BARS=12
    PF2_MIN_PUMP_PCT=0.07
    PF2_MAX_PUMP_PCT=0.45
    PF2_RSI_OB=72
    PF2_RSI_OS=28
    PF2_CONFIRM_BARS=1
    PF2_SL_ATR_MULT=1.5
    PF2_RR=1.8
    PF2_ALLOW_SHORTS=1
    PF2_ALLOW_LONGS=1
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
class PumpFadeV2Config:
    pump_window_bars: int = 12
    min_pump_pct: float = 0.07
    max_pump_pct: float = 0.45
    rsi_ob: float = 72.0
    rsi_os: float = 28.0
    rsi_period: int = 14
    atr_period: int = 14
    confirm_bars: int = 1
    vol_exhaust_mult: float = 0.0
    sl_atr_mult: float = 1.5
    rr: float = 1.8
    allow_shorts: bool = True
    allow_longs: bool = True
    time_stop_bars: int = 96
    cooldown_bars: int = 20


class PumpFadeV2Strategy:
    """Fades pumps and bounces dumps using RSI + reversal confirmation."""

    def __init__(self, cfg: Optional[PumpFadeV2Config] = None):
        self.cfg = cfg or PumpFadeV2Config()

        self.cfg.pump_window_bars = _env_int("PF2_PUMP_WINDOW_BARS", self.cfg.pump_window_bars)
        self.cfg.min_pump_pct = _env_float("PF2_MIN_PUMP_PCT", self.cfg.min_pump_pct)
        self.cfg.max_pump_pct = _env_float("PF2_MAX_PUMP_PCT", self.cfg.max_pump_pct)
        self.cfg.rsi_ob = _env_float("PF2_RSI_OB", self.cfg.rsi_ob)
        self.cfg.rsi_os = _env_float("PF2_RSI_OS", self.cfg.rsi_os)
        self.cfg.rsi_period = _env_int("PF2_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.atr_period = _env_int("PF2_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.confirm_bars = _env_int("PF2_CONFIRM_BARS", self.cfg.confirm_bars)
        self.cfg.vol_exhaust_mult = _env_float("PF2_VOL_EXHAUST_MULT", self.cfg.vol_exhaust_mult)
        self.cfg.sl_atr_mult = _env_float("PF2_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.rr = _env_float("PF2_RR", self.cfg.rr)
        self.cfg.allow_shorts = _env_bool("PF2_ALLOW_SHORTS", self.cfg.allow_shorts)
        self.cfg.allow_longs = _env_bool("PF2_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.time_stop_bars = _env_int("PF2_TIME_STOP_BARS", self.cfg.time_stop_bars)
        self.cfg.cooldown_bars = _env_int("PF2_COOLDOWN_BARS", self.cfg.cooldown_bars)

        self._allow = _env_csv_set("PF2_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("PF2_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_5m_ts: Optional[int] = None
        self._bars: List[tuple[int, float, float, float, float, float]] = []
        self.last_no_signal_reason = ""

    def _refresh_runtime_allowlists(self) -> None:
        self._allow = _env_csv_set("PF2_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("PF2_SYMBOL_DENYLIST")

    def maybe_signal(self, symbol: str, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        self._refresh_runtime_allowlists()

        sym = str(symbol or "").upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        need = self.cfg.pump_window_bars + self.cfg.confirm_bars + 5
        tf_ts = int(ts_ms)
        if self._last_5m_ts is not None and tf_ts == self._last_5m_ts:
            return None
        self._last_5m_ts = tf_ts
        self._bars.append((tf_ts, float(o), float(h), float(l), float(c), float(v or 0.0)))
        max_keep = max(need + 10, 220)
        if len(self._bars) > max_keep:
            self._bars = self._bars[-max_keep:]
        if len(self._bars) < need:
            self.last_no_signal_reason = "not_enough_5m_bars"
            return None

        # Extract data
        closes = [r[4] for r in self._bars]
        opens = [r[1] for r in self._bars]
        highs = [r[2] for r in self._bars]
        lows = [r[3] for r in self._bars]
        vols = [r[5] for r in self._bars]

        # Calculate indicators
        rows = [[ts, op, hi, lo, cl, vol] for ts, op, hi, lo, cl, vol in self._bars]
        rsi = _rsi(closes, self.cfg.rsi_period)
        atr = _atr_from_rows(rows, self.cfg.atr_period)
        if not all(math.isfinite(x) for x in (rsi, atr)) or atr <= 0:
            self.last_no_signal_reason = "indicators_invalid"
            return None

        cur = closes[-1]
        entry_price = float(c)

        # Detect pump window
        pump_start_idx = -self.cfg.pump_window_bars - 1
        pump_start_close = closes[pump_start_idx]
        pump_peak = max(closes[pump_start_idx:])
        pump_pct = (pump_peak - pump_start_close) / max(1e-12, pump_start_close)

        # Detect dump window
        dump_start_idx = -self.cfg.pump_window_bars - 1
        dump_start_close = closes[dump_start_idx]
        dump_trough = min(closes[dump_start_idx:])
        dump_pct = (dump_start_close - dump_trough) / max(1e-12, dump_start_close)

        side = None

        # SHORT: Pump fade
        if self.cfg.allow_shorts and self.cfg.min_pump_pct <= pump_pct <= self.cfg.max_pump_pct and rsi >= self.cfg.rsi_ob:
            # Check for reversal bars (last N bars bearish and falling)
            reversal_ok = True
            for i in range(1, min(self.cfg.confirm_bars + 1, 4)):
                if closes[-i] >= opens[-i]:
                    reversal_ok = False
                    break
                if closes[-i] >= closes[-i - 1]:
                    reversal_ok = False
                    break

            if reversal_ok:
                # Volume exhaustion check (optional)
                if self.cfg.vol_exhaust_mult > 0:
                    vol_cur = vols[-1]
                    vol_pump = max(vols[pump_start_idx:-1])
                    if vol_cur >= self.cfg.vol_exhaust_mult * vol_pump:
                        self.last_no_signal_reason = f"vol_not_exhausted_short"
                        return None

                side = "short"
                peak_high = max(highs[pump_start_idx:])
                sl = peak_high + self.cfg.sl_atr_mult * atr
                if sl <= entry_price:
                    self.last_no_signal_reason = "short_sl_invalid"
                    return None

                risk = sl - entry_price
                reward = risk * self.cfg.rr
                tp = entry_price - reward

                if tp >= entry_price:
                    self.last_no_signal_reason = "short_tp_invalid"
                    return None

        # LONG: Dump bounce
        elif self.cfg.allow_longs and self.cfg.min_pump_pct <= dump_pct <= self.cfg.max_pump_pct and rsi <= self.cfg.rsi_os:
            # Check for reversal bars (last N bars bullish and rising)
            reversal_ok = True
            for i in range(1, min(self.cfg.confirm_bars + 1, 4)):
                if closes[-i] <= opens[-i]:
                    reversal_ok = False
                    break
                if closes[-i] <= closes[-i - 1]:
                    reversal_ok = False
                    break

            if reversal_ok:
                # Volume exhaustion check (optional)
                if self.cfg.vol_exhaust_mult > 0:
                    vol_cur = vols[-1]
                    vol_dump = max(vols[dump_start_idx:-1])
                    if vol_cur >= self.cfg.vol_exhaust_mult * vol_dump:
                        self.last_no_signal_reason = f"vol_not_exhausted_long"
                        return None

                side = "long"
                trough_low = min(lows[dump_start_idx:])
                sl = trough_low - self.cfg.sl_atr_mult * atr
                if sl >= entry_price:
                    self.last_no_signal_reason = "long_sl_invalid"
                    return None

                risk = entry_price - sl
                reward = risk * self.cfg.rr
                tp = entry_price + reward

                if tp <= entry_price:
                    self.last_no_signal_reason = "long_tp_invalid"
                    return None

        if side is None:
            self.last_no_signal_reason = "no_signal_conditions"
            return None

        self._cooldown = max(0, int(self.cfg.cooldown_bars))
        sig = TradeSignal(
            strategy="pump_fade_v2",
            symbol=sym,
            side=side,
            entry=entry_price,
            sl=sl,
            tp=tp,
            trailing_atr_mult=0.0,
            time_stop_bars=max(0, int(self.cfg.time_stop_bars)),
            reason="pf2_pump_fade" if side == "short" else "pf2_dump_bounce",
        )
        return sig if sig.validate() else None
