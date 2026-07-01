"""Pre-flight frequency/coverage check — don't run OOS gates destined to fail.

Lesson from InPlay V4: we burned an expensive rolling-OOS gate that failed only
because the strategy is too RARE (21 trades / 4 folds, one fold had 1 trade). That
was a knowable-in-advance waste. This runs a CHEAP check on a strategy's signal
timestamps+symbols BEFORE the gate and returns GO / NO-GO:
  * enough trades per fold (variance kills thin folds);
  * enough SYMBOL coverage (not a 1-symbol selection artifact);
  * enough TIME coverage (not all trades in one window);
  * optional cheap quality sanity if dry-run records already contain R/PnL.
If NO-GO -> widen universe / loosen selectivity first, don't run the gate.

Pure stdlib. Feed it signals = [{"ts", "symbol"}, ...] or, when available,
[{"ts", "symbol", "r": realized_R}, ...] from a quick dry signal run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


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
    min_quality_trades: int = 20,
    min_quality_pf: float = 0.80,
    caution_quality_pf: float = 1.00,
    r_keys: Sequence[str] = ("r", "pnl_r", "net_r", "realized_r"),
    ts_key: str = "ts",
    symbol_key: str = "symbol",
) -> PreflightReport:
    """Cheap GO/NO-GO before an expensive OOS gate.

    The core check is frequency/coverage. If the caller includes rough R-multiples
    in records, we also run a cheap quality sanity check. This is not a replacement
    for OOS; it just prevents obviously noisy candidates from entering expensive
    WF when the signal run already says PF is deeply negative.
    """
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

    quality = _quality_sanity(
        sigs,
        r_keys=tuple(r_keys),
        min_quality_trades=min_quality_trades,
        min_quality_pf=min_quality_pf,
        caution_quality_pf=caution_quality_pf,
    )
    reasons.extend(quality["blockers"])

    go = not reasons
    if go:
        reasons.append("ready_for_gate")
    return PreflightReport(go, total, n_folds, per_fold, min_fold, n_sym, reasons,
                           extra={"symbols": sorted(symbols), **quality["extra"]})


def _first_float(record: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[float]:
    for k in keys:
        if k not in record or record.get(k) is None:
            continue
        try:
            v = float(record[k])
        except (TypeError, ValueError):
            continue
        if v == v:
            return v
    return None


def _quality_sanity(
    records: Sequence[Dict[str, Any]],
    *,
    r_keys: Tuple[str, ...],
    min_quality_trades: int,
    min_quality_pf: float,
    caution_quality_pf: float,
) -> Dict[str, Any]:
    vals = [_first_float(r, r_keys) for r in records]
    rs = [v for v in vals if v is not None]
    extra: Dict[str, Any] = {
        "quality_checked": False,
        "quality_n": len(rs),
        "quality_warnings": [],
    }
    blockers: List[str] = []
    if not rs:
        extra["quality_warnings"].append("quality_not_available")
        return {"blockers": blockers, "extra": extra}
    if len(rs) < min_quality_trades:
        extra["quality_warnings"].append(f"quality_thin_{len(rs)}<{min_quality_trades}")
        return {"blockers": blockers, "extra": extra}

    gains = sum(x for x in rs if x > 0)
    losses = -sum(x for x in rs if x < 0)
    if losses <= 0:
        pf = float("inf") if gains > 0 else 0.0
    else:
        pf = gains / losses
    mean_r = sum(rs) / len(rs)
    extra.update({
        "quality_checked": True,
        "quality_pf": pf,
        "quality_mean_r": mean_r,
        "quality_wins": sum(1 for x in rs if x > 0),
        "quality_losses": sum(1 for x in rs if x < 0),
    })
    if pf < min_quality_pf:
        blockers.append(f"low_quality_pf_{pf:.2f}<{min_quality_pf:.2f}")
    elif pf < caution_quality_pf:
        extra["quality_warnings"].append(f"caution_quality_pf_{pf:.2f}<{caution_quality_pf:.2f}")
    return {"blockers": blockers, "extra": extra}
