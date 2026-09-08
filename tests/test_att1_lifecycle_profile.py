from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from bot.att1_ets2s_signal_shadow_contract import ATT1_SOURCE_PATHS
from research_lab.att1_lifecycle_profile import (
    ProfileViolation,
    admit_signal,
    build_profile,
    validate_profile,
)


ROOT = Path(__file__).resolve().parents[1]
H1_MS = 3_600_000
BAR_CLOSE_MS = 1_800 * H1_MS
SOURCE_RECEIPT_SHA = "a" * 64
DATA_SHA = "b" * 64
INSTRUMENT_SHA = "c" * 64


def _signal(profile: dict[str, object], **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_id": "att1_lifecycle_signal_v1",
        "symbol": "BTCUSDT",
        "side": "short",
        "stream": "EXECUTION_FORWARD",
        "bar_close_ms": BAR_CLOSE_MS,
        "source_available_ms": BAR_CLOSE_MS + 10,
        "signal_ready_ms": BAR_CLOSE_MS + 20,
        "entry": "100",
        "sl": "110",
        "tps": ["88", "75"],
        "tp_fracs": ["0.55", "0.45"],
        "be_trigger_rr": "0",
        "be_lock_rr": "0.02",
        "trailing_atr_mult": "0",
        "trailing_atr_period": 14,
        "trail_activate_rr": "1",
        "time_stop_bars_5m": 4032,
        "source_sha256": SOURCE_RECEIPT_SHA,
        "data_sha256": DATA_SHA,
        "profile_sha256": profile["profile_sha256"],
    }
    value.update(changes)
    return value


def _instrument(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "symbol": "BTCUSDT",
        "tick_size": "0.01",
        "qty_step": "0.01",
        "min_order_qty": "0.01",
        "min_notional": "1",
        "max_market_qty": "10",
        "observed_ms": BAR_CLOSE_MS + 30,
        "source_sha256": INSTRUMENT_SHA,
    }
    value.update(changes)
    return value


def _state(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "active_decision_id": None,
        "last_admitted_bar_ms": None,
        "last_terminal_ms": None,
    }
    value.update(changes)
    return value


def _profile() -> dict[str, object]:
    return build_profile(ROOT)


def test_build_profile_is_source_bound_default_off_and_validates() -> None:
    profile = _profile()

    assert profile["schema_id"] == "att1_lifecycle_profile_v1"
    assert profile["profile_id"] == "SYNTHETIC_ATT1_LIFECYCLE_V1"
    assert profile["l1_source_aggregate_sha256"] == "a7b8d3f5d69ee3943aae8f4c9489fd1a5f5a84fe3ed89b08707231d647299f15"
    assert profile["resolved_config_sha256"] == "fbe3ad079bdf89a00786a5a9b3c27ffd8be27b7826ae3191d60dbb80ead47a9f"
    assert profile["authority"] == {
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
        "promotion_authority": False,
    }
    assert profile["strategy"]["short_target_tick_rounding"] == "down"
    assert set(profile["source_sha256"]) == set(ATT1_SOURCE_PATHS) | {"bot/live_native_decision_contract.py"}
    validate_profile(profile)


