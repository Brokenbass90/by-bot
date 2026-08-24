#!/usr/bin/env python3
"""Deterministic, read-only Alpaca protection and operations auditor.

The auditor may perform broker GET requests through
``check_alpaca_state_readonly`` and may write a local receipt.  It has no order,
cancel, replace, close-position, or money-authority path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib import parse, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


ACTIVE_ORDER_STATUSES = {
    "accepted",
    "held",
    "new",
    "partially_filled",
    "pending_new",
    "pending_replace",
}
PROTECTIVE_TYPES = {"stop", "stop_limit", "trailing_stop"}
BROKER_TRUTH_SCHEMA = "alpaca_broker_truth_readonly_v1"
OPERATIONS_AUTHORITY = "calculated_local_files_and_logs"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_json_object(path: Path) -> dict[str, Any]:
    """Return the latest JSON object from a line-oriented mixed log."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for raw in reversed(lines[-200:]):
        text = raw.strip()
        if not text.startswith("{"):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _env_bool_from_files(paths: Iterable[Path], key: str) -> bool | None:
    found: bool | None = None
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() != key:
                continue
            normalized = value.strip().strip("'\"").lower()
            found = normalized in {"1", "true", "yes", "on"}
    return found


def _schedule_active(schedule: dict[str, Any], now_utc: datetime) -> bool:
    weekdays = schedule.get("weekdays_utc")
    allowed = {int(value) for value in weekdays} if isinstance(weekdays, list) else set()
    if now_utc.weekday() not in allowed:
        return False

    def minute_of_day(value: Any) -> int | None:
        parts = str(value or "").split(":")
        if len(parts) != 2:
            return None
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return None
        return hour * 60 + minute

    start = minute_of_day(schedule.get("start_utc"))
    end = minute_of_day(schedule.get("end_utc"))
    if start is None or end is None or start >= end:
        return False
    current = now_utc.hour * 60 + now_utc.minute
    return start <= current < end


