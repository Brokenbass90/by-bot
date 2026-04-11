"""Live wrapper for AltSlopedMomentumV1Strategy (ASM1).

Provides a simple interface compatible with the live bot's entry flow.
Matches the pattern of sloped_channel_live.py and flat_resistance_fade_live.py.
"""
from __future__ import annotations

import os
from typing import Optional, Dict

from strategies.alt_sloped_momentum_v1 import AltSlopedMomentumV1Strategy
from strategies.signals import TradeSignal


class _ASM1Store:
    """Minimal store adapter that AltSlopedMomentumV1Strategy expects."""

    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)


class ASM1LiveEngine:
    """Per-symbol AltSlopedMomentumV1Strategy instances for live trading.

    Usage in live bot::

        engine = ASM1LiveEngine(fetch_klines_func)
        sig = engine.signal(symbol, ts_ms, o, h, l, c, v)
        if sig:
            # sig.side, sig.sl, sig.tp, sig.entry, sig.reason are set
            ...

    Notes:
        - ASM1 is a sloped channel BREAKOUT strategy (both long + short).
        - Best config: VOL_MULT=2.0, BODY_FRAC=0.35, EXT_ATR=0.15.
        - PF=1.531, DD=4.6% (100-run sweep, 360-day window ending 2026-04-01).
    """

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _ASM1Store] = {}
        self._strategies: Dict[str, AltSlopedMomentumV1Strategy] = {}
        self._no_signal_reasons: Dict[str, str] = {}

    def _get_store(self, symbol: str) -> _ASM1Store:
        if symbol not in self._stores:
            self._stores[symbol] = _ASM1Store(symbol, self._fetch)
        return self._stores[symbol]

    def _get_strategy(self, symbol: str) -> AltSlopedMomentumV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = AltSlopedMomentumV1Strategy()
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
