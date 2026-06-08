"""Backtest robustness tools — anti-overfit discipline (Opus 2026-06-08).

Two pieces every sweep should use before a strategy is trusted:

1. jitter_rows()        — perturb OHLC by a small % to test that a strategy's
                          edge survives realistic price noise / slippage. A
                          strategy that collapses under 0.2% jitter was fit to
                          noise, not signal.
2. walk_forward_windows() + aggregate_oos()
                        — split history into rolling in-sample (parameter pick)
                          and out-of-sample (validation) folds. The honest
                          performance number is the OOS aggregate, never the
                          in-sample fit.

Pure stdlib, no network, fully unit-tested. Operates on kline rows that are
either dicts {ts,o,h,l,c,v} or lists [ts,o,h,l,c,v].
"""
from __future__ import annotations

import math
import random
import statistics
from typing import Any, Dict, List, Optional, Sequence

_OHLC_KEYS = ("o", "h", "l", "c")
_DAY_MS = 86_400_000


def _is_dict_row(row: Any) -> bool:
    return isinstance(row, dict)


def _get(row: Any, key: str, idx: int) -> float:
    return float(row[key]) if _is_dict_row(row) else float(row[idx])


def jitter_rows(
    rows: Sequence[Any],
    pct: float = 0.002,
    seed: Optional[int] = None,
    mode: str = "uniform",
) -> List[Any]:
    """Return a copy of rows with O/H/L/C perturbed by up to ``pct`` (fraction).

    Invariants are preserved: high = max(o,h,l,c), low = min(o,h,l,c).
    Timestamp and volume are untouched. Input rows are not mutated.
    """
    if pct < 0:
        raise ValueError("pct must be >= 0")
    rng = random.Random(seed)
    out: List[Any] = []
    for row in rows:
        o, h, l, c = (_get(row, k, i) for i, k in enumerate(_OHLC_KEYS, start=1))
        vals = {}
        for name, base in (("o", o), ("h", h), ("l", l), ("c", c)):
            if mode == "gauss":
                factor = 1.0 + rng.gauss(0.0, pct / 2.0)
            else:
                factor = 1.0 + rng.uniform(-pct, pct)
            vals[name] = base * factor
        hi = max(vals.values())
        lo = min(vals.values())
        vals["h"], vals["l"] = hi, lo
        if _is_dict_row(row):
            new = dict(row)
            new.update(vals)
            out.append(new)
        else:
            r = list(row)
            r[1], r[2], r[3], r[4] = vals["o"], vals["h"], vals["l"], vals["c"]
            out.append(r)
    return out


def walk_forward_windows(
    start_ms: int,
    end_ms: int,
    is_days: int,
    oos_days: int,
    step_days: Optional[int] = None,
) -> List[Dict[str, int]]:
    """Rolling in-sample / out-of-sample windows over [start_ms, end_ms).

    Each fold: in-sample of ``is_days`` immediately followed by out-of-sample of
    ``oos_days``. The window then advances by ``step_days`` (default = oos_days,
    i.e. non-overlapping OOS coverage). Returns [] if the range is too short.
    """
    if is_days <= 0 or oos_days <= 0:
        raise ValueError("is_days and oos_days must be > 0")
    step = int(step_days if step_days else oos_days)
    if step <= 0:
        raise ValueError("step_days must be > 0")
    is_ms, oos_ms, step_ms = is_days * _DAY_MS, oos_days * _DAY_MS, step * _DAY_MS
    folds: List[Dict[str, int]] = []
    cur = int(start_ms)
    while cur + is_ms + oos_ms <= int(end_ms):
        is_start = cur
        is_end = cur + is_ms
        folds.append({
            "is_start": is_start,
            "is_end": is_end,
            "oos_start": is_end,
            "oos_end": is_end + oos_ms,
        })
        cur += step_ms
    return folds


def aggregate_oos(
    fold_metrics: List[Dict[str, float]],
    keys: Sequence[str] = ("profit_factor", "return_pct", "max_drawdown", "trades"),
) -> Dict[str, Any]:
    """Aggregate per-fold OOS metrics into an honest robustness summary.

    Returns mean/median/min/max per key plus a simple verdict: a strategy is
    'robust' only if the MEDIAN OOS profit_factor > 1.0 and no single fold is
    catastrophic (min profit_factor > 0.5).
    """
    summary: Dict[str, Any] = {"folds": len(fold_metrics)}
    if not fold_metrics:
        summary["verdict"] = "no_folds"
        return summary
    for k in keys:
        vals = [float(m[k]) for m in fold_metrics if k in m and m[k] is not None]
        if not vals:
            continue
        summary[k] = {
            "mean": round(statistics.fmean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
        }
    pf = summary.get("profit_factor")
    if pf is not None:
        summary["verdict"] = "robust" if (pf["median"] > 1.0 and pf["min"] > 0.5) else "fragile"
    else:
        summary["verdict"] = "unknown"
    return summary


# --- added 2026-06-08 (reviewer feedback): better comparison metrics ---

def geometric_mean_return(returns: Sequence[float]) -> float:
    """Geometric mean of per-period returns (fractions). Penalises volatility
    vs the arithmetic mean — a high-vol strategy won't look artificially good."""
    rs = [float(r) for r in returns]
    if not rs:
        return 0.0
    prod = 1.0
    for r in rs:
        prod *= (1.0 + r)
    if prod <= 0:
        return -1.0
    return prod ** (1.0 / len(rs)) - 1.0


def sortino_ratio(returns: Sequence[float], target: float = 0.0) -> float:
    """Sortino = mean excess return / downside deviation. Unlike Sharpe it only
    penalises downside volatility. +inf if there is no downside, 0 if empty."""
    rs = [float(r) for r in returns]
    if not rs:
        return 0.0
    excess = [r - target for r in rs]
    downside = [min(0.0, e) ** 2 for e in excess]
    dd = math.sqrt(sum(downside) / len(rs))
    mean_excess = sum(excess) / len(rs)
    if dd == 0:
        return math.inf if mean_excess > 0 else 0.0
    return mean_excess / dd


def fee_sensitivity(
    per_trade_gross: Sequence[float],
    fee_bps_list: Sequence[float] = (6.0, 8.0, 10.0),
    sides: int = 2,
) -> Dict[str, Any]:
    """Does the edge survive higher costs? For each fee level, subtract
    sides*fee from each trade's gross return and compound. A high-turnover
    strategy that is positive at 6bps but negative at 10bps is fee-fragile.
    """
    gross = [float(r) for r in per_trade_gross]
    out: Dict[str, Any] = {"trades": len(gross), "levels": {}}
    if not gross:
        out["verdict"] = "no_trades"
        return out
    survives_all = True
    for fee_bps in fee_bps_list:
        cost = sides * float(fee_bps) / 10000.0
        net = [r - cost for r in gross]
        prod = 1.0
        for r in net:
            prod *= (1.0 + r)
        net_total = prod - 1.0
        profitable = net_total > 0
        survives_all = survives_all and profitable
        out["levels"][f"{fee_bps:.0f}bps"] = {
            "net_total_return": round(net_total, 6),
            "mean_net_per_trade": round(sum(net) / len(net), 6),
            "profitable": profitable,
        }
    out["verdict"] = "fee_robust" if survives_all else "fee_fragile"
    return out
