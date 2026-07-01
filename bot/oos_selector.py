"""OOS-plateau selector — encode our anti-overfit selection discipline in code.

The recurring failure: picking the parameter set with the best IN-SAMPLE / single-window
PF, which turns out to be an overfit peak that dies live. This module scores candidate
configs by OUT-OF-SAMPLE STABILITY across independent walk-forward folds and *rejects
one-window heroes* automatically, so selection stops depending on human willpower.

A candidate = one parameter set with a list of per-fold OOS results. Each fold result
carries at least a profit metric (`net_r` preferred, else `pf`) and `trades`.

Robustness (higher = better), all from OUT-OF-SAMPLE folds only:
  * consistency — fraction of folds that are profitable (>= threshold);
  * central tendency — MEDIAN fold metric (robust to a single huge fold);
  * dispersion penalty — spread across folds hurts (unstable => not a plateau);
  * peak penalty — if the best fold dominates (max >> median) it's a hero, penalize/reject;
  * sample sufficiency — too few trades => untrustworthy.

Pure stdlib; deterministic; no lookahead concerns (operates on already-computed folds).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

_INF = float("inf")


def _median(xs: List[float]) -> float:
    ys = sorted(x for x in xs if x == x)
    n = len(ys)
    if n == 0:
        return float("nan")
    m = n // 2
    return ys[m] if n % 2 else (ys[m - 1] + ys[m]) / 2.0


def _mean(xs: List[float]) -> float:
    ys = [x for x in xs if x == x]
    return sum(ys) / len(ys) if ys else float("nan")


def _std(xs: List[float]) -> float:
    ys = [x for x in xs if x == x]
    if len(ys) < 2:
        return 0.0
    m = _mean(ys)
    return (sum((y - m) ** 2 for y in ys) / (len(ys) - 1)) ** 0.5


@dataclass
class Candidate:
    id: str
    passes: bool
    robustness: float            # composite score (higher = better)
    folds: int
    folds_positive: int
    frac_positive: float
    median_metric: float
    min_metric: float
    dispersion: float            # std across folds
    peak_ratio: float            # best_fold / median (hero detector)
    total_trades: int
    reason: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


def _fold_metric(fold: Dict[str, Any]) -> float:
    """Prefer net R (additive, honest); fall back to PF centered at 0 (pf-1)."""
    if "net_r" in fold and fold["net_r"] == fold["net_r"]:
        return float(fold["net_r"])
    pf = fold.get("pf")
    if pf is not None and pf == pf and pf != _INF:
        return float(pf) - 1.0        # >0 profitable, symmetric around break-even
    if pf == _INF:
        return 1.0                     # capped: inf PF (few wins, no losses) not rewarded
    return float("nan")


def evaluate_candidate(
    cand: Dict[str, Any],
    *,
    min_folds: int = 3,
    min_frac_positive: float = 0.75,
    min_trades_total: int = 40,
    min_trades_per_fold: int = 5,
    max_peak_ratio: float = 3.0,       # best fold may not exceed 3x the median
    dispersion_weight: float = 0.5,
) -> Candidate:
    """Grade one candidate by OOS stability; sets passes + robustness."""
    folds = cand.get("folds", []) or []
    metrics = [_fold_metric(f) for f in folds]
    metrics = [m for m in metrics if m == m]
    trades = [int(f.get("trades", 0)) for f in folds]
    total_trades = sum(trades)
    nf = len(metrics)

    base = Candidate(
        id=str(cand.get("id", "?")), passes=False, robustness=float("-inf"),
        folds=nf, folds_positive=0, frac_positive=0.0, median_metric=float("nan"),
        min_metric=float("nan"), dispersion=float("nan"), peak_ratio=float("nan"),
        total_trades=total_trades, params=cand.get("params", {}),
    )
    if nf < min_folds:
        base.reason = f"too_few_folds_{nf}"
        return base

    pos = sum(1 for m in metrics if m > 0)
    frac_pos = pos / nf
    med = _median(metrics)
    mn = min(metrics)
    disp = _std(metrics)
    best = max(metrics)
    peak_ratio = (best / med) if (med > 0) else _INF

    base.folds_positive = pos
    base.frac_positive = frac_pos
    base.median_metric = med
    base.min_metric = mn
    base.dispersion = disp
    base.peak_ratio = peak_ratio

    # robustness: reward median, penalize dispersion; only meaningful if median>0
    robustness = med - dispersion_weight * disp
    base.robustness = robustness

    # gates
    if total_trades < min_trades_total:
        base.reason = f"insufficient_trades_{total_trades}"
        return base
    if min(trades) < min_trades_per_fold:
        base.reason = f"thin_fold_{min(trades)}"
        return base
    if frac_pos < min_frac_positive:
        base.reason = f"unstable_frac_pos_{frac_pos:.2f}"
        return base
    if med <= 0:
        base.reason = "median_not_profitable"
        return base
    if peak_ratio > max_peak_ratio:
        base.reason = f"one_window_hero_peak_{peak_ratio:.1f}"
        return base

    base.passes = True
    base.reason = "robust_plateau"
    return base


def select_robust(candidates: Sequence[Dict[str, Any]], **kw) -> List[Candidate]:
    """Evaluate all candidates; return the PASSING ones sorted best-first.

    Sorting key rewards stability: (frac_positive, robustness, median) descending.
    """
    graded = [evaluate_candidate(c, **kw) for c in candidates]
    passing = [g for g in graded if g.passes]
    passing.sort(key=lambda g: (g.frac_positive, g.robustness, g.median_metric), reverse=True)
    return passing


def rank_all(candidates: Sequence[Dict[str, Any]], **kw) -> List[Candidate]:
    """Grade and rank ALL candidates (passing first), for inspection/AI review."""
    graded = [evaluate_candidate(c, **kw) for c in candidates]
    graded.sort(key=lambda g: (g.passes, g.frac_positive, g.robustness), reverse=True)
    return graded
