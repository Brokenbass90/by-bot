from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .alt_resistance_fade_v1 import (
    _atr_from_rows,
    _ema,
    _env_bool,
    _env_csv_set,
    _env_float,
    _env_int,
    _rsi_wilder,
)
from .signals import TradeSignal


@dataclass
class AltResistanceFadeV2Config:
    """Structured short-only resistance fade.

    V1 used the highest high over a lookback as "resistance". V2 requires a
    repeated pivot cluster and optionally scores confluence with volume-at-price
    memory. It is intentionally research-only until OOS/WF proves value.
    """

    regime_tf: str = "240"
    regime_lookback: int = 72
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_min_score: float = 0.42
    regime_max_gap_pct: float = 4.0
    regime_max_slope_pct: float = 2.2
    regime_min_atr_pct: float = 0.20
    regime_max_atr_pct: float = 7.0

    daily_filter_enabled: bool = False
    daily_tf: str = "1440"
    daily_lookback: int = 80
    daily_ema_period: int = 50
    daily_max_close_above_ema_pct: float = 8.0

    signal_tf: str = "60"
    signal_lookback: int = 72
    signal_ema_period: int = 20
    signal_atr_period: int = 14
    rsi_period: int = 14

    pivot_left: int = 2
    pivot_right: int = 2
    min_touches: int = 3
    level_tol_atr: float = 0.45
    min_level_score: float = 0.45
    min_range_pct: float = 3.0
    max_range_pct: float = 28.0

    hvn_bins: int = 24
    hvn_top_n: int = 5
    hvn_confluence_atr: float = 0.70
    vwap_confluence_atr: float = 1.25

    resistance_touch_buffer_atr: float = 0.35
    max_pierce_atr: float = 1.00
    reject_below_res_atr: float = 0.12
    reject_require_lower_close: bool = True
    min_upper_wick_frac: float = 0.28
    min_body_frac: float = 0.15
    min_rsi: float = 56.0
    max_close_vs_ema_pct: float = 1.8
    min_reject_vol_mult: float = 0.0
    volume_avg_period: int = 20

    funding_filter_enabled: bool = False
    funding_require_data: bool = True
    min_funding_rate: float = -0.0002

    sl_atr_mult: float = 0.70
    tp1_frac: float = 0.60
    tp2_buffer_pct: float = 0.35
    min_rr: float = 1.20
    min_stop_pct: float = 0.0015
    max_stop_pct: float = 0.06
    trail_atr_mult: float = 0.0
    trail_atr_period: int = 14
    be_trigger_rr: float = 0.0
    be_lock_rr: float = 0.0
    time_stop_bars_5m: int = 432
    cooldown_bars_5m: int = 36
    config_refresh_bars: int = 50


def _pivot_highs(rows: List[list], left: int, right: int) -> List[Tuple[float, int, int]]:
    highs = [float(r[2]) for r in rows]
    out: List[Tuple[float, int, int]] = []
    if len(highs) < left + right + 1:
        return out
    for i in range(left, len(highs) - right):
        px = highs[i]
        if all(px >= highs[j] for j in range(i - left, i)) and all(px > highs[j] for j in range(i + 1, i + right + 1)):
            out.append((px, i, int(float(rows[i][0]))))
    return out


def _pivot_lows(rows: List[list], left: int, right: int) -> List[Tuple[float, int, int]]:
    lows = [float(r[3]) for r in rows]
    out: List[Tuple[float, int, int]] = []
    if len(lows) < left + right + 1:
        return out
    for i in range(left, len(lows) - right):
        px = lows[i]
        if all(px <= lows[j] for j in range(i - left, i)) and all(px < lows[j] for j in range(i + 1, i + right + 1)):
            out.append((px, i, int(float(rows[i][0]))))
    return out


