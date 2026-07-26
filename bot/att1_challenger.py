"""Behavior-neutral ATT1 challenger classification.

The challenger never changes the baseline signal.  It labels an already
generated ATT1 signal so forward evidence can compare the exact same stream.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


_SLOPE = re.compile(r"(?:^|\s)slope=(-?\d+(?:\.\d+)?)%/d(?:\s|$)")
_RSI = re.compile(r"(?:^|\s)rsi=(-?\d+(?:\.\d+)?)(?:\s|$)")


@dataclass(frozen=True)
class Att1ChallengerDecision:
    challenger_id: str
    accepted: bool
    reason: str
    side: str
    slope_pct_day: float | None
    rsi: float | None

    def as_dict(self) -> dict:
        return asdict(self)


def classify_descending_rsi_50_70(
    side: str,
    signal_reason: str,
) -> Att1ChallengerDecision:
    """Classify the preregistered short-side meta-filter.

    Frozen rule from the July ATT1 entry gate:
      short AND slope <= -0.05 pct/day AND 50 <= RSI <= 70.
    """
    normalized_side = str(side or "").strip().lower()
    text = str(signal_reason or "")
    slope_match = _SLOPE.search(text)
    rsi_match = _RSI.search(text)
    slope = float(slope_match.group(1)) if slope_match else None
    rsi = float(rsi_match.group(1)) if rsi_match else None
    if slope is None or rsi is None:
        reason = "missing_entry_features"
        accepted = False
    elif normalized_side != "short":
        reason = "short_only"
        accepted = False
    elif slope > -0.05:
        reason = "slope_not_descending"
        accepted = False
    elif not 50.0 <= rsi <= 70.0:
        reason = "rsi_outside_50_70"
        accepted = False
    else:
        reason = "accepted"
        accepted = True
    return Att1ChallengerDecision(
        challenger_id="att1_desc_rsi50_70_shadow_v1",
        accepted=accepted,
        reason=reason,
        side=normalized_side,
        slope_pct_day=slope,
        rsi=rsi,
    )
