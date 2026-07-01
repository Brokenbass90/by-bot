"""Edge-decay monitor — keep sleeves honest in production for YEARS, not weeks.

The long-run killer isn't a bad backtest — it's a real edge quietly rotting live
(crowding, regime shift, rising costs) while it keeps bleeding. This governor
compares each sleeve's LIVE realized performance against its backtest baseline and
raises a health status the risk manager / strategy_breaker / AI can act on:

  healthy  — live expectancy in line with baseline;
  watch    — too few trades to judge, or mild slippage vs baseline;
  degraded — live expectancy well below baseline over enough trades -> throttle;
  halt     — drawdown breach or persistent negative expectancy -> stop the sleeve.

Reads R-multiples (from decision_bus outcomes). Pure stdlib. Nothing here creates
edge; it PROTECTS realized edge from silently decaying.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


def _mean(xs: List[float]) -> float:
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float("nan")


def _max_drawdown_R(r_list: Sequence[float]) -> float:
    """Peak-to-trough drawdown of the cumulative R curve (positive number)."""
    peak = 0.0
    cum = 0.0
    dd = 0.0
    for r in r_list:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return dd


def _worst_streak(r_list: Sequence[float]) -> int:
    worst = cur = 0
    for r in r_list:
        if r < 0:
            cur += 1
            worst = max(worst, cur)
        else:
            cur = 0
    return worst


@dataclass
class HealthReport:
    sleeve: str
    status: str                  # healthy | watch | degraded | halt
    n: int
    live_expectancy_R: float
    baseline_expectancy_R: float
    ratio: float                 # live / baseline (nan if baseline<=0)
    win_rate: float
    drawdown_R: float
    worst_losing_streak: int
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def assess_sleeve(
    r_multiples: Sequence[float],
    *,
    sleeve: str = "sleeve",
    baseline_expectancy_R: float = 0.0,
    min_trades: int = 20,
    decay_ratio: float = 0.5,        # degraded if live < decay_ratio * baseline
    max_dd_R: float = 6.0,           # halt if drawdown exceeds this
    max_losing_streak: int = 8,
) -> HealthReport:
    """Grade one sleeve's live health vs its backtest baseline."""
    rs = [float(r) for r in r_multiples if r == r]
    n = len(rs)
    live_exp = _mean(rs) if n else float("nan")
    wr = (sum(1 for r in rs if r > 0) / n) if n else float("nan")
    dd = _max_drawdown_R(rs)
    streak = _worst_streak(rs)
    ratio = (live_exp / baseline_expectancy_R) if baseline_expectancy_R > 0 else float("nan")

    base = HealthReport(
        sleeve=sleeve, status="watch", n=n, live_expectancy_R=live_exp,
        baseline_expectancy_R=baseline_expectancy_R, ratio=ratio, win_rate=wr,
        drawdown_R=dd, worst_losing_streak=streak,
    )

    # halt conditions take precedence (protect capital)
    if dd >= max_dd_R:
        base.status = "halt"; base.reason = f"drawdown_breach_{dd:.1f}R"
        return base
    if n >= min_trades and live_exp < 0:
        base.status = "halt"; base.reason = "negative_expectancy_live"
        return base
    if streak >= max_losing_streak:
        base.status = "halt"; base.reason = f"losing_streak_{streak}"
        return base

    if n < min_trades:
        base.status = "watch"; base.reason = f"insufficient_trades_{n}"
        return base
    if baseline_expectancy_R > 0 and live_exp < decay_ratio * baseline_expectancy_R:
        base.status = "degraded"; base.reason = f"edge_decay_ratio_{ratio:.2f}"
        return base
    base.status = "healthy"; base.reason = "in_line_with_baseline"
    return base


def assess_all(
    records: Sequence[Dict[str, Any]],
    baselines: Optional[Dict[str, float]] = None,
    **kw,
) -> Dict[str, HealthReport]:
    """Group decision_bus records by strategy and grade each sleeve's live health."""
    baselines = baselines or {}
    by_sleeve: Dict[str, List[float]] = {}
    for r in records:
        if r.get("decision") != "enter":
            continue
        oc = r.get("outcome") or {}
        if not oc.get("filled"):
            continue
        rm = oc.get("r_multiple")
        if rm is None or rm != rm:
            continue
        by_sleeve.setdefault(str(r.get("strategy", "?")), []).append(float(rm))
    out: Dict[str, HealthReport] = {}
    for sleeve, rs in by_sleeve.items():
        out[sleeve] = assess_sleeve(rs, sleeve=sleeve,
                                    baseline_expectancy_R=baselines.get(sleeve, 0.0), **kw)
    return out
