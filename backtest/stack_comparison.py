"""Stack comparison — does the control-plane (обвязка) HELP or HURT a strategy?

The double test the owner asked for: run a strategy's trades (a) BARE and (b)
through the control-plane filters (regime gate, per-sleeve slot cap), then
compare. If the stack makes a strategy worse (e.g. slot-starvation dropped
ASB1's good trades), that's a control-plane bug to fix — not a strategy to kill.

Pure / deterministic — operates on a list of trade dicts, NOT a data replay, so
it's fast and testable, and works on offline backtest trades OR real server
trades (feed it the journal). Each trade: {entry_ts, exit_ts, R, regime}.

Verdict: compares expectancy-R and profit-factor bare vs stacked.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional


def _stats(rs: List[float]) -> Dict[str, float]:
    n = len(rs)
    if n == 0:
        return {"trades": 0, "expectancy_R": 0.0, "profit_factor": 0.0, "win_pct": 0.0}
    wins = [r for r in rs if r > 0]
    gp = sum(wins)
    gl = -sum(r for r in rs if r <= 0)
    pf = (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0)
    return {
        "trades": n,
        "expectancy_R": round(sum(rs) / n, 3),
        "profit_factor": (round(pf, 2) if pf != float("inf") else "inf"),
        "win_pct": round(100.0 * len(wins) / n, 1),
    }


def _slot_filter(trades: List[dict], max_concurrent: int) -> List[dict]:
    """Drop trades that would exceed max_concurrent open positions (FIFO by entry)."""
    kept, open_until = [], []
    for t in sorted(trades, key=lambda x: x["entry_ts"]):
        open_until = [u for u in open_until if u > t["entry_ts"]]
        if len(open_until) < max_concurrent:
            kept.append(t)
            open_until.append(t.get("exit_ts", t["entry_ts"]))
    return kept


def compare(
    trades: List[dict],
    *,
    regime_ok: Optional[Callable[[str], bool]] = None,
    max_concurrent: Optional[int] = None,
    risk_mult: float = 1.0,
) -> Dict[str, object]:
    """Return bare vs control-plane-filtered stats + a help/hurt verdict."""
    bare = [float(t["R"]) for t in trades]
    stacked_trades = trades
    if regime_ok is not None:
        stacked_trades = [t for t in stacked_trades if regime_ok(t.get("regime", ""))]
    if max_concurrent is not None:
        stacked_trades = _slot_filter(stacked_trades, max_concurrent)
    stacked = [float(t["R"]) * risk_mult for t in stacked_trades]

    s_bare, s_stack = _stats(bare), _stats(stacked)
    be, se = s_bare["expectancy_R"], s_stack["expectancy_R"]
    if s_stack["trades"] == 0:
        verdict = "STACK BLOCKS ALL — control-plane too restrictive"
    elif se > be + 0.02:
        verdict = "control-plane HELPS"
    elif se < be - 0.02:
        verdict = "control-plane HURTS (fix obвязку, not strategy)"
    else:
        verdict = "neutral"
    return {"bare": s_bare, "stacked": s_stack, "dropped": len(trades) - s_stack["trades"],
            "verdict": verdict}


if __name__ == "__main__":
    demo = [
        {"entry_ts": 1, "exit_ts": 5, "R": 2.5, "regime": "bull_trend"},
        {"entry_ts": 2, "exit_ts": 4, "R": -1.0, "regime": "bear_chop"},
        {"entry_ts": 3, "exit_ts": 9, "R": 3.0, "regime": "bull_trend"},
        {"entry_ts": 4, "exit_ts": 6, "R": -1.0, "regime": "bear_chop"},
    ]
    res = compare(demo, regime_ok=lambda r: "bull" in r, max_concurrent=2)
    import json
    print(json.dumps(res, indent=2, ensure_ascii=False))
