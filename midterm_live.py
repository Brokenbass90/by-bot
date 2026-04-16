#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from backtest.bt_types import TradeSignal


class LiveKlineStore:
    """Minimal store adapter for midterm strategies in live mode."""

    def __init__(self, symbol: str, fetch_klines: Callable[[str, str, int], Any]):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)


# Strategy version selection via env:
#   MTPB_VERSION=3  → uses btc_eth_midterm_v3.BTCETHMidtermV3Strategy (recommended)
#   MTPB_VERSION=1  → uses btc_eth_midterm_pullback.BTCETHMidtermPullbackStrategy (legacy)
# Default: v3 (if available), fallback to v1.

def _make_strategy():
    version = os.getenv("MTPB_VERSION", "3").strip()
    if version == "3":
        try:
            from strategies.btc_eth_midterm_v3 import BTCETHMidtermV3Strategy
            return BTCETHMidtermV3Strategy()
        except ImportError:
            pass
    if version in ("2",):
        try:
            from strategies.btc_eth_midterm_pullback_v2 import BTCETHMidtermPullbackV2Strategy
            return BTCETHMidtermPullbackV2Strategy()
        except ImportError:
            pass
    # Fallback: v1
    from strategies.btc_eth_midterm_pullback import BTCETHMidtermPullbackStrategy
    return BTCETHMidtermPullbackStrategy()


class MidtermLiveEngine:
    """
    Creates per-symbol midterm strategy instances and returns TradeSignal.

    Strategy version is selected by MTPB_VERSION env var:
      3 = btc_eth_midterm_v3  (default, recommended — MACD filter + RSI + fresh touch)
      1 = btc_eth_midterm_pullback  (legacy v1)
      2 = btc_eth_midterm_pullback_v2  (channel version, experimental)
    """

    def __init__(self, fetch_klines: Callable[[str, str, int], Any]):
        self._fetch = fetch_klines
        self._stores: Dict[str, LiveKlineStore] = {}
        self._strategies: Dict[str, Any] = {}
        self._version = os.getenv("MTPB_VERSION", "3").strip()

    async def signal_async(self, symbol: str, price: float, ts_ms: int) -> Optional[TradeSignal]:
        if symbol not in self._stores:
            self._stores[symbol] = LiveKlineStore(symbol, self._fetch)

        if symbol not in self._strategies:
            self._strategies[symbol] = _make_strategy()

        store = self._stores[symbol]
        strat = self._strategies[symbol]
        return strat.maybe_signal(store, ts_ms, price, price, price, price, 0.0)
