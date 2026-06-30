"""Impulse (pump/dump) exhaustion detector for confirmation-gated fades.

Owner's rule: pumps are a real opportunity but the OLD code entered a fade with
no clear reversal confirmation, and modern pumps are manipulative (fake push,
then snap back). So we must NEVER fade the extreme — only AFTER the impulse is
exhausted AND price has visibly turned. This module supplies that gate.

Side split (one-directional, like range_filter):
  * up-pump exhausted  -> SHORT-ONLY fade  (short_ok)
  * down-dump exhausted -> LONG-ONLY fade  (long_ok)

A fade is allowed only when ALL confirmations hold:
  1. impulse present     — fast move over `impulse_window` >= `min_impulse_pct`
                           AND volume surge >= `min_vol_mult` vs baseline;
  2. momentum exhausted  — latest bar shows rejection (wick against impulse) or
                           body shrink, and volume faded vs the impulse peak;
  3. reversal confirmed  — price has retraced >= `confirm_retrace` of the impulse
                           range (closed back through it) — i.e. it already turned.

Row format: [ts, open, high, low, close, volume]. Pure stdlib, deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

TS, OPEN, HIGH, LOW, CLOSE, VOL = 0, 1, 2, 3, 4, 5


def _f(row: Sequence[float], i: int) -> float:
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def _mean(xs: List[float]) -> float:
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float("nan")


@dataclass
class ImpulseFadeState:
    ok: bool                 # enough data + decision made
    impulse: bool            # a pump/dump was detected
    direction: str           # "up" | "down" | "none"
    exhausted: bool          # momentum faded
    confirmed: bool          # price has turned (retraced through impulse)
    fade_side: str           # "short" | "long" | "none"
    short_ok: bool           # up-pump exhausted+confirmed -> fade short
    long_ok: bool            # down-dump exhausted+confirmed -> fade long
    impulse_pct: float       # signed impulse magnitude over window
    vol_mult: float          # impulse volume / baseline volume
    peak_fade: float         # recent volume / impulse peak volume
    retrace_frac: float      # how much of the impulse range price gave back
    rejection_frac: float    # wick-against-impulse fraction on the latest bar
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def impulse_exhaustion(
    rows: Sequence[Sequence[float]],
    *,
    impulse_window: int = 4,
    baseline_window: int = 20,
    peak_window: int = 6,
    min_impulse_pct: float = 0.05,     # >=5% fast move = impulse
    min_vol_mult: float = 2.0,         # impulse vol >= 2x baseline
    peak_fade_ratio: float = 0.70,     # recent vol < 70% of peak = fading
    min_rejection_frac: float = 0.35,  # wick against impulse on latest bar
    confirm_retrace: float = 0.33,     # price gave back >=33% of impulse range
    min_bars: int = 26,
) -> ImpulseFadeState:
    """Detect an exhausted+confirmed pump/dump and emit a one-sided fade gate."""
    blank = ImpulseFadeState(
        ok=False, impulse=False, direction="none", exhausted=False, confirmed=False,
        fade_side="none", short_ok=False, long_ok=False, impulse_pct=float("nan"),
        vol_mult=float("nan"), peak_fade=float("nan"), retrace_frac=float("nan"),
        rejection_frac=float("nan"), reason="insufficient_data",
    )
    n = len(rows)
    if n < max(min_bars, baseline_window + impulse_window + 1):
        return blank

    iw = impulse_window
    imp = rows[-iw:]
    base = rows[-(baseline_window + iw):-iw]

    start_open = _f(imp[0], OPEN)
    last = rows[-1]
    cur_close = _f(last, CLOSE)
    if not (start_open == start_open and start_open > 0 and cur_close == cur_close):
        return blank

    # impulse extremes within the window
    hi = max(_f(r, HIGH) for r in imp)
    lo = min(_f(r, LOW) for r in imp)
    impulse_pct = (max(_f(r, CLOSE) for r in imp) - start_open) / start_open  # up bias
    # direction by net move start->peak vs start->trough
    up_move = (hi - start_open) / start_open
    down_move = (start_open - lo) / start_open
    if up_move >= down_move:
        direction = "up"
        impulse_pct = up_move
    else:
        direction = "down"
        impulse_pct = down_move

    vol_recent = _mean([_f(r, VOL) for r in imp])
    vol_base = _mean([_f(r, VOL) for r in base])
    vol_mult = vol_recent / vol_base if (vol_base and vol_base == vol_base and vol_base > 0) else float("nan")

    impulse = (impulse_pct >= min_impulse_pct) and (vol_mult == vol_mult and vol_mult >= min_vol_mult)

    # exhaustion: volume fading vs the impulse's peak bar + rejection wick on last bar
    peak_vol = max(_f(r, VOL) for r in rows[-peak_window:])
    last_vol = _f(last, VOL)
    peak_fade = (last_vol / peak_vol) if (peak_vol and peak_vol > 0) else float("nan")
    o, h, l, c = _f(last, OPEN), _f(last, HIGH), _f(last, LOW), _f(last, CLOSE)
    bar_rng = max(1e-12, h - l)
    if direction == "up":
        rejection_frac = (h - max(o, c)) / bar_rng         # upper wick
    else:
        rejection_frac = (min(o, c) - l) / bar_rng         # lower wick
    vol_fading = (peak_fade == peak_fade and peak_fade < peak_fade_ratio)
    exhausted = bool(impulse and (vol_fading or rejection_frac >= min_rejection_frac))

    # confirmation: price retraced back through the impulse range
    rng = max(1e-12, hi - lo)
    if direction == "up":
        retrace_frac = (hi - cur_close) / rng              # gave back from the top
    else:
        retrace_frac = (cur_close - lo) / rng              # bounced from the bottom
    confirmed = bool(impulse and retrace_frac >= confirm_retrace)

    short_ok = bool(direction == "up" and exhausted and confirmed)
    long_ok = bool(direction == "down" and exhausted and confirmed)
    fade_side = "short" if short_ok else ("long" if long_ok else "none")

    if not impulse:
        reason = "no_impulse"
    elif not exhausted:
        reason = "not_exhausted_yet"
    elif not confirmed:
        reason = "no_reversal_confirmation"
    else:
        reason = "fade_confirmed"

    return ImpulseFadeState(
        ok=True, impulse=impulse, direction=direction, exhausted=exhausted,
        confirmed=confirmed, fade_side=fade_side, short_ok=short_ok, long_ok=long_ok,
        impulse_pct=impulse_pct, vol_mult=vol_mult, peak_fade=peak_fade,
        retrace_frac=retrace_frac, rejection_frac=rejection_frac, reason=reason,
        extra={"direction": direction, "hi": hi, "lo": lo},
    )
