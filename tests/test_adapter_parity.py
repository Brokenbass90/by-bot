from __future__ import annotations

import copy
from decimal import Decimal

from bot.live_native_decision_contract import (
    ActualFill,
    FillRebasePolicy,
    LiveNativeDecisionPlan,
)
from research_lab.adapter_parity import compare_ledgers
from research_lab.live_native_adapter_emitters import (
    AdapterParityContext,
    emit_research_adapter_row,
)


BAR_TS = 1_800_000_000_000


def _row(**updates):
    plan = LiveNativeDecisionPlan(
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
    fill = ActualFill(
        decision_id=plan.decision_id,
        order_id="order-a",
        fill_id="fill-a",
        lifecycle="finalized",
        fill_ts_ms=BAR_TS + 60_000,
        finalized_ts_ms=BAR_TS + 61_000,
        fill_price=Decimal("100"),
        cumulative_filled_qty=Decimal("1"),
        leaves_qty=Decimal("0"),
    )
    policy = FillRebasePolicy(
        spec_id=plan.spec_id,
        profile_hash=plan.profile_hash,
        tick_size=Decimal("0.01"),
        max_adverse_risk_expansion=Decimal("0.20"),
        max_fill_age_ms=300_000,
        max_finalize_delay_ms=60_000,
    )
    context = AdapterParityContext(
        cooldown_state="ready",
        cooldown_until_ts_ms=None,
        regime_value="flat_down",
        regime_bar_ts_ms=BAR_TS,
        outcome="tp1_then_stop",
        net_r=Decimal("0.21"),
        exit_ts_ms=BAR_TS + 3_600_000,
        cost_contract_hash="4" * 64,
    )
    row = emit_research_adapter_row(plan, fill, policy, context)
    row.update(updates)
    return row


def _ledger(row):
    return {(row["symbol"], row["bar_ts"], row["side"]): row}


def test_identical_ledgers_pass():
    row = _row()
    report = compare_ledgers(_ledger(row), _ledger(copy.deepcopy(row)))
    assert report["decision"] == "PASS"
    assert report["failures"] == []


def test_price_within_one_tick_passes_comparator_tolerance():
    research = _row()
    live = copy.deepcopy(research)
    live["sl"] = "110.01"
    assert compare_ledgers(_ledger(research), _ledger(live))["decision"] == "PASS"


def test_geometry_above_one_tick_fails_closed():
    research = _row()
    live = copy.deepcopy(research)
    live["sl"] = "110.011"
    report = compare_ledgers(_ledger(research), _ledger(live))
    assert report["decision"] == "FAIL_CLOSED"
    assert "contract_field_mismatch" in report["failures"]


def test_receipt_regime_or_outcome_mismatch_fails_closed():
    research = _row()
    live = copy.deepcopy(research)
    live["execution_fingerprint"] = "f" * 64
    live["regime_value"] = "flat_up"
    live["net_r"] = "0.19"
    report = compare_ledgers(_ledger(research), _ledger(live))
    assert report["decision"] == "FAIL_CLOSED"
    fields = {item["field"] for item in report["mismatches"]}
    assert {"execution_fingerprint", "regime_value", "net_r"}.issubset(fields)


def test_unmatched_row_fails_closed():
    research = _row()
    live = copy.deepcopy(research)
    live["bar_ts"] += 3_600_000
    report = compare_ledgers(_ledger(research), _ledger(live))
    assert report["decision"] == "FAIL_CLOSED"
    assert "unmatched_evaluation_rows" in report["failures"]
