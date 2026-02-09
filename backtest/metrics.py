#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Trade:
    strategy: str
    symbol: str
    side: str  # "long" | "short"
    entry_ts: int
    exit_ts: int
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct_equity: float
    fees: float
    reason: str
    outcome: str  # "tp" | "sl" | "time" | "manual"


@dataclass
class Summary:
    strategy: str
    net_pnl: float
    trades: int
    wins: int
    losses: int
    winrate: float
    profit_factor: float
    avg_pnl: float
    max_drawdown: float

    # Backwards-compatible alias used by some scripts
    @property
    def max_drawdown_pct(self) -> float:
        # In this backtest, max_drawdown is stored as a percentage (0..100).
        return float(self.max_drawdown)

    # Backwards-compatible alias used by some scripts
    @property
    def winrate_pct(self) -> float:
        return float(self.winrate) * 100.0


def max_drawdown(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    mdd = 0.0
    for x in equity_curve:
        if x > peak:
            peak = x
        # Percentage drawdown from the current peak.
        if peak > 0:
            dd_pct = (peak - x) / peak * 100.0
            if dd_pct > mdd:
                mdd = dd_pct
    return mdd


def summarize(strategy: str, trades: List[Trade], equity_curve: List[float]) -> Summary:
    net = sum(t.pnl for t in trades)
    n = len(trades)
    wins = sum(1 for t in trades if t.pnl > 0)
    losses = sum(1 for t in trades if t.pnl < 0)
    winrate = (wins / n) if n else 0.0

    gross_win = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = -sum(t.pnl for t in trades if t.pnl < 0)
    if gross_loss <= 0:
        pf = float('inf') if gross_win > 0 else 0.0
    else:
        pf = gross_win / gross_loss

    avg = (net / n) if n else 0.0
    mdd = max_drawdown(equity_curve)

    return Summary(
        strategy=strategy,
        net_pnl=net,
        trades=n,
        wins=wins,
        losses=losses,
        winrate=winrate,
        profit_factor=pf,
        avg_pnl=avg,
        max_drawdown=mdd,
    )


def to_row_dict(s: Summary) -> Dict[str, object]:
    return {
        'strategy': s.strategy,
        'net_pnl': round(s.net_pnl, 4),
        'trades': s.trades,
        'wins': s.wins,
        'losses': s.losses,
        'winrate': round(s.winrate, 4),
        'profit_factor': (round(s.profit_factor, 4) if math.isfinite(s.profit_factor) else 'inf'),
        'avg_pnl': round(s.avg_pnl, 6),
        'max_drawdown': round(s.max_drawdown, 4),
    }


# ---------------------------------------------------------------------------
# Backwards-compatible API
#
# Some entrypoints import `PerformanceSummary` and `summarize_trades`.
# The core implementation here uses `Summary` and `summarize`.
# Provide thin wrappers so older scripts keep working.

PerformanceSummary = Summary


def summarize_trades(trades: List[Trade], equity_curve: Optional[List[float]] = None, strategy: str = "") -> Summary:
    """Summarize a list of trades (optionally with an equity curve).

    This wrapper exists for compatibility with `backtest.run_month`.
    """
    eq = equity_curve or [0.0]
    return summarize(strategy=strategy, trades=trades, equity_curve=eq)
