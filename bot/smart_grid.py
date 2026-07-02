"""Regime-aware, FEE-AWARE smart grid — only strong flats, steps that beat fees.

v1 smoke lost badly (PF 0.34, DD 86): tiny takes eaten by fees + gridding into trends.
Root fixes here:
  1. STRONG-FLAT gate: activate only when range_filter confirms range (3-measure vote),
     regime not high_vol, and a valid bounded channel exists (not a weak/one-line "flat").
  2. FEE-AWARE spacing: each grid step must be >= fee_survival_mult * round-trip fee, so a
     level's TP actually clears costs. If the channel can't fit even 2 fee-surviving steps
     -> IDLE (don't grid inside noise).
  3. KILL-SWITCH: channel break or regime flip -> halt_and_flatten (never hold the bag).

Grid is ~n_levels bids/asks anchored in [lower, upper]. Profits from oscillation in a
strong flat, exits the whole idea on breakout. Row [ts,o,h,l,c,v]. Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.market_context import atr, classify_channel, CLOSE
from bot.regime_hmm import regime_probs
from bot.range_filter import range_state


def _f(row, i):
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


@dataclass
class GridState:
    ok: bool
    active: bool
    action: str                 # "run" | "halt_and_flatten" | "idle"
    lower: float
    upper: float
    buy_levels: List[float]
    sell_levels: List[float]
    step: float
    step_pct: float             # grid step as % of price (must beat fees)
    n_levels: int
    side: str                   # "long" | "short" | "both"
    regime: str
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def grid_plan(
    rows: Sequence[Sequence[float]],
    *,
    lookback: int = 60,
    n_levels: int = 10,
    fee_bps: float = 6.0,               # per-side taker fee
    fee_survival_mult: float = 3.0,     # step must be >= this * round-trip fee
    kill_buffer_atr: float = 0.75,
    min_width_atr: float = 2.0,
    require_strong_flat: bool = True,
    side: str = "both",           # "long"=only bids, "short"=only asks, "both"
    atr_value: Optional[float] = None,
) -> GridState:
    """Plan a fee-aware grid inside a STRONG flat, with a break kill-switch."""
    n = len(rows)
    if n < max(lookback, 30):
        return GridState(False, False, "idle", float("nan"), float("nan"), [], [],
                         float("nan"), float("nan"), 0, side, "unknown", "insufficient_data")
    a = float(atr_value) if (atr_value is not None and atr_value == atr_value and atr_value > 0) else atr(rows)
    if not (a == a and a > 0):
        return GridState(False, False, "idle", float("nan"), float("nan"), [], [],
                         float("nan"), float("nan"), 0, side, "unknown", "no_atr")

    price = _f(rows[-1], CLOSE)
    ch = classify_channel(rows, atr_value=a, lookback=lookback)
    lower, upper, regime = ch.get("lower_now", float("nan")), ch.get("upper_now", float("nan")), ch.get("regime", "unknown")
    reg = regime_probs(rows)

    # kill-switch first: broke channel or bad regime
    broke = (upper == upper and price > upper + kill_buffer_atr * a) or \
            (lower == lower and price < lower - kill_buffer_atr * a)
    regime_bad = reg.ok and reg.dominant == "high_vol" and reg.confidence >= 0.35
    if broke or regime_bad:
        return GridState(True, False, "halt_and_flatten", lower, upper, [], [], float("nan"),
                         float("nan"), 0, side, reg.dominant if reg.ok else regime,
                         "channel_break" if broke else "regime_high_vol")

    if not (lower == lower and upper == upper and upper > lower):
        return GridState(True, False, "idle", lower, upper, [], [], float("nan"), float("nan"),
                         0, side, regime, "no_channel")
    width_atr = (upper - lower) / a
    if width_atr < min_width_atr:
        return GridState(True, False, "idle", lower, upper, [], [], float("nan"), float("nan"),
                         0, side, regime, f"channel_too_narrow_{width_atr:.1f}")

    # STRONG-FLAT gate: range_filter must confirm range (3-measure vote), not just a slope label
    if require_strong_flat:
        rs = range_state(rows)
        if not (rs.ok and rs.is_range):
            return GridState(True, False, "idle", lower, upper, [], [], float("nan"), float("nan"),
                             0, side, regime, "not_strong_flat")

    # FEE-AWARE spacing: shrink n_levels until each step beats fees, else idle
    min_step_pct = fee_survival_mult * (2.0 * fee_bps / 1e4)   # round-trip fee * mult
    levels = int(n_levels)
    step = step_pct = 0.0
    while levels >= 2:
        step = (upper - lower) / (levels + 1)
        step_pct = step / price if price else 0.0
        if step_pct >= min_step_pct:
            break
        levels -= 1
    if levels < 2 or step_pct < min_step_pct:
        return GridState(True, False, "idle", lower, upper, [], [], step, step_pct, 0, side, regime,
                         f"fee_infeasible_step{step_pct*100:.3f}%<min{min_step_pct*100:.3f}%")

    grid = [lower + step * (k + 1) for k in range(levels)]
    buys = [g for g in grid if g < price]     # bids: open/add long on dips
    sells = [g for g in grid if g > price]    # asks: open/add short on rallies
    if side == "long":                        # long-only grid: only bid entries
        sells = []
    elif side == "short":                     # short-only grid: only ask entries
        buys = []
    if not buys and not sells:
        return GridState(True, False, "idle", lower, upper, [], [], step, step_pct, 0, side,
                         regime, f"no_entries_for_side_{side}")
    return GridState(True, True, "run", lower, upper, buys, sells, step, step_pct, levels, side,
                     regime, "grid_active", extra={"width_atr": width_atr, "price": price,
                                                   "min_step_pct": min_step_pct})
