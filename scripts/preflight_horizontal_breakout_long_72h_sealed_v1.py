#!/usr/bin/env python3
"""Integrity-only preflight for the one frozen H1 breakout-long successor.

This module is intentionally unable to load OHLCV rows or compute outcomes.
It validates only the preregistration and its small provenance manifests.  A
separate scorer must be written and reviewed after this freeze is committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    ROOT
    / "configs/preregistered/horizontal_breakout_long_72h_sealed_v1_20260715.json"
)
EXPECTED_KIND = "horizontal_breakout_long_72h_sealed_v1_preregistration"
EXPECTED_SYMBOLS = [
    "1000PEPEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "BNBUSDT",
    "BTCUSDT",
    "DOGEUSDT",
    "ETHUSDT",
    "ONDOUSDT",
    "SOLUSDT",
    "SUIUSDT",
    "TAOUSDT",
    "WIFUSDT",
    "XRPUSDT",
]
EXPECTED_PINS = {
    "atlas_preregistration": (
        "configs/preregistered/multicoin_pattern_atlas_v1_20260715.json",
        "9e4b16604d8b97c3c99d1faef47a4c394ab0c9f667913835e8d24468953d0551",
    ),
    "atlas_discovery_receipt": (
        "reports/research/multicoin_pattern_atlas_v1_20260715/receipt.json",
        "acb571eb59a5e85773176d21bce411ebaaab45294f4c168fefa292d484aab739",
    ),
    "uniform_window_manifest": (
        "configs/preregistered/event_long_dev13_uniform_m5_window_v1_20260714.json",
        "16b4f746a982c4e688de1c6766d93fb916173f3f3e636b7230038455d68facfb",
    ),
    "closed_bar_aggregation": (
        "bot/closed_bar_aggregation_v1.py",
        "5ad6b37ee5124b185ae1cefd0b7aed43863d338fed3d3abfcbf2fce96f2d95aa",
    ),
}


class BreakoutLongPreflightError(ValueError):
    """The frozen single-candidate contract is incomplete or changed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_exact_keys(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise BreakoutLongPreflightError(f"{label} schema keys changed")
    return value


def _repo_file(root: Path, raw: object) -> Path:
    text = str(raw or "")
    relative = Path(text)
    if (
        not text
        or relative.is_absolute()
        or "\\" in text
        or any(part in {"", ".", ".."} for part in relative.parts)
        or ".git" in relative.parts
    ):
        raise BreakoutLongPreflightError(f"unsafe repo-relative path: {text!r}")
    cursor = root.resolve()
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise BreakoutLongPreflightError(f"path contains a symlink: {text!r}")
    if not cursor.is_file():
        raise BreakoutLongPreflightError(f"required regular file is missing: {text!r}")
    return cursor


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BreakoutLongPreflightError(f"invalid JSON input {path}: {exc}") from exc


def _validate_provenance(root: Path, config: Mapping[str, Any]) -> None:
    provenance = _require_exact_keys(
        config.get("provenance"),
        {"pins", "selected_discovery_cell"},
        "provenance",
    )
    pins = provenance.get("pins")
    if not isinstance(pins, list) or len(pins) != len(EXPECTED_PINS):
        raise BreakoutLongPreflightError("exactly four provenance pins are required")
    by_role = {
        str(item.get("role")): item for item in pins if isinstance(item, Mapping)
    }
    if set(by_role) != set(EXPECTED_PINS):
        raise BreakoutLongPreflightError("provenance pin roles changed")
    for role, (expected_path, expected_sha) in EXPECTED_PINS.items():
        item = _require_exact_keys(by_role[role], {"role", "path", "sha256"}, f"pin {role}")
        if item.get("path") != expected_path or item.get("sha256") != expected_sha:
            raise BreakoutLongPreflightError(f"frozen provenance pin changed: {role}")
        if sha256_file(_repo_file(root, expected_path)) != expected_sha:
            raise BreakoutLongPreflightError(f"frozen provenance file changed: {role}")

    selected = provenance.get("selected_discovery_cell")
    if selected != {
        "pattern_id": "horizontal_breakout_long",
        "side": "long",
        "horizon_h1": 72,
        "selection_count": 1,
        "other_atlas_cells_rescued": 0,
    }:
        raise BreakoutLongPreflightError("the one selected discovery cell changed")

    receipt = _read_json(_repo_file(root, EXPECTED_PINS["atlas_discovery_receipt"][0]))
    if not isinstance(receipt, Mapping):
        raise BreakoutLongPreflightError("atlas receipt root must be an object")
    if receipt.get("sealed_holdout_scored") is not False:
        raise BreakoutLongPreflightError("atlas receipt no longer proves a sealed holdout")
    summaries = receipt.get("summaries")
    matches = [
        row
        for row in summaries if isinstance(row, Mapping)
        and row.get("pattern_id") == "horizontal_breakout_long"
        and row.get("side") == "long"
        and row.get("horizon_h1") == 72
    ] if isinstance(summaries, list) else []
    if len(matches) != 1:
        raise BreakoutLongPreflightError("selected atlas cell is missing or duplicated")


def _validate_data_contract(root: Path, config: Mapping[str, Any]) -> None:
    data = _require_exact_keys(
        config.get("data_contract"),
        {
            "cohort", "symbols", "source_timeframe", "decision_timeframe",
            "sealed_holdout", "source_hash_verification_before_scoring",
            "preflight_may_open_raw_snapshots", "preflight_may_decode_market_rows",
            "forming_bars_allowed", "provider_mixing_allowed",
        },
        "data_contract",
    )
    if data.get("cohort") != "exact_hash_pinned_dev13_no_additions_or_removals":
        raise BreakoutLongPreflightError("cohort identity changed")
    if data.get("symbols") != EXPECTED_SYMBOLS:
        raise BreakoutLongPreflightError("exact dev13 universe changed")
    if data.get("source_timeframe") != "M5" or data.get("decision_timeframe") != "H1":
        raise BreakoutLongPreflightError("source/decision timeframes changed")
    if any(data.get(key) is not False for key in (
        "preflight_may_open_raw_snapshots", "preflight_may_decode_market_rows",
        "forming_bars_allowed", "provider_mixing_allowed",
    )):
        raise BreakoutLongPreflightError("preflight/data safety flags changed")
    if data.get("source_hash_verification_before_scoring") is not True:
        raise BreakoutLongPreflightError("future scoring must verify immutable source hashes")
    if data.get("sealed_holdout") != {
        "start_ts": 1772805600000,
        "start_utc": "2026-03-06T14:00:00Z",
        "end_ts_exclusive": 1783173600000,
        "end_utc_exclusive": "2026-07-04T14:00:00Z",
        "calendar_days": 120,
        "status": "SEALED_UNDECODED_UNSCORED",
        "performance_access_before_freeze_commit_allowed": False,
        "discovery_prefix_may_be_used_as_20_H1_warmup_only": True,
    }:
        raise BreakoutLongPreflightError("sealed holdout boundaries or access rule changed")

    uniform = _read_json(_repo_file(root, EXPECTED_PINS["uniform_window_manifest"][0]))
    if not isinstance(uniform, Mapping) or uniform.get("symbols") != EXPECTED_SYMBOLS:
        raise BreakoutLongPreflightError("uniform manifest universe differs from dev13")
    window = uniform.get("window")
    if not isinstance(window, Mapping) or int(window.get("end_ts_exclusive", 0)) < 1783173600000:
        raise BreakoutLongPreflightError("uniform window does not cover the sealed end")


def _validate_strategy_contract(config: Mapping[str, Any]) -> None:
    strategy = _require_exact_keys(
        config.get("strategy_contract"),
        {
            "candidate_id", "physical_side", "short_logic_present", "signal",
            "retest", "entry", "exit", "overlap_and_state", "parameter_search",
        },
        "strategy_contract",
    )
    if strategy.get("candidate_id") != "horizontal_breakout_long_72h_v1":
        raise BreakoutLongPreflightError("candidate identity changed")
    if strategy.get("physical_side") != "long" or strategy.get("short_logic_present") is not False:
        raise BreakoutLongPreflightError("physical long-only identity changed")
    if strategy.get("parameter_search") is not False:
        raise BreakoutLongPreflightError("parameter search is forbidden")
    if strategy.get("signal") != {
        "lookback_h1": 20,
        "level": "maximum_high_of_exactly_20_completed_H1_bars_before_signal_bar",
        "signal_bar": "completed_H1_only",
        "condition": "signal_open_at_or_below_frozen_level_and_signal_close_strictly_above_frozen_level",
        "signal_timestamp": "exact_close_of_signal_H1_bar",
        "level_redraw_after_signal_allowed": False,
        "extra_regime_volume_momentum_or_AI_filters_allowed": False,
    }:
        raise BreakoutLongPreflightError("causal breakout signal changed")
    if strategy.get("retest") != {
        "required": False,
        "delayed_or_conditional_entry_allowed": False,
        "post_entry_level_behavior_changes_exit": False,
        "reason": "preserve_the_selected_atlas_next_open_72h_hypothesis_without_post_hoc_repair",
    }:
        raise BreakoutLongPreflightError("retest policy changed")
    if strategy.get("entry") != {
        "time": "next_H1_open_after_completed_signal_bar",
        "price": "actual_next_H1_open_plus_adverse_long_slippage",
        "order_assumption": "taker_market",
        "same_bar_or_signal_close_fill_allowed": False,
    }:
        raise BreakoutLongPreflightError("entry contract changed")
    if strategy.get("exit") != {
        "type": "fixed_time_exit_only",
        "holding_period_h1": 72,
        "price": "close_of_the_72nd_completed_H1_bar_after_entry_minus_adverse_long_slippage",
        "stop_loss": None,
        "take_profit": None,
        "trailing_or_breakeven": None,
        "early_exit_or_reentry": False,
    }:
        raise BreakoutLongPreflightError("fixed 72h exit contract changed")
    if strategy.get("overlap_and_state") != {
        "same_symbol_pattern_cooldown_h1": 168,
        "cooldown_clock": "completed_signal_bar_indices",
        "max_open_positions_per_symbol": 1,
        "cooldown_state_continues_through_folds_and_embargoes": True,
        "duplicate_event_ids_allowed": 0,
    }:
        raise BreakoutLongPreflightError("overlap/state contract changed")


def _validate_execution_and_partitions(config: Mapping[str, Any]) -> None:
    execution = _require_exact_keys(
        config.get("execution_and_cost_contract"),
        {"portfolio", "base_costs", "stress_costs", "funding"},
        "execution_and_cost_contract",
    )
    if execution.get("portfolio") != {
        "starting_equity_usd": 10000.0,
        "fixed_notional_per_trade_usd": 769.23,
        "compounding": False,
        "leverage_allowed": False,
        "max_global_open_positions": 13,
        "max_open_positions_per_symbol": 1,
        "timestamp_occupancy_required": True,
    }:
        raise BreakoutLongPreflightError("portfolio simulation contract changed")
    if execution.get("base_costs") != {
        "fee_bps_per_side": 6.0,
        "slippage_bps_per_side": 2.0,
        "round_trip_non_funding_cost_bps": 16.0,
    }:
        raise BreakoutLongPreflightError("base cost contract changed")
    if execution.get("stress_costs") != {
        "fee_bps_per_side": 10.0,
        "slippage_bps_per_side": 5.0,
        "round_trip_non_funding_cost_bps": 30.0,
    }:
        raise BreakoutLongPreflightError("stress cost contract changed")
    if execution.get("funding") != {
        "instrument": "Bybit_USDT_linear_perpetual_long",
        "event_interval": "use_symbol_specific_hash_pinned_funding_timestamps_not_a_fixed_8h_assumption",
        "event_inclusion": "entry_ts_lte_funding_ts_lt_exit_ts",
        "base_debit_bps": "max(actual_positive_funding_bps,0)",
        "stress_debit_bps": "max(actual_positive_funding_bps,5.0)",
        "negative_rate_credit_bps": 0.0,
        "missing_or_incomplete_history": "FAIL_CLOSED_NO_PERFORMANCE",
    }:
        raise BreakoutLongPreflightError("funding contract changed")

    temporal = _require_exact_keys(
        config.get("temporal_partition"),
        {"folds", "embargo_h1", "fold_assignment", "warmup", "one_shot_holdout_rule"},
        "temporal_partition",
    )
    expected_folds = [
        {"id": "fold_1", "start_utc": "2026-03-06T14:00:00Z", "end_utc_exclusive": "2026-04-05T14:00:00Z"},
        {"id": "fold_2", "start_utc": "2026-04-05T14:00:00Z", "end_utc_exclusive": "2026-05-05T14:00:00Z"},
        {"id": "fold_3", "start_utc": "2026-05-05T14:00:00Z", "end_utc_exclusive": "2026-06-04T14:00:00Z"},
        {"id": "fold_4", "start_utc": "2026-06-04T14:00:00Z", "end_utc_exclusive": "2026-07-04T14:00:00Z"},
    ]
    if temporal.get("folds") != expected_folds or temporal.get("embargo_h1") != 72:
        raise BreakoutLongPreflightError("fixed folds or 72h embargo changed")
    if temporal.get("fold_assignment") != {
        "event_assigned_by": "signal_close_timestamp",
        "entry_and_exit_must_both_complete_inside_same_fold": True,
        "first_72_H1_after_each_internal_boundary_scored": False,
        "signals_during_embargo_update_cooldown_but_are_not_scored": True,
    }:
        raise BreakoutLongPreflightError("fold assignment changed")
    if temporal.get("warmup") != {
        "completed_H1_bars": 20,
        "may_precede_holdout_start": True,
        "warmup_returns_or_outcomes_scored": False,
    }:
        raise BreakoutLongPreflightError("causal warmup contract changed")
    if temporal.get("one_shot_holdout_rule") != {
        "maximum_performance_runs": 1,
        "parameter_or_gate_changes_after_result": "new_named_generation_and_new_unseen_data_required",
        "partial_symbol_or_fold_preview_allowed": False,
    }:
        raise BreakoutLongPreflightError("one-shot sealed evaluation rule changed")


def _validate_gates(config: Mapping[str, Any]) -> None:
    gates = _require_exact_keys(
        config.get("promotion_gates"),
        {"aggregate", "folds", "breadth_and_concentration", "decision_rule"},
        "promotion_gates",
    )
    if gates.get("aggregate") != {
        "stress_closed_trades_min": 100,
        "base_profit_factor_min": 1.25,
        "stress_profit_factor_min": 1.10,
        "stress_net_pnl_must_be_positive": True,
        "stress_95pct_winsorized_mean_net_bps_must_be_positive": True,
        "stress_timestamp_portfolio_max_drawdown_pct_max": 12.0,
        "invalid_or_censored_trades_max": 0,
        "long_side_purity_pct_min": 100.0,
    }:
        raise BreakoutLongPreflightError("aggregate promotion gates changed")
    if gates.get("folds") != {
        "fixed_folds": 4,
        "stress_trades_per_fold_min": 15,
        "stress_net_positive_folds_min": 3,
        "stress_median_fold_profit_factor_min": 1.05,
    }:
        raise BreakoutLongPreflightError("fold promotion gates changed")
    if gates.get("breadth_and_concentration") != {
        "traded_symbols_min": 10,
        "stress_positive_symbols_min": 7,
        "largest_symbol_trade_count_share_max": 0.15,
        "symbol_trade_count_hhi_max": 0.12,
        "top_symbol_positive_net_contribution_share_max": 0.35,
        "top_10pct_trades_positive_net_contribution_share_max": 0.65,
        "leave_one_symbol_out_stress_net_must_be_positive": True,
        "leave_one_symbol_out_worst_stress_profit_factor_min": 1.02,
    }:
        raise BreakoutLongPreflightError("breadth/concentration gates changed")
    if gates.get("decision_rule") != {
        "any_gate_failure": "NO_PROMOTION",
        "all_gates_pass": "SEALED_RESEARCH_PASS_ONLY_REQUIRES_INDEPENDENT_PARITY_REVIEW_AND_PROSPECTIVE_PAPER",
        "automatic_live_or_shadow_authorization": False,
        "post_hoc_symbol_fold_trade_or_parameter_exclusion_allowed": False,
    }:
        raise BreakoutLongPreflightError("decision rule changed")


def validate_preregistration(root: Path, config_path: Path) -> dict[str, Any]:
    """Validate the frozen contract without opening any raw market snapshot."""
    config = _read_json(config_path)
    if not isinstance(config, Mapping):
        raise BreakoutLongPreflightError("preregistration root must be an object")
    fingerprint = config.get("preregistration_fingerprint_sha256")
    frozen = dict(config)
    frozen.pop("preregistration_fingerprint_sha256", None)
    if fingerprint != canonical_sha256(frozen):
        raise BreakoutLongPreflightError("preregistration fingerprint mismatch")
    if config.get("schema_version") != 1 or config.get("kind") != EXPECTED_KIND:
        raise BreakoutLongPreflightError("schema/kind changed")
    if config.get("candidate_count") != 1:
        raise BreakoutLongPreflightError("exactly one successor candidate is required")
    if not all(config.get(key) is True for key in (
        "research_only", "preregistered_before_holdout_access",
    )):
        raise BreakoutLongPreflightError("research/preregistration safety flags changed")
    if any(config.get(key) is not False for key in (
        "performance_computed", "sealed_holdout_decoded", "parameter_search",
        "promotion_eligible_now", "live_router_broker_or_allocator_integration",
    )):
        raise BreakoutLongPreflightError("performance/search/live flags must remain false")
    _validate_provenance(root, config)
    _validate_data_contract(root, config)
    _validate_strategy_contract(config)
    _validate_execution_and_partitions(config)
    _validate_gates(config)

    preflight = _require_exact_keys(
        config.get("preflight_contract"),
        {"path", "sha256", "mode", "performance_runner", "network_calls", "writes"},
        "preflight_contract",
    )
    if preflight.get("path") != "scripts/preflight_horizontal_breakout_long_72h_sealed_v1.py":
        raise BreakoutLongPreflightError("preflight path changed")
    if sha256_file(_repo_file(root, preflight["path"])) != preflight.get("sha256"):
        raise BreakoutLongPreflightError("preflight code pin changed")
    if preflight.get("mode") != "integrity_only_no_market_row_access":
        raise BreakoutLongPreflightError("preflight mode changed")
    if preflight.get("performance_runner") != "NOT_IMPLEMENTED_AND_FORBIDDEN_IN_THIS_FREEZE":
        raise BreakoutLongPreflightError("performance runner unexpectedly exists")
    if preflight.get("network_calls") is not False or preflight.get("writes") is not False:
        raise BreakoutLongPreflightError("preflight must remain read-only and offline")

    return {
        "schema": "horizontal_breakout_long_72h_sealed_v1_preflight_receipt",
        "integrity_pass": True,
        "config": config_path.relative_to(root.resolve()).as_posix(),
        "config_sha256": sha256_file(config_path),
        "preregistration_fingerprint_sha256": fingerprint,
        "candidate_count": 1,
        "candidate_id": "horizontal_breakout_long_72h_v1",
        "physical_side": "long",
        "sealed_holdout_rows_decoded": 0,
        "market_snapshots_opened": 0,
        "performance_computed": False,
        "promotion_eligible": False,
        "live_or_broker_calls": False,
        "writes_performed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    try:
        payload = validate_preregistration(ROOT, config_path)
        exit_code = 0
    except (OSError, TypeError, ValueError, BreakoutLongPreflightError) as exc:
        payload = {
            "schema": "horizontal_breakout_long_72h_sealed_v1_preflight_receipt",
            "integrity_pass": False,
            "sealed_holdout_rows_decoded": 0,
            "market_snapshots_opened": 0,
            "performance_computed": False,
            "promotion_eligible": False,
            "live_or_broker_calls": False,
            "writes_performed": False,
            "error": str(exc),
        }
        exit_code = 2
    print(json.dumps(payload, indent=None if args.compact else 2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
