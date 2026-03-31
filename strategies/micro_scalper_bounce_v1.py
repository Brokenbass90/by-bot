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
class MicroScalperBounceV1Config:
    trend_tf: str = "15"
    trend_ema: int = 20
    trend_lookback: int = 30
    trend_min_slope_pct: float = 0.05
    entry_lookback: int = 50
    entry_ema: int = 9
    atr_period: int = 14
    touch_atr: float = 0.10
    reclaim_atr: float = 0.03
    min_body_atr: float = 0.16
    min_wick_atr: float = 0.08
    vol_mult: float = 0.0
    rr: float = 1.25
    sl_buffer_atr: float = 0.10
    max_signals_per_day: int = 8
    cooldown_bars: int = 1
    session_start_utc: int = 7
    session_end_utc: int = 17
    min_sl_atr: float = 0.12
    max_sl_atr: float = 1.2
    time_stop_bars: int = 12
    use_vwap_bias: bool = True
    min_vwap_dist_atr: float = 0.03
    min_tp_atr: float = 0.35
    allow_longs: bool = True
    allow_shorts: bool = True


class MicroScalperBounceV1Strategy:
    NAME = "micro_scalper_bounce_v1"

    def __init__(self, cfg: Optional[MicroScalperBounceV1Config] = None):
        self.cfg = cfg or MicroScalperBounceV1Config()
        self.cfg.trend_tf = os.getenv("MSBNC_TREND_TF", self.cfg.trend_tf)
        self.cfg.trend_ema = _env_int("MSBNC_TREND_EMA", self.cfg.trend_ema)
        self.cfg.trend_lookback = _env_int("MSBNC_TREND_LOOKBACK", self.cfg.trend_lookback)
        self.cfg.trend_min_slope_pct = _env_float("MSBNC_TREND_MIN_SLOPE_PCT", self.cfg.trend_min_slope_pct)
        self.cfg.entry_lookback = _env_int("MSBNC_ENTRY_LOOKBACK", self.cfg.entry_lookback)
        self.cfg.entry_ema = _env_int("MSBNC_ENTRY_EMA", self.cfg.entry_ema)
        self.cfg.atr_period = _env_int("MSBNC_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.touch_atr = _env_float("MSBNC_TOUCH_ATR", self.cfg.touch_atr)
        self.cfg.reclaim_atr = _env_float("MSBNC_RECLAIM_ATR", self.cfg.reclaim_atr)
        self.cfg.min_body_atr = _env_float("MSBNC_MIN_BODY_ATR", self.cfg.min_body_atr)
        self.cfg.min_wick_atr = _env_float("MSBNC_MIN_WICK_ATR", self.cfg.min_wick_atr)
        self.cfg.vol_mult = _env_float("MSBNC_VOL_MULT", self.cfg.vol_mult)
        self.cfg.rr = _env_float("MSBNC_RR", self.cfg.rr)
        self.cfg.sl_buffer_atr = _env_float("MSBNC_SL_BUFFER_ATR", self.cfg.sl_buffer_atr)
        self.cfg.max_signals_per_day = _env_int("MSBNC_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.cooldown_bars = _env_int("MSBNC_COOLDOWN_BARS", self.cfg.cooldown_bars)
        self.cfg.session_start_utc = _env_int("MSBNC_SESSION_START_UTC", self.cfg.session_start_utc)
        self.cfg.session_end_utc = _env_int("MSBNC_SESSION_END_UTC", self.cfg.session_end_utc)
        self.cfg.min_sl_atr = _env_float("MSBNC_MIN_SL_ATR", self.cfg.min_sl_atr)
        self.cfg.max_sl_atr = _env_float("MSBNC_MAX_SL_ATR", self.cfg.max_sl_atr)
        self.cfg.time_stop_bars = _env_int("MSBNC_TIME_STOP_BARS", self.cfg.time_stop_bars)
        self.cfg.use_vwap_bias = _env_bool("MSBNC_USE_VWAP_BIAS", self.cfg.use_vwap_bias)
        self.cfg.min_vwap_dist_atr = _env_float("MSBNC_MIN_VWAP_DIST_ATR", self.cfg.min_vwap_dist_atr)
        self.cfg.min_tp_atr = _env_float("MSBNC_MIN_TP_ATR", self.cfg.min_tp_atr)
        self.cfg.allow_longs = _env_bool("MSBNC_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("MSBNC_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("MSBNC_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("MSBNC_SYMBOL_DENYLIST")
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
        if not entry_rows or len(entry_rows) < max(self.cfg.atr_period + 2, self.cfg.entry_ema + 2, 20):
            self.last_no_signal_reason = "entry_data"
            return None
        atr = _atr(entry_rows, self.cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = "atr_nan"
            return None
        entry_closes = [float(r[4]) for r in entry_rows]
        ema9 = _ema(entry_closes, self.cfg.entry_ema)
        if not math.isfinite(ema9) or ema9 <= 0:
            self.last_no_signal_reason = "ema_nan"
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

        if self.cfg.vol_mult > 0 and v > 0:
            vols = [float(r[5]) for r in entry_rows[:-1] if float(r[5]) > 0]
            lookback_v = min(20, len(vols))
            if lookback_v >= 5:
                avg_vol = sum(vols[-lookback_v:]) / float(lookback_v)
                if avg_vol > 0 and v < self.cfg.vol_mult * avg_vol:
                    self.last_no_signal_reason = "vol_weak"
                    return None

        entry_price = c
        fp_sl_mult = _fp.scale(sym, "sl", 1.0) if _FP_ENABLED else 1.0
        fp_tp_mult = _fp.scale(sym, "tp", 1.0) if _FP_ENABLED else 1.0
        fp_cd_mult = _fp.scale(sym, "cooldown", 1.0) if _FP_ENABLED else 1.0
        sl_buf = self.cfg.sl_buffer_atr * fp_sl_mult
        rr_scaled = self.cfg.rr * fp_tp_mult

        if trend == "long":
            lower_wick = min(o, c) - l
            if lower_wick < self.cfg.min_wick_atr * atr:
                self.last_no_signal_reason = "wick_small"
                return None
            if l > ema9 - self.cfg.touch_atr * atr:
                self.last_no_signal_reason = "no_ema_touch"
                return None
            if c < ema9 + self.cfg.reclaim_atr * atr or body <= 0:
                self.last_no_signal_reason = "no_reclaim"
                return None
            prev_l = float(entry_rows[-2][3])
            swing_low = min(l, prev_l)
            sl = swing_low - sl_buf * atr
            sl_dist = entry_price - sl
            tp = entry_price + rr_scaled * sl_dist
        else:
            upper_wick = h - max(o, c)
            if upper_wick < self.cfg.min_wick_atr * atr:
                self.last_no_signal_reason = "wick_small"
                return None
            if h < ema9 + self.cfg.touch_atr * atr:
                self.last_no_signal_reason = "no_ema_touch"
                return None
            if c > ema9 - self.cfg.reclaim_atr * atr or body >= 0:
                self.last_no_signal_reason = "no_reclaim"
                return None
            prev_h = float(entry_rows[-2][2])
            swing_high = max(h, prev_h)
            sl = swing_high + sl_buf * atr
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
            reason=f"bounce_{trend}|ema9={ema9:.2f}|vwap={session_vwap:.2f}|atr={atr:.4f}|slope={slope_pct:+.3f}%"
        )
        if not sig.validate():
            self.last_no_signal_reason = "validate_fail"
            return None
        self._cooldown = max(1, round(self.cfg.cooldown_bars * fp_cd_mult))
        self._day_signals += 1
        self.last_no_signal_reason = ""
        return sig
