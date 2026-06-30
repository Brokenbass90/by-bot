"""Confirmed level-breakout detector (horizontal + sloped), anti-false-break.

Layer 5 of the roadmap. Pumps/ranges fade; this is the *with-trend* arm: a level
(horizontal S/R or a sloped channel line) gives way and price commits beyond it.
The classic failure is the false breakout (stop-hunt then snap back), so a break
is only `confirmed` when:
  * close is beyond the level by >= `buffer_atr` * ATR (not just a wick);
  * volume on the break confirms (>= `vol_mult` vs recent norm) OR there is
    follow-through (>= `followthrough_bars` recent closes beyond the level);
  * price has NOT been reclaimed (current close still beyond the level).

Side split (one-directional):
  * break UP   -> LONG-ONLY  (long_ok)
  * break DOWN -> SHORT-ONLY (short_ok)

Pair with bot.retest_quality for the lower-risk retest entry after the break
(the broken level flips and is re-tested). Row: [ts,o,h,l,c,v]. Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.market_context import horizontal_levels, classify_channel, atr, CLOSE, HIGH, LOW, VOL


def _f(row: Sequence[float], i: int) -> float:
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def _mean(xs: List[float]) -> float:
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float("nan")


@dataclass
class BreakoutState:
    ok: bool
    broke: bool
    direction: str           # "up" | "down" | "none"
    kind: str                # "horizontal" | "sloped" | "none"
    confirmed: bool          # passed buffer + (volume or follow-through) + not reclaimed
    long_ok: bool            # confirmed up-break
    short_ok: bool           # confirmed down-break
    level: float
    close_beyond_atr: float  # how far beyond the level the close is, in ATR
    followthrough: int       # consecutive recent closes beyond the level
    vol_mult: float
    reclaimed: bool          # price closed back inside (false-break flag)
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _blank(reason: str) -> BreakoutState:
    return BreakoutState(
        ok=False, broke=False, direction="none", kind="none", confirmed=False,
        long_ok=False, short_ok=False, level=float("nan"), close_beyond_atr=float("nan"),
        followthrough=0, vol_mult=float("nan"), reclaimed=False, reason=reason,
    )


def breakout_confirm(
    rows: Sequence[Sequence[float]],
    *,
    buffer_atr: float = 0.25,
    vol_mult: float = 1.3,
    vol_window: int = 20,
    followthrough_bars: int = 2,
    event_window: int = 5,
    min_touches: int = 2,
    lookback: int = 60,
    use_sloped: bool = True,
) -> BreakoutState:
    """Detect a confirmed horizontal or sloped breakout with a long/short gate."""
    n = len(rows)
    if n < max(30, lookback // 2):
        return _blank("insufficient_data")
    a = atr(rows)
    if not (a == a and a > 0):
        return _blank("no_atr")
    buf = buffer_atr * a
    price = _f(rows[-1], CLOSE)
    closes = [_f(r, CLOSE) for r in rows]
    prior_close = closes[-event_window - 1] if n > event_window + 1 else closes[0]

    res = horizontal_levels(rows, side="resistance", atr_value=a, min_touches=min_touches)
    sup = horizontal_levels(rows, side="support", atr_value=a, min_touches=min_touches)

    cand = None  # (direction, kind, level)
    # horizontal up-break: a former resistance now closed above by buffer
    up_res = [lv["level"] for lv in res if price > lv["level"] + buf and prior_close <= lv["level"] + buf]
    dn_sup = [lv["level"] for lv in sup if price < lv["level"] - buf and prior_close >= lv["level"] - buf]
    if up_res:
        cand = ("up", "horizontal", max(up_res))      # the highest resistance cleared
    elif dn_sup:
        cand = ("down", "horizontal", min(dn_sup))     # the lowest support lost

    # sloped break (channel line) if no horizontal event
    if cand is None and use_sloped:
        ch = classify_channel(rows, atr_value=a, lookback=lookback)
        up_now, lo_now = ch.get("upper_now", float("nan")), ch.get("lower_now", float("nan"))
        if up_now == up_now and price > up_now + buf and prior_close <= up_now + buf:
            cand = ("up", "sloped", up_now)
        elif lo_now == lo_now and price < lo_now - buf and prior_close >= lo_now - buf:
            cand = ("down", "sloped", lo_now)

    if cand is None:
        return _blank("no_breakout")

    direction, kind, level = cand
    broke = True

    # confirmation metrics
    if direction == "up":
        close_beyond_atr = (price - level) / a
        ft = sum(1 for c in closes[-followthrough_bars:] if c > level)
        reclaimed = price <= level
    else:
        close_beyond_atr = (level - price) / a
        ft = sum(1 for c in closes[-followthrough_bars:] if c < level)
        reclaimed = price >= level

    base_vol = _mean([_f(r, VOL) for r in rows[-(vol_window + 1):-1]])
    cur_vol = _f(rows[-1], VOL)
    vmult = (cur_vol / base_vol) if (base_vol == base_vol and base_vol > 0 and cur_vol == cur_vol) else float("nan")

    vol_ok = (vmult == vmult and vmult >= vol_mult)
    ft_ok = ft >= followthrough_bars
    buffer_ok = close_beyond_atr >= buffer_atr
    confirmed = bool(broke and buffer_ok and (vol_ok or ft_ok) and not reclaimed)

    long_ok = bool(confirmed and direction == "up")
    short_ok = bool(confirmed and direction == "down")

    if reclaimed:
        reason = "false_break_reclaimed"
    elif not buffer_ok:
        reason = "inside_buffer"
    elif not (vol_ok or ft_ok):
        reason = "no_volume_or_followthrough"
    else:
        reason = "breakout_confirmed"

    return BreakoutState(
        ok=True, broke=broke, direction=direction, kind=kind, confirmed=confirmed,
        long_ok=long_ok, short_ok=short_ok, level=float(level),
        close_beyond_atr=close_beyond_atr, followthrough=int(ft), vol_mult=vmult,
        reclaimed=reclaimed, reason=reason, extra={"atr": a, "buffer": buf},
    )
