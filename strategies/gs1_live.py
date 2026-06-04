"""Live wrapper for GridSmartV1Strategy (GS1).

Mirrors the pattern of att1_live.py / breakdown_live.py.
"""
from __future__ import annotations

from typing import Optional, Dict

from strategies.grid_smart_v1 import GridSmartV1Strategy
from strategies.live_kline_utils import fetch_closed_klines
from strategies.signals import TradeSignal


class _GS1Store:
    """Minimal store adapter that GridSmartV1Strategy expects."""

    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return fetch_closed_klines(self._fetch, symbol, interval, limit)


class GS1LiveEngine:
    """Per-symbol GridSmartV1Strategy instances for live trading.

    Usage in live bot::

        engine = GS1LiveEngine(fetch_klines_func)
        sig = engine.signal(symbol, ts_ms, o, h, l, c, v)
        if sig:
            ...

    Reads GS1_* env vars on first instantiation of each per-symbol strategy.
    """

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _GS1Store] = {}
        self._strategies: Dict[str, GridSmartV1Strategy] = {}
        self._no_signal_reasons: Dict[str, str] = {}
        self._errors: Dict[str, str] = {}

    def _get_store(self, symbol: str) -> _GS1Store:
        if symbol not in self._stores:
            self._stores[symbol] = _GS1Store(symbol, self._fetch)
        return self._stores[symbol]

    def _get_strategy(self, symbol: str) -> GridSmartV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = GridSmartV1Strategy()
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
        strat = self._get_strategy(symbol)
        try:
            sig = strat.maybe_signal(store, ts_ms, o, h, l, c, v)
        except Exception as exc:
            reason = f"engine_error:{type(exc).__name__}"
            self._errors[symbol] = reason
            self._no_signal_reasons[symbol] = reason
            return None
        self._errors.pop(symbol, None)
        if sig is None:
            self._no_signal_reasons[symbol] = getattr(strat, "last_no_signal_reason", "") or ""
        return sig

    def last_no_signal_reason(self, symbol: str) -> str:
        return self._no_signal_reasons.get(symbol, "")

    def last_error(self, symbol: str) -> str:
        return self._errors.get(symbol, "")

    def reset(self, symbol: str) -> None:
        """Reset state for a symbol (e.g. after a closed trade)."""
        self._stores.pop(symbol, None)
        self._strategies.pop(symbol, None)
        self._no_signal_reasons.pop(symbol, None)
        self._errors.pop(symbol, None)
