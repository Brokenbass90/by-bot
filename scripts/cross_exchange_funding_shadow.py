#!/usr/bin/env python3
"""Conservative paper-shadow for cross-exchange funding candidates.

Research-only. Opens virtual pair trades from
`cross_exchange_funding_validated.json`, tracks executable exit prices and only
credits funding after a settlement boundary is crossed. It closes virtual
positions after a fixed hold.

No private keys, no orders, no account access.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from cross_exchange_funding_validate import _entry_leg, fetch_orderbook
except ImportError:
    from scripts.cross_exchange_funding_validate import _entry_leg, fetch_orderbook


ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = "settlement_execution_v2"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Replace a JSON state file atomically after a durable temporary write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc_epoch(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _cooldown_pair_keys(
    closed_positions: list[dict[str, Any]],
    *,
    now: float,
    cooldown_hours: float,
) -> set[str]:
    if cooldown_hours <= 0:
        return set()
    cutoff = now - cooldown_hours * 3600.0
    out: set[str] = set()
    for pos in closed_positions:
        closed_epoch = _f(pos.get("closed_at_epoch"))
        if closed_epoch <= 0:
            closed_epoch = _parse_utc_epoch(pos.get("closed_at_utc"))
        if closed_epoch >= cutoff:
            key = str(pos.get("pair_key") or "")
            if key:
                out.add(key)
    return out


def _update_validation_evidence(pos: dict[str, Any], update: dict[str, Any]) -> None:
    """Count only explicit validator failures; top-N absence is not failure."""
    observed = bool(update.get("current_observed"))
    passed = bool(update.get("current_validated"))
    if observed and passed:
        pos["validation_fail_streak"] = 0
        pos["validation_missing_streak"] = 0
        pos["last_validated_at_utc"] = str(update.get("ts_utc") or _utc_now())
    elif observed:
        pos["validation_fail_streak"] = int(pos.get("validation_fail_streak") or 0) + 1
        pos["validation_missing_streak"] = 0
    else:
        pos["validation_missing_streak"] = int(pos.get("validation_missing_streak") or 0) + 1


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _execution_leg(exchange: str, symbol: str, side: str, notional_usd: float) -> dict[str, Any]:
    book = fetch_orderbook(exchange, symbol, limit=20)
    leg = _entry_leg(book, side, notional_usd)
    if not leg.get("filled") or _f(leg.get("avg_price")) <= 0:
        raise RuntimeError(f"insufficient {exchange} {symbol} {side} depth")
    return leg


def _execution_leg_for_qty(exchange: str, symbol: str, side: str, qty: float) -> dict[str, Any]:
    book = fetch_orderbook(exchange, symbol, limit=20)
    levels = book.bids if side == "sell" else book.asks
    if side not in {"sell", "buy"} or qty <= 0 or not levels:
        raise RuntimeError(f"invalid {exchange} {symbol} {side} close request")
    best = levels[0][0]
    remaining = qty
    filled_qty = 0.0
    filled_notional = 0.0
    for price, available_qty in levels:
        take_qty = min(remaining, available_qty)
        filled_qty += take_qty
        filled_notional += take_qty * price
        remaining -= take_qty
        if remaining <= max(1e-12, qty * 0.001):
            break
    if filled_qty <= 0 or remaining > max(1e-12, qty * 0.001):
        raise RuntimeError(f"insufficient {exchange} {symbol} {side} close depth")
    avg = filled_notional / filled_qty
    slip_bps = (
        ((best / avg) - 1.0) * 10_000.0
        if side == "sell"
        else ((avg / best) - 1.0) * 10_000.0
    )
    return {
        "filled": True,
        "best_price": round(best, 8),
        "avg_price": round(avg, 8),
        "filled_qty": filled_qty,
        "filled_notional_usd": filled_notional,
        "slippage_bps": round(max(0.0, slip_bps), 4),
    }


def _pair_price_pnl_pct(pos: dict[str, Any], long_exit: float, short_exit: float) -> float:
    long_entry = _f(pos.get("long_entry_exec"))
    short_entry = _f(pos.get("short_entry_exec"))
    if long_entry <= 0 or short_entry <= 0 or long_exit <= 0 or short_exit <= 0:
        return 0.0
    long_ret = (long_exit / long_entry - 1.0) * 100.0
    short_ret = ((short_entry - short_exit) / short_entry) * 100.0
    return long_ret + short_ret


def _aligned_next_epoch(now: float, interval_h: float) -> float:
    period = max(1.0, interval_h) * 3600.0
    return (math.floor(now / period) + 1.0) * period


def _next_funding_epoch(next_ms: Any, now: float, interval_h: float) -> float:
    interval_s = max(1.0, interval_h) * 3600.0
    next_epoch = _f(next_ms) / 1000.0
    if next_epoch <= 0:
        return _aligned_next_epoch(now, interval_h)
    while next_epoch <= now:
        next_epoch += interval_s
    return next_epoch


def _settle_funding(pos: dict[str, Any], current: dict[str, Any] | None, now: float) -> float:
    accrued = _f(pos.get("funding_settled_pct_per_leg"))
    events = list(pos.get("funding_events") or [])
    for prefix, direction in (("short", 1.0), ("long", -1.0)):
        interval_h = max(1.0, _f(pos.get(f"{prefix}_funding_interval_h"), 8.0))
        next_key = f"{prefix}_next_funding_epoch"
        next_epoch = _f(pos.get(next_key))
        if next_epoch <= 0:
            next_epoch = _aligned_next_epoch(_f(pos.get("opened_at_epoch"), now), interval_h)
        event_count = 0
        while next_epoch <= now and event_count < 24:
            # Funding is fixed shortly before settlement. Credit the latest
            # pre-settlement snapshot stored on the position, not the current
            # post-settlement quote. If the worker missed multiple events,
            # credit only the first and zero the rest.
            pending_key = f"{prefix}_pending_funding_event_pct"
            rate_pct = _f(pos.get(pending_key)) if event_count == 0 else 0.0
            cash_pct = direction * rate_pct
            accrued += cash_pct
            events.append(
                {
                    "ts_epoch": round(next_epoch, 3),
                    "ts_utc": datetime.fromtimestamp(next_epoch, timezone.utc).isoformat(),
                    "leg": prefix,
                    "rate_pct": round(rate_pct, 6),
                    "cash_pct_per_leg": round(cash_pct, 6),
                    "source": "latest_pre_settlement_snapshot" if event_count == 0 else "missed_interval_zero_credit",
                }
            )
            next_epoch += interval_h * 3600.0
            event_count += 1
        pos[next_key] = next_epoch
        if current:
            pos[f"{prefix}_pending_funding_event_pct"] = _f(current.get(f"{prefix}_funding_event_pct"))
        else:
            pos[f"{prefix}_pending_funding_event_pct"] = 0.0
    pos["funding_settled_pct_per_leg"] = round(accrued, 8)
    pos["funding_events"] = events[-100:]
    return accrued


def _open_position(item: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    symbol = str(item.get("symbol") or "").upper()
    long_ex = str(item.get("long_exchange") or "").lower()
    short_ex = str(item.get("short_exchange") or "").lower()
    long_leg = _execution_leg(long_ex, symbol, "long", float(args.notional_usd))
    short_leg = _execution_leg(short_ex, symbol, "short", float(args.notional_usd))
    now = time.time()
    long_interval_h = max(1.0, _f(item.get("long_funding_interval_h"), 8.0))
    short_interval_h = max(1.0, _f(item.get("short_funding_interval_h"), 8.0))
    return {
        "model_version": MODEL_VERSION,
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
        "long_entry_exec": _f(long_leg.get("avg_price")),
        "short_entry_exec": _f(short_leg.get("avg_price")),
        "long_entry_qty": _f(long_leg.get("filled_notional_usd")) / _f(long_leg.get("avg_price"), 1.0),
        "short_entry_qty": _f(short_leg.get("filled_notional_usd")) / _f(short_leg.get("avg_price"), 1.0),
        "long_entry_slippage_bps": _f(long_leg.get("slippage_bps")),
        "short_entry_slippage_bps": _f(short_leg.get("slippage_bps")),
        "entry_spread_monthly_pct": _f(item.get("spread_monthly_pct")),
        "entry_expected_funding_pct_for_hold": _f(item.get("expected_funding_pct_for_hold")),
        "entry_estimated_roundtrip_cost_pct": _f(item.get("estimated_roundtrip_cost_pct")),
        "fee_cost_pct_per_leg": _f(
            item.get("estimated_fee_cost_pct_per_leg"),
            (4.0 * float(args.taker_fee_bps)) / 100.0,
        ),
        "entry_estimated_net_pct_for_hold": _f(item.get("estimated_net_pct_for_hold")),
        "entry_persistence_count": int(_f(item.get("persistence_count_in_window"))),
        "short_funding_interval_h": short_interval_h,
        "long_funding_interval_h": long_interval_h,
        "short_next_funding_epoch": _next_funding_epoch(item.get("short_next_funding_ms"), now, short_interval_h),
        "long_next_funding_epoch": _next_funding_epoch(item.get("long_next_funding_ms"), now, long_interval_h),
        "short_pending_funding_event_pct": _f(item.get("short_funding_event_pct")),
        "long_pending_funding_event_pct": _f(item.get("long_funding_event_pct")),
        "funding_settled_pct_per_leg": 0.0,
        "funding_events": [],
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
        long_exit_leg = _execution_leg_for_qty(long_ex, symbol, "sell", _f(pos.get("long_entry_qty")))
        short_exit_leg = _execution_leg_for_qty(short_ex, symbol, "buy", _f(pos.get("short_entry_qty")))
        long_exit = _f(long_exit_leg.get("avg_price"))
        short_exit = _f(short_exit_leg.get("avg_price"))
        error = ""
    except Exception as exc:
        long_exit = 0.0
        short_exit = 0.0
        long_exit_leg = {}
        short_exit_leg = {}
        error = f"{type(exc).__name__}: {exc}"

    current = current_by_key.get(str(pos.get("pair_key")))
    funding_settled = _settle_funding(pos, current, now)
    price_pnl = _pair_price_pnl_pct(pos, long_exit, short_exit)
    total_shadow = price_pnl + funding_settled - _f(pos.get("fee_cost_pct_per_leg"))
    update = {
        "ts_utc": _utc_now(),
        "age_hours": round(age_h, 4),
        "long_exit_exec": round(long_exit, 10),
        "short_exit_exec": round(short_exit, 10),
        "long_exit_slippage_bps": _f(long_exit_leg.get("slippage_bps")),
        "short_exit_slippage_bps": _f(short_exit_leg.get("slippage_bps")),
        "price_pnl_pct_per_leg": round(price_pnl, 4),
        "price_pnl_pct_total_capital": round(price_pnl / 2.0, 4),
        "funding_settled_pct_per_leg": round(funding_settled, 4),
        "fee_cost_pct_per_leg": round(_f(pos.get("fee_cost_pct_per_leg")), 4),
        "total_shadow_pct_per_leg": round(total_shadow, 4),
        "total_shadow_pct_total_capital": round(total_shadow / 2.0, 4),
        "current_observed": current is not None,
        "current_validated": bool(current and current.get("passed")),
        "current_net_pct_for_hold": current.get("estimated_net_pct_for_hold") if current else None,
        "error": error,
    }
    historical_markouts = [
        _f(row.get("total_shadow_pct_total_capital"))
        for row in list(pos.get("updates") or [])
        if row.get("total_shadow_pct_total_capital") is not None
    ]
    historical_markouts.append(_f(update.get("total_shadow_pct_total_capital")))
    # Persist MAE before any future stop threshold is selected.  The current
    # paper lifecycle remains unchanged; this is evidence for a separately
    # preregistered basis/markout breaker, not a post-hoc close rule.
    pos["worst_markout_pct_total_capital"] = round(min(historical_markouts), 4)
    pos["last_update"] = update
    pos.setdefault("updates", []).append(update)
    pos["updates"] = pos["updates"][-96:]
    if age_h >= hold_h:
        pos["status"] = "closed"
        pos["closed_at_utc"] = _utc_now()
        pos["closed_at_epoch"] = now
        pos["close_reason"] = "hold_time_elapsed"
        pos["final_shadow_pct_per_leg"] = update["total_shadow_pct_per_leg"]
        pos["final_shadow_pct_total_capital"] = update["total_shadow_pct_total_capital"]
        pos["final_worst_markout_pct_total_capital"] = pos[
            "worst_markout_pct_total_capital"
        ]
    return pos


def run(args: argparse.Namespace) -> dict[str, Any]:
    validated_path = ROOT / args.validated_json
    state_path = ROOT / args.state_json
    validated = _load_json(validated_path, {})
    state = _load_json(state_path, {"open": [], "closed": []})
    legacy_reset = bool(state and state.get("model_version") != MODEL_VERSION)
    if legacy_reset:
        state = {"open": [], "closed": []}
    items = validated.get("items") or []
    current_by_key = {str(x.get("pair_key")): x for x in items if x.get("pair_key")}

    open_positions = []
    closed_positions = list(state.get("closed") or [])[-500:]
    for pos in list(state.get("open") or []):
        updated = _update_position(pos, current_by_key)
        last = updated.get("last_update") or {}
        _update_validation_evidence(updated, last)
        close_invalid_after_h = float(args.close_invalid_after_hours)
        if (
            updated.get("status") != "closed"
            and close_invalid_after_h > 0
            and bool(last.get("current_observed"))
            and int(updated.get("validation_fail_streak") or 0) >= int(args.close_invalid_count)
            and _f(last.get("age_hours")) >= close_invalid_after_h
        ):
            updated["status"] = "closed"
            updated["closed_at_utc"] = _utc_now()
            updated["closed_at_epoch"] = time.time()
            updated["close_reason"] = "current_validation_lost"
            updated["final_shadow_pct_per_leg"] = last.get("total_shadow_pct_per_leg")
            updated["final_shadow_pct_total_capital"] = last.get("total_shadow_pct_total_capital")
        if updated.get("status") == "closed":
            closed_positions.append(updated)
        else:
            open_positions.append(updated)

    open_keys = {str(x.get("pair_key")) for x in open_positions}
    cooldown_keys = _cooldown_pair_keys(
        closed_positions,
        now=time.time(),
        cooldown_hours=float(args.reentry_cooldown_hours),
    )
    slots = max(0, int(args.max_open) - len(open_positions))
    opened = []
    for item in items:
        if slots <= 0:
            break
        key = str(item.get("pair_key") or "")
        if key in open_keys or key in cooldown_keys:
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
        _update_validation_evidence(pos, pos.get("last_update") or {})
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
            sum(_f((p.get("last_update") or {}).get("total_shadow_pct_total_capital")) for p in open_positions),
            4,
        ),
        "open_shadow_total_capital_pct": round(
            sum(_f((p.get("last_update") or {}).get("total_shadow_pct_total_capital")) for p in open_positions),
            4,
        ),
        "model_version": MODEL_VERSION,
        "legacy_model_reset": legacy_reset,
    }
    new_state = {
        **summary,
        "settings": {
            "notional_usd_per_leg": float(args.notional_usd),
            "hold_hours": float(args.hold_hours),
            "max_open": int(args.max_open),
            "min_net_pct": float(args.min_net_pct),
            "min_persistence_count": int(args.min_persistence_count),
            "taker_fee_bps": float(args.taker_fee_bps),
            "close_invalid_after_hours": float(args.close_invalid_after_hours),
            "close_invalid_count": int(args.close_invalid_count),
            "reentry_cooldown_hours": float(args.reentry_cooldown_hours),
        },
        "open": open_positions,
        "closed": closed_positions[-500:],
    }
    _write_json_atomic(state_path, new_state)
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
    ap.add_argument("--taker-fee-bps", type=float, default=6.0)
    ap.add_argument(
        "--close-invalid-after-hours",
        type=float,
        default=0.0,
        help="Research-only: close paper positions once they are no longer validated for this many hours. 0 disables.",
    )
    ap.add_argument(
        "--close-invalid-count",
        type=int,
        default=3,
        help="Require this many consecutive explicit validator failures before invalidation close.",
    )
    ap.add_argument(
        "--reentry-cooldown-hours",
        type=float,
        default=6.0,
        help="Do not reopen the same pair until this many hours after a paper close.",
    )
    args = ap.parse_args()
    if args.close_invalid_count < 1:
        ap.error("--close-invalid-count must be at least 1")
    if args.reentry_cooldown_hours < 0:
        ap.error("--reentry-cooldown-hours must be non-negative")

    state = run(args)
    print(
        f"open={state['open_count']} closed={state['closed_count']} "
        f"opened={state['opened_count']} open_est_total_cap={state['open_estimated_total_capital_pct']}%"
    )
    for pos in state.get("open", [])[:10]:
        last = pos.get("last_update") or {}
        print(
            f"OPEN {pos.get('pair_key')} age={last.get('age_hours')}h "
            f"shadow_total_cap={last.get('total_shadow_pct_total_capital')}% "
            f"current_validated={last.get('current_validated')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
