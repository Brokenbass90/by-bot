#!/usr/bin/env python3
"""Paper-shadow cross-exchange funding candidates.

Research-only. Opens virtual pair trades from
`cross_exchange_funding_validated.json`, tracks mark-to-market drift plus the
funding edge estimated by the validator, and closes them after a fixed hold.

No private keys, no orders, no account access.
"""

from __future__ import annotations

import argparse
import json
import math
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cross_exchange_funding_validate import fetch_orderbook


ROOT = Path(__file__).resolve().parents[1]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _book_mid(exchange: str, symbol: str) -> float:
    book = fetch_orderbook(exchange, symbol, limit=20)
    if not book.bids or not book.asks:
        return 0.0
    bid = book.bids[0][0]
    ask = book.asks[0][0]
    if bid <= 0 or ask <= 0:
        return 0.0
    return (bid + ask) / 2.0


def _pair_price_pnl_pct(pos: dict[str, Any], long_mid: float, short_mid: float) -> float:
    long_entry = _f(pos.get("long_entry_mid"))
    short_entry = _f(pos.get("short_entry_mid"))
    if long_entry <= 0 or short_entry <= 0 or long_mid <= 0 or short_mid <= 0:
        return 0.0
    long_ret = (long_mid / long_entry - 1.0) * 100.0
    short_ret = (short_entry / short_mid - 1.0) * 100.0
    # Percent of one leg notional. Divide by 2 to view return on fully-funded
    # two-leg capital.
    return long_ret + short_ret


