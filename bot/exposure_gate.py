"""Portfolio correlation / exposure gate — stop stacking the same bet.

Every leg is one-directional and sized to a fixed R, but three long alt sleeves at
once is really ONE big correlated long. This gate looks across OPEN positions and,
before a new trade, computes the CORRELATED cluster risk (same effective direction,
|corr| >= threshold) and either allows it, scales its risk down to fit the cluster
budget, or denies it. Opposite-direction correlated positions REDUCE the cluster
(a partial hedge), so the gate rewards genuine diversification.

Inputs are plain dicts so the live risk manager and backtests share one rule, and
the in-bot AI can read the decision (allow/scale/deny + cluster + reason) honestly.
Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _corr_key(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def correlation_from_prices(price_map: Dict[str, Sequence[float]]) -> Dict[Tuple[str, str], float]:
    """Pairwise return-correlation from aligned close series. Missing/short -> skip."""
    syms = [s for s, p in price_map.items() if p and len(p) >= 3]
    rets: Dict[str, List[float]] = {}
    for s in syms:
        p = list(price_map[s])
        rets[s] = [(p[i] / p[i - 1] - 1.0) for i in range(1, len(p)) if p[i - 1]]
    out: Dict[Tuple[str, str], float] = {}
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            a, b = syms[i], syms[j]
            xa, xb = rets[a], rets[b]
            n = min(len(xa), len(xb))
            if n < 2:
                continue
            xa, xb = xa[-n:], xb[-n:]
            ma, mb = sum(xa) / n, sum(xb) / n
            va = sum((x - ma) ** 2 for x in xa)
            vb = sum((x - mb) ** 2 for x in xb)
            if va <= 0 or vb <= 0:
                continue
            cov = sum((xa[k] - ma) * (xb[k] - mb) for k in range(n))
            out[_corr_key(a, b)] = cov / (va ** 0.5 * vb ** 0.5)
    return out


@dataclass
class ExposureDecision:
    ok: bool
    allow: bool
    scaled_risk_pct: float          # risk the gate permits (<= requested)
    requested_risk_pct: float
    cluster_risk_pct: float         # correlated same-direction risk incl. candidate
    correlated: List[str]           # open symbols in the candidate's cluster
    hedges: List[str]               # opposite-direction correlated open symbols
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def check_exposure(
    candidate: Dict[str, Any],                 # {"symbol","side","risk_pct"}
    open_positions: Sequence[Dict[str, Any]],  # [{"symbol","side","risk_pct"}, ...]
    correlations: Dict[Tuple[str, str], float],
    *,
    corr_threshold: float = 0.6,
    max_cluster_risk_pct: float = 1.5,
    allow_scale: bool = True,
    min_risk_pct: float = 0.05,
) -> ExposureDecision:
    """Decide allow / scale-down / deny for a new trade given open correlated risk."""
    sym = str(candidate.get("symbol", "")).upper()
    side = str(candidate.get("side", "")).lower()
    req = float(candidate.get("risk_pct", 0.0) or 0.0)
    if not sym or side not in ("long", "short") or req <= 0:
        return ExposureDecision(False, False, 0.0, req, 0.0, [], [], "bad_candidate")

    correlated: List[str] = []
    hedges: List[str] = []
    cluster = req
    for pos in open_positions:
        psym = str(pos.get("symbol", "")).upper()
        pside = str(pos.get("side", "")).lower()
        prisk = float(pos.get("risk_pct", 0.0) or 0.0)
        if psym == sym and not pside:  # malformed
            continue
        if psym == sym:
            c = 1.0                     # same symbol = perfectly correlated with itself
        else:
            c = correlations.get(_corr_key(sym, psym), 0.0)
        if abs(c) < corr_threshold:
            continue
        same_dir = (c > 0 and pside == side) or (c < 0 and pside != side)
        if same_dir:
            correlated.append(psym)
            cluster += prisk * abs(c)
        else:
            hedges.append(psym)
            cluster -= prisk * abs(c)   # opposite correlated position hedges the cluster

    cluster = max(0.0, cluster)
    if cluster <= max_cluster_risk_pct:
        return ExposureDecision(True, True, req, req, cluster, correlated, hedges,
                                "within_cluster_budget")

    # over budget: scale the candidate down to fit, or deny
    headroom = max_cluster_risk_pct - (cluster - req)
    if allow_scale and headroom >= min_risk_pct:
        return ExposureDecision(True, True, round(headroom, 6), req, max_cluster_risk_pct,
                                correlated, hedges, "scaled_to_cluster_budget")
    return ExposureDecision(True, False, 0.0, req, cluster, correlated, hedges,
                            "cluster_budget_exceeded")
