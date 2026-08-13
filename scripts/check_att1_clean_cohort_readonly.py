#!/usr/bin/env python3
"""Read-only ATT1 post-release cohort reconstruction from the live event ledger."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _events(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def reconstruct(path: Path, start_ts: int) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in _events(path):
        order_id = str(row.get("entry_order_id") or "").strip()
        if order_id and str(row.get("strategy") or "").startswith("att1"):
            grouped.setdefault(order_id, []).append(row)
    clean = []
    rejected = []
    for order_id, rows in grouped.items():
        rows.sort(key=lambda row: int(row.get("ts") or 0))
        close = next((row for row in reversed(rows) if row.get("event") == "close"), None)
        if close is None or int(close.get("ts") or 0) < start_ts:
            continue
        fill = next((row for row in rows if row.get("event") == "entry_filled"), None)
        reasons = []
        if fill is None:
            reasons.append("missing_entry_fill")
        if close.get("accounting_contaminated") is not False:
            reasons.append("accounting_not_explicitly_clean")
        risk = float((fill or {}).get("actual_risk_usd") or 0.0)
        if not math.isfinite(risk) or risk <= 0:
            reasons.append("missing_actual_initial_risk")
        if (fill or {}).get("post_fill_risk_allowed") is not True:
            reasons.append("post_fill_risk_not_allowed")
        if not bool(((fill or {}).get("runner") or {}).get("runner_enabled")):
            reasons.append("runner_not_enabled_at_fill")
        row = {
            "order_id": order_id,
            "symbol": close.get("symbol"),
            "close_ts": close.get("ts"),
            "close_ts_utc": close.get("ts_utc"),
            "net_pnl": float(close.get("pnl") or 0.0),
            "actual_initial_risk_usd": risk,
            "net_r": float(close.get("pnl") or 0.0) / risk if risk > 0 else None,
            "close_reason": close.get("close_reason"),
            "reasons": reasons,
        }
        (rejected if reasons else clean).append(row)
    clean.sort(key=lambda row: int(row["close_ts"] or 0))
    rs = [float(row["net_r"]) for row in clean]
    gains = sum(max(0.0, value) for value in rs)
    losses = -sum(min(0.0, value) for value in rs)
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for value in rs:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "schema_id": "att1_clean_cohort_readonly_v1",
        "authority": "read_only_no_order_or_risk_mutation",
        "start_ts": start_ts,
        "clean_closed": len(clean),
        "target_closed": 20,
        "net_r": sum(rs),
        "profit_factor_r": gains / losses if losses else (math.inf if gains else 0.0),
        "max_drawdown_r": max_dd,
        "clean": clean,
        "rejected": rejected,
        "gates": {
            "n20": len(clean) >= 20,
            "net_r_at_least_2": sum(rs) >= 2.0,
            "pf_at_least_1_2": (gains / losses if losses else (math.inf if gains else 0.0)) >= 1.2,
            "drawdown_at_most_5r": max_dd <= 5.0,
            "zero_rejected_conflicts": not rejected,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("runtime/live_trade_events.jsonl"))
    parser.add_argument("--start-ts", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(reconstruct(args.ledger, args.start_ts), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
