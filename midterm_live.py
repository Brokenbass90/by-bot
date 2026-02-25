#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from strategies.btc_eth_midterm_pullback import BTCETHMidtermPullbackStrategy
from backtest.bt_types import TradeSignal


class LiveKlineStore:
    """Minimal store adapter for BTC/ETH midterm strategy in live mode."""

    def __init__(self, symbol: str, fetch_klines: Callable[[str, str, int], Any]):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)


class MidtermLiveEngine:
    """Creates per-symbol BTCETHMidtermPullbackStrategy instances and returns TradeSignal."""

    def __init__(self, fetch_klines: Callable[[str, str, int], Any]):
        self._fetch = fetch_klines
        self._stores: Dict[str, LiveKlineStore] = {}
        self._strategies: Dict[str, BTCETHMidtermPullbackStrategy] = {}

    async def signal_async(self, symbol: str, price: float, ts_ms: int) -> Optional[TradeSignal]:
        if symbol not in self._stores:
            self._stores[symbol] = LiveKlineStore(symbol, self._fetch)
        if symbol not in self._strategies:
            self._strategies[symbol] = BTCETHMidtermPullbackStrategy()
        store = self._stores[symbol]
        strat = self._strategies[symbol]
        return strat.maybe_signal(store, ts_ms, price, price, price, price, 0.0)
