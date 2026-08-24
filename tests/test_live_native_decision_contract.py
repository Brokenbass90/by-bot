from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from bot.live_native_decision_contract import (
    ATT1_FROZEN_PROFILE,
    ActualFill,
    ContractViolation,
    FillRebasePolicy,
    H1_MS,
    LIVE_NATIVE_PARITY_ENABLED_BY_DEFAULT,
    LiveNativeDecisionPlan,
    RebaseReceipt,
    RebasedExecutionPlan,
    SBR1_FROZEN_PROFILE,
    apply_exchange_stop_filter,
    decision_identity,
    nominal_rrs,
    rebase_targets_once,
    round_price_to_tick,
    time_stop_deadline_ms,
    validate_fill_before_rebase,
    validate_residual_fraction,
)


CLOSED_H1_TS_MS = 1_800_000_000_000
CONFIG_HASH = "1" * 64
SOURCE_HASH = "2" * 64
DATA_HASH = "3" * 64


def _att1_plan(**updates: object) -> LiveNativeDecisionPlan:
    values: dict[str, object] = {
        "spec_id": "att1-live-native-v2",
        "sleeve_id": "ATT1",
        "symbol": "BTCUSDT",
        "side": "short",
        "closed_h1_ts_ms": CLOSED_H1_TS_MS,
        "planned_entry": Decimal("100"),
        "frozen_sl": Decimal("110"),
        "planned_tps": (Decimal("88"), Decimal("75")),
        "tp_fractions": (Decimal("0.55"), Decimal("0.45")),
        "residual_fraction": Decimal("0"),
        "time_stop_hours": 336,
        "config_hash": CONFIG_HASH,
        "source_hash": SOURCE_HASH,
        "data_hash": DATA_HASH,
    }
    values.update(updates)
    return LiveNativeDecisionPlan(**values)  # type: ignore[arg-type]


def _sbr1_plan(**updates: object) -> LiveNativeDecisionPlan:
    values: dict[str, object] = {
        "spec_id": "sbr1-live-native-v2",
        "sleeve_id": "SBR1",
        "symbol": "ETHUSDT",
        "side": "long",
        "closed_h1_ts_ms": CLOSED_H1_TS_MS,
        "planned_entry": Decimal("100"),
        "frozen_sl": Decimal("90"),
        "planned_tps": (Decimal("111"), Decimal("126")),
        "tp_fractions": (Decimal("0.50"), Decimal("0.30")),
        "residual_fraction": Decimal("0.20"),
        "time_stop_hours": 168,
        "config_hash": CONFIG_HASH,
        "source_hash": SOURCE_HASH,
        "data_hash": DATA_HASH,
    }
    values.update(updates)
    return LiveNativeDecisionPlan(**values)  # type: ignore[arg-type]


def _fill(
    plan: LiveNativeDecisionPlan,
    price: str = "100",
    *,
    suffix: str = "a",
    **updates: object,
) -> ActualFill:
    values: dict[str, object] = {
        "decision_id": plan.decision_id,
        "order_id": f"order-{suffix}",
        "fill_id": f"fill-{suffix}",
        "lifecycle": "finalized",
        "fill_ts_ms": CLOSED_H1_TS_MS + 90_000,
        "finalized_ts_ms": CLOSED_H1_TS_MS + 92_000,
        "fill_price": Decimal(price),
        "cumulative_filled_qty": Decimal("1.25"),
        "leaves_qty": Decimal("0"),
    }
    values.update(updates)
    return ActualFill(**values)  # type: ignore[arg-type]


def _policy(
    plan: LiveNativeDecisionPlan,
    *,
    expansion: str = "0.20",
    tick_size: str = "0.01",
    **updates: object,
) -> FillRebasePolicy:
    values: dict[str, object] = {
        "spec_id": plan.spec_id,
        "profile_hash": plan.profile_hash,
        "tick_size": Decimal(tick_size),
        "max_adverse_risk_expansion": Decimal(expansion),
        "max_fill_age_ms": 300_000,
        "max_finalize_delay_ms": 60_000,
    }
    values.update(updates)
    return FillRebasePolicy(**values)  # type: ignore[arg-type]


def test_default_off_and_all_execution_inputs_are_immutable() -> None:
    plan = _att1_plan()
    fill = _fill(plan)
    rebased = rebase_targets_once(plan, fill, _policy(plan))

    assert LIVE_NATIVE_PARITY_ENABLED_BY_DEFAULT is False
    for instance, field, value in (
        (plan, "planned_entry", Decimal("101")),
        (fill, "fill_price", Decimal("101")),
        (rebased.receipt, "receipt_id", "f" * 64),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, field, value)


