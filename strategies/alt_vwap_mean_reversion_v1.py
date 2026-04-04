"""
alt_vwap_mean_reversion_v1 — 15m VWAP mean reversion for choppy/ranging markets.

Idea:
  - use session VWAP as the intraday magnet;
  - only trade when 15m regime is sufficiently inefficient/rangy;
  - short stretched moves above VWAP after rejection;
  - buy stretched moves below VWAP after reclaim.

This sleeve is meant to complement ARF1/ARS1 in chop and add more frequent
signals without depending on pure horizontal levels.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
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


def _efficiency_ratio(values: List[float], period: int = 20) -> float:
    if len(values) < period + 1:
        return float("nan")
    segment = values[-(period + 1):]
    direction = abs(segment[-1] - segment[0])
    volatility = sum(abs(segment[i] - segment[i - 1]) for i in range(1, len(segment)))
    if volatility <= 1e-12:
        return 0.0
    return direction / volatility


def _session_vwap(rows: List[list], ts_ms: int) -> float:
    try:
        day = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return float("nan")
    num = 0.0
    den = 0.0
    for r in rows:
        try:
            row_day = datetime.fromtimestamp(float(r[0]) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
            if row_day != day:
                continue
            vol = float(r[5])
            if vol <= 0:
                continue
            typical = (float(r[2]) + float(r[3]) + float(r[4])) / 3.0
        except Exception:
            continue
        num += typical * vol
        den += vol
    return num / den if den > 0 else float("nan")


@dataclass
class AltVWAPMeanReversionV1Config:
    signal_tf: str = "15"
    signal_lookback: int = 72
    session_bars_min: int = 12
    rsi_period: int = 14
    atr_period: int = 14
    max_er: float = 0.38
    long_rsi_max: float = 39.0
    short_rsi_min: float = 61.0
    min_vwap_dev_atr: float = 0.95
    sl_atr_mult: float = 0.90
    tp1_frac: float = 0.65
    tp2_atr: float = 0.20
    time_stop_bars_5m: int = 144
    cooldown_bars_5m: int = 36
    allow_longs: bool = True
    allow_shorts: bool = True


class AltVWAPMeanReversionV1Strategy:
    NAME = "alt_vwap_mean_reversion_v1"

    def __init__(self, cfg: Optional[AltVWAPMeanReversionV1Config] = None):
        self.cfg = cfg or AltVWAPMeanReversionV1Config()
        self.cfg.signal_tf = os.getenv("AVW1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_lookback = _env_int("AVW1_SIGNAL_LOOKBACK", self.cfg.signal_lookback)
        self.cfg.session_bars_min = _env_int("AVW1_SESSION_BARS_MIN", self.cfg.session_bars_min)
        self.cfg.rsi_period = _env_int("AVW1_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.atr_period = _env_int("AVW1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.max_er = _env_float("AVW1_MAX_ER", self.cfg.max_er)
        self.cfg.long_rsi_max = _env_float("AVW1_LONG_RSI_MAX", self.cfg.long_rsi_max)
        self.cfg.short_rsi_min = _env_float("AVW1_SHORT_RSI_MIN", self.cfg.short_rsi_min)
        self.cfg.min_vwap_dev_atr = _env_float("AVW1_MIN_VWAP_DEV_ATR", self.cfg.min_vwap_dev_atr)
        self.cfg.sl_atr_mult = _env_float("AVW1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_frac = _env_float("AVW1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.tp2_atr = _env_float("AVW1_TP2_ATR", self.cfg.tp2_atr)
        self.cfg.time_stop_bars_5m = _env_int("AVW1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("AVW1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("AVW1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("AVW1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("AVW1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("AVW1_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self.last_no_signal_reason = ""

    def _refresh_runtime_allowlists(self) -> None:
        self._allow = _env_csv_set("AVW1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("AVW1_SYMBOL_DENYLIST")

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
        self._refresh_runtime_allowlists()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        rows_tf = store.fetch_klines(store.symbol, self.cfg.signal_tf, max(120, self.cfg.signal_lookback + 20)) or []
        if len(rows_tf) < max(self.cfg.signal_lookback, self.cfg.atr_period + 5, self.cfg.rsi_period + 5):
            self.last_no_signal_reason = "not_enough_signal_tf_bars"
            return None

        tf_ts = int(float(rows_tf[-1][0]))
        if self._last_tf_ts is not None and tf_ts == self._last_tf_ts:
            return None
        self._last_tf_ts = tf_ts

        rows_5m = store.fetch_klines(store.symbol, "5", 320) or []
        if len(rows_5m) < 40:
            self.last_no_signal_reason = "not_enough_5m_bars"
            return None

        session_rows = [r for r in rows_5m if _same_day(r[0], ts_ms)]
        if len(session_rows) < int(self.cfg.session_bars_min):
            self.last_no_signal_reason = "session_too_short"
            return None

        vwap = _session_vwap(rows_5m, ts_ms)
        if not math.isfinite(vwap) or vwap <= 0:
            self.last_no_signal_reason = "vwap_invalid"
            return None

        closes = [float(r[4]) for r in rows_tf]
        opens = [float(r[1]) for r in rows_tf]
        highs = [float(r[2]) for r in rows_tf]
        lows = [float(r[3]) for r in rows_tf]

        er = _efficiency_ratio(closes, min(int(self.cfg.signal_lookback), 20))
        rsi = _rsi(closes, self.cfg.rsi_period)
        atr = _atr_from_rows(rows_tf, self.cfg.atr_period)
        if not all(math.isfinite(x) for x in (er, rsi, atr)) or atr <= 0:
            self.last_no_signal_reason = "indicators_invalid"
            return None
        if er > float(self.cfg.max_er):
            self.last_no_signal_reason = f"er_too_high_{er:.2f}"
            return None

        cur = closes[-1]
        open_cur = opens[-1]
        high_cur = highs[-1]
        low_cur = lows[-1]
        dev_atr = (cur - vwap) / atr

        entry = float(c)
        side = None

        if (
            self.cfg.allow_shorts
            and dev_atr >= float(self.cfg.min_vwap_dev_atr)
            and rsi >= float(self.cfg.short_rsi_min)
            and cur < open_cur
            and cur > vwap
        ):
            side = "short"
            sl = max(high_cur, entry) + float(self.cfg.sl_atr_mult) * atr
            tp1 = entry - (entry - vwap) * float(self.cfg.tp1_frac)
            tp2 = vwap - float(self.cfg.tp2_atr) * atr
            if sl <= entry or tp1 >= entry or tp2 >= tp1:
                self.last_no_signal_reason = "short_levels_invalid"
                return None

        elif (
            self.cfg.allow_longs
            and dev_atr <= -float(self.cfg.min_vwap_dev_atr)
            and rsi <= float(self.cfg.long_rsi_max)
            and cur > open_cur
            and cur < vwap
        ):
            side = "long"
            sl = min(low_cur, entry) - float(self.cfg.sl_atr_mult) * atr
            tp1 = entry + (vwap - entry) * float(self.cfg.tp1_frac)
            tp2 = vwap + float(self.cfg.tp2_atr) * atr
            if sl >= entry or tp1 <= entry or tp2 <= tp1:
                self.last_no_signal_reason = "long_levels_invalid"
                return None

        else:
            self.last_no_signal_reason = "no_signal_conditions"
            return None

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy=self.NAME,
            symbol=store.symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[float(self.cfg.tp1_frac), 1.0 - float(self.cfg.tp1_frac)],
            trailing_atr_mult=0.0,
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"avw1_vwap_revert|vwap={vwap:.4f}|er={er:.3f}|rsi={rsi:.1f}|dev_atr={dev_atr:.2f}",
        )
        return sig if sig.validate() else None


def _same_day(row_ts_ms: float | int, ref_ts_ms: int) -> bool:
    try:
        row_day = datetime.fromtimestamp(float(row_ts_ms) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
        ref_day = datetime.fromtimestamp(ref_ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return False
    return row_day == ref_day