def _cluster_prices(points: List[Tuple[float, int, int]], tol: float) -> List[dict]:
    if not points or tol <= 0:
        return []
    clusters: List[dict] = []
    for price, idx, ts in sorted(points, key=lambda x: x[0]):
        if not clusters or abs(price - clusters[-1]["level"]) > tol:
            clusters.append({"prices": [price], "indices": [idx], "ts": [ts], "level": price})
        else:
            c = clusters[-1]
            c["prices"].append(price)
            c["indices"].append(idx)
            c["ts"].append(ts)
            c["level"] = sum(c["prices"]) / len(c["prices"])
    for c in clusters:
        c["touches"] = len(c["prices"])
        c["last_idx"] = max(c["indices"])
        c["last_ts"] = max(c["ts"])
    return clusters


def _volume_hvns(rows: List[list], bins: int, top_n: int) -> List[float]:
    if not rows or bins <= 1 or top_n <= 0:
        return []
    lows = [float(r[3]) for r in rows]
    highs = [float(r[2]) for r in rows]
    lo = min(lows)
    hi = max(highs)
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        return []
    width = (hi - lo) / float(bins)
    vols = [0.0 for _ in range(bins)]
    for r in rows:
        typ = (float(r[2]) + float(r[3]) + float(r[4])) / 3.0
        v = max(0.0, float(r[5]) if len(r) > 5 else 0.0)
        idx = min(bins - 1, max(0, int((typ - lo) / width)))
        vols[idx] += v
    ranked = sorted(range(bins), key=lambda i: vols[i], reverse=True)[:top_n]
    return [lo + (i + 0.5) * width for i in ranked if vols[i] > 0]


def _vwap(rows: List[list]) -> float:
    num = 0.0
    den = 0.0
    for r in rows:
        v = max(0.0, float(r[5]) if len(r) > 5 else 0.0)
        typ = (float(r[2]) + float(r[3]) + float(r[4])) / 3.0
        num += typ * v
        den += v
    if den <= 1e-12:
        return float("nan")
    return num / den


