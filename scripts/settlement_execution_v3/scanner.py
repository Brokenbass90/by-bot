"""Explicit metadata/taxonomy gates and predicted-funding ranking for v3."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Iterable


VENUES = {"bybit", "binance", "bitget"}


class InputContractError(ValueError):
    """Raised when a normalized public input violates the frozen schema."""


def _finite_number(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise InputContractError(f"{field} must be numeric") from exc
    if not math.isfinite(parsed):
        raise InputContractError(f"{field} must be finite")
    return parsed


def _positive_number(value: Any, field: str) -> float:
    parsed = _finite_number(value, field)
    if parsed <= 0:
        raise InputContractError(f"{field} must be positive")
    return parsed


def _positive_int(value: Any, field: str) -> int:
    parsed = _positive_number(value, field)
    if not parsed.is_integer():
        raise InputContractError(f"{field} must be an integer")
    return int(parsed)


def _records(
    responses: Iterable[dict[str, Any]], endpoint_class: str
) -> Iterable[tuple[str, dict[str, Any], str, int, int]]:
    for response in responses:
        if response.get("endpoint_class") != endpoint_class:
            continue
        venue = str(response.get("venue") or "").lower()
        payload = response.get("normalized_payload")
        rows = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise InputContractError(
                f"{venue} {endpoint_class} normalized_payload.records must be a list"
            )
        source_hash = str(response.get("normalized_payload_sha256") or "")
        if not source_hash:
            raise InputContractError(
                f"{venue} {endpoint_class} response is missing normalized payload hash"
            )
        try:
            exchange_timestamp_ms = int(response["exchange_timestamp_ms"])
            received_timestamp_ms = int(response["received_timestamp_ms"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InputContractError(
                f"{venue} {endpoint_class} response is missing normalized timestamps"
            ) from exc
        for row in rows:
            if not isinstance(row, dict):
                raise InputContractError(
                    f"{venue} {endpoint_class} record must be an object"
                )
            yield (
                venue,
                row,
                source_hash,
                exchange_timestamp_ms,
                received_timestamp_ms,
            )


def _base_metadata_reason(venue: str, row: dict[str, Any]) -> str | None:
    symbol = str(row.get("symbol") or "").upper()
    if venue not in VENUES:
        return "unsupported_venue"
    if not symbol or not symbol.endswith("USDT"):
        return "invalid_symbol"
    if str(row.get("asset_class") or "").lower() != "crypto":
        return "non_crypto_asset_class"
    if not str(row.get("underlying_id") or "").strip():
        return "missing_underlying_identity"
    if not str(row.get("identity_mapping_version") or "").strip():
        return "missing_identity_mapping_version"
    try:
        _positive_number(row.get("funding_interval_hours"), "funding_interval_hours")
        _positive_int(row.get("next_settlement_ts_ms"), "next_settlement_ts_ms")
    except InputContractError:
        return "missing_or_invalid_funding_schedule"
    return None


def metadata_reject_reason(venue: str, row: dict[str, Any]) -> str | None:
    """Return a fail-closed reject reason for venue-specific contract metadata."""

    base = _base_metadata_reason(venue, row)
    if base:
        return base

    if venue == "bybit":
        if row.get("contract_type") != "LinearPerpetual":
            return "not_perpetual"
        if row.get("status") != "Trading":
            return "contract_not_trading"
        if row.get("quote_asset") != "USDT" or row.get("settle_asset") != "USDT":
            return "wrong_quote_or_settle_asset"
        # Empty/unknown is deliberately rejected in v3.  Collectors must map
        # Bybit's public taxonomy to an explicit crypto class.
        if str(row.get("symbol_type") or "").lower() not in {"crypto", "innovation"}:
            return "bybit_taxonomy_not_crypto"
        return None

    if venue == "binance":
        if row.get("contract_type") != "PERPETUAL":
            return "not_perpetual"
        if row.get("status") != "TRADING":
            return "contract_not_trading"
        if row.get("quote_asset") != "USDT" or row.get("settle_asset") != "USDT":
            return "wrong_quote_or_settle_asset"
        if row.get("underlying_type") != "COIN":
            return "binance_underlying_not_coin"
        return None

    if venue == "bitget":
        if str(row.get("contract_type") or "").lower() != "perpetual":
            return "not_perpetual"
        if str(row.get("status") or "").lower() != "normal":
            return "contract_not_trading"
        if row.get("quote_asset") != "USDT" or row.get("settle_asset") != "USDT":
            return "wrong_quote_or_settle_asset"
        if str(row.get("is_rwa") or "").upper() != "NO":
            return "bitget_rwa_or_unknown"
        return None

    return "unsupported_venue"


def build_metadata_snapshot(public_snapshot: dict[str, Any]) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejects: Counter[str] = Counter()
    seen: dict[tuple[str, str], str] = {}
    for venue, source, source_hash, exchange_timestamp_ms, received_timestamp_ms in _records(
        public_snapshot.get("responses") or [], "instrument_metadata"
    ):
        row = dict(source)
        row["venue"] = venue
        row["symbol"] = str(row.get("symbol") or "").upper()
        reason = metadata_reject_reason(venue, row)
        if reason:
            rejects[reason] += 1
            continue
        row["funding_interval_hours"] = _positive_number(
            row["funding_interval_hours"], "funding_interval_hours"
        )
        row["next_settlement_ts_ms"] = _positive_int(
            row["next_settlement_ts_ms"], "next_settlement_ts_ms"
        )
        row["source_response_sha256"] = source_hash
        row["source_exchange_timestamp_ms"] = exchange_timestamp_ms
        row["source_received_timestamp_ms"] = received_timestamp_ms
        key = (venue, row["symbol"])
        digest_identity = "|".join(
            (
                str(row["underlying_id"]),
                str(row["identity_mapping_version"]),
                str(row["funding_interval_hours"]),
                str(row["next_settlement_ts_ms"]),
            )
        )
        if key in seen and seen[key] != digest_identity:
            raise InputContractError(f"conflicting metadata records for {venue}:{row['symbol']}")
        if key in seen:
            rejects["duplicate_identical_metadata"] += 1
            continue
        seen[key] = digest_identity
        accepted.append(row)

    accepted.sort(key=lambda row: (row["symbol"], row["venue"]))
    return {
        "schema_version": "settlement_execution_v3_metadata_snapshot_v1",
        "records": accepted,
        "reject_counters": dict(sorted(rejects.items())),
        "metrics": {
            "row_count": len(accepted),
            "reject_count": sum(rejects.values()),
        },
    }


def build_funding_snapshot(
    public_snapshot: dict[str, Any], metadata_snapshot: dict[str, Any]
) -> dict[str, Any]:
    metadata = {
        (str(row["venue"]), str(row["symbol"])): row
        for row in metadata_snapshot.get("records") or []
    }
    predicted: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    rejects: Counter[str] = Counter()
    seen_predicted: set[tuple[str, str]] = set()
    seen_history: dict[tuple[str, str, int], tuple[float, float]] = {}

    for venue, source, source_hash, exchange_timestamp_ms, received_timestamp_ms in _records(
        public_snapshot.get("responses") or [], "predicted_funding"
    ):
        symbol = str(source.get("symbol") or "").upper()
        meta = metadata.get((venue, symbol))
        if meta is None:
            rejects["predicted_without_accepted_metadata"] += 1
            continue
        try:
            rate = _finite_number(source.get("funding_rate"), "funding_rate")
            interval = _positive_number(
                source.get("funding_interval_hours"), "funding_interval_hours"
            )
            settlement = _positive_int(
                source.get("next_settlement_ts_ms"), "next_settlement_ts_ms"
            )
        except InputContractError:
            rejects["invalid_predicted_funding"] += 1
            continue
        if not math.isclose(
            interval,
            float(meta["funding_interval_hours"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or settlement != int(meta["next_settlement_ts_ms"]):
            rejects["funding_schedule_metadata_conflict"] += 1
            continue
        key = (venue, symbol)
        if key in seen_predicted:
            raise InputContractError(f"duplicate predicted funding for {venue}:{symbol}")
        seen_predicted.add(key)
        predicted.append(
            {
                "venue": venue,
                "symbol": symbol,
                "funding_rate": rate,
                "funding_interval_hours": interval,
                "next_settlement_ts_ms": settlement,
                "source_response_sha256": source_hash,
                "source_exchange_timestamp_ms": exchange_timestamp_ms,
                "source_received_timestamp_ms": received_timestamp_ms,
            }
        )

    for venue, source, source_hash, exchange_timestamp_ms, received_timestamp_ms in _records(
        public_snapshot.get("responses") or [], "funding_history"
    ):
        symbol = str(source.get("symbol") or "").upper()
        if (venue, symbol) not in metadata:
            rejects["history_without_accepted_metadata"] += 1
            continue
        try:
            rate = _finite_number(source.get("funding_rate"), "funding_rate")
            settlement = _positive_int(
                source.get("settlement_ts_ms"), "settlement_ts_ms"
            )
            settlement_mark_price = _positive_number(
                source.get("settlement_mark_price"), "settlement_mark_price"
            )
            settlement_mark_ts_ms = _positive_int(
                source.get("settlement_mark_ts_ms"), "settlement_mark_ts_ms"
            )
        except InputContractError:
            rejects["invalid_funding_history"] += 1
            continue
        if settlement_mark_ts_ms != settlement:
            rejects["non_exact_settlement_mark"] += 1
            continue
        if exchange_timestamp_ms < settlement or received_timestamp_ms < settlement:
            rejects["history_observed_before_settlement"] += 1
            continue
        key = (venue, symbol, settlement)
        previous = seen_history.get(key)
        observed = (rate, settlement_mark_price)
        if previous is not None and (
            not math.isclose(previous[0], observed[0], rel_tol=0.0, abs_tol=1e-15)
            or not math.isclose(previous[1], observed[1], rel_tol=0.0, abs_tol=1e-12)
        ):
            raise InputContractError(
                f"conflicting public settlement data for {venue}:{symbol}:{settlement}"
            )
        if previous is not None:
            rejects["duplicate_identical_history"] += 1
            continue
        seen_history[key] = observed
        history.append(
            {
                "venue": venue,
                "symbol": symbol,
                "settlement_ts_ms": settlement,
                "funding_rate": rate,
                "settlement_mark_price": settlement_mark_price,
                "settlement_mark_ts_ms": settlement_mark_ts_ms,
                "actual_public_settlement_receipt": True,
                "source_response_sha256": source_hash,
                "source_exchange_timestamp_ms": exchange_timestamp_ms,
                "source_received_timestamp_ms": received_timestamp_ms,
            }
        )

    predicted.sort(key=lambda row: (row["symbol"], row["venue"]))
    history.sort(
        key=lambda row: (row["settlement_ts_ms"], row["symbol"], row["venue"])
    )
    return {
        "schema_version": "settlement_execution_v3_funding_snapshot_v1",
        "as_of_ms": int(public_snapshot["as_of_ms"]),
        "predicted": predicted,
        "settlement_history": history,
        "reject_counters": dict(sorted(rejects.items())),
        "metrics": {
            "predicted_count": len(predicted),
            "settlement_receipt_count": len(history),
            "reject_count": sum(rejects.values()),
        },
    }


def scan_candidates(
    metadata_snapshot: dict[str, Any],
    funding_snapshot: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    metadata = {
        (row["venue"], row["symbol"]): row
        for row in metadata_snapshot.get("records") or []
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in funding_snapshot.get("predicted") or []:
        grouped[str(row["symbol"])].append(row)

    minimum_apr = float(config["ranking"]["minimum_predicted_spread_apr_pct"])
    candidates: list[dict[str, Any]] = []
    rejects: Counter[str] = Counter()
    as_of_ms = int(funding_snapshot["as_of_ms"])
    max_predicted_age_ms = int(config["execution"]["max_predicted_age_ms"])
    max_predicted_pair_skew_ms = int(
        config["execution"]["max_predicted_pair_skew_ms"]
    )
    for symbol, rows in sorted(grouped.items()):
        causal_rows: list[dict[str, Any]] = []
        for row in rows:
            ages = (
                as_of_ms - int(row["source_exchange_timestamp_ms"]),
                as_of_ms - int(row["source_received_timestamp_ms"]),
            )
            if any(age < 0 or age > max_predicted_age_ms for age in ages):
                rejects["stale_or_future_predicted_funding"] += 1
                continue
            causal_rows.append(row)
        if len({row["venue"] for row in causal_rows}) < 2:
            rejects["fewer_than_two_venues"] += 1
            continue
        enriched: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        for row in causal_rows:
            meta = metadata[(row["venue"], symbol)]
            annualized_pct = (
                float(row["funding_rate"])
                * (24.0 / float(row["funding_interval_hours"]))
                * 365.0
                * 100.0
            )
            enriched.append((annualized_pct, row, meta))
        high = max(enriched, key=lambda item: item[0])
        low = min(enriched, key=lambda item: item[0])
        if high[1]["venue"] == low[1]["venue"]:
            rejects["same_venue_route"] += 1
            continue
        if (
            abs(
                int(high[1]["source_exchange_timestamp_ms"])
                - int(low[1]["source_exchange_timestamp_ms"])
            )
            > max_predicted_pair_skew_ms
            or abs(
                int(high[1]["source_received_timestamp_ms"])
                - int(low[1]["source_received_timestamp_ms"])
            )
            > max_predicted_pair_skew_ms
        ):
            rejects["predicted_funding_pair_skew"] += 1
            continue
        if (
            high[2]["underlying_id"] != low[2]["underlying_id"]
            or high[2]["identity_mapping_version"]
            != low[2]["identity_mapping_version"]
        ):
            rejects["underlying_identity_conflict"] += 1
            continue
        spread = high[0] - low[0]
        if spread < minimum_apr:
            rejects["below_predicted_spread_gate"] += 1
            continue
        candidates.append(
            {
                "symbol": symbol,
                "underlying_id": high[2]["underlying_id"],
                "identity_mapping_version": high[2]["identity_mapping_version"],
                "short_venue": high[1]["venue"],
                "long_venue": low[1]["venue"],
                "short_predicted_rate": high[1]["funding_rate"],
                "long_predicted_rate": low[1]["funding_rate"],
                "short_interval_hours": high[1]["funding_interval_hours"],
                "long_interval_hours": low[1]["funding_interval_hours"],
                "short_next_settlement_ts_ms": high[1]["next_settlement_ts_ms"],
                "long_next_settlement_ts_ms": low[1]["next_settlement_ts_ms"],
                "predicted_spread_apr_pct": spread,
                "predicted_sources": {
                    "short": high[1]["source_response_sha256"],
                    "long": low[1]["source_response_sha256"],
                },
                "short_predicted_exchange_timestamp_ms": high[1][
                    "source_exchange_timestamp_ms"
                ],
                "long_predicted_exchange_timestamp_ms": low[1][
                    "source_exchange_timestamp_ms"
                ],
                "short_predicted_received_timestamp_ms": high[1][
                    "source_received_timestamp_ms"
                ],
                "long_predicted_received_timestamp_ms": low[1][
                    "source_received_timestamp_ms"
                ],
                "signal_ready_received_timestamp_ms": max(
                    int(high[1]["source_received_timestamp_ms"]),
                    int(low[1]["source_received_timestamp_ms"]),
                    int(high[2]["source_received_timestamp_ms"]),
                    int(low[2]["source_received_timestamp_ms"]),
                ),
            }
        )

    candidates.sort(
        key=lambda row: (row["predicted_spread_apr_pct"], row["symbol"]),
        reverse=True,
    )
    return {
        "schema_version": "settlement_execution_v3_scan_v1",
        "candidates": candidates,
        "reject_counters": dict(sorted(rejects.items())),
        "metrics": {
            "candidate_count": len(candidates),
            "reject_count": sum(rejects.values()),
        },
    }
