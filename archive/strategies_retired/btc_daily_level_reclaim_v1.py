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


def _compress_4h_to_daily(rows: List[list], group_n: int) -> List[dict]:
    out: List[dict] = []
    g = max(1, int(group_n))
    for i in range(0, len(rows), g):
        chunk = rows[i:i + g]
        if len(chunk) < g:
            break
        out.append(
            {
                "ts": int(float(chunk[0][0])),
                "o": float(chunk[0][1]),
                "h": max(float(r[2]) for r in chunk),
                "l": min(float(r[3]) for r in chunk),
                "c": float(chunk[-1][4]),
            }
        )
    return out


@dataclass
class BTCDailyLevelReclaimV1Config:
    regime_tf: str = "240"
    daily_group: int = 6
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    regime_slope_days: int = 5
    regime_min_gap_pct: float = 0.80
    regime_slope_min_pct: float = 0.30

    level_lookback_days: int = 20
    breakout_buffer_pct: float = 0.15
    signal_tf: str = "15"
    signal_atr_period: int = 14
    max_atr_pct_signal: float = 1.50
    retest_touch_pct: float = 0.25
    reclaim_pct: float = 0.10
    max_retest_bars_5m: int = 96

    sl_atr_mult: float = 1.35
    level_sl_buffer_atr: float = 0.10
    tp1_rr: float = 1.20
    tp2_rr: float = 3.20
    tp1_frac: float = 0.50
    trail_atr_mult: float = 0.0
    time_stop_bars_5m: int = 1152

    cooldown_bars_5m: int = 96
    allow_longs: bool = True
    allow_shorts: bool = False


