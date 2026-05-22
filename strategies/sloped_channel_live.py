"""Live wrapper for AltSlopedChannelV1Strategy.

Provides a simple interface compatible with the live bot's
`try_sloped_entry_async()` flow.
"""
from __future__ import annotations

import os
from typing import Optional, Any, Dict, List, Tuple

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
        self._no_signal_reasons: Dict[str, str] = {}

    @staticmethod
    def _row_start_ms(row: List[Any]) -> int:
        try:
            raw = int(float(row[0]))
        except Exception:
            return 0
        return raw if raw > 10**11 else raw * 1000

    @staticmethod
    def _row_ohlcv(row: List[Any]) -> Optional[Tuple[float, float, float, float, float]]:
        try:
            vol = float(row[5]) if len(row) > 5 and row[5] not in (None, "", "nan") else 0.0
            return float(row[1]), float(row[2]), float(row[3]), float(row[4]), vol
        except Exception:
            return None

    def _latest_closed_5m_ohlcv(
        self,
        store: _SlopedStore,
        symbol: str,
        ts_ms: int,
    ) -> Optional[Tuple[float, float, float, float, float]]:
        rows = store.fetch_klines(symbol, "5", 8) or []
        if not rows:
            return None
        for row in reversed(rows):
            start_ms = self._row_start_ms(row)
            if start_ms > 0 and ts_ms - start_ms >= 5 * 60 * 1000:
                parsed = self._row_ohlcv(row)
                if parsed is not None:
                    return parsed
        if len(rows) >= 2:
            return self._row_ohlcv(rows[-2])
        return self._row_ohlcv(rows[-1])

    def has_pending(self, symbol: str) -> bool:
        strat = self._strategies.get(str(symbol).upper()) or self._strategies.get(str(symbol))
        return bool(getattr(strat, "_pending", None)) if strat is not None else False

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
        if (
            getattr(strat, "_pending", None) is not None
            and int(getattr(getattr(strat, "cfg", None), "confirm_5m_bars", 0) or 0) > 0
            and (float(o or 0) <= 0 or float(h or 0) <= 0 or float(l or 0) <= 0 or float(c or 0) <= 0)
        ):
            closed_5m = self._latest_closed_5m_ohlcv(store, symbol, int(ts_ms))
            if closed_5m is not None:
                o, h, l, c, v = closed_5m
        sig = strat.maybe_signal(store, ts_ms, o, h, l, c, v)
        self._no_signal_reasons[str(symbol).upper()] = str(getattr(strat, "last_no_signal_reason", "") or "")
        return sig

    def last_no_signal_reason(self, symbol: str) -> str:
        return str(self._no_signal_reasons.get(str(symbol).upper(), "") or "")
