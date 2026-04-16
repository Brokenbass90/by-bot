"""Live wrapper for AltHorizontalBreakV1Strategy (HZBO1).

Provides a simple interface compatible with the live bot's entry flow.
Matches the pattern of att1_live.py / flat_resistance_fade_live.py.

HZBO1 = Horizontal Zone Breakout v1
Strategy: short horizontal support zones (flat clusters → support failure)
WF-22 result: AvgPF=1.647, PF>1.0: 13/22 (59%) — VIABLE at 0.40× risk

Complement to ASB1:
  ASB1  shorts SLOPED ascending trendlines (higher lows → momentum break)
  HZBO1 shorts HORIZONTAL support zones (flat clusters → support failure)
  Low correlation — fires on fundamentally different price structures.
"""
from __future__ import annotations

from typing import Optional, Dict

from strategies.alt_horizontal_break_v1 import AltHorizontalBreakV1Strategy
from strategies.signals import TradeSignal


class _HZBO1Store:
    """Minimal store adapter that AltHorizontalBreakV1Strategy expects."""

    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)


class HZBO1LiveEngine:
    """Per-symbol AltHorizontalBreakV1Strategy instances for live trading.

    Usage in live bot::

        engine = HZBO1LiveEngine(fetch_klines_func)
        sig = engine.signal(symbol, ts_ms, o, h, l, c, v)
        if sig:
            # sig.side, sig.sl, sig.tp, sig.entry, sig.reason are set
            ...
    """

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _HZBO1Store] = {}
        self._strategies: Dict[str, AltHorizontalBreakV1Strategy] = {}
        self._no_signal_reasons: Dict[str, str] = {}

    def _get_store(self, symbol: str) -> _HZBO1Store:
        if symbol not in self._stores:
            self._stores[symbol] = _HZBO1Store(symbol, self._fetch)
        return self._stores[symbol]

    def _get_strategy(self, symbol: str) -> AltHorizontalBreakV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = AltHorizontalBreakV1Strategy()
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
        except Exception:
            sig = None
        if sig is None:
            self._no_signal_reasons[symbol] = getattr(strat, "_last_no_signal_reason", "")
        return sig

    def last_no_signal_reason(self, symbol: str) -> str:
        return self._no_signal_reasons.get(symbol, "")

    def reset(self, symbol: str) -> None:
        """Reset state for a symbol (e.g. after a closed trade)."""
        self._stores.pop(symbol, None)
        self._strategies.pop(symbol, None)
        self._no_signal_reasons.pop(symbol, None)
