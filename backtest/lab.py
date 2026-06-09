"""Backtest Lab — flexible scenario orchestration + honest comparison (Opus 2026-06-08).

Sits ON TOP of the existing engine (backtest/engine.py, run_portfolio.py) — does
NOT replace it. Lets you define and compare arbitrary SCENARIOS:
  - any arm / any strategy, alone or combined;
  - supporting systems (regime orchestrator, allocator, AI gate) ON or OFF;
  - any window, fees, slippage, price jitter, walk-forward.

Then produces ONE comparable honest report per scenario and a ranked comparison
plus ABLATION (leave-one-out: marginal contribution of each strategy/component).

Design:
  - The actual execution is a pluggable `runner(scenario) -> RunResult` callable.
    Real runner = adapter to run_portfolio.py (needs data/network -> Codex/server).
    A stub runner is used for offline tests of the framework itself.
  - Metrics reuse backtest/robustness.py (sortino, geometric mean) for consistency.

Pure-stdlib framework; the metric/compare/ablation logic is unit-tested offline.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

try:
    from backtest.robustness import sortino_ratio, geometric_mean_return
except Exception:  # allow standalone import in tests
    from robustness import sortino_ratio, geometric_mean_return  # type: ignore


@dataclass
class Scenario:
    name: str
    strategies: List[str] = field(default_factory=list)   # [] = whatever runner defaults to
    components: Dict[str, bool] = field(default_factory=lambda: {
        "regime_orchestrator": True, "allocator": True, "ai_gate": False,
    })
    symbols: List[str] = field(default_factory=list)
    start: str = ""           # YYYY-MM-DD
    end: str = ""
    fee_bps: float = 6.0
    slippage_bps: float = 2.0
    jitter_pct: float = 0.0   # >0 -> robustness perturbation
    walk_forward: Optional[Dict[str, int]] = None  # {"is_days":90,"oos_days":30}
    risk_pct: float = 1.0


@dataclass
class RunResult:
    """What a runner returns. trades: list of {'pnl': float, 'fees'?: float,
    'return_pct'?: float}. equity_curve: list[float] (optional)."""
    trades: List[Dict[str, float]]
    equity_curve: List[float] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


def _max_drawdown_pct(equity: Sequence[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    mdd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak * 100.0)
    return mdd


def report_from_result(res: RunResult, starting_equity: float = 100.0) -> Dict[str, Any]:
    """Unified honest report for one scenario. Consistent across all scenarios."""
    trades = res.trades or []
    n = len(trades)
    pnls = [float(t.get("pnl", 0.0)) for t in trades]
    fees = sum(float(t.get("fees", 0.0)) for t in trades)
    rets = [float(t["return_pct"]) for t in trades if t.get("return_pct") is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    net = sum(pnls)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (math.inf if gross_win > 0 else 0.0)
    # equity curve: use provided, else build from cumulative pnl
    eq = list(res.equity_curve) if res.equity_curve else None
    if eq is None:
        eq = [starting_equity]
        for p in pnls:
            eq.append(eq[-1] + p)
    return {
        "scenario": res.meta.get("name", ""),
        "trades": n,
        "net_pnl": round(net, 4),
        "total_fees": round(fees, 4),
        "fee_drag_pct_of_gross": round((fees / gross_win * 100.0), 2) if gross_win > 0 else None,
        "win_rate": round(len(wins) / n * 100.0, 2) if n else 0.0,
        "profit_factor": round(pf, 4) if math.isfinite(pf) else "inf",
        "avg_win": round(gross_win / len(wins), 4) if wins else 0.0,
        "avg_loss": round(gross_loss / len(losses), 4) if losses else 0.0,
        "expectancy": round(net / n, 4) if n else 0.0,
        "max_drawdown_pct": round(_max_drawdown_pct(eq), 2),
        "sortino": round(sortino_ratio(rets), 4) if rets else None,
        "geo_mean_return": round(geometric_mean_return(rets), 6) if rets else None,
    }


def run_scenarios(scenarios: Sequence[Scenario], runner: Callable[[Scenario], RunResult]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for sc in scenarios:
        res = runner(sc)
        res.meta.setdefault("name", sc.name)
        out[sc.name] = report_from_result(res)
    return out


def compare(reports: Dict[str, Dict[str, Any]], key: str = "profit_factor") -> List[Dict[str, Any]]:
    """Rank scenarios by a metric (desc). 'inf' sorts highest."""
    def _val(r):
        v = r.get(key)
        if v == "inf":
            return math.inf
        return float(v) if isinstance(v, (int, float)) else -math.inf
    return sorted(reports.values(), key=_val, reverse=True)


def ablation(reports: Dict[str, Dict[str, Any]], full_key: str = "FULL", metric: str = "net_pnl") -> Dict[str, Any]:
    """Given a FULL report and 'minus_<component>' reports, compute marginal
    contribution = FULL.metric - minus.metric. Positive => that component HELPS.
    """
    if full_key not in reports:
        return {"error": f"no '{full_key}' scenario"}
    full_val = reports[full_key].get(metric)
    full_val = float(full_val) if isinstance(full_val, (int, float)) else 0.0
    contrib = {}
    for name, rep in reports.items():
        if not name.startswith("minus_"):
            continue
        comp = name[len("minus_"):]
        v = rep.get(metric)
        v = float(v) if isinstance(v, (int, float)) else 0.0
        contrib[comp] = round(full_val - v, 4)  # how much removing it COSTS
    return {"metric": metric, "full": round(full_val, 4),
            "marginal_contribution": dict(sorted(contrib.items(), key=lambda kv: kv[1], reverse=True))}
