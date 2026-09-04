"""Broker-free live/shadow wrapper for the frozen ETS2S signal profile.

The wrapper is deliberately incapable of placing orders.  It only exposes the
same closed-candle boundary used by the monolith and applies the preregistered
post-signal geometry used by the ETS2S research profile.
"""
from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import Callable, Dict, Optional

from strategies.elder_triple_screen_v2 import ElderTripleScreenV2Strategy
from strategies.live_kline_utils import fetch_closed_klines
from strategies.signals import TradeSignal


ETS2S_LIVE_WRAPPER_ENABLED_BY_DEFAULT = False
ETS2S_STOP_DISTANCE_MULTIPLIER = 4.0
ETS2S_TIME_STOP_BARS_5M = 4032
ETS2S_STOP_TRANSFORM_ID = "scale_raw_stop_distance_x4_v1"
ETS2S_FROZEN_ENV = MappingProxyType(
    {
        "ETS2_TREND_TF": "1440",
        "ETS2_WAVE_TF": "240",
        "ETS2_ENTRY_TF": "60",
        "ETS2_RISK_TF": "240",
        "ETS2_ALLOW_LONGS": "0",
        "ETS2_ALLOW_SHORTS": "1",
        "ETS2_COOLDOWN_BARS_5M": "0",
        "ETS2_TIME_STOP_BARS_5M": str(ETS2S_TIME_STOP_BARS_5M),
    }
)
ETS2S_ENTRY_TYPE = "limit"
ETS2S_ENTRY_OFFSET = 0.002
ETS2S_ENTRY_WAIT_BARS = 6


def apply_ets2s_effective_geometry(signal: TradeSignal) -> TradeSignal:
    """Return the exact effective ETS2S geometry without mutating raw output."""

    if signal.side != "short":
        raise ValueError("ETS2S frozen profile is short-only")
    entry = float(signal.entry)
    raw_stop = float(signal.sl)
    if not raw_stop > entry:
        raise ValueError("ETS2S short stop must be above entry")
    effective_stop = entry + (raw_stop - entry) * ETS2S_STOP_DISTANCE_MULTIPLIER
    result = replace(
        signal,
        sl=effective_stop,
        time_stop_bars=ETS2S_TIME_STOP_BARS_5M,
        tps=list(signal.tps or []),
        tp_fracs=list(signal.tp_fracs or []),
    )
    if not result.validate():
        raise ValueError("ETS2S effective geometry is invalid")
    return result


class _ElderClosedStore:
    def __init__(self, symbol: str, fetch_klines: Callable):
        self.symbol = symbol
        self._fetch = fetch_klines
        self._observed_at_ms: Optional[int] = None
        self._last_closed_rows: Dict[str, list] = {}

    def set_observed_at_ms(self, value: Optional[int]) -> None:
        self._observed_at_ms = None if value is None else int(value)

    def fetch_klines(self, symbol: str, interval: str, limit: int) -> list:
        rows = fetch_closed_klines(
            self._fetch,
            symbol,
            interval,
            limit,
            now_ms=self._observed_at_ms,
        )
        self._last_closed_rows[str(interval)] = list(rows)
        return rows

    def last_closed_rows(self, interval: str) -> list:
        return list(self._last_closed_rows.get(str(interval), []))


class ElderShadowEngine:
    """Stateful, default-off ETS2S evaluator with no broker dependency."""

    def __init__(self, fetch_klines: Callable):
        self._fetch = fetch_klines
        self._stores: Dict[str, _ElderClosedStore] = {}
        self._strategies: Dict[str, ElderTripleScreenV2Strategy] = {}
        self._no_signal_reasons: Dict[str, str] = {}

    def _get_store(self, symbol: str) -> _ElderClosedStore:
        if symbol not in self._stores:
            self._stores[symbol] = _ElderClosedStore(symbol, self._fetch)
        return self._stores[symbol]

    def _get_strategy(self, symbol: str) -> ElderTripleScreenV2Strategy:
        if symbol not in self._strategies:
            self._strategies[symbol] = ElderTripleScreenV2Strategy()
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
        *,
        observed_at_ms: Optional[int] = None,
    ) -> Optional[TradeSignal]:
        store = self._get_store(symbol)
        store.set_observed_at_ms(observed_at_ms)
        strategy = self._get_strategy(symbol)
        signal = strategy.maybe_signal(store, ts_ms, o, h, l, c, v)
        if signal is None:
            self._no_signal_reasons[symbol] = getattr(
                strategy, "last_no_signal_reason", ""
            )
            return None
        return apply_ets2s_effective_geometry(signal)

    def last_no_signal_reason(self, symbol: str) -> str:
        return self._no_signal_reasons.get(symbol, "")

    def last_closed_rows(self, symbol: str, interval: str) -> list:
        store = self._stores.get(symbol)
        return store.last_closed_rows(interval) if store is not None else []

    def reset(self, symbol: str) -> None:
        self._stores.pop(symbol, None)
        self._strategies.pop(symbol, None)
        self._no_signal_reasons.pop(symbol, None)
