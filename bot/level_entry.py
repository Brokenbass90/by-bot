"""Maker-limit-at-level entry planner — heals the late-entry root cause.

The core failure of the directional legs (InPlay etc.): they entered at the bar
CLOSE, already far from the level -> wide stop -> killed R:R. This module turns a
detected setup (level + side) into a LIMIT order placed AT the level, so the stop
is tight (just beyond the level) and R is large. It also refuses to CHASE: if
price has already run past the level, it skips instead of entering late.

It only builds a *plan* (price/stop/tp/validity/guards) — the live executor places
the order. `simulate_fill` lets backtests model maker fills honestly (did price
trade back to the limit within the validity window?).

Side split: support -> LONG plan, resistance -> SHORT plan.
Row format: [ts, open, high, low, close, volume]. Pure stdlib + bot.market_context.atr.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.market_context import atr, OPEN, HIGH, LOW, CLOSE


def _f(row: Sequence[float], i: int) -> float:
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


@dataclass
class LimitEntryPlan:
    ok: bool
    place: bool                # place the limit order?
    side: str                  # "long" | "short" | "none"
    order_type: str            # "limit" | "skip"
    limit_price: float
    stop: float
    tp1: float
    tp2: float
    risk: float                # price distance to stop (per unit)
    rr1: float
    rr2: float
    stop_pct: float
    validity_bars: int
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _skip(side: str, reason: str) -> LimitEntryPlan:
    return LimitEntryPlan(
        ok=True, place=False, side=side, order_type="skip", limit_price=float("nan"),
        stop=float("nan"), tp1=float("nan"), tp2=float("nan"), risk=float("nan"),
        rr1=float("nan"), rr2=float("nan"), stop_pct=float("nan"), validity_bars=0,
        reason=reason,
    )


def plan_level_entry(
    rows: Sequence[Sequence[float]],
    level: float,
    side: str,                        # "support" (long) | "resistance" (short)
    *,
    atr_value: Optional[float] = None,
    offset_atr: float = 0.05,         # place limit this far INSIDE the level (maker)
    stop_buffer_atr: float = 0.4,     # stop this far BEYOND the level (~tight)
    tp1_rr: float = 1.0,
    tp_rr: float = 2.5,               # asymmetric take (2-3R)
    max_chase_atr: float = 0.5,       # if price is already this far past level -> skip
    validity_bars: int = 4,
    min_stop_pct: float = 0.0015,
    max_stop_pct: float = 0.08,
) -> LimitEntryPlan:
    """Build a maker-limit entry AT the level with a tight stop and asymmetric TP."""
    n = len(rows)
    if n < 5 or side not in ("support", "resistance"):
        return _skip("none", "bad_input")
    a = float(atr_value) if (atr_value is not None and atr_value == atr_value and atr_value > 0) else atr(rows)
    if not (a == a and a > 0) or not (level == level and level > 0):
        return _skip("none", "no_atr_or_level")

    price = _f(rows[-1], CLOSE)
    long_side = (side == "support")
    s = "long" if long_side else "short"

    if long_side:
        # buy the retest: limit just above support; stop below support
        limit_price = level + offset_atr * a
        stop = level - stop_buffer_atr * a
        # chase guard: price already ran far ABOVE the level -> we'd be entering late
        if price - level > max_chase_atr * a:
            return _skip(s, "would_chase_above_level")
        risk = limit_price - stop
        tp1 = limit_price + tp1_rr * risk
        tp2 = limit_price + tp_rr * risk
    else:
        # sell the retest: limit just below resistance; stop above resistance
        limit_price = level - offset_atr * a
        stop = level + stop_buffer_atr * a
        if level - price > max_chase_atr * a:
            return _skip(s, "would_chase_below_level")
        risk = stop - limit_price
        tp1 = limit_price - tp1_rr * risk
        tp2 = limit_price - tp_rr * risk

    if risk <= 0:
        return _skip(s, "nonpositive_risk")
    stop_pct = risk / limit_price
    if stop_pct < min_stop_pct:
        return _skip(s, f"stop_too_tight_{stop_pct:.4f}")
    if stop_pct > max_stop_pct:
        return _skip(s, f"stop_too_wide_{stop_pct:.4f}")

    rr1 = abs(tp1 - limit_price) / risk
    rr2 = abs(tp2 - limit_price) / risk
    return LimitEntryPlan(
        ok=True, place=True, side=s, order_type="limit", limit_price=limit_price,
        stop=stop, tp1=tp1, tp2=tp2, risk=risk, rr1=rr1, rr2=rr2, stop_pct=stop_pct,
        validity_bars=validity_bars, reason="limit_at_level", extra={"atr": a, "level": level},
    )


def simulate_fill(rows_after: Sequence[Sequence[float]], plan: LimitEntryPlan) -> Dict[str, Any]:
    """Honest maker-fill model: did price trade to the limit within validity_bars?

    Long fills if a subsequent bar's LOW <= limit_price; short if HIGH >= limit_price.
    Returns filled(bool), fill_bar(index into rows_after or -1), bars_waited.
    """
    if not plan.place:
        return {"filled": False, "fill_bar": -1, "bars_waited": 0, "reason": "no_order"}
    horizon = min(len(rows_after), max(1, plan.validity_bars))
    for k in range(horizon):
        r = rows_after[k]
        if plan.side == "long" and _f(r, LOW) <= plan.limit_price:
            return {"filled": True, "fill_bar": k, "bars_waited": k, "reason": "filled"}
        if plan.side == "short" and _f(r, HIGH) >= plan.limit_price:
            return {"filled": True, "fill_bar": k, "bars_waited": k, "reason": "filled"}
    return {"filled": False, "fill_bar": -1, "bars_waited": horizon, "reason": "expired_unfilled"}
