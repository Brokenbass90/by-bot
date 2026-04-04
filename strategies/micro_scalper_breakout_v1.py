from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from .signals import TradeSignal

try:
    from bot.family_profiles import profiles as _fp
    _FP_ENABLED = True
except ImportError:
    _fp = None  # type: ignore[assignment]
    _FP_ENABLED = False


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
    n = len(values)
    if n < 1:
        return float("nan")
    p = min(period, n)
    ema = sum(values[:p]) / float(p)
    alpha = 2.0 / (period + 1.0)
    for v in values[p:]:
        ema = alpha * v + (1.0 - alpha) * ema
    return ema


def _atr(rows: List[list], period: int) -> float:
    if len(rows) < period + 1:
        return float("nan")
    trs: List[float] = []
    for i in range(1, len(rows)):
        h = float(rows[i][2])
        l = float(rows[i][3])
        pc = float(rows[i - 1][4])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return float("nan")
    atr = sum(trs[:period]) / float(period)
    alpha = 1.0 / float(period)
    for tr in trs[period:]:
        atr = (1.0 - alpha) * atr + alpha * tr
    return atr


def _utc_hour(ts_ms: int) -> int:
    try:
        return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).hour
    except Exception:
        return -1


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
class MicroScalperBreakoutV1Config:
    trend_tf: str = "15"
    trend_ema: int = 20
    trend_lookback: int = 30
    trend_min_slope_pct: float = 0.06
    entry_lookback: int = 50
    atr_period: int = 14
    breakout_lookback: int = 6
    breakout_buffer_atr: float = 0.05
    min_body_atr: float = 0.22
    min_close_frac: float = 0.65
    vol_mult: float = 0.0
    rr: float = 1.50          # was 1.10 — deeply sub-breakeven after 20bps fees
    sl_buffer_atr: float = 0.10
    max_signals_per_day: int = 6
    cooldown_bars: int = 3    # was 1 — prevents cascading false breakout entries
    session_start_utc: int = 7
    session_end_utc: int = 22
    min_sl_atr: float = 0.12
    max_sl_atr: float = 1.0
    time_stop_bars: int = 20  # was 8 — too short; breakout follow-through needs more room
    use_vwap_bias: bool = True
    min_vwap_dist_atr: float = 0.05
    min_tp_atr: float = 0.30
    allow_longs: bool = True
    allow_shorts: bool = True


