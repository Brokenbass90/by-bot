from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .signals import TradeSignal

# Family-profile scaling (BTC_ETH tighter SL, MID_ALTS wider SL/TP/cooldown)
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


def _linear_regression(values: List[float]) -> Tuple[float, float]:
    n = len(values)
    if n < 2:
        return float("nan"), float("nan")
    xs = list(range(n))
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / float(n)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den <= 1e-12:
        return 0.0, y_mean
    m = num / den
    b = y_mean - m * x_mean
    return m, b


@dataclass
class AltSlopedChannelV1Config:
    signal_tf: str = "60"
    signal_lookback: int = 96
    atr_period: int = 14
    min_channel_width_pct: float = 4.0
    max_channel_width_pct: float = 22.0
    max_abs_slope_pct: float = 3.2
    min_abs_slope_pct: float = 0.05
    min_body_frac: float = 0.22
    touch_buffer_atr: float = 0.40
    reclaim_atr: float = 0.12
    reject_atr: float = 0.12
    min_range_r2: float = 0.25
    rsi_period: int = 14
    long_max_rsi: float = 46.0
    short_min_rsi: float = 56.0
    short_min_reject_depth_atr: float = 0.0
    short_min_upper_wick_frac: float = 0.0
    touch_count_lookback_bars: int = 24
    short_min_upper_touches: int = 0
    short_pre_touch_lookback_bars: int = 6
    short_near_upper_atr: float = 0.20
    short_max_near_upper_bars: int = 999
    short_vol_avg_bars: int = 20
    short_min_reject_vol_mult: float = 0.0
    allow_longs: bool = True
    allow_shorts: bool = True

    sl_atr_mult: float = 0.90
    tp1_frac: float = 0.55
    tp2_buffer_pct: float = 0.40
    be_trigger_rr: float = 0.0
    be_lock_rr: float = 0.0
    # ATR trailing stop: 0.0 = disabled, e.g. 1.5 = trail at 1.5*ATR below peak
    trail_atr_mult: float = 0.0
    trail_atr_period: int = 14
    time_stop_bars_5m: int = 480
    cooldown_bars_5m: int = 72
    # 5m entry confirmation: wait N 5m bars after 1h setup for confirming candle
    # 0 = disabled (fire immediately on 1h close, old behavior)
    # 3-6 = wait 15-30 min for bearish/bullish 5m confirmation candle
    confirm_5m_bars: int = 0