def test_frozen_profiles_match_selected_att1_and_sbr1_contracts_exactly() -> None:
    assert ATT1_FROZEN_PROFILE.side == "short"
    assert ATT1_FROZEN_PROFILE.nominal_rrs == (Decimal("1.20"), Decimal("2.50"))
    assert ATT1_FROZEN_PROFILE.tp_fractions == (Decimal("0.55"), Decimal("0.45"))
    assert ATT1_FROZEN_PROFILE.residual_fraction == 0
    assert ATT1_FROZEN_PROFILE.time_stop_hours == 336

    assert SBR1_FROZEN_PROFILE.side == "long"
    assert SBR1_FROZEN_PROFILE.nominal_rrs == (Decimal("1.10"), Decimal("2.60"))
    assert SBR1_FROZEN_PROFILE.tp_fractions == (Decimal("0.50"), Decimal("0.30"))
    assert SBR1_FROZEN_PROFILE.residual_fraction == Decimal("0.20")
    assert SBR1_FROZEN_PROFILE.time_stop_hours == 168
    assert ATT1_FROZEN_PROFILE.profile_hash != SBR1_FROZEN_PROFILE.profile_hash


def test_plans_enforce_exact_profile_side_rr_fractions_and_holding_period() -> None:
    assert nominal_rrs(_att1_plan()) == ATT1_FROZEN_PROFILE.nominal_rrs
    assert nominal_rrs(_sbr1_plan()) == SBR1_FROZEN_PROFILE.nominal_rrs

    with pytest.raises(ContractViolation, match="wrong_strategy_side"):
        _att1_plan(side="long", frozen_sl=90, planned_tps=(112, 125))
    with pytest.raises(ContractViolation, match="wrong_strategy_nominal_rrs"):
        _att1_plan(planned_tps=(Decimal("89"), Decimal("75")))
    with pytest.raises(ContractViolation, match="wrong_strategy_tp_fractions"):
        _att1_plan(tp_fractions=(Decimal("0.50"), Decimal("0.50")))
    with pytest.raises(ContractViolation, match="wrong_strategy_time_stop"):
        _sbr1_plan(time_stop_hours=24)


def test_fraction_validator_does_not_accept_arbitrary_sum_to_one_allocations() -> None:
    validate_residual_fraction(
        sleeve_id="ATT1", tp_fractions=("0.55", "0.45"), residual_fraction="0"
    )
    validate_residual_fraction(
        sleeve_id="SBR1", tp_fractions=("0.50", "0.30"), residual_fraction="0.20"
    )
    with pytest.raises(ContractViolation):
        validate_residual_fraction(
            sleeve_id="ATT1", tp_fractions=("0.60", "0.40"), residual_fraction="0"
        )
    with pytest.raises(ContractViolation):
        validate_residual_fraction(
            sleeve_id="SBR1", tp_fractions=("0.50", "0.50"), residual_fraction="0"
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"closed_h1_ts_ms": float(CLOSED_H1_TS_MS)},
        {"closed_h1_ts_ms": Decimal(str(CLOSED_H1_TS_MS)) + Decimal("0.5")},
        {"time_stop_hours": 336.9},
        {"time_stop_hours": True},
    ],
)
def test_integer_fields_never_silently_truncate(updates: dict[str, object]) -> None:
    with pytest.raises(ContractViolation, match="invalid_integer"):
        _att1_plan(**updates)


def test_hash_fields_are_strict_sha256_values() -> None:
    with pytest.raises(ContractViolation, match="invalid_sha256"):
        _att1_plan(config_hash="config")
    with pytest.raises(ContractViolation, match="invalid_sha256"):
        _att1_plan(source_hash="A" * 64)


def test_decision_fingerprint_is_canonical_and_binds_geometry_and_evidence() -> None:
    base = _att1_plan()
    normalized = _att1_plan(
        sleeve_id="att1",
        symbol="btcusdt",
        side="SHORT",
        planned_entry="100.0",
        frozen_sl="110.00",
        planned_tps=("88.0", "75.000"),
    )
    variants = (
        _att1_plan(spec_id="att1-live-native-v3"),
        _att1_plan(symbol="SOLUSDT"),
        _att1_plan(closed_h1_ts_ms=CLOSED_H1_TS_MS + H1_MS),
        _att1_plan(
            planned_entry=Decimal("101"),
            frozen_sl=Decimal("111"),
            planned_tps=(Decimal("89"), Decimal("76")),
        ),
        _att1_plan(config_hash="4" * 64),
        _att1_plan(source_hash="5" * 64),
        _att1_plan(data_hash="6" * 64),
    )

    assert decision_identity(base) == base.decision_id == normalized.decision_id
    assert all(item.decision_id != base.decision_id for item in variants)
    assert len({item.decision_id for item in variants}) == len(variants)
    assert base.decision_payload()["profile_hash"] == ATT1_FROZEN_PROFILE.profile_hash


