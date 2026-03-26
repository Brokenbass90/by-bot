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
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


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


def _sma(values: List[float], period: int) -> float:
    if period <= 0 or len(values) < period:
        return float("nan")
    return sum(values[-period:]) / float(period)


def _compress_closes(rows: List[list], group_n: int) -> List[float]:
    out: List[float] = []
    if group_n <= 1:
        return [float(r[4]) for r in rows]
    for i in range(0, len(rows), group_n):
        chunk = rows[i:i + group_n]
        if len(chunk) < group_n:
            break
        out.append(float(chunk[-1][4]))
    return out


@dataclass
class BTCRegimeRetestV1Config:
    regime_tf: str = "240"
    regime_daily_group: int = 6  # 6 x 4h ~= 1d proxy
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_slope_days: int = 5
    regime_min_gap_pct: float = 0.80
    regime_slope_min_pct: float = 0.35

    breakout_tf: str = "240"
    breakout_lookback_bars: int = 18
    breakout_atr_period: int = 14
    breakout_atr_mult: float = 0.20
    breakout_vol_period: int = 20
    breakout_vol_mult: float = 1.05

    signal_tf: str = "60"
    signal_atr_period: int = 14
    signal_max_atr_pct: float = 2.20
    retest_touch_atr: float = 0.20
    reclaim_hold_atr: float = 0.05
    invalidation_atr: float = 0.45
    max_retest_bars_5m: int = 48
    min_retest_vol_mult_5m: float = 0.90
    vol_period_5m: int = 24

    sl_atr_mult: float = 1.35
    tp1_rr: float = 1.20
    tp2_rr: float = 2.80
    tp1_frac: float = 0.50
    trail_atr_mult: float = 1.50
    time_stop_bars_5m: int = 288

    cooldown_bars_5m: int = 48
    max_signals_per_day: int = 1
    allow_longs: bool = True
    allow_shorts: bool = True


