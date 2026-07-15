#!/usr/bin/env python3
"""Materialize immutable, research-only Alpaca parity input receipts.

This command never imports a broker SDK, reads credentials, calculates P&L,
changes SAFE_HOLD, or grants promotion authority.  It records which parts of
the exact-parity contract can be proved from local, hash-pinned evidence and
keeps every unavailable input explicitly blocked.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.alpaca_exact_parity_contract import (  # noqa: E402
    DailyBar,
    ParityContractError,
    SharedExitContract,
    XNYSSession,
    adverse_fill_price,
    calendar_month_signal_schedule,
    daily_max_drawdown,
    daily_next_open_schedule,
    daily_portfolio_mark_to_market,
    load_xnys_session_ledger,
    sha256_file,
    simulate_position,
)
from scripts.preflight_alpaca_monthly_exact_parity import (  # noqa: E402
    DEFAULT_CONFIG as PARENT_PREREG,
    evaluate_preflight,
)


DEFAULT_CONFIG = (
    ROOT
    / "configs"
    / "preregistered"
    / "alpaca_exact_parity_materialization_v1_20260715.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "reports"
    / "research"
    / "alpaca_exact_parity_materialization_v1_20260715"
    / "receipt.json"
)
REQUIRED_INPUT_SCHEMAS = {
    "official_xnys_session_ledger": "xnys_session_ledger_v1",
    "point_in_time_universe": "alpaca_point_in_time_universe_v1",
    "point_in_time_market_data_manifest": "alpaca_point_in_time_market_data_manifest_v1",
    "corporate_actions_and_delistings": "alpaca_corporate_actions_delistings_v1",
    "broker_order_fill_lifecycle": "alpaca_broker_lifecycle_v1",
    "untouched_forward_manifest": "alpaca_untouched_forward_manifest_v2",
}
SOURCE_KEYS = {
    "parent_preregistration": "configs/preregistered/alpaca_monthly_exact_parity_replay_20260713.json",
    "parent_preflight": "scripts/preflight_alpaca_monthly_exact_parity.py",
    "parity_contract_implementation": "backtest/alpaca_exact_parity_contract.py",
    "materializer": "scripts/materialize_alpaca_exact_parity_inputs.py",
}


class MaterializationError(ValueError):
    """Raised when the materialization contract itself is unsafe."""


def _is_sha(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _repo_path(raw: object) -> Path:
    text = str(raw or "")
    candidate = Path(text)
    if not text or candidate.is_absolute() or "\\" in text or ".." in candidate.parts:
        raise MaterializationError(f"path must be safe and repo-relative: {text!r}")
    path = ROOT
    for part in candidate.parts:
        path = path / part
        if path.is_symlink():
            raise MaterializationError(f"path contains symlink: {text!r}")
    return path


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise MaterializationError(f"refusing to overwrite immutable receipt: {path}")
    if path.is_symlink():
        raise MaterializationError("refusing output symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def validate_materialization_config(cfg: Mapping[str, Any]) -> None:
    required_true = (
        "research_only",
        "performance_forbidden",
        "no_broker_calls",
        "no_live_writes",
        "safe_hold_must_remain",
    )
    if cfg.get("schema_version") != 1 or not all(cfg.get(key) is True for key in required_true):
        raise MaterializationError("research-only fail-closed flags are mandatory")
    if cfg.get("risk_pct") != 0 or cfg.get("promotion_authority") is not False:
        raise MaterializationError("materializer must remain risk-zero without promotion authority")
    sources = cfg.get("sources")
    if not isinstance(sources, Mapping) or set(sources) != set(SOURCE_KEYS):
        raise MaterializationError("source pin set changed")
    for key, rel in SOURCE_KEYS.items():
        row = sources[key]
        if not isinstance(row, Mapping) or row.get("path") != rel or not _is_sha(row.get("sha256")):
            raise MaterializationError(f"source pin invalid: {key}")
    inputs = cfg.get("required_inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != set(REQUIRED_INPUT_SCHEMAS):
        raise MaterializationError("required input set changed")
    for key, schema_id in REQUIRED_INPUT_SCHEMAS.items():
        row = inputs[key]
        if not isinstance(row, Mapping) or set(row) != {"schema_id", "path", "sha256"}:
            raise MaterializationError(f"input contract invalid: {key}")
        if row.get("schema_id") != schema_id:
            raise MaterializationError(f"input schema changed: {key}")
        if bool(row.get("path")) != bool(row.get("sha256")):
            raise MaterializationError(f"input path/hash must be pinned together: {key}")
        if row.get("sha256") and not _is_sha(row.get("sha256")):
            raise MaterializationError(f"input hash invalid: {key}")
    contract = cfg.get("contract")
    expected_contract = {
        "calendar": "XNYS",
        "signal_time": "last_completed_xnys_session_close_of_calendar_month",
        "entry_time": "next_xnys_session_open",
        "completed_bars_only": True,
        "same_close_entry": False,
        "base_cost_bps_per_side": 5.0,
        "stress_cost_bps_per_side": 10.0,
        "entry_cost_application": "adverse_at_next_open",
        "stop_gap_fill": "opening_price_if_open_beyond_stop",
        "target_gap_fill": "frozen_target_no_favorable_gap_credit",
        "same_bar_stop_and_target": "stop_first",
        "daily_mark_to_market": True,
        "daily_drawdown_includes_initial_capital": True,
        "shared_exit": {
            "initial_stop_atr": 2.0,
            "profit_target_atr": 3.2,
            "break_even_trigger_r": 0.8,
            "trail_atr": 1.5,
            "max_hold_sessions": 22,
            "intramonth_portfolio_stop_pct": 0.08,
            "stop_update_timing": "completed_bar_for_next_session",
        },
    }
    if contract != expected_contract:
        raise MaterializationError("calendar/execution/cost/MTM/shared-exit contract changed")


def _source_status(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in SOURCE_KEYS:
        row = cfg["sources"][key]
        path = _repo_path(row["path"])
        actual = sha256_file(path) if path.is_file() else None
        expected = row["sha256"]
        out.append(
            {
                "name": key,
                "path": row["path"],
                "expected_sha256": expected,
                "actual_sha256": actual,
                "ok": actual == expected,
            }
        )
    return out


def _validate_json_input(name: str, path: Path, schema_id: str) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["json_unreadable"]
    if not isinstance(payload, Mapping) or payload.get("schema_id") != schema_id:
        return ["schema_mismatch"]
    reasons: list[str] = []
    if name == "point_in_time_universe":
        if payload.get("point_in_time_membership") is not True or not payload.get("membership_intervals"):
            reasons.append("point_in_time_membership_unproven")
    elif name == "point_in_time_market_data_manifest":
        expected = {
            "point_in_time": True,
            "completed_bars_only": True,
            "calendar": "XNYS",
            "bar_interval": "1d",
            "price_basis": "split_and_dividend_adjusted_ohlcv",
        }
        if any(payload.get(key) != value for key, value in expected.items()) or not payload.get("files"):
            reasons.append("market_data_pit_or_adjustment_unproven")
    elif name == "corporate_actions_and_delistings":
        if (
            payload.get("point_in_time") is not True
            or payload.get("includes_delisted_names") is not True
            or payload.get("known_as_of_event_time") is not True
        ):
            reasons.append("corporate_action_or_delisting_history_unproven")
    elif name == "broker_order_fill_lifecycle":
        if payload.get("reconstruction_complete") is not True or payload.get("unresolved_conflicts") != 0:
            reasons.append("broker_lifecycle_incomplete")
    elif name == "untouched_forward_manifest":
        try:
            sealed = datetime.fromisoformat(str(payload["sealed_at_utc"]).replace("Z", "+00:00"))
            starts = datetime.fromisoformat(str(payload["window_start_utc"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            reasons.append("forward_dates_invalid")
        else:
            if sealed.tzinfo is None or starts.tzinfo is None or sealed >= starts:
                reasons.append("forward_not_sealed_before_window")
            if payload.get("outcomes_read_before_seal") is not False:
                reasons.append("forward_outcome_embargo_unproven")
    return sorted(set(reasons))


def _required_input_status(cfg: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[XNYSSession] | None]:
    statuses: list[dict[str, Any]] = []
    official_sessions: list[XNYSSession] | None = None
    for name, schema_id in REQUIRED_INPUT_SCHEMAS.items():
        row = cfg["required_inputs"][name]
        if not row["path"]:
            statuses.append(
                {
                    "name": name,
                    "schema_id": schema_id,
                    "status": "MISSING_UNPINNED",
                    "ok": False,
                    "reasons": ["artifact_unpinned"],
                }
            )
            continue
        try:
            path = _repo_path(row["path"])
        except MaterializationError as exc:
            statuses.append(
                {"name": name, "schema_id": schema_id, "status": "INVALID", "ok": False, "reasons": [str(exc)]}
            )
            continue
        reasons: list[str] = []
        if not path.is_file():
            reasons.append("artifact_missing")
        elif sha256_file(path) != row["sha256"]:
            reasons.append("artifact_hash_mismatch")
        elif name == "official_xnys_session_ledger":
            try:
                official_sessions = load_xnys_session_ledger(path, expected_sha256=row["sha256"])
            except ParityContractError as exc:
                reasons.append(str(exc))
        else:
            reasons.extend(_validate_json_input(name, path, schema_id))
        statuses.append(
            {
                "name": name,
                "schema_id": schema_id,
                "path": row["path"],
                "sha256": row["sha256"],
                "status": "READY" if not reasons else "INVALID",
                "ok": not reasons,
                "reasons": reasons,
            }
        )
    return statuses, official_sessions


def _diagnostic_observed_schedule(cfg: Mapping[str, Any]) -> dict[str, Any]:
    row = cfg.get("diagnostic_observed_session_source")
    if not isinstance(row, Mapping) or not row.get("path") or not _is_sha(row.get("sha256")):
        return {"status": "NOT_AVAILABLE", "authoritative": False, "rows": []}
    path = _repo_path(row["path"])
    if not path.is_file() or sha256_file(path) != row["sha256"]:
        return {"status": "HASH_OR_FILE_MISMATCH", "authoritative": False, "rows": []}
    ny = ZoneInfo("America/New_York")
    observed: dict[date, list[datetime]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "ts" not in (reader.fieldnames or []):
            return {"status": "TS_COLUMN_MISSING", "authoritative": False, "rows": []}
        for record in reader:
            try:
                instant = datetime.fromtimestamp(int(float(record["ts"])), tz=timezone.utc)
            except (KeyError, TypeError, ValueError, OSError):
                continue
            session_date = instant.astimezone(ny).date()
            observed.setdefault(session_date, []).append(instant)
    pseudo_sessions = [
        XNYSSession(
            session_date=session_date,
            market_open_utc=min(instants),
            market_close_utc=max(instants),
            source_record_sha256=row["sha256"],
        )
        for session_date, instants in sorted(observed.items())
    ]
    try:
        pairs = calendar_month_signal_schedule(pseudo_sessions)
    except ParityContractError:
        pairs = []
    return {
        "status": "DIAGNOSTIC_ONLY_NOT_XNYS_AUTHORITY",
        "authoritative": False,
        "source_path": row["path"],
        "source_sha256": row["sha256"],
        "observed_session_count": len(pseudo_sessions),
        "observed_first_session": pseudo_sessions[0].session_date.isoformat() if pseudo_sessions else None,
        "observed_last_session": pseudo_sessions[-1].session_date.isoformat() if pseudo_sessions else None,
        "calendar_month_pairs": pairs,
        "warning": "dates/times are inferred from observed SPY bars and cannot prove the official XNYS holiday or early-close calendar",
    }


def _diagnostic_market_inventory(cfg: Mapping[str, Any]) -> dict[str, Any]:
    raw = cfg.get("diagnostic_market_data_directory")
    if not raw:
        return {"status": "NOT_AVAILABLE", "authoritative": False, "files": []}
    directory = _repo_path(raw)
    if not directory.is_dir():
        return {"status": "MISSING", "authoritative": False, "files": []}
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*_M5.csv")):
        first_ts: int | None = None
        last_ts: int | None = None
        count = 0
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if "ts" not in (reader.fieldnames or []):
                continue
            for record in reader:
                try:
                    timestamp = int(float(record["ts"]))
                except (KeyError, TypeError, ValueError):
                    continue
                first_ts = timestamp if first_ts is None else min(first_ts, timestamp)
                last_ts = timestamp if last_ts is None else max(last_ts, timestamp)
                count += 1
        rows.append(
            {
                "symbol": path.name.removesuffix("_M5.csv"),
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256_file(path),
                "timestamp_rows": count,
                "first_ts": first_ts,
                "last_ts": last_ts,
            }
        )
    return {
        "status": "DIAGNOSTIC_INVENTORY_ONLY_NOT_PIT_OR_CORPORATE_ACTION_PROOF",
        "authoritative": False,
        "file_count": len(rows),
        "files": rows,
    }


def _unit_conformance() -> dict[str, Any]:
    source_sha = "a" * 64
    sessions = [
        XNYSSession(date(2026, 1, 30), datetime(2026, 1, 30, 14, 30, tzinfo=timezone.utc), datetime(2026, 1, 30, 21, 0, tzinfo=timezone.utc), source_sha),
        XNYSSession(date(2026, 2, 2), datetime(2026, 2, 2, 14, 30, tzinfo=timezone.utc), datetime(2026, 2, 2, 21, 0, tzinfo=timezone.utc), source_sha),
        XNYSSession(date(2026, 2, 27), datetime(2026, 2, 27, 14, 30, tzinfo=timezone.utc), datetime(2026, 2, 27, 21, 0, tzinfo=timezone.utc), source_sha),
        XNYSSession(date(2026, 3, 2), datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc), datetime(2026, 3, 2, 21, 0, tzinfo=timezone.utc), source_sha),
    ]
    monthly = calendar_month_signal_schedule(sessions)
    daily = daily_next_open_schedule(sessions)
    contract = SharedExitContract()
    both_touch = simulate_position(
        [DailyBar(date(2026, 2, 2), 100, 104, 97, 101)],
        atr_at_signal=1.0,
        cost_bps_per_side=0.0,
        contract=contract,
    )
    gap_stop = simulate_position(
        [
            DailyBar(date(2026, 2, 2), 100, 101, 99, 100),
            DailyBar(date(2026, 2, 3), 97, 98, 96, 97),
        ],
        atr_at_signal=1.0,
        cost_bps_per_side=0.0,
        contract=contract,
    )
    trail = simulate_position(
        [
            DailyBar(date(2026, 2, 2), 100, 102, 99, 101),
            DailyBar(date(2026, 2, 3), 101, 102, 100, 101),
        ],
        atr_at_signal=1.0,
        cost_bps_per_side=0.0,
        contract=contract,
    )
    cases = {
        "calendar_month_signal_date": monthly[0]["signal_session"] == "2026-01-30",
        "next_session_open": monthly[0]["entry_session"] == "2026-02-02" and len(daily) == 3,
        "entry_adverse_cost": adverse_fill_price(100, side="buy", cost_bps=5) > 100,
        "exit_adverse_cost": adverse_fill_price(100, side="sell", cost_bps=5) < 100,
        "same_bar_stop_first": both_touch["exit_reason"] == "stop_first",
        "opening_gap_before_intraday": gap_stop["exit_reason"] == "stop_gap_open" and gap_stop["exit_reference"] == 97,
        "break_even_and_trail_next_session": trail["daily_marks"][0]["next_session_stop"] >= trail["entry_fill"],
        "daily_mark_to_market": daily_portfolio_mark_to_market(settled_cash=50, open_positions=[{"qty": 2, "close": 25}]) == 100,
        "daily_drawdown_includes_initial": math.isclose(
            daily_max_drawdown(100, [92, 95]), -0.08, rel_tol=0.0, abs_tol=1e-12
        ),
    }
    return {
        "all_cases_passed": all(cases.values()),
        "cases": cases,
        "synthetic_only": True,
        "broker_lifecycle_exact_match": False,
        "promotion_authority": False,
    }


def build_receipt(cfg: Mapping[str, Any]) -> dict[str, Any]:
    validate_materialization_config(cfg)
    sources = _source_status(cfg)
    required_inputs, official_sessions = _required_input_status(cfg)
    parent_cfg = json.loads(PARENT_PREREG.read_text(encoding="utf-8"))
    parent_state = evaluate_preflight(ROOT, parent_cfg)
    unit = _unit_conformance()
    blockers = [f"missing_or_invalid:{row['name']}" for row in required_inputs if not row["ok"]]
    if not all(row["ok"] for row in sources):
        blockers.append("materialization_source_hash_drift")
    if not unit["all_cases_passed"]:
        blockers.append("shared_exit_unit_conformance_failed")
    blockers.extend(
        [
            "broker_calibrated_fee_slippage_unavailable",
            "shared_exit_broker_lifecycle_conformance_unavailable",
            "original_2026_07_13_forward_window_not_retroactively_sealable",
            "end_to_end_four_arm_replay_runner_not_authorized",
        ]
    )
    calendar_rows = calendar_month_signal_schedule(official_sessions) if official_sessions else []
    daily_rows = daily_next_open_schedule(official_sessions) if official_sessions else []
    component_receipts = [
        {
            "component": "calendar_month_signal_dates",
            "status": "READY" if official_sessions else "BLOCKED_OFFICIAL_XNYS_LEDGER_MISSING",
            "calendar": "XNYS",
            "rows": calendar_rows,
            "rows_sha256": _canonical_sha(calendar_rows),
        },
        {
            "component": "next_session_open_execution",
            "status": "READY" if official_sessions else "CONTRACT_READY_INPUT_BLOCKED",
            "same_close_allowed": False,
            "daily_negative_control_rows": daily_rows,
            "rows_sha256": _canonical_sha(daily_rows),
        },
        {
            "component": "point_in_time_universe_and_corporate_actions",
            "status": "BLOCKED_UNTIL_BOTH_HASH_PINNED_AND_VALID",
            "assumption_policy": "fixed modern universe or adjusted bars alone are not PIT/delisting proof",
        },
        {
            "component": "daily_mark_to_market_and_drawdown",
            "status": "EXECUTABLE_CONTRACT_READY",
            "mark_formula": "settled_cash_plus_sum(quantity_times_completed_session_close)",
            "drawdown": "daily_curve_with_initial_capital_as_first_peak",
            "implementation_sha256": cfg["sources"]["parity_contract_implementation"]["sha256"],
        },
        {
            "component": "fee_slippage_and_gap_model",
            "status": "FROZEN_DEFAULTS_BUT_BROKER_CALIBRATION_BLOCKED",
            "base_bps_per_side": 5.0,
            "stress_bps_per_side": 10.0,
            "four_fills_for_round_trip_two_position_rotations": False,
            "applied_adversely_on_every_entry_and_exit": True,
        },
        {
            "component": "shared_stop_break_even_trailing_contract",
            "status": "SYNTHETIC_CONFORMANCE_READY_BROKER_PARITY_BLOCKED",
            "contract": cfg["contract"]["shared_exit"],
            "unit_conformance": unit,
            "implementation_sha256": cfg["sources"]["parity_contract_implementation"]["sha256"],
        },
    ]
    return {
        "schema_version": 1,
        "materialization_id": cfg.get("materialization_id"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "permission": "BLOCKED_FAIL_CLOSED",
        "blockers": sorted(set(blockers)),
        "config_sha256": _canonical_sha(cfg),
        "sources": sources,
        "required_inputs": required_inputs,
        "component_receipts": component_receipts,
        "diagnostic_observed_schedule": _diagnostic_observed_schedule(cfg),
        "diagnostic_market_data_inventory": _diagnostic_market_inventory(cfg),
        "parent_preflight_current_state": parent_state,
        "performance_computed": False,
        "performance_fields_present": False,
        "outcome_access_allowed": False,
        "promotion_authorized": False,
        "live_or_broker_calls": False,
        "live_or_environment_writes": False,
        "safe_hold_changed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        config_path = args.config.resolve()
        output_path = args.output.resolve()
        config_path.relative_to(ROOT / "configs" / "preregistered")
        output_path.relative_to(ROOT / "reports" / "research")
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        receipt = build_receipt(cfg)
        _atomic_json(output_path, receipt)
    except (OSError, json.JSONDecodeError, MaterializationError, ParityContractError, ValueError) as exc:
        raise SystemExit(f"Alpaca exact-parity materialization refused: {exc}") from exc
    print(json.dumps({"output": str(output_path), "permission": receipt["permission"], "blockers": receipt["blockers"]}, sort_keys=True))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
