"""Live wrapper for PumpFadeSmartV1Strategy (PFS1).

Mirrors the pattern of att1_live.py / breakdown_live.py / flat_resistance_fade_live.py.
Provides a simple interface compatible with the live bot's entry flow.
"""
from __future__ import annotations

from typing import Optional, Dict

from strategies.pump_fade_smart_v1 import PumpFadeSmartV1Strategy
from strategies.live_kline_utils import fetch_closed_klines
from strategies.signals import TradeSignal


class _PFS1Store:
    """Minimal store adapter that PumpFadeSmartV1Strategy expects."""

    def __init__(self, symbol: str, fetch_klines, fetch_funding=None):
        self.symbol = symbol
        self._fetch = fetch_klines
        self._fetch_funding = fetch_funding

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return fetch_closed_klines(self._fetch, symbol, interval, limit)

    def fetch_funding_rate(self, symbol: str) -> float:
        if not self._fetch_funding:
            return 0.0
        try:
            return float(self._fetch_funding(symbol))
        except Exception:
            return 0.0


class PFS1LiveEngine:
    """Per-symbol PumpFadeSmartV1Strategy instances for live trading.

    Usage in live bot::

        engine = PFS1LiveEngine(fetch_klines_func, fetch_funding_func)
        sig = engine.signal(symbol, ts_ms, o, h, l, c, v)
        if sig:
            # sig.side, sig.sl, sig.tp, sig.entry, sig.reason are set
            ...

    Reads PFS1_* env vars on first instantiation of each per-symbol strategy.
    """

    def __init__(self, fetch_klines, fetch_funding=None):
        self._fetch = fetch_klines
        self._fetch_funding = fetch_funding
        self._stores: Dict[str, _PFS1Store] = {}
        self._strategies: Dict[str, PumpFadeSmartV1Strategy] = {}
        self._no_signal_reasons: Dict[str, str] = {}
        self._errors: Dict[str, str] = {}

    def _get_store(self, symbol: str) -> _PFS1Store:
        if symbol not in self._stores:
            self._stores[symbol] = _PFS1Store(symbol, self._fetch, self._fetch_funding)
        return self._stores[symbol]

    def _get_strategy(self, symbol: str) -> PumpFadeSmartV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = PumpFadeSmartV1Strategy()
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
