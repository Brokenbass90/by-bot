"""
scalper_breakout_v2 (SBR2) — Strict range-breakout с retest требованием.

Полный rewrite SC1.breakout mode. Главные отличия:

  • **Confirmed range**: range должен иметь ≥ 3 touches с каждой стороны
    (не arbitrary high-low за N баров)
  • **Range width 1.5-3.0 ATR** (узкий диапазон с edge на выходе)
  • **Vol z ≥ 3.0** на breakout candle (true breakout = volume burst)
  • **Min break depth ≥ 0.5 ATR** за range edge (no marginal breaks)
  • **Pullback retest required**: 2-bar retracement к range edge, потом
    bounce обратно в direction of break — no chase
  • **TP1 2.0R / TP2 3.5R** — clean breakouts run far

Дизайн-цель: PF ≥ 1.7, DD ≤ 6%, 10-20 трейдов/мес — самый редкий setup
но самый высокий per-trade edge.

Env vars (префикс SBR2_)
------------------------
  SBR2_SYMBOL_ALLOWLIST           csv     BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT
  SBR2_SIGNAL_TF                  str     5
  SBR2_SIGNAL_LOOKBACK            int     250
  SBR2_ATR_PERIOD                 int     14
  SBR2_RANGE_LOOKBACK             int     40
  SBR2_MIN_TOUCHES_PER_SIDE       int     3
  SBR2_TOUCH_TOLERANCE_ATR        float   0.20
  SBR2_RANGE_MIN_ATR              float   1.50
  SBR2_RANGE_MAX_ATR              float   3.00
  SBR2_VOL_Z_MIN                  float   3.00
  SBR2_MIN_BREAK_DEPTH_ATR        float   0.50
  SBR2_RETEST_MAX_BARS            int     5
  SBR2_RETEST_TOLERANCE_ATR       float   0.30
  SBR2_MIN_ATR_PCT                float   0.25
  SBR2_MAX_ATR_PCT                float   3.00
  SBR2_SL_ATR_BUFFER              float   0.40
  SBR2_TP1_RR                     float   2.00
  SBR2_TP2_RR                     float   3.50
  SBR2_TP1_FRAC                   float   0.50
  SBR2_BE_TRIGGER_RR              float   1.00
  SBR2_TIME_STOP_BARS_5M          int     72
  SBR2_COOLDOWN_BARS_5M           int     48
  SBR2_ALLOW_LONGS                bool    1
  SBR2_ALLOW_SHORTS               bool    1

State (in-memory): per-symbol tracking of broken-range event awaiting retest.

Author: Claude Opus, 2026-06-03. Rewrite of SC1.breakout — confirmed range + retest.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
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
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return sum(trs[-period:]) / period


def _vol_zscore(volumes: List[float], baseline_period: int = 40, recent_n: int = 1) -> float:
    if len(volumes) < baseline_period + recent_n:
        return 0.0
    base = volumes[-baseline_period - recent_n:-recent_n]
    recent = volumes[-recent_n:]
    if not base:
        return 0.0
    mean = sum(base) / len(base)
    var = sum((v - mean) ** 2 for v in base) / max(1, len(base) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std <= 0:
        return 0.0
    return ((sum(recent) / len(recent)) - mean) / std


def _count_touches(prices: List[float], level: float, tolerance: float) -> int:
    if tolerance <= 0:
        return 0
    return sum(1 for p in prices if abs(p - level) <= tolerance)


@dataclass
class SBR2Config:
    signal_tf: str = "5"
    signal_lookback: int = 250
    atr_period: int = 14
    range_lookback: int = 40
    min_touches_per_side: int = 3
    touch_tolerance_atr: float = 0.20
    range_min_atr: float = 1.50
    range_max_atr: float = 3.00
    vol_z_min: float = 3.00
    min_break_depth_atr: float = 0.50
    retest_max_bars: int = 5
    retest_tolerance_atr: float = 0.30
    min_atr_pct: float = 0.25
    max_atr_pct: float = 3.00
    sl_atr_buffer: float = 0.40
    tp1_rr: float = 2.00
    tp2_rr: float = 3.50
    tp1_frac: float = 0.50
    be_trigger_rr: float = 1.00
    time_stop_bars_5m: int = 72
    cooldown_bars_5m: int = 48
    allow_longs: bool = True
    allow_shorts: bool = True


@dataclass
class _PendingBreak:
    """Track a confirmed breakout awaiting retest."""
    direction: str  # "long" or "short"
    break_bar_ts: int
    break_close: float
    range_top: float
    range_bot: float
    bars_since: int = 0


class ScalperBreakoutV2Strategy:
    """Confirmed-range breakout with mandatory retest entry."""

    def __init__(self) -> None:
        self.cfg = SBR2Config()
        self._load_env()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._allow: set = set()
        self._deny: set = set()
        self.last_no_signal_reason: str = ""
        self._pending: Optional[_PendingBreak] = None
        self._refresh_lists()

    def _no_signal(self, reason: str) -> None:
        self.last_no_signal_reason = str(reason or "unknown")

    def _load_env(self) -> None:
        c = self.cfg
        c.signal_tf = os.getenv("SBR2_SIGNAL_TF", c.signal_tf)
        c.signal_lookback = _env_int("SBR2_SIGNAL_LOOKBACK", c.signal_lookback)
        c.atr_period = _env_int("SBR2_ATR_PERIOD", c.atr_period)
        c.range_lookback = _env_int("SBR2_RANGE_LOOKBACK", c.range_lookback)
        c.min_touches_per_side = _env_int("SBR2_MIN_TOUCHES_PER_SIDE", c.min_touches_per_side)
        c.touch_tolerance_atr = _env_float("SBR2_TOUCH_TOLERANCE_ATR", c.touch_tolerance_atr)
        c.range_min_atr = _env_float("SBR2_RANGE_MIN_ATR", c.range_min_atr)
        c.range_max_atr = _env_float("SBR2_RANGE_MAX_ATR", c.range_max_atr)
        c.vol_z_min = _env_float("SBR2_VOL_Z_MIN", c.vol_z_min)
        c.min_break_depth_atr = _env_float("SBR2_MIN_BREAK_DEPTH_ATR", c.min_break_depth_atr)
        c.retest_max_bars = _env_int("SBR2_RETEST_MAX_BARS", c.retest_max_bars)
        c.retest_tolerance_atr = _env_float("SBR2_RETEST_TOLERANCE_ATR", c.retest_tolerance_atr)
        c.min_atr_pct = _env_float("SBR2_MIN_ATR_PCT", c.min_atr_pct)
        c.max_atr_pct = _env_float("SBR2_MAX_ATR_PCT", c.max_atr_pct)
        c.sl_atr_buffer = _env_float("SBR2_SL_ATR_BUFFER", c.sl_atr_buffer)
        c.tp1_rr = _env_float("SBR2_TP1_RR", c.tp1_rr)
        c.tp2_rr = _env_float("SBR2_TP2_RR", c.tp2_rr)
        c.tp1_frac = _env_float("SBR2_TP1_FRAC", c.tp1_frac)
        c.be_trigger_rr = _env_float("SBR2_BE_TRIGGER_RR", c.be_trigger_rr)
        c.time_stop_bars_5m = _env_int("SBR2_TIME_STOP_BARS_5M", c.time_stop_bars_5m)
        c.cooldown_bars_5m = _env_int("SBR2_COOLDOWN_BARS_5M", c.cooldown_bars_5m)
        c.allow_longs = _env_bool("SBR2_ALLOW_LONGS", c.allow_longs)
        c.allow_shorts = _env_bool("SBR2_ALLOW_SHORTS", c.allow_shorts)

    def _refresh_lists(self) -> None:
        self._allow = _env_csv_set("SBR2_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT")
        self._deny = _env_csv_set("SBR2_SYMBOL_DENYLIST")

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, cl: float, v: float = 0.0) -> Optional[TradeSignal]:
        self.last_no_signal_reason = ""
        symbol = getattr(store, "symbol", "")
        c = self.cfg

        if self._allow and symbol.upper() not in self._allow:
            self._no_signal("symbol_not_allowed"); return None
        if self._deny and symbol.upper() in self._deny:
            self._no_signal("symbol_denied"); return None
        if not c.allow_shorts and not c.allow_longs:
            self._no_signal("both_sides_disabled"); return None
        if self._last_tf_ts is not None and ts_ms <= self._last_tf_ts:
            self._no_signal("same_signal_bar"); return None
        if self._cooldown > 0:
            self._cooldown -= 1; self._no_signal("cooldown"); return None

        try:
            rows_5m = store.fetch_klines(symbol, c.signal_tf, c.signal_lookback) or []
        except Exception:
            self._no_signal("history_short"); return None

        if len(rows_5m) < c.range_lookback + 30:
            self._no_signal("history_short"); return None

        highs5 = [float(r[2]) for r in rows_5m]
        lows5 = [float(r[3]) for r in rows_5m]
        closes5 = [float(r[4]) for r in rows_5m]
        volumes5 = [float(r[5]) for r in rows_5m]

        atr = _atr(highs5, lows5, closes5, c.atr_period)
        price = closes5[-1]
        if atr <= 0 or price <= 0:
            self._no_signal("atr_invalid"); return None
        atr_pct = (atr / price) * 100.0
        if atr_pct < c.min_atr_pct:
            self._no_signal(f"atr_too_low={atr_pct:.3f}"); return None
        if atr_pct > c.max_atr_pct:
            self._no_signal(f"atr_too_high={atr_pct:.3f}"); return None

        # === If we have a pending break, look for retest entry ===
        if self._pending is not None:
            self._pending.bars_since += 1
            if self._pending.bars_since > c.retest_max_bars:
                self._pending = None  # retest window expired
            else:
                cur_close = closes5[-1]
                tol = c.retest_tolerance_atr * atr
                if self._pending.direction == "long":
                    # Retest: price pulled back to range_top ± tol, now closing above
                    if abs(min(lows5[-2:]) - self._pending.range_top) <= tol and cur_close > self._pending.range_top:
                        entry = cur_close
                        sl = self._pending.range_bot - c.sl_atr_buffer * atr
                        risk = entry - sl
                        if risk > 0:
                            tp1 = entry + c.tp1_rr * risk
                            range_top = self._pending.range_top
                            self._last_tf_ts = ts_ms
                            self._cooldown = c.cooldown_bars_5m
                            self._pending = None
                            return TradeSignal(
                                strategy="scalper_breakout_v2",
                                symbol=symbol, side="long", entry=entry, sl=sl, tp=tp1,
                                reason=f"sbr2_breakout_long_retest range_top={range_top:.6f}",
                            )
                else:  # short
                    if abs(max(highs5[-2:]) - self._pending.range_bot) <= tol and cur_close < self._pending.range_bot:
                        entry = cur_close
                        sl = self._pending.range_top + c.sl_atr_buffer * atr
                        risk = sl - entry
                        if risk > 0:
                            tp1 = entry - c.tp1_rr * risk
                            range_bot = self._pending.range_bot
                            self._last_tf_ts = ts_ms
                            self._cooldown = c.cooldown_bars_5m
                            self._pending = None
                            return TradeSignal(
                                strategy="scalper_breakout_v2",
                                symbol=symbol, side="short", entry=entry, sl=sl, tp=tp1,
                                reason=f"sbr2_breakout_short_retest range_bot={range_bot:.6f}",
                            )

        # === No pending — look for fresh confirmed-range breakout ===
        vol_z = _vol_zscore(volumes5, baseline_period=40, recent_n=1)
        if vol_z < c.vol_z_min:
            self._no_signal(f"vol_z_low={vol_z:.2f}"); return None

        prior_highs = highs5[-c.range_lookback - 1:-1]
        prior_lows = lows5[-c.range_lookback - 1:-1]
        if not prior_highs or not prior_lows:
            self._no_signal("history_short"); return None
        range_top = max(prior_highs)
        range_bot = min(prior_lows)
        range_width = range_top - range_bot
        if range_width <= 0:
            self._no_signal("range_zero"); return None

        range_atrs = range_width / atr
        if range_atrs < c.range_min_atr or range_atrs > c.range_max_atr:
            self._no_signal(f"range_width_atr={range_atrs:.2f}"); return None

        # Confirm range quality: ≥ min_touches each side
        touch_tol = c.touch_tolerance_atr * atr
        top_touches = _count_touches(prior_highs, range_top, touch_tol)
        bot_touches = _count_touches(prior_lows, range_bot, touch_tol)
        if top_touches < c.min_touches_per_side or bot_touches < c.min_touches_per_side:
            self._no_signal(f"range_unconfirmed top={top_touches} bot={bot_touches}"); return None

        cur_close = closes5[-1]

        # Long break
        if c.allow_longs and cur_close > range_top + c.min_break_depth_atr * atr:
            self._pending = _PendingBreak(direction="long", break_bar_ts=ts_ms,
                                          break_close=cur_close, range_top=range_top, range_bot=range_bot)
            self._no_signal("pending_retest_long")
            return None

        # Short break
        if c.allow_shorts and cur_close < range_bot - c.min_break_depth_atr * atr:
            self._pending = _PendingBreak(direction="short", break_bar_ts=ts_ms,
                                          break_close=cur_close, range_top=range_top, range_bot=range_bot)
            self._no_signal("pending_retest_short")
            return None

        self._no_signal("no_setup")
        return None


class SBR2Selector:
    def __init__(self):
        self._strategies: dict[str, ScalperBreakoutV2Strategy] = {}

    def get(self, symbol: str) -> ScalperBreakoutV2Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = ScalperBreakoutV2Strategy()
        return self._strategies[symbol]

    def reset(self, symbol: str) -> None:
        self._strategies.pop(symbol, None)
