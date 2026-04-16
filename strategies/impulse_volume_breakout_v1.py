"""
impulse_volume_breakout_v1 — 5m impulse breakout with shallow retrace entry.

This is intentionally a different family from the old breakout retest logic:
- not a slow 4h level reclaim,
- not a blind market chase into a pump,
- but a short-lived high-volume impulse, followed by a controlled retrace,
  and then a continuation entry while the breakout level is still defended.

Typical use:
  - current90 / mixed regime research on liquid pump-capable symbols,
  - future bull / momentum sleeve if the standalone edge proves real.
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
    if not values:
        return float("nan")
    tail = values[-period:] if len(values) >= period else values
    if not tail:
        return float("nan")
    return sum(tail) / float(len(tail))


@dataclass
class ImpulseVolumeBreakoutV1Config:
    entry_tf: str = "5"
    regime_tf: str = "60"
    atr_period: int = 14
    breakout_lookback_bars: int = 24
    impulse_lookback_bars: int = 18
    min_impulse_pct: float = 0.045
    min_vol_mult: float = 1.8
    vol_period: int = 20
    min_body_frac: float = 0.45
    min_bar_range_atr: float = 1.20
    breakout_buffer_atr: float = 0.10
    retrace_min_frac: float = 0.25
    retrace_max_frac: float = 0.60
    reclaim_atr: float = 0.08
    entry_body_min_frac: float = 0.25
    touch_below_breakout_atr: float = 0.20
    invalidation_close_atr: float = 0.35
    # RR tuned 2026-04-16: avg_win $0.39 < avg_loss $0.58 at RR=1.8.
    # Raised to 2.2 + tighter SL to fix the imbalance.
    # Must re-validate with WF-22 on server before enabling in bear stack.
    sl_atr: float = 0.75       # was 1.0 — tighter stop, smaller loss when wrong
    rr: float = 2.2            # was 1.8 — larger winner to fix avg_win < avg_loss
    tp1_rr: float = 1.1        # was 0.9 — partial TP proportional to new RR
    trail_atr_mult: float = 1.2
    trail_activate_rr: float = 1.1
    min_stop_pct: float = 0.008
    max_stop_pct: float = 0.060
    time_stop_bars_5m: int = 72
    cooldown_bars_5m: int = 12
    max_wait_bars_5m: int = 8
    allow_longs: bool = True
    regime_mode: str = "off"
    regime_ema_fast: int = 20
    regime_ema_slow: int = 50
    # ── 4h MACD macro filter (added 2026-04-16) ──────────────────────────
    # IVB1 is a LONG-ONLY momentum strategy. In bear markets it has 0% WR
    # (Q1-2026: 9 trades, 0 wins, -5.71%). Adding a 4h MACD histogram check
    # blocks entries when macro is bearish.
    # IVB1_MACRO_REQUIRE_BULL=1 (default): only enter longs when 4h MACD hist > 0
    # IVB1_MACRO_REQUIRE_BULL=0: disable filter (old behaviour)
    macro_require_bull: bool = True   # block longs when 4h hist <= 0
    macro_tf: str = "240"             # timeframe for MACD check
    macro_macd_fast: int = 12
    macro_macd_slow: int = 26
    macro_macd_signal: int = 9


class ImpulseVolumeBreakoutV1Strategy:
    STRATEGY_NAME = "impulse_volume_breakout_v1"

    def __init__(self, cfg: Optional[ImpulseVolumeBreakoutV1Config] = None):
        self.cfg = cfg or ImpulseVolumeBreakoutV1Config()
        self._load_runtime_config()
        self._cooldown = 0
        self._last_entry_ts: Optional[int] = None
        self._armed: Optional[dict] = None
        self.last_no_signal_reason = ""

    def _load_runtime_config(self) -> None:
        self.cfg.entry_tf = os.getenv("IVB1_ENTRY_TF", self.cfg.entry_tf)
        self.cfg.regime_tf = os.getenv("IVB1_REGIME_TF", self.cfg.regime_tf)
        self.cfg.atr_period = _env_int("IVB1_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.breakout_lookback_bars = _env_int("IVB1_BREAKOUT_LOOKBACK_BARS", self.cfg.breakout_lookback_bars)
        self.cfg.impulse_lookback_bars = _env_int("IVB1_IMPULSE_LOOKBACK_BARS", self.cfg.impulse_lookback_bars)
        self.cfg.min_impulse_pct = _env_float("IVB1_MIN_IMPULSE_PCT", self.cfg.min_impulse_pct)
        self.cfg.min_vol_mult = _env_float("IVB1_MIN_VOL_MULT", self.cfg.min_vol_mult)
        self.cfg.vol_period = _env_int("IVB1_VOL_PERIOD", self.cfg.vol_period)
        self.cfg.min_body_frac = _env_float("IVB1_MIN_BODY_FRAC", self.cfg.min_body_frac)
        self.cfg.min_bar_range_atr = _env_float("IVB1_MIN_BAR_RANGE_ATR", self.cfg.min_bar_range_atr)
        self.cfg.breakout_buffer_atr = _env_float("IVB1_BREAKOUT_BUFFER_ATR", self.cfg.breakout_buffer_atr)
        self.cfg.retrace_min_frac = _env_float("IVB1_RETRACE_MIN_FRAC", self.cfg.retrace_min_frac)
        self.cfg.retrace_max_frac = _env_float("IVB1_RETRACE_MAX_FRAC", self.cfg.retrace_max_frac)
        self.cfg.reclaim_atr = _env_float("IVB1_RECLAIM_ATR", self.cfg.reclaim_atr)
        self.cfg.entry_body_min_frac = _env_float("IVB1_ENTRY_BODY_MIN_FRAC", self.cfg.entry_body_min_frac)
        self.cfg.touch_below_breakout_atr = _env_float("IVB1_TOUCH_BELOW_BREAKOUT_ATR", self.cfg.touch_below_breakout_atr)
        self.cfg.invalidation_close_atr = _env_float("IVB1_INVALIDATION_CLOSE_ATR", self.cfg.invalidation_close_atr)
        self.cfg.sl_atr = _env_float("IVB1_SL_ATR", self.cfg.sl_atr)
        self.cfg.rr = _env_float("IVB1_RR", self.cfg.rr)
        self.cfg.tp1_rr = _env_float("IVB1_TP1_RR", self.cfg.tp1_rr)
        self.cfg.trail_atr_mult = _env_float("IVB1_TRAIL_ATR_MULT", self.cfg.trail_atr_mult)
        self.cfg.trail_activate_rr = _env_float("IVB1_TRAIL_ACTIVATE_RR", self.cfg.trail_activate_rr)
        self.cfg.min_stop_pct = _env_float("IVB1_MIN_STOP_PCT", self.cfg.min_stop_pct)
        self.cfg.max_stop_pct = _env_float("IVB1_MAX_STOP_PCT", self.cfg.max_stop_pct)
        self.cfg.time_stop_bars_5m = _env_int("IVB1_TIME_STOP_BARS_5M", self.cfg.time_stop_bars_5m)
        self.cfg.cooldown_bars_5m = _env_int("IVB1_COOLDOWN_BARS_5M", self.cfg.cooldown_bars_5m)
        self.cfg.max_wait_bars_5m = _env_int("IVB1_MAX_WAIT_BARS_5M", self.cfg.max_wait_bars_5m)
        self.cfg.allow_longs = _env_bool("IVB1_ALLOW_LONGS", self.cfg.allow_longs)
        self.cfg.regime_mode = os.getenv("IVB1_REGIME_MODE", self.cfg.regime_mode)
        self.cfg.regime_ema_fast = _env_int("IVB1_REGIME_EMA_FAST", self.cfg.regime_ema_fast)
        self.cfg.regime_ema_slow = _env_int("IVB1_REGIME_EMA_SLOW", self.cfg.regime_ema_slow)
        self.cfg.macro_require_bull = _env_bool("IVB1_MACRO_REQUIRE_BULL", self.cfg.macro_require_bull)
        self.cfg.macro_tf = os.getenv("IVB1_MACRO_TF", self.cfg.macro_tf)
        self.cfg.macro_macd_fast = _env_int("IVB1_MACRO_MACD_FAST", self.cfg.macro_macd_fast)
        self.cfg.macro_macd_slow = _env_int("IVB1_MACRO_MACD_SLOW", self.cfg.macro_macd_slow)
        self.cfg.macro_macd_signal = _env_int("IVB1_MACRO_MACD_SIGNAL", self.cfg.macro_macd_signal)

        self._allow = _env_csv_set("IVB1_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("IVB1_SYMBOL_DENYLIST")

    def _refresh_runtime_config(self) -> None:
        self._load_runtime_config()

    def _macro_ok(self, store) -> bool:
        """4h MACD histogram check — block longs when macro is bearish.

        Returns True if longs are allowed:
          - macro_require_bull=False → always OK (old behaviour)
          - macro_require_bull=True  → only OK when 4h MACD hist > 0

        Uses standard MACD(12,26,9). Mirrors the filter in elder_triple_screen_v2
        so all momentum strategies share the same macro gate.
        """
        if not self.cfg.macro_require_bull:
            return True
        needed = self.cfg.macro_macd_slow + self.cfg.macro_macd_signal + 5
        rows_4h = store.fetch_klines(store.symbol, self.cfg.macro_tf, needed + 10) or []
        if len(rows_4h) < needed:
            self.last_no_signal_reason = "macro_history_short"
            return False
        closes = [float(r[4]) for r in rows_4h]
        # EMA helpers
        def _ema_seq(vals: List[float], period: int) -> List[float]:
            k = 2.0 / (period + 1.0)
            e = vals[0]
            out = [e]
            for v in vals[1:]:
                e = v * k + e * (1.0 - k)
                out.append(e)
            return out
        fast_seq = _ema_seq(closes, self.cfg.macro_macd_fast)
        slow_seq = _ema_seq(closes, self.cfg.macro_macd_slow)
        # align (fast_seq is longer, trim to slow length)
        offset = len(fast_seq) - len(slow_seq)
        macd_line = [fast_seq[i + offset] - slow_seq[i] for i in range(len(slow_seq))]
        signal_line = _ema_seq(macd_line, self.cfg.macro_macd_signal)
        hist = macd_line[-1] - signal_line[-1]
        if hist <= 0:
            self.last_no_signal_reason = f"macro_bearish_hist={hist:.6f}"
            return False
        return True

    def _regime_ok(self, store) -> bool:
        if str(self.cfg.regime_mode).strip().lower() != "ema":
            return True
        rows = store.fetch_klines(store.symbol, self.cfg.regime_tf, max(100, self.cfg.regime_ema_slow + 20)) or []
        if len(rows) < self.cfg.regime_ema_slow + 20:
            self.last_no_signal_reason = "regime_history_short"
            return False
        closes = [float(r[4]) for r in rows]
        ema_fast = _ema(closes, self.cfg.regime_ema_fast)
        ema_slow = _ema(closes, self.cfg.regime_ema_slow)
        if not all(math.isfinite(x) for x in (ema_fast, ema_slow)):
            self.last_no_signal_reason = "regime_invalid"
            return False
        return ema_fast > ema_slow

    def _arm_if_impulse(self, rows_5m: List[list], atr_5m: float, vol_base: float) -> None:
        if self._armed is not None:
            return
        if not self.cfg.allow_longs:
            self.last_no_signal_reason = "longs_disabled"
            return

        opens = [float(r[1]) for r in rows_5m]
        highs = [float(r[2]) for r in rows_5m]
        lows = [float(r[3]) for r in rows_5m]
        closes = [float(r[4]) for r in rows_5m]
        volumes = [float(r[5]) if len(r) > 5 else 0.0 for r in rows_5m]

        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        cur_close = closes[-1]
        cur_volume = volumes[-1]
        prior_high = max(highs[-(self.cfg.breakout_lookback_bars + 1):-1])
        recent_low = min(lows[-(self.cfg.impulse_lookback_bars + 1):-1])
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range
        impulse_pct = (cur_close - recent_low) / max(1e-12, recent_low)
        vol_mult = cur_volume / max(1e-12, vol_base) if vol_base > 0 else 0.0
        broke_out = cur_close > prior_high + self.cfg.breakout_buffer_atr * atr_5m
        bar_range_atr = bar_range / max(1e-12, atr_5m)

        if cur_close <= cur_open:
            self.last_no_signal_reason = "impulse_bar_not_bullish"
            return
        if not broke_out:
            self.last_no_signal_reason = "impulse_no_breakout"
            return
        if impulse_pct < self.cfg.min_impulse_pct:
            self.last_no_signal_reason = f"impulse_too_small_{impulse_pct:.3f}"
            return
        if vol_mult < self.cfg.min_vol_mult:
            self.last_no_signal_reason = f"impulse_vol_weak_{vol_mult:.2f}"
            return
        if body_frac < self.cfg.min_body_frac:
            self.last_no_signal_reason = f"impulse_body_weak_{body_frac:.2f}"
            return
        if bar_range_atr < self.cfg.min_bar_range_atr:
            self.last_no_signal_reason = f"impulse_range_weak_{bar_range_atr:.2f}"
            return

        self._armed = {
            "armed_ts": int(float(rows_5m[-1][0])),
            "breakout_level": float(prior_high),
            "impulse_high": float(cur_high),
            "impulse_low": float(max(prior_high, cur_low)),
            "impulse_range": float(max(cur_high - prior_high, atr_5m * 0.5)),
            "atr": float(atr_5m),
        }
        self.last_no_signal_reason = "armed_impulse_breakout"

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (ts_ms, o, h, l, c, v)
        self.last_no_signal_reason = ""
        self._refresh_runtime_config()

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            self.last_no_signal_reason = "symbol_not_allowed"
            return None
        if sym in self._deny:
            self.last_no_signal_reason = "symbol_denied"
            return None

        rows_5m = store.fetch_klines(store.symbol, self.cfg.entry_tf, max(160, self.cfg.breakout_lookback_bars + self.cfg.impulse_lookback_bars + self.cfg.vol_period + self.cfg.atr_period + 20)) or []
        min_rows = max(self.cfg.breakout_lookback_bars + 3, self.cfg.impulse_lookback_bars + 3, self.cfg.vol_period + 3, self.cfg.atr_period + 3)
        if len(rows_5m) < min_rows:
            self.last_no_signal_reason = "not_enough_5m_bars"
            return None

        bar_ts = int(float(rows_5m[-1][0]))
        if self._last_entry_ts is not None and bar_ts == self._last_entry_ts:
            self.last_no_signal_reason = "same_entry_bar"
            return None
        self._last_entry_ts = bar_ts

        if self._cooldown > 0:
            self._cooldown -= 1
            self.last_no_signal_reason = "cooldown"
            return None
        if not self._macro_ok(store):
            return None
        if not self._regime_ok(store):
            return None

        closes = [float(r[4]) for r in rows_5m]
        opens = [float(r[1]) for r in rows_5m]
        highs = [float(r[2]) for r in rows_5m]
        lows = [float(r[3]) for r in rows_5m]
        volumes = [float(r[5]) if len(r) > 5 else 0.0 for r in rows_5m]
        atr_5m = _atr_from_rows(rows_5m, self.cfg.atr_period)
        vol_base = _sma(volumes[:-1], self.cfg.vol_period)

        if not math.isfinite(atr_5m) or atr_5m <= 0:
            self.last_no_signal_reason = "atr_invalid"
            return None
        if not math.isfinite(vol_base) or vol_base <= 0:
            self.last_no_signal_reason = "volume_baseline_invalid"
            return None

        cur_open = opens[-1]
        cur_high = highs[-1]
        cur_low = lows[-1]
        cur_close = closes[-1]
        bar_range = max(1e-12, cur_high - cur_low)
        body_frac = abs(cur_close - cur_open) / bar_range

        armed = self._armed
        if armed is not None:
            wait_bars = max(1, int((bar_ts - int(armed["armed_ts"])) / (5 * 60 * 1000)))
            breakout_level = float(armed["breakout_level"])
            impulse_high = float(armed["impulse_high"])
            impulse_range = float(armed["impulse_range"])
            risk_atr = max(float(armed["atr"]) * 0.85, atr_5m)
            zone_top = impulse_high - self.cfg.retrace_min_frac * impulse_range
            zone_bot = impulse_high - self.cfg.retrace_max_frac * impulse_range

            if wait_bars > self.cfg.max_wait_bars_5m:
                self._armed = None
                self.last_no_signal_reason = "armed_expired"
            elif cur_close < breakout_level - self.cfg.invalidation_close_atr * risk_atr:
                self._armed = None
                self.last_no_signal_reason = "armed_lost_breakout_level"
            else:
                touched_retrace = cur_low <= zone_top
                not_too_deep = cur_low >= max(zone_bot, breakout_level - self.cfg.touch_below_breakout_atr * risk_atr)
                bullish_reclaim = cur_close > cur_open and cur_close > breakout_level + self.cfg.reclaim_atr * risk_atr
                if touched_retrace and not_too_deep and bullish_reclaim and body_frac >= self.cfg.entry_body_min_frac:
                    entry = float(cur_close)
                    sl = breakout_level - self.cfg.sl_atr * risk_atr
                    if sl >= entry:
                        self.last_no_signal_reason = "sl_at_or_above_entry"
                        return None
                    risk = entry - sl
                    stop_pct = risk / max(1e-12, entry)
                    if stop_pct < self.cfg.min_stop_pct:
                        self.last_no_signal_reason = f"stop_too_tight_{stop_pct:.4f}"
                        return None
                    if stop_pct > self.cfg.max_stop_pct:
                        self.last_no_signal_reason = f"stop_too_wide_{stop_pct:.4f}"
                        return None

                    tp1 = entry + self.cfg.tp1_rr * risk
                    tp2 = entry + self.cfg.rr * risk
                    if tp2 <= tp1:
                        tp2 = tp1 + 0.5 * risk
                    self._armed = None
                    self._cooldown = max(0, self.cfg.cooldown_bars_5m)
                    return TradeSignal(
                        strategy=self.STRATEGY_NAME,
                        symbol=sym,
                        side="long",
                        entry=entry,
                        sl=sl,
                        tp=tp2,
                        tps=[tp1, tp2],
                        tp_fracs=[0.5, 0.5],
                        trailing_atr_mult=self.cfg.trail_atr_mult,
                        trailing_atr_period=self.cfg.atr_period,
                        trail_activate_rr=self.cfg.trail_activate_rr,
                        time_stop_bars=self.cfg.time_stop_bars_5m,
                        reason="impulse_retrace_long",
                    )
                self.last_no_signal_reason = "armed_waiting_retrace"
                return None

        self._arm_if_impulse(rows_5m, atr_5m, vol_base)
        return None