def test_actual_fill_must_be_final_complete_and_chronologically_valid() -> None:
    plan = _att1_plan()
    with pytest.raises(ContractViolation, match="fill_not_finalized"):
        _fill(plan, lifecycle="working")
    with pytest.raises(ContractViolation, match="finalized_fill_has_leaves"):
        _fill(plan, leaves_qty=Decimal("0.1"))
    with pytest.raises(ContractViolation, match="nonpositive_filled_qty"):
        _fill(plan, cumulative_filled_qty=Decimal("0"))
    with pytest.raises(ContractViolation, match="finalized_before_fill"):
        _fill(
            plan,
            fill_ts_ms=CLOSED_H1_TS_MS + 90_000,
            finalized_ts_ms=CLOSED_H1_TS_MS + 89_999,
        )
    with pytest.raises(ContractViolation, match="invalid_integer"):
        _fill(plan, fill_ts_ms=float(CLOSED_H1_TS_MS + 90_000))


def test_policy_integer_and_profile_fields_are_strict() -> None:
    plan = _att1_plan()
    with pytest.raises(ContractViolation, match="invalid_integer"):
        _policy(plan, max_fill_age_ms=300_000.5)
    with pytest.raises(ContractViolation, match="invalid_integer"):
        _policy(plan, max_finalize_delay_ms=False)
    with pytest.raises(ContractViolation, match="invalid_sha256"):
        _policy(plan, profile_hash="profile")


@pytest.mark.parametrize(
    ("factory", "fill_price", "expected_code"),
    [
        (_sbr1_plan, "90", "gap_through_stop"),
        (_att1_plan, "110", "gap_through_stop"),
        (_sbr1_plan, "111", "original_tp_already_crossed"),
        (_att1_plan, "88", "original_tp_already_crossed"),
        (_sbr1_plan, "103", "adverse_risk_expansion_exceeded"),
        (_att1_plan, "97", "adverse_risk_expansion_exceeded"),
    ],
)
def test_fill_geometry_rejections_fail_closed(factory, fill_price, expected_code) -> None:
    plan = factory()
    fill = _fill(plan, fill_price)
    policy = _policy(plan)

    assert validate_fill_before_rebase(plan, fill, policy).code == expected_code
    with pytest.raises(ContractViolation, match=expected_code):
        rebase_targets_once(plan, fill, policy)


def test_fill_validation_binds_decision_spec_profile_and_lifecycle_age() -> None:
    plan = _att1_plan()
    wrong_decision = _fill(plan, decision_id="f" * 64)
    before = _fill(
        plan,
        fill_ts_ms=CLOSED_H1_TS_MS - 1,
        finalized_ts_ms=CLOSED_H1_TS_MS,
    )
    too_old = _fill(
        plan,
        fill_ts_ms=CLOSED_H1_TS_MS + 300_001,
        finalized_ts_ms=CLOSED_H1_TS_MS + 300_002,
    )
    too_slow = _fill(
        plan,
        fill_ts_ms=CLOSED_H1_TS_MS + 1,
        finalized_ts_ms=CLOSED_H1_TS_MS + 60_002,
    )

    assert validate_fill_before_rebase(plan, wrong_decision, _policy(plan)).code == "decision_mismatch"
    assert validate_fill_before_rebase(
        plan, _fill(plan), _policy(plan, spec_id="different")
    ).code == "spec_mismatch"
    assert validate_fill_before_rebase(
        plan, _fill(plan), _policy(plan, profile_hash="f" * 64)
    ).code == "profile_mismatch"
    assert validate_fill_before_rebase(plan, before, _policy(plan)).code == "fill_before_closed_h1"
    assert validate_fill_before_rebase(plan, too_old, _policy(plan)).code == "fill_too_old"
    assert validate_fill_before_rebase(plan, too_slow, _policy(plan)).code == "fill_finalization_too_slow"


@pytest.mark.parametrize(
    ("factory", "expected_tps"),
    [
        (_att1_plan, (Decimal("88"), Decimal("75"))),
        (_sbr1_plan, (Decimal("111"), Decimal("126"))),
    ],
)
def test_exact_profiles_rebase_around_final_fill_and_keep_stop_frozen(
    factory, expected_tps
) -> None:
    plan = factory()
    fill = _fill(plan)
    result = rebase_targets_once(plan, fill, _policy(plan))

    assert result.rebase_applied is True
    assert result.rebased_tps == expected_tps
    assert result.nominal_rrs == plan.profile.nominal_rrs
    assert result.execution_entry == fill.fill_price
    assert result.frozen_sl == plan.frozen_sl


