"""Executable-book gates shared by validation and the actual virtual entry."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any, Iterable

from .scanner import InputContractError


def _iso_to_ms(value: Any, field: str) -> int:
    if not isinstance(value, str) or not value:
        raise InputContractError(f"{field} must be a non-empty UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputContractError(f"invalid {field}: {value}") from exc
    if parsed.tzinfo is None:
        raise InputContractError(f"{field} must include a timezone")
    return int(parsed.timestamp() * 1000)


def _levels(value: Any, field: str) -> list[tuple[float, float]]:
    if not isinstance(value, list):
        raise InputContractError(f"{field} must be a list")
    out: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, list | tuple) or len(item) < 2:
            raise InputContractError(f"invalid level in {field}")
        try:
            price = float(item[0])
            quantity = float(item[1])
        except (TypeError, ValueError) as exc:
            raise InputContractError(f"non-numeric level in {field}") from exc
        if not math.isfinite(price) or not math.isfinite(quantity):
            raise InputContractError(f"non-finite level in {field}")
        if price <= 0 or quantity <= 0:
            raise InputContractError(f"non-positive level in {field}")
        out.append((price, quantity))
    return out


def _walk(
    levels: list[tuple[float, float]], notional_usd: float
) -> tuple[bool, float, float, float]:
    if not levels or notional_usd <= 0:
        return False, 0.0, 0.0, 0.0
    remaining = notional_usd
    notional = 0.0
    quantity = 0.0
    best = levels[0][0]
    for price, available_quantity in levels:
        take_notional = min(remaining, price * available_quantity)
        notional += take_notional
        quantity += take_notional / price
        remaining -= take_notional
        if remaining <= 1e-8:
            break
    if quantity <= 0:
        return False, 0.0, notional, best
    return remaining <= 1e-8, notional / quantity, notional, best


def executable_leg(book: dict[str, Any], side: str, notional_usd: float) -> dict[str, Any]:
    if side == "long":
        levels = _levels(book.get("asks"), "asks")
        filled, average, filled_notional, best = _walk(levels, notional_usd)
        slippage = (average / best - 1.0) * 10_000.0 if best else math.inf
    elif side == "short":
        levels = _levels(book.get("bids"), "bids")
        filled, average, filled_notional, best = _walk(levels, notional_usd)
        slippage = (best / average - 1.0) * 10_000.0 if average else math.inf
    else:
        raise InputContractError(f"unsupported side: {side}")
    return {
        "filled": filled,
        "best_price": best,
        "average_price": average,
        "filled_notional_usd": filled_notional,
        "quantity": (filled_notional / average) if average > 0 else 0.0,
        "slippage_bps": max(0.0, slippage),
    }


def _book_index(
    responses: Iterable[dict[str, Any]], phase: str
) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for response in responses:
        if response.get("endpoint_class") != phase:
            continue
        venue = str(response.get("venue") or "").lower()
        payload = response.get("normalized_payload")
        if not isinstance(payload, dict):
            raise InputContractError(f"{venue} {phase} payload must be an object")
        symbol = str(payload.get("symbol") or "").upper()
        key = (venue, symbol)
        if key in index:
            raise InputContractError(f"duplicate {phase} for {venue}:{symbol}")
        index[key] = {
            "venue": venue,
            "symbol": symbol,
            "server_timestamp_ms": int(response["exchange_timestamp_ms"]),
            "received_timestamp_ms": _iso_to_ms(
                response["received_at_utc"], "received_at_utc"
            ),
            "source_response_sha256": response["normalized_payload_sha256"],
            "bids": payload.get("bids"),
            "asks": payload.get("asks"),
        }
    return index


def _fee_contract(config: dict[str, Any], venue: str) -> dict[str, Any]:
    contract = (config.get("venue_fee_contracts") or {}).get(venue)
    if not isinstance(contract, dict):
        raise InputContractError(f"missing assumed fee contract for {venue}")
    for field in ("entry_fee_bps", "exit_fee_bps", "source", "valid_at_utc"):
        if field not in contract:
            raise InputContractError(f"{venue} fee contract missing {field}")
    if contract.get("fee_kind") != "assumed_conservative_public_only":
        raise InputContractError(f"{venue} fee contract is not explicitly assumed")
    return contract


def _reject_reason(
    candidate: dict[str, Any],
    short_book: dict[str, Any] | None,
    long_book: dict[str, Any] | None,
    *,
    as_of_ms: int,
    config: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    if short_book is None or long_book is None:
        return "missing_pair_book", None
    execution = config["execution"]
    max_age = int(execution["max_book_age_ms"])
    for book in (short_book, long_book):
        server_age = as_of_ms - int(book["server_timestamp_ms"])
        receive_age = as_of_ms - int(book["received_timestamp_ms"])
        if server_age < 0 or receive_age < 0 or server_age > max_age or receive_age > max_age:
            return "stale_or_future_book", None
    if (
        abs(short_book["server_timestamp_ms"] - long_book["server_timestamp_ms"])
        > int(execution["max_pair_skew_ms"])
        or abs(
            short_book["received_timestamp_ms"] - long_book["received_timestamp_ms"]
        )
        > int(execution["max_pair_skew_ms"])
    ):
        return "pair_book_skew", None

    notional = float(execution["virtual_notional_usd_per_leg"])
    short_leg = executable_leg(short_book, "short", notional)
    long_leg = executable_leg(long_book, "long", notional)
    if not short_leg["filled"] or not long_leg["filled"]:
        return "not_fully_fillable_equal_notional", None
    if max(short_leg["slippage_bps"], long_leg["slippage_bps"]) > float(
        execution["max_entry_slippage_bps_per_leg"]
    ):
        return "entry_slippage_limit", None

    middle = (short_leg["average_price"] + long_leg["average_price"]) / 2.0
    basis_pct = abs(short_leg["average_price"] - long_leg["average_price"]) / middle * 100.0
    if basis_pct > float(execution["max_actual_basis_pct"]):
        return "actual_basis_limit", None

    hold_hours = float(execution["virtual_hold_hours"])
    gross_carry_bps = (
        float(candidate["short_predicted_rate"])
        / float(candidate["short_interval_hours"])
        - float(candidate["long_predicted_rate"])
        / float(candidate["long_interval_hours"])
    ) * hold_hours * 10_000.0
    short_fee = _fee_contract(config, candidate["short_venue"])
    long_fee = _fee_contract(config, candidate["long_venue"])
    four_fill_fee_bps = sum(
        float(value)
        for value in (
            short_fee["entry_fee_bps"],
            short_fee["exit_fee_bps"],
            long_fee["entry_fee_bps"],
            long_fee["exit_fee_bps"],
        )
    )
    entry_slippage_bps = short_leg["slippage_bps"] + long_leg["slippage_bps"]
    exit_slippage_bps = 2.0 * float(execution["exit_slippage_buffer_bps_per_leg"])
    safety_buffer_bps = float(execution["additional_safety_buffer_bps"])
    net_bps_pair_sum = (
        gross_carry_bps
        - four_fill_fee_bps
        - entry_slippage_bps
        - exit_slippage_bps
        - safety_buffer_bps
    )
    if net_bps_pair_sum < float(execution["minimum_predicted_net_bps_pair_sum"]):
        return "corrected_net_gate", None

    return None, {
        "short_leg": short_leg,
        "long_leg": long_leg,
        "actual_basis_pct": basis_pct,
        "predicted_gross_carry_bps_pair_sum": gross_carry_bps,
        "four_fill_assumed_fee_bps_pair_sum": four_fill_fee_bps,
        "entry_slippage_bps_pair_sum": entry_slippage_bps,
        "exit_slippage_buffer_bps_pair_sum": exit_slippage_bps,
        "additional_safety_buffer_bps": safety_buffer_bps,
        "predicted_net_bps_pair_sum": net_bps_pair_sum,
        "short_book_source_sha256": short_book["source_response_sha256"],
        "long_book_source_sha256": long_book["source_response_sha256"],
        "short_book_server_timestamp_ms": short_book["server_timestamp_ms"],
        "long_book_server_timestamp_ms": long_book["server_timestamp_ms"],
        "short_book_received_timestamp_ms": short_book["received_timestamp_ms"],
        "long_book_received_timestamp_ms": long_book["received_timestamp_ms"],
        "fee_contracts": {
            "short": dict(short_fee),
            "long": dict(long_fee),
        },
    }


def validate_candidates(
    candidates: list[dict[str, Any]],
    public_snapshot: dict[str, Any],
    config: dict[str, Any],
    *,
    phase: str,
) -> dict[str, Any]:
    """Apply all book and corrected-net gates for one explicit snapshot phase."""

    if phase not in {"validation_orderbook", "entry_orderbook"}:
        raise InputContractError(f"unsupported orderbook phase: {phase}")
    books = _book_index(public_snapshot.get("responses") or [], phase)
    as_of_ms = int(public_snapshot["as_of_ms"])
    accepted: list[dict[str, Any]] = []
    rejects: Counter[str] = Counter()
    for candidate in candidates:
        short_book = books.get((candidate["short_venue"], candidate["symbol"]))
        long_book = books.get((candidate["long_venue"], candidate["symbol"]))
        reason, execution = _reject_reason(
            candidate,
            short_book,
            long_book,
            as_of_ms=as_of_ms,
            config=config,
        )
        if reason is None and execution is not None:
            short_received = int(execution["short_book_received_timestamp_ms"])
            long_received = int(execution["long_book_received_timestamp_ms"])
            if phase == "validation_orderbook":
                try:
                    predecessor = int(candidate["signal_ready_received_timestamp_ms"])
                except (KeyError, TypeError, ValueError):
                    reason = "missing_signal_temporal_lineage"
                else:
                    if min(short_received, long_received) < predecessor:
                        reason = "validation_before_signal"
            else:
                prior_execution = candidate.get("execution")
                if not isinstance(prior_execution, dict):
                    reason = "missing_validation_temporal_lineage"
                else:
                    try:
                        predecessor = max(
                            int(prior_execution["short_book_received_timestamp_ms"]),
                            int(prior_execution["long_book_received_timestamp_ms"]),
                        )
                    except (KeyError, TypeError, ValueError):
                        reason = "missing_validation_temporal_lineage"
                    else:
                        if min(short_received, long_received) < predecessor:
                            reason = "entry_before_validation"
            if reason is None:
                execution["causal_predecessor_received_timestamp_ms"] = predecessor
                execution["phase_ready_received_timestamp_ms"] = max(
                    short_received, long_received
                )
        if reason:
            rejects[reason] += 1
            continue
        accepted.append({**candidate, "execution": execution})

    return {
        "schema_version": f"settlement_execution_v3_{phase}_validation_v1",
        "phase": phase,
        "accepted": accepted,
        "reject_counters": dict(sorted(rejects.items())),
        "metrics": {
            "accepted_count": len(accepted),
            "reject_count": sum(rejects.values()),
        },
    }
