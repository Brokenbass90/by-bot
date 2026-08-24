from __future__ import annotations

import copy
import json
from decimal import Decimal

import pytest

from bot.live_native_decision_contract import (
    ActualFill,
    ContractViolation,
    FillRebasePolicy,
    LiveNativeDecisionPlan,
    RebaseReceipt,
)
from research_lab.adapter_parity import (
    LedgerError,
    compare_ledgers,
    read_jsonl,
    validate_normalized_row,
)
from research_lab.live_native_adapter_emitters import (
    AdapterParityContext,
    LIVE_NATIVE_ADAPTER_EMITTERS_ENABLED_BY_DEFAULT,
    emit_live_adapter_row,
    emit_research_adapter_row,
    normalized_row_jsonl_bytes,
)


BAR_TS = 1_800_000_000_000


def _plan(sleeve: str) -> LiveNativeDecisionPlan:
    if sleeve == "ATT1":
        return LiveNativeDecisionPlan(
            spec_id="att1-live-native-v2",
            sleeve_id="ATT1",
            symbol="BTCUSDT",
            side="short",
            closed_h1_ts_ms=BAR_TS,
            planned_entry=Decimal("100"),
            frozen_sl=Decimal("110"),
            planned_tps=(Decimal("88"), Decimal("75")),
            tp_fractions=(Decimal("0.55"), Decimal("0.45")),
            residual_fraction=Decimal("0"),
            time_stop_hours=336,
            config_hash="1" * 64,
            source_hash="2" * 64,
            data_hash="3" * 64,
        )
    return LiveNativeDecisionPlan(
        spec_id="sbr1-live-native-v2",
        sleeve_id="SBR1",
        symbol="ETHUSDT",
        side="long",
        closed_h1_ts_ms=BAR_TS,
        planned_entry=Decimal("100"),
        frozen_sl=Decimal("90"),
        planned_tps=(Decimal("111"), Decimal("126")),
        tp_fractions=(Decimal("0.50"), Decimal("0.30")),
        residual_fraction=Decimal("0.20"),
        time_stop_hours=168,
        config_hash="5" * 64,
        source_hash="6" * 64,
        data_hash="7" * 64,
    )


def _fill(
    plan: LiveNativeDecisionPlan,
    *,
    suffix: str = "a",
    price: str = "100",
    fill_age_ms: int = 75_000,
    finalization_delay_ms: int = 2_000,
) -> ActualFill:
    return ActualFill(
        decision_id=plan.decision_id,
        order_id=f"order-{plan.sleeve_id.lower()}-{suffix}",
        fill_id=f"fill-{plan.sleeve_id.lower()}-{suffix}",
        lifecycle="finalized",
        fill_ts_ms=BAR_TS + fill_age_ms,
        finalized_ts_ms=BAR_TS + fill_age_ms + finalization_delay_ms,
        fill_price=Decimal(price),
        cumulative_filled_qty=Decimal("1.25"),
        leaves_qty=Decimal("0"),
    )


def _policy(plan: LiveNativeDecisionPlan) -> FillRebasePolicy:
    return FillRebasePolicy(
        spec_id=plan.spec_id,
        profile_hash=plan.profile_hash,
        tick_size=Decimal("0.10"),
        max_adverse_risk_expansion=Decimal("0.20"),
        max_fill_age_ms=300_000,
        max_finalize_delay_ms=60_000,
    )


def _context(sleeve: str, **updates: object) -> AdapterParityContext:
    values: dict[str, object] = {
        "cooldown_state": "ready",
        "cooldown_until_ts_ms": None,
        "regime_value": "flat_down" if sleeve == "ATT1" else "flat_up",
        "regime_bar_ts_ms": BAR_TS,
        "outcome": "not_scored",
        "net_r": Decimal("0"),
        "exit_ts_ms": BAR_TS + 3_600_000,
        "cost_contract_hash": "8" * 64,
    }
    values.update(updates)
    return AdapterParityContext(**values)  # type: ignore[arg-type]


def _keyed(rows: list[dict[str, object]]):
    return {
        (str(row["symbol"]), int(row["bar_ts"]), str(row["side"])): row
        for row in rows
    }


@pytest.mark.parametrize("sleeve", ["ATT1", "SBR1"])
def test_research_and_live_boundaries_emit_field_and_byte_equal_rows(sleeve: str) -> None:
    plan = _plan(sleeve)
    fill = _fill(plan)
    policy = _policy(plan)
    context = _context(sleeve)
    research = emit_research_adapter_row(plan, fill, policy, context)
    persisted = RebaseReceipt.from_dict(research["rebase_receipt"])  # type: ignore[arg-type]
    live = emit_live_adapter_row(
        plan,
        fill,
        policy,
        context,
        persisted_receipt=persisted,
    )

    assert research == live
    assert normalized_row_jsonl_bytes(research) == normalized_row_jsonl_bytes(live)
    assert research["release_or_promotion_authority"] is False
    assert research["adapter_emitters_default_off"] is True
    assert research["runner_fraction"] == ("0" if sleeve == "ATT1" else "0.2")
    assert research["time_stop"]["hours"] == (336 if sleeve == "ATT1" else 168)  # type: ignore[index]


