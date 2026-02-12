#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Any, List

from strategies.inplay_wrapper import InPlayWrapper
from backtest.bt_types import TradeSignal


@dataclass
class LiteCandle:
    h: float
    l: float


class LiveKlineStore:
    """Minimal store adapter for InPlayWrapper in live mode."""

    def __init__(self, symbol: str, fetch_klines: Callable[[str, str, int], Any]):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)

    def _slice(self, interval: str, limit: int) -> List[LiteCandle]:
        rows = self._fetch(self.symbol, interval, int(limit)) or []
        out: List[LiteCandle] = []
        for r in rows:
            try:
                h = float(r[2])
                l = float(r[3])
            except Exception:
                continue
            out.append(LiteCandle(h=h, l=l))
        return out


class InPlayLiveEngine:
    """Creates per-symbol InPlayWrapper instances and returns TradeSignal."""

    def __init__(self, fetch_klines: Callable[[str, str, int], Any]):
        self._fetch = fetch_klines
        self._stores: Dict[str, LiveKlineStore] = {}
        self._wrappers: Dict[str, InPlayWrapper] = {}

    def signal(self, symbol: str, price: float, ts_ms: int) -> Optional[TradeSignal]:
        if symbol not in self._stores:
            self._stores[symbol] = LiveKlineStore(symbol, self._fetch)
        if symbol not in self._wrappers:
            self._wrappers[symbol] = InPlayWrapper()
        store = self._stores[symbol]
        wrapper = self._wrappers[symbol]
        return wrapper.signal(store, ts_ms, price)

    async def signal_async(self, symbol: str, price: float, ts_ms: int) -> Optional[TradeSignal]:
        """Async entry point to avoid coroutine warnings in async contexts."""
        if symbol not in self._stores:
            self._stores[symbol] = LiveKlineStore(symbol, self._fetch)
        if symbol not in self._wrappers:
            self._wrappers[symbol] = InPlayWrapper()
        store = self._stores[symbol]
        wrapper = self._wrappers[symbol]
        return await wrapper.maybe_signal(store, ts_ms, price)
