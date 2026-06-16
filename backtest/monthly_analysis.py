"""Monthly performance analysis with a BEAR-month failure rule.

Owner's rule (2026-06): a strategy is only acceptable if it does NOT bleed in
bear months. So we break every run down by calendar month, mark which months
were bearish, and FAIL any candidate that has a red (negative) bear month.

Also compares the SAME trade stream "bare" (no control-plane) vs how the
control-plane (обвязка) would have filtered it — to see if the foundation helps
or hurts each strategy month by month.

Pure / testable / additive. Codex feeds the per-strategy trade stream from the
full classic-package run; this produces the monthly table + verdict.

A trade: {"exit_ts_ms", "pnl" (usd) or "R", "regime" (e.g. "bull_trend"/"bear_chop")}.
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, Iterable, List, Sequence


def _month_key(ts_ms: int) -> str:
    d = dt.datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=dt.timezone.utc)
    return f"{d.year:04d}-{d.month:02d}"


def _val(t: dict) -> float:
    if "pnl" in t and t["pnl"] is not None:
        return float(t["pnl"])
    return float(t.get("R", 0.0))


def _month_set(months: Iterable[str] | None) -> set[str]:
    return {str(m).strip() for m in (months or []) if str(m).strip()}


def monthly_breakdown(trades: Sequence[dict], *, bear_months: Iterable[str] | None = None) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    explicit_bear_months = _month_set(bear_months)
    for t in trades:
        m = _month_key(t["exit_ts_ms"])
        b = out.setdefault(m, {"pnl": 0.0, "trades": 0, "wins": 0, "bear_trades": 0})
        v = _val(t)
        b["pnl"] += v
        b["trades"] += 1
        if v > 0:
            b["wins"] += 1
        if "bear" in str(t.get("regime", "")).lower():
            b["bear_trades"] += 1
    for m, b in out.items():
        b["pnl"] = round(b["pnl"], 4)
        b["win_pct"] = round(100.0 * b["wins"] / b["trades"], 1) if b["trades"] else 0.0
        if explicit_bear_months:
            b["is_bear_month"] = m in explicit_bear_months
            b["bear_source"] = "explicit"
        else:
            b["is_bear_month"] = b["bear_trades"] >= max(1, b["trades"] // 2)
            b["bear_source"] = "trade_regime"
        b["red"] = b["pnl"] < 0
    return dict(sorted(out.items()))


def verdict(breakdown: Dict[str, dict]) -> dict:
    """FAIL if any bear month is red (the owner's hard rule), or overall negative."""
    red_bear = [m for m, b in breakdown.items() if b.get("is_bear_month") and b.get("red")]
    total = round(sum(b["pnl"] for b in breakdown.values()), 4)
    months = len(breakdown)
    pos_months = sum(1 for b in breakdown.values() if b["pnl"] > 0)
    bear_months = [m for m, b in breakdown.items() if b.get("is_bear_month")]
    ok = (len(red_bear) == 0) and (total > 0)
    return {
        "verdict": "PASS" if ok else "FAIL",
        "total_pnl": total,
        "months": months,
        "positive_months": pos_months,
        "bear_months": bear_months,
        "red_bear_months": red_bear,   # the dealbreakers
        "reason": ("clean: no red bear month, net positive" if ok
                   else (f"red bear months: {red_bear}" if red_bear else "net negative")),
    }


def format_table(breakdown: Dict[str, dict]) -> str:
    lines = [f"{'month':<9}{'pnl':>10}  {'trades':>6}  {'win%':>5}  flags"]
    for m, b in breakdown.items():
        flags = []
        if b["is_bear_month"]:
            flags.append("BEAR")
        if b["red"]:
            flags.append("RED")
        tag = ("  <-- RED BEAR (fail)" if (b["is_bear_month"] and b["red"]) else "")
        lines.append(f"{m:<9}{b['pnl']:>10.2f}  {b['trades']:>6}  {b['win_pct']:>5.0f}  "
                     f"{' '.join(flags):<10}{tag}")
    return "\n".join(lines)
