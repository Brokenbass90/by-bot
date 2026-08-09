#!/usr/bin/env python3
"""Find non-reduce orders that contaminated an ATT1 position lifecycle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if isinstance(value, dict):
                rows.append(value)
    return rows


def audit_att1_contamination(
    trade_events: Iterable[dict[str, Any]],
    order_events: Iterable[dict[str, Any]],
    *,
    strategy: str = "att1_trendline_touch",
) -> dict[str, Any]:
    trades = sorted(trade_events, key=lambda row: int(row.get("ts") or 0))
    orders = sorted(order_events, key=lambda row: int(row.get("ts") or 0))
    entries = [
        row
        for row in trades
        if row.get("event") == "entry_filled" and row.get("strategy") == strategy
    ]
    closes = [
        row
        for row in trades
        if row.get("event") == "close" and row.get("strategy") == strategy
    ]
    lifecycles: list[dict[str, Any]] = []

    for entry in entries:
        entry_ts = int(entry.get("ts") or 0)
        symbol = str(entry.get("symbol") or "")
        side = str(entry.get("side") or "")
        entry_order_id = str(entry.get("entry_order_id") or "")
        close = next(
            (
                row
                for row in closes
                if int(row.get("ts") or 0) >= entry_ts
                and str(row.get("symbol") or "") == symbol
            ),
            None,
        )
        close_ts = int(close.get("ts") or 0) if close else None
        extras = [
            row
            for row in orders
            if int(row.get("ts") or 0) >= entry_ts
            and (close_ts is None or int(row.get("ts") or 0) <= close_ts)
            and str(row.get("symbol") or "") == symbol
            and str(row.get("side") or "") == side
            and not bool(row.get("reduce_only"))
            and str(row.get("order_id") or "") != entry_order_id
            and str(row.get("status") or "") == "placed"
        ]
        lifecycles.append(
            {
                "symbol": symbol,
                "entry_ts": entry_ts,
                "close_ts": close_ts,
                "entry_order_id": entry_order_id,
                "entry_qty": entry.get("qty"),
                "contaminated": bool(extras),
                "extra_non_reduce_orders": [
                    {
                        "ts": row.get("ts"),
                        "order_id": row.get("order_id"),
                        "qty": row.get("qty"),
                        "side": row.get("side"),
                    }
                    for row in extras
                ],
            }
        )

    contaminated = [row for row in lifecycles if row["contaminated"]]
    return {
        "schema_version": 1,
        "strategy": strategy,
        "lifecycles": len(lifecycles),
        "contaminated_lifecycles": len(contaminated),
        "clean_lifecycles": len(lifecycles) - len(contaminated),
        "coverage_warning": (
            "order-link log may be retention-limited; clean means no extra order "
            "was found in the supplied log, not proof that none existed"
        ),
        "details": lifecycles,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", type=Path, required=True)
    parser.add_argument("--orders", type=Path, required=True)
    parser.add_argument("--strategy", default="att1_trendline_touch")
    args = parser.parse_args()
    result = audit_att1_contamination(
        _load_jsonl(args.trades),
        _load_jsonl(args.orders),
        strategy=args.strategy,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if result["contaminated_lifecycles"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
