"""Regime-aware smart grid — a FREQUENT mechanical arm that trades daily in range.

Plain grid bots (Veles-style) place buy/sell orders on a fixed grid and profit from
oscillation — but they get RUN OVER in a trend (grid keeps buying into a falling
market -> holding a losing bag). That trend-blindness is their #1 failure. This grid
is "smarter" because it only operates when the market is actually ranging and it
KILLS itself the moment the range breaks:

  * ACTIVATE only when regime is range/flat (classify_channel + regime_hmm), NOT trend/high_vol;
  * ANCHOR the grid to the real channel [lower, upper] (not arbitrary spacing);
  * KILL-SWITCH: if price breaks the channel or regime flips to trend/high_vol ->
    halt & flatten (don't hold the bag);
  * risk-managed per level (position_sizing/exposure handled by caller).

Profits from mean-reversion inside a confirmed range -> trades often (daily) without
predicting direction. Must still pass backtest/OOS before live. Row [ts,o,h,l,c,v].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.market_context import atr, classify_channel, CLOSE
from bot.regime_hmm import regime_probs


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
    buy_levels: List[float]     # below price (bids)
    sell_levels: List[float]    # above price (asks)
    step: float
    regime: str
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def grid_plan(
    rows: Sequence[Sequence[float]],
    *,
    lookback: int = 60,
    n_levels: int = 6,
    kill_buffer_atr: float = 0.75,     # price this far beyond channel -> break -> kill
    min_width_atr: float = 2.0,        # channel must be wide enough to grid
    block_regimes: Sequence[str] = ("high_vol",),
    require_flat_regime: bool = True,  # only grid in flat/range, not trend
    atr_value: Optional[float] = None,
) -> GridState:
    """Plan a regime-gated grid inside the current channel, with a break kill-switch."""
    n = len(rows)
    if n < max(lookback, 30):
        return GridState(False, False, "idle", float("nan"), float("nan"), [], [],
                         float("nan"), "unknown", "insufficient_data")
    a = float(atr_value) if (atr_value is not None and atr_value == atr_value and atr_value > 0) else atr(rows)
    if not (a == a and a > 0):
        return GridState(False, False, "idle", float("nan"), float("nan"), [], [],
                         float("nan"), "unknown", "no_atr")

    price = _f(rows[-1], CLOSE)
    ch = classify_channel(rows, atr_value=a, lookback=lookback)
    lower, upper, regime = ch.get("lower_now", float("nan")), ch.get("upper_now", float("nan")), ch.get("regime", "unknown")
    reg = regime_probs(rows)

    # kill-switch: price broke out of the channel, or a blocked regime dominates
    broke = (upper == upper and price > upper + kill_buffer_atr * a) or \
            (lower == lower and price < lower - kill_buffer_atr * a)
    regime_bad = reg.ok and reg.dominant in block_regimes and reg.confidence >= 0.35
    if broke or regime_bad:
        return GridState(True, False, "halt_and_flatten", lower, upper, [], [], float("nan"),
                         reg.dominant if reg.ok else regime,
                         "channel_break" if broke else f"regime_{reg.dominant}")

    # activation gate: need a valid, wide-enough channel and (optionally) a flat regime
    if not (lower == lower and upper == upper and upper > lower):
        return GridState(True, False, "idle", lower, upper, [], [], float("nan"),
                         regime, "no_channel")
    width_atr = (upper - lower) / a
    if width_atr < min_width_atr:
        return GridState(True, False, "idle", lower, upper, [], [], float("nan"),
                         regime, f"channel_too_narrow_{width_atr:.1f}")
    if require_flat_regime and regime not in ("flat",) and not (reg.ok and reg.dominant == "range"):
        return GridState(True, False, "idle", lower, upper, [], [], float("nan"),
                         regime, f"not_range_regime_{regime}")

    # build grid inside [lower, upper]
    step = (upper - lower) / (n_levels + 1)
    grid = [lower + step * (k + 1) for k in range(n_levels)]
    buys = [g for g in grid if g < price]
    sells = [g for g in grid if g > price]
    return GridState(True, True, "run", lower, upper, buys, sells, step, regime,
                     "grid_active", extra={"width_atr": width_atr, "price": price})
