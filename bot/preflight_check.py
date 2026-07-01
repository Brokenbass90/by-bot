"""Pre-flight frequency/coverage check — don't run OOS gates destined to fail.

Lesson from InPlay V4: we burned an expensive rolling-OOS gate that failed only
because the strategy is too RARE (21 trades / 4 folds, one fold had 1 trade). That
was a knowable-in-advance waste. This runs a CHEAP check on a strategy's signal
timestamps+symbols BEFORE the gate and returns GO / NO-GO:
  * enough trades per fold (variance kills thin folds);
  * enough SYMBOL coverage (not a 1-symbol selection artifact);
  * enough TIME coverage (not all trades in one window).
If NO-GO -> widen universe / loosen selectivity first, don't run the gate.

Pure stdlib. Feed it signals = [{"ts", "symbol"}, ...] (from a quick dry signal run).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class PreflightReport:
    go: bool
    total_trades: int
    n_folds: int
    per_fold_trades: List[int]
    min_fold_trades: int
    symbols_covered: int
    reasons: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


def preflight(
    signals: Sequence[Dict[str, Any]],
    *,
    n_folds: int = 4,
    fold_edges: Optional[Sequence[float]] = None,   # n_folds+1 timestamps; else derived
    min_trades_total: int = 40,
    min_trades_per_fold: int = 8,
    min_symbols: int = 3,
    ts_key: str = "ts",
    symbol_key: str = "symbol",
) -> PreflightReport:
    """Cheap GO/NO-GO before an expensive OOS gate."""
    sigs = [s for s in signals if s.get(ts_key) is not None]
    total = len(sigs)
    symbols = {str(s.get(symbol_key, "?")).upper() for s in sigs}
    n_sym = len(symbols)

    if total == 0:
        return PreflightReport(False, 0, n_folds, [0] * n_folds, 0, n_sym,
                               ["no_signals"])

    tss = [float(s[ts_key]) for s in sigs]
    if fold_edges is not None and len(fold_edges) == n_folds + 1:
        edges = [float(e) for e in fold_edges]
    else:
        t0, t1 = min(tss), max(tss)
        span = (t1 - t0) / n_folds if t1 > t0 else 1.0
        edges = [t0 + i * span for i in range(n_folds + 1)]

    per_fold = [0] * n_folds
    for t in tss:
        for i in range(n_folds):
            lo, hi = edges[i], edges[i + 1]
            if (t >= lo and t < hi) or (i == n_folds - 1 and t == hi):
                per_fold[i] += 1
                break
    min_fold = min(per_fold) if per_fold else 0

    reasons: List[str] = []
    if total < min_trades_total:
        reasons.append(f"too_few_total_{total}<{min_trades_total}")
    if min_fold < min_trades_per_fold:
        reasons.append(f"thin_fold_{min_fold}<{min_trades_per_fold}")
    if n_sym < min_symbols:
        reasons.append(f"low_symbol_coverage_{n_sym}<{min_symbols}")

    go = not reasons
    if go:
        reasons.append("ready_for_gate")
    return PreflightReport(go, total, n_folds, per_fold, min_fold, n_sym, reasons,
                           extra={"symbols": sorted(symbols)})