def test_end_to_end_two_sleeve_jsonl_fixture_passes_comparator(tmp_path) -> None:
    research_rows: list[dict[str, object]] = []
    live_rows: list[dict[str, object]] = []
    for sleeve in ("ATT1", "SBR1"):
        plan = _plan(sleeve)
        fill = _fill(plan)
        policy = _policy(plan)
        context = _context(sleeve)
        research = emit_research_adapter_row(plan, fill, policy, context)
        live = emit_live_adapter_row(
            plan,
            fill,
            policy,
            context,
            persisted_receipt=research["rebase_receipt"],  # type: ignore[arg-type]
        )
        research_rows.append(research)
        live_rows.append(live)

    research_path = tmp_path / "research.jsonl"
    live_path = tmp_path / "live.jsonl"
    research_path.write_bytes(b"".join(normalized_row_jsonl_bytes(row) for row in research_rows))
    live_path.write_bytes(b"".join(normalized_row_jsonl_bytes(row) for row in live_rows))
    report = compare_ledgers(read_jsonl(research_path), read_jsonl(live_path))

    assert research_path.read_bytes() == live_path.read_bytes()
    assert report["decision"] == "PASS"
    assert report["matched_rows"] == 2
    assert report["release_or_promotion_authority"] is False


def test_independently_emitted_context_mismatch_fails_closed() -> None:
    plan = _plan("ATT1")
    fill = _fill(plan)
    policy = _policy(plan)
    research = emit_research_adapter_row(plan, fill, policy, _context("ATT1"))
    live = emit_live_adapter_row(
        plan,
        fill,
        policy,
        _context(
            "ATT1",
            outcome="time_stop",
            net_r=Decimal("-0.25"),
            cost_contract_hash="9" * 64,
        ),
    )
    report = compare_ledgers(_keyed([research]), _keyed([live]))

    assert report["decision"] == "FAIL_CLOSED"
    assert {item["field"] for item in report["mismatches"]}.issuperset(
        {"outcome", "net_r", "cost_contract_hash"}
    )


@pytest.mark.parametrize(
    ("fill_age_ms", "finalization_delay_ms", "code"),
    [
        (300_001, 1, "fill_too_old"),
        (1, 60_001, "fill_finalization_too_slow"),
    ],
)
def test_emitters_enforce_fill_age_and_finalization_gates(
    fill_age_ms: int, finalization_delay_ms: int, code: str
) -> None:
    plan = _plan("ATT1")
    fill = _fill(
        plan,
        fill_age_ms=fill_age_ms,
        finalization_delay_ms=finalization_delay_ms,
    )
    with pytest.raises(ContractViolation, match=code):
        emit_research_adapter_row(plan, fill, _policy(plan), _context("ATT1"))
    with pytest.raises(ContractViolation, match=code):
        emit_live_adapter_row(plan, fill, _policy(plan), _context("ATT1"))


def test_persisted_receipt_for_a_second_fill_is_a_hard_claim_conflict() -> None:
    plan = _plan("ATT1")
    policy = _policy(plan)
    context = _context("ATT1")
    first = emit_research_adapter_row(plan, _fill(plan, suffix="a"), policy, context)

    with pytest.raises(ContractViolation, match="rebase_claim_conflict"):
        emit_live_adapter_row(
            plan,
            _fill(plan, suffix="b", price="101"),
            policy,
            context,
            persisted_receipt=first["rebase_receipt"],  # type: ignore[arg-type]
        )


def test_context_rejects_future_regime_and_incoherent_cooldown() -> None:
    with pytest.raises(ContractViolation, match="ready_cooldown_has_deadline"):
        _context("ATT1", cooldown_until_ts_ms=BAR_TS + 1)
    with pytest.raises(ContractViolation, match="regime_bar_ts_not_closed_h1"):
        _context("ATT1", regime_bar_ts_ms=BAR_TS + 1)

    plan = _plan("ATT1")
    future_regime = _context("ATT1", regime_bar_ts_ms=BAR_TS + 3_600_000)
    with pytest.raises(ContractViolation, match="regime_bar_after_decision"):
        emit_research_adapter_row(plan, _fill(plan), _policy(plan), future_regime)


def test_reader_rejects_tampered_durable_receipt_and_extra_fields(tmp_path) -> None:
    plan = _plan("SBR1")
    row = emit_research_adapter_row(plan, _fill(plan), _policy(plan), _context("SBR1"))
    tampered = copy.deepcopy(row)
    tampered["rebase_receipt"]["fill_id"] = "tampered"  # type: ignore[index]
    with pytest.raises(LedgerError, match="checksum mismatch"):
        validate_normalized_row(tampered)

    extra = copy.deepcopy(row)
    extra["money_authority"] = True
    path = tmp_path / "extra.jsonl"
    path.write_text(json.dumps(extra) + "\n", encoding="utf-8")
    with pytest.raises(LedgerError, match="unexpected fields"):
        read_jsonl(path)


def test_emitters_remain_explicitly_default_off() -> None:
    assert LIVE_NATIVE_ADAPTER_EMITTERS_ENABLED_BY_DEFAULT is False
