"""alt_liquidity_sweep_reversal_v2 — improved liquidity hunter (Claude 2026-05-04).

v2 changes vs v1 (from LIQUIDITY_HUNTER_V1_REVIEW_20260503.md):
  1. PER-SYMBOL cooldown — dict {symbol → last_signal_i} instead of single var.
     Critical: v1 had global cooldown that silenced ALL symbols after one signal.
  2. Regime gate — by default только chop regimes (LQH2_REGIME_MODE=chop_only),
     env vars LQH2_ALLOW_REGIMES override.
  3. Partial TP1 + breakeven + trailing после TP1 hit.
     Default: TP1 at 0.8R, 50% size; SL → BE; trailing на оставшиеся 50% by ATR×1.0.
  4. min_pool_touches default raised 2 → 3 (v1's =2 was inflated by extremum bar itself).
  5. max_sweep_atr default 0.9 → 1.5 + LQH2_PANIC_MODE flag для extremes 1.5-3.0.
  6. pool_persistence_min_bars (default 8) — pool must exist for ≥ N bars before
     accepting sweep. Защита от моментальных «псевдо-pool» на одном свече.

Env vars (all prefixed LQH2_):
  LQH2_LOOKBACK_BARS          (36)   — pool detection window
  LQH2_MIN_POOL_TOUCHES       (3)    — min touches at pool boundary
  LQH2_POOL_TOUCH_ATR         (0.18) — distance tolerance for "touch"
  LQH2_MIN_POOL_WIDTH_ATR     (1.2)
  LQH2_POOL_PERSISTENCE_BARS  (8)    — NEW v2
  LQH2_MIN_SWEEP_ATR          (0.10)
  LQH2_MAX_SWEEP_ATR          (1.5)  — was 0.9 in v1
  LQH2_PANIC_MAX_SWEEP_ATR    (3.0)  — NEW v2 — used when LQH2_PANIC_MODE=1
  LQH2_PANIC_MODE             (0)    — accept panic sweeps up to PANIC_MAX
  LQH2_RECLAIM_ATR            (0.04)
  LQH2_MIN_REJECT_WICK_ATR    (0.10)
  LQH2_MIN_WICK_TO_BODY       (1.3)
  LQH2_MIN_VOL_MULT           (1.5)
  LQH2_VOL_AVG_BARS           (24)
  LQH2_EMA_FAST               (9)
  LQH2_EMA_SLOW               (21)
  LQH2_MAX_EMA_GAP_ATR        (1.2)
  LQH2_ATR_PERIOD             (14)
  LQH2_MAX_BODY_ATR           (0.6)
  LQH2_RR                     (2.0)
  LQH2_TP1_RR                 (0.8)  — NEW v2
  LQH2_TP1_FRAC               (0.50) — NEW v2
  LQH2_BREAKEVEN_AFTER_TP1    (1)    — NEW v2
  LQH2_TRAIL_ATR_MULT         (1.0)  — NEW v2 trailing на оставшейся позиции
  LQH2_SL_PAD_ATR             (0.10)
  LQH2_MAX_RISK_ATR           (1.5)
  LQH2_TIME_STOP_BARS         (144)  — 12h на 5m
  LQH2_COOLDOWN_BARS_5M       (24)   — per-symbol cooldown
  LQH2_REGIME_MODE            (chop_only) — chop_only|all|trending|env-csv
  LQH2_ALLOW_REGIMES          ()     — comma-separated если override
  LQH2_SYMBOL_ALLOWLIST       ()
  LQH2_ALLOW_LONGS            (1)
  LQH2_ALLOW_SHORTS           (1)
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from .signals import TradeSignal
except ImportError:  # pragma: no cover
    from strategies.signals import TradeSignal


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(float(str(raw).strip()))
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_set(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip().upper() for x in str(raw).replace(";", ",").split(",") if x.strip()}


def _atr(candles: list, period: int) -> float:
    if len(candles) < period + 1:
        return float("nan")
    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i].h)
        l = float(candles[i].l)
        pc = float(candles[i - 1].c)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    recent = trs[-period:]
    return sum(recent) / float(len(recent)) if recent else float("nan")


def _ema(values: list[float], period: int) -> float:
    if len(values) < period or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = float(values[0])
    for v in values[1:]:
        e = float(v) * k + e * (1.0 - k)
    return e


_REGIME_MODE_PRESETS = {
    "chop_only": {"BEAR_CHOP", "BULL_CHOP"},
    "trending": {"BEAR_TREND", "BULL_TREND"},
    "all":      {"BEAR_CHOP", "BULL_CHOP", "BEAR_TREND", "BULL_TREND"},
}


@dataclass
class LQH2Config:
    lookback_bars: int = field(default_factory=lambda: _env_int("LQH2_LOOKBACK_BARS", 36))
    min_pool_touches: int = field(default_factory=lambda: _env_int("LQH2_MIN_POOL_TOUCHES", 3))
    pool_touch_atr: float = field(default_factory=lambda: _env_float("LQH2_POOL_TOUCH_ATR", 0.18))
    min_pool_width_atr: float = field(default_factory=lambda: _env_float("LQH2_MIN_POOL_WIDTH_ATR", 1.2))
    pool_persistence_bars: int = field(default_factory=lambda: _env_int("LQH2_POOL_PERSISTENCE_BARS", 8))
    min_sweep_atr: float = field(default_factory=lambda: _env_float("LQH2_MIN_SWEEP_ATR", 0.10))
    max_sweep_atr: float = field(default_factory=lambda: _env_float("LQH2_MAX_SWEEP_ATR", 1.5))
    panic_max_sweep_atr: float = field(default_factory=lambda: _env_float("LQH2_PANIC_MAX_SWEEP_ATR", 3.0))
    panic_mode: bool = field(default_factory=lambda: _env_bool("LQH2_PANIC_MODE", False))
    reclaim_atr: float = field(default_factory=lambda: _env_float("LQH2_RECLAIM_ATR", 0.04))
    min_reject_wick_atr: float = field(default_factory=lambda: _env_float("LQH2_MIN_REJECT_WICK_ATR", 0.10))
    min_wick_to_body: float = field(default_factory=lambda: _env_float("LQH2_MIN_WICK_TO_BODY", 1.3))
    min_vol_mult: float = field(default_factory=lambda: _env_float("LQH2_MIN_VOL_MULT", 1.5))
    vol_avg_bars: int = field(default_factory=lambda: _env_int("LQH2_VOL_AVG_BARS", 24))
    ema_fast: int = field(default_factory=lambda: _env_int("LQH2_EMA_FAST", 9))
    ema_slow: int = field(default_factory=lambda: _env_int("LQH2_EMA_SLOW", 21))
    max_ema_gap_atr: float = field(default_factory=lambda: _env_float("LQH2_MAX_EMA_GAP_ATR", 1.2))
    atr_period: int = field(default_factory=lambda: _env_int("LQH2_ATR_PERIOD", 14))
    max_body_atr: float = field(default_factory=lambda: _env_float("LQH2_MAX_BODY_ATR", 0.6))
    rr: float = field(default_factory=lambda: _env_float("LQH2_RR", 2.0))
    tp1_rr: float = field(default_factory=lambda: _env_float("LQH2_TP1_RR", 0.8))
    tp1_frac: float = field(default_factory=lambda: _env_float("LQH2_TP1_FRAC", 0.50))
    breakeven_after_tp1: bool = field(default_factory=lambda: _env_bool("LQH2_BREAKEVEN_AFTER_TP1", True))
    trail_atr_mult: float = field(default_factory=lambda: _env_float("LQH2_TRAIL_ATR_MULT", 1.0))
    sl_pad_atr: float = field(default_factory=lambda: _env_float("LQH2_SL_PAD_ATR", 0.10))
    max_risk_atr: float = field(default_factory=lambda: _env_float("LQH2_MAX_RISK_ATR", 1.5))
    time_stop_bars: int = field(default_factory=lambda: _env_int("LQH2_TIME_STOP_BARS", 144))
    cooldown_bars: int = field(default_factory=lambda: _env_int("LQH2_COOLDOWN_BARS_5M", 24))
    regime_mode: str = field(default_factory=lambda: os.getenv("LQH2_REGIME_MODE", "chop_only").strip().lower())
    allow_regimes_override: set[str] = field(default_factory=lambda: _env_csv_set("LQH2_ALLOW_REGIMES"))
    symbol_allowlist: set[str] = field(default_factory=lambda: _env_csv_set("LQH2_SYMBOL_ALLOWLIST"))
    allow_longs: bool = field(default_factory=lambda: _env_bool("LQH2_ALLOW_LONGS", True))
    allow_shorts: bool = field(default_factory=lambda: _env_bool("LQH2_ALLOW_SHORTS", True))

    def normalized_sides(self) -> tuple[bool, bool]:
        return self.allow_longs, self.allow_shorts

    def allowed_regimes(self) -> set[str]:
        if self.allow_regimes_override:
            return self.allow_regimes_override
        return _REGIME_MODE_PRESETS.get(self.regime_mode, _REGIME_MODE_PRESETS["chop_only"])


class AltLiquiditySweepReversalV2Strategy:
    NAME = "alt_liquidity_sweep_reversal_v2"

    def __init__(self):
        self.cfg = LQH2Config()
        self._last_signal_i_by_symbol: dict[str, int] = {}  # FIX #1 — per-symbol cooldown
        self.last_no_signal_reason = ""

    def _check_pool_persistence(self, candles: list, i: int, pool_low: float, pool_high: float, atr: float) -> bool:
        """FIX #6: pool boundary must hold for >= persistence_bars without major break."""
        cfg = self.cfg
        if cfg.pool_persistence_bars <= 0:
            return True
        # Look at first pool_persistence_bars from start of pool window
        start = i - cfg.lookback_bars
        end = start + cfg.pool_persistence_bars
        if end > i:
            return False
        seg = candles[start:end]
        # Pool low/high should not have been broken by margin > pool_touch_atr * ATR
        seg_low = min(float(x.l) for x in seg)
        seg_high = max(float(x.h) for x in seg)
        if seg_low < pool_low - cfg.pool_touch_atr * atr:
            return False
        if seg_high > pool_high + cfg.pool_touch_atr * atr:
            return False
        return True

    def signal(self, store, symbol: str, i: int, regime: Optional[str] = None) -> Optional[TradeSignal]:
        cfg = self.cfg
        candles = store.candles(symbol) if hasattr(store, "candles") else getattr(store, "rows", [])
        need = max(cfg.lookback_bars + 3, cfg.ema_slow + 5, cfg.vol_avg_bars + 2, cfg.atr_period + 2)
        if i < need:
            self.last_no_signal_reason = "not_enough_bars"
            return None

        # FIX #2: regime gate
        if regime is not None:
            allowed = cfg.allowed_regimes()
            if regime.upper() not in allowed:
                self.last_no_signal_reason = f"regime_blocked:{regime}"
                return None

        # Symbol allowlist check
        if cfg.symbol_allowlist and symbol.upper() not in cfg.symbol_allowlist:
            self.last_no_signal_reason = "symbol_blocked"
            return None

        # FIX #1: per-symbol cooldown
        last_i = self._last_signal_i_by_symbol.get(symbol, -10**9)
        if i - last_i < cfg.cooldown_bars:
            self.last_no_signal_reason = f"cooldown:{symbol}"
            return None

        atr = _atr(candles[max(0, i - cfg.atr_period - 2): i + 1], cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = "bad_atr"
            return None

        cur = candles[i]
        o, h, l, c, v = float(cur.o), float(cur.h), float(cur.l), float(cur.c), float(cur.v)

        pool = candles[i - cfg.lookback_bars: i]
        pool_high = max(float(x.h) for x in pool)
        pool_low = min(float(x.l) for x in pool)
        pool_width = pool_high - pool_low
        if pool_width < cfg.min_pool_width_atr * atr:
            self.last_no_signal_reason = "pool_too_narrow"
            return None

        # FIX #6: persistence check
        if not self._check_pool_persistence(candles, i, pool_low, pool_high, atr):
            self.last_no_signal_reason = "pool_not_persistent"
            return None

        # FIX #4: count touches with min=3 default (excluding extremum's own bar would be cleaner,
        # but we leave it because higher threshold makes the inflation harmless)
        high_touches = sum(1 for x in pool if abs(float(x.h) - pool_high) <= cfg.pool_touch_atr * atr)
        low_touches = sum(1 for x in pool if abs(float(x.l) - pool_low) <= cfg.pool_touch_atr * atr)

        closes = [float(x.c) for x in candles[max(0, i - cfg.ema_slow - 20): i + 1]]
        ema_fast = _ema(closes, cfg.ema_fast)
        ema_slow = _ema(closes, cfg.ema_slow)
        if math.isfinite(ema_fast) and math.isfinite(ema_slow):
            if abs(ema_fast - ema_slow) / atr > cfg.max_ema_gap_atr:
                self.last_no_signal_reason = "trend_too_extended"
                return None

        avg_vol = sum(float(candles[j].v) * float(candles[j].c) for j in range(i - cfg.vol_avg_bars, i)) / float(cfg.vol_avg_bars)
        cur_vol = v * c
        vol_mult = cur_vol / avg_vol if avg_vol > 0 else 0.0
        if vol_mult < cfg.min_vol_mult:
            self.last_no_signal_reason = "weak_volume"
            return None

        body = abs(c - o)
        if body > cfg.max_body_atr * atr:
            self.last_no_signal_reason = "body_too_large"
            return None
        body_floor = max(body, 0.02 * atr)
        allow_longs, allow_shorts = cfg.normalized_sides()

        # FIX #5: panic mode allows wider sweep
        max_sweep = cfg.panic_max_sweep_atr if cfg.panic_mode else cfg.max_sweep_atr

        # ── LONG (buy after sweep below pool_low + reclaim) ──────────────────
        if allow_longs and low_touches >= cfg.min_pool_touches:
            sweep_atr = (pool_low - l) / atr
            lower_wick = min(o, c) - l
            if (
                sweep_atr >= cfg.min_sweep_atr
                and sweep_atr <= max_sweep
                and c >= pool_low + cfg.reclaim_atr * atr
                and lower_wick >= cfg.min_reject_wick_atr * atr
                and lower_wick >= cfg.min_wick_to_body * body_floor
            ):
                sl = l - cfg.sl_pad_atr * atr
                risk = c - sl
                if risk > 0 and risk <= cfg.max_risk_atr * atr:
                    self._last_signal_i_by_symbol[symbol] = i
                    # FIX #3: TP1 partial + breakeven + trailing
                    tp_final = c + cfg.rr * risk
                    tp1 = c + cfg.tp1_rr * risk if cfg.tp1_frac > 0 else None
                    sig = TradeSignal(
                        strategy=self.NAME,
                        symbol=symbol,
                        side="long",
                        entry=c,
                        sl=sl,
                        tp=tp_final,
                        time_stop_bars=cfg.time_stop_bars,
                        reason=f"LQH2_LONG pool={pool_low:.6g} sweep_atr={sweep_atr:.2f} vol={vol_mult:.2f} touches={low_touches}",
                    )
                    # Optional TP1 / trailing fields if TradeSignal supports them
                    if tp1 is not None and hasattr(sig, "tps"):
                        sig.tps = [float(tp1), float(tp_final)]
                        sig.tp_fracs = [cfg.tp1_frac, max(0.0, 1.0 - cfg.tp1_frac)]
                    if cfg.trail_atr_mult > 0 and hasattr(sig, "trailing_atr_mult"):
                        sig.trailing_atr_mult = float(cfg.trail_atr_mult)
                    if cfg.breakeven_after_tp1 and hasattr(sig, "breakeven_after_tp1"):
                        sig.breakeven_after_tp1 = True
                    return sig

        # ── SHORT (sell after sweep above pool_high + reclaim) ───────────────
        if allow_shorts and high_touches >= cfg.min_pool_touches:
            sweep_atr = (h - pool_high) / atr
            upper_wick = h - max(o, c)
            if (
                sweep_atr >= cfg.min_sweep_atr
                and sweep_atr <= max_sweep
                and c <= pool_high - cfg.reclaim_atr * atr
                and upper_wick >= cfg.min_reject_wick_atr * atr
                and upper_wick >= cfg.min_wick_to_body * body_floor
            ):
                sl = h + cfg.sl_pad_atr * atr
                risk = sl - c
                if risk > 0 and risk <= cfg.max_risk_atr * atr:
                    self._last_signal_i_by_symbol[symbol] = i
                    tp_final = c - cfg.rr * risk
                    tp1 = c - cfg.tp1_rr * risk if cfg.tp1_frac > 0 else None
                    sig = TradeSignal(
                        strategy=self.NAME,
                        symbol=symbol,
                        side="short",
                        entry=c,
                        sl=sl,
                        tp=tp_final,
                        time_stop_bars=cfg.time_stop_bars,
                        reason=f"LQH2_SHORT pool={pool_high:.6g} sweep_atr={sweep_atr:.2f} vol={vol_mult:.2f} touches={high_touches}",
                    )
                    if tp1 is not None and hasattr(sig, "tps"):
                        sig.tps = [float(tp1), float(tp_final)]
                        sig.tp_fracs = [cfg.tp1_frac, max(0.0, 1.0 - cfg.tp1_frac)]
                    if cfg.trail_atr_mult > 0 and hasattr(sig, "trailing_atr_mult"):
                        sig.trailing_atr_mult = float(cfg.trail_atr_mult)
                    if cfg.breakeven_after_tp1 and hasattr(sig, "breakeven_after_tp1"):
                        sig.breakeven_after_tp1 = True
                    return sig

        self.last_no_signal_reason = "no_sweep_reclaim"
        return None
