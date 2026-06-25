"""Red-month hedge pairing — does a second sleeve cover the first sleeve's red
bear months?  (Owner's idea #2: range + breakdown/Elder in counter-phase.)

The whole reason range can't be scaled today is `neg_months>4` / red bear months.
If a counter-phase sleeve (breakdown for downside, Elder for trend) is GREEN in
exactly the months range bleeds, the COMBINED book has no red bear month and can
be scaled. This module measures that, on real trade streams, using the existing
monthly_analysis (same bear-month FAIL rule).

A trade: {"exit_ts_ms", "pnl" (usd) or "R", "regime" (e.g. "bear_chop")}.
Pure / additive / testable. Codex feeds the per-sleeve trade streams from the
package run; this prints the combined monthly verdict + coverage.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

from backtest.monthly_analysis import monthly_breakdown, verdict


def combine_streams(*streams: Sequence[dict]) -> List[dict]:
    """Merge several sleeves' trade streams into one book (time order not required;
    monthly_breakdown buckets by month)."""
    out: List[dict] = []
    for s in streams:
        out.extend(s or [])
    return out


def _red_bear_set(breakdown: Dict[str, dict]) -> set[str]:
    return {m for m, b in breakdown.items() if b.get("is_bear_month") and b.get("red")}


def hedge_report(
    primary: Sequence[dict],
    hedge: Sequence[dict],
    *,
    bear_months: Iterable[str] | None = None,
) -> dict:
    """Compare primary alone vs primary+hedge, focused on red bear-month coverage.

    Returns:
      - primary_verdict / combined_verdict (PASS/FAIL via the bear-month rule)
      - red_bear_primary: months where primary bled in a bear month (the problem)
      - covered / uncovered: which of those the hedge turned green in the combined book
      - hedge_drag_months: months that were green for primary but the hedge made red
        (the cost of carrying the hedge) — we want this small
      - monthly tables for primary, hedge, combined
    """
    bp = monthly_breakdown(primary, bear_months=bear_months)
    bh = monthly_breakdown(hedge, bear_months=bear_months)
    combined = combine_streams(primary, hedge)
    bc = monthly_breakdown(combined, bear_months=bear_months)

    red_primary = _red_bear_set(bp)
    red_combined = _red_bear_set(bc)
    covered = sorted(red_primary - red_combined)      # hedge fixed these
    uncovered = sorted(red_primary & red_combined)     # still red after hedge

    # months the primary was net-positive but the combined turned net-negative
    drag = sorted(
        m for m in bc
        if bc[m].get("red") and (m in bp) and not bp[m].get("red")
    )

    vp = verdict(bp)
    vc = verdict(bc)
    return {
        "primary_verdict": vp["verdict"],
        "combined_verdict": vc["verdict"],
        "primary_total_pnl": vp["total_pnl"],
        "combined_total_pnl": vc["total_pnl"],
        "red_bear_primary": sorted(red_primary),
        "red_bear_combined": sorted(red_combined),
        "covered_red_bear_months": covered,
        "uncovered_red_bear_months": uncovered,
        "hedge_drag_months": drag,
        "improved": (vc["verdict"] == "PASS" and vp["verdict"] == "FAIL"),
        "monthly_primary": bp,
        "monthly_hedge": bh,
        "monthly_combined": bc,
    }


def format_hedge_summary(rep: dict) -> str:
    lines = [
        f"primary:  {rep['primary_verdict']}  (pnl {rep['primary_total_pnl']:+.2f}, "
        f"red bear: {rep['red_bear_primary'] or 'none'})",
        f"combined: {rep['combined_verdict']}  (pnl {rep['combined_total_pnl']:+.2f}, "
        f"red bear: {rep['red_bear_combined'] or 'none'})",
        f"hedge covered: {rep['covered_red_bear_months'] or 'none'}",
        f"still red:     {rep['uncovered_red_bear_months'] or 'none'}",
        f"hedge drag:    {rep['hedge_drag_months'] or 'none'}",
        f"verdict: {'HEDGE HELPS (FAIL->PASS)' if rep['improved'] else 'no flip'}",
    ]
    return "\n".join(lines)
