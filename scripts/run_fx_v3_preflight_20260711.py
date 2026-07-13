#!/usr/bin/env python3
"""Fail-closed data/news/cost preflight for the FX/CFD V3 research branch.

This runner intentionally does not compute strategy PnL.  The V3 configuration
is frozen before outcomes, but performance research is permitted only after all
of the following are present and hash-pinned:

* promotion-grade M5/H1 data for enough instruments;
* a historical macro-news calendar covering the research window;
* target-broker spread/commission/financing calibration.

When those inputs are absent, the only authorized output is data diagnostics.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.fx_calendar import assess_schedule_coverage  # noqa: E402
from bot.fx_instruments import get_instrument  # noqa: E402
from bot.fx_setups_v3 import (  # noqa: E402
    FailedBreakRetestShortConfig,
    HorizontalRangeConfig,
    HorizontalRangeRejectionConfig,
    RangeEdgeExpansionRetestConfig,
)
from scripts.run_fx_v2_preregistered_gate_20260711 import (  # noqa: E402
    _aggregate_h1_complete,
    _load_m5,
)


DEFAULT_CONFIG = ROOT / "configs" / "research" / "fx_v3_preflight_20260711.json"
DEFAULT_OUTPUT = ROOT / "reports" / "research" / "fx_v3_preflight_20260711"

FAMILY_CLASSES = {
    "failed_break_retest_short_v3": FailedBreakRetestShortConfig,
    "horizontal_range_rejection_v3": HorizontalRangeRejectionConfig,
    "range_edge_expansion_retest_v3": RangeEdgeExpansionRetestConfig,
}

SOURCE_PATHS = {
    "runner_sha256": "scripts/run_fx_v3_preflight_20260711.py",
    "setups_v3_sha256": "bot/fx_setups_v3.py",
    "contracts_sha256": "bot/fx_contracts.py",
    "instruments_sha256": "bot/fx_instruments.py",
    "calendar_sha256": "bot/fx_calendar.py",
    "harness_sha256": "bot/fx_harness_v2.py",
    "market_context_sha256": "bot/market_context.py",
    "range_filter_sha256": "bot/range_filter.py",
    "level_memory_sha256": "bot/level_memory.py",
    "news_session_filter_sha256": "bot/news_session_filter.py",
    "forex_regime_sha256": "forex/regime.py",
    "forex_types_sha256": "forex/types.py",
    "base_preflight_sha256": "scripts/run_fx_v2_preregistered_gate_20260711.py",
}

VALID_COST_SESSIONS = {
    "asian",
    "london",
    "london_ny_overlap",
    "newyork",
    "off_session",
    "all",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    data = [dict(row) for row in rows]
    if not data:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for row in data:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


def _instantiate_config(cls: type, params: Mapping[str, Any]) -> Any:
    allowed = {field.name for field in fields(cls)}
    unknown = sorted(set(params) - allowed)
    if unknown:
        raise ValueError(f"unknown {cls.__name__} fields: {unknown}")
    payload = dict(params)
    range_payload = payload.get("range")
    if range_payload is not None:
        if not isinstance(range_payload, Mapping):
            raise ValueError(f"{cls.__name__}.range must be an object")
        range_allowed = {field.name for field in fields(HorizontalRangeConfig)}
        range_unknown = sorted(set(range_payload) - range_allowed)
        if range_unknown:
            raise ValueError(f"unknown HorizontalRangeConfig fields: {range_unknown}")
        payload["range"] = HorizontalRangeConfig(**dict(range_payload))
    if "allowed_sessions" in payload:
        payload["allowed_sessions"] = tuple(payload["allowed_sessions"])
    return cls(**payload)


def validate_frozen_families(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    seen: set[str] = set()
    validated: Dict[str, Any] = {}
    for family in cfg.get("families", []):
        name = str(family.get("name", ""))
        if name not in FAMILY_CLASSES or name in seen:
            raise ValueError(f"unknown or duplicate V3 family: {name}")
        seen.add(name)
        sides = tuple(str(side) for side in family.get("sides", []))
        expected = ("short",) if name == "failed_break_retest_short_v3" else ("long", "short")
        if sides != expected:
            raise ValueError(f"{name} sides must be exactly {expected}")
        validated[name] = _instantiate_config(FAMILY_CLASSES[name], family.get("params", {}))
    if seen != set(FAMILY_CLASSES):
        raise ValueError(f"missing V3 families: {sorted(set(FAMILY_CLASSES) - seen)}")
    return validated


def _append_reason(reasons: list[str], reason: str) -> None:
    if reason and reason not in reasons:
        reasons.append(reason)


def _strict_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _artifact_kind(contract: Mapping[str, Any]) -> str:
    explicit = str(contract.get("artifact_kind", "")).strip().lower()
    if explicit:
        return explicit
    collection_key = str(contract.get("collection_key", "")).strip().lower()
    if collection_key == "events":
        return "historical_news"
    if collection_key in {"rows", "costs", "calibrations"} or contract.get("broker"):
        return "broker_cost_calibration"
    return "generic"


def _extract_rows(
    payload: Any, contract: Mapping[str, Any]
) -> tuple[list[Mapping[str, Any]], int]:
    raw_rows: list[Any] = []
    if isinstance(payload, list):
        raw_rows = payload
    elif isinstance(payload, Mapping):
        collection_key = str(contract.get("collection_key", "") or "")
        candidates = [collection_key] if collection_key else []
        candidates.extend(["events", "rows", "costs", "calibrations"])
        for key in candidates:
            candidate_rows = payload.get(key) if key else None
            if isinstance(candidate_rows, list):
                raw_rows = candidate_rows
                break
    rows = [row for row in raw_rows if isinstance(row, Mapping)]
    return rows, len(raw_rows) - len(rows)


def _required_window(
    contract: Mapping[str, Any], *, prefix: str, reasons: list[str]
) -> tuple[int | None, int | None]:
    start = _strict_int(contract.get("required_window_start_ts"))
    end = _strict_int(contract.get("required_window_end_ts_exclusive"))
    if start is None or end is None or start <= 0 or end <= start:
        _append_reason(reasons, f"{prefix}_contract_missing_valid_required_window")
        return None, None
    return start, end


def _news_contract(
    contract: Mapping[str, Any], reasons: list[str]
) -> tuple[tuple[str, ...], int | None, float | None, int | None, int | None]:
    start, end = _required_window(contract, prefix="news", reasons=reasons)
    raw_currencies = contract.get("required_currencies")
    currencies: list[str] = []
    if not isinstance(raw_currencies, list) or not raw_currencies:
        _append_reason(reasons, "news_contract_missing_required_currencies")
    else:
        for raw in raw_currencies:
            currency = str(raw).strip()
            if currency != currency.upper() or len(currency) != 3 or not currency.isalpha():
                _append_reason(reasons, "news_contract_invalid_required_currency")
                continue
            if currency in currencies:
                _append_reason(reasons, "news_contract_duplicate_required_currency")
                continue
            currencies.append(currency)

    min_events = _strict_int(contract.get("min_events_per_currency"))
    if min_events is None or min_events <= 0:
        min_events = None
        _append_reason(reasons, "news_contract_missing_min_events_per_currency")

    max_gap_days = _finite_number(contract.get("max_event_gap_days_per_currency"))
    if max_gap_days is None or max_gap_days <= 0:
        max_gap_days = None
        _append_reason(reasons, "news_contract_missing_max_event_gap_days_per_currency")
    return tuple(currencies), min_events, max_gap_days, start, end


def _validate_news_artifact(
    payload: Any,
    rows: list[Mapping[str, Any]],
    contract: Mapping[str, Any],
    contract_reasons: list[str],
) -> Dict[str, Any]:
    reasons = list(contract_reasons)
    currencies, min_events, max_gap_days, required_start, required_end = _news_contract(
        contract, reasons
    )
    required_fields = {str(field) for field in contract.get("required_fields", [])}
    min_rows = max(1, int(contract.get("min_rows", 1)))
    if len(rows) < min_rows:
        _append_reason(reasons, "news_rows_below_minimum")
    if any(not required_fields.issubset(row.keys()) for row in rows):
        _append_reason(reasons, "news_row_missing_required_fields")

    payload_start = payload_end = None
    if isinstance(payload, Mapping):
        payload_start = _strict_int(payload.get("window_start_ts"))
        payload_end = _strict_int(payload.get("window_end_ts_exclusive"))
    envelope_ok = bool(
        payload_start is not None
        and payload_end is not None
        and payload_start > 0
        and payload_end > payload_start
    )
    if not envelope_ok:
        _append_reason(reasons, "news_payload_window_invalid")
    elif required_start is not None and required_end is not None and not (
        payload_start <= required_start and payload_end >= required_end
    ):
        envelope_ok = False
        _append_reason(reasons, "news_payload_window_does_not_cover_required")

    valid_events: list[tuple[int, str, str, int]] = []
    invalid_rows = 0
    for row in rows:
        row_valid = required_fields.issubset(row.keys())
        ts = _strict_int(row.get("ts"))
        currency = str(row.get("currency", "")).strip()
        impact = _strict_int(row.get("impact"))
        event = str(row.get("event", "")).strip()
        if ts is None or ts <= 0:
            _append_reason(reasons, "news_invalid_timestamp")
            row_valid = False
        elif envelope_ok and not (int(payload_start) <= ts < int(payload_end)):
            _append_reason(reasons, "news_timestamp_outside_declared_window")
            row_valid = False
        if currency != currency.upper() or len(currency) != 3 or not currency.isalpha():
            _append_reason(reasons, "news_invalid_currency")
            row_valid = False
        if impact not in {1, 2, 3}:
            _append_reason(reasons, "news_invalid_impact")
            row_valid = False
        if not event:
            _append_reason(reasons, "news_empty_event")
            row_valid = False
        if row_valid and ts is not None:
            valid_events.append(
                (ts, currency, " ".join(event.casefold().split()), int(impact))
            )
        else:
            invalid_rows += 1

    seen_events: Dict[tuple[int, str, str], int] = {}
    duplicate_rows = 0
    for ts, currency, event, impact in valid_events:
        event_key = (ts, currency, event)
        if event_key in seen_events:
            duplicate_rows += 1
        else:
            seen_events[event_key] = impact
    if duplicate_rows:
        _append_reason(reasons, "news_duplicate_events")

    counts: Dict[str, int] = {}
    max_gaps_days: Dict[str, float] = {}
    coverage_ok = bool(envelope_ok and currencies and min_events and max_gap_days)
    if coverage_ok and required_start is not None and required_end is not None:
        for currency in currencies:
            timestamps = sorted(
                ts
                for (ts, row_currency, _), impact in seen_events.items()
                if (
                    row_currency == currency
                    and impact >= 2
                    and required_start <= ts < required_end
                )
            )
            counts[currency] = len(timestamps)
            if len(timestamps) < int(min_events):
                coverage_ok = False
                _append_reason(reasons, "news_currency_below_min_events")
            points = [required_start, *timestamps, required_end]
            max_gap = max(
                (right - left for left, right in zip(points, points[1:])),
                default=required_end - required_start,
            )
            max_gaps_days[currency] = round(max_gap / 86400.0, 6)
            if max_gap > float(max_gap_days) * 86400.0:
                coverage_ok = False
                _append_reason(reasons, "news_currency_gap_exceeds_contract")
    else:
        coverage_ok = False

    schema_ok = bool(
        len(rows) >= min_rows
        and not invalid_rows
        and all(required_fields.issubset(row.keys()) for row in rows)
    )
    quality_ok = bool(schema_ok and not duplicate_rows and coverage_ok)
    return {
        "schema_ok": schema_ok,
        "coverage_ok": coverage_ok,
        "quality_ok": quality_ok,
        "invalid_rows": invalid_rows,
        "duplicate_rows": duplicate_rows,
        "coverage_details": {
            "required_currencies": list(currencies),
            "coverage_min_impact": 2,
            "events_per_currency": counts,
            "max_gap_days_per_currency": max_gaps_days,
        },
        "reasons": reasons,
    }


def _canonical_cost_pair(raw: Any) -> tuple[str, str] | None:
    if not isinstance(raw, Mapping):
        return None
    symbol = str(raw.get("symbol", "")).strip()
    session = str(raw.get("session", "")).strip()
    if (
        symbol != symbol.upper()
        or not (3 <= len(symbol) <= 20)
        or not symbol.replace("_", "").isalnum()
        or session != session.lower()
        or session not in VALID_COST_SESSIONS
    ):
        return None
    return symbol, session


def _required_cost_pairs(
    contract: Mapping[str, Any], reasons: list[str]
) -> set[tuple[str, str]]:
    required: set[tuple[str, str]] = set()
    raw_pairs = contract.get("required_symbol_sessions")
    if isinstance(raw_pairs, list) and raw_pairs:
        for raw in raw_pairs:
            pair = _canonical_cost_pair(raw)
            if pair is None:
                _append_reason(reasons, "cost_contract_invalid_required_symbol_session")
                continue
            if pair in required:
                _append_reason(reasons, "cost_contract_duplicate_required_symbol_session")
            required.add(pair)
        return required

    raw_symbols = contract.get("required_symbols")
    raw_sessions = contract.get("required_sessions")
    if isinstance(raw_symbols, list) and raw_symbols and isinstance(raw_sessions, list) and raw_sessions:
        for raw_symbol in raw_symbols:
            for raw_session in raw_sessions:
                pair = _canonical_cost_pair({"symbol": raw_symbol, "session": raw_session})
                if pair is None:
                    _append_reason(reasons, "cost_contract_invalid_required_symbol_session")
                    continue
                required.add(pair)
        return required

    _append_reason(reasons, "cost_contract_missing_required_symbol_sessions")
    return required


def _cost_contract(
    contract: Mapping[str, Any], reasons: list[str]
) -> tuple[str, str, set[tuple[str, str]]]:
    broker = str(contract.get("broker", "")).strip()
    if broker.upper() != "OANDA":
        _append_reason(reasons, "cost_contract_broker_must_be_oanda")
    account_type = str(contract.get("account_type", "")).strip()
    lowered = account_type.casefold()
    if not account_type or any(
        marker in lowered for marker in ("unconfirmed", "unknown", "placeholder")
    ):
        _append_reason(reasons, "cost_contract_account_type_unconfirmed")
    required_pairs = _required_cost_pairs(contract, reasons)
    return broker, account_type, required_pairs


def external_input_contract_blockers(cfg: Mapping[str, Any]) -> Dict[str, list[str]]:
    """Return definition-only blockers without reading artifacts or market outcomes.

    This gate deliberately runs before source-hash validation in ``main``.  It lets
    an old frozen config fail with actionable contract errors, while still requiring
    a new versioned preregistration (including new source hashes) before any changed
    runner can proceed to data or performance work.
    """

    blockers: Dict[str, list[str]] = {}
    for key in ("historical_news", "broker_cost_calibration"):
        contract = cfg.get(key)
        reasons: list[str] = []
        if not isinstance(contract, Mapping):
            reasons.append(f"{key}_contract_missing")
        else:
            kind = _artifact_kind(contract)
            if key == "historical_news" and kind != "historical_news":
                reasons.append("news_contract_artifact_kind_invalid")
            elif key == "broker_cost_calibration" and kind != "broker_cost_calibration":
                reasons.append("cost_contract_artifact_kind_invalid")
            if key == "historical_news":
                _news_contract(contract, reasons)
            else:
                _cost_contract(contract, reasons)
        if reasons:
            blockers[key] = reasons
    return blockers


def _validate_cost_artifact(
    payload: Any,
    rows: list[Mapping[str, Any]],
    contract: Mapping[str, Any],
    contract_reasons: list[str],
) -> Dict[str, Any]:
    reasons = list(contract_reasons)
    broker, account_type, required_pairs = _cost_contract(contract, reasons)
    required_fields = {str(field) for field in contract.get("required_fields", [])}
    min_rows = max(1, int(contract.get("min_rows", 1)))
    min_observations = max(1, int(contract.get("min_observations_per_row", 1)))
    if len(rows) < min_rows:
        _append_reason(reasons, "cost_rows_below_minimum")
    if any(not required_fields.issubset(row.keys()) for row in rows):
        _append_reason(reasons, "cost_row_missing_required_fields")

    payload_broker = str(payload.get("broker", "")).strip() if isinstance(payload, Mapping) else ""
    payload_account_type = (
        str(payload.get("account_type", "")).strip() if isinstance(payload, Mapping) else ""
    )
    metadata_ok = True
    if not payload_broker or payload_broker.casefold() != broker.casefold():
        metadata_ok = False
        _append_reason(reasons, "cost_payload_broker_mismatch")
    if not payload_account_type or payload_account_type.casefold() != account_type.casefold():
        metadata_ok = False
        _append_reason(reasons, "cost_payload_account_type_mismatch")

    seen_pairs: set[tuple[str, str]] = set()
    duplicate_rows = 0
    invalid_rows = 0
    for row in rows:
        row_valid = required_fields.issubset(row.keys())
        pair = _canonical_cost_pair(row)
        if pair is None:
            _append_reason(reasons, "cost_invalid_symbol_or_session")
            row_valid = False

        p50 = _finite_number(row.get("spread_bps_p50"))
        p95 = _finite_number(row.get("spread_bps_p95"))
        commission = _finite_number(row.get("commission_bps_per_side"))
        financing = _finite_number(row.get("financing_bps_per_day"))
        observations = _strict_int(row.get("observations"))
        if any(value is None or value < 0 for value in (p50, p95, commission, financing)):
            _append_reason(reasons, "cost_invalid_numeric_value")
            row_valid = False
        elif float(p50) > float(p95):
            _append_reason(reasons, "cost_spread_p50_exceeds_p95")
            row_valid = False
        if observations is None or observations < min_observations:
            _append_reason(reasons, "cost_observations_below_minimum")
            row_valid = False

        if pair is not None:
            if pair in seen_pairs:
                duplicate_rows += 1
            seen_pairs.add(pair)
        if not row_valid:
            invalid_rows += 1

    if duplicate_rows:
        _append_reason(reasons, "cost_duplicate_symbol_session_rows")
    missing_pairs = sorted(required_pairs - seen_pairs)
    if missing_pairs:
        _append_reason(reasons, "cost_required_symbol_session_missing")
    unexpected_pairs = sorted(seen_pairs - required_pairs)
    if unexpected_pairs:
        _append_reason(reasons, "cost_unexpected_symbol_session")
    coverage_ok = bool(required_pairs and not missing_pairs and not unexpected_pairs)
    schema_ok = bool(
        len(rows) >= min_rows
        and not invalid_rows
        and all(required_fields.issubset(row.keys()) for row in rows)
    )
    quality_ok = bool(schema_ok and metadata_ok and not duplicate_rows and coverage_ok)
    return {
        "schema_ok": schema_ok,
        "coverage_ok": coverage_ok,
        "quality_ok": quality_ok,
        "invalid_rows": invalid_rows,
        "duplicate_rows": duplicate_rows,
        "coverage_details": {
            "required_symbol_sessions": [list(pair) for pair in sorted(required_pairs)],
            "observed_symbol_sessions": [list(pair) for pair in sorted(seen_pairs)],
            "missing_symbol_sessions": [list(pair) for pair in missing_pairs],
            "unexpected_symbol_sessions": [list(pair) for pair in unexpected_pairs],
        },
        "reasons": reasons,
    }


def _validate_generic_artifact(
    payload: Any,
    rows: list[Mapping[str, Any]],
    contract: Mapping[str, Any],
    contract_reasons: list[str],
) -> Dict[str, Any]:
    reasons = list(contract_reasons)
    required_fields = {str(field) for field in contract.get("required_fields", [])}
    min_rows = max(1, int(contract.get("min_rows", 1)))
    schema_ok = len(rows) >= min_rows and all(
        required_fields.issubset(row.keys()) for row in rows
    )
    if not schema_ok:
        _append_reason(reasons, "artifact_schema_invalid")
    required_start = contract.get("required_window_start_ts")
    required_end = contract.get("required_window_end_ts_exclusive")
    coverage_ok = required_start is None and required_end is None
    if required_start is not None or required_end is not None:
        if isinstance(payload, Mapping):
            start = _strict_int(payload.get("window_start_ts"))
            end = _strict_int(payload.get("window_end_ts_exclusive"))
            coverage_ok = bool(
                start is not None
                and end is not None
                and start <= int(required_start)
                and end >= int(required_end)
            )
        if not coverage_ok:
            _append_reason(reasons, "artifact_window_coverage_invalid")
    return {
        "schema_ok": schema_ok,
        "coverage_ok": coverage_ok,
        "quality_ok": schema_ok,
        "invalid_rows": 0,
        "duplicate_rows": 0,
        "coverage_details": {},
        "reasons": reasons,
    }


def external_artifact_status(root: Path, contract: Mapping[str, Any]) -> Dict[str, Any]:
    path = root / str(contract.get("path", ""))
    kind = _artifact_kind(contract)
    contract_reasons: list[str] = []
    if kind == "historical_news":
        _news_contract(contract, contract_reasons)
    elif kind == "broker_cost_calibration":
        _cost_contract(contract, contract_reasons)

    exists = path.is_file()
    actual = _sha256(path) if exists else ""
    expected = str(contract.get("sha256", ""))
    hash_ok = bool(exists and expected and actual == expected)
    parse_ok = False
    schema_ok = False
    coverage_ok = False
    quality_ok = False
    rows: list[Mapping[str, Any]] = []
    payload: Any = None
    reasons = list(contract_reasons)
    invalid_rows = 0
    duplicate_rows = 0
    coverage_details: Dict[str, Any] = {}

    if bool(contract.get("required", True)) and not exists:
        _append_reason(reasons, "artifact_missing")
    if not expected:
        _append_reason(reasons, "artifact_sha256_unpinned")
    elif exists and actual != expected:
        _append_reason(reasons, "artifact_sha256_mismatch")

    if hash_ok:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            parse_ok = True
        except Exception:
            payload = None
            _append_reason(reasons, "artifact_json_parse_failed")

    if parse_ok:
        rows, non_mapping_rows = _extract_rows(payload, contract)
        if kind == "historical_news":
            validation = _validate_news_artifact(payload, rows, contract, contract_reasons)
        elif kind == "broker_cost_calibration":
            validation = _validate_cost_artifact(payload, rows, contract, contract_reasons)
        else:
            validation = _validate_generic_artifact(payload, rows, contract, contract_reasons)
        schema_ok = bool(validation["schema_ok"])
        coverage_ok = bool(validation["coverage_ok"])
        quality_ok = bool(validation["quality_ok"])
        invalid_rows = int(validation["invalid_rows"])
        duplicate_rows = int(validation["duplicate_rows"])
        coverage_details = dict(validation["coverage_details"])
        if non_mapping_rows:
            invalid_rows += non_mapping_rows
            schema_ok = False
            quality_ok = False
            _append_reason(
                reasons,
                "news_non_object_rows"
                if kind == "historical_news"
                else (
                    "cost_non_object_rows"
                    if kind == "broker_cost_calibration"
                    else "artifact_non_object_rows"
                ),
            )
        for reason in validation["reasons"]:
            _append_reason(reasons, str(reason))

    content_ok = bool(parse_ok and schema_ok and coverage_ok and quality_ok)
    required = bool(contract.get("required", True))
    ok = bool(hash_ok and content_ok and not reasons)
    if not required and not exists and not contract_reasons:
        ok = True
    return {
        "artifact_kind": kind,
        "path": str(path),
        "required": required,
        "exists": exists,
        "expected_sha256": expected,
        "actual_sha256": actual,
        "hash_ok": hash_ok,
        "parse_ok": parse_ok,
        "schema_ok": schema_ok,
        "coverage_ok": coverage_ok,
        "quality_ok": quality_ok,
        "rows": len(rows),
        "invalid_rows": invalid_rows,
        "duplicate_rows": duplicate_rows,
        "coverage_details": coverage_details,
        "reasons": reasons,
        "ok": ok,
    }


def classify_permission(
    *,
    diagnostic_symbols: int,
    promotion_symbols: int,
    min_diagnostic_symbols: int,
    min_promotion_symbols: int,
    news_ok: bool,
    costs_ok: bool,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if diagnostic_symbols < min_diagnostic_symbols:
        blockers.append("insufficient_diagnostic_data")
    if promotion_symbols < min_promotion_symbols:
        blockers.append("strict_promotion_data_gate_failed")
    if not news_ok:
        blockers.append("historical_news_calendar_missing_or_unpinned")
    if not costs_ok:
        blockers.append("target_broker_cost_calibration_missing_or_unpinned")
    if "insufficient_diagnostic_data" in blockers:
        return "INVALID_DATA", blockers
    if blockers:
        return "DATA_DIAGNOSTICS_ONLY", blockers
    return "PERFORMANCE_RESEARCH_ALLOWED", blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite evidence: {output}")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    if not (
        cfg.get("research_only")
        and cfg.get("frozen_before_results")
        and cfg.get("no_parameter_scan")
        and cfg.get("execution_permission") == "preflight_decides"
    ):
        raise SystemExit("config must be frozen research-only/no-scan and preflight-decides")

    validated = validate_frozen_families(cfg)
    contract_blockers = external_input_contract_blockers(cfg)
    if contract_blockers:
        raise SystemExit(
            "external input contract gate failed: "
            + json.dumps(contract_blockers, sort_keys=True)
        )

    source_mismatches = []
    for key, rel in SOURCE_PATHS.items():
        actual = _sha256(ROOT / rel)
        expected = str(cfg.get("source_code", {}).get(key, ""))
        if not expected or expected != actual:
            source_mismatches.append(
                {"key": key, "path": rel, "expected": expected, "actual": actual}
            )
    if source_mismatches:
        raise SystemExit("source SHA256 gate failed: " + json.dumps(source_mismatches, sort_keys=True))
    output.mkdir(parents=True)

    data = cfg["data"]
    start = int(data["window_start_ts"])
    end = int(data["window_end_ts_exclusive"])
    as_of = int(data["snapshot_as_of_ts"])
    interval_sec = int(data["source_interval_min"]) * 60
    coverage: list[Dict[str, Any]] = []
    diagnostic_symbols: list[str] = []
    promotion_symbols: list[str] = []

    for symbol in data["symbols"]:
        spec = get_instrument(symbol)
        path = ROOT / data["data_dir"] / f"{symbol}_M5.csv"
        if not path.exists():
            coverage.append({"symbol": symbol, "diagnostic_data_ok": False, "promotion_data_ok": False, "reasons": "missing_file"})
            continue
        actual_hash = _sha256(path)
        input_hash_ok = actual_hash == str(data["input_sha256"].get(symbol, ""))
        try:
            raw = _load_m5(path)
        except ValueError as exc:
            coverage.append({
                "symbol": symbol,
                "diagnostic_data_ok": False,
                "promotion_data_ok": False,
                "input_sha256": actual_hash,
                "input_hash_ok": input_hash_ok,
                "reasons": f"loader:{exc}",
            })
            continue
        source = [row for row in raw if start <= int(row[0]) < end]
        latest = max((int(row[0]) for row in raw), default=0)
        snapshot_age_hours = max(0.0, (as_of - latest) / 3600.0)
        source_report = assess_schedule_coverage(
            source,
            symbol=symbol,
            schedule=spec.schedule,
            interval_sec=interval_sec,
            min_coverage=float(data["source_min_coverage"]),
            max_missing_run=int(data["source_max_missing_run"]),
            min_bars=int(data["source_min_bars"]),
            min_span_days=float(data["min_span_days"]),
            max_off_schedule_bars=int(data["max_off_schedule_bars"]),
            window_start_ts=start,
            window_end_ts_exclusive=end,
        )
        h1, incomplete = _aggregate_h1_complete(
            source,
            schedule=spec.schedule,
            source_interval_sec=interval_sec,
        )
        h1_report = assess_schedule_coverage(
            h1,
            symbol=symbol,
            schedule=spec.schedule,
            interval_sec=3600,
            min_coverage=float(data["h1_min_coverage"]),
            max_missing_run=int(data["h1_max_missing_run"]),
            min_bars=int(data["h1_min_bars"]),
            min_span_days=float(data["min_span_days"]),
            max_off_schedule_bars=0,
            window_start_ts=start,
            window_end_ts_exclusive=end,
        )
        snapshot_fresh = snapshot_age_hours <= float(data["max_snapshot_age_hours"])
        promotion_ok = bool(
            input_hash_ok
            and snapshot_fresh
            and source_report.ok
            and h1_report.ok
            and not incomplete
        )
        diagnostic_ok = bool(
            input_hash_ok
            and source_report.coverage >= float(data["source_min_coverage"])
            and source_report.duplicate_bars == 0
            and source_report.invalid_ohlc_bars == 0
            and source_report.actual_expected_bars >= int(data["source_min_bars"])
            and h1_report.coverage >= float(data["h1_min_coverage"])
            and h1_report.duplicate_bars == 0
            and h1_report.invalid_ohlc_bars == 0
            and h1_report.actual_expected_bars >= int(data["h1_min_bars"])
            and h1_report.span_days >= float(data["min_span_days"])
        )
        if diagnostic_ok:
            diagnostic_symbols.append(symbol)
        if promotion_ok:
            promotion_symbols.append(symbol)
        coverage.append({
            "symbol": symbol,
            "diagnostic_data_ok": diagnostic_ok,
            "promotion_data_ok": promotion_ok,
            "input_sha256": actual_hash,
            "input_hash_ok": input_hash_ok,
            "snapshot_age_hours": round(snapshot_age_hours, 3),
            "snapshot_fresh": snapshot_fresh,
            "source_coverage": source_report.coverage,
            "source_max_missing_run": source_report.max_missing_run,
            "source_off_schedule_bars": source_report.off_schedule_bars,
            "source_reasons": ";".join(source_report.reasons),
            "h1_coverage": h1_report.coverage,
            "h1_max_missing_run": h1_report.max_missing_run,
            "h1_reasons": ";".join(h1_report.reasons),
            "incomplete_h1_buckets": len(incomplete),
            "max_h1_missing_subbars": max((int(row["missing_subbars"]) for row in incomplete), default=0),
        })

    news = external_artifact_status(ROOT, cfg["historical_news"])
    costs = external_artifact_status(ROOT, cfg["broker_cost_calibration"])
    status, blockers = classify_permission(
        diagnostic_symbols=len(diagnostic_symbols),
        promotion_symbols=len(promotion_symbols),
        min_diagnostic_symbols=int(data["min_diagnostic_symbols"]),
        min_promotion_symbols=int(data["min_promotion_symbols"]),
        news_ok=bool(news["ok"]),
        costs_ok=bool(costs["ok"]),
    )
    _write_csv(output / "coverage.csv", coverage)
    preflight = {
        "status": status,
        "performance_research_allowed": status == "PERFORMANCE_RESEARCH_ALLOWED",
        "diagnostic_symbols": sorted(diagnostic_symbols),
        "promotion_symbols": sorted(promotion_symbols),
        "blocked_symbols": sorted(set(data["symbols"]) - set(promotion_symbols)),
        "historical_news": news,
        "broker_cost_calibration": costs,
        "input_contract_blockers": {
            "historical_news": list(news.get("reasons", [])),
            "broker_cost_calibration": list(costs.get("reasons", [])),
        },
        "blockers": blockers,
        "validated_families": sorted(validated),
        "candidate_sides": {
            family["name"]: family["sides"] for family in cfg["families"]
        },
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "source_sha256": {key: _sha256(ROOT / rel) for key, rel in SOURCE_PATHS.items()},
    }
    (output / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    summary = [
        "# FX/CFD V3 fail-closed preflight — 2026-07-11",
        "",
        f"- Status: **{status}**.",
        f"- Performance research allowed: **{str(preflight['performance_research_allowed']).lower()}**.",
        f"- Diagnostic symbols: `{','.join(sorted(diagnostic_symbols)) or 'none'}`.",
        f"- Promotion-grade symbols: `{','.join(sorted(promotion_symbols)) or 'none'}`.",
        f"- Historical news artifact valid: `{news['ok']}`.",
        f"- Historical news blockers: `{';'.join(news.get('reasons', [])) or 'none'}`.",
        f"- Target-broker cost calibration valid: `{costs['ok']}`.",
        f"- Target-broker cost blockers: `{';'.join(costs.get('reasons', [])) or 'none'}`.",
        f"- Blockers: `{';'.join(blockers) or 'none'}`.",
        "",
        "No strategy PnL, demo order, or live order is produced by this runner.",
    ]
    (output / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "blockers": blockers, "diagnostic_symbols": sorted(diagnostic_symbols)}), flush=True)
    return 2 if status == "INVALID_DATA" else 0


if __name__ == "__main__":
    raise SystemExit(main())
