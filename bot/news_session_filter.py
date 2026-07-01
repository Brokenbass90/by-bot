"""News + session entry filter for forex/CFD (DeepSeek H2 — mandatory).

Forex ranges are cleaner than crypto, BUT high-impact news (NFP, rate decisions)
blows through any level (false breakouts / stop runs), the Asian session is often
too thin for a range TP to fill while spread accrues, and desks hunt stops at round
numbers. This gate blocks/flags those exact traps so a range/bounce leg only trades
when conditions are sane.

Timestamps are epoch SECONDS (UTC). `events` is a calendar list [{"ts", "impact"}]
supplied by the live wiring / a data file; the filter is pure logic over it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# FX sessions by UTC hour (rough, standard desks)
def session_of(ts: float) -> str:
    h = int(ts // 3600) % 24
    if 12 <= h < 16:
        return "london_ny_overlap"      # most liquid
    if 7 <= h < 12:
        return "london"
    if 16 <= h < 21:
        return "newyork"
    return "asian"                       # 21:00-07:00 UTC, thin


LOW_LIQ_SESSIONS = {"asian"}


@dataclass
class FilterState:
    ok: bool
    allow: bool
    session: str
    is_low_liq_session: bool
    in_news_blackout: bool
    minutes_to_event: float             # to nearest blocking event (nan if none)
    near_round_number: bool
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _near_round(price: float, tol_frac: float) -> bool:
    if not (price == price and price > 0):
        return False
    # distance to nearest 0.5%-scale round level: use the price's own magnitude
    import math
    mag = 10 ** (math.floor(math.log10(price)) - 1)   # ~1% grid step
    step = mag
    nearest = round(price / step) * step
    return abs(price - nearest) <= tol_frac * price


def entry_allowed(
    ts: float,
    *,
    events: Optional[Sequence[Dict[str, Any]]] = None,
    price: Optional[float] = None,
    block_before_min: float = 60.0,
    block_after_min: float = 30.0,
    min_impact: int = 2,                 # block events with impact >= this (e.g. 2=high)
    avoid_low_liq_session: bool = True,
    round_number_tol_frac: float = 0.0005,
) -> FilterState:
    """Decide if a forex entry is allowed at `ts` given news calendar + session."""
    sess = session_of(ts)
    low_liq = sess in LOW_LIQ_SESSIONS

    in_blackout = False
    mins_to = float("nan")
    before_s = block_before_min * 60.0
    after_s = block_after_min * 60.0
    for ev in (events or []):
        ets = ev.get("ts")
        imp = int(ev.get("impact", 0) or 0)
        if ets is None or imp < min_impact:
            continue
        ets = float(ets)
        if ets - before_s <= ts <= ets + after_s:
            in_blackout = True
            d = abs(ets - ts) / 60.0
            mins_to = d if (mins_to != mins_to or d < mins_to) else mins_to
        elif ts < ets:
            d = (ets - ts) / 60.0
            mins_to = d if (mins_to != mins_to or d < mins_to) else mins_to

    near_round = _near_round(float(price), round_number_tol_frac) if price is not None else False

    allow = True
    reason = "ok"
    if in_blackout:
        allow = False
        reason = "news_blackout"
    elif avoid_low_liq_session and low_liq:
        allow = False
        reason = "low_liquidity_session"

    return FilterState(
        ok=True, allow=allow, session=sess, is_low_liq_session=low_liq,
        in_news_blackout=in_blackout, minutes_to_event=mins_to,
        near_round_number=near_round, reason=reason,
        extra={"round_flag_only": near_round and allow},
    )
