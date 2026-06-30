"""Unified range/chop filter for bounce & fade legs (crypto + forex/CFD).

Single source of truth that consolidates the previously-fragmented detectors:
  * forex.regime.is_ranging  -> 3-measure vote (Choppiness, VolatilityPercentile, ADX-proxy)
  * bot.market_context.classify_channel -> slope regime (flat/ascending/descending),
    position in channel (0=lower band, 1=upper band) and sloped bounds.
  * bot.market_context.horizontal_levels -> nearest horizontal S/R (level-aware bounce).

Why: ARF1/ARF2 ("pila"), ASB/ACB bounces, and forex range legs each rolled their
own range gate (classify_channel ~33% flat vs choppiness ~8% choppy -> 3-4x mismatch,
see reports/RANGE_DETECTOR_AUDIT_2026_06_30.md). This module gives every leg ONE
gate, plus an explicit LONG-ONLY / SHORT-ONLY side hint so sleeves stay one-directional:
  * long bounce  -> price near LOWER band/support  (long_ok)
  * short fade    -> price near UPPER band/resistance (short_ok)

Pure-stdlib glue (no numpy). Input is the canonical crypto row format
[ts, open, high, low, close, vol]; use `from_candles` to feed forex Candle lists.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.market_context import (
    classify_channel, horizontal_levels, atr,
    TS, OPEN, HIGH, LOW, CLOSE, VOL,
)

try:  # forex.regime is pure-stdlib; import is cheap
    from forex.regime import choppiness as _chop, volatility_percentile as _volp, adx_proxy as _adx
    from forex.types import Candle as _Candle
    _HAVE_FOREX = True
except Exception:  # pragma: no cover - defensive
    _HAVE_FOREX = False


@dataclass
class RangeState:
    ok: bool                       # data sufficient + decision made
    is_range: bool                 # market is ranging/choppy enough to fade-bounce
    regime: str                    # flat | ascending | descending | unknown
    pos_in_channel: float          # 0=at lower band, 1=at upper band, nan if unknown
    side_hint: str                 # "long" | "short" | "none"
    long_ok: bool                  # range AND price near lower band/support
    short_ok: bool                 # range AND price near upper band/resistance
    upper_now: float               # sloped resistance value at last bar
    lower_now: float               # sloped support value at last bar
    width_atr: float               # channel width in ATR
    nearest_support: float         # nearest horizontal support (nan if none)
    nearest_resistance: float      # nearest horizontal resistance (nan if none)
    ci: float                      # choppiness index
    vp: float                      # volatility percentile
    adx: float                     # adx proxy
    votes: int                     # how many of the 3 range-measures agreed
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _rows_to_candles(rows: Sequence[Sequence[float]]):
    return [_Candle(int(r[TS]), float(r[OPEN]), float(r[HIGH]), float(r[LOW]),
                    float(r[CLOSE]), float(r[VOL]) if len(r) > VOL else 0.0) for r in rows]


def from_candles(candles) -> List[list]:
    """Adapt a forex Candle list to canonical rows for range_state()."""
    return [[c.ts, c.o, c.h, c.l, c.c, getattr(c, "v", 0.0)] for c in candles]


def range_state(
    rows: Sequence[Sequence[float]],
    *,
    lookback: int = 60,
    ci_threshold: float = 58.0,
    vp_threshold: float = 40.0,
    adx_threshold: float = 25.0,
    require_all: bool = False,       # True = stricter "all 3 agree" anti-saw gate
    lower_zone: float = 0.30,        # pos<=lower_zone -> long bounce candidate
    upper_zone: float = 0.70,        # pos>=upper_zone -> short fade candidate
    allow_sloped: bool = True,       # accept ascending/descending channels too
    atr_period: int = 14,
) -> RangeState:
    """Single unified gate. Returns a RangeState with a long/short side hint.

    Range decision = (range-measure vote) AND (channel is flat, or sloped allowed).
    side_hint/long_ok/short_ok come from position inside the channel so a sleeve
    can stay strictly one-directional.
    """
    blank = RangeState(
        ok=False, is_range=False, regime="unknown", pos_in_channel=float("nan"),
        side_hint="none", long_ok=False, short_ok=False, upper_now=float("nan"),
        lower_now=float("nan"), width_atr=float("nan"), nearest_support=float("nan"),
        nearest_resistance=float("nan"), ci=float("nan"), vp=float("nan"),
        adx=float("nan"), votes=0, reason="insufficient_data",
    )
    n = len(rows)
    if n < max(lookback, 30):
        return blank

    a = atr(rows, atr_period)
    ch = classify_channel(rows, atr_value=a if (a == a and a > 0) else None, lookback=lookback)
    regime = ch.get("regime", "unknown")
    pos = ch.get("pos_in_channel", float("nan"))

    # 3-measure range vote (reuse forex.regime exactly; fallback = neutral)
    ci = vp = adx = float("nan")
    votes = 0
    if _HAVE_FOREX:
        cnds = _rows_to_candles(rows)
        i = len(cnds) - 1
        ci = _chop(cnds, i, 14)
        vp = _volp(cnds, i, atr_period, 100)
        adx = _adx(cnds, i, 14)
        sub = []
        if ci == ci:
            sub.append(ci > ci_threshold)
        if vp == vp:
            sub.append(vp < vp_threshold)
        if adx == adx:
            sub.append(adx < adx_threshold)
        votes = sum(1 for s in sub if s)
        if len(sub) < 2:
            range_vote = (regime == "flat")  # fall back to slope when measures thin
        elif require_all:
            range_vote = (votes == len(sub))
        else:
            range_vote = votes >= 2
    else:  # no forex.regime -> rely on slope classifier only
        range_vote = (regime == "flat")

    regime_ok = (regime == "flat") or (allow_sloped and regime in ("ascending", "descending"))
    is_range = bool(range_vote and regime_ok)

    # horizontal levels for level-aware bounce/fade
    nsup = nres = float("nan")
    if a == a and a > 0:
        try:
            price = float(rows[-1][CLOSE])
            sup_lv = horizontal_levels(rows, side="support", atr_value=a)
            res_lv = horizontal_levels(rows, side="resistance", atr_value=a)
            sups = [float(l["level"]) for l in sup_lv if float(l["level"]) < price]
            ress = [float(l["level"]) for l in res_lv if float(l["level"]) > price]
            if sups:
                nsup = max(sups)
            if ress:
                nres = min(ress)
        except Exception:
            pass

    long_ok = bool(is_range and pos == pos and pos <= lower_zone)
    short_ok = bool(is_range and pos == pos and pos >= upper_zone)
    if long_ok and not short_ok:
        side_hint = "long"
    elif short_ok and not long_ok:
        side_hint = "short"
    else:
        side_hint = "none"

    reason = "ok" if is_range else (
        "regime_not_range" if not regime_ok else "measures_say_trending")

    return RangeState(
        ok=True, is_range=is_range, regime=regime, pos_in_channel=pos,
        side_hint=side_hint, long_ok=long_ok, short_ok=short_ok,
        upper_now=ch.get("upper_now", float("nan")), lower_now=ch.get("lower_now", float("nan")),
        width_atr=ch.get("width_atr", float("nan")), nearest_support=nsup,
        nearest_resistance=nres, ci=ci, vp=vp, adx=adx, votes=votes, reason=reason,
        extra={"upper_r2": ch.get("upper_r2"), "lower_r2": ch.get("lower_r2"),
               "slope_atr": ch.get("slope_atr"), "require_all": require_all},
    )
