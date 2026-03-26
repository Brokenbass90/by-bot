"""Live wrapper for MicroScalperV1Strategy.

Mirrors the pattern of breakdown_live.py and sloped_channel_live.py.
Provides a simple signal(symbol, ts_ms, o, h, l, c, v) interface for the
live bot's entry flow.
"""
from __future__ import annotations

from typing import Optional, Dict

from strategies.micro_scalper_v1 import MicroScalperV1Strategy
from strategies.signals import TradeSignal


class _MicroScalperStore:
    """Minimal store adapter that MicroScalperV1Strategy expects."""

    def __init__(self, symbol: str, fetch_klines):
        self.symbol = symbol
        self._fetch = fetch_klines

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        return self._fetch(symbol, interval, limit)


class MicroScalperLiveEngine:
    """Creates per-symbol MicroScalperV1Strategy instances.

    Usage in live bot::

        engine = MicroScalperLiveEngine(fetch_klines_func)
        sig = engine.signal(symbol, ts_ms, o, h, l, c, v)
        if sig:
            # sig.side == 'long' or 'short', sig.sl, sig.tp, sig.entry are set
            ...

    Reads MSCALP_* env vars on first instantiation of each symbol strategy.
    Key settings:
        MSCALP_SYMBOL_ALLOWLIST       comma-separated symbols
        MSCALP_SYMBOL_DENYLIST        comma-separated symbols to skip
        MSCALP_ALLOW_LONGS=1
        MSCALP_ALLOW_SHORTS=1
        MSCALP_TREND_TF=15            trend timeframe (15m)
        MSCALP_TREND_EMA=20           EMA period for trend direction
        MSCALP_ENTRY_EMA=9            EMA period on 5m for pullback zone
        MSCALP_ATR_PERIOD=14          ATR period on 5m
        MSCALP_PULLBACK_ATR=0.35      max distance from close to EMA9
        MSCALP_MIN_BODY_ATR=0.22      minimum body (in ATR) for entry
        MSCALP_VOL_MULT=0.0           volume filter (0 = disabled)
        MSCALP_RR=1.5                 risk/reward ratio
        MSCALP_SL_BUFFER_ATR=0.15     extra ATR buffer beyond bar extreme
        MSCALP_SESSION_START_UTC=7    trading session start (UTC hour)
        MSCALP_SESSION_END_UTC=17     trading session end (UTC hour)
        MSCALP_COOLDOWN_BARS=3        min bars between signals
        MSCALP_MAX_SIGNALS_PER_DAY=5  daily signal limit
    """

    def __init__(self, fetch_klines):
        self._fetch = fetch_klines
        self._stores: Dict[str, _MicroScalperStore] = {}
        self._strategies: Dict[str, MicroScalperV1Strategy] = {}

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
        """Generate a trade signal for the given symbol and OHLCV bar.

        Args:
            symbol: Trading pair (e.g. 'BTCUSDT')
            ts_ms: Millisecond timestamp of the bar close
            o: Open price
            h: High price
            l: Low price
            c: Close price
            v: Volume (optional, default 0.0)

        Returns:
            TradeSignal if conditions are met, None otherwise.
        """
        if symbol not in self._stores:
            self._stores[symbol] = _MicroScalperStore(symbol, self._fetch)
        if symbol not in self._strategies:
            self._strategies[symbol] = MicroScalperV1Strategy()
        store = self._stores[symbol]
        strat = self._strategies[symbol]
        return strat.maybe_signal(store, ts_ms, o, h, l, c, v)
