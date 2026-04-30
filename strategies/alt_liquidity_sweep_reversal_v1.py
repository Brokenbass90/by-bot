"""alt_liquidity_sweep_reversal_v1 - crypto liquidity sweep/reclaim research sleeve.

Research-only strategy for stop-hunt style setups:
- identify a recent local liquidity pool at the rolling high/low;
- require the current 5m candle to sweep beyond that pool;
- require a close back inside the range plus rejection wick and volume context;
- enter the reversal with a stop beyond the sweep wick.

This is intentionally OHLCV-only. Real liquidation-map / order-book features can
be layered later, but this first version lets us test whether the price action
edge exists before adding external data dependencies.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from .signals import TradeSignal
except ImportError:  # pragma: no cover - fallback for direct execution
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


@dataclass
class LiquiditySweepReversalConfig:
    side_mode: str = field(default_factory=lambda: os.getenv("LQH_SIDE_MODE", "both").strip().lower())
    allow_longs: bool = field(default_factory=lambda: _env_bool("LQH_ALLOW_LONGS", True))
    allow_shorts: bool = field(default_factory=lambda: _env_bool("LQH_ALLOW_SHORTS", True))
    lookback_bars: int = field(default_factory=lambda: _env_int("LQH_LOOKBACK_BARS", 36))
    atr_period: int = field(default_factory=lambda: _env_int("LQH_ATR_PERIOD", 14))
    min_pool_touches: int = field(default_factory=lambda: _env_int("LQH_MIN_POOL_TOUCHES", 2))
    pool_touch_atr: float = field(default_factory=lambda: _env_float("LQH_POOL_TOUCH_ATR", 0.18))
    min_pool_width_atr: float = field(default_factory=lambda: _env_float("LQH_MIN_POOL_WIDTH_ATR", 1.2))
    max_ema_gap_atr: float = field(default_factory=lambda: _env_float("LQH_MAX_EMA_GAP_ATR", 2.4))
    ema_fast: int = field(default_factory=lambda: _env_int("LQH_EMA_FAST", 34))
    ema_slow: int = field(default_factory=lambda: _env_int("LQH_EMA_SLOW", 89))
    min_sweep_atr: float = field(default_factory=lambda: _env_float("LQH_MIN_SWEEP_ATR", 0.10))
    max_sweep_atr: float = field(default_factory=lambda: _env_float("LQH_MAX_SWEEP_ATR", 0.90))
    reclaim_atr: float = field(default_factory=lambda: _env_float("LQH_RECLAIM_ATR", 0.04))
    min_reject_wick_atr: float = field(default_factory=lambda: _env_float("LQH_MIN_REJECT_WICK_ATR", 0.10))
    min_wick_to_body: float = field(default_factory=lambda: _env_float("LQH_MIN_WICK_TO_BODY", 1.3))
    max_body_atr: float = field(default_factory=lambda: _env_float("LQH_MAX_BODY_ATR", 0.60))
    vol_avg_bars: int = field(default_factory=lambda: _env_int("LQH_VOL_AVG_BARS", 30))
    min_vol_mult: float = field(default_factory=lambda: _env_float("LQH_MIN_VOL_MULT", 1.15))
    sl_pad_atr: float = field(default_factory=lambda: _env_float("LQH_SL_PAD_ATR", 0.12))
    max_risk_atr: float = field(default_factory=lambda: _env_float("LQH_MAX_RISK_ATR", 1.30))
    rr: float = field(default_factory=lambda: _env_float("LQH_RR", 1.5))
    time_stop_bars: int = field(default_factory=lambda: _env_int("LQH_TIME_STOP_BARS_5M", 48))
    cooldown_bars: int = field(default_factory=lambda: _env_int("LQH_COOLDOWN_BARS_5M", 24))

    def normalized_sides(self) -> tuple[bool, bool]:
        if self.side_mode == "long":
            return True, False
        if self.side_mode == "short":
            return False, True
        if self.side_mode == "both":
            return self.allow_longs, self.allow_shorts
        return self.allow_longs, self.allow_shorts


class AltLiquiditySweepReversalV1Strategy:
    def __init__(self, cfg: Optional[LiquiditySweepReversalConfig] = None) -> None:
        self.cfg = cfg or LiquiditySweepReversalConfig()
        self._allow = _env_csv_set("LQH_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("LQH_SYMBOL_DENYLIST")
        self._last_signal_i = -10**9
        self.last_no_signal_reason = ""

    def _reload_cfg(self) -> None:
        self.cfg = LiquiditySweepReversalConfig()
        self._allow = _env_csv_set("LQH_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("LQH_SYMBOL_DENYLIST")

    def _allowed_symbol(self, symbol: str) -> bool:
        sym = symbol.upper()
        if self._allow and sym not in self._allow:
            self.last_no_signal_reason = "symbol_not_allowed"
            return False
        if self._deny and sym in self._deny:
            self.last_no_signal_reason = "symbol_denied"
            return False
        return True

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0) -> Optional[TradeSignal]:
        self._reload_cfg()
        cfg = self.cfg
        symbol = str(getattr(store, "symbol", "") or "").upper()
        if not self._allowed_symbol(symbol):
            return None

        try:
            i = int(getattr(store, "i5", getattr(store, "i", None)))
            candles = store.c5
        except Exception:
            self.last_no_signal_reason = "no_store_index"
            return None

        need = max(cfg.lookback_bars + 3, cfg.ema_slow + 5, cfg.vol_avg_bars + 2, cfg.atr_period + 2)
        if i < need:
            self.last_no_signal_reason = "not_enough_bars"
            return None
        if i - self._last_signal_i < cfg.cooldown_bars:
            self.last_no_signal_reason = "cooldown"
            return None

        atr = _atr(candles[max(0, i - cfg.atr_period - 2): i + 1], cfg.atr_period)
        if not math.isfinite(atr) or atr <= 0:
            self.last_no_signal_reason = "bad_atr"
            return None

        pool = candles[i - cfg.lookback_bars: i]
        pool_high = max(float(x.h) for x in pool)
        pool_low = min(float(x.l) for x in pool)
        pool_width = pool_high - pool_low
        if pool_width < cfg.min_pool_width_atr * atr:
            self.last_no_signal_reason = "pool_too_narrow"
            return None

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
        cur_vol = float(v) * float(c)
        vol_mult = cur_vol / avg_vol if avg_vol > 0 else 0.0
        if vol_mult < cfg.min_vol_mult:
            self.last_no_signal_reason = "weak_volume"
            return None

        body = abs(float(c) - float(o))
        if body > cfg.max_body_atr * atr:
            self.last_no_signal_reason = "body_too_large"
            return None
        body_floor = max(body, 0.02 * atr)
        allow_longs, allow_shorts = cfg.normalized_sides()

        if allow_longs and low_touches >= cfg.min_pool_touches:
            sweep_atr = (pool_low - float(l)) / atr
            lower_wick = min(float(o), float(c)) - float(l)
            if (
                sweep_atr >= cfg.min_sweep_atr
                and sweep_atr <= cfg.max_sweep_atr
                and float(c) >= pool_low + cfg.reclaim_atr * atr
                and lower_wick >= cfg.min_reject_wick_atr * atr
                and lower_wick >= cfg.min_wick_to_body * body_floor
            ):
                sl = float(l) - cfg.sl_pad_atr * atr
                risk = float(c) - sl
                if risk > 0 and risk <= cfg.max_risk_atr * atr:
                    self._last_signal_i = i
                    return TradeSignal(
                        strategy="alt_liquidity_sweep_reversal_v1",
                        symbol=symbol,
                        side="long",
                        entry=float(c),
                        sl=sl,
                        tp=float(c) + cfg.rr * risk,
                        time_stop_bars=cfg.time_stop_bars,
                        reason=f"LQH_LONG pool={pool_low:.6g} sweep_atr={sweep_atr:.2f} vol={vol_mult:.2f}",
                    )

        if allow_shorts and high_touches >= cfg.min_pool_touches:
            sweep_atr = (float(h) - pool_high) / atr
            upper_wick = float(h) - max(float(o), float(c))
            if (
                sweep_atr >= cfg.min_sweep_atr
                and sweep_atr <= cfg.max_sweep_atr
                and float(c) <= pool_high - cfg.reclaim_atr * atr
                and upper_wick >= cfg.min_reject_wick_atr * atr
                and upper_wick >= cfg.min_wick_to_body * body_floor
            ):
                sl = float(h) + cfg.sl_pad_atr * atr
                risk = sl - float(c)
                if risk > 0 and risk <= cfg.max_risk_atr * atr:
                    self._last_signal_i = i
                    return TradeSignal(
                        strategy="alt_liquidity_sweep_reversal_v1",
                        symbol=symbol,
                        side="short",
                        entry=float(c),
                        sl=sl,
                        tp=float(c) - cfg.rr * risk,
                        time_stop_bars=cfg.time_stop_bars,
                        reason=f"LQH_SHORT pool={pool_high:.6g} sweep_atr={sweep_atr:.2f} vol={vol_mult:.2f}",
                    )

        self.last_no_signal_reason = "no_sweep_reclaim"
        return None