def _open_position(item: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    symbol = str(item.get("symbol") or "").upper()
    long_ex = str(item.get("long_exchange") or "").lower()
    short_ex = str(item.get("short_exchange") or "").lower()
    long_mid = _book_mid(long_ex, symbol)
    short_mid = _book_mid(short_ex, symbol)
    now = time.time()
    return {
        "id": str(uuid.uuid4())[:12],
        "status": "open",
        "pair_key": item.get("pair_key") or f"{symbol}:{long_ex}->{short_ex}",
        "symbol": symbol,
        "long_exchange": long_ex,
        "short_exchange": short_ex,
        "opened_at_utc": _utc_now(),
        "opened_at_epoch": now,
        "hold_hours": float(args.hold_hours),
        "notional_usd_per_leg": float(args.notional_usd),
        "long_entry_mid": round(long_mid, 10),
        "short_entry_mid": round(short_mid, 10),
        "entry_spread_monthly_pct": _f(item.get("spread_monthly_pct")),
        "entry_expected_funding_pct_for_hold": _f(item.get("expected_funding_pct_for_hold")),
        "entry_estimated_roundtrip_cost_pct": _f(item.get("estimated_roundtrip_cost_pct")),
        "entry_estimated_net_pct_for_hold": _f(item.get("estimated_net_pct_for_hold")),
        "entry_persistence_count": int(_f(item.get("persistence_count_in_window"))),
        "updates": [],
    }


def _update_position(pos: dict[str, Any], current_by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    now = time.time()
    age_h = max(0.0, (now - _f(pos.get("opened_at_epoch"), now)) / 3600.0)
    hold_h = max(1e-9, _f(pos.get("hold_hours"), 24.0))
    symbol = str(pos.get("symbol") or "").upper()
    long_ex = str(pos.get("long_exchange") or "").lower()
    short_ex = str(pos.get("short_exchange") or "").lower()
    try:
        long_mid = _book_mid(long_ex, symbol)
        short_mid = _book_mid(short_ex, symbol)
        error = ""
    except Exception as exc:
        long_mid = 0.0
        short_mid = 0.0
        error = f"{type(exc).__name__}: {exc}"

    price_pnl = _pair_price_pnl_pct(pos, long_mid, short_mid)
    elapsed_frac = min(1.0, age_h / hold_h)
    funding_accrued = _f(pos.get("entry_expected_funding_pct_for_hold")) * elapsed_frac
    total_estimated = price_pnl + funding_accrued - _f(pos.get("entry_estimated_roundtrip_cost_pct"))
    current = current_by_key.get(str(pos.get("pair_key")))
    update = {
        "ts_utc": _utc_now(),
        "age_hours": round(age_h, 4),
        "long_mid": round(long_mid, 10),
        "short_mid": round(short_mid, 10),
        "price_pnl_pct_per_leg": round(price_pnl, 4),
        "price_pnl_pct_total_capital": round(price_pnl / 2.0, 4),
        "funding_accrued_est_pct": round(funding_accrued, 4),
        "total_estimated_pct_per_leg": round(total_estimated, 4),
        "total_estimated_pct_total_capital": round(total_estimated / 2.0, 4),
        "current_validated": bool(current and current.get("passed")),
        "current_net_pct_for_hold": current.get("estimated_net_pct_for_hold") if current else None,
        "error": error,
    }
    pos["last_update"] = update
    pos.setdefault("updates", []).append(update)
    pos["updates"] = pos["updates"][-96:]
    if age_h >= hold_h:
        pos["status"] = "closed"
        pos["closed_at_utc"] = _utc_now()
        pos["close_reason"] = "hold_time_elapsed"
        pos["final_estimated_pct_per_leg"] = update["total_estimated_pct_per_leg"]
        pos["final_estimated_pct_total_capital"] = update["total_estimated_pct_total_capital"]
    return pos


def run(args: argparse.Namespace) -> dict[str, Any]:
    validated_path = ROOT / args.validated_json
    state_path = ROOT / args.state_json
    validated = _load_json(validated_path, {})
    state = _load_json(state_path, {"open": [], "closed": []})
    items = validated.get("items") or []
    current_by_key = {str(x.get("pair_key")): x for x in items if x.get("pair_key")}

    open_positions = []
    closed_positions = list(state.get("closed") or [])[-500:]
    for pos in list(state.get("open") or []):
        updated = _update_position(pos, current_by_key)
        if updated.get("status") == "closed":
            closed_positions.append(updated)
        else:
            open_positions.append(updated)

    open_keys = {str(x.get("pair_key")) for x in open_positions}
    slots = max(0, int(args.max_open) - len(open_positions))
    opened = []
    for item in items:
        if slots <= 0:
            break
        key = str(item.get("pair_key") or "")
        if key in open_keys:
            continue
        if not item.get("passed"):
            continue
        if _f(item.get("estimated_net_pct_for_hold")) < float(args.min_net_pct):
            continue
        if int(_f(item.get("persistence_count_in_window"))) < int(args.min_persistence_count):
            continue
        try:
            pos = _open_position(item, args)
        except Exception as exc:
            print(f"[warn] open {key}: {type(exc).__name__}: {exc}")
            continue
        pos = _update_position(pos, current_by_key)
        open_positions.append(pos)
        open_keys.add(key)
        opened.append(pos)
        slots -= 1

    summary = {
        "generated_at_utc": _utc_now(),
        "source": str(Path(args.validated_json)),
        "open_count": len(open_positions),
        "closed_count": len(closed_positions),
        "opened_count": len(opened),
        "open_estimated_total_capital_pct": round(
            sum(_f((p.get("last_update") or {}).get("total_estimated_pct_total_capital")) for p in open_positions),
            4,
        ),
    }
    new_state = {
        **summary,
        "settings": {
            "notional_usd_per_leg": float(args.notional_usd),
            "hold_hours": float(args.hold_hours),
            "max_open": int(args.max_open),
            "min_net_pct": float(args.min_net_pct),
            "min_persistence_count": int(args.min_persistence_count),
        },
        "open": open_positions,
        "closed": closed_positions[-500:],
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(new_state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return new_state


def main() -> int:
    ap = argparse.ArgumentParser(description="Research-only paper shadow for cross-exchange funding candidates.")
    ap.add_argument("--validated-json", default="runtime/arb/cross_exchange_funding_validated.json")
    ap.add_argument("--state-json", default="runtime/arb/cross_exchange_funding_shadow.json")
    ap.add_argument("--notional-usd", type=float, default=100.0)
    ap.add_argument("--hold-hours", type=float, default=24.0)
    ap.add_argument("--max-open", type=int, default=5)
    ap.add_argument("--min-net-pct", type=float, default=0.20)
    ap.add_argument("--min-persistence-count", type=int, default=3)
    args = ap.parse_args()

    state = run(args)
    print(
        f"open={state['open_count']} closed={state['closed_count']} "
        f"opened={state['opened_count']} open_est_total_cap={state['open_estimated_total_capital_pct']}%"
    )
    for pos in state.get("open", [])[:10]:
        last = pos.get("last_update") or {}
        print(
            f"OPEN {pos.get('pair_key')} age={last.get('age_hours')}h "
            f"est_total_cap={last.get('total_estimated_pct_total_capital')}% "
            f"current_validated={last.get('current_validated')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
