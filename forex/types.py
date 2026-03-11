from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Candle:
    ts: int  # epoch seconds
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


@dataclass
class Signal:
    side: str  # long|short
    entry: float
    sl: float
    tp: float
    reason: str = ""


@dataclass
class Trade:
    side: str
    entry_ts: int
    exit_ts: int
    entry_price: float
    exit_price: float
    pnl_pips: float
    net_pips: float
    reason: str
    risk_pips: float = 0.0
    r_multiple: float = 0.0


@dataclass
class BacktestSummary:
    trades: int
    winrate: float
    net_pips: float
    gross_pips: float
    max_dd_pips: float
    avg_win_pips: float
    avg_loss_pips: float
    last_equity_pips: float
    sum_r: float = 0.0
    return_pct_est: float = 0.0
    notes: Optional[str] = None