def _candidate_asof_from_bridge(bridge_event: dict[str, Any]) -> str:
    raw = str(bridge_event.get("latest_entry_day") or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    return parsed.isoformat()


def _bridge_success_at(bridge_event: dict[str, Any]) -> str:
    """Return causal completion time from the bridge's actual receipt schema."""
    direct = str(bridge_event.get("generated_at_utc") or "").strip()
    if direct:
        return direct
    broker_truth_after = bridge_event.get("broker_truth_after")
    if isinstance(broker_truth_after, dict):
        return str(broker_truth_after.get("generated_at_utc") or "").strip()
    return ""


def build_operations_from_manifest(
    manifest: dict[str, Any],
    *,
    root: Path = ROOT,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Calculate operational evidence from local files without credentials."""
    if manifest.get("schema_id") != "alpaca_health_auditor_manifest_v1":
        raise ValueError("unsupported Alpaca health manifest schema")
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    source_hashes: dict[str, dict[str, Any]] = {}
    source_files = manifest.get("source_files")
    for component, raw in sorted(
        (source_files if isinstance(source_files, dict) else {}).items()
    ):
        row = raw if isinstance(raw, dict) else {}
        relative = str(row.get("path") or "").strip()
        path = root / relative
        try:
            observed = _sha256_file(path)
        except OSError:
            observed = ""
        source_hashes[str(component)] = {
            "path": relative,
            "expected": str(row.get("expected_sha256") or "").strip().lower(),
            "observed": observed,
        }

    bridge_event = _latest_json_object(root / str(manifest.get("bridge_log_path") or ""))
    protection_event = _latest_json_object(
        root / str(manifest.get("protection_log_path") or "")
    )
    env_paths = [
        root / str(value)
        for value in manifest.get("env_files", [])
        if str(value).strip()
    ]
    allow_new_entries = _env_bool_from_files(env_paths, "ALPACA_ALLOW_NEW_ENTRIES")
    return {
        "authority": OPERATIONS_AUTHORITY,
        "expected_broker_mode": str(
            manifest.get("expected_broker_mode") or "LIVE"
        ).upper(),
        "broker_truth_max_age_minutes": _number(
            manifest.get("broker_truth_max_age_minutes"), 5.0
        ),
        "safe_hold_expected": bool(manifest.get("safe_hold_expected")),
        "send_orders": bool(manifest.get("send_orders")),
        "allow_new_entries": allow_new_entries,
        "schedule_expected_active": _schedule_active(
            manifest.get("schedule") if isinstance(manifest.get("schedule"), dict) else {},
            now,
        ),
        "protection_last_success_at_utc": str(
            protection_event.get("generated_at_utc") or ""
        ),
        "protection_max_age_minutes": _number(
            manifest.get("protection_max_age_minutes"), 30.0
        ),
        "bridge_last_success_at_utc": str(
            _bridge_success_at(bridge_event)
        ),
        "bridge_max_age_minutes": _number(
            manifest.get("bridge_max_age_minutes"), 90.0
        ),
        "candidate_asof_utc": _candidate_asof_from_bridge(bridge_event),
        "candidate_max_age_days": _number(
            manifest.get("candidate_max_age_days"), 45.0
        ),
        "source_hashes": source_hashes,
    }


def _remaining_qty(order: dict[str, Any]) -> float:
    leaves = order.get("leaves_qty")
    if leaves not in {None, ""}:
        return max(0.0, abs(_number(leaves)))
    return max(
        0.0,
        abs(_number(order.get("qty"))) - abs(_number(order.get("filled_qty"))),
    )


def _is_whole(value: float, tolerance: float = 1e-9) -> bool:
    return value > 0 and abs(value - round(value)) <= tolerance


def _issue(issues: list[dict[str, Any]], code: str, severity: str, **context: Any) -> None:
    issues.append({"code": code, "severity": severity, **context})


def _active_protective_orders(
    orders: Iterable[dict[str, Any]], symbol: str
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for raw in orders:
        row = dict(raw or {})
        if str(row.get("symbol") or "").strip().upper() != symbol:
            continue
        if str(row.get("side") or "").strip().lower() != "sell":
            continue
        if str(row.get("type") or "").strip().lower() not in PROTECTIVE_TYPES:
            continue
        if str(row.get("status") or "").strip().lower() not in ACTIVE_ORDER_STATUSES:
            continue
        if _remaining_qty(row) <= 0:
            continue
        selected.append(row)
    return selected


def _freshness_issue(
    issues: list[dict[str, Any]],
    operations: dict[str, Any],
    *,
    timestamp_key: str,
    max_age_key: str,
    code: str,
    now_utc: datetime,
) -> None:
    observed = _utc(operations.get(timestamp_key))
    max_age = max(0.0, _number(operations.get(max_age_key)))
    if observed is None or max_age <= 0:
        _issue(issues, code, "CRITICAL", reason="missing_freshness_evidence")
        return
    raw_age_minutes = (now_utc - observed).total_seconds() / 60.0
    if raw_age_minutes < -1.0:
        _issue(
            issues,
            code,
            "CRITICAL",
            reason="freshness_timestamp_from_future",
            age_minutes=round(raw_age_minutes, 3),
        )
        return
    age_minutes = raw_age_minutes
    if age_minutes > max_age:
        _issue(
            issues,
            code,
            "CRITICAL",
            age_minutes=round(age_minutes, 3),
            max_age_minutes=max_age,
        )


def evaluate_health(
    broker_truth: dict[str, Any],
    floor_state: dict[str, Any],
    operations: dict[str, Any],
    *,
    now_utc: datetime | None = None,
    qty_tolerance: float = 1e-6,
    price_tolerance: float = 1e-8,
) -> dict[str, Any]:
    """Evaluate broker protection and operational evidence without mutation."""
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    issues: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    if operations.get("authority") != OPERATIONS_AUTHORITY:
        _issue(issues, "operations_evidence_not_calculated", "CRITICAL")

    required_broker_fields = {
        "schema_id",
        "authority",
        "broker_mode",
        "generated_at_utc",
        "account",
        "position_count",
        "positions",
        "open_order_count",
        "open_orders",
    }
    if not required_broker_fields.issubset(broker_truth):
        _issue(
            issues,
            "broker_truth_incomplete",
            "CRITICAL",
            missing=sorted(required_broker_fields.difference(broker_truth)),
        )
    if broker_truth.get("schema_id") != BROKER_TRUTH_SCHEMA:
        _issue(issues, "broker_truth_schema_invalid", "CRITICAL")

    generated_at = _utc(broker_truth.get("generated_at_utc"))
    broker_max_age = max(
        0.0, _number(operations.get("broker_truth_max_age_minutes"), 5.0)
    )
    if generated_at is None or broker_max_age <= 0:
        _issue(issues, "broker_truth_freshness_unknown", "CRITICAL")
    else:
        age_minutes = (now - generated_at).total_seconds() / 60.0
        if age_minutes < -1.0:
            _issue(
                issues,
                "broker_truth_from_future",
                "CRITICAL",
                age_minutes=round(age_minutes, 3),
            )
        elif age_minutes > broker_max_age:
            _issue(
                issues,
                "broker_truth_stale",
                "CRITICAL",
                age_minutes=round(age_minutes, 3),
                max_age_minutes=broker_max_age,
            )

    account = broker_truth.get("account")
    account_status = (
        str(account.get("status") or "").strip().upper()
        if isinstance(account, dict)
        else ""
    )
    if account_status != "ACTIVE":
        _issue(
            issues,
            "broker_account_not_active",
            "CRITICAL",
            observed=account_status or None,
        )

    positions_value = broker_truth.get("positions")
    orders_value = broker_truth.get("open_orders")
    if not isinstance(positions_value, list) or not isinstance(orders_value, list):
        _issue(issues, "broker_truth_incomplete", "CRITICAL", reason="lists_missing")
    else:
        if int(_number(broker_truth.get("position_count"), -1.0)) != len(positions_value):
            _issue(issues, "broker_position_count_mismatch", "CRITICAL")
        if int(_number(broker_truth.get("open_order_count"), -1.0)) != len(orders_value):
            _issue(issues, "broker_order_count_mismatch", "CRITICAL")

    expected_mode = str(operations.get("expected_broker_mode") or "LIVE").upper()
    observed_mode = str(broker_truth.get("broker_mode") or "UNKNOWN").upper()
    if observed_mode != expected_mode:
        _issue(
            issues,
            "unexpected_broker_mode",
            "CRITICAL",
            expected=expected_mode,
            observed=observed_mode,
        )
    if broker_truth.get("authority") != "read_only_get_no_order_mutation":
        _issue(issues, "broker_truth_authority_not_read_only", "CRITICAL")

    if bool(operations.get("safe_hold_expected")):
        allow_new_entries = operations.get("allow_new_entries")
        if not isinstance(allow_new_entries, bool):
            _issue(issues, "safe_hold_state_unknown", "CRITICAL")
        elif allow_new_entries:
            _issue(issues, "safe_hold_new_entries_enabled", "CRITICAL")

    if bool(operations.get("schedule_expected_active")):
        _freshness_issue(
            issues,
            operations,
            timestamp_key="protection_last_success_at_utc",
            max_age_key="protection_max_age_minutes",
            code="protective_manager_stale",
            now_utc=now,
        )
        _freshness_issue(
            issues,
            operations,
            timestamp_key="bridge_last_success_at_utc",
            max_age_key="bridge_max_age_minutes",
            code="alpaca_bridge_stale",
            now_utc=now,
        )

    candidate_asof = _utc(operations.get("candidate_asof_utc"))
    candidate_max_age_days = max(0.0, _number(operations.get("candidate_max_age_days")))
    if candidate_asof is None or candidate_max_age_days <= 0:
        _issue(issues, "candidate_snapshot_age_unknown", "CRITICAL")
    else:
        candidate_age_days = (now - candidate_asof).total_seconds() / 86400.0
        if candidate_age_days < -(1.0 / 24.0):
            _issue(
                issues,
                "candidate_snapshot_from_future",
                "CRITICAL",
                age_days=round(candidate_age_days, 3),
            )
        elif candidate_age_days > candidate_max_age_days:
            _issue(
                issues,
                "candidate_snapshot_stale",
                "CRITICAL",
                age_days=round(candidate_age_days, 3),
                max_age_days=candidate_max_age_days,
            )

    source_hashes = operations.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        _issue(issues, "source_hash_evidence_missing", "CRITICAL")
    else:
        for component, raw in sorted(source_hashes.items()):
            row = raw if isinstance(raw, dict) else {}
            expected = str(row.get("expected") or "").strip().lower()
            observed = str(row.get("observed") or "").strip().lower()
            if not expected or not observed or expected != observed:
                _issue(
                    issues,
                    "source_hash_mismatch",
                    "CRITICAL",
                    component=str(component),
                    expected=expected or None,
                    observed=observed or None,
                )

    orders = broker_truth.get("open_orders")
    open_orders = orders if isinstance(orders, list) else []
    positions = broker_truth.get("positions")
    for raw_position in positions if isinstance(positions, list) else []:
        position = dict(raw_position or {})
        symbol = str(position.get("symbol") or "").strip().upper()
        qty = abs(_number(position.get("qty")))
        entry = _number(position.get("avg_entry_price"))
        if not symbol or qty <= 0:
            continue
        side = str(position.get("side") or "").strip().lower()
        if side != "long":
            _issue(
                issues,
                "unsupported_non_long_position",
                "CRITICAL",
                symbol=symbol,
                side=side or None,
            )
            continue
        stops = _active_protective_orders(open_orders, symbol)
        protected_qty = sum(_remaining_qty(row) for row in stops)
        fully_covered = abs(protected_qty - qty) <= qty_tolerance

        floor_row = floor_state.get(symbol) if isinstance(floor_state, dict) else None
        floor = floor_row if isinstance(floor_row, dict) else {}
        accepted_floor = _number(floor.get("accepted_stop_floor"))
        floor_entry = _number(floor.get("entry_price"))
        floor_qty = abs(_number(floor.get("qty"), qty))
        lifecycle_first_seen = _utc(floor.get("lifecycle_first_seen_at_utc"))
        lifecycle_matches = (
            accepted_floor > 0
            and floor_entry > 0
            and entry > 0
            and lifecycle_first_seen is not None
            and lifecycle_first_seen <= now
            and abs(floor_entry - entry) <= max(price_tolerance, entry * 1e-6)
            and abs(floor_qty - qty) <= qty_tolerance
        )
        if accepted_floor <= 0:
            _issue(issues, "accepted_floor_missing", "CRITICAL", symbol=symbol)
        elif not lifecycle_matches:
            _issue(issues, "accepted_floor_lifecycle_mismatch", "CRITICAL", symbol=symbol)

        if not fully_covered:
            _issue(
                issues,
                "position_not_fully_protected",
                "CRITICAL",
                symbol=symbol,
                position_qty=qty,
                protected_qty=round(protected_qty, 9),
            )

        fixed_stops = [
            row
            for row in stops
            if str(row.get("type") or "").lower() != "trailing_stop"
        ]
        fixed_stop_prices = [
            _number(row.get("stop_price"))
            for row in fixed_stops
            if _number(row.get("stop_price")) > 0
        ]
        if len(fixed_stop_prices) != len(fixed_stops):
            _issue(
                issues,
                "protective_stop_price_invalid",
                "CRITICAL",
                symbol=symbol,
            )
        floor_preserved: bool | None = None
        if fixed_stop_prices and accepted_floor > 0:
            floor_preserved = min(fixed_stop_prices) + price_tolerance >= accepted_floor
            if not floor_preserved:
                _issue(
                    issues,
                    "broker_stop_below_accepted_floor",
                    "CRITICAL",
                    symbol=symbol,
                    broker_stop=min(fixed_stop_prices),
                    accepted_stop_floor=accepted_floor,
                )
        elif any(str(row.get("type") or "").lower() == "trailing_stop" for row in stops):
            _issue(issues, "native_trailing_floor_not_observable", "WARN", symbol=symbol)

        tifs = sorted({str(row.get("time_in_force") or "").lower() for row in stops})
        if not _is_whole(qty) and "day" in tifs:
            _issue(
                issues,
                "fractional_day_stop_not_persistent_across_sessions",
                "WARN",
                symbol=symbol,
            )
        if _is_whole(qty) and any(tif != "gtc" for tif in tifs):
            _issue(issues, "whole_share_stop_not_gtc", "CRITICAL", symbol=symbol)

        coverage.append(
            {
                "symbol": symbol,
                "position_qty": qty,
                "protected_qty": round(protected_qty, 9),
                "fully_covered": fully_covered,
                "accepted_stop_floor": accepted_floor or None,
                "floor_preserved": floor_preserved,
                "fixed_stop_prices": sorted(fixed_stop_prices),
                "order_types": sorted(
                    {str(row.get("type") or "").lower() for row in stops}
                ),
                "time_in_force": tifs,
            }
        )

    severities = {row["severity"] for row in issues}
    status = "CRITICAL" if "CRITICAL" in severities else ("WARN" if issues else "PASS")
    return {
        "schema_id": "alpaca_deterministic_health_audit_v1",
        "generated_at_utc": now.isoformat(),
        "authority": "read_only_observation_no_order_mutation_no_money_promotion",
        "status": status,
        "broker_mode": observed_mode,
        "coverage": sorted(coverage, key=lambda row: row["symbol"]),
        "issues": sorted(
            issues,
            key=lambda row: (0 if row["severity"] == "CRITICAL" else 1, row["code"], str(row.get("symbol") or "")),
        ),
        "money_authority": {
            "send_orders_observed": bool(operations.get("send_orders")),
            "allow_new_entries_observed": bool(operations.get("allow_new_entries")),
            "promotion_authorized": False,
        },
    }


def build_receipt(evaluation: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(
        evaluation,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {**evaluation, "evidence_sha256": hashlib.sha256(canonical).hexdigest()}


def _status_exit_code(status: str) -> int:
    normalized = str(status or "").upper()
    if normalized == "PASS":
        return 0
    if normalized == "WARN":
        return 2
    return 1


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _telegram_alert(receipt: dict[str, Any]) -> bool:
    token = os.getenv("TG_TOKEN", "").strip()
    chat_id = os.getenv("TG_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    critical_codes = [
        row["code"] for row in receipt.get("issues", []) if row.get("severity") == "CRITICAL"
    ]
    body = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": "Alpaca health CRITICAL: " + ", ".join(critical_codes[:12]),
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=10) as response:
            return 200 <= int(response.status) < 300
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker-truth-json", default="")
    parser.add_argument(
        "--env-file",
        default=str(ROOT / "configs" / "alpaca_live_v38.env"),
        help="explicit Alpaca credential env used only by the read-only GET collector",
    )
    parser.add_argument(
        "--floor-state-json",
        default=str(ROOT / "runtime" / "alpaca_live_v38" / "protective_exit_hwm.json"),
    )
    parser.add_argument(
        "--manifest-json",
        default=str(ROOT / "configs" / "alpaca_health_auditor_v1.json"),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "runtime" / "alpaca_health" / "latest.json"),
    )
    parser.add_argument("--telegram-alert", action="store_true")
    args = parser.parse_args()

    if args.broker_truth_json:
        broker_truth = _load_object(Path(args.broker_truth_json))
    else:
        from scripts.check_alpaca_state_readonly import collect

        broker_truth = collect(env_file=args.env_file)
    floor_state = _load_object(Path(args.floor_state_json))
    operations = build_operations_from_manifest(
        _load_object(Path(args.manifest_json)), root=ROOT
    )
    receipt = build_receipt(evaluate_health(broker_truth, floor_state, operations))
    _write_json_atomic(Path(args.output), receipt)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    if receipt["status"] != "PASS" and args.telegram_alert:
        _telegram_alert(receipt)
    return _status_exit_code(receipt["status"])


if __name__ == "__main__":
    raise SystemExit(main())
