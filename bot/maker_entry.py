"""Maker / post-only entry helpers — recover the fees that kill thin edges.

Measured: ASB1's edge thins from +0.65R to +0.18R purely from taker fees. ASB1/
ARF1 enter AT a level (support/resistance), so they are limit-natural — a
post-only limit a hair on the passive side earns the spread instead of paying
taker. This is the single highest-impact profitability lever and it's execution,
not a new strategy.

Pure / testable / additive. Codex wires `post_only_price` into the order body
(timeInForce=PostOnly) and uses `should_fallback_to_taker` to cross the spread
if price runs away before the maker fill lands.
"""
from __future__ import annotations

import math
from typing import Optional


def post_only_price(side: str, reference_price: float, *, offset_bps: float = 2.0,
                    tick: Optional[float] = None) -> float:
    """Passive limit price for a post-only entry.

    Buy  -> slightly BELOW reference (wait for price to come to us).
    Sell -> slightly ABOVE reference.
    `offset_bps` is how far inside the passive side to sit (small = more fills,
    larger = better price but more misses). Rounded to `tick` if given.
    """
    ref = float(reference_price)
    if ref <= 0:
        raise ValueError("reference_price must be > 0")
    off = ref * (float(offset_bps) / 10000.0)
    side_n = str(side or "").strip().lower()
    if side_n in ("buy", "long"):
        px = ref - off
    elif side_n in ("sell", "short"):
        px = ref + off
    else:
        raise ValueError(f"unknown side: {side}")
    if tick and tick > 0:
        # Preserve passive intent after tick rounding: buy must not round up,
        # sell must not round down, or PostOnly can become an accidental taker.
        units = px / tick
        if side_n in ("buy", "long"):
            px = math.floor(units) * tick
        else:
            px = math.ceil(units) * tick
    return px


def should_fallback_to_taker(*, bars_waited: int, max_wait_bars: int,
                             price_now: float, entry_ref: float, side: str,
                             max_adverse_bps: float = 15.0) -> bool:
    """Cross the spread (taker) if the maker order hasn't filled and either we
    waited too long OR price ran away past `max_adverse_bps` (we'd miss the move).
    """
    if bars_waited >= max_wait_bars:
        return True
    side_n = str(side or "").strip().lower()
    ref = float(entry_ref)
    if ref <= 0:
        return False
    move_bps = (float(price_now) - ref) / ref * 10000.0
    if side_n in ("buy", "long"):
        return move_bps >= max_adverse_bps      # price rose away from our buy
    if side_n in ("sell", "short"):
        return -move_bps >= max_adverse_bps      # price fell away from our sell
    return False
