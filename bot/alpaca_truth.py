"""Canonical Alpaca live-monthly truth projection for web and AI consumers."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ACTIVE_ORDER_STATUSES = {"accepted", "new", "pending_new", "partially_filled", "accepted_for_bidding"}
_STOP_ORDER_TYPES = {"stop", "stop_limit", "trailing_stop"}


def _json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        return {}
    return out


def _bool_env(value: Any) -> bool | None:
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def _age_sec(path: Path) -> int | None:
    try:
        return max(0, int(time.time() - path.stat().st_mtime))
    except Exception:
        return None


def _generated_age_sec(value: Any) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        age = time.time() - parsed.astimezone(timezone.utc).timestamp()
        if age < -300:
            return None
        return max(0, int(age))
    except (TypeError, ValueError, OverflowError):
        return None


def _float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number == number else None
    except Exception:
        return None


def _enrich_positions(positions: list[dict[str, Any]], open_stops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stop_by_symbol = {
        str(row.get("symbol") or "").strip().upper(): row
        for row in open_stops
        if str(row.get("symbol") or "").strip()
    }
    out: list[dict[str, Any]] = []
    for raw in positions:
        row = dict(raw or {})
        symbol = str(row.get("symbol") or "").strip().upper()
        qty = _float(row.get("qty"))
        market_value = _float(row.get("market_value"))
        current = (market_value / abs(qty)) if market_value is not None and qty not in {None, 0.0} else None
        stop = stop_by_symbol.get(symbol) or {}
        row.update(
            {
                "symbol": symbol,
                "entry_price": _float(row.get("avg_entry_price")),
                "last_price": current,
                "stop_price": _float(stop.get("stop_price")),
                "broker_stop_type": str(stop.get("type") or ""),
                "broker_stop_status": str(stop.get("status") or ""),
            }
        )
        out.append(row)
    return sorted(out, key=lambda row: str(row.get("symbol") or ""))


def _fallback_account_truth(payload: dict[str, Any]) -> dict[str, Any]:
    positions = [dict(row) for row in (payload.get("positions") or []) if isinstance(row, dict)]
    symbols = sorted({str(row.get("symbol") or "").strip().upper() for row in positions if str(row.get("symbol") or "").strip()})
    position_qty_by_symbol = {
        str(row.get("symbol") or "").strip().upper(): abs(_float(row.get("qty")) or 0.0)
        for row in positions
        if str(row.get("symbol") or "").strip()
    }
    stop_rows: list[dict[str, Any]] = []
    stop_symbols: set[str] = set()
    protected_qty_by_symbol: dict[str, float] = {}
    for raw in payload.get("open_orders") or []:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("symbol") or "").strip().upper()
        side = str(raw.get("side") or "").strip().lower()
        order_type = str(raw.get("type") or "").strip().lower()
        status = str(raw.get("status") or "").strip().lower()
        if symbol not in symbols or side != "sell" or order_type not in _STOP_ORDER_TYPES or status not in _ACTIVE_ORDER_STATUSES:
            continue
        stop_symbols.add(symbol)
        order_qty = abs(_float(raw.get("qty")) or 0.0)
        filled_qty = abs(_float(raw.get("filled_qty")) or 0.0)
        leaves_qty = _float(raw.get("leaves_qty"))
        protected_qty = abs(leaves_qty) if leaves_qty is not None else max(0.0, order_qty - filled_qty)
        protected_qty_by_symbol[symbol] = protected_qty_by_symbol.get(symbol, 0.0) + protected_qty
        stop_rows.append(
            {
                "symbol": symbol,
                "type": order_type,
                "status": status,
                "qty": str(raw.get("qty") or ""),
                "filled_qty": str(raw.get("filled_qty") or ""),
                "protected_remaining_qty": protected_qty,
                "stop_price": str(raw.get("stop_price") or ""),
                "trail_percent": str(raw.get("trail_percent") or ""),
            }
        )
    missing = sorted(set(symbols) - stop_symbols)
    underprotected: list[str] = []
    overprotected: list[str] = []
    fully_protected: list[str] = []
    for symbol in symbols:
        position_qty = position_qty_by_symbol.get(symbol, 0.0)
        protected_qty = protected_qty_by_symbol.get(symbol, 0.0)
        tolerance = max(1e-9, position_qty * 1e-6)
        if position_qty <= 0:
            if symbol in stop_symbols:
                underprotected.append(symbol)
        elif protected_qty + tolerance < position_qty:
            if symbol in stop_symbols:
                underprotected.append(symbol)
        elif protected_qty <= position_qty + tolerance:
            fully_protected.append(symbol)
        if protected_qty > position_qty + tolerance:
            overprotected.append(symbol)
    protection_gaps = sorted(set(missing) | set(underprotected) | set(overprotected))
    return {
        "generated_at_utc": str(payload.get("generated_at_utc") or ""),
        "account": dict(payload.get("account") or {}),
        "positions": positions,
        "open_stops": sorted(stop_rows, key=lambda row: row["symbol"]),
        "position_symbols": symbols,
        "stop_symbols": sorted(stop_symbols),
        "missing_stop_symbols": missing,
        "underprotected_stop_symbols": underprotected,
        "overprotected_stop_symbols": overprotected,
        "protection_gap_symbols": protection_gaps,
        "position_qty_by_symbol": position_qty_by_symbol,
        "protected_qty_by_symbol": protected_qty_by_symbol,
        "stop_coverage_count": len(fully_protected),
        "position_count": len(symbols),
        "stop_coverage_complete": not protection_gaps,
    }


def build_alpaca_live_truth(
    root: Path,
    *,
    runtime_root: Path | None = None,
    stale_after_sec: int = 26 * 3600,
) -> dict[str, Any]:
    """Prefer the manager's post-action receipt, then sanitized report state."""
    root = Path(root)
    runtime = Path(runtime_root) if runtime_root is not None else root / "runtime"
    receipt_path = runtime / "equities_monthly_v36" / "latest_manager_receipt.json"
    account_state_path = runtime / "alpaca_live_v38" / "account_state.json"
    safe_hold_env = _env(root / "configs" / "alpaca_live_v38_safe_hold.env")
    allow_new_entries = _bool_env(safe_hold_env.get("ALPACA_ALLOW_NEW_ENTRIES"))
    close_stale_positions = _bool_env(safe_hold_env.get("ALPACA_CLOSE_STALE_POSITIONS"))

    source = "missing"
    source_path = receipt_path
    report: dict[str, Any] = {}
    truth: dict[str, Any] = {}
    receipt = _json(receipt_path)
    if receipt:
        report = dict(receipt.get("report") or {})
        truth = dict(report.get("broker_truth_after") or {})
        if truth:
            source = "monthly_manager_post_action_receipt"
    if not truth:
        account_state = _json(account_state_path)
        if account_state:
            truth = _fallback_account_truth(account_state)
            source = "alpaca_live_v38_account_state"
            source_path = account_state_path

    generated_at = str(truth.get("generated_at_utc") or receipt.get("generated_at_utc") or "")
    age = _generated_age_sec(generated_at) if generated_at else _age_sec(source_path)
    freshness_basis = "generated_at_utc" if generated_at else "source_mtime"
    is_stale = age is None or age > max(1, int(stale_after_sec))
    receipt_authoritative = source != "monthly_manager_post_action_receipt" or bool(
        report.get("broker_truth_authoritative")
    )
    if allow_new_entries is False and close_stale_positions is False:
        mode = "SAFE_HOLD"
    elif allow_new_entries is True and close_stale_positions is True:
        mode = "MONTHLY_ROTATION"
    else:
        mode = "UNKNOWN_OR_MIXED"

    positions = list(truth.get("positions") or [])
    open_stops = list(truth.get("open_stops") or [])
    return {
        "source": source,
        "source_path": str(source_path),
        "exists": source != "missing",
        "generated_at_utc": generated_at,
        "age_sec": age,
        "freshness_basis": freshness_basis,
        "is_stale": is_stale,
        "authoritative": source != "missing" and not is_stale and receipt_authoritative,
        "mode": mode,
        "allow_new_entries": allow_new_entries,
        "close_stale_positions": close_stale_positions,
        "manager_status": str(report.get("status") or ""),
        "account": dict(truth.get("account") or {}),
        "positions": _enrich_positions(positions, open_stops),
        "open_stops": open_stops,
        "position_symbols": list(truth.get("position_symbols") or []),
        "stop_symbols": list(truth.get("stop_symbols") or []),
        "missing_stop_symbols": list(truth.get("missing_stop_symbols") or []),
        "underprotected_stop_symbols": list(truth.get("underprotected_stop_symbols") or []),
        "overprotected_stop_symbols": list(truth.get("overprotected_stop_symbols") or []),
        "protection_gap_symbols": list(
            truth.get("protection_gap_symbols")
            or truth.get("missing_stop_symbols")
            or []
        ),
        "position_qty_by_symbol": dict(truth.get("position_qty_by_symbol") or {}),
        "protected_qty_by_symbol": dict(truth.get("protected_qty_by_symbol") or {}),
        "stop_coverage_count": int(truth.get("stop_coverage_count") or 0),
        "position_count": int(truth.get("position_count") or 0),
        "stop_coverage_complete": bool(truth.get("stop_coverage_complete")),
        "recent_actions": list(report.get("results") or [])[-12:],
        "research_metrics_are_live_pnl": False,
    }
