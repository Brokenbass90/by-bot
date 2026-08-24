#!/usr/bin/env python3
"""Exit-only Alpaca stop ratchet for fractional SAFE_HOLD positions.

The process has no buy, rotation, or market-close code path.  It can only
replace an existing, quantity-covering broker stop with a higher stop after a
position has reached a configured profit.  Dry-run is the default; live order
replacement needs two independent environment acknowledgements.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import stat
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.equities_alpaca_paper_bridge import (  # noqa: E402
    AlpacaClient,
    _acquire_account_writer_lock,
    _alpaca_account_lock_path,
    _remaining_sell_order_qty,
)


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


def _load_state_strict(path: Path) -> tuple[dict[str, Any], str]:
    """Load the live HWM ledger without treating corruption as an empty book."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, "state_missing"
    except Exception as exc:
        return {}, f"state_read_error:{type(exc).__name__}"
    try:
        payload = json.loads(raw)
    except Exception as exc:
        return {}, f"state_json_error:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return {}, "state_root_not_object"
    return payload, ""


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


def _same_lifecycle_entry(previous: dict[str, Any], entry_price: float) -> bool:
    previous_entry = _f(previous.get("entry_price"), 0.0)
    if previous_entry <= 0 or entry_price <= 0:
        return False
    return abs(previous_entry - entry_price) <= max(0.01, entry_price * 1e-4)