def test_short_target_that_rounds_to_zero_is_rejected() -> None:
    plan = _att1_plan(
        planned_entry=Decimal("0.03"),
        frozen_sl=Decimal("0.04"),
        planned_tps=(Decimal("0.018"), Decimal("0.005")),
    )
    fill = _fill(plan, "0.03")
    with pytest.raises(ContractViolation, match="target_nonpositive_after_tick_rounding"):
        rebase_targets_once(plan, fill, _policy(plan, tick_size="0.01"))


def test_receipt_is_deterministic_roundtrippable_and_recovery_safe() -> None:
    plan = _att1_plan()
    fill = _fill(plan)
    policy = _policy(plan)
    first = rebase_targets_once(plan, fill, policy)
    cold_repeat = rebase_targets_once(plan, fill, policy)
    persisted = first.receipt.to_dict()
    recovered = rebase_targets_once(plan, fill, policy, persisted_receipt=persisted)

    assert cold_repeat.receipt == first.receipt == recovered.receipt
    assert RebaseReceipt.from_dict(persisted) == first.receipt
    assert first.receipt.claim_key.endswith(plan.decision_id)
    assert len(first.receipt.receipt_id) == 64


def test_receipt_tampering_and_second_fill_claim_fail_closed() -> None:
    plan = _att1_plan()
    policy = _policy(plan)
    first_fill = _fill(plan, "100", suffix="a")
    first = rebase_targets_once(plan, first_fill, policy)
    tampered = first.receipt.to_dict()
    tampered["fill_id"] = "changed"

    with pytest.raises(ContractViolation, match="rebase_receipt_checksum_mismatch"):
        RebaseReceipt.from_dict(tampered)
    with pytest.raises(ContractViolation, match="rebase_claim_conflict"):
        rebase_targets_once(
            plan,
            _fill(plan, "101", suffix="b"),
            policy,
            persisted_receipt=first.receipt,
        )
    with pytest.raises(ContractViolation, match="rebase_already_applied"):
        rebase_targets_once(first, _fill(plan, "101", suffix="b"), policy)


def test_rebased_execution_plan_rejects_manually_tampered_geometry() -> None:
    plan = _sbr1_plan()
    fill = _fill(plan)
    policy = _policy(plan)
    valid = rebase_targets_once(plan, fill, policy)

    with pytest.raises(ContractViolation, match="rebased_targets_do_not_match_contract"):
        replace(valid, rebased_tps=(Decimal("112"), Decimal("126")))


def test_time_stop_can_only_be_derived_from_an_accepted_rebase() -> None:
    for plan in (_att1_plan(), _sbr1_plan()):
        fill = _fill(plan)
        accepted = rebase_targets_once(plan, fill, _policy(plan))
        assert time_stop_deadline_ms(accepted) == (
            fill.fill_ts_ms + plan.profile.time_stop_hours * H1_MS
        )
        with pytest.raises(ContractViolation, match="time_stop_requires_accepted_rebase"):
            time_stop_deadline_ms(plan)  # type: ignore[arg-type]


def test_directional_tick_rounding_is_decimal_exact() -> None:
    assert round_price_to_tick("100.001", "0.01", direction="up") == Decimal("100.01")
    assert round_price_to_tick("100.001", "0.01", direction="down") == Decimal("100.00")
    assert round_price_to_tick("100.00", "0.01", direction="up") == Decimal("100.00")
    assert round_price_to_tick("0.3000000000000000001", "0.1", direction="up") == Decimal("0.4")


def test_exchange_stop_filter_rounds_outward_and_preserves_nominal_rrs() -> None:
    short = apply_exchange_stop_filter(
        _att1_plan(
            frozen_sl=Decimal("110.001"),
            planned_tps=(Decimal("87.9988"), Decimal("74.9975")),
        ),
        "0.01",
    )
    long = apply_exchange_stop_filter(
        _sbr1_plan(
            frozen_sl=Decimal("89.999"),
            planned_tps=(Decimal("111.0011"), Decimal("126.0026")),
        ),
        "0.01",
    )
    assert short.frozen_sl == Decimal("110.01")
    assert long.frozen_sl == Decimal("89.99")
    assert nominal_rrs(short) == short.profile.nominal_rrs
    assert nominal_rrs(long) == long.profile.nominal_rrs