class AltSlopedChannelV1Strategy:
    """Mean-reversion inside a sloped 1h channel for liquid alts."""

    def __init__(self, cfg: Optional[AltSlopedChannelV1Config] = None):
        self.cfg = cfg or AltSlopedChannelV1Config()

        self.cfg.signal_tf = os.getenv("ASC1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_lookback = _env_int("ASC1_SIGNAL_LOOKBACK", self.cfg.signal_lookback)
        self.cfg.atr_period = _env_int("ASC1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.min_channel_width_pct = _env_float("ASC1_MIN_CHANNEL_WIDTH_PCT", self.cfg.min_channel_width_pct)
        self.cfg.max_channel_width_pct = _env_float("ASC1_MAX_CHANNEL_WIDTH_PCT", self.cfg.max_channel_width_pct)
        self.cfg.max_abs_slope_pct = _env_float("ASC1_MAX_ABS_SLOPE_PCT", self.cfg.max_abs_slope_pct)
        self.cfg.min_abs_slope_pct = _env_float("ASC1_MIN_ABS_SLOPE_PCT", self.cfg.min_abs_slope_pct)
        self.cfg.min_body_frac = _env_float("ASC1_MIN_BODY_FRAC", self.cfg.min_body_frac)
        self.cfg.touch_buffer_atr = _env_float("ASC1_TOUCH_BUFFER_ATR", self.cfg.touch_buffer_atr)
        self.cfg.reclaim_atr = _env_float("ASC1_RECLAIM_ATR", self.cfg.reclaim_atr)
        self.cfg.reject_atr = _env_float("ASC1_REJECT_ATR", self.cfg.reject_atr)
        self.cfg.min_range_r2 = _env_float("ASC1_MIN_RANGE_R2", self.cfg.min_range_r2)
        self.cfg.rsi_period = _env_int("ASC1_RSI_PERIOD", self.cfg.rsi_period)
        self.cfg.long_max_rsi = _env_float("ASC1_LONG_MAX_RSI", self.cfg.long_max_rsi)
        self.cfg.short_min_rsi = _env_float("ASC1_SHORT_MIN_RSI", self.cfg.short_min_rsi)
        self.cfg.short_min_reject_depth_atr = _env_float(
            "ASC1_SHORT_MIN_REJECT_DEPTH_ATR",
            self.cfg.short_min_reject_depth_atr,
        )
        self.cfg.short_min_upper_wick_frac = _env_float(
            "ASC1_SHORT_MIN_UPPER_WICK_FRAC",
            self.cfg.short_min_upper_wick_frac,
        )
        self.cfg.touch_count_lookback_bars = _env_int(
            "ASC1_TOUCH_COUNT_LOOKBACK_BARS",
            self.cfg.touch_count_lookback_bars,
        )
        self.cfg.short_min_upper_touches = _env_int(
            "ASC1_SHORT_MIN_UPPER_TOUCHES",
            self.cfg.short_min_upper_touches,
        )
        self.cfg.short_pre_touch_lookback_bars = _env_int(
            "ASC1_SHORT_PRE_TOUCH_LOOKBACK_BARS",
            self.cfg.short_pre_touch_lookback_bars,
        )
        self.cfg.short_near_upper_atr = _env_float(
            "ASC1_SHORT_NEAR_UPPER_ATR",
            self.cfg.short_near_upper_atr,
        )
        self.cfg.short_max_near_upper_bars = _env_int(
            "ASC1_SHORT_MAX_NEAR_UPPER_BARS",
            self.cfg.short_max_near_upper_bars,
        )
        self.cfg.short_vol_avg_bars = _env_int(
            "ASC1_SHORT_VOL_AVG_BARS",
            self.cfg.short_vol_avg_bars,
        )
        self.cfg.short_min_reject_vol_mult = _env_float(
            "ASC1_SHORT_MIN_REJECT_VOL_MULT",
            self.cfg.short_min_reject_vol_mult,
        )
        self.cfg.allow_longs = _env_bool("ASC1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("ASC1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self.cfg.sl_atr_mult = _env_float("ASC1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_frac = _env_float("ASC1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.tp2_buffer_pct = _env_float("ASC1_TP2_BUFFER_PCT", self.cfg.tp2_buffer_pct)
        self.cfg.be_trigger_rr = _env_float("ASC1_BE_TRIGGER_RR", self.cfg.be_trigger_rr)
        self.cfg.be_lock_rr = _env_float("ASC1_BE_LOCK_RR", self.cfg.be_lock_rr)
        self.cfg.trail_atr_mult = _env_float("ASC1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.trail_atr_period = _env_int("ASC1_TRAIL_ATR_PERIOD", self.cfg.trail_atr_period)
        self.cfg.time_stop_bars_5m = _env_int("ASC1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("ASC1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.confirm_5m_bars = _env_int("ASC1_CONFIRM_5M_BARS", self.cfg.confirm_5m_bars)

        self._allow = _env_csv_set(
            "ASC1_SYMBOL_ALLOWLIST",
            "ADAUSDT,DOGEUSDT,LINKUSDT,LTCUSDT,BCHUSDT,ATOMUSDT,BNBUSDT,ETCUSDT",
        )
        self._deny = _env_csv_set("ASC1_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        # pending 5m confirmation state:
        # {side, sl, tp, tp1, upper_band, lower_band, atr, timeout_bars}
        self._pending: Optional[Dict] = None
        self._pending_bars_left: int = 0

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, c, v)
        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None
        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        # ── 5m CONFIRMATION CHECK ─────────────────────────────────────
        # If we have a pending 1h setup, check each 5m bar for entry confirmation.
        if self._pending is not None and self.cfg.confirm_5m_bars > 0:
            p = self._pending
            self._pending_bars_left -= 1
            confirmed = False
            invalidated = False

            if p["side"] == "short":
                # Confirm: bearish 5m candle that stays below upper band
                bearish = c < o and (o - c) > 0.05 * p["atr"]
                still_below = h < p["upper_band"] + p["atr"] * 0.15
                confirmed = bearish and still_below
                # Invalidate: price breaks clearly above upper band
                invalidated = c > p["upper_band"] + p["atr"] * 0.30
            else:  # long
                # Confirm: bullish 5m candle that stays above lower band
                bullish = c > o and (c - o) > 0.05 * p["atr"]
                still_above = l > p["lower_band"] - p["atr"] * 0.15
                confirmed = bullish and still_above
                # Invalidate: price breaks clearly below lower band
                invalidated = c < p["lower_band"] - p["atr"] * 0.30

            if confirmed:
                # Build the signal with current 5m price as entry
                entry  = float(c)
                sym_fp = str(getattr(store, "symbol", "")).upper()

                # Family-profile scaling: adjust SL dist and TP dist by multiplier
                fp_sl_mult = _fp.scale(sym_fp, "sl",      1.0) if _FP_ENABLED else 1.0
                fp_tp_mult = _fp.scale(sym_fp, "tp",      1.0) if _FP_ENABLED else 1.0
                fp_cd_mult = _fp.scale(sym_fp, "cooldown", 1.0) if _FP_ENABLED else 1.0

                # Recompute SL/TP around the new entry, applying family multipliers
                base_sl = float(p["sl"]) + (entry - p["entry_ref"])
                sl_dist_base = abs(entry - base_sl)
                sl_dist_fp   = sl_dist_base * fp_sl_mult
                tp_dist_base = abs(float(p["tp2"]) - p["entry_ref"])
                tp_dist_fp   = tp_dist_base * fp_tp_mult
                tp1_dist_base = abs(float(p["tp1"]) - p["entry_ref"])
                tp1_dist_fp   = tp1_dist_base * fp_tp_mult

                if p["side"] == "long":
                    sl_fp  = entry - sl_dist_fp
                    tp2_fp = entry + tp_dist_fp
                    tp1_fp = entry + tp1_dist_fp
                else:
                    sl_fp  = entry + sl_dist_fp
                    tp2_fp = entry - tp_dist_fp
                    tp1_fp = entry - tp1_dist_fp

                self._pending = None
                self._pending_bars_left = 0
                self._cooldown = max(1, round(self.cfg.cooldown_bars_5m * fp_cd_mult))

                fp_label = f"|fp={_fp.family_name(sym_fp)}" if _FP_ENABLED else ""
                sig = TradeSignal(
                    strategy="alt_sloped_channel_v1",
                    symbol=store.symbol,
                    side=p["side"],
                    entry=entry,
                    sl=sl_fp,
                    tp=tp2_fp,
                    tps=[tp1_fp, tp2_fp],
                    tp_fracs=[min(0.9, max(0.1, self.cfg.tp1_frac)), max(0.0, 1.0 - min(0.9, max(0.1, self.cfg.tp1_frac)))],
                    be_trigger_rr=max(0.0, float(self.cfg.be_trigger_rr)),
                    be_lock_rr=max(0.0, float(self.cfg.be_lock_rr)),
                    trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
                    trailing_atr_period=max(5, int(self.cfg.trail_atr_period)),
                    time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
                    reason=f"asc1_sloped_channel_{p['side']}_5m_confirm{fp_label}",
                )
                if sig.validate():
                    return sig

            if invalidated or self._pending_bars_left <= 0:
                self._pending = None
                self._pending_bars_left = 0
            return None
        # ── END 5m CONFIRMATION CHECK ─────────────────────────────────

        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, self.cfg.signal_lookback) or []
        if len(rows) < self.cfg.signal_lookback:
            return None

        tf_ts = int(float(rows[-1][0]))
        if self._last_tf_ts is None:
            self._last_tf_ts = tf_ts
            return None
        if tf_ts == self._last_tf_ts:
            return None
        self._last_tf_ts = tf_ts

        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        opens = [float(r[1]) for r in rows]
        vols = [float(r[5]) if len(r) > 5 and r[5] not in (None, "", "nan") else 0.0 for r in rows]

        cur = closes[-1]
        prev = closes[-2]
        atr = _atr_from_rows(rows, self.cfg.atr_period)
        rsi = _rsi(closes, self.cfg.rsi_period)
        if not all(math.isfinite(x) for x in (atr, rsi)) or cur <= 0 or atr <= 0:
            return None

        slope, intercept = _linear_regression(closes)
        if not (math.isfinite(slope) and math.isfinite(intercept)):
            return None
        n = len(closes)
        fit = [slope * i + intercept for i in range(n)]
        residual_high = [h_i - f_i for h_i, f_i in zip(highs, fit)]
        residual_low = [l_i - f_i for l_i, f_i in zip(lows, fit)]
        upper_off = max(residual_high)
        lower_off = min(residual_low)
        if not (math.isfinite(upper_off) and math.isfinite(lower_off)):
            return None

        fit_now = fit[-1]
        upper = fit_now + upper_off
        lower = fit_now + lower_off
        width = upper - lower
        width_pct = width / max(1e-12, cur) * 100.0
        slope_pct = abs(slope) / max(1e-12, abs(fit_now)) * 100.0 * 24.0
        if width <= 0:
            return None
        if width_pct < self.cfg.min_channel_width_pct or width_pct > self.cfg.max_channel_width_pct:
            return None
        if slope_pct < self.cfg.min_abs_slope_pct or slope_pct > self.cfg.max_abs_slope_pct:
            return None

        y_mean = sum(closes) / float(n)
        ss_tot = sum((x - y_mean) ** 2 for x in closes)
        ss_res = sum((x - f) ** 2 for x, f in zip(closes, fit))
        r2 = 1.0 - ss_res / max(1e-12, ss_tot)
        if r2 < self.cfg.min_range_r2:
            return None

        low_now = lows[-1]
        high_now = highs[-1]
        body = abs(cur - opens[-1])
        bar_range = max(1e-12, high_now - low_now)
        body_frac = body / bar_range
        upper_wick_frac = max(0.0, high_now - max(cur, opens[-1])) / bar_range
        reject_depth_atr = max(0.0, upper - cur) / max(1e-12, atr)
        touch_look = max(3, min(n - 1, int(self.cfg.touch_count_lookback_bars)))
        upper_touch_count = 0
        for idx in range(n - touch_look - 1, n - 1):
            bound_upper = fit[idx] + upper_off
            if highs[idx] >= bound_upper - self.cfg.touch_buffer_atr * atr:
                upper_touch_count += 1
        pre_touch_look = max(2, min(n - 1, int(self.cfg.short_pre_touch_lookback_bars)))
        near_upper_count = 0
        near_upper_band = max(0.0, float(self.cfg.short_near_upper_atr)) * atr
        for idx in range(n - pre_touch_look - 1, n - 1):
            bound_upper = fit[idx] + upper_off
            if highs[idx] >= bound_upper - near_upper_band or closes[idx] >= bound_upper - near_upper_band:
                near_upper_count += 1
        short_vol_avg = 0.0
        vol_look = max(2, min(n - 1, int(self.cfg.short_vol_avg_bars)))
        hist_vols = [v for v in vols[-vol_look - 1:-1] if math.isfinite(v) and v > 0]
        if hist_vols:
            short_vol_avg = sum(hist_vols) / float(len(hist_vols))
        reject_vol_mult = (vols[-1] / short_vol_avg) if short_vol_avg > 0 else 0.0
        if body_frac < self.cfg.min_body_frac:
            return None

        touched_lower = low_now <= lower + self.cfg.touch_buffer_atr * atr
        reclaimed_lower = cur >= lower + self.cfg.reclaim_atr * atr and cur > prev
        touched_upper = high_now >= upper - self.cfg.touch_buffer_atr * atr
        rejected_upper = cur <= upper - self.cfg.reject_atr * atr and cur < prev

        long_bias_ok = slope >= -abs(fit_now) * 0.00025
        short_bias_ok = slope <= abs(fit_now) * 0.00025

        if self.cfg.allow_longs and long_bias_ok and touched_lower and reclaimed_lower and rsi <= self.cfg.long_max_rsi:
            sl = min(low_now, lower) - self.cfg.sl_atr_mult * atr
            tp2 = upper - self.cfg.tp2_buffer_pct / 100.0 * width
            if sl < cur < tp2:
                tp1 = cur + (tp2 - cur) * 0.55
                if self.cfg.confirm_5m_bars > 0:
                    # Queue for 5m confirmation instead of firing immediately
                    self._pending = {
                        "side": "long", "entry_ref": float(cur),
                        "sl": float(sl), "tp2": float(tp2), "tp1": float(tp1),
                        "upper_band": float(upper), "lower_band": float(lower), "atr": float(atr),
                    }
                    self._pending_bars_left = max(1, int(self.cfg.confirm_5m_bars))
                    return None
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                sig = TradeSignal(
                    strategy="alt_sloped_channel_v1",
                    symbol=store.symbol,
                    side="long",
                    entry=float(cur),
                    sl=float(sl),
                    tp=float(tp2),
                    tps=[float(tp1), float(tp2)],
                    tp_fracs=[min(0.9, max(0.1, self.cfg.tp1_frac)), max(0.0, 1.0 - min(0.9, max(0.1, self.cfg.tp1_frac)))],
                    be_trigger_rr=max(0.0, float(self.cfg.be_trigger_rr)),
                    be_lock_rr=max(0.0, float(self.cfg.be_lock_rr)),
                    trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
                    trailing_atr_period=max(5, int(self.cfg.trail_atr_period)),
                    time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
                    reason="asc1_sloped_channel_long",
                )
                if sig.validate():
                    return sig

        if (
            self.cfg.allow_shorts
            and short_bias_ok
            and touched_upper
            and rejected_upper
            and rsi >= self.cfg.short_min_rsi
            and reject_depth_atr >= self.cfg.short_min_reject_depth_atr
            and upper_wick_frac >= self.cfg.short_min_upper_wick_frac
            and upper_touch_count >= self.cfg.short_min_upper_touches
            and near_upper_count <= self.cfg.short_max_near_upper_bars
            and (
                self.cfg.short_min_reject_vol_mult <= 0.0
                or (short_vol_avg > 0 and reject_vol_mult >= self.cfg.short_min_reject_vol_mult)
            )
        ):
            sl = max(high_now, upper) + self.cfg.sl_atr_mult * atr
            tp2 = lower + self.cfg.tp2_buffer_pct / 100.0 * width
            if tp2 < cur < sl:
                tp1 = cur - (cur - tp2) * 0.55
                if self.cfg.confirm_5m_bars > 0:
                    # Queue for 5m confirmation instead of firing immediately
                    self._pending = {
                        "side": "short", "entry_ref": float(cur),
                        "sl": float(sl), "tp2": float(tp2), "tp1": float(tp1),
                        "upper_band": float(upper), "lower_band": float(lower), "atr": float(atr),
                    }
                    self._pending_bars_left = max(1, int(self.cfg.confirm_5m_bars))
                    return None
                self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                sig = TradeSignal(
                    strategy="alt_sloped_channel_v1",
                    symbol=store.symbol,
                    side="short",
                    entry=float(cur),
                    sl=float(sl),
                    tp=float(tp2),
                    tps=[float(tp1), float(tp2)],
                    tp_fracs=[min(0.9, max(0.1, self.cfg.tp1_frac)), max(0.0, 1.0 - min(0.9, max(0.1, self.cfg.tp1_frac)))],
                    be_trigger_rr=max(0.0, float(self.cfg.be_trigger_rr)),
                    be_lock_rr=max(0.0, float(self.cfg.be_lock_rr)),
                    trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
                    trailing_atr_period=max(5, int(self.cfg.trail_atr_period)),
                    time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
                    reason="asc1_sloped_channel_short",
                )
                if sig.validate():
                    return sig

        return None
