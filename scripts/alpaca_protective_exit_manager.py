#!/usr/bin/env python3
"""Exit-only Alpaca stop ratchet for fractional SAFE_HOLD positions.

The process has no buy, rotation, or market-close code path.  It can only
replace an existing, quantity-covering broker stop with a higher stop after a
position has reached a configured profit.  Dry-run is the default; live order
replacement needs two independent environment acknowledgements.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.equities_alpaca_paper_bridge import AlpacaClient  # noqa: E402


OPEN_ORDER_STATUSES = {"new", "accepted", "pending_new", "partially_filled", "held"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _format_price(price: float) -> str:
    """Format an Alpaca equity stop on the broker's legal price grid.

    Alpaca accepts at most two decimals at or above $1 and four decimals below
    $1.  Round a sell stop down so quantization cannot move it above the
    already-checked market ceiling.
    """
    value = Decimal(str(max(0.0, price)))
    quantum = Decimal("0.01") if value >= Decimal("1") else Decimal("0.0001")
    return format(value.quantize(quantum, rounding=ROUND_DOWN), "f")


def build_stop_replace_payload(target_stop: float) -> dict[str, str]:
    """Raise only the stop price while preserving the broker order quantity.

    Alpaca accepts an existing fractional stop order, but its replace endpoint
    rejects a fractional ``qty`` field with ``qty must be an integer``.  The
    plan already verifies that the existing order covers the whole position,
    so resending quantity is both unnecessary and harmful.
    """
    return {"stop_price": _format_price(target_stop)}


def build_ratchet_plan(
    positions: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    hwm_state: dict[str, Any],
    *,
    activate_gain_pct: float,
    trail_pct: float,
    min_lock_gain_pct: float,
    min_raise_bps: float,
    market_gap_bps: float,
    excluded_symbols: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return deterministic stop replacements and the updated HWM state."""
    excluded = {s.upper() for s in (excluded_symbols or set())}
    now = datetime.now(timezone.utc).isoformat()
    positions_by_symbol: dict[str, dict[str, Any]] = {}
    for raw in positions:
        symbol = str(raw.get("symbol") or "").upper()
        if symbol and symbol not in excluded:
            positions_by_symbol[symbol] = raw

    next_state: dict[str, Any] = {}
    for symbol, pos in positions_by_symbol.items():
        current = _f(pos.get("current_price"))
        entry = _f(pos.get("avg_entry_price"))
        qty = abs(_f(pos.get("qty")))
        if current <= 0 or entry <= 0 or qty <= 0:
            continue
        previous = hwm_state.get(symbol) if isinstance(hwm_state.get(symbol), dict) else {}
        previous_hwm = _f(previous.get("hwm"), current)
        next_state[symbol] = {
            "hwm": max(current, previous_hwm),
            "entry_price": entry,
            "qty": qty,
            "updated_at_utc": now,
        }

    stops_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for order in orders:
        symbol = str(order.get("symbol") or "").upper()
        status = str(order.get("status") or "").lower()
        side = str(order.get("side") or "").lower()
        order_type = str(order.get("type") or order.get("order_type") or "").lower()
        if symbol and side == "sell" and order_type in {"stop", "stop_limit"} and status in OPEN_ORDER_STATUSES:
            stops_by_symbol.setdefault(symbol, []).append(order)

    plan: list[dict[str, Any]] = []
    for symbol, pos in sorted(positions_by_symbol.items()):
        current = _f(pos.get("current_price"))
        entry = _f(pos.get("avg_entry_price"))
        qty = abs(_f(pos.get("qty")))
        hwm = _f((next_state.get(symbol) or {}).get("hwm"), current)
        peak_gain_pct = (hwm / entry - 1.0) * 100.0 if entry > 0 else 0.0
        rows = stops_by_symbol.get(symbol, [])
        base = {
            "symbol": symbol,
            "qty": qty,
            "entry_price": entry,
            "current_price": current,
            "hwm": hwm,
            "peak_gain_pct": round(peak_gain_pct, 6),
        }
        if peak_gain_pct + 1e-9 < activate_gain_pct:
            plan.append({**base, "action": "hold", "reason": "trail_not_armed"})
            continue
        if len(rows) != 1:
            plan.append({**base, "action": "blocked", "reason": f"expected_one_stop_found_{len(rows)}"})
            continue
        order = rows[0]
        protected_qty = max(0.0, _f(order.get("qty")) - _f(order.get("filled_qty")))
        if protected_qty + 1e-8 < qty:
            plan.append({**base, "action": "blocked", "reason": "stop_under_covers_position"})
            continue
        current_stop = _f(order.get("stop_price"))
        if current_stop <= 0:
            plan.append({**base, "action": "blocked", "reason": "missing_stop_price"})
            continue
        trail_floor = hwm * (1.0 - trail_pct / 100.0)
        locked_floor = entry * (1.0 + min_lock_gain_pct / 100.0)
        market_ceiling = current * (1.0 - market_gap_bps / 10000.0)
        target_stop = min(max(current_stop, trail_floor, locked_floor), market_ceiling)
        target_stop = float(_format_price(target_stop))
        min_raise = current_stop * (1.0 + min_raise_bps / 10000.0)
        if target_stop + 1e-12 < min_raise:
            plan.append({**base, "action": "hold", "reason": "no_material_stop_raise", "current_stop": current_stop})
            continue
        plan.append({
            **base,
            "action": "replace_stop",
            "order_id": str(order.get("id") or ""),
            "current_stop": current_stop,
            "target_stop": round(target_stop, 8),
            "protected_qty": protected_qty,
            "time_in_force": str(order.get("time_in_force") or "gtc").lower(),
            "locked_gain_pct_at_stop": round((target_stop / entry - 1.0) * 100.0, 6),
        })
    return plan, next_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Alpaca protective-exits-only stop ratchet")
    parser.add_argument("--apply", action="store_true", help="Apply broker stop replacements after env acknowledgements")
    args = parser.parse_args()

    key = os.getenv("ALPACA_API_KEY_ID", "").strip()
    secret = os.getenv("ALPACA_API_SECRET_KEY", "").strip()
    base_url = os.getenv("ALPACA_BASE_URL", "https://api.alpaca.markets").strip().rstrip("/")
    if not key or not secret:
        print("error=missing_alpaca_credentials", file=sys.stderr)
        return 2

    apply_requested = bool(args.apply or _env_bool("ALPACA_PROTECTIVE_EXIT_APPLY", False))
    ack = os.getenv("ALPACA_PROTECTIVE_EXIT_ACK", "").strip()
    if apply_requested and ack != "PROTECTIVE_EXITS_ONLY":
        print("error=missing_protective_exit_ack", file=sys.stderr)
        return 3
    if apply_requested and base_url != "https://api.alpaca.markets":
        print("error=apply_requires_live_alpaca_endpoint", file=sys.stderr)
        return 4
    if apply_requested and _env_bool("ALPACA_ALLOW_NEW_ENTRIES", True):
        print("error=protective_manager_requires_new_entries_off", file=sys.stderr)
        return 5

    runtime_dir = Path(os.getenv("ALPACA_PROTECTIVE_EXIT_RUNTIME_DIR", str(ROOT / "runtime" / "alpaca_live_v38")))
    state_path = Path(os.getenv("ALPACA_PROTECTIVE_EXIT_HWM_PATH", str(runtime_dir / "protective_exit_hwm.json")))
    receipt_path = Path(os.getenv("ALPACA_PROTECTIVE_EXIT_RECEIPT_PATH", str(runtime_dir / "protective_exit_latest.json")))
    excluded = {s.strip().upper() for s in os.getenv("ALPACA_PROTECTIVE_EXIT_EXCLUDED_SYMBOLS", "").split(",") if s.strip()}

    client = AlpacaClient(base_url, key, secret)
    account = client.get_account()
    clock = client.get_clock()
    positions = client.list_positions()
    orders = client.list_orders(status="open", limit=200)
    plan, next_state = build_ratchet_plan(
        positions,
        orders,
        _load_json(state_path),
        activate_gain_pct=max(0.0, _f(os.getenv("ALPACA_PROTECTIVE_TRAIL_ACTIVATE_GAIN_PCT"), 3.5)),
        trail_pct=max(0.1, _f(os.getenv("ALPACA_PROTECTIVE_TRAIL_PCT"), 3.5)),
        min_lock_gain_pct=max(0.0, _f(os.getenv("ALPACA_PROTECTIVE_MIN_LOCK_GAIN_PCT"), 0.5)),
        min_raise_bps=max(0.0, _f(os.getenv("ALPACA_PROTECTIVE_MIN_RAISE_BPS"), 10.0)),
        market_gap_bps=max(1.0, _f(os.getenv("ALPACA_PROTECTIVE_MARKET_GAP_BPS"), 10.0)),
        excluded_symbols=excluded,
    )
    _write_json_atomic(state_path, next_state)

    applied: list[dict[str, Any]] = []
    market_open = bool(clock.get("is_open"))
    account_blocked = bool(account.get("trading_blocked") or account.get("account_blocked"))
    for row in plan:
        if row.get("action") != "replace_stop":
            continue
        if not apply_requested:
            applied.append({"symbol": row["symbol"], "status": "dry_run"})
            continue
        if not market_open or account_blocked:
            applied.append({"symbol": row["symbol"], "status": "blocked", "reason": "market_closed_or_account_blocked"})
            continue
        order_id = str(row.get("order_id") or "")
        if not order_id:
            applied.append({"symbol": row["symbol"], "status": "blocked", "reason": "missing_order_id"})
            continue
        try:
            result = client.replace_order(
                order_id,
                build_stop_replace_payload(float(row["target_stop"])),
            )
            applied.append({
                "symbol": row["symbol"],
                "status": str(result.get("status") or "accepted"),
                "old_order_id": order_id,
                "new_order_id": str(result.get("id") or ""),
                "target_stop": row["target_stop"],
            })
        except Exception as exc:
            applied.append({"symbol": row["symbol"], "status": "error", "error": str(exc)[:500]})

    receipt = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if apply_requested else "dry_run",
        "authority": "protective_exits_only_no_buys_no_rotation_no_market_close",
        "market_open": market_open,
        "account_blocked": account_blocked,
        "positions": len(positions),
        "open_orders": len(orders),
        "plan": plan,
        "results": applied,
    }
    _write_json_atomic(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return 1 if any(row.get("status") == "error" for row in applied) else 0


if __name__ == "__main__":
    raise SystemExit(main())