class BTCRegimeRetestV1Strategy:
    """BTC-only regime breakout -> retest -> hold.

    The design is intentionally narrow:
    - trend/cycle proxy from compressed 4h bars (~daily closes)
    - structure level from recent 4h highs/lows
    - entry only after breakout and a real retest hold
    """

    def __init__(self, cfg: Optional[BTCRegimeRetestV1Config] = None):
        self.cfg = cfg or BTCRegimeRetestV1Config()

        self.cfg.regime_tf = os.getenv("BTCR1_REGIME_TF", self.cfg.regime_tf)
        self.cfg.regime_daily_group = _env_int("BTCR1_REGIME_DAILY_GROUP", self.cfg.regime_daily_group)
        self.cfg.regime_ema_fast = _env_int("BTCR1_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("BTCR1_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_slope_days = _env_int("BTCR1_REGIME_SLOPE_DAYS", self.cfg.regime_slope_days)
        self.cfg.regime_min_gap_pct = _env_float("BTCR1_REGIME_MIN_GAP_PCT", self.cfg.regime_min_gap_pct)
        self.cfg.regime_slope_min_pct = _env_float("BTCR1_REGIME_SLOPE_MIN_PCT", self.cfg.regime_slope_min_pct)

        self.cfg.breakout_tf = os.getenv("BTCR1_BREAKOUT_TF", self.cfg.breakout_tf)
        self.cfg.breakout_lookback_bars = _env_int("BTCR1_BREAKOUT_LOOKBACK_BARS", self.cfg.breakout_lookback_bars)
        self.cfg.breakout_atr_period = _env_int("BTCR1_BREAKOUT_ATR_PERIOD", self.cfg.breakout_atr_period)
        self.cfg.breakout_atr_mult = _env_float("BTCR1_BREAKOUT_ATR_MULT", self.cfg.breakout_atr_mult)
        self.cfg.breakout_vol_period = _env_int("BTCR1_BREAKOUT_VOL_PERIOD", self.cfg.breakout_vol_period)
        self.cfg.breakout_vol_mult = _env_float("BTCR1_BREAKOUT_VOL_MULT", self.cfg.breakout_vol_mult)

        self.cfg.signal_tf = os.getenv("BTCR1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_atr_period = _env_int("BTCR1_SIGNAL_ATR_PERIOD", self.cfg.signal_atr_period)
        self.cfg.signal_max_atr_pct = _env_float("BTCR1_SIGNAL_MAX_ATR_PCT", self.cfg.signal_max_atr_pct)
        self.cfg.retest_touch_atr = _env_float("BTCR1_RETEST_TOUCH_ATR", self.cfg.retest_touch_atr)
        self.cfg.reclaim_hold_atr = _env_float("BTCR1_RECLAIM_HOLD_ATR", self.cfg.reclaim_hold_atr)
        self.cfg.invalidation_atr = _env_float("BTCR1_INVALIDATION_ATR", self.cfg.invalidation_atr)
        self.cfg.max_retest_bars_5m = _env_int("BTCR1_MAX_RETEST_BARS_5M", self.cfg.max_retest_bars_5m)
        self.cfg.min_retest_vol_mult_5m = _env_float("BTCR1_MIN_RETEST_VOL_MULT_5M", self.cfg.min_retest_vol_mult_5m)
        self.cfg.vol_period_5m = _env_int("BTCR1_VOL_PERIOD_5M", self.cfg.vol_period_5m)

        self.cfg.sl_atr_mult = _env_float("BTCR1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.tp1_rr = _env_float("BTCR1_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_rr = _env_float("BTCR1_TP2_RR", self.cfg.tp2_rr)
        self.cfg.tp1_frac = _env_float("BTCR1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.trail_atr_mult = _env_float("BTCR1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("BTCR1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)

        self.cfg.cooldown_bars_5m = _env_int("BTCR1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_signals_per_day = _env_int("BTCR1_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.allow_longs = _env_bool("BTCR1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("BTCR1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("BTCR1_SYMBOL_ALLOWLIST", "BTCUSDT")
        self._deny = _env_csv_set("BTCR1_SYMBOL_DENYLIST")

        self._cooldown = 0
        self._day_key: Optional[int] = None
        self._day_signals = 0
        self._last_breakout_ts: Optional[int] = None
        self._pending_long: Optional[dict] = None
        self._pending_short: Optional[dict] = None

        self._v5: List[float] = []

    def _regime_bias(self, store) -> Optional[int]:
        need_daily = max(self.cfg.regime_ema_slow + self.cfg.regime_slope_days + 5, 70)
        need_4h = int(need_daily * max(1, self.cfg.regime_daily_group)) + 6
        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, need_4h) or []
        closes_daily = _compress_closes(rows, max(1, int(self.cfg.regime_daily_group)))
        if len(closes_daily) < self.cfg.regime_ema_slow + self.cfg.regime_slope_days + 2:
            return None

        ef = _ema(closes_daily, self.cfg.regime_ema_fast)
        es = _ema(closes_daily, self.cfg.regime_ema_slow)
        es_prev = _ema(closes_daily[:-max(1, self.cfg.regime_slope_days)], self.cfg.regime_ema_slow)
        cur = closes_daily[-1]
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev) and cur > 0 and es_prev != 0):
            return None

        gap_pct = abs(ef - es) / cur * 100.0
        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        if gap_pct < self.cfg.regime_min_gap_pct:
            return 1
        if ef > es and slope_pct >= self.cfg.regime_slope_min_pct:
            return 2
        if ef < es and slope_pct <= -self.cfg.regime_slope_min_pct:
            return 0
        return 1

    def _signal_atr(self, store) -> float:
        need = max(self.cfg.signal_atr_period + 5, 30)
        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, need) or []
        return _atr_from_rows(rows, self.cfg.signal_atr_period)

    def _make_signal(self, store, side: str, entry: float, level: float, atr_now: float) -> Optional[TradeSignal]:
        if side == "long":
            sl = level - self.cfg.sl_atr_mult * atr_now
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = entry + self.cfg.tp1_rr * risk
            tp2 = entry + self.cfg.tp2_rr * risk
        else:
            sl = level + self.cfg.sl_atr_mult * atr_now
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = entry - self.cfg.tp1_rr * risk
            tp2 = entry - self.cfg.tp2_rr * risk

        sig = TradeSignal(
            strategy="btc_regime_retest_v1",
            symbol=store.symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[min(0.9, max(0.1, self.cfg.tp1_frac)), max(0.0, 1.0 - min(0.9, max(0.1, self.cfg.tp1_frac)))],
            trailing_atr_mult=self.cfg.trail_atr_mult,
            trailing_atr_period=max(10, int(self.cfg.signal_atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=f"btcr1_{side}_regime_break_retest",
        )
        return sig if sig.validate() else None

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = o
        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny:
            return None

        self._v5.append(v)

        if self._cooldown > 0:
            self._cooldown -= 1

        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            return None

        atr_sig = self._signal_atr(store)
        if not (math.isfinite(atr_sig) and atr_sig > 0):
            return None
        atr_pct = atr_sig / max(1e-12, abs(float(c))) * 100.0
        if atr_pct > self.cfg.signal_max_atr_pct:
            return None

        vol_avg_5m = _sma(self._v5[:-1], self.cfg.vol_period_5m)
        if not math.isfinite(vol_avg_5m) or vol_avg_5m <= 0:
            vol_avg_5m = float(v)

        bias = self._regime_bias(store)
        if bias is None:
            return None

        i5 = getattr(store, "i5", None)
        if i5 is None:
            return None
        cur_i = int(i5)

        if self._pending_long is not None:
            p = self._pending_long
            if cur_i > int(p["expires_i"]):
                self._pending_long = None
            else:
                level = float(p["level"])
                touched = float(l) <= level + self.cfg.retest_touch_atr * atr_sig
                hold_ok = float(c) >= level + self.cfg.reclaim_hold_atr * atr_sig
                vol_ok = float(v) >= vol_avg_5m * self.cfg.min_retest_vol_mult_5m
                invalid = float(c) < level - self.cfg.invalidation_atr * atr_sig
                if invalid:
                    self._pending_long = None
                elif touched and hold_ok and vol_ok and self._cooldown <= 0 and self.cfg.allow_longs and bias == 2:
                    sig = self._make_signal(store, "long", float(c), level, atr_sig)
                    self._pending_long = None
                    if sig is not None:
                        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                        self._day_signals += 1
                        return sig

        if self._pending_short is not None:
            p = self._pending_short
            if cur_i > int(p["expires_i"]):
                self._pending_short = None
            else:
                level = float(p["level"])
                touched = float(h) >= level - self.cfg.retest_touch_atr * atr_sig
                hold_ok = float(c) <= level - self.cfg.reclaim_hold_atr * atr_sig
                vol_ok = float(v) >= vol_avg_5m * self.cfg.min_retest_vol_mult_5m
                invalid = float(c) > level + self.cfg.invalidation_atr * atr_sig
                if invalid:
                    self._pending_short = None
                elif touched and hold_ok and vol_ok and self._cooldown <= 0 and self.cfg.allow_shorts and bias == 0:
                    sig = self._make_signal(store, "short", float(c), level, atr_sig)
                    self._pending_short = None
                    if sig is not None:
                        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
                        self._day_signals += 1
                        return sig

        need_4h = max(self.cfg.breakout_lookback_bars + 3, self.cfg.breakout_atr_period + 5, self.cfg.breakout_vol_period + 5)
        rows_4h = store.fetch_klines(store.symbol, self.cfg.breakout_tf, need_4h) or []
        if len(rows_4h) < need_4h:
            return None

        t_last = int(float(rows_4h[-1][0]))
        if self._last_breakout_ts is None:
            self._last_breakout_ts = t_last
            return None
        if t_last == self._last_breakout_ts:
            return None
        self._last_breakout_ts = t_last

        highs_4h = [float(r[2]) for r in rows_4h]
        lows_4h = [float(r[3]) for r in rows_4h]
        closes_4h = [float(r[4]) for r in rows_4h]
        vols_4h = [float(r[5]) if len(r) > 5 else 0.0 for r in rows_4h]

        atr_4h = _atr_from_rows(rows_4h, self.cfg.breakout_atr_period)
        vol_avg_4h = _sma(vols_4h[:-1], self.cfg.breakout_vol_period)
        if not (math.isfinite(atr_4h) and atr_4h > 0 and math.isfinite(vol_avg_4h) and vol_avg_4h > 0):
            return None

        hi = max(highs_4h[-(self.cfg.breakout_lookback_bars + 1):-1])
        lo = min(lows_4h[-(self.cfg.breakout_lookback_bars + 1):-1])
        break_buf = self.cfg.breakout_atr_mult * atr_4h
        close_4h = closes_4h[-1]
        vol_break_ok = vols_4h[-1] >= vol_avg_4h * self.cfg.breakout_vol_mult

        if self.cfg.allow_longs and bias == 2 and vol_break_ok and close_4h >= hi + break_buf:
            self._pending_long = {"level": float(hi), "expires_i": int(cur_i + self.cfg.max_retest_bars_5m)}
            self._pending_short = None

        if self.cfg.allow_shorts and bias == 0 and vol_break_ok and close_4h <= lo - break_buf:
            self._pending_short = {"level": float(lo), "expires_i": int(cur_i + self.cfg.max_retest_bars_5m)}
            self._pending_long = None

        return None
