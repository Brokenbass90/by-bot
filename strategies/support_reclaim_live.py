"""Live wrapper for AltSupportReclaimV1Strategy.

Provides a simple interface compatible with the live bot's
`try_flat_entry_async()` flow.

Mirrors the pattern of flat_resistance_fade_live.py.
"""
from __future__ import annotations

from typing import Optional, Dict

from strategies.alt_support_reclaim_v1 import AltSupportReclaimV1Strategy
from strategies.signals import TradeSignal


class _FlatStore:
    """Minimal store adapter that AltSupportReclaimV1Strategy expects."""

    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)


class SupportReclaimLiveEngine:
    """Creates per-symbol AltSupportReclaimV1Strategy instances.

    Usage in live bot::

        engine = SupportReclaimLiveEngine(fetch_klines_func)
        sig = engine.signal(symbol, ts_ms, o, h, l, c, v)
        if sig:
            # sig.side, sig.sl, sig.tp, sig.entry are set
            ...

    Reads ASR1_* env vars on first instantiation of each symbol strategy.
    Key settings:
        ASR1_SYMBOL_ALLOWLIST   comma-separated symbols (e.g. LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT)
        ASR1_SIGNAL_TF          signal timeframe (default "60")
    """

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _FlatStore] = {}
        self._strategies: Dict[str, AltSupportReclaimV1Strategy] = {}

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
            self._strategies[symbol] = AltSupportReclaimV1Strategy()
        store = self._stores[symbol]
        strat = self._strategies[symbol]
        return strat.maybe_signal(store, ts_ms, o, h, l, c, v)
