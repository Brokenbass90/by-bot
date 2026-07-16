"""Frozen, research-only arm contract for the Alpaca monthly bake-off v2.

This module contains definitions only.  It has no broker, network, credential,
environment, order, P&L, or live-runtime imports.  The successor bake-off uses
it to avoid the old confound where changing the selector also changed the
regime gate, sizing, schedule, or exit model.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


class BakeoffContractError(ValueError):
    """Raised when the frozen comparison stops being an apples-to-apples test."""


COMMON_SCHEDULE = {
    "calendar": "XNYS",
    "signal_time": "completed_last_xnys_session_close_of_calendar_month",
    "entry_time": "next_xnys_session_open",
    "same_close_or_same_bar_entry": False,
    "target_refresh": "calendar_monthly",
}

COMMON_EXECUTION = {
    "completed_bars_only": True,
    "target_gross_exposure": 0.70,
    "base_cost_bps_per_side": 5.0,
    "stress_cost_bps_per_side": 10.0,
    "entry_cost": "adverse_at_next_open",
    "stop_gap_fill": "opening_price_if_open_beyond_stop",
    "target_gap_fill": "frozen_target_no_favorable_gap_credit",
    "same_bar_stop_and_target": "stop_first",
    "daily_mark_to_market": True,
    "daily_drawdown_includes_initial_capital": True,
}

COMMON_EXIT = {
    "implementation": "backtest.alpaca_exact_parity_contract.simulate_position",
    "initial_stop_atr": 2.0,
    "profit_target_atr": 3.2,
    "break_even_trigger_r": 0.8,
    "trail_atr": 1.5,
    "max_hold_sessions": 22,
    "intramonth_portfolio_stop_pct": 0.08,
    "stop_update_timing": "completed_bar_for_next_session",
}

COMMON_SPY200_GATE = {
    "id": "spy_close_ge_trailing_sma200_v1",
    "benchmark": "SPY",
    "lookback_completed_sessions": 200,
    "pass_rule": "signal_close_ge_trailing_sma",
    "insufficient_history": "cash_fail_closed",
    "exposure_on_pass": 1.0,
    "exposure_on_fail": 0.0,
}

GATE_OFF = {
    "id": "gate_disabled_control_v1",
    "exposure": 1.0,
    "purpose": "isolate_regime_gate_effect_only",
}

V38_SUCCESSOR_SELECTOR = {
    "id": "v38_monthly_live_intent_successor_v2",
    "family": "v38",
    "eligible_universe": "point_in_time_membership_only",
    "top_n": 4,
    "momentum_lookback_sessions": 28,
    "minimum_momentum_pct": 5.0,
    "pullback_min_pct": -12.0,
    "pullback_max_pct": -1.5,
    "universe_top_k": 18,
    "universe_score_lookback_sessions": 80,
    "correlation_lookback_sessions": 60,
    "max_pair_correlation": 0.75,
    "correlation_penalty_multiplier": 2.5,
    "correlation_penalty_threshold": 0.5,
    "max_per_cluster": 1,
    "max_per_sector": 2,
    "earnings_blackout_sessions_before": 3,
    "earnings_blackout_sessions_after": 1,
    "weighting": "score_div_sqrt_atr_then_normalize",
    "max_position_share_of_allocated_sleeve": 0.60,
    "parameter_scan": False,
}

ADAPTIVE_SELECTOR = {
    "id": "adaptive_v1_defaults_frozen_v2",
    "family": "adaptive_v1",
    "eligible_universe": "point_in_time_membership_only",
    "mom_fast_sessions": 20,
    "mom_slow_sessions": 60,
    "volatility_sessions": 60,
    "per_name_trend_sma_sessions": 50,
    "minimum_slow_momentum": 0.0,
    "target_daily_volatility": 0.02,
    "max_position_share_of_allocated_sleeve": 0.40,
    "max_per_sector": 2,
    "top_n": 5,
    "max_positions": 4,
    "weighting": "inverse_realized_vol_then_cap_without_upward_renormalization",
    "ai_approver": False,
    "parameter_scan": False,
}

LEGACY_V38_REFERENCE = {
    "id": "v38_legacy_research_reference_20260710",
    "family": "v38_legacy_diagnostic",
    "eligible_universe": "fixed_current_tickers_not_pit",
    "top_n": 4,
    "momentum_lookback_sessions": 28,
    "minimum_momentum_pct": 5.0,
    "pullback_min_pct": -12.0,
    "pullback_max_pct": -1.5,
    "universe_top_k": 14,
    "universe_score_lookback_sessions": 80,
    "correlation_lookback_sessions": 60,
    "max_pair_correlation": 0.75,
    "correlation_penalty_multiplier": 2.5,
    "correlation_penalty_threshold": 0.5,
    "max_per_cluster": 1,
    "max_per_sector": None,
    "earnings_blackout_calendar_days_before": 5,
    "earnings_blackout_calendar_days_after": 2,
    "weighting": "score_div_atr_then_normalized_to_full_investment",
    "target_gross_exposure": 1.0,
    "promotion_eligible": False,
}

LEGACY_NATIVE_GATE = {
    "id": "v38_legacy_breadth_plus_benchmark_reference",
    "universe_breadth_sma_lookback_sessions": 28,
    "minimum_breadth_above_sma_pct": 60.0,
    "minimum_breadth_positive_momentum_pct": 45.0,
    "minimum_average_momentum_pct": 1.5,
    "benchmarks": ["SPY", "QQQ"],
    "benchmark_lookback_sessions": 60,
    "minimum_benchmarks_above_sma": 1,
}

KNOWN_LEGACY_PARITY_GAPS = [
    "legacy_research_fixed_current_universe_not_point_in_time",
    "legacy_research_target_exposure_100pct_vs_live_intent_70pct",
    "legacy_research_universe_top_k_14_vs_live_intent_18",
    "legacy_research_earnings_blackout_5_2_vs_live_intent_3_1",
    "legacy_research_no_sector_cap_vs_live_intent_max_2",
    "legacy_research_weight_score_div_atr_vs_live_score_div_sqrt_atr",
    "legacy_research_monthly_endpoint_drawdown_not_daily_mtm",
]


def expected_arms() -> list[dict[str, Any]]:
    """Return the frozen arms; callers receive an independent copy."""

    rows = [
            {
                "id": "v38_successor_spy200_gated",
                "role": "candidate",
                "selector": V38_SUCCESSOR_SELECTOR,
                "regime_gate": COMMON_SPY200_GATE,
                "schedule": COMMON_SCHEDULE,
                "execution": COMMON_EXECUTION,
                "exit": COMMON_EXIT,
            },
            {
                "id": "v38_successor_ungated_control",
                "role": "gate_ab_control",
                "selector": V38_SUCCESSOR_SELECTOR,
                "regime_gate": GATE_OFF,
                "schedule": COMMON_SCHEDULE,
                "execution": COMMON_EXECUTION,
                "exit": COMMON_EXIT,
            },
            {
                "id": "adaptive_v1_spy200_gated",
                "role": "challenger",
                "selector": ADAPTIVE_SELECTOR,
                "regime_gate": COMMON_SPY200_GATE,
                "schedule": COMMON_SCHEDULE,
                "execution": COMMON_EXECUTION,
                "exit": COMMON_EXIT,
            },
            {
                "id": "adaptive_v1_ungated_control",
                "role": "gate_ab_control",
                "selector": ADAPTIVE_SELECTOR,
                "regime_gate": GATE_OFF,
                "schedule": COMMON_SCHEDULE,
                "execution": COMMON_EXECUTION,
                "exit": COMMON_EXIT,
            },
            {
                "id": "v38_legacy_native_reference",
                "role": "diagnostic_reference_not_winner_eligible",
                "selector": LEGACY_V38_REFERENCE,
                "regime_gate": LEGACY_NATIVE_GATE,
                "schedule": COMMON_SCHEDULE,
                "execution": {**COMMON_EXECUTION, "target_gross_exposure": 1.0},
                "exit": COMMON_EXIT,
            },
        ]
    # Copy each arm independently.  A single deepcopy of the whole list would
    # preserve aliases between the shared constant dictionaries, so mutating a
    # test arm could silently mutate its control as well.
    return [deepcopy(row) for row in rows]


PAIRWISE_CONTRASTS = [
    {
        "id": "v38_gate_effect",
        "left": "v38_successor_spy200_gated",
        "right": "v38_successor_ungated_control",
        "only_allowed_difference": "regime_gate",
    },
    {
        "id": "adaptive_gate_effect",
        "left": "adaptive_v1_spy200_gated",
        "right": "adaptive_v1_ungated_control",
        "only_allowed_difference": "regime_gate",
    },
    {
        "id": "selector_effect_with_spy200_gate",
        "left": "v38_successor_spy200_gated",
        "right": "adaptive_v1_spy200_gated",
        "only_allowed_difference": "selector",
    },
    {
        "id": "selector_effect_without_gate",
        "left": "v38_successor_ungated_control",
        "right": "adaptive_v1_ungated_control",
        "only_allowed_difference": "selector",
    },
]


def validate_pairwise_contrasts(
    arms: Sequence[Mapping[str, Any]],
    contrasts: Sequence[Mapping[str, str]] = PAIRWISE_CONTRASTS,
) -> None:
    """Prove each named A/B comparison changes exactly one component."""

    by_id = {str(row.get("id") or ""): row for row in arms}
    if len(by_id) != len(arms) or "" in by_id:
        raise BakeoffContractError("arm ids must be unique and non-empty")
    for contrast in contrasts:
        left = by_id.get(str(contrast.get("left") or ""))
        right = by_id.get(str(contrast.get("right") or ""))
        allowed = str(contrast.get("only_allowed_difference") or "")
        if left is None or right is None or allowed not in {"selector", "regime_gate"}:
            raise BakeoffContractError("pairwise contrast is incomplete")
        shared_keys = {"schedule", "execution", "exit"}
        if any(left.get(key) != right.get(key) for key in shared_keys):
            raise BakeoffContractError(f"{contrast['id']} changes shared mechanics")
        other = "selector" if allowed == "regime_gate" else "regime_gate"
        if left.get(other) != right.get(other):
            raise BakeoffContractError(f"{contrast['id']} changes {other} as well")
        if left.get(allowed) == right.get(allowed):
            raise BakeoffContractError(f"{contrast['id']} has no {allowed} difference")


def spy200_gate(index_closes: Sequence[float]) -> bool:
    """Causal common gate evaluated only from closes available at signal time."""

    if len(index_closes) < 200:
        return False
    sample = [float(value) for value in index_closes[-200:]]
    if any(value <= 0 or value != value for value in sample):
        return False
    return sample[-1] >= sum(sample) / 200.0
