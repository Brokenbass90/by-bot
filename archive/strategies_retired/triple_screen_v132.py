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


def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1.0 - k)
    return e


def _sma(values: List[float], period: int) -> float:
    if period <= 0 or len(values) < period:
        return float("nan")
    w = values[-period:]
    return sum(w) / float(period) if w else float("nan")


def _atr(h: List[float], l: List[float], c: List[float], period: int) -> float:
    if period <= 0 or len(c) < period + 1:
        return float("nan")
    trs = []
    for i in range(-period, 0):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
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


def _stoch(c: List[float], h: List[float], l: List[float], period: int) -> float:
    if period <= 0 or len(c) < period:
        return float("nan")
    hh = max(h[-period:])
    ll = min(l[-period:])
    if hh <= ll:
        return 50.0
    return 100.0 * (c[-1] - ll) / (hh - ll)


def _stoch_sma(c: List[float], h: List[float], l: List[float], period: int, smooth: int = 3) -> float:
    if smooth <= 1:
        return _stoch(c, h, l, period)
    vals = []
    for off in range(smooth):
        if len(c) - off < period:
            break
        end = None if off == 0 else -off
        vals.append(_stoch(c[:end], h[:end], l[:end], period))
    return sum(vals) / float(len(vals)) if vals else float("nan")


def _cci(c: List[float], h: List[float], l: List[float], period: int) -> float:
    if period <= 0 or len(c) < period:
        return float("nan")
    tp = [(h[i] + l[i] + c[i]) / 3.0 for i in range(len(c))]
    tp_w = tp[-period:]
    sma_tp = sum(tp_w) / float(period)
    md = sum(abs(x - sma_tp) for x in tp_w) / float(period)
    if md <= 1e-12:
        return 0.0
    return (tp[-1] - sma_tp) / (0.015 * md)


def _osc_value_for_series(osc_type: str, c: List[float], h: List[float], l: List[float], period: int) -> float:
    if osc_type == "rsi":
        return _rsi(c, period)
    if osc_type == "cci":
        return _cci(c, h, l, max(5, period))
    return _stoch_sma(c, h, l, period, smooth=3)


@dataclass
class TripleScreenV132Config:
    trade_mode: str = "active"  # conservative|active|aggressive
    trend_tf: str = "60"
    eval_tf_min: int = 60
    use_eval_tf_osc: bool = False
    trend_ema_len: int = 45
    use_trend_strength_filter: bool = False
    trend_slope_lookback: int = 8
    trend_min_gap_pct: float = 0.10
    trend_min_slope_pct: float = 0.05
    osc_type: str = "stoch"  # stoch|rsi|cci
    osc_period: int = 8
    osc_ob: float = 70.0
    osc_os: float = 30.0
    atr_period: int = 14
    sl_atr_mult: float = 2.0
    tp_atr_mult: float = 9.0
    be_pct: float = 3.0
    trail_atr_mult_long: float = 1.5
    trail_atr_mult_short: float = 2.0
    trail_activate_long_atr: float = 3.0
    trail_activate_short_atr: float = 4.0
    cooldown_conservative: int = 10
    cooldown_active: int = 5
    cooldown_aggressive: int = 2
    use_vol_filter: bool = False
    vol_mult: float = 0.5
    use_btc_filter: bool = False  # not supported in this backtest wrapper; kept for API parity
    max_signals_per_day: int = 4
    time_stop_bars_5m: int = 576
    exec_mode: str = "optimistic"  # optimistic|eth|alts
    allow_longs: bool = True
    allow_shorts: bool = True


