"""Reusable level-freshness + retest-quality scorer (crypto + forex/CFD).

InPlay V4 already enters tightly at fresh levels; this module factors that logic
out into ONE shared scorer every level-based leg can use (IRV4, support_bounce,
channel_bounce, breakout-retest, forex retests) so "what is a good retest" is
defined in a single place and graded 0..1 instead of a yes/no patchwork.

A good retest entry (owner's fast-entry-at-level rule -> small stop, big R):
  * freshness  — the level was touched recently (stale levels decay);
  * proximity  — price is right AT the level now (tight band -> small stop);
  * strength   — the level has multiple touches (but not so many it's about to break);
  * rejection  — the current bar shows a wick rejecting off the level;
  * volume     — retest bar volume confirms (>= mult vs recent norm).

Side split (one-directional): retest of SUPPORT -> LONG-ONLY; of RESISTANCE -> SHORT-ONLY.

Row format: [ts, open, high, low, close, volume]. Pure stdlib + bot.market_context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.market_context import horizontal_levels, atr, TS, OPEN, HIGH, LOW, CLOSE, VOL


def _f(row: Sequence[float], i: int) -> float:
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def _mean(xs: List[float]) -> float:
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float("nan")


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


@dataclass
class RetestScore:
    ok: bool                 # data sufficient + a level was evaluated
    entry_ok: bool           # quality + proximity + rejection all clear
    side: str                # "long" | "short" | "none"
    long_ok: bool            # fresh support retest
    short_ok: bool           # fresh resistance retest
    level: float
    dist_atr: float          # |price - level| / atr  (proximity)
    freshness_bars: int      # bars since the level was last touched
    touches: int
    quality: float           # 0..1 weighted score
    freshness_score: float
    proximity_score: float
    strength_score: float
    rejection_score: float
    volume_score: float
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _blank(reason: str) -> RetestScore:
    return RetestScore(
        ok=False, entry_ok=False, side="none", long_ok=False, short_ok=False,
        level=float("nan"), dist_atr=float("nan"), freshness_bars=-1, touches=0,
        quality=0.0, freshness_score=0.0, proximity_score=0.0, strength_score=0.0,
        rejection_score=0.0, volume_score=0.0, reason=reason,
    )


def score_retest(
    rows: Sequence[Sequence[float]],
    level: float,
    side: str,                       # "support" (long) | "resistance" (short)
    *,
    atr_value: Optional[float] = None,
    last_touch_idx: Optional[int] = None,
    touches: int = 0,
    entry_band_atr: float = 0.30,
    max_age_bars: int = 48,
    ideal_touches: int = 3,
    max_touches: int = 8,
    vol_mult: float = 1.3,
    vol_window: int = 20,
    min_quality: float = 0.55,
    w=(0.25, 0.30, 0.15, 0.20, 0.10),   # freshness, proximity, strength, rejection, volume
) -> RetestScore:
    """Grade one candidate level as a retest entry. side picks long/short."""
    n = len(rows)
    if n < 5 or side not in ("support", "resistance"):
        return _blank("bad_input")
    a = float(atr_value) if (atr_value is not None and atr_value == atr_value and atr_value > 0) else atr(rows)
    if not (a == a and a > 0) or not (level == level and level > 0):
        return _blank("no_atr_or_level")

    bar = rows[-1]
    o, h, l, c = _f(bar, OPEN), _f(bar, HIGH), _f(bar, LOW), _f(bar, CLOSE)
    bar_rng = max(1e-12, h - l)

    # proximity: how close is price to the level now (tight = small stop)
    dist_atr = abs(c - level) / a
    proximity_score = _clamp01(1.0 - dist_atr / max(1e-9, entry_band_atr))

    # freshness: bars since last touch
    fresh_bars = (n - 1 - int(last_touch_idx)) if last_touch_idx is not None else max_age_bars
    freshness_score = _clamp01(1.0 - fresh_bars / max(1, max_age_bars))

    # strength: touches near an ideal count; too many -> level likely to break
    if touches <= 0:
        strength_score = 0.0
    elif touches <= ideal_touches:
        strength_score = _clamp01(touches / ideal_touches)
    else:
        strength_score = _clamp01(1.0 - (touches - ideal_touches) / max(1, max_touches - ideal_touches))

    # rejection wick on the retest bar (against the break direction)
    if side == "support":
        rejection_frac = (min(o, c) - l) / bar_rng          # lower wick = bounce
    else:
        rejection_frac = (h - max(o, c)) / bar_rng          # upper wick = fade
    rejection_score = _clamp01(rejection_frac / 0.5)         # 50% wick -> full score

    # volume confirmation
    base_vol = _mean([_f(r, VOL) for r in rows[-(vol_window + 1):-1]])
    cur_vol = _f(bar, VOL)
    if base_vol == base_vol and base_vol > 0 and cur_vol == cur_vol:
        volume_score = _clamp01((cur_vol / base_vol) / max(1e-9, vol_mult))
    else:
        volume_score = 0.0

    quality = (w[0] * freshness_score + w[1] * proximity_score + w[2] * strength_score
               + w[3] * rejection_score + w[4] * volume_score)

    near = dist_atr <= entry_band_atr
    fresh = fresh_bars <= max_age_bars
    has_rejection = rejection_frac > 0.0
    entry_ok = bool(quality >= min_quality and near and fresh and has_rejection)

    long_ok = bool(entry_ok and side == "support")
    short_ok = bool(entry_ok and side == "resistance")
    side_hint = "long" if long_ok else ("short" if short_ok else "none")

    if not near:
        reason = "too_far_from_level"
    elif not fresh:
        reason = "level_stale"
    elif not has_rejection:
        reason = "no_rejection_wick"
    elif quality < min_quality:
        reason = "low_quality"
    else:
        reason = "retest_ok"

    return RetestScore(
        ok=True, entry_ok=entry_ok, side=side_hint, long_ok=long_ok, short_ok=short_ok,
        level=float(level), dist_atr=dist_atr, freshness_bars=int(fresh_bars), touches=int(touches),
        quality=quality, freshness_score=freshness_score, proximity_score=proximity_score,
        strength_score=strength_score, rejection_score=rejection_score, volume_score=volume_score,
        reason=reason, extra={"atr": a},
    )


def best_retest(
    rows: Sequence[Sequence[float]],
    *,
    entry_band_atr: float = 0.30,
    max_age_bars: int = 48,
    min_touches: int = 2,
    **score_kw,
) -> RetestScore:
    """Find nearest fresh horizontal level within the entry band and score it.

    Picks the closer eligible side so the result stays one-directional.
    """
    n = len(rows)
    if n < 30:
        return _blank("insufficient_data")
    a = atr(rows)
    if not (a == a and a > 0):
        return _blank("no_atr")
    price = _f(rows[-1], CLOSE)
    last_idx = n - 1

    sup = horizontal_levels(rows, side="support", atr_value=a, min_touches=min_touches)
    res = horizontal_levels(rows, side="resistance", atr_value=a, min_touches=min_touches)

    cands = []  # (dist, side, level_dict)
    for lv in sup:
        if lv["level"] <= price and (price - lv["level"]) <= entry_band_atr * a:
            cands.append(((price - lv["level"]), "support", lv))
    for lv in res:
        if lv["level"] >= price and (lv["level"] - price) <= entry_band_atr * a:
            cands.append(((lv["level"] - price), "resistance", lv))
    if not cands:
        return _blank("no_level_in_band")

    _, side, lv = min(cands, key=lambda x: x[0])
    return score_retest(
        rows, lv["level"], side, atr_value=a, last_touch_idx=lv.get("last_idx"),
        touches=int(lv.get("touches", 0)), entry_band_atr=entry_band_atr,
        max_age_bars=max_age_bars, **score_kw,
    )