def _confirmed_fixed_stop(
    order: dict[str, Any],
    *,
    symbol: str,
    position_qty: float,
) -> dict[str, Any]:
    order_symbol = str(order.get("symbol") or "").strip().upper()
    side = str(order.get("side") or "").strip().lower()
    order_type = str(order.get("type") or order.get("order_type") or "").strip().lower()
    status = str(order.get("status") or "").strip().lower()
    remaining = _remaining_sell_order_qty(order)
    stop_price = _f(order.get("stop_price"), 0.0)
    tolerance = max(1e-9, position_qty * 1e-6)
    if (
        order_symbol != symbol.strip().upper()
        or side != "sell"
        or order_type not in {"stop", "stop_limit"}
        or status not in OPEN_ORDER_STATUSES
        or abs(remaining - position_qty) > tolerance
        or stop_price <= 0
    ):
        return {}
    return {
        "order_id": str(order.get("id") or ""),
        "stop_price": stop_price,
        "time_in_force": str(order.get("time_in_force") or "").lower(),
        "status": status,
        "protected_qty": remaining,
    }


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
        same_lifecycle = _same_lifecycle_entry(previous, entry)
        previous_hwm = _f(previous.get("hwm"), current) if same_lifecycle else current
        first_seen = (
            str(previous.get("lifecycle_first_seen_at_utc") or now)
            if same_lifecycle
            else now
        )
        next_state[symbol] = {
            "hwm": max(current, previous_hwm),
            "entry_price": entry,
            "qty": qty,
            "lifecycle_first_seen_at_utc": first_seen,
            "accepted_stop_floor": (
                max(0.0, _f(previous.get("accepted_stop_floor"), 0.0))
                if same_lifecycle
                else 0.0
            ),
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
        if len(rows) == 1:
            observed = _confirmed_fixed_stop(
                rows[0],
                symbol=symbol,
                position_qty=qty,
            )
            if observed:
                state_row = next_state[symbol]
                state_row["accepted_stop_floor"] = max(
                    _f(state_row.get("accepted_stop_floor"), 0.0),
                    _f(observed.get("stop_price"), 0.0),
                )
                state_row["accepted_order_id"] = observed["order_id"]
                state_row["accepted_order_tif"] = observed["time_in_force"]
                state_row["accepted_observed_at_utc"] = now
        base = {
            "symbol": symbol,
            "qty": qty,
            "entry_price": entry,
            "current_price": current,
            "hwm": hwm,
            "peak_gain_pct": round(peak_gain_pct, 6),
            "accepted_stop_floor": _f(
                (next_state.get(symbol) or {}).get("accepted_stop_floor"),
                0.0,
            ),
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
        accepted_floor = _f(
            (next_state.get(symbol) or {}).get("accepted_stop_floor"),
            0.0,
        )
        trail_floor = hwm * (1.0 - trail_pct / 100.0)
        locked_floor = entry * (1.0 + min_lock_gain_pct / 100.0)
        market_ceiling = current * (1.0 - market_gap_bps / 10000.0)
        if accepted_floor > 0 and market_ceiling + 1e-12 < accepted_floor:
            plan.append(
                {
                    **base,
                    "action": "escalate_below_accepted_floor",
                    "reason": "market_below_broker_accepted_floor",
                    "current_stop": current_stop,
                    "market_ceiling": float(_format_price(market_ceiling)),
                }
            )
            continue
        target_stop = min(
            max(current_stop, accepted_floor, trail_floor, locked_floor),
            market_ceiling,
        )
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


def _main_unlocked() -> int:
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
    prior_state, state_error = _load_state_strict(state_path)
    if state_error and positions:
        print(
            json.dumps(
                {
                    "error": "protective_hwm_state_not_authoritative",
                    "state_path": str(state_path),
                    "state_error": state_error,
                    "position_count": len(positions),
                }
            ),
            file=sys.stderr,
        )
        return 7
    plan, next_state = build_ratchet_plan(
        positions,
        orders,
        prior_state,
        activate_gain_pct=max(0.0, _f(os.getenv("ALPACA_PROTECTIVE_TRAIL_ACTIVATE_GAIN_PCT"), 3.5)),
        trail_pct=max(0.1, _f(os.getenv("ALPACA_PROTECTIVE_TRAIL_PCT"), 3.5)),
        min_lock_gain_pct=max(0.0, _f(os.getenv("ALPACA_PROTECTIVE_MIN_LOCK_GAIN_PCT"), 0.5)),
        min_raise_bps=max(0.0, _f(os.getenv("ALPACA_PROTECTIVE_MIN_RAISE_BPS"), 10.0)),
        market_gap_bps=max(1.0, _f(os.getenv("ALPACA_PROTECTIVE_MARKET_GAP_BPS"), 10.0)),
        excluded_symbols=excluded,
    )
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
            new_order_id = str(result.get("id") or "")
            if not new_order_id:
                raise RuntimeError("replacement_missing_new_order_id")
            confirmed_order = client.get_order(new_order_id)
            confirmed = _confirmed_fixed_stop(
                confirmed_order,
                symbol=str(row["symbol"]),
                position_qty=float(row["qty"]),
            )
            if not confirmed:
                raise RuntimeError("replacement_not_confirmed_by_broker_readback")
            confirmed_stop = _f(confirmed.get("stop_price"), 0.0)
            if confirmed_stop + 1e-12 < float(row["target_stop"]):
                raise RuntimeError("replacement_confirmed_below_target_stop")
            state_row = next_state.get(str(row["symbol"]))
            if isinstance(state_row, dict):
                state_row["accepted_stop_floor"] = max(
                    _f(state_row.get("accepted_stop_floor"), 0.0),
                    confirmed_stop,
                )
                state_row["accepted_order_id"] = confirmed["order_id"]
                state_row["accepted_order_tif"] = confirmed["time_in_force"]
                state_row["accepted_observed_at_utc"] = datetime.now(timezone.utc).isoformat()
            applied.append({
                "symbol": row["symbol"],
                "status": "confirmed",
                "old_order_id": order_id,
                "new_order_id": new_order_id,
                "target_stop": row["target_stop"],
                "confirmed_stop": confirmed_stop,
                "confirmed_tif": confirmed["time_in_force"],
            })
        except Exception as exc:
            applied.append({"symbol": row["symbol"], "status": "error", "error": str(exc)[:500]})

    _write_json_atomic(state_path, next_state)
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
    result_failed = any(
        row.get("status") in {"error", "blocked"}
        for row in applied
    )
    plan_failed = any(
        row.get("action") in {"blocked", "escalate_below_accepted_floor"}
        for row in plan
    )
    return 1 if result_failed or plan_failed else 0


def main() -> int:
    """Serialize bridge and ratchet mutations with one per-account lock."""
    key = os.getenv("ALPACA_API_KEY_ID", "").strip()
    base_url = os.getenv("ALPACA_BASE_URL", "https://api.alpaca.markets").strip().rstrip("/")
    lock_path = _alpaca_account_lock_path(base_url, key)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            print("error=alpaca_writer_lock_not_regular_file", file=sys.stderr)
            return 6
        if not _acquire_account_writer_lock(
            fd,
            _f(os.getenv("ALPACA_WRITER_LOCK_WAIT_SEC"), 60.0),
        ):
            print(json.dumps({"status": "failed", "reason": "alpaca_writer_lock_timeout"}))
            return 75
        return _main_unlocked()
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
