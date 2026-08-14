#!/usr/bin/env python3
"""Reconstruct ATT1 runner lifecycles from an event ledger without broker calls."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _read(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def reconstruct(path: Path, *, start_ts: int = 0) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in _read(path):
        order_id = str(row.get("entry_order_id") or "").strip()
        if order_id and str(row.get("strategy") or "").startswith("att1"):
            grouped.setdefault(order_id, []).append(row)

    trades: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for order_id, rows in grouped.items():
        rows.sort(key=lambda row: int(row.get("ts") or 0))
        fill = next((row for row in rows if row.get("event") == "entry_filled"), None)
        close = next((row for row in reversed(rows) if row.get("event") == "close"), None)
        if close is None or int(close.get("ts") or 0) < start_ts:
            continue
        reasons: list[str] = []
        if fill is None:
            reasons.append("missing_entry_fill")
        if close.get("accounting_contaminated") is not False:
            reasons.append("accounting_not_explicitly_clean")
        risk_usd = _finite((fill or {}).get("actual_risk_usd"))
        if risk_usd is None or risk_usd <= 0:
            reasons.append("missing_actual_initial_risk")
        if (fill or {}).get("post_fill_risk_allowed") is not True:
            reasons.append("post_fill_risk_not_allowed")
        if not bool(((fill or {}).get("runner") or {}).get("runner_enabled")):
            reasons.append("runner_not_enabled_at_fill")

        entry = _finite((fill or {}).get("fill_price") or (fill or {}).get("entry_price"))
        initial_sl = _finite(((fill or {}).get("runner") or {}).get("initial_sl_price"))
        side = str((fill or {}).get("side") or close.get("side") or "").lower()
        risk_price = abs(entry - initial_sl) if entry is not None and initial_sl is not None else None
        observed = []
        for row in rows:
            if row.get("event") not in {"runner_breakeven", "runner_trailing_sl", "runner_tp"}:
                continue
            price = _finite(row.get("price"))
            if price is not None:
                observed.append((int(row.get("ts") or 0), price))
        if entry is not None:
            observed.insert(0, (int((fill or {}).get("ts") or 0), entry))

        best_ts = None
        best_price = None
        if observed:
            if side in {"sell", "short"}:
                best_ts, best_price = min(observed, key=lambda item: item[1])
            else:
                best_ts, best_price = max(observed, key=lambda item: item[1])
        mfe_lower_r = None
        if entry is not None and best_price is not None and risk_price and risk_price > 0:
            favorable = entry - best_price if side in {"sell", "short"} else best_price - entry
            mfe_lower_r = favorable / risk_price

        tp_events = [row for row in rows if row.get("event") == "runner_tp"]
        tp1_hit = any(int(row.get("tp_index") or 0) == 1 for row in tp_events)
        tp2_hit = any(int(row.get("tp_index") or 0) == 2 for row in tp_events)
        runner_snapshot = (close.get("runner") or {}) if close else {}
        tp_hit_snapshot = runner_snapshot.get("tp_hit") or []
        if len(tp_hit_snapshot) >= 1:
            tp1_hit = tp1_hit or bool(tp_hit_snapshot[0])
        if len(tp_hit_snapshot) >= 2:
            tp2_hit = tp2_hit or bool(tp_hit_snapshot[1])
        net_pnl = _finite(close.get("pnl")) or 0.0
        row_out = {
            "order_id": order_id,
            "symbol": close.get("symbol"),
            "side": close.get("side"),
            "entry_ts": (fill or {}).get("ts"),
            "close_ts": close.get("ts"),
            "close_ts_utc": close.get("ts_utc"),
            "holding_sec": int(close.get("ts") or 0) - int((fill or {}).get("ts") or 0),
            "entry_price": entry,
            "initial_sl": initial_sl,
            "exit_price": _finite(close.get("exit_price")),
            "net_pnl_usd": net_pnl,
            "actual_initial_risk_usd": risk_usd,
            "net_r": net_pnl / risk_usd if risk_usd and risk_usd > 0 else None,
            "tp1_hit": tp1_hit,
            "tp2_hit": tp2_hit,
            "breakeven_armed": any(row.get("event") == "runner_breakeven" for row in rows),
            "trailing_armed": any(row.get("event") == "runner_trailing_sl" for row in rows),
            "runner_event_mfe_lower_bound_r": mfe_lower_r,
            "seconds_from_best_runner_observation_to_close": (
                int(close.get("ts") or 0) - int(best_ts) if best_ts is not None else None
            ),
            "close_reason": close.get("close_reason"),
            "limitations": [
                "MFE is a lower bound from runner events, not a complete market-bar replay",
                "close reason can be SL after a profitable trailing stop",
            ],
            "reasons": reasons,
        }
        (rejected if reasons else trades).append(row_out)

    trades.sort(key=lambda row: int(row["close_ts"] or 0))
    net_rs = [float(row["net_r"]) for row in trades]
    gains = sum(max(0.0, value) for value in net_rs)
    losses = -sum(min(0.0, value) for value in net_rs)
    return {
        "schema_id": "att1_lifecycle_readonly_v1",
        "authority": "read_only_no_order_or_risk_mutation",
        "source_ledger": str(path),
        "start_ts": start_ts,
        "clean_closed": len(trades),
        "net_r": sum(net_rs),
        "profit_factor_r": gains / losses if losses else (None if gains else 0.0),
        "profit_factor_r_infinite": bool(gains and not losses),
        "tp1_hits": sum(bool(row["tp1_hit"]) for row in trades),
        "tp2_hits": sum(bool(row["tp2_hit"]) for row in trades),
        "trailing_armed": sum(bool(row["trailing_armed"]) for row in trades),
        "trades": trades,
        "rejected": rejected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--start-ts", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = reconstruct(args.ledger, start_ts=args.start_ts)
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
