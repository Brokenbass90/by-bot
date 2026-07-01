"""Purge + embargo walk-forward folds — honest OOS windows (DeepSeek H5 / CPCV-lite).

Our nested-window "OOS" (90/240/360d all ending now) overstated results: overlapping
positions leak across the train/test boundary and adjacent windows share trades. This
builds NON-overlapping, time-ordered OOS folds with:
  * PURGE   — drop any trade whose lifetime straddles a fold boundary (its outcome
              depends on data on both sides -> leakage);
  * EMBARGO — drop trades entering within an embargo gap right after each boundary
              (kills serial correlation between adjacent folds).
Output folds plug straight into bot.oos_selector.evaluate_candidate / select_robust.

Light enough for a 1GB box (pure list logic, no heavy compute). Pure stdlib.
Each trade: {"entry_ts", "exit_ts", "r"} (ms or any monotonic unit; r = R-multiple).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class FoldSet:
    folds: List[Dict[str, Any]]      # [{fold, window, trades, net_r, r_list}, ...]
    n_folds: int
    used: int                        # trades placed into a fold
    purged: int                      # dropped for straddling a boundary
    embargoed: int                   # dropped inside an embargo gap
    total: int
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_candidate(self, cid: str = "candidate", params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Shape for bot.oos_selector: {id, folds:[{net_r, trades}], params}."""
        return {"id": cid, "params": params or {},
                "folds": [{"net_r": f["net_r"], "trades": f["trades"]} for f in self.folds]}


def purge_embargo_folds(
    trades: Sequence[Dict[str, Any]],
    *,
    n_folds: int = 4,
    embargo: float = 0.0,            # gap after each boundary, same unit as timestamps
    entry_key: str = "entry_ts",
    exit_key: str = "exit_ts",
    r_key: str = "r",
) -> FoldSet:
    """Partition trades into n_folds non-overlapping OOS windows with purge+embargo."""
    ts = [t for t in trades
          if t.get(entry_key) is not None and t.get(exit_key) is not None]
    total = len(trades)
    if n_folds < 1 or len(ts) < n_folds:
        return FoldSet([], n_folds, 0, 0, 0, total, {"reason": "too_few_trades"})

    ts = sorted(ts, key=lambda t: float(t[entry_key]))
    t0 = min(float(t[entry_key]) for t in ts)
    t1 = max(float(t[exit_key]) for t in ts)
    if t1 <= t0:
        return FoldSet([], n_folds, 0, 0, 0, total, {"reason": "degenerate_time_range"})

    span = (t1 - t0) / n_folds
    edges = [t0 + i * span for i in range(n_folds + 1)]

    folds: List[Dict[str, Any]] = []
    used = purged = embargoed = 0
    for i in range(n_folds):
        lo, hi = edges[i], edges[i + 1]
        r_list: List[float] = []
        for t in ts:
            e = float(t[entry_key]); x = float(t[exit_key])
            if e < lo or e >= hi:
                continue                      # entered in a different window
            if x > hi:                        # lifetime straddles the fold's end boundary
                purged += 1
                continue
            if e < lo + embargo:              # inside the embargo gap after the boundary
                embargoed += 1
                continue
            rv = t.get(r_key)
            if rv is None or rv != rv:
                continue
            r_list.append(float(rv))
        used += len(r_list)
        folds.append({"fold": i, "window": [lo, hi], "trades": len(r_list),
                      "net_r": round(sum(r_list), 6), "r_list": r_list})
    return FoldSet(folds, n_folds, used, purged, embargoed, total)
