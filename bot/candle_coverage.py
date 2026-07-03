"""Candle coverage gate — honest data before honest verdicts.

Live forensics 2026-07-03: 31/41 live trades had missing candles; several range
symbols had ZERO cached files. Any strategy verdict (and any MFE/MAE forensics)
computed on holed data is uninformative. This module grades a symbol's candle
series and a whole universe BEFORE a sleeve is screened, gated or re-enabled.

Rule (P0, 2026-07-03): range/pila sleeves do not return to live until their
universe passes this gate at 0-missing (coverage >= min_coverage, no giant gaps,
flat-bar share sane).

Contract: rows = [[ts_ms, o, h, l, c, v], ...] ascending (same as everywhere).
Dependency-free, causal, unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

__all__ = ["CoverageReport", "assess_coverage", "assess_universe"]


@dataclass
class CoverageReport:
    symbol: str
    interval_min: int
    expected_bars: int
    actual_bars: int
    coverage: float              # actual / expected in [0..1]
    n_gaps: int
    max_gap_bars: int
    gaps: List[Tuple[int, int, int]]   # (ts_before_ms, ts_after_ms, missing_bars)
    flat_frac: float             # share of bars with high == low (dead/filled bars)
    dup_bars: int                # duplicated timestamps
    ok: bool = False
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = self.__dict__.copy()
        d["gaps"] = [list(g) for g in self.gaps[:20]]  # bounded output
        return d


def _f(row: Sequence[float], idx: int) -> float:
    try:
        return float(row[idx])
    except Exception:
        return float("nan")


def assess_coverage(
    rows: Sequence[Sequence[float]],
    *,
    symbol: str = "?",
    interval_min: int = 60,
    min_coverage: float = 0.995,
    max_gap_bars_allowed: int = 12,
    max_flat_frac: float = 0.05,
    min_bars: int = 200,
    market_closure_gap_bars: int | None = None,
) -> CoverageReport:
    """Grade one symbol's candle series for analysis-worthiness.

    market_closure_gap_bars: gaps with at least this many missing bars are
    treated as scheduled market closures (FX weekends: ~576 M5 bars / ~48 H1
    bars), excluded from expected-bar count and NOT flagged as holes. Keep
    None for 24/7 markets (crypto) — there a giant gap IS a hole.

    ok=False reasons:
      too_few_bars_N        — series shorter than min_bars
      coverage_below_X      — (actual/expected) under min_coverage
      gap_over_N_bars       — at least one hole longer than max_gap_bars_allowed
      flat_share_X          — too many high==low bars (stale fills / dead feed)
      duplicate_bars_N      — repeated timestamps (collector bug)
      non_monotonic_ts      — timestamps go backwards (corrupt file)
    """
    step_ms = int(interval_min) * 60_000
    base = CoverageReport(
        symbol=str(symbol).upper(), interval_min=int(interval_min),
        expected_bars=0, actual_bars=len(rows), coverage=0.0,
        n_gaps=0, max_gap_bars=0, gaps=[], flat_frac=0.0, dup_bars=0,
    )
    if len(rows) < int(min_bars):
        base.reasons.append(f"too_few_bars_{len(rows)}")
        return base

    ts_prev = _f(rows[0], 0)
    gaps: List[Tuple[int, int, int]] = []
    dup = 0
    flat = 0
    if _f(rows[0], 2) == _f(rows[0], 3):
        flat += 1
    for i in range(1, len(rows)):
        ts = _f(rows[i], 0)
        if ts == ts_prev:
            dup += 1
        elif ts < ts_prev:
            base.reasons.append("non_monotonic_ts")
            return base
        else:
            missing = int(round((ts - ts_prev) / step_ms)) - 1
            if missing > 0:
                gaps.append((int(ts_prev), int(ts), missing))
        if _f(rows[i], 2) == _f(rows[i], 3):
            flat += 1
        ts_prev = ts

    closure_thr = int(market_closure_gap_bars) if market_closure_gap_bars else 0
    closure_missing = sum(g[2] for g in gaps if closure_thr and g[2] >= closure_thr)
    if closure_thr:
        gaps = [g for g in gaps if g[2] < closure_thr]

    span_bars = int(round((_f(rows[-1], 0) - _f(rows[0], 0)) / step_ms)) + 1
    expected = max(1, span_bars - closure_missing)
    actual_unique = len(rows) - dup
    coverage = min(1.0, actual_unique / expected)
    max_gap = max((g[2] for g in gaps), default=0)
    flat_frac = flat / len(rows)

    base.expected_bars = expected
    base.actual_bars = actual_unique
    base.coverage = round(coverage, 6)
    base.n_gaps = len(gaps)
    base.max_gap_bars = max_gap
    base.gaps = gaps
    base.flat_frac = round(flat_frac, 6)
    base.dup_bars = dup

    if coverage < float(min_coverage):
        base.reasons.append(f"coverage_below_{coverage:.4f}")
    if max_gap > int(max_gap_bars_allowed):
        base.reasons.append(f"gap_over_{max_gap}_bars")
    if flat_frac > float(max_flat_frac):
        base.reasons.append(f"flat_share_{flat_frac:.3f}")
    if dup > 0:
        base.reasons.append(f"duplicate_bars_{dup}")

    base.ok = not base.reasons
    return base


def assess_universe(
    rows_by_symbol: Dict[str, Sequence[Sequence[float]]],
    *,
    interval_min: int = 60,
    min_coverage: float = 0.995,
    max_gap_bars_allowed: int = 12,
    max_flat_frac: float = 0.05,
    min_bars: int = 200,
    min_ok_symbols: int = 3,
    market_closure_gap_bars: int | None = None,
) -> Dict[str, Any]:
    """Gate a whole universe: which symbols are analysis-worthy RIGHT NOW.

    Returns {go, ok_symbols, failed, reports}. go=False when fewer than
    min_ok_symbols pass — running a screen/gate on such a universe produces
    verdicts about data holes, not about the market (EURUSD/M5 lesson).
    """
    reports = {
        sym: assess_coverage(
            rows, symbol=sym, interval_min=interval_min,
            min_coverage=min_coverage, max_gap_bars_allowed=max_gap_bars_allowed,
            max_flat_frac=max_flat_frac, min_bars=min_bars,
            market_closure_gap_bars=market_closure_gap_bars,
        )
        for sym, rows in rows_by_symbol.items()
    }
    ok_symbols = sorted(s for s, r in reports.items() if r.ok)
    failed = {s: r.reasons for s, r in reports.items() if not r.ok}
    return {
        "go": len(ok_symbols) >= int(min_ok_symbols),
        "ok_symbols": ok_symbols,
        "failed": failed,
        "reports": {s: r.to_dict() for s, r in reports.items()},
    }
