"""Default-off live-shaped wrapper for ``sloped_break_retest_v1`` (SBR1).

This module adds the missing production-shaped signal boundary without granting
order or money authority.  It deliberately mirrors the ATT1 wrapper interface,
keeps one stateful strategy instance per symbol, consumes closed candles only,
and never converts exceptions into ordinary no-signal decisions.
"""
from __future__ import annotations

from typing import Dict, Optional

from strategies.live_kline_utils import fetch_closed_klines
from strategies.signals import TradeSignal
from strategies.sloped_break_retest_v1 import SlopedBreakRetestV1Strategy


SBR1_LIVE_WRAPPER_ENABLED_BY_DEFAULT = False


class _SBR1Store:
    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines
        self._last_closed_rows: Dict[str, list] = {}

    def fetch_klines(self, symbol: str, interval: str, limit: int) -> list:
        rows = fetch_closed_klines(self._fetch, symbol, interval, limit)
        self._last_closed_rows[str(interval)] = list(rows)
        return rows

    def last_closed_rows(self, interval: str = "60") -> list:
        return list(self._last_closed_rows.get(str(interval), []))


class SBR1LiveEngine:
    """Stateful per-symbol SBR1 signal wrapper; no order path is imported."""

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _SBR1Store] = {}
        self._strategies: Dict[str, SlopedBreakRetestV1Strategy] = {}

    def _get_store(self, symbol: str) -> _SBR1Store:
        if symbol not in self._stores:
            self._stores[symbol] = _SBR1Store(symbol, self._fetch)
        return self._stores[symbol]

    def _get_strategy(self, symbol: str) -> SlopedBreakRetestV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = SlopedBreakRetestV1Strategy()
        return self._strategies[symbol]

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
        store = self._get_store(symbol)
        strategy = self._get_strategy(symbol)
        return strategy.maybe_signal(store, ts_ms, o, h, l, c, v)

    def effective_config(self, symbol: str):
        """Expose the actual parsed config object used for this symbol."""

        return self._get_strategy(symbol).cfg

    def last_closed_rows(self, symbol: str, interval: str = "60") -> list:
        store = self._stores.get(symbol)
        return store.last_closed_rows(interval) if store is not None else []

    def reset(self, symbol: str) -> None:
        self._stores.pop(symbol, None)
        self._strategies.pop(symbol, None)


__all__ = [
    "SBR1_LIVE_WRAPPER_ENABLED_BY_DEFAULT",
    "SBR1LiveEngine",
]
