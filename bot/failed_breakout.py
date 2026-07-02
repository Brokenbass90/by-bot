"""Failed-breakout / exhaustion fade — the RIGHT logic for range-fade (ARF2 fix).

Fading "just because price is at resistance" gets chopped up: in a real breakout the
level gives way and you're run over. The edge is fading a breakout that FAILED —
price pushed BEYOND the level, could not hold, and reclaimed back inside. That failure
is the signal (trapped breakout traders unwind). This is multi-bar (unlike a 1-bar
liquidity sweep): a bar closed beyond the level, then price closed back inside within
`event_window`, ideally with volume/momentum exhausting.

Side split: failed break ABOVE resistance -> SHORT fade; failed break BELOW support -> LONG.
Pairs with level_entry + range_filter. Row [ts,o,h,l,c,v]. Pure stdlib + market_context.atr.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

from bot.market_context import atr, HIGH, LOW, CLOSE, VOL


def _f(row, i):
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def _mean(xs):
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float("nan")


@dataclass
class FailedBreakState:
    ok: bool
    failed: bool
    direction: str            # "up" (failed break above) | "down" | "none"
    level: float
    side: str                 # "short" | "long" | "none"
    long_ok: bool
    short_ok: bool
    reclaim_bars: int         # bars price spent beyond the level before reclaiming
    vol_faded: bool
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def failed_breakout(
    rows: Sequence[Sequence[float]],
    *,
    level_lookback: int = 20,
    event_window: int = 5,
    buffer_atr: float = 0.15,
    require_reclaim_close: bool = True,
    require_vol_fade: bool = False,
    vol_window: int = 20,
    atr_value: Optional[float] = None,
) -> FailedBreakState:
    """Detect a failed breakout (broke a level, could not hold, reclaimed) -> fade."""
    n = len(rows)
    if n < level_lookback + event_window + 2:
        return FailedBreakState(False, False, "none", float("nan"), "none", False, False,
                                0, False, "insufficient_data")
    a = float(atr_value) if (atr_value is not None and atr_value == atr_value and atr_value > 0) else atr(rows)
    if not (a == a and a > 0):
        return FailedBreakState(False, False, "none", float("nan"), "none", False, False,
                                0, False, "no_atr")
    buf = buffer_atr * a
    # define the level from bars BEFORE the event window (the range boundary being tested)
    base = rows[-level_lookback - event_window:-event_window]
    resistance = max(_f(r, HIGH) for r in base)
    support = min(_f(r, LOW) for r in base)
    ev = rows[-event_window:]
    price = _f(rows[-1], CLOSE)

    # volume fade on the event vs baseline
    base_vol = _mean([_f(r, VOL) for r in rows[-(vol_window + event_window):-event_window]])
    ev_peak_vol = max(_f(r, VOL) for r in ev)
    last_vol = _f(rows[-1], VOL)
    vol_faded = bool(base_vol == base_vol and base_vol > 0 and ev_peak_vol > base_vol
                     and last_vol < ev_peak_vol)

    # failed break UP: a bar in the window pushed a CLOSE above resistance+buf, latest close back below
    up_break_bars = [j for j, r in enumerate(ev) if _f(r, CLOSE) > resistance + buf]
    reclaimed_down = price < resistance
    if up_break_bars and reclaimed_down and (not require_vol_fade or vol_faded):
        return FailedBreakState(True, True, "up", resistance, "short", False, True,
                                len(up_break_bars), vol_faded, "failed_break_above")

    # failed break DOWN
    dn_break_bars = [j for j, r in enumerate(ev) if _f(r, CLOSE) < support - buf]
    reclaimed_up = price > support
    if dn_break_bars and reclaimed_up and (not require_vol_fade or vol_faded):
        return FailedBreakState(True, True, "down", support, "long", True, False,
                                len(dn_break_bars), vol_faded, "failed_break_below")

    return FailedBreakState(True, False, "none", float("nan"), "none", False, False,
                            0, vol_faded, "no_failed_break")
