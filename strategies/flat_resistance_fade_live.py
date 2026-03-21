"""Live wrapper for AltResistanceFadeV1Strategy.

Provides a simple interface compatible with the live bot's
`try_flat_entry_async()` flow.

Mirrors the pattern of sloped_channel_live.py.
"""
from __future__ import annotations

from typing import Optional, Dict

from strategies.alt_resistance_fade_v1 import AltResistanceFadeV1Strategy
from strategies.signals import TradeSignal


class _FlatStore:
    """Minimal store adapter that AltResistanceFadeV1Strategy expects."""

    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)


class FlatResistanceFadeLiveEngine:
    """Creates per-symbol AltResistanceFadeV1Strategy instances.

    Usage in live bot::

        engine = FlatResistanceFadeLiveEngine(fetch_klines_func)
        sig = engine.signal(symbol, ts_ms, o, h, l, c, v)
        if sig:
            # sig.side, sig.sl, sig.tp, sig.entry are set
            ...

    Reads ARF1_* env vars on first instantiation of each symbol strategy.
    Key settings:
        ARF1_SYMBOL_ALLOWLIST   comma-separated symbols (e.g. LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT)
        ARF1_SIGNAL_TF          signal timeframe (default "60")
    """

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _FlatStore] = {}
        self._strategies: Dict[str, AltResistanceFadeV1Strategy] = {}

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
            self._stores[symbol] = _FlatStore(symbol, self._fetch)
        if symbol not in self._strategies:
            self._strategies[symbol] = AltResistanceFadeV1Strategy()
        store = self._stores[symbol]
        strat = self._strategies[symbol]
        return strat.maybe_signal(store, ts_ms, o, h, l, c, v)
