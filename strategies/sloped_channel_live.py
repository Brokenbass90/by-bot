"""Live wrapper for AltSlopedChannelV1Strategy.

Provides a simple interface compatible with the live bot's
`try_sloped_entry_async()` flow.
"""
from __future__ import annotations

import os
from typing import Optional, Any, Dict, List

from strategies.alt_sloped_channel_v1 import (
    AltSlopedChannelV1Strategy,
    AltSlopedChannelV1Config,
)
from strategies.signals import TradeSignal


class _SlopedStore:
    """Minimal store adapter that AltSlopedChannelV1Strategy expects."""

    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)


class SlopedChannelLiveEngine:
    """Creates per-symbol AltSlopedChannelV1Strategy instances.

    Usage in live bot::

        engine = SlopedChannelLiveEngine(fetch_klines_func)
        sig = engine.signal(symbol, ts_ms, o, h, l, c, v)
        if sig:
            # sig.side, sig.sl, sig.tp, sig.entry are set
            ...
    """

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _SlopedStore] = {}
        self._strategies: Dict[str, AltSlopedChannelV1Strategy] = {}

    def signal(
        self,
        symbol: str,
        ts_ms: int,
        o: float,
        h: float,
        l: float,
        c: float,
        v: float = 0.0,
    ) -> Optional[TradeSignal]:
        if symbol not in self._stores:
            self._stores[symbol] = _SlopedStore(symbol, self._fetch)
        if symbol not in self._strategies:
            self._strategies[symbol] = AltSlopedChannelV1Strategy()
        store = self._stores[symbol]
        strat = self._strategies[symbol]
        return strat.maybe_signal(store, ts_ms, o, h, l, c, v)
