"""In-play volume universe scoring.

This module formalizes the owner's first manual step: before looking for a
level/retest, find coins where volume is coming in *right now* relative to the
coin's own baseline. It is intentionally standalone so it can be used by the
symbol router, research runners, or tests without touching live order logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Sequence


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _quote_volume(row: Sequence[Any]) -> float:
    """Estimate quote volume from a kline row.

    Expected row shape is `[ts, o, h, l, c, v, ...]`. Bybit kline volume can be
    base volume depending on the endpoint; multiplying by close gives a stable
    quote-volume proxy. If a caller has true turnover, it can pass it as index 6
    and this helper will prefer it when positive.
    """
    if len(row) > 6:
        turnover = _f(row[6], 0.0)
        if turnover > 0:
            return turnover
    close = _f(row[4], 0.0) if len(row) > 4 else 0.0
    vol = _f(row[5], 0.0) if len(row) > 5 else 0.0
    return max(0.0, close * vol)


def _close(row: Sequence[Any]) -> float:
    return _f(row[4], 0.0) if len(row) > 4 else 0.0


@dataclass(frozen=True)
class InplayVolumeScore:
    ok: bool
    score: float
    reason: str
    recent_quote_usd: float
    baseline_quote_usd: float
    inflow_mult: float
    inflow_z: float
    recent_return_pct: float


def score_inplay_volume(
    rows: Sequence[Sequence[Any]],
    *,
    recent_bars: int = 3,
    baseline_bars: int = 72,
    min_recent_quote_usd: float = 250_000.0,
    min_inflow_mult: float = 2.0,
    min_inflow_z: float = 2.0,
    max_abs_recent_return_pct: float = 18.0,
) -> InplayVolumeScore:
    """Score whether a symbol is currently in-play by relative volume inflow.

    The scorer is deliberately conservative:
    - recent quote volume must be liquid enough;
    - recent volume must exceed the symbol's own baseline by both multiplier and
      robust z-score;
    - extreme one-shot blow-offs can be rejected by return cap because those are
      usually late/chase setups, not controlled retests.
    """
    rb = max(1, int(recent_bars))
    bb = max(rb + 5, int(baseline_bars))
    need = rb + bb
    if len(rows) < need:
        return InplayVolumeScore(False, 0.0, "not_enough_rows", 0.0, 0.0, 0.0, 0.0, 0.0)

    sample = list(rows[-need:])
    baseline_rows = sample[:bb]
    recent_rows = sample[bb:]
    baseline_values = [_quote_volume(r) for r in baseline_rows]
    recent_values = [_quote_volume(r) for r in recent_rows]

    recent_quote = sum(recent_values)
    baseline_per_bar = median(baseline_values) if baseline_values else 0.0
    baseline_recent = baseline_per_bar * rb
    if baseline_recent <= 0:
        return InplayVolumeScore(False, 0.0, "baseline_invalid", recent_quote, 0.0, 0.0, 0.0, 0.0)

    inflow_mult = recent_quote / max(1e-12, baseline_recent)
    abs_devs = [abs(v - baseline_per_bar) for v in baseline_values]
    mad = median(abs_devs) if abs_devs else 0.0
    robust_sigma_recent = max(1e-12, 1.4826 * mad * (rb ** 0.5))
    inflow_z = (recent_quote - baseline_recent) / robust_sigma_recent

    first_close = _close(recent_rows[0])
    last_close = _close(recent_rows[-1])
    recent_ret_pct = 0.0 if first_close <= 0 else (last_close - first_close) / first_close * 100.0

    if recent_quote < min_recent_quote_usd:
        return InplayVolumeScore(False, 0.0, "recent_quote_too_low", recent_quote, baseline_recent, inflow_mult, inflow_z, recent_ret_pct)
    if inflow_mult < min_inflow_mult:
        return InplayVolumeScore(False, 0.0, "inflow_mult_low", recent_quote, baseline_recent, inflow_mult, inflow_z, recent_ret_pct)
    if inflow_z < min_inflow_z:
        return InplayVolumeScore(False, 0.0, "inflow_z_low", recent_quote, baseline_recent, inflow_mult, inflow_z, recent_ret_pct)
    if abs(recent_ret_pct) > max_abs_recent_return_pct:
        return InplayVolumeScore(False, 0.0, "recent_move_too_extreme", recent_quote, baseline_recent, inflow_mult, inflow_z, recent_ret_pct)

    mult_component = min(1.0, (inflow_mult - min_inflow_mult) / max(1.0, min_inflow_mult * 2.0))
    z_component = min(1.0, (inflow_z - min_inflow_z) / max(1.0, min_inflow_z * 2.0))
    liq_component = min(1.0, recent_quote / max(1.0, min_recent_quote_usd * 4.0))
    score = 0.45 * mult_component + 0.35 * z_component + 0.20 * liq_component
    return InplayVolumeScore(
        True,
        round(float(score), 6),
        "ok",
        recent_quote,
        baseline_recent,
        inflow_mult,
        inflow_z,
        recent_ret_pct,
    )
