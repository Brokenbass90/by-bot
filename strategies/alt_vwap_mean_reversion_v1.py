"""
alt_vwap_mean_reversion_v1 — 15m VWAP mean reversion for choppy/ranging markets.

Idea:
  - use session VWAP as the intraday magnet;
  - only trade when 15m regime is sufficiently inefficient/rangy (ER < max_er);
  - short stretched moves above VWAP after rejection;
  - buy stretched moves below VWAP after reclaim.

v2 FIX (2026-04-26):
  Root cause of -96%:
    1. TP1 was a FRACTION of the way to VWAP, not the VWAP itself.
       Entry at 0.95 ATR from VWAP, TP1 at 65% of that = 0.617 ATR,
       SL = 0.90 ATR → TP1/SL = 0.69R (negative EV below 53% WR).
    2. TP2 was only 0.20 ATR PAST VWAP (nearly useless).
    3. No max_signals_per_day → up to 8 trades/day/symbol.
    4. SL too tight (0.90 ATR) → normal noise hits it constantly.
    5. 12H time stop → holding intraday trades overnight.

  Fixes:
    - TP1 = VWAP itself (the actual mean reversion target)
    - TP2 = VWAP ± tp2_atr * ATR (meaningful overshoot target)
    - sl_atr_mult: 0.90 → 1.50 (survive normal noise)
    - min_vwap_dev_atr: 0.95 → 1.50 (require real extension first)
    - time_stop_bars_5m: 144 → 36 (3H max — intraday only)
    - cooldown_bars_5m: 36 → 72 (6H cooldown, was 3H)
    - max_signals_per_day: NEW = 2 (hard cap)

  New math at min_dev=1.5 ATR, sl=1.5 ATR:
    TP1 = VWAP = 1.5 ATR from entry → RR 1:1
    TP2 = VWAP ± 1.0 ATR → RR 1.67:1
    50% at each: avg = 1.335R per win
    At WR=50%: EV = 0.50×1.335 − 0.50×1.0 = +0.168R/trade ✓
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


def _same_day(row_ts_ms: float | int, ref_ts_ms: int) -> bool:
    try:
        row_day = datetime.fromtimestamp(float(row_ts_ms) / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
        ref_day = datetime.fromtimestamp(ref_ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return False
    return row_day == ref_day


@dataclass
class AltVWAPMeanReversionV1Config:
    signal_tf: str = "15"
    signal_lookback: int = 72
    session_bars_min: int = 12        # Need at least 1H of session data for VWAP
    rsi_period: int = 14
    atr_period: int = 14

    # Chop gate: ER must be LOW (ranging market) — VWAP works in chop, not trends
    max_er: float = 0.35              # was 0.38 — slightly tighter

    # Entry: price must be this many ATR from VWAP to qualify
    min_vwap_dev_atr: float = 1.50   # FIX: was 0.95 — requires real extension

    # RSI confirmation
    long_rsi_max: float = 39.0       # Long: RSI < 39 (oversold below VWAP)
    short_rsi_min: float = 61.0      # Short: RSI > 61 (overbought above VWAP)

    # Risk management — FIX: proper SL
    sl_atr_mult: float = 1.50        # FIX: was 0.90 — survive normal 15m noise

    # Exit — FIX: TP1 IS VWAP, TP2 overshoots VWAP
    # tp1_frac = fraction of POSITION (not distance) exiting at TP1=VWAP
    tp1_frac: float = 0.50           # FIX: was 0.65 — equal split
    tp2_atr: float = 1.00            # FIX: was 0.20 — TP2 = 1.0 ATR past VWAP

    # Throttling — FIX: prevent overtrading
    time_stop_bars_5m: int = 36      # FIX: was 144 (12H!) → 3H max intraday hold
    cooldown_bars_5m: int = 72       # FIX: was 36 (3H) → 6H cooldown
    max_signals_per_day: int = 2     # NEW: hard cap per symbol per day

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
        self.cfg.max_signals_per_day = _env_int("AVW1_MAX_SIGNALS_PER_DAY", self.cfg.max_signals_per_day)
        self.cfg.allow_longs = _env_bool("AVW1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.allow_shorts = _env_bool("AVW1_ALLOW_SHORTS", self.cfg.allow_shorts)

        self._allow = _env_csv_set("AVW1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("AVW1_SYMBOL_DENYLIST")
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._day_key: Optional[int] = None
        self._day_signals: int = 0
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

        # Daily signal cap
        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = ts_sec // 86400
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= self.cfg.max_signals_per_day:
            self.last_no_signal_reason = "daily_cap_reached"
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
        dev_atr = (cur - vwap) / atr   # positive = above VWAP, negative = below

        entry = float(c)
        side = None

        if (
            self.cfg.allow_shorts
            and dev_atr >= float(self.cfg.min_vwap_dev_atr)   # price sufficiently above VWAP
            and rsi >= float(self.cfg.short_rsi_min)           # overbought
            and cur < open_cur                                  # current bar bearish (rejection)
            and cur > vwap                                      # still above VWAP
        ):
            side = "short"
            sl = max(high_cur, entry) + float(self.cfg.sl_atr_mult) * atr
            # FIX: TP1 IS the VWAP (full mean reversion target)
            tp1 = vwap
            # FIX: TP2 overshoots VWAP by tp2_atr (runner past the magnet)
            tp2 = vwap - float(self.cfg.tp2_atr) * atr
            if sl <= entry or tp1 >= entry or tp2 >= tp1:
                self.last_no_signal_reason = "short_levels_invalid"
                return None

        elif (
            self.cfg.allow_longs
            and dev_atr <= -float(self.cfg.min_vwap_dev_atr)  # price sufficiently below VWAP
            and rsi <= float(self.cfg.long_rsi_max)            # oversold
            and cur > open_cur                                  # current bar bullish (reclaim)
            and cur < vwap                                      # still below VWAP
        ):
            side = "long"
            sl = min(low_cur, entry) - float(self.cfg.sl_atr_mult) * atr
            # FIX: TP1 IS the VWAP
            tp1 = vwap
            # FIX: TP2 overshoots VWAP
            tp2 = vwap + float(self.cfg.tp2_atr) * atr
            if sl >= entry or tp1 <= entry or tp2 <= tp1:
                self.last_no_signal_reason = "long_levels_invalid"
                return None

        else:
            self.last_no_signal_reason = "no_signal_conditions"
            return None

        tp1_frac = min(0.90, max(0.10, float(self.cfg.tp1_frac)))
        self._cooldown = max(0, int(self.cfg.cooldown_bars_5m))
        self._day_signals += 1

        sig = TradeSignal(
            strategy=self.NAME,
            symbol=store.symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[tp1_frac, 1.0 - tp1_frac],
            trailing_atr_mult=0.0,
            time_stop_bars=max(0, int(self.cfg.time_stop_bars_5m)),
            reason=(
                f"avw1_vwap_revert|vwap={vwap:.4f}|er={er:.3f}"
                f"|rsi={rsi:.1f}|dev_atr={dev_atr:.2f}"
                f"|tp1=vwap|tp2={'over' if side == 'long' else 'under'}shoot"
            ),
        )
        return sig if sig.validate() else None
