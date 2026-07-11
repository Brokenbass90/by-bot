from __future__ import annotations

import json
import hashlib

import pytest

from scripts.run_fx_v3_preflight_20260711 import (
    classify_permission,
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


def test_pinned_artifact_passes_only_with_valid_rows_and_envelope(tmp_path) -> None:
    path = tmp_path / "news.json"
    path.write_text(
        json.dumps(
            {
                "window_start_ts": 90,
                "window_end_ts_exclusive": 210,
                "events": [
                    {"ts": 150, "currency": "USD", "impact": 3, "event": "CPI"}
                ],
            }
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    valid = external_artifact_status(
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
    assert valid["ok"]
    assert valid["rows"] == 1
