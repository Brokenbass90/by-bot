"""Live wrapper for AltTrendlineTouchV2Strategy (ATT1 v2).

Drop-in sibling of att1_live.py. Same interface as ATT1LiveEngine, so the
live bot can switch ATT1 to v2 by importing ATT1V2LiveEngine instead of
ATT1LiveEngine. NOT wired by default — meant for backtest validation first
(see AUDIT_AND_FIXES_2026_06_08.md, раздел ATT1).

v2 adds: weighted linear regression with decay, R^2 line-quality threshold,
setup quality scoring, optional volume confirmation, separate RSI gates.

Env: reads ATT2_* variables (with ATT1_* fallback if ATT2_USE_ATT1_ENV=1).
"""
from __future__ import annotations

from typing import Optional, Dict

from strategies.alt_trendline_touch_v2 import AltTrendlineTouchV2Strategy
from strategies.live_kline_utils import fetch_closed_klines
from strategies.signals import TradeSignal


class _ATT1V2Store:
    """Minimal store adapter that AltTrendlineTouchV2Strategy expects."""

    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return fetch_closed_klines(self._fetch, symbol, interval, limit)


class ATT1V2LiveEngine:
    """Per-symbol AltTrendlineTouchV2Strategy instances for live trading.

    Identical surface to ATT1LiveEngine:
        engine = ATT1V2LiveEngine(fetch_klines_func)
        sig = engine.signal(symbol, ts_ms, o, h, l, c, v)
        reason = engine.last_no_signal_reason(symbol)
        engine.reset(symbol)
    """

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _ATT1V2Store] = {}
        self._strategies: Dict[str, AltTrendlineTouchV2Strategy] = {}
        self._no_signal_reasons: Dict[str, str] = {}

    def _get_store(self, symbol: str) -> _ATT1V2Store:
        if symbol not in self._stores:
            self._stores[symbol] = _ATT1V2Store(symbol, self._fetch)
        return self._stores[symbol]

    def _get_strategy(self, symbol: str) -> AltTrendlineTouchV2Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = AltTrendlineTouchV2Strategy()
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
