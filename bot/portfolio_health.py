"""Portfolio-wide sleeve health monitor.

Generalizes the att1 edge_monitor to EVERY sleeve: reads closed trades from the live
trades DB, computes actual-risk R-multiples per strategy (qty*|entry-sl|), grades each
sleeve via edge_monitor.assess_sleeve, maps status -> a soft risk multiplier, and builds
a persistable report.

ALERT-FIRST by design: this module never trades and never changes sizing. Callers decide
whether to (a) only alert on status changes, or (b) apply status_risk_mult() to a sleeve's
risk (auto-cut) — kept behind a flag so a monitoring bug can never block live trading.

Pure stdlib + bot.edge_monitor.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence

from bot.edge_monitor import assess_sleeve, HealthReport

# status -> soft risk multiplier (applied ONLY when the caller opts into auto-cut)
_STATUS_MULT: Dict[str, float] = {"healthy": 1.0, "watch": 1.0, "degraded": 0.5, "halt": 0.0}


def status_risk_mult(status: str) -> float:
    return float(_STATUS_MULT.get(str(status or "").strip().lower(), 1.0))


def sleeve_r_multiples_from_db(db_path: str, *, lookback_days: int = 45,
                               start_ts: int = 0) -> Dict[str, List[float]]:
    """Return {strategy: [R, ...]} from closed trades, actual-risk based.

    R = pnl / (qty * |entry_price - sl_price|). Trades with non-positive risk or missing
    pnl are skipped (minqty-fallback trades therefore do not distort R).
    """
    out: Dict[str, List[float]] = {}
    cutoff = int(time.time()) - int(lookback_days) * 86400
    if start_ts and int(start_ts) > cutoff:
        cutoff = int(start_ts)
    try:
        with sqlite3.connect(db_path) as con:
            rows = con.execute(
                "SELECT strategy, qty, entry_price, sl_price, pnl FROM trade_events "
                "WHERE event='CLOSE' AND ts>=? ORDER BY ts",
                (cutoff,),
            ).fetchall()
    except Exception:
        return out
    for strat, qty, entry_px, sl_px, pnl in rows:
        try:
            risk = float(qty or 0.0) * abs(float(entry_px or 0.0) - float(sl_px or 0.0))
            if risk > 0 and pnl is not None:
                out.setdefault(str(strat or "?"), []).append(float(pnl) / risk)
        except Exception:
            continue
    return out


def assess_portfolio(
    db_path: str,
    *,
    baselines: Optional[Dict[str, float]] = None,
    lookback_days: int = 45,
    start_ts: int = 0,
    **assess_kw: Any,
) -> Dict[str, HealthReport]:
    """Grade every sleeve found in the trades DB against its (optional) baseline."""
    baselines = baselines or {}
    by_sleeve = sleeve_r_multiples_from_db(db_path, lookback_days=lookback_days, start_ts=start_ts)
    out: Dict[str, HealthReport] = {}
    for sleeve, rs in by_sleeve.items():
        out[sleeve] = assess_sleeve(
            rs, sleeve=sleeve,
            baseline_expectancy_R=float(baselines.get(sleeve, 0.0)),
            **assess_kw,
        )
    return out


def build_report(reports: Dict[str, HealthReport]) -> Dict[str, Any]:
    """Serialize sleeve reports into a compact, persistable dict."""
    sleeves: Dict[str, Any] = {}
    for s, r in reports.items():
        sleeves[s] = {
            "status": r.status,
            "n": r.n,
            "live_expectancy_R": (r.live_expectancy_R if r.live_expectancy_R == r.live_expectancy_R else None),
            "baseline_expectancy_R": r.baseline_expectancy_R,
            "win_rate": (r.win_rate if r.win_rate == r.win_rate else None),
            "drawdown_R": r.drawdown_R,
            "worst_losing_streak": r.worst_losing_streak,
            "reason": r.reason,
            "risk_mult": status_risk_mult(r.status),
        }
    return {
        "ts": int(time.time()),
        "sleeves": sleeves,
        "degraded_sleeves": sorted(s for s, r in reports.items() if r.status in ("degraded", "halt")),
        "halted_sleeves": sorted(s for s, r in reports.items() if r.status == "halt"),
    }
