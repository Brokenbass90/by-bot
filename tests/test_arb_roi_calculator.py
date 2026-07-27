from __future__ import annotations

from scripts.arb_roi_calculator import (
    COHORT_EXPLICIT_VALIDATION,
    build_report,
)


def _closed(
    result: float,
    age_hours: float = 24.0,
    *,
    explicit_validation: bool = False,
) -> dict:
    cycle = {
        "model_version": "settlement_execution_v2",
        "final_shadow_pct_total_capital": result,
        "last_update": {"age_hours": age_hours},
    }
    if explicit_validation:
        cycle["last_update"].update(
            {
                "current_observed": True,
                "current_validated": False,
            }
        )
    return cycle


def test_refuses_projection_without_closed_cycles() -> None:
    state = {
        "model_version": "settlement_execution_v2",
        "settings": {"max_open": 5, "notional_usd_per_leg": 20},
        "open": [{"opened_at_epoch": 1000.0, "hold_hours": 24.0}],
        "closed": [],
    }

    report = build_report(state, capitals=[1000], min_closed_cycles=3)

    assert report["status"] == "insufficient_closed_cycles"
    assert report["projection"] is None
    assert report["sample"]["closed_cycles"] == 0
    assert report["sample"]["next_expected_close_utc"] is not None


def test_ignores_legacy_and_incomplete_cycles() -> None:
    state = {
        "model_version": "settlement_execution_v2",
        "settings": {"max_open": 2, "notional_usd_per_leg": 20},
        "open": [],
        "closed": [
            _closed(0.2),
            {"model_version": "legacy_v1", "final_shadow_pct_total_capital": 99},
            {"model_version": "settlement_execution_v2"},
        ],
    }

    report = build_report(state, capitals=[100], min_closed_cycles=2)

    assert report["status"] == "insufficient_closed_cycles"
    assert report["sample"]["closed_cycles"] == 1


def test_projects_only_from_observed_p25_closed_cycles() -> None:
    state = {
        "model_version": "settlement_execution_v2",
        "settings": {"max_open": 2, "notional_usd_per_leg": 100},
        "open": [],
        "closed": [_closed(value) for value in [0.1, 0.2, 0.3, 0.4]],
    }

    report = build_report(state, capitals=[200, 1000], min_closed_cycles=4)

    assert report["status"] == "projection_available"
    assert report["sample"]["win_rate"] == 1.0
    assert report["projection"]["method"] == "observed_closed_cycles_p25"
    assert report["projection"]["planning_cycle_return_pct_total_capital"] == 0.175
    assert report["projection"]["monthly_return_pct_deployed_capital"] == 5.25
    assert report["projection"]["capacity_usd"] == 400.0
    assert report["projection"]["scenarios"][0]["capital_deployed_usd"] == 200.0
    assert report["projection"]["scenarios"][1]["capital_deployed_usd"] == 400.0


def test_explicit_validation_cohort_excludes_pre_fix_cycles() -> None:
    state = {
        "model_version": "settlement_execution_v2",
        "settings": {"max_open": 2, "notional_usd_per_leg": 100},
        "open": [],
        "closed": [
            _closed(99.0),
            _closed(0.1, explicit_validation=True),
            _closed(0.2, explicit_validation=True),
        ],
    }

    report = build_report(
        state,
        capitals=[200],
        min_closed_cycles=3,
        cohort=COHORT_EXPLICIT_VALIDATION,
    )

    assert report["status"] == "insufficient_closed_cycles"
    assert report["sample"]["closed_cycles"] == 2
    assert report["sample"]["excluded_current_model_cycles"] == 1


def test_positive_distribution_is_required_after_count_gate() -> None:
    state = {
        "model_version": "settlement_execution_v2",
        "settings": {"max_open": 2, "notional_usd_per_leg": 100},
        "open": [],
        "closed": [
            _closed(-0.4, explicit_validation=True),
            _closed(-0.2, explicit_validation=True),
            _closed(0.1, explicit_validation=True),
            _closed(0.2, explicit_validation=True),
        ],
    }

    report = build_report(
        state,
        capitals=[200],
        min_closed_cycles=4,
        cohort=COHORT_EXPLICIT_VALIDATION,
    )

    assert report["status"] == "non_positive_executable_distribution"
    assert report["projection"] is None
    assert "p25=" in report["reason"]