class BTCDailyLevelReclaimV1Strategy:
    """BTC-only daily breakout level -> reclaim -> hold."""

    def __init__(self, cfg: Optional[BTCDailyLevelReclaimV1Config] = None):
        self.cfg = cfg or BTCDailyLevelReclaimV1Config()

        self.cfg.regime_tf = os.getenv("BTCD1_REGIME_TF", self.cfg.regime_tf)
        self.cfg.daily_group = _env_int("BTCD1_DAILY_GROUP", self.cfg.daily_group)
        self.cfg.regime_ema_fast = _env_int("BTCD1_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("BTCD1_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.regime_slope_days = _env_int("BTCD1_REGIME_SLOPE_DAYS", self.cfg.regime_slope_days)
        self.cfg.regime_min_gap_pct = _env_float("BTCD1_REGIME_MIN_GAP_PCT", self.cfg.regime_min_gap_pct)
        self.cfg.regime_slope_min_pct = _env_float("BTCD1_REGIME_SLOPE_MIN_PCT", self.cfg.regime_slope_min_pct)

        self.cfg.level_lookback_days = _env_int("BTCD1_LEVEL_LOOKBACK_DAYS", self.cfg.level_lookback_days)
        self.cfg.breakout_buffer_pct = _env_float("BTCD1_BREAKOUT_BUFFER_PCT", self.cfg.breakout_buffer_pct)
        self.cfg.signal_tf = os.getenv("BTCD1_SIGNAL_TF", self.cfg.signal_tf)
        self.cfg.signal_atr_period = _env_int("BTCD1_SIGNAL_ATR_PERIOD", self.cfg.signal_atr_period)
        self.cfg.max_atr_pct_signal = _env_float("BTCD1_MAX_ATR_PCT_SIGNAL", self.cfg.max_atr_pct_signal)
        self.cfg.retest_touch_pct = _env_float("BTCD1_RETEST_TOUCH_PCT", self.cfg.retest_touch_pct)
        self.cfg.reclaim_pct = _env_float("BTCD1_RECLAIM_PCT", self.cfg.reclaim_pct)
        self.cfg.max_retest_bars_5m = _env_int("BTCD1_MAX_RETEST_BARS_5M", self.cfg.max_retest_bars_5m)

        self.cfg.sl_atr_mult = _env_float("BTCD1_SL_ATR_MULT", self.cfg.sl_atr_mult)
        self.cfg.level_sl_buffer_atr = _env_float("BTCD1_LEVEL_SL_BUFFER_ATR", self.cfg.level_sl_buffer_atr)
        self.cfg.tp1_rr = _env_float("BTCD1_TP1_RR", self.cfg.tp1_rr)
        self.cfg.tp2_rr = _env_float("BTCD1_TP2_RR", self.cfg.tp2_rr)
        self.cfg.tp1_frac = _env_float("BTCD1_TP1_FRAC", self.cfg.tp1_frac)
        self.cfg.trail_atr_mult = _env_float("BTCD1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.time_stop_bars_5m = _env_int("BTCD1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("BTCD1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.allow_longs = _env_bool("BTCD1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("BTCD1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("BTCD1_SYMBOL_ALLOWLIST", "BTCUSDT")
        self._deny = _env_csv_set("BTCD1_SYMBOL_DENYLIST")

        self._cooldown = 0
        self._pending_long: Optional[dict] = None
        self._last_signal_tf_ts: Optional[int] = None

    def _daily_context(self, store) -> Optional[dict]:
        need_days = max(self.cfg.regime_ema_slow + self.cfg.regime_slope_days + self.cfg.level_lookback_days + 5, 90)
        need_4h = need_days * max(1, self.cfg.daily_group) + 6
        rows_4h = store.fetch_klines(store.symbol, self.cfg.regime_tf, need_4h) or []
        daily = _compress_4h_to_daily(rows_4h, self.cfg.daily_group)
        if len(daily) < self.cfg.regime_ema_slow + self.cfg.regime_slope_days + self.cfg.level_lookback_days + 2:
            return None

        closes = [x["c"] for x in daily]
        ef = _ema(closes, self.cfg.regime_ema_fast)
        es = _ema(closes, self.cfg.regime_ema_slow)
        es_prev = _ema(closes[:-max(1, self.cfg.regime_slope_days)], self.cfg.regime_ema_slow)
        cur = closes[-1]
        if not (math.isfinite(ef) and math.isfinite(es) and math.isfinite(es_prev) and cur > 0 and es_prev != 0):
            return None

        gap_pct = abs(ef - es) / cur * 100.0
        slope_pct = (es - es_prev) / abs(es_prev) * 100.0
        bullish = ef > es and slope_pct >= self.cfg.regime_slope_min_pct and gap_pct >= self.cfg.regime_min_gap_pct
        if not bullish:
            return {"bias": 1}

        look = self.cfg.level_lookback_days
        prev_high = max(x["h"] for x in daily[-look - 1:-1])
        cur_close = daily[-1]["c"]
        cur_high = daily[-1]["h"]
        broke_out = cur_high >= prev_high * (1.0 + self.cfg.breakout_buffer_pct / 100.0) and cur_close >= prev_high
        return {"bias": 2, "level": prev_high, "broke_out": broke_out}

    def _signal_atr(self, store) -> float:
        need = max(self.cfg.signal_atr_period + 5, 30)
        rows = store.fetch_klines(store.symbol, self.cfg.signal_tf, need) or []
        return _atr_from_rows(rows, self.cfg.signal_atr_period)

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, v)
        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            return None
        if sym in self._deny or not self.cfg.allow_longs:
            return None

        if self._cooldown > 0:
            self._cooldown -= 1
            return None

        ctx = self._daily_context(store)
        if not ctx or ctx.get("bias") != 2:
            self._pending_long = None
            return None

        level = float(ctx["level"])
        atr_now = self._signal_atr(store)
        if not (math.isfinite(atr_now) and atr_now > 0):
            return None
        atr_pct = atr_now / max(1e-12, abs(c)) * 100.0
        if atr_pct > self.cfg.max_atr_pct_signal:
            return None

        rows_sig = store.fetch_klines(store.symbol, self.cfg.signal_tf, 6) or []
        if not rows_sig:
            return None
        sig_ts = int(float(rows_sig[-1][0]))
        sig_close = float(rows_sig[-1][4])
        sig_low = float(rows_sig[-1][3])

        if self._last_signal_tf_ts is None:
            self._last_signal_tf_ts = sig_ts
            return None

        if ctx.get("broke_out") and self._pending_long is None:
            self._pending_long = {"level": level, "born": ts_ms}

        if self._pending_long is None:
            return None

        if ts_ms - int(self._pending_long["born"]) > self.cfg.max_retest_bars_5m * 5 * 60 * 1000:
            self._pending_long = None
            return None

        if sig_ts == self._last_signal_tf_ts:
            return None
        self._last_signal_tf_ts = sig_ts

        touched = sig_low <= level * (1.0 + self.cfg.retest_touch_pct / 100.0)
        reclaimed = sig_close >= level * (1.0 + self.cfg.reclaim_pct / 100.0)
        if not (touched and reclaimed):
            return None

        level_sl = level - self.cfg.level_sl_buffer_atr * atr_now
        atr_sl = float(c) - self.cfg.sl_atr_mult * atr_now
        sl = min(level_sl, atr_sl)
        if sl >= float(c):
            return None
        risk = float(c) - sl
        tp1 = float(c) + self.cfg.tp1_rr * risk
        tp2 = float(c) + self.cfg.tp2_rr * risk
        tp1_frac = min(0.9, max(0.1, float(self.cfg.tp1_frac)))

        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        self._pending_long = None
        sig = TradeSignal(
            strategy="btc_daily_level_reclaim_v1",
            symbol=store.symbol,
            side="long",
            entry=float(c),
            sl=float(sl),
            tp=float(tp2),
            tps=[float(tp1), float(tp2)],
            tp_fracs=[tp1_frac, max(0.0, 1.0 - tp1_frac)],
            trailing_atr_mult=max(0.0, float(self.cfg.trail_atr_mult)),
            trailing_atr_period=max(10, int(self.cfg.signal_atr_period)),
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason="btcd1_daily_level_reclaim",
        )
        return sig if sig.validate() else None