class MicroScalperBreakoutV1Strategy:
    NAME = "micro_scalper_breakout_v1"

    def __init__(self, cfg: Optional[MicroScalperBreakoutV1Config] = None):
        self.cfg = cfg or MicroScalperBreakoutV1Config()
        self.cfg.trend_tf = os.getenv("MSBRK_TREND_TF", self.cfg.trend_tf)
        self.cfg.trend_ema = _env_int("MSBRK_TREND_EMA", self.cfg.trend_ema)
        self.cfg.trend_lookback = _env_int("MSBRK_TREND_LOOKBACK", self.cfg.trend_lookback)
        self.cfg.trend_min_slope_pct = _env_float("MSBRK_TREND_MIN_SLOPE_PCT", self.cfg.trend_min_slope_pct)
        self.cfg.entry_lookback = _env_int("MSBRK_ENTRY_LOOKBACK", self.cfg.entry_lookback)
        self.cfg.atr_period = _env_int("MSBRK_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.breakout_lookback = _env_int("MSBRK_BREAKOUT_LOOKBACK", self.cfg.breakout_lookback)
        self.cfg.breakout_buffer_atr = _env_float("MSBRK_BREAKOUT_BUFFER_ATR", self.cfg.breakout_buffer_atr)
        self.cfg.min_body_atr = _env_float("MSBRK_MIN_BODY_ATR", self.cfg.min_body_atr)
        self.cfg.min_close_frac = _env_float("MSBRK_MIN_CLOSE_FRAC", self.cfg.min_close_frac)
        self.cfg.vol_mult = _env_float("MSBRK_VOL_MULT", self.cfg.vol_mult)
        self.cfg.rr = _env_float("MSBRK_RR", self.cfg.rr)
        self.cfg.sl_buffer_atr = _env_float("MSBRK_SL_BUFFER_ATR", self.cfg.sl_buffer_atr)
        self.cfg.max_signals_per_day = _env_int("MSBRK_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.cooldown_bars = _env_int("MSBRK_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.session_start_utc = _env_int("MSBRK_SESSION_START_UTC", self.cfg.session_start_utc)
        self.cfg.session_end_utc = _env_int("MSBRK_SESSION_END_UTC", self.cfg.session_end_utc)
        self.cfg.min_sl_atr = _env_float("MSBRK_MIN_SL_ATR", self.cfg.min_sl_atr)
        self.cfg.max_sl_atr = _env_float("MSBRK_MAX_SL_ATR", self.cfg.max_sl_atr)
        self.cfg.time_stop_bars = _env_int("MSBRK_TIME_STOP_BARS", self.cfg.time_stop_bars)
        self.cfg.use_vwap_bias = _env_bool("MSBRK_USE_VWAP_BIAS", self.cfg.use_vwap_bias)
        self.cfg.min_vwap_dist_atr = _env_float("MSBRK_MIN_VWAP_DIST_ATR", self.cfg.min_vwap_dist_atr)
        self.cfg.min_tp_atr = _env_float("MSBRK_MIN_TP_ATR", self.cfg.min_tp_atr)
        self.cfg.allow_longs = _env_bool("MSBRK_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("MSBRK_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("MSBRK_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("MSBRK_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._day_signals = 0
        self._last_day = -1
        self.last_no_signal_reason = ""

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            self.last_no_signal_reason = "symbol_allow"
            return None
        if sym in self._deny:
            self.last_no_signal_reason = "symbol_deny"
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            self.last_no_signal_reason = "cooldown"
            return None
        hour = _utc_hour(ts_ms)
        if hour < self.cfg.session_start_utc or hour >= self.cfg.session_end_utc:
            self.last_no_signal_reason = "session"
            return None
        day = ts_ms // 86_400_000
        if day != self._last_day:
            self._last_day = day
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            self.last_no_signal_reason = "daily_cap"
            return None

        trend_rows = store.fetch_klines(sym, self.cfg.trend_tf, self.cfg.trend_lookback)
        if not trend_rows or len(trend_rows) < max(self.cfg.trend_ema + 3, 10):
            self.last_no_signal_reason = "trend_data"
            return None
        trend_closes = [float(r[4]) for r in trend_rows]
        ema_now = _ema(trend_closes, self.cfg.trend_ema)
        ema_lag = _ema(trend_closes[:-3], self.cfg.trend_ema)
        if not math.isfinite(ema_now) or not math.isfinite(ema_lag) or ema_lag <= 0:
            self.last_no_signal_reason = "trend_nan"
            return None
        slope_pct = (ema_now - ema_lag) / ema_lag * 100.0
        if abs(slope_pct) < self.cfg.trend_min_slope_pct:
            self.last_no_signal_reason = "trend_flat"
            return None
        trend = "long" if slope_pct > 0 else "short"
        if trend == "long" and not self.cfg.allow_longs:
            self.last_no_signal_reason = "longs_off"
            return None
        if trend == "short" and not self.cfg.allow_shorts:
            self.last_no_signal_reason = "shorts_off"
            return None

        entry_rows = store.fetch_klines(sym, "5", self.cfg.entry_lookback)
        if not entry_rows or len(entry_rows) < max(self.cfg.atr_period + 2, self.cfg.breakout_lookback + 2, 20):
            self.last_no_signal_reason = "entry_data"
            return None
        atr = _atr(entry_rows, self.cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = "atr_nan"
            return None
        session_vwap = _session_vwap(entry_rows, ts_ms)
        if self.cfg.use_vwap_bias:
            if not math.isfinite(session_vwap) or session_vwap <= 0:
                self.last_no_signal_reason = "vwap_nan"
                return None
            vwap_dist_atr = (c - session_vwap) / atr
            if trend == "long" and vwap_dist_atr < self.cfg.min_vwap_dist_atr:
                self.last_no_signal_reason = "vwap_bias"
                return None
            if trend == "short" and vwap_dist_atr > -self.cfg.min_vwap_dist_atr:
                self.last_no_signal_reason = "vwap_bias"
                return None
        body = c - o
        abs_body = abs(body)
        if abs_body < self.cfg.min_body_atr * atr:
            self.last_no_signal_reason = "body_weak"
            return None
        bar_range = max(1e-12, h - l)
        close_frac = (c - l) / bar_range if trend == "long" else (h - c) / bar_range
        if close_frac < self.cfg.min_close_frac:
            self.last_no_signal_reason = "close_weak"
            return None

        if self.cfg.vol_mult > 0 and v > 0:
            vols = [float(r[5]) for r in entry_rows[:-1] if float(r[5]) > 0]
            lookback_v = min(20, len(vols))
            if lookback_v >= 5:
                avg_vol = sum(vols[-lookback_v:]) / float(lookback_v)
                if avg_vol > 0 and v < self.cfg.vol_mult * avg_vol:
                    self.last_no_signal_reason = "vol_weak"
                    return None

        highs = [float(r[2]) for r in entry_rows[:-1]]
        lows = [float(r[3]) for r in entry_rows[:-1]]
        recent_high = max(highs[-self.cfg.breakout_lookback:])
        recent_low = min(lows[-self.cfg.breakout_lookback:])
        entry_price = c
        fp_sl_mult = _fp.scale(sym, "sl", 1.0) if _FP_ENABLED else 1.0
        fp_tp_mult = _fp.scale(sym, "tp", 1.0) if _FP_ENABLED else 1.0
        fp_cd_mult = _fp.scale(sym, "cooldown", 1.0) if _FP_ENABLED else 1.0
        sl_buf = self.cfg.sl_buffer_atr * fp_sl_mult
        rr_scaled = self.cfg.rr * fp_tp_mult

        if trend == "long":
            if body <= 0 or c <= recent_high + self.cfg.breakout_buffer_atr * atr:
                self.last_no_signal_reason = "no_breakout"
                return None
            sl = min(l, recent_high) - sl_buf * atr
            sl_dist = entry_price - sl
            tp = entry_price + rr_scaled * sl_dist
        else:
            if body >= 0 or c >= recent_low - self.cfg.breakout_buffer_atr * atr:
                self.last_no_signal_reason = "no_breakout"
                return None
            sl = max(h, recent_low) + sl_buf * atr
            sl_dist = sl - entry_price
            tp = entry_price - rr_scaled * sl_dist

        if sl_dist <= 0:
            self.last_no_signal_reason = "sl_invalid"
            return None
        sl_in_atr = sl_dist / atr
        if sl_in_atr < self.cfg.min_sl_atr:
            self.last_no_signal_reason = "sl_too_tight"
            return None
        if sl_in_atr > self.cfg.max_sl_atr:
            self.last_no_signal_reason = "sl_too_wide"
            return None
        tp_in_atr = rr_scaled * sl_in_atr
        if tp_in_atr < self.cfg.min_tp_atr:
            self.last_no_signal_reason = "edge_too_small"
            return None

        sig = TradeSignal(
            strategy=self.NAME,
            symbol=sym,
            side=trend,
            entry=entry_price,
            sl=sl,
            tp=tp,
            time_stop_bars=self.cfg.time_stop_bars,
            reason=f"breakout_{trend}|vwap={session_vwap:.2f}|atr={atr:.4f}|slope={slope_pct:+.3f}%|close_frac={close_frac:.2f}"
        )
        if not sig.validate():
            self.last_no_signal_reason = "validate_fail"
            return None
        self._cooldown = max(1, round(self.cfg.cooldown_bars * fp_cd_mult))
        self._day_signals += 1
        self.last_no_signal_reason = ""
        return sig
