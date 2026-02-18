#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Optional, Any

from sr_range import RangeRegistry, RangeScanner
from sr_range_strategy import RangeStrategy, RangeSignal


# Module-level event loop for synchronous backtests (avoid asyncio.run() per bar)
_BT_LOOP: asyncio.AbstractEventLoop | None = None

def _run_coro_sync(obj: Any) -> Any:
    """If `obj` is a coroutine, execute it and return the result.

    Portfolio/month backtests are synchronous; range components are async only
    because the live bot uses async fetchers. In backtests we run coroutines
    on a single reusable event loop to keep things fast.

    NOTE: This must NOT be called from inside an already-running event loop.
    """
    global _BT_LOOP
    if not asyncio.iscoroutine(obj):
        return obj
    # If someone calls this from an async context, fail loudly (nested loop).
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None and running.is_running():
        raise RuntimeError('Cannot run coroutine sync inside a running event loop')
    if _BT_LOOP is None or _BT_LOOP.is_closed():
        _BT_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_BT_LOOP)
    return _BT_LOOP.run_until_complete(obj)

from .signals import TradeSignal


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return int(v.strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None:
        return default
    try:
        return float(v.strip())
    except Exception:
        return default


def _env_csv_set(name: str) -> set[str]:
    v = os.getenv(name, "").strip()
    if not v:
        return set()
    return {p.strip().upper() for p in v.replace(";", ",").split(",") if p.strip()}


@dataclass
class RangeWrapperConfig:
    # Scanner
    lookback_h: int = 120
    rescan_every_bars_5m: int = 12 * 3  # every 3 hours
    scan_tf: str = "60"
    mode: str = "box"

    # Scanner filters (defaults relaxed vs earlier versions)
    min_range_pct: float = 1.5
    max_range_pct: float = 20.0
    max_ema_spread_pct: float = 1.5
    min_touches: int = 2
    spike_mult: float = 3.0
    low_pct: float = 0.10
    high_pct: float = 0.90
    touch_tolerance_pct: float = 0.003
    touch_tolerance_atr_mult: float = 0.6

    # Strategy
    confirm_tf: str = "5"
    confirm_limit: int = 60
    atr_period: int = 14
    tp_mode: str = "mid"  # "mid" | "other"
    min_rr: float = 3.0
    entry_zone_frac: float = 0.30
    sweep_frac: float = 0.015
    reclaim_frac: float = 0.003
    wick_frac_min: float = 0.15
    require_prev_sweep: bool = True
    impulse_body_atr_max: float = 0.9
    adaptive_regime: bool = False
    regime_low_atr_pct: float = 0.35
    regime_high_atr_pct: float = 0.90
    impulse_body_atr_max_low: float = 0.60
    impulse_body_atr_max_high: float = 1.10
    min_rr_low: float = 2.2
    min_rr_high: float = 1.5


class RangeBacktestStrategy:
    """Adapter around existing RangeScanner/RangeStrategy.

    For backtests we call scanner.detect periodically and store ranges in a registry.
    Then RangeStrategy produces entry signals around the detected range boundaries.
    """

    def __init__(self, fetch_klines, cfg: RangeWrapperConfig | None = None):
        self.fetch_klines = fetch_klines
        self.cfg = cfg or RangeWrapperConfig()

        # Fast iteration knobs (optional)
        self.cfg.lookback_h = _env_int("RANGE_LOOKBACK_H", self.cfg.lookback_h)
        self.cfg.scan_tf = os.getenv("RANGE_SCAN_TF", self.cfg.scan_tf)
        self.cfg.mode = os.getenv("RANGE_MODE", self.cfg.mode)
        self.cfg.min_range_pct = _env_float("RANGE_MIN_RANGE_PCT", self.cfg.min_range_pct)
        self.cfg.max_range_pct = _env_float("RANGE_MAX_RANGE_PCT", self.cfg.max_range_pct)
        self.cfg.max_ema_spread_pct = _env_float("RANGE_MAX_EMA_SPREAD_PCT", self.cfg.max_ema_spread_pct)
        self.cfg.min_touches = _env_int("RANGE_MIN_TOUCHES", self.cfg.min_touches)
        self.cfg.spike_mult = _env_float("RANGE_SPIKE_MULT", self.cfg.spike_mult)
        self.cfg.low_pct = _env_float("RANGE_LOW_PCT", self.cfg.low_pct)
        self.cfg.high_pct = _env_float("RANGE_HIGH_PCT", self.cfg.high_pct)
        self.cfg.touch_tolerance_pct = _env_float("RANGE_TOUCH_TOL_PCT", self.cfg.touch_tolerance_pct)
        self.cfg.touch_tolerance_atr_mult = _env_float("RANGE_TOUCH_TOL_ATR_MULT", self.cfg.touch_tolerance_atr_mult)

        self.cfg.atr_period = _env_int("RANGE_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.min_rr = _env_float("RANGE_MIN_RR", self.cfg.min_rr)
        self.cfg.entry_zone_frac = _env_float("RANGE_ENTRY_ZONE_FRAC", self.cfg.entry_zone_frac)
        self.cfg.sweep_frac = _env_float("RANGE_SWEEP_FRAC", self.cfg.sweep_frac)
        self.cfg.reclaim_frac = _env_float("RANGE_RECLAIM_FRAC", self.cfg.reclaim_frac)
        self.cfg.wick_frac_min = _env_float("RANGE_WICK_FRAC_MIN", self.cfg.wick_frac_min)
        self.cfg.require_prev_sweep = _env_bool("RANGE_REQUIRE_PREV_SWEEP", self.cfg.require_prev_sweep)
        self.cfg.impulse_body_atr_max = _env_float("RANGE_IMPULSE_BODY_ATR_MAX", self.cfg.impulse_body_atr_max)
        self.cfg.adaptive_regime = _env_bool("RANGE_ADAPTIVE_REGIME", self.cfg.adaptive_regime)
        self.cfg.regime_low_atr_pct = _env_float("RANGE_REGIME_LOW_ATR_PCT", self.cfg.regime_low_atr_pct)
        self.cfg.regime_high_atr_pct = _env_float("RANGE_REGIME_HIGH_ATR_PCT", self.cfg.regime_high_atr_pct)
        self.cfg.impulse_body_atr_max_low = _env_float("RANGE_IMPULSE_BODY_ATR_MAX_LOW", self.cfg.impulse_body_atr_max_low)
        self.cfg.impulse_body_atr_max_high = _env_float("RANGE_IMPULSE_BODY_ATR_MAX_HIGH", self.cfg.impulse_body_atr_max_high)
        self.cfg.min_rr_low = _env_float("RANGE_MIN_RR_LOW", self.cfg.min_rr_low)
        self.cfg.min_rr_high = _env_float("RANGE_MIN_RR_HIGH", self.cfg.min_rr_high)

        self.registry = RangeRegistry()
        self.scanner = RangeScanner(
            fetch_klines=self.fetch_klines,
            registry=self.registry,
            interval_1h=self.cfg.scan_tf,
            lookback_h=self.cfg.lookback_h,
            # Keep detected ranges alive between rescans; 0 would expire immediately.
            rescan_ttl_sec=max(900, int(self.cfg.rescan_every_bars_5m * 300 * 2)),
            min_range_pct=self.cfg.min_range_pct,
            max_range_pct=self.cfg.max_range_pct,
            max_ema_spread_pct=self.cfg.max_ema_spread_pct,
            min_touches=self.cfg.min_touches,
            spike_mult=self.cfg.spike_mult,
            mode=self.cfg.mode,
            low_pct=self.cfg.low_pct,
            high_pct=self.cfg.high_pct,
            touch_tolerance_pct=self.cfg.touch_tolerance_pct,
            touch_tolerance_atr_mult=self.cfg.touch_tolerance_atr_mult,
        )
        self.strategy = RangeStrategy(
            fetch_klines=self.fetch_klines,
            registry=self.registry,
            confirm_tf=self.cfg.confirm_tf,
            confirm_limit=self.cfg.confirm_limit,
            atr_period=self.cfg.atr_period,
            tp_mode=self.cfg.tp_mode,
            min_rr=self.cfg.min_rr,
            entry_zone_frac=self.cfg.entry_zone_frac,
            sweep_frac=self.cfg.sweep_frac,
            reclaim_frac=self.cfg.reclaim_frac,
            wick_frac_min=self.cfg.wick_frac_min,
            require_prev_sweep=self.cfg.require_prev_sweep,
            impulse_body_atr_max=self.cfg.impulse_body_atr_max,
            adaptive_regime=self.cfg.adaptive_regime,
            regime_low_atr_pct=self.cfg.regime_low_atr_pct,
            regime_high_atr_pct=self.cfg.regime_high_atr_pct,
            impulse_body_atr_max_low=self.cfg.impulse_body_atr_max_low,
            impulse_body_atr_max_high=self.cfg.impulse_body_atr_max_high,
            min_rr_low=self.cfg.min_rr_low,
            min_rr_high=self.cfg.min_rr_high,
            confirm_cache_ttl_sec=0,
        )

        self._debug = os.getenv("RANGE_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
        self._allow = _env_csv_set("RANGE_SYMBOL_ALLOWLIST")
        self._deny = _env_csv_set("RANGE_SYMBOL_DENYLIST")
        self._entry_max_ema_spread_pct = _env_float("RANGE_ENTRY_MAX_EMA_SPREAD_PCT", 0.8)
        self._entry_max_range_pct = _env_float("RANGE_ENTRY_MAX_RANGE_PCT", 12.0)
        self._entry_min_range_pct = _env_float("RANGE_ENTRY_MIN_RANGE_PCT", 1.2)
        self._cooldown_bars = _env_int("RANGE_ENTRY_COOLDOWN_BARS", 24)  # 24*5m = 2h
        self._max_signals_per_day = _env_int("RANGE_MAX_SIGNALS_PER_DAY", 2)
        self._last_signal_i5 = -10**9
        self._day_key: Optional[int] = None
        self._day_signals = 0

        self._bar_count_5m = 0

    def signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        """Sync adapter for the backtest runner."""
        return _run_coro_sync(self.maybe_signal(store, ts_ms, last_price))

    async def maybe_signal(self, store, ts_ms: int, last_price: float) -> Optional[TradeSignal]:
        """Backtest-compatible entry point.

        The backtest runner invokes strategies as maybe_signal(store, ts_ms, last_price).
        Internally, range detection and trading logic are keyed by symbol.
        """
        symbol = getattr(store, "symbol", None) or getattr(store, "_symbol", None) or ""
        symbol_u = str(symbol).upper()
        if self._allow and symbol_u not in self._allow:
            return None
        if symbol_u in self._deny:
            return None

        # IMPORTANT: In backtests we already have the full candle series in-memory
        # (via the KlineStore). Using the public Bybit REST endpoint here will be
        # extremely slow and will usually hit rate-limits, leading to 0 trades.
        #
        # If the store exposes a fetch_klines(symbol, interval, limit) helper,
        # prefer it for both scanning and confirmation.
        if hasattr(store, "fetch_klines") and callable(getattr(store, "fetch_klines")):
            self.fetch_klines = store.fetch_klines
            self.scanner.fetch_klines = store.fetch_klines
            self.strategy.fetch_klines = store.fetch_klines

        self._bar_count_5m += 1

        # Periodic range detection
        if self._bar_count_5m == 1 or (self._bar_count_5m % self.cfg.rescan_every_bars_5m == 0):
            try:
                info = await self.scanner.detect(symbol)
                if info:
                    self.registry.set(info)
                    if self._debug:
                        print(
                            f"[RANGE] {symbol} detected: support={info.support:.6g} resistance={info.resistance:.6g} "
                            f"range%={info.range_pct:.2f} touches=({info.touches_support},{info.touches_resistance}) score={info.score:.1f}"
                        )
            except Exception:
                # In backtests we treat scanner failures as "no range" for this step.
                pass

        try:
            sig: RangeSignal | None = await self.strategy.maybe_signal(symbol, last_price)
        except Exception:
            return None

        if not sig:
            return None

        info = self.registry.get(symbol)
        if not info:
            return None
        # Extra anti-chop / regime filters
        if float(info.ema_spread_pct) > float(self._entry_max_ema_spread_pct):
            return None
        if float(info.range_pct) > float(self._entry_max_range_pct):
            return None
        if float(info.range_pct) < float(self._entry_min_range_pct):
            return None

        # Per-symbol cooldown after each signal
        i5 = int(getattr(store, "i5", -1))
        if i5 - int(self._last_signal_i5) < int(self._cooldown_bars):
            return None
        # Cap signals per day
        ts_sec = int(ts_ms // 1000 if ts_ms > 10_000_000_000 else ts_ms)
        day_key = int(ts_sec // 86400)
        if self._day_key != day_key:
            self._day_key = day_key
            self._day_signals = 0
        if self._day_signals >= int(self._max_signals_per_day):
            return None

        # Backtest engine expects side in {"long", "short"}.
        # RangeStrategy emits {"Buy", "Sell"}.
        side = "long" if sig.side == "Buy" else "short"

        entry = float(last_price)
        out = TradeSignal(
            strategy="range",
            symbol=symbol,
            side=side,
            entry=entry,
            sl=float(sig.sl),
            tp=float(sig.tp),
            reason=str(getattr(sig, "reason", "range")),
        )
        if out.validate():
            self._last_signal_i5 = i5
            self._day_signals += 1
            return out
        return None

# Backwards-compatible alias expected by backtest.run_month
RangeWrapper = RangeBacktestStrategy
