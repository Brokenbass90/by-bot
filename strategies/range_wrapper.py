#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import os
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


@dataclass
class RangeWrapperConfig:
    # Scanner
    lookback_h: int = 200
    rescan_every_bars_5m: int = 12 * 6  # every 6 hours

    # Scanner filters (defaults relaxed vs earlier versions)
    min_range_pct: float = 1.5
    max_range_pct: float = 20.0
    max_ema_spread_pct: float = 1.5
    min_touches: int = 2
    spike_mult: float = 3.0

    # Strategy
    confirm_tf: str = "5"
    confirm_limit: int = 24
    atr_period: int = 14
    tp_mode: str = "mid"  # "mid" | "other"
    min_rr: float = 1.2
    entry_zone_frac: float = 0.20
    sweep_frac: float = 0.015
    reclaim_frac: float = 0.006
    wick_frac_min: float = 0.25


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
        self.cfg.min_range_pct = _env_float("RANGE_MIN_RANGE_PCT", self.cfg.min_range_pct)
        self.cfg.max_range_pct = _env_float("RANGE_MAX_RANGE_PCT", self.cfg.max_range_pct)
        self.cfg.max_ema_spread_pct = _env_float("RANGE_MAX_EMA_SPREAD_PCT", self.cfg.max_ema_spread_pct)
        self.cfg.min_touches = _env_int("RANGE_MIN_TOUCHES", self.cfg.min_touches)
        self.cfg.spike_mult = _env_float("RANGE_SPIKE_MULT", self.cfg.spike_mult)

        self.cfg.atr_period = _env_int("RANGE_ATR_PERIOD", self.cfg.atr_period)
        self.cfg.min_rr = _env_float("RANGE_MIN_RR", self.cfg.min_rr)
        self.cfg.entry_zone_frac = _env_float("RANGE_ENTRY_ZONE_FRAC", self.cfg.entry_zone_frac)
        self.cfg.sweep_frac = _env_float("RANGE_SWEEP_FRAC", self.cfg.sweep_frac)
        self.cfg.reclaim_frac = _env_float("RANGE_RECLAIM_FRAC", self.cfg.reclaim_frac)
        self.cfg.wick_frac_min = _env_float("RANGE_WICK_FRAC_MIN", self.cfg.wick_frac_min)

        self.registry = RangeRegistry()
        self.scanner = RangeScanner(
            fetch_klines=self.fetch_klines,
            registry=self.registry,
            interval_1h="60",
            lookback_h=self.cfg.lookback_h,
            rescan_ttl_sec=0,
            min_range_pct=self.cfg.min_range_pct,
            max_range_pct=self.cfg.max_range_pct,
            max_ema_spread_pct=self.cfg.max_ema_spread_pct,
            min_touches=self.cfg.min_touches,
            spike_mult=self.cfg.spike_mult,
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
            confirm_cache_ttl_sec=0,
        )

        self._debug = os.getenv("RANGE_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}

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
                            f"[RANGE] {symbol} detected: low={info.low:.6g} high={info.high:.6g} "
                            f"width%={info.width_pct:.2f} touches={info.touches} score={info.score:.1f}"
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
            reason=f"range {sig.edge} rr={sig.rr:.2f}",
        )
        return out if out.validate() else None

# Backwards-compatible alias expected by backtest.run_month
RangeWrapper = RangeBacktestStrategy
