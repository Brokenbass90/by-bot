"""Promotion gate — objective GO/NO-GO for moving a candidate to a live canary.

The capstone of the validation pipeline. Turns the scattered §D launch criteria
into ONE auditable decision so nobody promotes a strategy/coin to live risk on a
hunch. Feed it a candidate's walk-forward result (+ optional stack-comparison and
trade count); it returns go=True only if EVERY criterion passes.

Criteria (conservative, from CLAUDE_HANDOFF §D):
  * windows_with_trades >= min_windows           (enough disjoint OOS evidence)
  * positive_windows / windows >= min_pos_frac   (consistency, default 0.75 = 3/4)
  * profit_factor > min_pf  AFTER fees           (real edge net of costs)
  * expectancy_R >= min_expectancy               (positive per-trade edge)
  * trades >= min_trades                         (statistically meaningful)
  * stack_verdict not in {HURTS, BLOCKS ALL}     (control-plane doesn't kill it)

Pure / testable / additive. Use after auto_pick_wf + stack_comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class GateThresholds:
    min_windows: int = 3
    min_pos_frac: float = 0.75
    min_pf: float = 1.0
    min_expectancy: float = 0.0
    min_trades: int = 30   # crypto: 20 too few given outliers (reviewer 2026-06-16)


@dataclass
class GateResult:
    go: bool
    passed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)


def _to_float(v) -> Optional[float]:
    try:
        if v == "inf":
            return float("inf")
        return float(v)
    except (TypeError, ValueError):
        return None


def evaluate(candidate: dict, thr: Optional[GateThresholds] = None) -> GateResult:
    """candidate keys: windows_with_trades, positive_windows, profit_factor,
    expectancy_R, trades, stack_verdict (optional)."""
    t = thr or GateThresholds()
    passed: List[str] = []
    failed: List[str] = []

    nwin = int(candidate.get("windows_with_trades", 0) or 0)
    pos = int(candidate.get("positive_windows", 0) or 0)
    pf = _to_float(candidate.get("profit_factor"))
    exp = _to_float(candidate.get("expectancy_R"))
    trades = int(candidate.get("trades", 0) or 0)
    stack = str(candidate.get("stack_verdict", "") or "")

    def chk(ok: bool, msg: str):
        (passed if ok else failed).append(msg)

    chk(nwin >= t.min_windows, f"windows_with_trades {nwin} >= {t.min_windows}")
    frac = (pos / nwin) if nwin > 0 else 0.0
    chk(nwin > 0 and frac >= t.min_pos_frac,
        f"positive_frac {frac:.2f} >= {t.min_pos_frac} ({pos}/{nwin})")
    chk(pf is not None and pf > t.min_pf, f"profit_factor {pf} > {t.min_pf} (after fees)")
    chk(exp is not None and exp >= t.min_expectancy, f"expectancy_R {exp} >= {t.min_expectancy}")
    chk(trades >= t.min_trades, f"trades {trades} >= {t.min_trades}")
    if stack:
        bad = ("HURTS" in stack) or ("BLOCKS ALL" in stack)
        chk(not bad, f"stack_verdict ok ({stack or 'n/a'})")

    return GateResult(go=(len(failed) == 0), passed=passed, failed=failed)


if __name__ == "__main__":
    good = {"windows_with_trades": 4, "positive_windows": 4, "profit_factor": 1.6,
            "expectancy_R": 0.4, "trades": 35, "stack_verdict": "control-plane HELPS"}
    bad = {"windows_with_trades": 4, "positive_windows": 1, "profit_factor": 0.8,
           "expectancy_R": -0.1, "trades": 12, "stack_verdict": "control-plane HURTS"}
    for name, c in (("GOOD", good), ("WEAK", bad)):
        r = evaluate(c)
        print(f"{name}: go={r.go}")
        for f in r.failed:
            print(f"   FAIL: {f}")
