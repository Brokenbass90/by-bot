from __future__ import annotations

import json
import hashlib

import pytest

from scripts.run_fx_v3_preflight_20260711 import (
    classify_permission,
    external_input_contract_blockers,
    external_artifact_status,
    validate_frozen_families,
)


def _families() -> list[dict]:
    shared_range = {
        "lookback": 72,
        "min_touches": 2,
        "tolerance_atr": 0.35,
        "min_width_atr": 2.0,
        "max_width_atr": 8.0,
        "min_range_votes": 2,
        "require_all_range_votes": False,
    }
    return [
        {
            "name": "failed_break_retest_short_v3",
            "sides": ["short"],
            "params": {"range": shared_range},
        },
        {
            "name": "horizontal_range_rejection_v3",
            "sides": ["long", "short"],
            "params": {"range": shared_range},
        },
        {
            "name": "range_edge_expansion_retest_v3",
            "sides": ["long", "short"],
            "params": {"range": shared_range},
        },
    ]


def test_frozen_family_contract_side_separates_candidates() -> None:
    validated = validate_frozen_families({"families": _families()})
    assert sorted(validated) == [
        "failed_break_retest_short_v3",
        "horizontal_range_rejection_v3",
        "range_edge_expansion_retest_v3",
    ]
    assert validated["failed_break_retest_short_v3"].range.lookback == 72


def test_frozen_family_contract_rejects_combined_failed_break() -> None:
    families = _families()
    families[0]["sides"] = ["long", "short"]
    with pytest.raises(ValueError, match="sides must be exactly"):
        validate_frozen_families({"families": families})


def test_preflight_blocks_performance_when_news_cost_or_data_missing() -> None:
    status, blockers = classify_permission(
        diagnostic_symbols=4,
        promotion_symbols=0,
        min_diagnostic_symbols=3,
        min_promotion_symbols=3,
        news_ok=False,
        costs_ok=False,
    )
    assert status == "DATA_DIAGNOSTICS_ONLY"
    assert "strict_promotion_data_gate_failed" in blockers
    assert "historical_news_calendar_missing_or_unpinned" in blockers
    assert "target_broker_cost_calibration_missing_or_unpinned" in blockers


def test_preflight_allows_performance_only_when_every_gate_passes() -> None:
    assert classify_permission(
        diagnostic_symbols=4,
        promotion_symbols=3,
        min_diagnostic_symbols=3,
        min_promotion_symbols=3,
        news_ok=True,
        costs_ok=True,
    ) == ("PERFORMANCE_RESEARCH_ALLOWED", [])


def test_external_artifact_must_exist_and_be_hash_pinned(tmp_path) -> None:
    missing = external_artifact_status(
        tmp_path,
        {"path": "news.json", "sha256": "", "required": True},
    )
    assert not missing["ok"]
    path = tmp_path / "news.json"
    path.write_text(json.dumps({"events": []}), encoding="utf-8")
    unpinned = external_artifact_status(
        tmp_path,
        {"path": "news.json", "sha256": "", "required": True},
    )
    assert unpinned["exists"] and not unpinned["ok"]