class AltResistanceFadeV2Strategy:
    """Short-only structured resistance fade for research/OOS validation."""

    def __init__(self, cfg: Optional[AltResistanceFadeV2Config] = None):
        self.cfg = cfg or AltResistanceFadeV2Config()
        self._load_runtime_config()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._bar_count = 0
        self.last_no_signal_reason = ""

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
        c.regime_tf = os.getenv("ARF2_REGIME_TF", c.regime_tf)
        c.regime_lookback = _env_int("ARF2_REGIME_LOOKBACK", c.regime_lookback)
        c.regime_ema_fast = _env_int("ARF2_REGIME_EMA_FAST", c.regime_ema_fast)
        c.regime_ema_slow = _env_int("ARF2_REGIME_EMA_SLOW", c.regime_ema_slow)
        c.regime_min_score = _env_float("ARF2_REGIME_MIN_SCORE", c.regime_min_score)
        c.regime_max_gap_pct = _env_float("ARF2_REGIME_MAX_GAP_PCT", c.regime_max_gap_pct)
        c.regime_max_slope_pct = _env_float("ARF2_REGIME_MAX_SLOPE_PCT", c.regime_max_slope_pct)
        c.regime_min_atr_pct = _env_float("ARF2_REGIME_MIN_ATR_PCT", c.regime_min_atr_pct)
        c.regime_max_atr_pct = _env_float("ARF2_REGIME_MAX_ATR_PCT", c.regime_max_atr_pct)

        c.daily_filter_enabled = _env_bool("ARF2_DAILY_FILTER_ENABLED", c.daily_filter_enabled)
        c.daily_tf = os.getenv("ARF2_DAILY_TF", c.daily_tf)
        c.daily_lookback = _env_int("ARF2_DAILY_LOOKBACK", c.daily_lookback)
        c.daily_ema_period = _env_int("ARF2_DAILY_EMA_PERIOD", c.daily_ema_period)
        c.daily_max_close_above_ema_pct = _env_float("ARF2_DAILY_MAX_CLOSE_ABOVE_EMA_PCT", c.daily_max_close_above_ema_pct)

        c.signal_tf = os.getenv("ARF2_SIGNAL_TF", c.signal_tf)
        c.signal_lookback = _env_int("ARF2_SIGNAL_LOOKBACK", c.signal_lookback)
        c.signal_ema_period = _env_int("ARF2_SIGNAL_EMA_PERIOD", c.signal_ema_period)
        c.signal_atr_period = _env_int("ARF2_SIGNAL_ATR_PERIOD", c.signal_atr_period)
        c.rsi_period = _env_int("ARF2_RSI_PERIOD", c.rsi_period)
        c.pivot_left = _env_int("ARF2_PIVOT_LEFT", c.pivot_left)
        c.pivot_right = _env_int("ARF2_PIVOT_RIGHT", c.pivot_right)
        c.min_touches = _env_int("ARF2_MIN_TOUCHES", c.min_touches)
        c.level_tol_atr = _env_float("ARF2_LEVEL_TOL_ATR", c.level_tol_atr)
        c.min_level_score = _env_float("ARF2_MIN_LEVEL_SCORE", c.min_level_score)
        c.min_range_pct = _env_float("ARF2_MIN_RANGE_PCT", c.min_range_pct)
        c.max_range_pct = _env_float("ARF2_MAX_RANGE_PCT", c.max_range_pct)
        c.hvn_bins = _env_int("ARF2_HVN_BINS", c.hvn_bins)
        c.hvn_top_n = _env_int("ARF2_HVN_TOP_N", c.hvn_top_n)
        c.hvn_confluence_atr = _env_float("ARF2_HVN_CONFLUENCE_ATR", c.hvn_confluence_atr)
        c.vwap_confluence_atr = _env_float("ARF2_VWAP_CONFLUENCE_ATR", c.vwap_confluence_atr)

        c.resistance_touch_buffer_atr = _env_float("ARF2_RES_TOUCH_BUFFER_ATR", c.resistance_touch_buffer_atr)
        c.max_pierce_atr = _env_float("ARF2_MAX_PIERCE_ATR", c.max_pierce_atr)
        c.reject_below_res_atr = _env_float("ARF2_REJECT_BELOW_RES_ATR", c.reject_below_res_atr)
        c.reject_require_lower_close = _env_bool("ARF2_REJECT_REQUIRE_LOWER_CLOSE", c.reject_require_lower_close)
        c.min_upper_wick_frac = _env_float("ARF2_MIN_UPPER_WICK_FRAC", c.min_upper_wick_frac)
        c.min_body_frac = _env_float("ARF2_MIN_BODY_FRAC", c.min_body_frac)
        c.min_rsi = _env_float("ARF2_MIN_RSI", c.min_rsi)
        c.max_close_vs_ema_pct = _env_float("ARF2_MAX_CLOSE_VS_EMA_PCT", c.max_close_vs_ema_pct)
        c.min_reject_vol_mult = _env_float("ARF2_MIN_REJECT_VOL_MULT", c.min_reject_vol_mult)
        c.volume_avg_period = _env_int("ARF2_VOLUME_AVG_PERIOD", c.volume_avg_period)

        c.funding_filter_enabled = _env_bool("ARF2_FUNDING_FILTER_ENABLED", c.funding_filter_enabled)
        c.funding_require_data = _env_bool("ARF2_FUNDING_REQUIRE_DATA", c.funding_require_data)
        c.min_funding_rate = _env_float("ARF2_MIN_FUNDING_RATE", c.min_funding_rate)

        c.sl_atr_mult = _env_float("ARF2_SL_ATR_MULT", c.sl_atr_mult)
        c.tp1_frac = _env_float("ARF2_TP1_FRAC", c.tp1_frac)
        c.tp2_buffer_pct = _env_float("ARF2_TP2_BUFFER_PCT", c.tp2_buffer_pct)
        c.min_rr = _env_float("ARF2_MIN_RR", c.min_rr)
        c.min_stop_pct = _env_float("ARF2_MIN_STOP_PCT", c.min_stop_pct)
        c.max_stop_pct = _env_float("ARF2_MAX_STOP_PCT", c.max_stop_pct)
        c.trail_atr_mult = _env_float("ARF2_TRAIL_ATR_MULT", c.trail_atr_mult)
        c.trail_atr_period = _env_int("ARF2_TRAIL_ATR_PERIOD", c.trail_atr_period)
        c.be_trigger_rr = _env_float("ARF2_BE_TRIGGER_RR", c.be_trigger_rr)
        c.be_lock_rr = _env_float("ARF2_BE_LOCK_RR", c.be_lock_rr)
        c.time_stop_bars_5m = _env_int("ARF2_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("ARF2_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.config_refresh_bars = _env_int("ARF2_CONFIG_REFRESH_BARS", c.config_refresh_bars)

        self._allow = _env_csv_set("ARF2_SYMBOL_ALLOWLIST", "")
        self._deny = _env_csv_set("ARF2_SYMBOL_DENYLIST", "")

    def _maybe_refresh_config(self) -> None:
        if self._bar_count % max(1, int(self.cfg.config_refresh_bars)) == 0:
            self._load_runtime_config()

    def _regime_ok(self, store) -> bool:
        c = self.cfg
        need = max(c.regime_lookback, c.regime_ema_slow + 8)
        rows = store.fetch_klines(store.symbol, c.regime_tf, need) or []
        if len(rows) < c.regime_ema_slow + 8:
            self._no_signal("regime_history_short")
            return False
        closes = [float(r[4]) for r in rows]
        cur = closes[-1]
        ef = _ema(closes, c.regime_ema_fast)
        es = _ema(closes, c.regime_ema_slow)
        es_prev = _ema(closes[:-4], c.regime_ema_slow) if len(closes) > c.regime_ema_slow + 4 else float("nan")
        atr = _atr_from_rows(rows, 14)
        if not all(math.isfinite(x) for x in (cur, ef, es, es_prev, atr)) or cur <= 0 or atr <= 0:
            self._no_signal("regime_invalid")
            return False

        gap_pct = abs(ef - es) / cur * 100.0
        slope_pct = abs((es - es_prev) / max(1e-12, abs(es_prev))) * 100.0
        atr_pct = atr / cur * 100.0
        s_gap = 1.0 / (1.0 + gap_pct / max(1e-9, c.regime_max_gap_pct))
        s_slope = 1.0 / (1.0 + slope_pct / max(1e-9, c.regime_max_slope_pct))
        if atr_pct < c.regime_min_atr_pct:
            s_atr = atr_pct / max(1e-9, c.regime_min_atr_pct)
        elif atr_pct > c.regime_max_atr_pct:
            s_atr = c.regime_max_atr_pct / max(1e-9, atr_pct)
        else:
            s_atr = 1.0
        short_bias = 1.0 if (ef <= es or cur <= ef) else 0.35
        score = 0.30 * s_gap + 0.25 * s_slope + 0.20 * s_atr + 0.25 * short_bias
        if score < c.regime_min_score:
            self._no_signal(f"regime_score_low_{score:.2f}")
            return False
        return True

    def _daily_ok(self, store) -> bool:
        c = self.cfg
        if not c.daily_filter_enabled:
            return True
        need = max(c.daily_lookback, c.daily_ema_period + 5)
        rows = store.fetch_klines(store.symbol, c.daily_tf, need) or []
        if len(rows) < c.daily_ema_period + 5:
            self._no_signal("daily_history_short")
            return False
        closes = [float(r[4]) for r in rows]
        ema = _ema(closes, c.daily_ema_period)
        cur = closes[-1]
        if not math.isfinite(ema) or ema <= 0 or cur <= 0:
            self._no_signal("daily_invalid")
            return False
        ext_pct = (cur - ema) / ema * 100.0
        if ext_pct > c.daily_max_close_above_ema_pct:
            self._no_signal(f"daily_too_bullish_{ext_pct:.2f}")
            return False
        return True

    def _funding_ok(self, store) -> bool:
        c = self.cfg
        if not c.funding_filter_enabled:
            return True
        fn = getattr(store, "fetch_funding_rate", None)
        rate = None
        if callable(fn):
            try:
                rate = fn(store.symbol)
            except TypeError:
                rate = fn(store.symbol, None)
            except Exception:
                rate = None
        if rate is None:
            if c.funding_require_data:
                self._no_signal("funding_missing")
                return False
            return True
        if float(rate) < c.min_funding_rate:
            self._no_signal(f"funding_too_low_{float(rate):.6f}")
            return False
        return True

    def _select_resistance(self, history: List[list], atr: float, high_now: float) -> Optional[dict]:
        c = self.cfg
        tol = max(1e-12, c.level_tol_atr * atr)
        clusters = _cluster_prices(_pivot_highs(history, c.pivot_left, c.pivot_right), tol)
        if not clusters:
            return None
        hvns = _volume_hvns(history[-c.signal_lookback:], c.hvn_bins, c.hvn_top_n)
        vwap = _vwap(history[-c.signal_lookback:])
        candidates: List[dict] = []
        for cl in clusters:
            level = float(cl["level"])
            if int(cl["touches"]) < c.min_touches:
                continue
            if high_now < level - c.resistance_touch_buffer_atr * atr:
                continue
            if high_now > level + c.max_pierce_atr * atr:
                continue
            touch_score = min(1.0, float(cl["touches"]) / max(1.0, float(c.min_touches + 1)))
            hvn_score = 1.0 if any(abs(level - h) <= c.hvn_confluence_atr * atr for h in hvns) else 0.0
            vwap_score = 0.0
            if math.isfinite(vwap):
                vwap_score = max(0.0, 1.0 - abs(level - vwap) / max(1e-12, c.vwap_confluence_atr * atr))
            recency_score = max(0.0, min(1.0, float(cl["last_idx"]) / max(1, len(history) - 1)))
            score = 0.45 * touch_score + 0.35 * hvn_score + 0.15 * vwap_score + 0.05 * recency_score
            if score >= c.min_level_score:
                out = dict(cl)
                out.update({"score": score, "hvn_score": hvn_score, "vwap_score": vwap_score})
                candidates.append(out)
        if not candidates:
            return None
        candidates.sort(key=lambda x: (x["score"], x["level"]), reverse=True)
        return candidates[0]

    def _support_below(self, history: List[list], entry: float, atr: float) -> Optional[float]:
        c = self.cfg
        tol = max(1e-12, c.level_tol_atr * atr)
        lows = _cluster_prices(_pivot_lows(history, c.pivot_left, c.pivot_right), tol)
        below = [float(cl["level"]) for cl in lows if int(cl["touches"]) >= 2 and float(cl["level"]) < entry - 0.5 * atr]
        if below:
            return max(below)
        raw = [float(r[3]) for r in history[-c.signal_lookback:] if float(r[3]) < entry - 0.5 * atr]
        return min(raw) if raw else None

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, c, v, ts_ms)
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
        if not self._regime_ok(store) or not self._daily_ok(store) or not self._funding_ok(store):
            return None

        need = max(
            c_need := self.cfg.signal_lookback + self.cfg.pivot_right + 3,
            self.cfg.signal_ema_period + self.cfg.rsi_period * 2 + 5,
            self.cfg.volume_avg_period + 5,
        )
        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, need) or []
        if len(rows) < max(10, min(need, c_need)):
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

        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        opens = [float(r[1]) for r in rows]
        vols = [float(r[5]) if len(r) > 5 else 0.0 for r in rows]
        cur = closes[-1]
        prev = closes[-2]
        atr = _atr_from_rows(rows, self.cfg.signal_atr_period)
        ema = _ema(closes, self.cfg.signal_ema_period)
        rsi = _rsi_wilder(closes, self.cfg.rsi_period)
        if not all(math.isfinite(x) for x in (cur, atr, ema, rsi)) or cur <= 0 or atr <= 0:
            self._no_signal("signal_invalid")
            return None

        history = rows[:-1]
        high_now = highs[-1]
        low_now = lows[-1]
        open_now = opens[-1]
        resistance = self._select_resistance(history, atr, high_now)
        if not resistance:
            self._no_signal("level_not_found")
            return None
        level = float(resistance["level"])
        support = self._support_below(history, cur, atr)
        if support is None:
            self._no_signal("support_not_found")
            return None

        range_pct = (level - support) / max(1e-12, cur) * 100.0
        if range_pct < self.cfg.min_range_pct:
            self._no_signal(f"range_too_narrow_{range_pct:.2f}")
            return None
        if range_pct > self.cfg.max_range_pct:
            self._no_signal(f"range_too_wide_{range_pct:.2f}")
            return None

        if high_now < level - self.cfg.resistance_touch_buffer_atr * atr:
            self._no_signal("no_res_touch")
            return None
        if high_now > level + self.cfg.max_pierce_atr * atr:
            self._no_signal("pierce_too_deep")
            return None

        bar_range = max(1e-12, high_now - low_now)
        upper_wick_frac = (high_now - max(open_now, cur)) / bar_range
        body_frac = abs(cur - open_now) / bar_range
        bearish_bar = cur < open_now
        closed_below = cur <= level - self.cfg.reject_below_res_atr * atr
        lower_close = cur < prev if self.cfg.reject_require_lower_close else True
        if not (bearish_bar and closed_below and lower_close):
            self._no_signal("no_rejection")
            return None
        if upper_wick_frac < self.cfg.min_upper_wick_frac:
            self._no_signal(f"wick_weak_{upper_wick_frac:.2f}")
            return None
        if body_frac < self.cfg.min_body_frac:
            self._no_signal(f"body_weak_{body_frac:.2f}")
            return None
        if rsi < self.cfg.min_rsi:
            self._no_signal(f"rsi_too_low_{rsi:.2f}")
            return None
        close_vs_ema_pct = (cur - ema) / max(1e-12, ema) * 100.0
        if close_vs_ema_pct > self.cfg.max_close_vs_ema_pct:
            self._no_signal(f"ema_extension_high_{close_vs_ema_pct:.2f}")
            return None
        if self.cfg.min_reject_vol_mult > 0.0:
            avg_vol = sum(vols[-self.cfg.volume_avg_period - 1:-1]) / max(1, self.cfg.volume_avg_period)
            if avg_vol > 0 and vols[-1] < self.cfg.min_reject_vol_mult * avg_vol:
                self._no_signal("reject_volume_low")
                return None

        entry_price = float(cur)
        sl = max(high_now, level) + self.cfg.sl_atr_mult * atr
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

        tp1 = entry_price - (entry_price - tp2) * 0.55
        tp1_frac = min(0.9, max(0.1, self.cfg.tp1_frac))
        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        sig = TradeSignal(
            strategy="alt_resistance_fade_v2",
            symbol=store.symbol,
            side="short",
            entry=entry_price,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=max(5, int(self.cfg.trail_atr_period)),
            be_trigger_rr=max(0.0, float(self.cfg.be_trigger_rr)),
            be_lock_rr=max(0.0, float(self.cfg.be_lock_rr)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"arf2_structured_resistance_fade score={float(resistance['score']):.2f}",
        )
        if not sig.validate():
            self._no_signal("signal_invalid_post")
            return None
        return sig
