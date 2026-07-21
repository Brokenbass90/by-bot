"""Receipt-backed virtual position lifecycle for settlement_execution_v3."""

from __future__ import annotations

import copy
import hashlib
import math
from collections import Counter
from typing import Any, Iterable

from .scanner import InputContractError
from .validator import _book_index, _levels, validate_candidates


MODEL_VERSION = "settlement_execution_v3"
STATE_SCHEMA = "settlement_execution_v3_state_v1"


def initial_state(as_of_utc: str) -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA,
        "model_version": MODEL_VERSION,
        "research_only": True,
        "capital_at_risk_usd": 0,
        "derived_from_append_only_receipts": True,
        "as_of_utc": as_of_utc,
        "positions": [],
        "metrics": {
            "position_count": 0,
            "active_count": 0,
            "closed_complete_count": 0,
            "pending_settlement_count": 0,
            "invalid_exit_count": 0,
        },
    }


def funding_receipt_key(
    cycle_id: str, venue: str, symbol: str, side: str, settlement_ts_ms: int
) -> str:
    return "|".join(
        (cycle_id, venue.lower(), symbol.upper(), side.lower(), str(int(settlement_ts_ms)))
    )


def _cycle_event(
    position: dict[str, Any],
    event_type: str,
    *,
    run_id: str,
    recorded_at_utc: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    position["event_sequence"] = int(position.get("event_sequence") or 0) + 1
    key = f"{position['cycle_id']}|{position['event_sequence']}|{event_type}"
    return {
        "schema_version": "settlement_execution_v3_cycle_receipt_v1",
        "model_version": MODEL_VERSION,
        "idempotency_key": key,
        "cycle_id": position["cycle_id"],
        "event_sequence": position["event_sequence"],
        "event_type": event_type,
        "run_id": run_id,
        "recorded_at_utc": recorded_at_utc,
        "details": details or {},
        "position_snapshot": copy.deepcopy(position),
    }


def _expected_settlements(
    position: dict[str, Any], cutoff_ts_ms: int
) -> list[dict[str, Any]]:
    fully_opened = int(position["fully_opened_at_ms"])
    out: list[dict[str, Any]] = []
    for leg_name in ("long_leg", "short_leg"):
        leg = position[leg_name]
        settlement = int(leg["next_settlement_ts_ms"])
        interval_ms = int(round(float(leg["funding_interval_hours"]) * 3_600_000.0))
        if interval_ms <= 0:
            raise InputContractError(
                f"invalid stored funding interval for {position['cycle_id']}:{leg_name}"
            )
        iterations = 0
        while settlement <= cutoff_ts_ms:
            iterations += 1
            if iterations > 10_000:
                raise InputContractError(
                    f"unbounded settlement schedule for {position['cycle_id']}:{leg_name}"
                )
            if fully_opened < settlement:
                out.append(
                    {
                        "cycle_id": position["cycle_id"],
                        "venue": leg["venue"],
                        "symbol": position["symbol"],
                        "side": leg["side"],
                        "settlement_ts_ms": settlement,
                        "quantity": float(leg["quantity"]),
                    }
                )
            settlement += interval_ms
    return out


def _position_status_metrics(positions: list[dict[str, Any]]) -> dict[str, int]:
    active = {"open", "close_pending_data"}
    return {
        "position_count": len(positions),
        "active_count": sum(1 for row in positions if row.get("status") in active),
        "closed_complete_count": sum(
            1 for row in positions if row.get("status") == "closed_complete"
        ),
        "pending_settlement_count": sum(
            len(row.get("pending_settlements") or []) for row in positions
        ),
        "invalid_exit_count": sum(
            1 for row in positions if row.get("status") == "invalid_exit_data"
        ),
    }


def _apply_derived_funding(
    position: dict[str, Any], funding_receipts: list[dict[str, Any]]
) -> None:
    receipts = [
        row
        for row in funding_receipts
        if row.get("cycle_id") == position.get("cycle_id")
    ]
    if any(row.get("actual_public_settlement_receipt") is not True for row in receipts):
        raise InputContractError(
            f"non-public funding receipt in cycle {position.get('cycle_id')}"
        )
    position["funding_receipt_keys"] = sorted(
        str(row["idempotency_key"]) for row in receipts
    )
    position["earned_funding_usd"] = sum(float(row["earned_funding_usd"]) for row in receipts)
    pending = position.get("pending_settlements") or []
    if any(row.get("status") == "data_missing" for row in pending):
        settlement_status = "data_missing"
    elif pending:
        settlement_status = "settlement_pending"
    else:
        settlement_status = "complete"
    position["settlement_status"] = settlement_status

    if position.get("exit_execution_valid") is True:
        if settlement_status == "complete":
            position["status"] = "closed_complete"
            net = (
                float(position["price_pnl_usd"])
                + float(position["earned_funding_usd"])
                - float(position["fee_cost_usd"])
            )
            position["net_pnl_usd"] = net
            position["net_pnl_pct_total_deployed_capital"] = (
                net / float(position["total_deployed_capital_usd"]) * 100.0
            )
        else:
            position["status"] = (
                "closed_data_missing"
                if settlement_status == "data_missing"
                else "closed_settlement_pending"
            )
            # Missing funding is unknown, not zero.  Do not expose a final P&L.
            position["net_pnl_usd"] = None
            position["net_pnl_pct_total_deployed_capital"] = None


def derive_state(
    cycle_receipts: Iterable[dict[str, Any]],
    funding_receipts: Iterable[dict[str, Any]],
    *,
    as_of_utc: str,
) -> dict[str, Any]:
    """Rebuild the mutable view solely from append-only lifecycle receipts."""

    latest: dict[str, tuple[int, dict[str, Any]]] = {}
    seen_sequence: dict[tuple[str, int], str] = {}
    for receipt in cycle_receipts:
        if receipt.get("model_version") != MODEL_VERSION:
            raise InputContractError("cycle ledger contains a foreign model version")
        cycle_id = str(receipt.get("cycle_id") or "")
        sequence = int(receipt.get("event_sequence") or 0)
        snapshot = receipt.get("position_snapshot")
        if not cycle_id or sequence <= 0 or not isinstance(snapshot, dict):
            raise InputContractError("malformed cycle receipt")
        sequence_key = (cycle_id, sequence)
        idempotency_key = str(receipt.get("idempotency_key") or "")
        previous_key = seen_sequence.get(sequence_key)
        if previous_key is not None and previous_key != idempotency_key:
            raise InputContractError(
                f"conflicting cycle event sequence for {cycle_id}:{sequence}"
            )
        seen_sequence[sequence_key] = idempotency_key
        if sequence > latest.get(cycle_id, (0, {}))[0]:
            latest[cycle_id] = (sequence, copy.deepcopy(snapshot))

    funding = list(funding_receipts)
    positions = [value[1] for _, value in sorted(latest.items())]
    for position in positions:
        _apply_derived_funding(position, funding)
    positions.sort(key=lambda row: (int(row["opened_at_ms"]), row["cycle_id"]))
    state = initial_state(as_of_utc)
    state["positions"] = positions
    state["metrics"] = _position_status_metrics(positions)
    return state


def reconcile_settlements(
    state: dict[str, Any],
    funding_snapshot: dict[str, Any],
    existing_funding_receipts: list[dict[str, Any]],
    *,
    as_of_ms: int,
    as_of_utc: str,
    run_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Create earned-funding receipts only from exact public history rows."""

    positions = copy.deepcopy(state.get("positions") or [])
    history = {
        (row["venue"], row["symbol"], int(row["settlement_ts_ms"])): row
        for row in funding_snapshot.get("settlement_history") or []
    }
    existing_keys = {
        str(row["idempotency_key"]) for row in existing_funding_receipts
    }
    new_funding: list[dict[str, Any]] = []
    cycle_events: list[dict[str, Any]] = []
    max_attempts = int(config["settlement"]["max_missing_receipt_attempts"])
    counters: Counter[str] = Counter()

    for position in positions:
        if position.get("status") == "invalid_exit_data":
            continue
        cutoff = min(as_of_ms, int(position.get("closed_at_ms") or as_of_ms))
        pending_by_key = {
            str(row["idempotency_key"]): row
            for row in position.get("pending_settlements") or []
        }
        changed = False
        for expected in _expected_settlements(position, cutoff):
            key = funding_receipt_key(
                expected["cycle_id"],
                expected["venue"],
                expected["symbol"],
                expected["side"],
                expected["settlement_ts_ms"],
            )
            if key in existing_keys:
                if pending_by_key.pop(key, None) is not None:
                    changed = True
                continue
            public = history.get(
                (expected["venue"], expected["symbol"], expected["settlement_ts_ms"])
            )
            if public is None:
                prior = pending_by_key.get(key) or {}
                if prior.get("status") == "data_missing":
                    counters["data_missing_retry_exhausted"] += 1
                    continue
                attempts = int(prior.get("attempt_count") or 0) + 1
                status = "data_missing" if attempts >= max_attempts else "settlement_pending"
                pending_by_key[key] = {
                    **expected,
                    "idempotency_key": key,
                    "status": status,
                    "attempt_count": attempts,
                    "first_missing_at_utc": prior.get("first_missing_at_utc") or as_of_utc,
                    "last_attempt_at_utc": as_of_utc,
                }
                counters[status] += 1
                changed = True
                continue

            side_multiplier = 1.0 if expected["side"] == "short" else -1.0
            settlement_position_value_usd = (
                float(expected["quantity"])
                * float(public["settlement_mark_price"])
            )
            earned = (
                settlement_position_value_usd
                * float(public["funding_rate"])
                * side_multiplier
            )
            receipt = {
                "schema_version": "settlement_execution_v3_funding_receipt_v1",
                "model_version": MODEL_VERSION,
                "idempotency_key": key,
                "cycle_id": expected["cycle_id"],
                "venue": expected["venue"],
                "symbol": expected["symbol"],
                "side": expected["side"],
                "settlement_ts_ms": expected["settlement_ts_ms"],
                "funding_rate": float(public["funding_rate"]),
                "quantity": float(expected["quantity"]),
                "settlement_mark_price": float(public["settlement_mark_price"]),
                "settlement_mark_ts_ms": int(public["settlement_mark_ts_ms"]),
                "settlement_position_value_usd": settlement_position_value_usd,
                "earned_funding_usd": earned,
                "actual_public_settlement_receipt": True,
                "source_response_sha256": public["source_response_sha256"],
                "recorded_at_utc": as_of_utc,
                "run_id": run_id,
            }
            new_funding.append(receipt)
            existing_keys.add(key)
            pending_by_key.pop(key, None)
            counters["actual_public_receipt"] += 1
            changed = True

        position["pending_settlements"] = sorted(
            pending_by_key.values(),
            key=lambda row: (row["settlement_ts_ms"], row["venue"], row["side"]),
        )
        if changed:
            cycle_events.append(
                _cycle_event(
                    position,
                    "settlement_reconciliation",
                    run_id=run_id,
                    recorded_at_utc=as_of_utc,
                    details={"new_public_receipts": counters["actual_public_receipt"]},
                )
            )

    return {
        "schema_version": "settlement_execution_v3_settlement_update_v1",
        "state": {**state, "as_of_utc": as_of_utc, "positions": positions},
        "new_funding_receipts": new_funding,
        "new_cycle_receipts": cycle_events,
        "metrics": dict(sorted(counters.items())),
    }


def _walk_quantity(
    levels: list[tuple[float, float]], target_quantity: float
) -> tuple[bool, float, float]:
    remaining = target_quantity
    filled_quantity = 0.0
    notional = 0.0
    for price, available in levels:
        take = min(remaining, available)
        filled_quantity += take
        notional += take * price
        remaining -= take
        if remaining <= max(1e-12, target_quantity * 1e-9):
            break
    average = notional / filled_quantity if filled_quantity > 0 else 0.0
    return remaining <= max(1e-12, target_quantity * 1e-9), average, notional


def _exit_leg(book: dict[str, Any], position_leg: dict[str, Any]) -> dict[str, Any]:
    quantity = float(position_leg["quantity"])
    side = position_leg["side"]
    if side == "long":
        levels = _levels(book.get("bids"), "bids")
        filled, average, notional = _walk_quantity(levels, quantity)
        best = levels[0][0] if levels else 0.0
        slippage = (best / average - 1.0) * 10_000.0 if average else math.inf
    elif side == "short":
        levels = _levels(book.get("asks"), "asks")
        filled, average, notional = _walk_quantity(levels, quantity)
        best = levels[0][0] if levels else 0.0
        slippage = (average / best - 1.0) * 10_000.0 if best else math.inf
    else:
        raise InputContractError(f"invalid stored side: {side}")
    return {
        "filled": filled,
        "average_price": average,
        "quantity": quantity if filled else 0.0,
        "notional_usd": notional,
        "slippage_bps": max(0.0, slippage),
    }


def close_due_positions(
    update: dict[str, Any],
    public_snapshot: dict[str, Any],
    *,
    as_of_ms: int,
    as_of_utc: str,
    run_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    state = copy.deepcopy(update["state"])
    positions = state.get("positions") or []
    events = list(update.get("new_cycle_receipts") or [])
    books = _book_index(public_snapshot.get("responses") or [], "exit_orderbook")
    execution = config["execution"]
    retry = config["exit_retry"]
    counters: Counter[str] = Counter()

    for position in positions:
        if position.get("status") not in {"open", "close_pending_data"}:
            continue
        if int(position["hold_until_ms"]) > as_of_ms:
            continue
        short_book = books.get((position["short_leg"]["venue"], position["symbol"]))
        long_book = books.get((position["long_leg"]["venue"], position["symbol"]))
        error: str | None = None
        if short_book is None or long_book is None:
            error = "missing_pair_exit_book"
        else:
            max_age = int(execution["max_book_age_ms"])
            timestamps = (
                short_book["server_timestamp_ms"],
                long_book["server_timestamp_ms"],
                short_book["received_timestamp_ms"],
                long_book["received_timestamp_ms"],
            )
            if any(
                as_of_ms - int(value) < 0 or as_of_ms - int(value) > max_age
                for value in timestamps
            ):
                error = "stale_or_future_exit_book"
            elif (
                abs(short_book["server_timestamp_ms"] - long_book["server_timestamp_ms"])
                > int(execution["max_pair_skew_ms"])
                or abs(
                    short_book["received_timestamp_ms"]
                    - long_book["received_timestamp_ms"]
                )
                > int(execution["max_pair_skew_ms"])
            ):
                error = "pair_exit_book_skew"

        short_exit = long_exit = None
        if error is None:
            short_exit = _exit_leg(short_book, position["short_leg"])
            long_exit = _exit_leg(long_book, position["long_leg"])
            if not short_exit["filled"] or not long_exit["filled"]:
                error = "exit_not_fully_fillable"

        if error is not None:
            attempts = int(position.get("exit_retry_count") or 0) + 1
            position["exit_retry_count"] = attempts
            position.setdefault("exit_errors", []).append(
                {"attempt": attempts, "at_utc": as_of_utc, "error": error}
            )
            deadline = int(position["hold_until_ms"]) + int(retry["deadline_ms"])
            exhausted = attempts >= int(retry["max_attempts"]) or as_of_ms >= deadline
            position["status"] = "invalid_exit_data" if exhausted else "close_pending_data"
            position["exit_execution_valid"] = False if exhausted else None
            counters[position["status"]] += 1
            events.append(
                _cycle_event(
                    position,
                    "invalid_exit_data" if exhausted else "close_pending_data",
                    run_id=run_id,
                    recorded_at_utc=as_of_utc,
                    details={"error": error, "attempt": attempts},
                )
            )
            continue

        assert short_exit is not None and long_exit is not None
        long_entry = float(position["long_leg"]["entry_average_price"])
        short_entry = float(position["short_leg"]["entry_average_price"])
        long_quantity = float(position["long_leg"]["quantity"])
        short_quantity = float(position["short_leg"]["quantity"])
        price_pnl = (
            (float(long_exit["average_price"]) - long_entry) * long_quantity
            + (short_entry - float(short_exit["average_price"])) * short_quantity
        )
        long_entry_notional = float(position["long_leg"]["entry_notional_usd"])
        short_entry_notional = float(position["short_leg"]["entry_notional_usd"])
        long_fee = position["long_leg"]["fee_contract"]
        short_fee = position["short_leg"]["fee_contract"]
        fee_cost = (
            long_entry_notional * float(long_fee["entry_fee_bps"]) / 10_000.0
            + float(long_exit["notional_usd"]) * float(long_fee["exit_fee_bps"]) / 10_000.0
            + short_entry_notional * float(short_fee["entry_fee_bps"]) / 10_000.0
            + float(short_exit["notional_usd"]) * float(short_fee["exit_fee_bps"]) / 10_000.0
        )
        position.update(
            {
                "closed_at_ms": as_of_ms,
                "closed_at_utc": as_of_utc,
                "exit_execution_valid": True,
                "exit_execution": {
                    "long": long_exit,
                    "short": short_exit,
                    "long_source_response_sha256": long_book["source_response_sha256"],
                    "short_source_response_sha256": short_book["source_response_sha256"],
                },
                "price_pnl_usd": price_pnl,
                "fee_cost_usd": fee_cost,
                "total_deployed_capital_usd": long_entry_notional + short_entry_notional,
                "status": "closed_settlement_pending"
                if position.get("pending_settlements")
                else "closed_complete",
            }
        )
        counters["closed_with_executable_books"] += 1
        events.append(
            _cycle_event(
                position,
                "closed_with_executable_books",
                run_id=run_id,
                recorded_at_utc=as_of_utc,
            )
        )

    state["positions"] = positions
    return {
        "schema_version": "settlement_execution_v3_close_update_v1",
        "state": state,
        "new_funding_receipts": list(update.get("new_funding_receipts") or []),
        "new_cycle_receipts": events,
        "metrics": dict(sorted(counters.items())),
    }


def open_new_positions(
    close_update: dict[str, Any],
    validation: dict[str, Any],
    public_snapshot: dict[str, Any],
    *,
    as_of_utc: str,
    run_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    state = copy.deepcopy(close_update["state"])
    positions = state.get("positions") or []
    active_statuses = {"open", "close_pending_data"}
    active_symbols = {
        row["symbol"] for row in positions if row.get("status") in active_statuses
    }
    active_count = sum(1 for row in positions if row.get("status") in active_statuses)
    maximum = int(config["execution"]["max_open_virtual_routes"])
    events = list(close_update.get("new_cycle_receipts") or [])
    counters: Counter[str] = Counter()

    entry_validation = validate_candidates(
        list(validation.get("accepted") or []),
        public_snapshot,
        config,
        phase="entry_orderbook",
    )
    for candidate in entry_validation["accepted"]:
        if active_count >= maximum:
            counters["max_open_routes"] += 1
            continue
        symbol = candidate["symbol"]
        if symbol in active_symbols:
            counters["one_open_route_per_symbol"] += 1
            continue
        actual = candidate["execution"]
        fully_opened_at_ms = max(
            int(actual["short_book_received_timestamp_ms"]),
            int(actual["long_book_received_timestamp_ms"]),
        )
        if fully_opened_at_ms >= min(
            int(candidate["short_next_settlement_ts_ms"]),
            int(candidate["long_next_settlement_ts_ms"]),
        ):
            counters["not_fully_open_before_settlement"] += 1
            continue
        digest = hashlib.sha256(
            f"{run_id}|{symbol}|{candidate['short_venue']}|{candidate['long_venue']}".encode()
        ).hexdigest()[:20]
        cycle_id = f"sev3-{digest}"
        hold_until_ms = fully_opened_at_ms + int(
            round(float(config["execution"]["virtual_hold_hours"]) * 3_600_000.0)
        )
        position = {
            "model_version": MODEL_VERSION,
            "cycle_id": cycle_id,
            "symbol": symbol,
            "underlying_id": candidate["underlying_id"],
            "identity_mapping_version": candidate["identity_mapping_version"],
            "status": "open",
            "settlement_status": "complete",
            "research_only": True,
            "simulation": True,
            "capital_at_risk_usd": 0,
            "opened_at_ms": fully_opened_at_ms,
            "opened_at_utc": as_of_utc,
            "fully_opened_at_ms": fully_opened_at_ms,
            "hold_until_ms": hold_until_ms,
            "event_sequence": 0,
            "exit_retry_count": 0,
            "exit_errors": [],
            "pending_settlements": [],
            "funding_receipt_keys": [],
            "earned_funding_usd": 0.0,
            "predicted_funding_for_ranking_only": {
                "short_rate": candidate["short_predicted_rate"],
                "long_rate": candidate["long_predicted_rate"],
                "predicted_net_bps_pair_sum": actual["predicted_net_bps_pair_sum"],
            },
            "long_leg": {
                "venue": candidate["long_venue"],
                "side": "long",
                "entry_average_price": actual["long_leg"]["average_price"],
                "quantity": actual["long_leg"]["quantity"],
                "entry_notional_usd": actual["long_leg"]["filled_notional_usd"],
                "funding_interval_hours": candidate["long_interval_hours"],
                "next_settlement_ts_ms": candidate["long_next_settlement_ts_ms"],
                "fee_contract": actual["fee_contracts"]["long"],
                "entry_book_source_sha256": actual["long_book_source_sha256"],
            },
            "short_leg": {
                "venue": candidate["short_venue"],
                "side": "short",
                "entry_average_price": actual["short_leg"]["average_price"],
                "quantity": actual["short_leg"]["quantity"],
                "entry_notional_usd": actual["short_leg"]["filled_notional_usd"],
                "funding_interval_hours": candidate["short_interval_hours"],
                "next_settlement_ts_ms": candidate["short_next_settlement_ts_ms"],
                "fee_contract": actual["fee_contracts"]["short"],
                "entry_book_source_sha256": actual["short_book_source_sha256"],
            },
        }
        events.append(
            _cycle_event(
                position,
                "virtual_pair_opened",
                run_id=run_id,
                recorded_at_utc=as_of_utc,
                details={"entry_gate_recomputed": True},
            )
        )
        positions.append(position)
        active_symbols.add(symbol)
        active_count += 1
        counters["opened"] += 1

    for reason, count in entry_validation["reject_counters"].items():
        counters[f"entry_recheck_{reason}"] += int(count)
    state["positions"] = positions
    return {
        "schema_version": "settlement_execution_v3_open_update_v1",
        "state": state,
        "new_funding_receipts": list(close_update.get("new_funding_receipts") or []),
        "new_cycle_receipts": events,
        "entry_revalidation": entry_validation,
        "metrics": dict(sorted(counters.items())),
    }