def test_build_profile_detects_pinned_l1_source_drift_before_claiming_binding(tmp_path: Path) -> None:
    isolated = tmp_path / "source"
    for relative in ATT1_SOURCE_PATHS:
        destination = isolated / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    source = isolated / ATT1_SOURCE_PATHS[0]
    source.write_text(source.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")

    with pytest.raises(ProfileViolation, match="pinned_l1_source_drift"):
        build_profile(isolated)


def test_build_profile_isolates_att1_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATT1_TP1_RR", "999")
    monkeypatch.setenv("ATT1_SYMBOL_ALLOWLIST", "EVILUSDT")

    profile = _profile()

    assert profile["strategy"]["tp_rr"] == ["1.2", "2.5"]
    assert os.environ["ATT1_TP1_RR"] == "999"
    assert os.environ["ATT1_SYMBOL_ALLOWLIST"] == "EVILUSDT"


def test_validate_profile_rejects_any_tampering_or_authority_opt_in() -> None:
    profile = _profile()
    altered = json.loads(json.dumps(profile))
    altered["authority"]["orders_allowed"] = True

    with pytest.raises(ProfileViolation, match="profile_authority"):
        validate_profile(altered)

    altered = json.loads(json.dumps(profile))
    altered["profile_sha256"] = "0" * 64
    with pytest.raises(ProfileViolation, match="profile_sha256"):
        validate_profile(altered)

    altered = json.loads(json.dumps(profile))
    altered["authority"]["orders_allowed"] = 0
    unsigned = {key: value for key, value in altered.items() if key != "profile_sha256"}
    altered["profile_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()
    with pytest.raises(ProfileViolation, match="profile_authority"):
        validate_profile(altered)


def test_admit_signal_returns_exact_research_plan_for_causal_short_geometry() -> None:
    profile = _profile()
    result = admit_signal(
        profile,
        _signal(profile),
        _instrument(),
        _state(),
        book="ATT1_RESEARCH",
        submit_ms=BAR_CLOSE_MS + 100,
    )

    assert result["accepted"] is True
    assert result["code"] == "ACCEPTED"
    plan = result["plan"]
    assert set(plan) == {
        "profile_id", "profile_sha256", "book", "symbol", "decision_id", "order_id",
        "bar_close_ms", "signal_ready_ms", "submit_ms", "nominal_entry", "original_stop",
        "requested_qty", "qty_step", "price_tick", "planned_risk_amount",
        "signal_source_sha256", "data_sha256", "instrument_source_sha256",
    }
    assert plan["nominal_entry"] == "100"
    assert plan["original_stop"] == "110"
    assert plan["requested_qty"] == "0.1"
    assert plan["planned_risk_amount"] == "1"
    assert plan["order_id"] == "research-order:" + plan["decision_id"]
    expected_decision = hashlib.sha256(json.dumps({
        "signal_payload_sha256": hashlib.sha256(json.dumps(_signal(profile), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest(),
        "bar_close_ms": BAR_CLOSE_MS,
        "book": "ATT1_RESEARCH",
        "data_sha256": DATA_SHA,
        "instrument_source_sha256": INSTRUMENT_SHA,
        "profile_sha256": profile["profile_sha256"],
        "signal_source_sha256": SOURCE_RECEIPT_SHA,
        "symbol": "BTCUSDT",
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    assert plan["decision_id"] == expected_decision


@pytest.mark.parametrize(
    ("signal_changes", "instrument_changes", "state_changes", "submit_ms", "code"),
    [
        ({"stream": "ALPHA_FORWARD_BACKFILL"}, {}, {}, BAR_CLOSE_MS + 100, "STREAM_NOT_EXECUTION_FORWARD"),
        ({"source_available_ms": BAR_CLOSE_MS - 1}, {}, {}, BAR_CLOSE_MS + 100, "TIMESTAMP_ORDER"),
        ({}, {"observed_ms": BAR_CLOSE_MS - 3_600_001}, {}, BAR_CLOSE_MS + 100, "INSTRUMENT_STALE"),
        ({}, {"observed_ms": BAR_CLOSE_MS + 101}, {}, BAR_CLOSE_MS + 100, "INSTRUMENT_FUTURE"),
        ({}, {}, {"active_decision_id": "pending"}, BAR_CLOSE_MS + 100, "POSITION_ACTIVE"),
        ({}, {}, {"last_admitted_bar_ms": BAR_CLOSE_MS}, BAR_CLOSE_MS + 100, "BAR_DUPLICATE_OR_EARLIER"),
        ({}, {}, {"last_admitted_bar_ms": BAR_CLOSE_MS - 7 * H1_MS}, BAR_CLOSE_MS + 100, "COOLDOWN_ACTIVE"),
        ({}, {}, {"last_terminal_ms": BAR_CLOSE_MS}, BAR_CLOSE_MS + 100, "TERMINAL_BAR_NOT_LATER"),
        ({"symbol": "NOTUSDT"}, {}, {}, BAR_CLOSE_MS + 100, "SYMBOL_MISMATCH"),
        ({"profile_sha256": "d" * 64}, {}, {}, BAR_CLOSE_MS + 100, "PROFILE_HASH_MISMATCH"),
        ({"sl": "99"}, {}, {}, BAR_CLOSE_MS + 100, "INVALID_SHORT_STOP"),
        ({"tps": ["88", "74"]}, {}, {}, BAR_CLOSE_MS + 100, "TARGET_RR_MISMATCH"),
        ({}, {"min_notional": "20"}, {}, BAR_CLOSE_MS + 100, "BELOW_MIN_NOTIONAL"),
        ({}, {"min_order_qty": "0.11"}, {}, BAR_CLOSE_MS + 100, "BELOW_MIN_QTY"),
    ],
)
def test_admission_rejects_noncausal_missing_or_ineligible_evidence(
    signal_changes: dict[str, object],
    instrument_changes: dict[str, object],
    state_changes: dict[str, object],
    submit_ms: int,
    code: str,
) -> None:
    profile = _profile()
    result = admit_signal(
        profile,
        _signal(profile, **signal_changes),
        _instrument(**instrument_changes),
        _state(**state_changes),
        book="ATT1_RESEARCH",
        submit_ms=submit_ms,
    )

    assert result == {"accepted": False, "code": code, "plan": None}


@pytest.mark.parametrize(
    "field,value",
    [
        ("bar_close_ms", True),
        ("entry", "NaN"),
        ("source_sha256", "A" * 64),
        ("tps", ["88"]),
    ],
)
def test_admission_raises_for_malformed_signal_fields(field: str, value: object) -> None:
    profile = _profile()
    with pytest.raises(ProfileViolation):
        admit_signal(
            profile,
            _signal(profile, **{field: value}),
            _instrument(),
            _state(),
            book="ATT1_RESEARCH",
            submit_ms=BAR_CLOSE_MS + 100,
        )


@pytest.mark.parametrize("entry", ["9" * 129, "1." + "9" * 65])
def test_admission_rejects_oversized_decimal_text_before_fraction_parsing(entry: str) -> None:
    profile = _profile()
    with pytest.raises(ProfileViolation, match="invalid_decimal:entry"):
        admit_signal(
            profile,
            _signal(profile, entry=entry),
            _instrument(),
            _state(),
            book="ATT1_RESEARCH",
            submit_ms=BAR_CLOSE_MS + 100,
        )


def test_admission_rounds_short_stop_up_and_refuses_dust_quantity() -> None:
    profile = _profile()
    rounded = admit_signal(
        profile,
        _signal(profile, sl="110.001", tps=["87.9988", "74.9975"]),
        _instrument(),
        _state(),
        book="ATT1_RESEARCH",
        submit_ms=BAR_CLOSE_MS + 100,
    )
    assert rounded["accepted"] is True
    assert rounded["plan"]["original_stop"] == "110.01"
    assert rounded["plan"]["requested_qty"] == "0.09"

    dust = admit_signal(
        profile,
        _signal(profile, sl="110.001", tps=["87.9988", "74.9975"]),
        _instrument(qty_step="1", min_order_qty="0.01"),
        _state(),
        book="ATT1_RESEARCH",
        submit_ms=BAR_CLOSE_MS + 100,
    )
    assert dust == {"accepted": False, "code": "BELOW_MIN_QTY", "plan": None}


def test_admission_requires_raw_short_geometry_and_rebased_target_ladder() -> None:
    profile = _profile()
    raw_stop = admit_signal(
        profile,
        _signal(profile, sl="99", tps=["101.2", "102.5"]),
        _instrument(),
        _state(),
        book="ATT1_RESEARCH",
        submit_ms=BAR_CLOSE_MS + 100,
    )
    assert raw_stop == {"accepted": False, "code": "INVALID_SHORT_STOP", "plan": None}

    rebased = admit_signal(
        profile,
        _signal(profile),
        _instrument(tick_size="100"),
        _state(),
        book="ATT1_RESEARCH",
        submit_ms=BAR_CLOSE_MS + 100,
    )
    assert rebased == {"accepted": False, "code": "REBASED_TARGET_INVALID", "plan": None}


def test_admission_state_uses_bar_close_and_accepts_exact_native_eight_hour_cooldown() -> None:
    profile = _profile()
    accepted = admit_signal(
        profile,
        _signal(profile),
        _instrument(),
        _state(last_admitted_bar_ms=BAR_CLOSE_MS - 8 * H1_MS),
        book="ATT1_RESEARCH",
        submit_ms=BAR_CLOSE_MS + 100,
    )
    assert accepted["accepted"] is True

    early = admit_signal(
        profile,
        _signal(profile),
        _instrument(),
        _state(last_admitted_bar_ms=BAR_CLOSE_MS - 8 * H1_MS + 1),
        book="ATT1_RESEARCH",
        submit_ms=BAR_CLOSE_MS + 100,
    )
    assert early == {"accepted": False, "code": "COOLDOWN_ACTIVE", "plan": None}


def test_signal_computation_time_is_not_confused_with_post_submit_quote_age():
    profile = _profile()
    result = admit_signal(profile, _signal(profile, source_available_ms=BAR_CLOSE_MS+1, signal_ready_ms=BAR_CLOSE_MS+2999), _instrument(), _state(), book="ATT1_RESEARCH", submit_ms=BAR_CLOSE_MS+3000)
    assert result["accepted"] is True
    # Fresh executable quote timestamps are checked separately by coordinator.


def test_decision_identity_binds_full_geometry_even_if_external_source_claim_is_reused():
    profile = _profile()
    a = admit_signal(profile, _signal(profile), _instrument(), _state(), book='B', submit_ms=BAR_CLOSE_MS+100)
    b = admit_signal(profile, _signal(profile, sl='111', tps=['86.8', '72.5']), _instrument(), _state(), book='B', submit_ms=BAR_CLOSE_MS+100)
    assert a['accepted'] and b['accepted']
    assert a['plan']['decision_id'] != b['plan']['decision_id']
