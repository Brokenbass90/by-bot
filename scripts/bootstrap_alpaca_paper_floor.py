#!/usr/bin/env python3
"""One-time PAPER-only migration from historical accepted stops to an HWM floor.

The tool performs authenticated GET requests and writes two local mode-0600
artifacts.  It has no order endpoint.  Every currently open PAPER position
must have at least one historical broker-accepted fixed stop with the exact
remaining quantity; otherwise the migration fails without writing anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import equities_alpaca_intraday_bridge as bridge
from scripts.alpaca_adaptive_paper import _atomic_write_private_json


ACK = "PAPER_HISTORICAL_STOP_FLOOR_BOOTSTRAP"
ACCEPTED_HISTORY_STATUSES = {
    "accepted",
    "accepted_for_bidding",
    "new",
    "pending_new",
    "partially_filled",
    "held",
    "canceled",
    "expired",
    "replaced",
}


class PaperFloorBootstrapError(RuntimeError):
    """The historical broker proof is insufficient or unsafe."""


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _historical_stop_candidates(
    position: dict[str, Any], orders: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    symbol = str(position.get("symbol") or "").strip().upper()
    qty = abs(_f(position.get("qty")))
    current = _f(position.get("current_price"))
    tolerance = max(1e-9, qty * 1e-6)
    candidates: list[dict[str, Any]] = []
    for raw in orders:
        row = dict(raw or {})
        remaining = max(0.0, abs(_f(row.get("qty"))) - abs(_f(row.get("filled_qty"))))
        stop = _f(row.get("stop_price"))
        if (
            str(row.get("symbol") or "").strip().upper() != symbol
            or str(row.get("side") or "").strip().lower() != "sell"
            or str(row.get("type") or row.get("order_type") or "").strip().lower()
            not in {"stop", "stop_limit"}
            or str(row.get("status") or "").strip().lower()
            not in ACCEPTED_HISTORY_STATUSES
            or abs(remaining - qty) > tolerance
            or stop <= 0
            or current <= 0
            or stop >= current
            or not str(row.get("created_at") or "").strip()
        ):
            continue
        candidates.append(row)
    return candidates


def build_historical_floor_state(
    positions: Iterable[dict[str, Any]],
    orders: Iterable[dict[str, Any]],
    *,
    observed_at_utc: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    observed = observed_at_utc
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    observed_text = observed.astimezone(timezone.utc).isoformat()
    position_rows = [dict(row or {}) for row in positions]
    order_rows = [dict(row or {}) for row in orders]
    state: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []
    for position in sorted(
        position_rows, key=lambda row: str(row.get("symbol") or "").upper()
    ):
        symbol = str(position.get("symbol") or "").strip().upper()
        qty = abs(_f(position.get("qty")))
        entry = _f(position.get("avg_entry_price"))
        current = _f(position.get("current_price"))
        if not symbol or min(qty, entry, current) <= 0:
            raise PaperFloorBootstrapError(f"invalid_position:{symbol or 'UNKNOWN'}")
        candidates = _historical_stop_candidates(position, order_rows)
        if not candidates:
            raise PaperFloorBootstrapError(f"missing_historical_floor:{symbol}")
        selected = max(candidates, key=lambda row: _f(row.get("stop_price")))
        first_seen = min(str(row.get("created_at")) for row in candidates)
        floor = _f(selected.get("stop_price"))
        state[symbol] = {
            "hwm": max(current, floor),
            "entry_price": entry,
            "qty": qty,
            "lifecycle_first_seen_at_utc": first_seen,
            "accepted_stop_floor": floor,
            "accepted_order_id": str(selected.get("id") or ""),
            "accepted_order_tif": str(selected.get("time_in_force") or "").lower(),
            "accepted_observed_at_utc": observed_text,
            "updated_at_utc": observed_text,
            "bootstrap_source": "historical_broker_fixed_stop_exact_qty",
        }
        evidence.append(
            {
                "symbol": symbol,
                "entry_price": entry,
                "qty": qty,
                "current_price": current,
                "accepted_stop_floor": floor,
                "accepted_order_id": str(selected.get("id") or ""),
                "accepted_order_status": str(selected.get("status") or "").lower(),
                "accepted_order_created_at": str(selected.get("created_at") or ""),
                "candidate_count": len(candidates),
            }
        )
    return state, evidence


def write_bootstrap_artifacts(
    state_path: Path,
    receipt_path: Path,
    *,
    state: dict[str, Any],
    evidence: list[dict[str, Any]],
    generated_at_utc: str,
) -> None:
    if state_path.exists():
        raise PaperFloorBootstrapError("state_already_exists")
    if receipt_path.exists():
        raise PaperFloorBootstrapError("receipt_already_exists")
    if not state:
        raise PaperFloorBootstrapError("no_open_positions")
    state_hash = _canonical_sha256(state)
    receipt = {
        "schema_id": "alpaca_paper_historical_floor_bootstrap_v1",
        "authority": "paper_state_migration_no_orders",
        "generated_at_utc": generated_at_utc,
        "state_path": str(state_path),
        "state_sha256": state_hash,
        "position_count": len(state),
        "evidence": evidence,
        "orders_created_or_changed": 0,
        "live_account_authority": False,
    }
    _atomic_write_private_json(state_path, state)
    _atomic_write_private_json(receipt_path, receipt)


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PaperFloorBootstrapError("env_file_unreadable") from exc
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        values[key.strip()] = value.split("#", 1)[0].strip().strip('"').strip("'")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", default=str(ROOT / "configs" / "alpaca_paper_local.env")
    )
    parser.add_argument(
        "--state-path",
        default=str(
            ROOT
            / "runtime/equities_alpaca_adaptive_v1/protective_exit/protective_exit_hwm.json"
        ),
    )
    parser.add_argument(
        "--receipt-path",
        default=str(
            ROOT
            / "runtime/equities_alpaca_adaptive_v1/protective_exit/bootstrap_receipt.json"
        ),
    )
    parser.add_argument("--ack", default="")
    args = parser.parse_args()
    if args.ack != ACK:
        print(
            json.dumps(
                {
                    "status": "PAPER_FLOOR_BOOTSTRAP_DISABLED",
                    "required_ack": ACK,
                    "network_calls": False,
                    "writes": False,
                    "orders_allowed": False,
                    "live_account_authority": False,
                },
                sort_keys=True,
            )
        )
        return 2

    values = _read_env(Path(args.env_file))
    key = values.get("ALPACA_API_KEY_ID", "")
    secret = values.get("ALPACA_API_SECRET_KEY", "")
    base_url = values.get("ALPACA_BASE_URL", "")
    parsed_base = urlparse(base_url)
    if (
        not key
        or not secret
        or parsed_base.scheme.lower() != "https"
        or (parsed_base.hostname or "").lower() != "paper-api.alpaca.markets"
    ):
        raise PaperFloorBootstrapError("paper_account_not_proven")
    client = bridge.AlpacaClient(base_url, key, secret)
    observed = datetime.now(timezone.utc)
    positions = client.list_positions()
    after = (observed - timedelta(days=30)).isoformat()
    orders = client.list_orders(status="all", after=after)
    state, evidence = build_historical_floor_state(
        positions,
        orders,
        observed_at_utc=observed,
    )
    write_bootstrap_artifacts(
        Path(args.state_path),
        Path(args.receipt_path),
        state=state,
        evidence=evidence,
        generated_at_utc=observed.isoformat(),
    )
    print(
        json.dumps(
            {
                "status": "PAPER_FLOOR_BOOTSTRAP_WRITTEN",
                "position_count": len(state),
                "symbols": sorted(state),
                "state_sha256": _canonical_sha256(state),
                "orders_created_or_changed": 0,
                "live_account_authority": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
