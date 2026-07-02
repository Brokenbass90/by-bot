"""Break-of-structure (BOS) + change-of-character (CHoCH) — a frequent mechanical event.

We had BOS/CHoCH scattered inside strategies (choch_v1, breakdowns) but no clean,
tested detector. Structure breaks happen OFTEN (every swing break) -> a good answer to
our frequency problem, IF it carries edge. Definitions (from swing pivots):
  * trend = sequence of swings: HH+HL -> up, LH+LL -> down, else range.
  * BOS  = break of the last swing WITH the trend (continuation): up-trend breaks last
    swing HIGH -> long; down-trend breaks last swing LOW -> short.
  * CHoCH = break AGAINST the trend (character change / early reversal): up-trend breaks
    last swing LOW -> short; down-trend breaks last swing HIGH -> long.

Side split (long_ok XOR short_ok). Pairs with level_entry(retest of broken swing) or
immediate entry. Row [ts,o,h,l,c,v]. Pure stdlib + market_context pivots.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

from bot.market_context import atr, pivot_highs, pivot_lows, CLOSE


def _f(row, i):
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


@dataclass
class StructureBreak:
    ok: bool
    event: str                 # "bos" | "choch" | "none"
    direction: str             # "up" | "down" | "none"
    trend: str                 # "up" | "down" | "range"
    level: float               # the swing that was broken
    side: str                  # "long" | "short" | "none"
    long_ok: bool
    short_ok: bool
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def structure_break(
    rows: Sequence[Sequence[float]],
    *,
    left: int = 2,
    right: int = 2,
    buffer_atr: float = 0.10,
    atr_value: Optional[float] = None,
) -> StructureBreak:
    """Detect a BOS (continuation) or CHoCH (reversal) from swing structure."""
    n = len(rows)
    if n < 4 * (left + right) + 5:
        return StructureBreak(False, "none", "none", "range", float("nan"), "none",
                              False, False, "insufficient_data")
    a = float(atr_value) if (atr_value is not None and atr_value == atr_value and atr_value > 0) else atr(rows)
    if not (a == a and a > 0):
        return StructureBreak(False, "none", "none", "range", float("nan"), "none",
                              False, False, "no_atr")
    ph = pivot_highs(rows, left, right)
    pl = pivot_lows(rows, left, right)
    if len(ph) < 2 or len(pl) < 2:
        return StructureBreak(True, "none", "none", "range", float("nan"), "none",
                              False, False, "not_enough_swings")

    last_high, prev_high = ph[-1]["price"], ph[-2]["price"]
    last_low, prev_low = pl[-1]["price"], pl[-2]["price"]
    if last_high > prev_high and last_low > prev_low:
        trend = "up"
    elif last_high < prev_high and last_low < prev_low:
        trend = "down"
    else:
        trend = "range"

    price = _f(rows[-1], CLOSE)
    buf = buffer_atr * a
    broke_high = price > last_high + buf
    broke_low = price < last_low - buf

    if broke_high:
        event = "choch" if trend == "down" else "bos"
        return StructureBreak(True, event, "up", trend, last_high, "long", True, False,
                              f"{event}_up")
    if broke_low:
        event = "choch" if trend == "up" else "bos"
        return StructureBreak(True, event, "down", trend, last_low, "short", False, True,
                              f"{event}_down")
    return StructureBreak(True, "none", "none", trend, float("nan"), "none", False, False,
                          "no_break")
