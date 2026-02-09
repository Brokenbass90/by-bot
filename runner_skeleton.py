#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Runner skeleton for the refactor.

The current project historically grew around `smart_pump_reversal_bot.py`.
This skeleton documents the *target* architecture:

- runner (thin): wires everything and starts loops
- exchange client: REST/WebSocket + signing, no strategy logic
- trade manager: state machine + reconciliation with exchange
- strategies: pure signal generators, one per file
- data: candle store + indicators, shared utilities

This file is not a replacement yet (it is intentionally non-executable).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional


@dataclass
class Signal:
    symbol: str
    side: str  # "long" | "short"
    entry: float
    sl: float
    tp: float
    reason: str = ""


class Strategy(Protocol):
    name: str

    def on_tick(self, symbol: str, price: float, ts_ms: int) -> Optional[Signal]:
        """Return a signal or None. Pure logic: no REST calls, no side effects."""
        ...


@dataclass
class RunnerConfig:
    max_positions: int = 3
    risk_pct: float = 0.01
    cap_notional_usd: float = 50.0


# Target boundaries (to be implemented in the refactor):
# - BybitClient: REST/WS
# - DataFeed: candle building, caching
# - TradeManager: place orders, TPSL, sync & closed-pnl finalize
# - Strategy plugins: range/bounce/pump_fade/inplay/breakout
