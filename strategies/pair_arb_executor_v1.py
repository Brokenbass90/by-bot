"""Two-leg executor for pair stat-arb — PAE1 (Opus 2026-06-09).

Turns a PairSignal (from pair_stat_arb_v1) into a concrete, market-neutral
two-leg plan: LONG the underperformer + SHORT the outperformer with equal notional
on ONE exchange (no cross-exchange transfers, no withdrawal keys). Pure planning +
position management + realized PnL — it returns ORDER INTENTS, it does NOT place
orders. Codex wires intents to the exchange (paper first). Risk is bounded by the
z-blowout stop.

Flow:
    plan_entry(signal, equity) -> (PairPosition, [OrderIntent x2])   # open
    plan_exit(position, px_long, px_short, cur_z) -> (reason, pnl, [OrderIntent x2]) or None
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

try:
    from strategies.pair_stat_arb_v1 import PairSignal, PairConfig
except Exception:  # standalone import for tests
    from pair_stat_arb_v1 import PairSignal, PairConfig  # type: ignore


@dataclass
class PairExecConfig:
    leg_frac_of_equity: float = 0.3    # notional per leg = equity * this (both legs ~equal)
    max_notional_per_leg: float = 100.0
    min_notional_per_leg: float = 10.0
    leverage: float = 1.0
    exit_z: float = 0.5                 # take profit: spread reverted
    stop_z: float = 3.0                 # bail: spread kept widening
    max_hold_bars: int = 168


@dataclass
class OrderIntent:
    symbol: str
    side: str          # "Buy" | "Sell"
    qty: float
    notional: float
    reduce_only: bool = False


@dataclass
class PairPosition:
    long_symbol: str
    short_symbol: str
    long_qty: float
    short_qty: float
    long_entry: float
    short_entry: float
    entry_z: float
    beta: float
    opened_bar: int = 0
    status: str = "PENDING"


def plan_entry(signal: PairSignal, equity: float, px_long: float, px_short: float,
               cfg: Optional[PairExecConfig] = None, opened_bar: int = 0):
    """Build the two opening legs (equal notional) + a PairPosition. Returns
    (position, [long_intent, short_intent]) or (None, []) if too small."""
    cfg = cfg or PairExecConfig()
    if px_long <= 0 or px_short <= 0 or equity <= 0:
        return None, []
    leg_notional = min(equity * cfg.leg_frac_of_equity * cfg.leverage, cfg.max_notional_per_leg)
    if leg_notional < cfg.min_notional_per_leg:
        return None, []
    long_qty = leg_notional / px_long
    short_qty = leg_notional / px_short
    pos = PairPosition(
        long_symbol=signal.long_symbol, short_symbol=signal.short_symbol,
        long_qty=long_qty, short_qty=short_qty, long_entry=px_long, short_entry=px_short,
        entry_z=signal.z, beta=signal.beta, opened_bar=opened_bar, status="OPEN",
    )
    intents = [
        OrderIntent(signal.long_symbol, "Buy", round(long_qty, 8), round(leg_notional, 4)),
        OrderIntent(signal.short_symbol, "Sell", round(short_qty, 8), round(leg_notional, 4)),
    ]
    return pos, intents


def pair_pnl(pos: PairPosition, px_long: float, px_short: float) -> float:
    """Realized/unrealized $ PnL of the pair = long leg + short leg."""
    long_pnl = (px_long - pos.long_entry) * pos.long_qty
    short_pnl = (pos.short_entry - px_short) * pos.short_qty
    return long_pnl + short_pnl


def plan_exit(pos: PairPosition, px_long: float, px_short: float, cur_z: float,
              cur_bar: int, cfg: Optional[PairExecConfig] = None):
    """Decide whether to close. Returns (reason, pnl, [close_intent x2]) or None."""
    cfg = cfg or PairExecConfig()
    if pos.status != "OPEN":
        return None
    reason = ""
    if abs(cur_z) <= cfg.exit_z:
        reason = f"reverted_z_{cur_z:.2f}"
    elif abs(cur_z) >= cfg.stop_z:
        reason = f"stop_z_{cur_z:.2f}"
    elif (cur_bar - pos.opened_bar) >= cfg.max_hold_bars:
        reason = "max_hold"
    if not reason:
        return None
    pnl = pair_pnl(pos, px_long, px_short)
    closes = [
        OrderIntent(pos.long_symbol, "Sell", round(pos.long_qty, 8), round(px_long * pos.long_qty, 4), reduce_only=True),
        OrderIntent(pos.short_symbol, "Buy", round(pos.short_qty, 8), round(px_short * pos.short_qty, 4), reduce_only=True),
    ]
    return reason, round(pnl, 6), closes
