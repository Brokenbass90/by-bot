"""Level memory — does THIS symbol respect ITS levels? (owner idea, 2026-07-07)

Level legs (bounce/retest/inplay/failed-breakout) currently treat every level as
equally trustworthy. Reality: some symbols bounce off their levels for months,
others slice through them like butter. This module gives levels a MEMORY:

  for each historical touch of a level, classify the reaction —
    BOUNCE : price rejects and moves away without closing beyond;
    SWEEP  : price pierces beyond, then reclaims back within a few bars (закол);
    BREAK  : price closes beyond and stays there.

  respect_score = (bounces + 0.5 * sweeps) / touches   in [0..1]

Support and resistance reactions must not be mixed.  ``approach`` can keep all
touches (the backward-compatible default), only touches approached from above
(support), or only touches approached from below (resistance).

Intended use (MTF): levels drawn on H1, execution on M5; a leg consults the H1
respect history BEFORE leaning on a level. High respect -> full confidence;
low respect -> skip or downweight (the symbol "не чувствует" its levels).
Also a natural future meta-labeling feature.

Causal by construction: reactions are classified strictly on bars AFTER each
touch, and any consumer should call it on history rows[:now] only.
Contract: rows = [[ts, o, h, l, c, v], ...] ascending. Dependency-light.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from bot.market_context import atr, HIGH, LOW, CLOSE

__all__ = ["LevelStats", "level_respect", "symbol_respect"]


@dataclass
class LevelStats:
    level: float
    approach: str = "both"
    touches: int = 0
    bounces: int = 0
    sweeps: int = 0
    breaks: int = 0
    unresolved: int = 0            # touch too close to the end to classify
    respect_score: float = float("nan")
    touch_indices: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level, "approach": self.approach,
            "touches": self.touches, "bounces": self.bounces,
            "sweeps": self.sweeps, "breaks": self.breaks, "unresolved": self.unresolved,
            "respect_score": self.respect_score,
        }


def _f(row: Sequence[float], idx: int) -> float:
    try:
        return float(row[idx])
    except Exception:
        return float("nan")


def level_respect(
    rows: Sequence[Sequence[float]],
    level: float,
    *,
    approach: str = "both",          # both | from_above (support) | from_below (resistance)
    touch_tol_atr: float = 0.25,    # bar counts as a touch if it comes this close
    pierce_max_atr: float = 0.75,   # sweep may pierce at most this far beyond
    confirm_bars: int = 6,          # bars to resolve the reaction
    move_away_atr: float = 1.0,     # bounce must travel this far from the level
    cooldown_bars: int = 3,         # collapse a cluster of bars into one touch
    atr_period: int = 14,
    min_history: int = 30,
) -> LevelStats:
    """Classify historical touches of ``level`` (causal per touch).

    ``approach="from_above"`` rates support reactions only; ``from_below``
    rates resistance reactions only.  ``both`` preserves the original API.
    """
    approach = str(approach or "both").strip().lower()
    if approach not in {"both", "from_above", "from_below"}:
        raise ValueError("approach must be both, from_above, or from_below")
    stats = LevelStats(level=float(level), approach=approach)
    n = len(rows)
    if n < max(min_history, atr_period + 3) or not (level == level and level > 0):
        return stats

    i = atr_period + 2
    while i < n - 1:
        a = atr(rows[: i + 1], atr_period)
        if not (a == a and a > 0):
            i += 1
            continue
        hi, lo, close_i = _f(rows[i], HIGH), _f(rows[i], LOW), _f(rows[i], CLOSE)
        tol = touch_tol_atr * a
        touched = (lo - tol) <= level <= (hi + tol)
        if not touched:
            i += 1
            continue

        # side of approach from the PRIOR bar close: a breaking touch bar already
        # closes beyond the level, so its own close cannot define the side.
        prev_close = _f(rows[i - 1], CLOSE) if i > 0 else close_i
        from_above = prev_close >= level
        if (
            (approach == "from_above" and not from_above)
            or (approach == "from_below" and from_above)
        ):
            # Ignore the whole local touch cluster, not each bar in it.  This
            # keeps side-filtered counts comparable with the legacy aggregate.
            i += max(1, cooldown_bars + 1)
            continue
        stats.touches += 1
        stats.touch_indices.append(i)

        end = min(n - 1, i + confirm_bars)
        if end <= i:
            stats.unresolved += 1
            break

        max_pierce = 0.0
        had_beyond_close = False
        reclaimed_after_beyond = False
        deep_break = False
        bounced = False
        for j in range(i, end + 1):
            hj, lj, cj = _f(rows[j], HIGH), _f(rows[j], LOW), _f(rows[j], CLOSE)
            pierce = (level - lj) if from_above else (hj - level)
            max_pierce = max(max_pierce, pierce)
            beyond_close = (cj < level - 0.1 * a) if from_above else (cj > level + 0.1 * a)
            if beyond_close:
                had_beyond_close = True
                if pierce > pierce_max_atr * a:
                    # Preserve the legacy hard-break rule: a deep close through
                    # the level resolves immediately as a break, rather than a
                    # later unrelated rebound rewriting it as a sweep.
                    deep_break = True
                    break
            elif had_beyond_close:
                back_on_original_side = (cj >= level) if from_above else (cj <= level)
                reclaimed_after_beyond = reclaimed_after_beyond or back_on_original_side
            away = (cj - level) if from_above else (level - cj)
            if j > i and away >= move_away_atr * a:
                bounced = True
                break

        final_close = _f(rows[j], CLOSE)
        final_beyond = (
            (final_close < level - 0.1 * a)
            if from_above
            else (final_close > level + 0.1 * a)
        )
        final_on_original_side = (final_close >= level) if from_above else (final_close <= level)

        # A close beyond the level that remains there is a BREAK even when the
        # penetration is shallow.  The old implementation required >0.75 ATR
        # penetration, then mislabeled a sustained 0.1..0.75 ATR break as a
        # bounce merely because max_pierce was below pierce_max_atr.
        if deep_break:
            stats.breaks += 1
        elif had_beyond_close and final_beyond and not reclaimed_after_beyond:
            stats.breaks += 1
        elif had_beyond_close and reclaimed_after_beyond:
            stats.sweeps += 1
        elif bounced and max_pierce > 0.05 * a:
            stats.sweeps += 1          # pierced first, then reclaimed and left
        elif bounced:
            stats.bounces += 1
        elif (
            j >= end
            and not had_beyond_close
            and final_on_original_side
            and max_pierce <= pierce_max_atr * a
        ):
            stats.bounces += 1         # held the level through the window
        else:
            stats.unresolved += 1

        i = max(i + 1, j) + cooldown_bars

    resolved = stats.bounces + stats.sweeps + stats.breaks
    if resolved > 0:
        stats.respect_score = round((stats.bounces + 0.5 * stats.sweeps) / resolved, 4)
    return stats


def symbol_respect(
    rows: Sequence[Sequence[float]],
    levels: Sequence[float],
    *,
    min_touches_per_level: int = 3,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Aggregate respect across a symbol's levels: does the coin feel levels at all?

    Returns {symbol_respect, rated_levels, per_level}. Levels with fewer than
    min_touches_per_level resolved touches are reported but excluded from the
    aggregate (no verdicts on tiny N — the house rule applies here too)."""
    per_level: List[Dict[str, Any]] = []
    scores: List[float] = []
    weights: List[int] = []
    for lv in levels:
        st = level_respect(rows, float(lv), **kwargs)
        d = st.to_dict()
        resolved = st.bounces + st.sweeps + st.breaks
        d["rated"] = resolved >= int(min_touches_per_level)
        per_level.append(d)
        if d["rated"] and st.respect_score == st.respect_score:
            scores.append(st.respect_score)
            weights.append(resolved)
    agg = (sum(s * w for s, w in zip(scores, weights)) / sum(weights)) if weights else float("nan")
    return {
        "symbol_respect": round(agg, 4) if agg == agg else float("nan"),
        "rated_levels": len(scores),
        "per_level": per_level,
    }
