#!/usr/bin/env python3
"""Phase-0 fail-closed preflight for event_expansion_retest_long_v1.

The module intentionally imports no project/trading code and cannot calculate
returns, simulate fills, call a broker, or authorize a performance run.  It
only verifies the frozen file/data identity and emits the preregistered missing
research-mechanics blockers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    ROOT
    / "configs"
    / "preregistered"
    / "event_expansion_retest_long_v1_20260713.json"
)

EXPECTED_COMMIT = "f07dd012810d55028d238fe5d6780e591768bb64"
EXPECTED_DEV_MANIFEST_PATH = (
    "data_cache/immutable/"
    "pump_exhaustion_unwind_short_v1_720d_20260711/manifest.json"
)
EXPECTED_DEV_MANIFEST_SHA256 = (
    "f1f425e8822a5a8de56676fb24f257982d4c5fb33e254a328dc2b8243aedffd8"
)
EXPECTED_DEV13 = (
    "1000PEPEUSDT", "ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT",
    "DOGEUSDT", "ETHUSDT", "ONDOUSDT", "SOLUSDT", "SUIUSDT",
    "TAOUSDT", "WIFUSDT", "XRPUSDT",
)
EXPECTED_EXTERNAL8_BASE = ("FIL", "UNI", "ETC", "ICP", "TRX", "TON", "MNT", "IMX")
EXPECTED_EXTERNAL8 = tuple(f"{symbol}USDT" for symbol in EXPECTED_EXTERNAL8_BASE)
EXPECTED_PIN_ROLES = {
    "phase0_preflight": "scripts/preflight_event_expansion_retest_long_v1.py",
    "level_snapshot_source": "bot/level_snapshot_v1.py",
    "strategy_mechanics_source": "strategies/event_expansion_retest_long_v1.py",
    "state_store_source": "bot/event_expansion_retest_long_state_store.py",
    "market_context_dependency": "bot/market_context.py",
    "closed_bar_aggregation_source": "bot/closed_bar_aggregation_v1.py",
    "level_snapshot_tests": "tests/test_level_snapshot_v1.py",
    "strategy_mechanics_tests": "tests/test_event_expansion_retest_long_v1.py",
    "state_store_tests": "tests/test_event_expansion_retest_long_state_store.py",
    "closed_bar_aggregation_tests": "tests/test_closed_bar_aggregation_v1.py",
    "phase0_preflight_tests": "tests/test_preflight_event_expansion_retest_long_v1.py",
}
EXPECTED_BLOCKERS = (
    "PERFORMANCE_RUNNER_ABSENT",
    "MULTITIMEFRAME_ORCHESTRATOR_ABSENT",
    "EXIT_MODEL_ABSENT",
    "COST_FUNDING_MODEL_ABSENT",
    "EXTERNAL8_MARKET_DATA_ABSENT",
    "EXTERNAL8_METADATA_ABSENT",
    "EXTERNAL8_LIQUIDITY_ABSENT",
    "EXTERNAL8_FUNDING_ABSENT",
    "ATT1_REFERENCE_ABSENT",
)


class PreflightError(ValueError):
    """The phase-0 preregistration is malformed or no longer frozen."""


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


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _repo_file(root: Path, raw: object) -> Path:
    text = str(raw or "")
    relative = Path(text)
    if not text or relative.is_absolute() or "\\" in text:
        raise PreflightError(f"path must be non-empty and repo-relative: {text!r}")
    if any(part in {"", ".", ".."} for part in relative.parts) or ".git" in relative.parts:
        raise PreflightError(f"unsafe repo-relative path: {text!r}")
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PreflightError(f"pinned path contains a symlink: {text!r}")
    return cursor


def _contract_fingerprint(cfg: Mapping[str, Any]) -> str:
    frozen = dict(cfg)
    frozen.pop("contract_fingerprint_sha256", None)
    return canonical_sha256(frozen)


def _forbidden_outcome_section(value: object) -> bool:
    forbidden = {
        "performance_results", "outcome_results", "trade_results",
        "selected_winner", "promotion_verdict", "observed_metrics",
    }
    if isinstance(value, Mapping):
        return any(
            str(key) in forbidden or _forbidden_outcome_section(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_forbidden_outcome_section(item) for item in value)
    return False


def validate_contract(cfg: Mapping[str, Any]) -> None:
    if cfg.get("schema_version") != 1 or cfg.get("phase") != "PHASE_0_MECHANICS_IDENTITY_ONLY":
        raise PreflightError("schema/phase must remain the frozen phase-0 contract")
    if cfg.get("name") != "event_expansion_retest_long_v1_20260713_phase0":
        raise PreflightError("preregistration identity changed")
    required_true = ("research_only", "no_parameter_scan", "no_performance_access")
    if not all(cfg.get(key) is True for key in required_true):
        raise PreflightError("research-only performance embargo is mandatory")
    if cfg.get("live_or_broker_calls") is not False or cfg.get("risk_pct") != 0:
        raise PreflightError("phase 0 must remain broker-free and risk-zero")
    if cfg.get("current_automatic_verdict") != "BLOCKED_RESEARCH_MECHANICS":
        raise PreflightError("phase-0 verdict must remain blocked")
    if cfg.get("current_performance_permission") != "PERFORMANCE_FORBIDDEN":
        raise PreflightError("performance must remain forbidden")
    if cfg.get("current_live_permission") != "LIVE_FORBIDDEN":
        raise PreflightError("live permission must remain forbidden")

    identity = cfg.get("implementation_identity")
    if not isinstance(identity, Mapping):
        raise PreflightError("implementation identity is missing")
    if identity.get("git_commit") != EXPECTED_COMMIT or identity.get("side_identity") != "long_only":
        raise PreflightError("implementation commit or physical side identity changed")
    if identity.get("level_schema") != "level_snapshot_v1":
        raise PreflightError("level schema changed")
    if identity.get("level_scope") != "horizontal_h1_h4_resistance_flip_only":
        raise PreflightError("phase 0 is horizontal H1/H4 only")
    if identity.get("sloped_levels") != "DEFERRED_TO_A_SEPARATE_VERSIONED_CONTRACT":
        raise PreflightError("sloped levels must stay deferred")
    pins = identity.get("pinned_files")
    if not isinstance(pins, list) or len(pins) != len(EXPECTED_PIN_ROLES):
        raise PreflightError("pinned source/dependency/test set is incomplete")
    pin_map: dict[str, Mapping[str, Any]] = {}
    for row in pins:
        if not isinstance(row, Mapping) or set(row) != {"role", "path", "sha256"}:
            raise PreflightError("each pinned file needs role/path/sha256 only")
        role = str(row.get("role") or "")
        if role in pin_map:
            raise PreflightError(f"duplicate pinned role: {role}")
        pin_map[role] = row
    if set(pin_map) != set(EXPECTED_PIN_ROLES):
        raise PreflightError("pinned roles changed")
    for role, expected_path in EXPECTED_PIN_ROLES.items():
        if pin_map[role].get("path") != expected_path or not _is_sha256(pin_map[role].get("sha256")):
            raise PreflightError(f"invalid frozen pin: {role}")

    cohorts = cfg.get("cohorts")
    if not isinstance(cohorts, Mapping) or set(cohorts) != {"dev13", "sealed_external8", "prospective"}:
        raise PreflightError("cohort split changed")
    dev = cohorts["dev13"]
    external = cohorts["sealed_external8"]
    prospective = cohorts["prospective"]
    if not all(isinstance(row, Mapping) for row in (dev, external, prospective)):
        raise PreflightError("cohort contracts must be objects")
    if tuple(dev.get("symbols", ())) != EXPECTED_DEV13:
        raise PreflightError("dev13 symbols changed")
    if dev.get("role") != "DEVELOPMENT_MECHANICS_ONLY_NO_PROMOTION_AUTHORITY":
        raise PreflightError("dev13 cannot acquire promotion authority")
    if (
        dev.get("source_interval") != "M5"
        or dev.get("window_start_utc") != "2024-07-15T00:00:00Z"
        or dev.get("window_end_utc_exclusive") != "2026-07-05T00:00:00Z"
    ):
        raise PreflightError("dev13 source grain/window changed")
    if dev.get("manifest_path") != EXPECTED_DEV_MANIFEST_PATH:
        raise PreflightError("dev13 manifest path changed")
    if dev.get("manifest_sha256") != EXPECTED_DEV_MANIFEST_SHA256:
        raise PreflightError("dev13 manifest hash changed")
    if tuple(external.get("base_assets", ())) != EXPECTED_EXTERNAL8_BASE:
        raise PreflightError("sealed external8 assets changed")
    if tuple(external.get("symbols", ())) != EXPECTED_EXTERNAL8:
        raise PreflightError("sealed external8 symbols changed")
    if external.get("role") != "STRATEGY_UNTOUCHED_HISTORICAL_REPLICATION":
        raise PreflightError("external8 must not be overstated as genuinely untouched")
    if external.get("data_status") != "ABSENT_AND_UNREAD":
        raise PreflightError("phase-0 external8 data status changed")
    if external.get("sealed_before_data_access") is not True:
        raise PreflightError("external8 must remain sealed")
    if external.get("manifest_path") or external.get("manifest_sha256"):
        raise PreflightError("phase 0 cannot silently attach external8 data")
    if prospective.get("start_utc") is not None or prospective.get("status") != "NOT_STARTED":
        raise PreflightError("prospective observation cannot start before runnable freeze/push")

    expected_mtf = {
        "raw_source": "exact_closed_M5_bars",
        "aggregation": {
            "H1": "12_contiguous_M5_bars_utc_grid_no_partial_bucket",
            "H4": "48_contiguous_M5_bars_utc_grid_no_partial_bucket",
            "M15": "3_contiguous_M5_bars_utc_grid_no_partial_bucket",
        },
        "level_source": "frozen_horizontal_resistance_from_closed_H1_or_H4_only",
        "expansion_signal": "closed_H1_only",
        "hold_and_first_retest": "strictly_later_closed_M15_bars_only",
        "bullish_structure_confirmation": "strictly_later_closed_M15_bar_after_first_retest",
        "execution": "first_eligible_M5_open_strictly_after_confirmation",
        "same_bar_stage_collapse_allowed": False,
        "future_bar_access_allowed": False,
        "first_retest_only": True,
        "duplicate_event_or_plan_ids_allowed": False,
        "level_redraw_after_event_allowed": False,
        "provider_mixing_allowed": False,
        "missing_or_duplicate_source_bars_allowed": False,
    }
    if cfg.get("intended_multitimeframe_contract") != expected_mtf:
        raise PreflightError("multi-timeframe causal contract changed")

    missing = cfg.get("phase0_missing_artifacts")
    if not isinstance(missing, list) or tuple(row.get("code") for row in missing if isinstance(row, Mapping)) != EXPECTED_BLOCKERS:
        raise PreflightError("phase-0 blocker set/order changed")
    for row in missing:
        if set(row) != {"code", "required_artifact", "path", "sha256"}:
            raise PreflightError("blocker artifact fields changed")
        if row.get("path") or row.get("sha256"):
            raise PreflightError("phase-0 missing artifacts must remain unpinned")

    gates = cfg.get("future_evaluation_gates")
    if not isinstance(gates, Mapping):
        raise PreflightError("future gates are missing")
    aggregate = gates.get("aggregate", {})
    folds = gates.get("folds", {})
    holdout = gates.get("final_holdout", {})
    breadth = gates.get("cohort_breadth", {})
    loso = gates.get("leave_one_symbol_out", {})
    additivity = gates.get("att1_additivity", {})
    exact_values = (
        (aggregate.get("base_profit_factor_min"), 1.35),
        (aggregate.get("stress_profit_factor_min"), 1.25),
        (aggregate.get("stress_closed_trades_min"), 60),
        (aggregate.get("stress_conservative_max_drawdown_pct_max"), 8.0),
        (aggregate.get("long_side_purity_pct_min"), 100.0),
        (folds.get("fixed_folds"), 4),
        (folds.get("calendar_days_per_fold"), 150),
        (folds.get("trades_per_fold_min"), 8),
        (folds.get("net_positive_folds_min"), 3),
        (folds.get("median_fold_profit_factor_min"), 1.1),
        (holdout.get("stress_closed_trades_min"), 12),
        (holdout.get("stress_profit_factor_min"), 1.1),
        (breadth.get("dev13_traded_symbols_min"), 7),
        (breadth.get("dev13_positive_symbols_min"), 4),
        (breadth.get("external8_traded_symbols_min"), 6),
        (breadth.get("external8_positive_symbols_min"), 4),
        (breadth.get("top_positive_net_concentration_pct_max"), 30.0),
        (loso.get("worst_stress_profit_factor_min"), 1.05),
        (loso.get("worst_stress_max_drawdown_pct_max"), 10.0),
        (additivity.get("daily_return_correlation_abs_max"), 0.35),
        (additivity.get("downside_return_correlation_abs_max"), 0.45),
        (additivity.get("co_loss_day_jaccard_max"), 0.4),
    )
    if any(actual != expected for actual, expected in exact_values):
        raise PreflightError("a strict future numerical gate changed")
    if any(
        aggregate.get(key) != 0
        for key in ("duplicate_event_ids_max", "duplicate_plan_ids_max", "censored_or_invalid_trades_max")
    ):
        raise PreflightError("duplicates and invalid/censored trades must remain zero")
    if holdout.get("stress_net_r_must_be_positive") is not True:
        raise PreflightError("holdout net R must remain positive")
    if loso.get("worst_stress_net_r_must_be_positive") is not True:
        raise PreflightError("worst LOSO net R must remain positive")
    if additivity.get("occupancy_orderings_required") != ["ATT1_FIRST", "EVENT_LONG_FIRST"]:
        raise PreflightError("both occupancy orderings are mandatory")
    if (
        additivity.get("worse_ordering_long_trade_retention_pct_min") != 70.0
        or additivity.get("worse_ordering_max_drawdown_ratio_to_att1_max") != 1.1
        or additivity.get("worse_ordering_return_over_drawdown_ratio_to_att1_min") != 1.1
        or additivity.get("worse_ordering_worst_month_degradation_percentage_points_max") != 0.5
    ):
        raise PreflightError("ATT1 occupancy/additivity gates changed")
    if cfg.get("fixed_temporal_partition", {}).get("embargo_after_boundaries_days") != 7:
        raise PreflightError("the seven-day boundary embargo changed")
    costs = cfg.get("future_execution_and_cost_contract", {})
    if costs.get("sizing") != {
        "starting_equity_usd": 100.0,
        "risk_fraction_per_trade": 0.005,
        "notional_cap_usd": 30.0,
        "max_global_open_positions": 4,
        "max_open_positions_per_symbol": 1,
    }:
        raise PreflightError("future sizing contract changed")
    if costs.get("base_costs") != {"fee_bps_per_side": 6.0, "slippage_bps_per_side": 2.0}:
        raise PreflightError("base costs changed")
    if costs.get("stress_costs") != {"fee_bps_per_side": 10.0, "slippage_bps_per_side": 5.0}:
        raise PreflightError("stress costs changed")
    if costs.get("funding") != {
        "credits_bps": 0.0,
        "debit_rule": "max(actual_debit,5_bps_per_funding_event)",
        "missing_funding_data": "FAIL_CLOSED",
    }:
        raise PreflightError("funding contract changed")
    if costs.get("exit_model", "").split("_")[0] != "UNDEFINED":
        raise PreflightError("an exit model requires a successor runnable freeze")
    if _forbidden_outcome_section(cfg):
        raise PreflightError("phase-0 preregistration contains forbidden outcome data")
    expected_fingerprint = _contract_fingerprint(cfg)
    if cfg.get("contract_fingerprint_sha256") != expected_fingerprint:
        raise PreflightError("contract fingerprint mismatch")


def _manifest_identity(root: Path, dev: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    path = _repo_file(root, dev["manifest_path"])
    expected = str(dev["manifest_sha256"])
    actual = sha256_file(path) if path.is_file() else None
    blockers: list[dict[str, str]] = []
    symbols: list[str] = []
    shape_ok = False
    if actual == expected:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            symbols = sorted(str(item) for item in raw.get("input_snapshots", {}))
            snapshot_rows = raw.get("input_snapshots", {})
            shape_ok = (
                raw.get("interval_ms") == 300_000
                and raw.get("network_calls") is False
                and raw.get("performance_computed") is False
                and tuple(symbols) == tuple(sorted(EXPECTED_DEV13))
                and isinstance(snapshot_rows, Mapping)
                and all(_is_sha256(row.get("sha256")) for row in snapshot_rows.values())
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            shape_ok = False
    if actual != expected:
        blockers.append({
            "code": "DEV13_MANIFEST_HASH_MISMATCH",
            "severity": "CRITICAL",
            "reason": "the frozen dev13 manifest is missing or changed",
        })
    elif not shape_ok:
        blockers.append({
            "code": "DEV13_MANIFEST_IDENTITY_INVALID",
            "severity": "CRITICAL",
            "reason": "the pinned manifest no longer describes the exact immutable M5 dev13 cohort",
        })
    return {
        "path": dev["manifest_path"],
        "expected_sha256": expected,
        "actual_sha256": actual,
        "hash_match": actual == expected,
        "shape_match": shape_ok,
        "symbols": symbols,
    }, blockers


def build_preflight(cfg: Mapping[str, Any], root: Path) -> dict[str, Any]:
    validate_contract(cfg)
    identity = cfg["implementation_identity"]
    file_rows: list[dict[str, Any]] = []
    integrity_blockers: list[dict[str, str]] = []
    for pin in identity["pinned_files"]:
        path = _repo_file(root, pin["path"])
        actual = sha256_file(path) if path.is_file() else None
        match = actual == pin["sha256"]
        file_rows.append({
            "role": pin["role"],
            "path": pin["path"],
            "expected_sha256": pin["sha256"],
            "actual_sha256": actual,
            "match": match,
        })
        if not match:
            integrity_blockers.append({
                "code": "PINNED_FILE_HASH_MISMATCH",
                "severity": "CRITICAL",
                "reason": f"pinned identity mismatch: {pin['role']}",
            })
    manifest_identity, manifest_blockers = _manifest_identity(root, cfg["cohorts"]["dev13"])
    integrity_blockers.extend(manifest_blockers)
    declared_blockers = [
        {
            "code": row["code"],
            "severity": "CRITICAL",
            "reason": row["required_artifact"],
        }
        for row in cfg["phase0_missing_artifacts"]
    ]
    return {
        "schema": "event_expansion_retest_long_v1_phase0_preflight",
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "BLOCKED_RESEARCH_MECHANICS",
        "performance_permission": "PERFORMANCE_FORBIDDEN",
        "live_permission": "LIVE_FORBIDDEN",
        "identity": {
            "preregistration": cfg["name"],
            "contract_fingerprint_sha256": cfg["contract_fingerprint_sha256"],
            "implementation_commit": identity["git_commit"],
            "side_identity": "long_only",
            "level_scope": identity["level_scope"],
            "sloped_levels": identity["sloped_levels"],
            "pinned_files": file_rows,
            "dev13_manifest": manifest_identity,
            "sealed_external8": list(cfg["cohorts"]["sealed_external8"]["symbols"]),
            "prospective_status": cfg["cohorts"]["prospective"]["status"],
            "integrity_pass": not integrity_blockers,
        },
        "blockers": integrity_blockers + declared_blockers,
    }


def _failure_payload(message: str) -> dict[str, Any]:
    return {
        "schema": "event_expansion_retest_long_v1_phase0_preflight",
        "status": "BLOCKED_RESEARCH_MECHANICS",
        "performance_permission": "PERFORMANCE_FORBIDDEN",
        "live_permission": "LIVE_FORBIDDEN",
        "identity": {"integrity_pass": False},
        "blockers": [{
            "code": "PREREGISTRATION_INTEGRITY_FAILURE",
            "severity": "CRITICAL",
            "reason": str(message),
        }],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    try:
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(cfg, Mapping):
            raise PreflightError("config root must be an object")
        payload = build_preflight(cfg, args.root.resolve())
        exit_code = 0 if payload["identity"]["integrity_pass"] else 2
    except (OSError, TypeError, ValueError, json.JSONDecodeError, PreflightError) as exc:
        payload = _failure_payload(str(exc))
        exit_code = 2
    print(json.dumps(payload, indent=None if args.compact else 2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
