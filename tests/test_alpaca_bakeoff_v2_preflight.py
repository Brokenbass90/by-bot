from __future__ import annotations

import json
from copy import deepcopy

import pytest

from backtest.alpaca_bakeoff_v2_contract import (
    PAIRWISE_CONTRASTS,
    BakeoffContractError,
    expected_arms,
    spy200_gate,
    validate_pairwise_contrasts,
)
from scripts.preflight_alpaca_bakeoff_v2 import (
    DEFAULT_CONFIG,
    BakeoffPreflightError,
    build_receipt,
    validate_config,
)


def _config() -> dict:
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))


def test_pairwise_contract_is_one_variable_at_a_time() -> None:
    arms = expected_arms()
    validate_pairwise_contrasts(arms, PAIRWISE_CONTRASTS)

    broken = deepcopy(arms)
    broken[1]["execution"]["target_gross_exposure"] = 1.0
    with pytest.raises(BakeoffContractError, match="shared mechanics"):
        validate_pairwise_contrasts(broken, PAIRWISE_CONTRASTS)


def test_common_spy_gate_is_causal_and_fails_closed() -> None:
    assert spy200_gate([100.0] * 199) is False
    assert spy200_gate([100.0] * 199 + [101.0]) is True
    assert spy200_gate([100.0] * 199 + [99.0]) is False
    assert spy200_gate([100.0] * 199 + [float("nan")]) is False


def test_preflight_freezes_future_window_but_stays_blocked_on_inputs() -> None:
    cfg = _config()
    validate_config(cfg)
    receipt = build_receipt(cfg)

    assert receipt["permission"] == "BLOCKED_FAIL_CLOSED"
    assert receipt["performance_computed"] is False
    assert receipt["outcome_files_opened"] is False
    assert receipt["broker_or_network_calls"] is False
    assert receipt["live_writes"] is False
    assert receipt["promotion_authorized"] is False
    assert all(row["ok"] for row in receipt["sources"])
    assert receipt["untouched_forward_manifest"]["ok"] is True
    assert receipt["untouched_forward_manifest"]["minimum_complete_monthly_entry_cycles"] == 3
    assert receipt["safe_hold"]["ok"] is True
    assert receipt["safe_hold"]["forced_liquidation_required_by_research"] is False
    assert receipt["safe_hold"]["safe_hold_changed"] is False
    blocked_inputs = [row for row in receipt["required_inputs"] if not row["ok"]]
    assert len(blocked_inputs) == 5
    assert all(row["reasons"] == ["artifact_unpinned"] for row in blocked_inputs)


def test_preflight_cannot_erase_safe_hold_or_legacy_gaps() -> None:
    cfg = _config()
    cfg["safe_hold_must_remain"] = False
    with pytest.raises(BakeoffPreflightError, match="safe_hold_must_remain"):
        validate_config(cfg)

    cfg = _config()
    cfg["known_legacy_parity_gaps"] = []
    with pytest.raises(BakeoffPreflightError, match="cannot be erased"):
        validate_config(cfg)


def test_preflight_detects_pinned_source_drift_without_opening_outcomes() -> None:
    cfg = _config()
    cfg["sources"]["adaptive_selector"]["sha256"] = "0" * 64
    receipt = build_receipt(cfg)
    row = next(item for item in receipt["sources"] if item["name"] == "adaptive_selector")

    assert row["ok"] is False
    assert "source:adaptive_selector" in receipt["blockers"]
    assert receipt["performance_computed"] is False
    assert receipt["outcome_files_opened"] is False

