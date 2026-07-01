"""HMM-lite market regime — sticky probabilistic state + a trade gate.

A full HMM needs training; this is a lightweight, deterministic stand-in that emits
PROBABILITIES over regimes from observable features (trend vs ATR, volatility
percentile, choppiness) and applies STICKY smoothing (the Markov idea: regimes
persist, so blend with the prior estimate to avoid flip-flopping). Practical value
(per 2025 practice): disallow / down-size trades in bad regimes -> higher Sharpe.

States: bull | bear | range | high_vol. Feeds sizing (down-weight low-confidence)
and a gate (block trading in high_vol chaos). Generalizes classify_channel + elder.
Row [ts,o,h,l,c,v]. Pure stdlib + bot.market_context.atr.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from bot.market_context import atr, CLOSE, HIGH, LOW

STATES = ("bull", "bear", "range", "high_vol")


def _col(rows, i):
    return [float(r[i]) for r in rows]


def _ema(values: List[float], period: int) -> float:
    if not values:
        return float("nan")
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def _vol_percentile(rows, atr_period=14, lookback=100) -> float:
    closes = _col(rows, CLOSE)
    if len(closes) < atr_period + lookback + 2:
        # degrade: percentile of current atr vs available window
        lookback = max(10, len(closes) - atr_period - 2)
    cur = atr(rows[-atr_period - 2:]) if len(rows) > atr_period + 2 else atr(rows)
    hist = []
    step = max(1, lookback // 20)
    for k in range(len(rows) - lookback, len(rows), step):
        if k < atr_period + 1:
            continue
        a = atr(rows[k - atr_period - 1:k + 1])
        if a == a and a > 0:
            hist.append(a)
    if len(hist) < 3 or not (cur == cur):
        return 50.0
    return 100.0 * sum(1 for x in hist if x < cur) / len(hist)


@dataclass
class RegimeState:
    ok: bool
    probs: Dict[str, float]
    dominant: str
    confidence: float
    trend_norm: float
    vol_pctile: float
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def regime_probs(
    rows: Sequence[Sequence[float]],
    *,
    prior: Optional[Dict[str, float]] = None,
    ema_fast: int = 20,
    ema_slow: int = 50,
    stickiness: float = 0.6,          # weight on the prior estimate (Markov persistence)
    atr_period: int = 14,
) -> RegimeState:
    """Estimate sticky regime probabilities from observable features."""
    n = len(rows)
    if n < max(ema_slow, 30):
        return RegimeState(False, {s: 0.25 for s in STATES}, "unknown", 0.0,
                           float("nan"), float("nan"), "insufficient_data")
    a = atr(rows, atr_period)
    closes = _col(rows, CLOSE)
    ef, es = _ema(closes[-ema_slow * 3:], ema_fast), _ema(closes[-ema_slow * 3:], ema_slow)
    price = closes[-1]
    trend_norm = ((ef - es) / a) if (a == a and a > 0) else 0.0
    vp = _vol_percentile(rows, atr_period)

    t = math.tanh(trend_norm)                    # -1..1
    v_high = max(0.0, min(1.0, (vp - 70.0) / 30.0))
    calm = 1.0 - v_high
    raw = {
        "bull": max(0.0, t) * calm,
        "bear": max(0.0, -t) * calm,
        "range": (1.0 - abs(t)) * calm,
        "high_vol": v_high,
    }
    tot = sum(raw.values()) or 1.0
    obs = {s: raw[s] / tot for s in STATES}

    pri = prior if prior and abs(sum(prior.values()) - 1.0) < 0.01 else {s: 0.25 for s in STATES}
    probs = {s: stickiness * pri.get(s, 0.25) + (1 - stickiness) * obs[s] for s in STATES}
    z = sum(probs.values()) or 1.0
    probs = {s: probs[s] / z for s in STATES}

    dominant = max(probs, key=probs.get)
    conf = probs[dominant]
    return RegimeState(True, {s: round(probs[s], 4) for s in STATES}, dominant, round(conf, 4),
                       round(trend_norm, 4), round(vp, 1), "ok")


def regime_gate(
    state: RegimeState,
    *,
    block_states: Sequence[str] = ("high_vol",),
    min_confidence: float = 0.35,
) -> Dict[str, Any]:
    """Allow trading unless a blocked regime dominates with enough confidence."""
    if not state.ok:
        return {"allow": True, "reason": "no_regime_info", "risk_scalar": 1.0}
    if state.dominant in block_states and state.confidence >= min_confidence:
        return {"allow": False, "reason": f"blocked_regime_{state.dominant}", "risk_scalar": 0.0}
    # down-weight risk when regime is uncertain (low confidence)
    risk_scalar = round(min(1.0, state.confidence / 0.5), 3)
    return {"allow": True, "reason": f"regime_{state.dominant}", "risk_scalar": risk_scalar}