def test_pinned_artifact_still_requires_schema_and_window_coverage(tmp_path) -> None:
    path = tmp_path / "news.json"
    path.write_text(json.dumps({"events": [{}]}), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    malformed = external_artifact_status(
        tmp_path,
        {
            "path": "news.json",
            "sha256": digest,
            "required": True,
            "collection_key": "events",
            "required_fields": ["ts", "currency", "impact", "event"],
            "required_window_start_ts": 100,
            "required_window_end_ts_exclusive": 200,
        },
    )
    assert malformed["hash_ok"]
    assert not malformed["schema_ok"]
    assert not malformed["coverage_ok"]
    assert not malformed["ok"]


def _news_contract(path: str, digest: str, start: int, end: int) -> dict:
    return {
        "path": path,
        "sha256": digest,
        "required": True,
        "collection_key": "events",
        "required_fields": ["ts", "currency", "impact", "event"],
        "required_window_start_ts": start,
        "required_window_end_ts_exclusive": end,
        "required_currencies": ["USD", "EUR"],
        "min_events_per_currency": 3,
        "max_event_gap_days_per_currency": 26,
        "min_rows": 6,
    }


def _cost_contract(path: str, digest: str) -> dict:
    return {
        "path": path,
        "sha256": digest,
        "required": True,
        "broker": "OANDA",
        "account_type": "spread_only",
        "collection_key": "rows",
        "min_rows": 2,
        "min_observations_per_row": 20,
        "required_symbol_sessions": [
            {"symbol": "EURUSD", "session": "london"},
            {"symbol": "USDJPY", "session": "newyork"},
        ],
        "required_fields": [
            "symbol",
            "session",
            "spread_bps_p50",
            "spread_bps_p95",
            "commission_bps_per_side",
            "financing_bps_per_day",
            "observations",
        ],
    }


def test_pinned_news_passes_only_with_typed_rows_and_measurable_coverage(tmp_path) -> None:
    day = 86400
    start = 1_700_000_000
    end = start + 60 * day
    path = tmp_path / "news.json"
    path.write_text(
        json.dumps(
            {
                "window_start_ts": start - day,
                "window_end_ts_exclusive": end + day,
                "events": [
                    {"ts": start + 5 * day, "currency": "USD", "impact": 3, "event": "CPI"},
                    {"ts": start + 30 * day, "currency": "USD", "impact": 2, "event": "FOMC"},
                    {"ts": start + 55 * day, "currency": "USD", "impact": 3, "event": "NFP"},
                    {"ts": start + 10 * day, "currency": "EUR", "impact": 2, "event": "CPI"},
                    {"ts": start + 35 * day, "currency": "EUR", "impact": 3, "event": "ECB"},
                    {"ts": start + 50 * day, "currency": "EUR", "impact": 2, "event": "PMI"},
                ],
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    valid = external_artifact_status(
        tmp_path,
        _news_contract("news.json", digest, start, end),
    )
    assert valid["ok"]
    assert valid["rows"] == 6
    assert valid["invalid_rows"] == 0
    assert valid["duplicate_rows"] == 0
    assert valid["coverage_details"]["events_per_currency"] == {"USD": 3, "EUR": 3}


def test_news_contract_fails_closed_without_measurable_currency_coverage(tmp_path) -> None:
    path = tmp_path / "news.json"
    path.write_text(
        json.dumps(
            {
                "window_start_ts": 1_699_999_900,
                "window_end_ts_exclusive": 1_700_000_200,
                "events": [
                    {"ts": 1_700_000_050, "currency": "USD", "impact": 3, "event": "CPI"}
                ],
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    status = external_artifact_status(
        tmp_path,
        {
            "path": "news.json",
            "sha256": digest,
            "required": True,
            "collection_key": "events",
            "required_fields": ["ts", "currency", "impact", "event"],
            "required_window_start_ts": 1_700_000_000,
            "required_window_end_ts_exclusive": 1_700_000_100,
        },
    )
    assert not status["ok"]
    assert "news_contract_missing_required_currencies" in status["reasons"]
    assert "news_contract_missing_min_events_per_currency" in status["reasons"]
    assert "news_contract_missing_max_event_gap_days_per_currency" in status["reasons"]


def test_news_rejects_duplicate_or_malformed_event_rows(tmp_path) -> None:
    day = 86400
    start = 1_700_000_000
    end = start + 60 * day
    duplicate = {"ts": start + 5 * day, "currency": "USD", "impact": 3, "event": "CPI"}
    path = tmp_path / "news.json"
    path.write_text(
        json.dumps(
            {
                "window_start_ts": start,
                "window_end_ts_exclusive": end,
                "events": [
                    duplicate,
                    dict(duplicate),
                    {"ts": str(start + 30 * day), "currency": "USD", "impact": 3, "event": "FOMC"},
                    {"ts": start + 10 * day, "currency": "eur", "impact": 2, "event": "CPI"},
                    {"ts": start + 35 * day, "currency": "EUR", "impact": "high", "event": "ECB"},
                    {"ts": start + 50 * day, "currency": "EUR", "impact": 1, "event": ""},
                ],
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    status = external_artifact_status(
        tmp_path,
        _news_contract("news.json", digest, start, end),
    )
    assert not status["ok"]
    assert status["invalid_rows"] == 4
    assert status["duplicate_rows"] == 1
    assert "news_invalid_timestamp" in status["reasons"]
    assert "news_invalid_currency" in status["reasons"]
    assert "news_invalid_impact" in status["reasons"]
    assert "news_empty_event" in status["reasons"]
    assert "news_duplicate_events" in status["reasons"]


def test_news_rejects_non_object_rows_even_when_valid_row_count_passes(tmp_path) -> None:
    day = 86400
    start = 1_700_000_000
    end = start + 60 * day
    events = [
        {"ts": start + offset * day, "currency": currency, "impact": 2, "event": event}
        for currency, offsets in (("USD", (5, 30, 55)), ("EUR", (10, 35, 50)))
        for offset, event in zip(offsets, ("CPI", "RATE", "JOBS"))
    ]
    events.append("not-an-event-object")
    path = tmp_path / "news.json"
    path.write_text(
        json.dumps(
            {
                "window_start_ts": start,
                "window_end_ts_exclusive": end,
                "events": events,
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    status = external_artifact_status(
        tmp_path,
        _news_contract("news.json", digest, start, end),
    )
    assert not status["ok"]
    assert status["invalid_rows"] == 1
    assert "news_non_object_rows" in status["reasons"]


def test_pinned_oanda_costs_require_unique_typed_symbol_session_rows(tmp_path) -> None:
    path = tmp_path / "costs.json"
    path.write_text(
        json.dumps(
            {
                "broker": "OANDA",
                "account_type": "spread_only",
                "rows": [
                    {
                        "symbol": "EURUSD",
                        "session": "london",
                        "spread_bps_p50": 0.8,
                        "spread_bps_p95": 1.4,
                        "commission_bps_per_side": 0.0,
                        "financing_bps_per_day": 0.04,
                        "observations": 25,
                    },
                    {
                        "symbol": "USDJPY",
                        "session": "newyork",
                        "spread_bps_p50": 0.9,
                        "spread_bps_p95": 1.6,
                        "commission_bps_per_side": 0.0,
                        "financing_bps_per_day": 0.05,
                        "observations": 30,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    status = external_artifact_status(tmp_path, _cost_contract("costs.json", digest))
    assert status["ok"]
    assert status["coverage_details"]["missing_symbol_sessions"] == []


def test_oanda_costs_reject_duplicates_bad_numbers_and_missing_pairs(tmp_path) -> None:
    path = tmp_path / "costs.json"
    path.write_text(
        json.dumps(
            {
                "broker": "OANDA",
                "account_type": "core_commission",
                "rows": [
                    {
                        "symbol": "EURUSD",
                        "session": "london",
                        "spread_bps_p50": 1.5,
                        "spread_bps_p95": 1.0,
                        "commission_bps_per_side": 0.0,
                        "financing_bps_per_day": 0.04,
                        "observations": 10,
                    },
                    {
                        "symbol": "EURUSD",
                        "session": "london",
                        "spread_bps_p50": 0.8,
                        "spread_bps_p95": 1.4,
                        "commission_bps_per_side": 0.0,
                        "financing_bps_per_day": 0.04,
                        "observations": 25,
                    },
                    {
                        "symbol": "USDJPY",
                        "session": "newyork",
                        "spread_bps_p50": 0.9,
                        "spread_bps_p95": 1.6,
                        "commission_bps_per_side": "0.1",
                        "financing_bps_per_day": -0.05,
                        "observations": 30,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    contract = _cost_contract("costs.json", digest)
    contract["min_rows"] = 3
    contract["required_symbol_sessions"].append(
        {"symbol": "GBPUSD", "session": "london_ny_overlap"}
    )
    status = external_artifact_status(tmp_path, contract)
    assert not status["ok"]
    assert status["duplicate_rows"] == 1
    assert "cost_payload_account_type_mismatch" in status["reasons"]
    assert "cost_spread_p50_exceeds_p95" in status["reasons"]
    assert "cost_observations_below_minimum" in status["reasons"]
    assert "cost_invalid_numeric_value" in status["reasons"]
    assert "cost_duplicate_symbol_session_rows" in status["reasons"]
    assert "cost_required_symbol_session_missing" in status["reasons"]


def test_oanda_cost_contract_fails_closed_until_account_and_pairs_are_confirmed(tmp_path) -> None:
    status = external_artifact_status(
        tmp_path,
        {
            "path": "costs.json",
            "sha256": "",
            "required": True,
            "broker": "OANDA",
            "account_type": "target_account_unconfirmed",
            "collection_key": "rows",
        },
    )
    assert not status["ok"]
    assert "cost_contract_account_type_unconfirmed" in status["reasons"]
    assert "cost_contract_missing_required_symbol_sessions" in status["reasons"]


def test_definition_gate_reports_old_contract_before_source_hash_gate() -> None:
    blockers = external_input_contract_blockers(
        {
            "historical_news": {
                "collection_key": "events",
                "required_window_start_ts": 1_720_389_600,
                "required_window_end_ts_exclusive": 1_783_317_600,
            },
            "broker_cost_calibration": {
                "broker": "OANDA",
                "account_type": "target_account_unconfirmed",
                "collection_key": "rows",
            },
        }
    )
    assert blockers == {
        "historical_news": [
            "news_contract_missing_required_currencies",
            "news_contract_missing_min_events_per_currency",
            "news_contract_missing_max_event_gap_days_per_currency",
        ],
        "broker_cost_calibration": [
            "cost_contract_account_type_unconfirmed",
            "cost_contract_missing_required_symbol_sessions",
        ],
    }


def test_definition_gate_accepts_complete_external_contracts() -> None:
    assert external_input_contract_blockers(
        {
            "historical_news": {
                "collection_key": "events",
                "required_window_start_ts": 1_720_389_600,
                "required_window_end_ts_exclusive": 1_783_317_600,
                "required_currencies": ["USD", "EUR"],
                "min_events_per_currency": 20,
                "max_event_gap_days_per_currency": 45,
            },
            "broker_cost_calibration": {
                "broker": "OANDA",
                "account_type": "spread_only",
                "collection_key": "rows",
                "required_symbol_sessions": [
                    {"symbol": "EURUSD", "session": "london"}
                ],
            },
        }
    ) == {}
