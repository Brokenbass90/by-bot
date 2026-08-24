from __future__ import annotations

from decimal import Decimal

from bot.live_native_decision_contract import (
    ActualFill,
    FillRebasePolicy,
    LiveNativeDecisionPlan,
)
from research_lab.run_att1_sbr1_actual_adapter_parity import (
    M5_MS,
    MarketData,
    _simulate_outcome,
)


BAR_TS = 1_728_000_000_000  # exact 8-hour UTC funding-grid boundary


def _plan(sleeve: str) -> LiveNativeDecisionPlan:
    is_long = sleeve == "SBR1"
    return LiveNativeDecisionPlan(
        spec_id=f"{sleeve.lower()}-test",
        sleeve_id=sleeve,
        symbol="BTCUSDT",
        side="long" if is_long else "short",
        closed_h1_ts_ms=BAR_TS,
        planned_entry=Decimal("100"),
        frozen_sl=Decimal("90" if is_long else "110"),
        planned_tps=(
            (Decimal("111"), Decimal("126"))
            if is_long
            else (Decimal("88"), Decimal("75"))
        ),
        tp_fractions=(
            (Decimal("0.5"), Decimal("0.3"))
            if is_long
            else (Decimal("0.55"), Decimal("0.45"))
        ),
        residual_fraction=Decimal("0.2" if is_long else "0"),
        time_stop_hours=168 if is_long else 336,
        config_hash="1" * 64,
        source_hash="2" * 64,
        data_hash="3" * 64,
    )


def _fill(plan: LiveNativeDecisionPlan) -> ActualFill:
    return ActualFill(
        decision_id=plan.decision_id,
        order_id="order-test",
        fill_id="fill-test",
        lifecycle="finalized",
        fill_ts_ms=BAR_TS,
        finalized_ts_ms=BAR_TS,
        fill_price=Decimal("100"),
        cumulative_filled_qty=Decimal("1"),
        leaves_qty=Decimal("0"),
    )


def _policy(plan: LiveNativeDecisionPlan) -> FillRebasePolicy:
    return FillRebasePolicy(
        spec_id=plan.spec_id,
        profile_hash=plan.profile_hash,
        tick_size=Decimal("0.1"),
        max_adverse_risk_expansion=Decimal("0.2"),
        max_fill_age_ms=300_000,
        max_finalize_delay_ms=60_000,
    )


def _market(hours: int, overrides: dict[int, tuple[str, str, str, str]] | None = None) -> MarketData:
    rows = []
    overrides = overrides or {}
    for index in range(hours * 12):
        o, h, l, c = overrides.get(index, ("100", "101", "99", "100"))
        rows.append((BAR_TS + index * M5_MS, o, h, l, c, "1"))
    frozen = tuple(rows)
    return MarketData(
        symbol="BTCUSDT",
        m5=frozen,
        h1=(),
        m5_index={int(row[0]): index for index, row in enumerate(frozen)},
        h1_index={},
    )


def test_gap_through_stop_executes_at_adverse_open() -> None:
    plan = _plan("ATT1")
    data = _market(336, {1: ("112", "113", "111", "112")})
    outcome, net_r, exit_ts = _simulate_outcome(
        plan,
        _fill(plan),
        _policy(plan),
        data,
        {
            "fee_bps_per_side": "0",
            "slippage_bps_per_side": "0",
            "adverse_funding_bps_per_8h": "0",
        },
    )
    assert outcome == "gap_stop"
    assert net_r == Decimal("-1.2")
    assert exit_ts == BAR_TS + 2 * M5_MS


def test_stress_funding_is_charged_only_after_entry() -> None:
    plan = _plan("SBR1")
    data = _market(168)
    common = {"fee_bps_per_side": "0", "slippage_bps_per_side": "0"}
    _, base_r, base_exit = _simulate_outcome(
        plan,
        _fill(plan),
        _policy(plan),
        data,
        {**common, "adverse_funding_bps_per_8h": "0"},
    )
    _, stress_r, stress_exit = _simulate_outcome(
        plan,
        _fill(plan),
        _policy(plan),
        data,
        {**common, "adverse_funding_bps_per_8h": "1"},
    )
    assert base_r == 0
    assert stress_r < base_r
    assert stress_exit == base_exit == BAR_TS + 168 * 3_600_000
