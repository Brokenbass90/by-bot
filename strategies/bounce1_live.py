"""Live wrapper for AltSupportBounceV1Strategy (Bounce1 / ASB1-long).

Provides a simple interface compatible with the live bot's entry flow.
Matches the pattern of asb1_live.py / hzbo1_live.py.

Bounce1 = Alt Support Bounce v1
Strategy: LONG at key 1h support levels during uptrend/flat regime.
WF-22 result: AvgPF=1.421 — VIABLE at 0.40× risk (active in bull/chop only)

Regime gate:
  - active in BULL_TREND and BULL_CHOP (allocator gives 1.1× and 0.9× mult)
  - disabled in BEAR_CHOP and BEAR_TREND (allocator gives 0.0×)
  - strategy also has internal 4h EMA check: requires EMA20 >= EMA50 or flat
  So double-gated: allocator regime + internal regime check.

Env config:
  ENABLE_BOUNCE1_TRADING=1
  BOUNCE1_RISK_MULT=0.40
  BOUNCE1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT
  BOUNCE1_MAX_OPEN_TRADES=1
  ASB1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT  (reused by strategy)
"""
from __future__ import annotations

from typing import Dict, Optional

from strategies.alt_support_bounce_v1 import AltSupportBounceV1Strategy
from strategies.signals import TradeSignal


class _Bounce1Store:
    """Minimal store adapter that AltSupportBounceV1Strategy expects."""

    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)


class Bounce1LiveEngine:
    """Per-symbol AltSupportBounceV1Strategy instances for live trading.

    Usage in live bot::

        engine = Bounce1LiveEngine(fetch_klines_func)
        sig = engine.signal(symbol, ts_ms, o, h, l, c, v)
        if sig:
            # sig.side == "long" always (long-only strategy)
            # sig.sl, sig.tp, sig.entry, sig.reason are set
            ...
    """

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _Bounce1Store] = {}
        self._strategies: Dict[str, AltSupportBounceV1Strategy] = {}
        self._no_signal_reasons: Dict[str, str] = {}

    def _get_store(self, symbol: str) -> _Bounce1Store:
        if symbol not in self._stores:
            self._stores[symbol] = _Bounce1Store(symbol, self._fetch)
        return self._stores[symbol]

    def _get_strategy(self, symbol: str) -> AltSupportBounceV1Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = AltSupportBounceV1Strategy()
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
            self._no_signal_reasons[symbol] = getattr(strat, "last_no_signal_reason", "")
        return sig

    def last_no_signal_reason(self, symbol: str) -> str:
        return self._no_signal_reasons.get(symbol, "")

    def reset(self, symbol: str) -> None:
        """Reset state for a symbol (e.g. after a closed trade)."""
        self._stores.pop(symbol, None)
        self._strategies.pop(symbol, None)
        self._no_signal_reasons.pop(symbol, None)
