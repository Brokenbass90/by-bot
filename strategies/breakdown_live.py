"""Live wrapper for AltInplayBreakdownV1Strategy.

Mirrors the pattern of flat_resistance_fade_live.py / sloped_channel_live.py.
Provides a simple signal(symbol, ts_ms, last_price) interface for the
live bot's try_breakdown_entry_async() flow.
"""
from __future__ import annotations

from typing import Optional, Dict, Any

from strategies.alt_inplay_breakdown_v1 import AltInplayBreakdownV1Strategy
from strategies.signals import TradeSignal


class _BreakdownStore:
    """Minimal store adapter that AltInplayBreakdownV1Strategy expects."""

    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)


class BreakdownLiveEngine:
    """Creates per-symbol AltInplayBreakdownV1Strategy instances.

    Usage in live bot::

        engine = BreakdownLiveEngine(fetch_klines_func)
        sig = engine.signal(symbol, ts_ms, last_price)
        if sig:
            # sig.side == 'short', sig.sl, sig.tp, sig.entry are set
            ...

    Reads BREAKDOWN_* env vars on first instantiation of each symbol strategy.
    Key settings:
        BREAKDOWN_SYMBOL_ALLOWLIST   comma-separated symbols (e.g. BTCUSDT,ETHUSDT,SOLUSDT)
        BREAKDOWN_ALLOW_SHORTS=1
        BREAKDOWN_ALLOW_LONGS=0
        BREAKDOWN_REGIME_MODE=off    (or ema)
        BREAKDOWN_LOOKBACK_H=48
        BREAKDOWN_RR=2.0
        BREAKDOWN_SL_ATR=1.8
        BREAKDOWN_MAX_DIST_ATR=2.0
    """

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _BreakdownStore] = {}
        self._strategies: Dict[str, AltInplayBreakdownV1Strategy] = {}

    def signal(
        self,
        symbol: str,
        ts_ms: int,
        last_price: float,
    ) -> Optional[TradeSignal]:
        if symbol not in self._stores:
            self._stores[symbol] = _BreakdownStore(symbol, self._fetch)
        if symbol not in self._strategies:
            self._strategies[symbol] = AltInplayBreakdownV1Strategy()
        store = self._stores[symbol]
        strat = self._strategies[symbol]
        return strat.signal(store, ts_ms, last_price)