class TripleScreenV132Strategy:
    """Approximation of TradingView Triple Screen v13.2 in backtest engine format."""

    def __init__(self, cfg: Optional[TripleScreenV132Config] = None):
        self.cfg = cfg or TripleScreenV132Config()
        self.cfg.trade_mode = str(os.getenv("TS132_TRADE_MODE", self.cfg.trade_mode)).strip().lower()
        self.cfg.trend_tf = os.getenv("TS132_TREND_TF", self.cfg.trend_tf)
        self.cfg.eval_tf_min = _env_int("TS132_EVAL_TF_MIN", self.cfg.eval_tf_min)
        self.cfg.use_eval_tf_osc = str(os.getenv("TS132_USE_EVAL_TF_OSC", "0")).strip().lower() in {"1", "true", "yes", "on"}
        self.cfg.trend_ema_len = _env_int("TS132_TREND_EMA_LEN", self.cfg.trend_ema_len)
        self.cfg.use_trend_strength_filter = str(os.getenv("TS132_USE_TREND_STRENGTH_FILTER", "0")).strip().lower() in {"1", "true", "yes", "on"}
        self.cfg.trend_slope_lookback = _env_int("TS132_TREND_SLOPE_LOOKBACK", self.cfg.trend_slope_lookback)
        self.cfg.trend_min_gap_pct = _env_float("TS132_TREND_MIN_GAP_PCT", self.cfg.trend_min_gap_pct)
        self.cfg.trend_min_slope_pct = _env_float("TS132_TREND_MIN_SLOPE_PCT", self.cfg.trend_min_slope_pct)
        self.cfg.osc_type = str(os.getenv("TS132_OSC_TYPE", self.cfg.osc_type)).strip().lower()
        self.cfg.osc_period = _env_int("TS132_OSC_PERIOD", self.cfg.osc_period)
        self.cfg.osc_ob = _env_float("TS132_OSC_OB", self.cfg.osc_ob)
        self.cfg.osc_os = _env_float("TS132_OSC_OS", self.cfg.osc_os)
        self.cfg.atr_period = _env_int("TS132_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.sl_atr_mult = _env_float("TS132_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp_atr_mult = _env_float("TS132_TP_ATR_MULT", self.cfg.tp_atr_mult)
        self.cfg.be_pct = _env_float("TS132_BE_PCT", self.cfg.be_pct)
        self.cfg.trail_atr_mult_long = _env_float("TS132_TRAIL_ATR_MULT_LONG", self.cfg.trail_atr_mult_long)
        self.cfg.trail_atr_mult_short = _env_float("TS132_TRAIL_ATR_MULT_SHORT", self.cfg.trail_atr_mult_short)
        self.cfg.trail_activate_long_atr = _env_float("TS132_TRAIL_ACTIVATE_LONG_ATR", self.cfg.trail_activate_long_atr)
        self.cfg.trail_activate_short_atr = _env_float("TS132_TRAIL_ACTIVATE_SHORT_ATR", self.cfg.trail_activate_short_atr)
        self.cfg.cooldown_conservative = _env_int("TS132_COOLDOWN_CONSERVATIVE", self.cfg.cooldown_conservative)
        self.cfg.cooldown_active = _env_int("TS132_COOLDOWN_ACTIVE", self.cfg.cooldown_active)
        self.cfg.cooldown_aggressive = _env_int("TS132_COOLDOWN_AGGRESSIVE", self.cfg.cooldown_aggressive)
        self.cfg.use_vol_filter = str(os.getenv("TS132_USE_VOL_FILTER", "0")).strip().lower() in {"1", "true", "yes", "on"}
        self.cfg.vol_mult = _env_float("TS132_VOL_MULT", self.cfg.vol_mult)
        self.cfg.use_btc_filter = str(os.getenv("TS132_USE_BTC_FILTER", "0")).strip().lower() in {"1", "true", "yes", "on"}
        self.cfg.max_signals_per_day = _env_int("TS132_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.time_stop_bars_5m = _env_int("TS132_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.exec_mode = str(os.getenv("TS132_EXEC_MODE", self.cfg.exec_mode)).strip().lower()
        self.cfg.allow_longs = str(os.getenv("TS132_ALLOW_LONGS", "1")).strip().lower() in {"1", "true", "yes", "on"}
        self.cfg.allow_shorts = str(os.getenv("TS132_ALLOW_SHORTS", "1")).strip().lower() in {"1", "true", "yes", "on"}

        self._c: List[float] = []
        self._h: List[float] = []
        self._l: List[float] = []
        self._v: List[float] = []
        self._cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0
        self._last_eval_bucket: Optional[int] = None

    def _cooldown_bars(self) -> int:
        if self.cfg.trade_mode.startswith("cons"):
            return self.cfg.cooldown_conservative
        if self.cfg.trade_mode.startswith("agg"):
            return self.cfg.cooldown_aggressive
        return self.cfg.cooldown_active

    def _slip_adj(self) -> float:
        if self.cfg.exec_mode == "eth":
            return 0.0002
        if self.cfg.exec_mode == "alts":
            return 0.0006
        return 0.0

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = o
        self._c.append(float(c))
        self._h.append(float(h))
        self._l.append(float(l))
        self._v.append(max(0.0, float(v or 0.0)))

        min_need = max(self.cfg.atr_period + 2, self.cfg.osc_period + 5, 30)
        if len(self._c) < min_need:
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

        # Trend screen on higher TF EMA
        rows_t = store.fetch_klines(
            store.symbol,
            self.cfg.trend_tf,
            max(self.cfg.trend_ema_len + self.cfg.trend_slope_lookback + 20, 120),
        ) or []
        if len(rows_t) < self.cfg.trend_ema_len + 3:
            return None
        t_closes = [float(r[4]) for r in rows_t]
        trend_ema = _ema(t_closes, self.cfg.trend_ema_len)
        if not math.isfinite(trend_ema):
            return None
        trend_up = self._c[-1] > trend_ema
        trend_down = self._c[-1] < trend_ema
        if self.cfg.use_trend_strength_filter:
            if len(t_closes) < self.cfg.trend_ema_len + self.cfg.trend_slope_lookback + 3:
                return None
            ema_prev = _ema(t_closes[:-self.cfg.trend_slope_lookback], self.cfg.trend_ema_len)
            if not math.isfinite(ema_prev):
                return None
            px = self._c[-1]
            if px <= 0:
                return None
            trend_gap_pct = abs(px - trend_ema) / px * 100.0
            trend_slope_pct = (trend_ema - ema_prev) / max(1e-12, abs(ema_prev)) * 100.0
            trend_up = trend_up and trend_gap_pct >= self.cfg.trend_min_gap_pct and trend_slope_pct >= self.cfg.trend_min_slope_pct
            trend_down = trend_down and trend_gap_pct >= self.cfg.trend_min_gap_pct and trend_slope_pct <= -self.cfg.trend_min_slope_pct

        # Oscillator screen on local TF or the intermediate eval TF.
        osc_c, osc_h, osc_l = self._c, self._h, self._l
        if self.cfg.use_eval_tf_osc:
            rows_e = store.fetch_klines(store.symbol, str(self.cfg.eval_tf_min), max(self.cfg.osc_period + 10, 60)) or []
            if len(rows_e) < max(self.cfg.osc_period + 4, 12):
                return None
            osc_c = [float(r[4]) for r in rows_e]
            osc_h = [float(r[2]) for r in rows_e]
            osc_l = [float(r[3]) for r in rows_e]

        osc = _osc_value_for_series(self.cfg.osc_type, osc_c, osc_h, osc_l, self.cfg.osc_period)
        osc_prev = _osc_value_for_series(self.cfg.osc_type, osc_c[:-1], osc_h[:-1], osc_l[:-1], self.cfg.osc_period)
        if not (math.isfinite(osc) and math.isfinite(osc_prev)):
            return None

        # Volume filter
        vol_ok = True
        if self.cfg.use_vol_filter:
            avg_vol = _sma(self._v, 20)
            vol_ok = math.isfinite(avg_vol) and self._v[-1] > avg_vol * self.cfg.vol_mult
        if not vol_ok:
            return None

        # BTC filter is not available in current strategy interface (no cross-symbol feed).
        if self.cfg.use_btc_filter:
            return None

        # Conditions by trade mode
        mode = self.cfg.trade_mode
        if mode.startswith("cons"):
            osc_long = (osc_prev < self.cfg.osc_os and osc >= self.cfg.osc_os)
            osc_short = (osc_prev > self.cfg.osc_ob and osc <= self.cfg.osc_ob)
        elif mode.startswith("agg"):
            osc_long = (osc < self.cfg.osc_os + 10.0 and osc > osc_prev)
            osc_short = (osc > self.cfg.osc_ob - 10.0 and osc < osc_prev)
        else:
            osc_long = (osc_prev <= self.cfg.osc_os and osc > self.cfg.osc_os) or (osc_prev < self.cfg.osc_os and osc >= self.cfg.osc_os)
            osc_short = (osc_prev >= self.cfg.osc_ob and osc < self.cfg.osc_ob) or (osc_prev > self.cfg.osc_ob and osc <= self.cfg.osc_ob)

        long_signal = trend_up and osc_long
        short_signal = trend_down and osc_short

        if mode.startswith("agg"):
            hh = max(self._h[-6:-1]) if len(self._h) >= 6 else self._h[-1]
            ll = min(self._l[-6:-1]) if len(self._l) >= 6 else self._l[-1]
            long_signal = long_signal or (trend_up and self._c[-1] > hh and vol_ok)
            short_signal = short_signal or (trend_down and self._c[-1] < ll and vol_ok)

        if not (long_signal or short_signal):
            return None

        atr_now = _atr(self._h, self._l, self._c, self.cfg.atr_period)
        if not (math.isfinite(atr_now) and atr_now > 0):
            return None

        slip_adj = self._slip_adj()
        entry = float(self._c[-1])
        risk = atr_now * float(self.cfg.sl_atr_mult)
        be_trigger_rr = 0.0
        if risk > 0 and self.cfg.be_pct > 0:
            be_trigger_rr = (entry * (float(self.cfg.be_pct) / 100.0)) / risk

        if self.cfg.allow_longs and long_signal:
            sl = entry - atr_now * self.cfg.sl_atr_mult
            tp = entry + atr_now * self.cfg.tp_atr_mult
            # pessimistic execution adjustment
            sl *= (1.0 - slip_adj)
            tp *= (1.0 - slip_adj)
            if sl < entry < tp:
                self._cooldown = self._cooldown_bars()
                self._day_signals += 1
                return TradeSignal(
                    strategy="triple_screen_v132",
                    symbol=getattr(store, "symbol", ""),
                    side="long",
                    entry=entry,
                    sl=sl,
                    tp=tp,
                    trailing_atr_mult=self.cfg.trail_atr_mult_long,
                    trailing_atr_period=self.cfg.atr_period,
                    trail_activate_rr=float(self.cfg.trail_activate_long_atr) / max(1e-12, float(self.cfg.sl_atr_mult)),
                    be_trigger_rr=be_trigger_rr,
                    be_lock_rr=0.0,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason=f"ts132_long_{mode}_{self.cfg.osc_type}",
                )

        if self.cfg.allow_shorts and short_signal:
            sl = entry + atr_now * self.cfg.sl_atr_mult
            tp = entry - atr_now * self.cfg.tp_atr_mult
            sl *= (1.0 + slip_adj)
            tp *= (1.0 + slip_adj)
            if tp < entry < sl:
                self._cooldown = self._cooldown_bars()
                self._day_signals += 1
                return TradeSignal(
                    strategy="triple_screen_v132",
                    symbol=getattr(store, "symbol", ""),
                    side="short",
                    entry=entry,
                    sl=sl,
                    tp=tp,
                    trailing_atr_mult=self.cfg.trail_atr_mult_short,
                    trailing_atr_period=self.cfg.atr_period,
                    trail_activate_rr=float(self.cfg.trail_activate_short_atr) / max(1e-12, float(self.cfg.sl_atr_mult)),
                    be_trigger_rr=be_trigger_rr,
                    be_lock_rr=0.0,
                    time_stop_bars=self.cfg.time_stop_bars_5m,
                    reason=f"ts132_short_{mode}_{self.cfg.osc_type}",
                )
        return None
