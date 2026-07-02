"""Smart adaptive risk — wise, flexible, IN RAILS (never martingale).

Turns a base risk-per-trade into an adaptive one by multiplying it by scalars that
reflect the current situation, then capping hard. Every scalar can only REDUCE risk
from baseline in adverse conditions and restore toward (never above) baseline when
things are good:

  * regime_scalar   — regime_hmm: 0 in high_vol chaos, scaled by confidence otherwise;
  * health_scalar   — edge_monitor: healthy 1.0 / watch 0.75 / degraded 0.5 / halt 0.0;
  * drawdown_scalar — ANTI-MARTINGALE: cut risk as equity drawdown deepens (never raise);
  * vol_scalar      — position_sizing vol-target (down when ATR% is high).

final = base * regime * health * drawdown * vol, clamped to [0, hard_cap]. Pure stdlib.
Compose with regime_hmm.RegimeState + edge_monitor.HealthReport (or dicts).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


@dataclass
class RiskDecision:
    risk_pct: float                 # adaptive risk per trade (% of equity)
    base_pct: float
    regime_scalar: float
    health_scalar: float
    drawdown_scalar: float
    vol_scalar: float
    blocked: bool                   # risk forced to 0
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


_HEALTH = {"healthy": 1.0, "watch": 0.75, "degraded": 0.5, "halt": 0.0}


def smart_risk(
    base_risk_pct: float,
    *,
    regime: Any = None,             # regime_hmm.RegimeState or {dominant,confidence}
    health: Any = None,             # edge_monitor.HealthReport or {status}
    equity_drawdown_pct: float = 0.0,   # current live drawdown, % (>=0)
    vol_scalar: float = 1.0,
    max_drawdown_pct: float = 10.0,     # at this DD, risk cut to dd_floor
    dd_floor: float = 0.25,
    regime_block_conf: float = 0.35,
    hard_cap_pct: float = 1.0,
    min_live_pct: float = 0.02,
) -> RiskDecision:
    """Compute an adaptive, anti-martingale risk-per-trade in rails."""
    base = max(0.0, float(base_risk_pct))

    # regime: block chaos, scale by confidence otherwise
    dom = _get(regime, "dominant"); conf = float(_get(regime, "confidence", 0.0) or 0.0)
    if dom is None:
        regime_scalar = 1.0
    elif dom == "high_vol" and conf >= regime_block_conf:
        regime_scalar = 0.0
    else:
        regime_scalar = _clamp(conf / 0.5, 0.0, 1.0) if conf > 0 else 1.0

    # health
    status = _get(health, "status")
    health_scalar = _HEALTH.get(str(status), 1.0) if status is not None else 1.0

    # drawdown: ANTI-MARTINGALE — cut as DD deepens, never increase
    dd = max(0.0, float(equity_drawdown_pct))
    drawdown_scalar = _clamp(1.0 - dd / max(1e-9, max_drawdown_pct), dd_floor, 1.0)

    vs = _clamp(float(vol_scalar), 0.0, 1.0)

    risk = base * regime_scalar * health_scalar * drawdown_scalar * vs
    risk = min(risk, hard_cap_pct)
    blocked = False
    reason = "ok"
    if regime_scalar == 0.0:
        blocked, reason, risk = True, "blocked_high_vol", 0.0
    elif health_scalar == 0.0:
        blocked, reason, risk = True, "blocked_halt", 0.0
    elif risk < min_live_pct:
        blocked, reason, risk = True, f"below_min_{risk:.3f}", 0.0

    return RiskDecision(round(risk, 4), base, round(regime_scalar, 3), round(health_scalar, 3),
                        round(drawdown_scalar, 3), round(vs, 3), blocked, reason,
                        extra={"equity_drawdown_pct": dd})
