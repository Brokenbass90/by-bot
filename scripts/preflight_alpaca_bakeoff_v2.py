#!/usr/bin/env python3
"""Fail-closed preflight for the successor Alpaca monthly bake-off.

The preflight can verify a frozen arm design and a future forward seal.  It is
deliberately incapable of calculating returns, calling Alpaca, reading secrets,
changing SAFE_HOLD, or authorizing live orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.alpaca_bakeoff_v2_contract import (  # noqa: E402
    KNOWN_LEGACY_PARITY_GAPS,
    PAIRWISE_CONTRASTS,
    BakeoffContractError,
    expected_arms,
    validate_pairwise_contrasts,
)


DEFAULT_CONFIG = ROOT / "configs" / "preregistered" / "alpaca_bakeoff_v2_20260716.json"
DEFAULT_OUTPUT = (
    ROOT / "reports" / "research" / "alpaca_bakeoff_v2_20260716" / "preflight_receipt.json"
)

REQUIRED_INPUT_SCHEMAS = {
    "official_xnys_session_ledger": "xnys_session_ledger_v1",
    "point_in_time_universe": "alpaca_point_in_time_universe_v1",
    "point_in_time_market_data_manifest": "alpaca_point_in_time_market_data_manifest_v1",
    "corporate_actions_and_delistings": "alpaca_corporate_actions_delistings_v1",
    "broker_lifecycle_and_cost_calibration": "alpaca_broker_lifecycle_cost_bundle_v1",
}


class BakeoffPreflightError(ValueError):
    """The persisted research freeze is unsafe or internally inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _repo_file(raw: object) -> Path:
    text = str(raw or "")
    candidate = Path(text)
    if not text or candidate.is_absolute() or "\\" in text or ".." in candidate.parts:
        raise BakeoffPreflightError(f"path must be safe and repo-relative: {text!r}")
    path = ROOT
    for part in candidate.parts:
        path = path / part
        if path.is_symlink():
            raise BakeoffPreflightError(f"path contains symlink: {text!r}")
    return path


def _parse_utc(value: object, *, field: str) -> datetime:
    text = str(value or "")
    if not text.endswith("Z"):
        raise BakeoffPreflightError(f"{field} must end in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise BakeoffPreflightError(f"{field} is not ISO-8601") from exc
    if parsed.tzinfo != timezone.utc:
        raise BakeoffPreflightError(f"{field} must be UTC")
    return parsed


def _env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def validate_config(cfg: Mapping[str, Any]) -> None:
    if cfg.get("schema_version") != 2:
        raise BakeoffPreflightError("schema_version must remain 2")
    for key in (
        "research_only",
        "performance_forbidden_until_preflight_pass",
        "no_broker_calls",
        "no_live_writes",
        "safe_hold_must_remain",
        "no_parameter_scan",
    ):
        if cfg.get(key) is not True:
            raise BakeoffPreflightError(f"mandatory fail-closed flag changed: {key}")
    if cfg.get("risk_pct") != 0 or cfg.get("promotion_authority") is not False:
        raise BakeoffPreflightError("preflight must remain risk-zero without promotion authority")
    arms = expected_arms()
    expected_ids = [row["id"] for row in arms]
    if cfg.get("arm_contract") != "alpaca_bakeoff_v2_contract":
        raise BakeoffPreflightError("frozen arm contract id changed")
    if cfg.get("arm_ids") != expected_ids:
        raise BakeoffPreflightError("frozen arm ids changed")
    if cfg.get("pairwise_contrasts") != PAIRWISE_CONTRASTS:
        raise BakeoffPreflightError("pairwise contrast contract changed")
    try:
        validate_pairwise_contrasts(arms, cfg["pairwise_contrasts"])
    except BakeoffContractError as exc:
        raise BakeoffPreflightError(str(exc)) from exc
    if cfg.get("known_legacy_parity_gaps") != KNOWN_LEGACY_PARITY_GAPS:
        raise BakeoffPreflightError("known legacy parity gaps cannot be erased")
    sources = cfg.get("sources")
    if not isinstance(sources, Mapping) or not sources:
        raise BakeoffPreflightError("source pins are missing")
    for name, row in sources.items():
        if not name or not isinstance(row, Mapping) or set(row) != {"path", "sha256"}:
            raise BakeoffPreflightError("source pin shape invalid")
        if not _is_sha(row.get("sha256")):
            raise BakeoffPreflightError(f"source is unpinned: {name}")
        _repo_file(row.get("path"))
    inputs = cfg.get("required_inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != set(REQUIRED_INPUT_SCHEMAS):
        raise BakeoffPreflightError("required input set changed")
    for name, schema_id in REQUIRED_INPUT_SCHEMAS.items():
        row = inputs[name]
        if not isinstance(row, Mapping) or set(row) != {"schema_id", "path", "sha256"}:
            raise BakeoffPreflightError(f"input contract invalid: {name}")
        if row.get("schema_id") != schema_id:
            raise BakeoffPreflightError(f"input schema changed: {name}")
        if bool(row.get("path")) != bool(row.get("sha256")):
            raise BakeoffPreflightError(f"input path/hash must be pinned together: {name}")
        if row.get("sha256") and not _is_sha(row.get("sha256")):
            raise BakeoffPreflightError(f"input hash invalid: {name}")
    forward = cfg.get("untouched_forward_manifest")
    if not isinstance(forward, Mapping) or set(forward) != {"path", "sha256"}:
        raise BakeoffPreflightError("future forward manifest pin is missing")
    if not _is_sha(forward.get("sha256")):
        raise BakeoffPreflightError("future forward manifest is unpinned")


def _source_status(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, pin in cfg["sources"].items():
        path = _repo_file(pin["path"])
        actual = sha256_file(path) if path.is_file() else None
        rows.append(
            {
                "name": name,
                "path": pin["path"],
                "expected_sha256": pin["sha256"],
                "actual_sha256": actual,
                "ok": actual == pin["sha256"],
            }
        )
    return rows


def _future_status(cfg: Mapping[str, Any]) -> dict[str, Any]:
    pin = cfg["untouched_forward_manifest"]
    path = _repo_file(pin["path"])
    reasons: list[str] = []
    payload: dict[str, Any] = {}
    if not path.is_file():
        reasons.append("future_manifest_missing")
    elif sha256_file(path) != pin["sha256"]:
        reasons.append("future_manifest_hash_mismatch")
    else:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            payload = raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            reasons.append("future_manifest_unreadable")
    if payload:
        expected = {
            "schema_id": "alpaca_untouched_forward_manifest_v2",
            "outcomes_read_before_seal": False,
            "performance_embargo_until_window_complete": True,
            "parameters_frozen_for_window": True,
            "interim_reads_allowed": False,
            "promotion_authority": False,
            "risk_pct": 0,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            reasons.append("future_manifest_semantics_invalid")
        try:
            sealed = _parse_utc(payload.get("sealed_at_utc"), field="sealed_at_utc")
            start = _parse_utc(payload.get("window_start_utc"), field="window_start_utc")
            end = _parse_utc(payload.get("window_end_utc_exclusive"), field="window_end_utc_exclusive")
        except BakeoffPreflightError:
            reasons.append("future_manifest_dates_invalid")
        else:
            if not sealed < start < end:
                reasons.append("future_manifest_not_sealed_before_window")
        if payload.get("outcome_files") != []:
            reasons.append("future_manifest_contains_outcomes_at_seal")
        if int(payload.get("minimum_complete_monthly_entry_cycles") or 0) < 3:
            reasons.append("future_window_too_short")
    return {
        "path": pin["path"],
        "sha256": pin["sha256"],
        "ok": not reasons,
        "reasons": sorted(set(reasons)),
        "sealed_at_utc": payload.get("sealed_at_utc"),
        "window_start_utc": payload.get("window_start_utc"),
        "window_end_utc_exclusive": payload.get("window_end_utc_exclusive"),
        "minimum_complete_monthly_entry_cycles": payload.get("minimum_complete_monthly_entry_cycles"),
    }


def _safe_hold_status(cfg: Mapping[str, Any]) -> dict[str, Any]:
    path = _repo_file(cfg["safe_hold_env_path"])
    values = _env(path) if path.is_file() else {}
    expected = {
        "ALPACA_ALLOW_NEW_ENTRIES": "0",
        "ALPACA_CLOSE_STALE_POSITIONS": "0",
        "MONTHLY_MIDMONTH_ROTATION": "0",
    }
    mismatches = [key for key, value in expected.items() if values.get(key) != value]
    return {
        "path": cfg["safe_hold_env_path"],
        "ok": path.is_file() and not mismatches,
        "expected": expected,
        "mismatches": mismatches,
        "forced_liquidation_required_by_research": False,
        "safe_hold_changed": False,
    }


def _input_status(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, schema_id in REQUIRED_INPUT_SCHEMAS.items():
        pin = cfg["required_inputs"][name]
        reasons: list[str] = []
        if not pin["path"]:
            reasons.append("artifact_unpinned")
        else:
            path = _repo_file(pin["path"])
            if not path.is_file():
                reasons.append("artifact_missing")
            elif sha256_file(path) != pin["sha256"]:
                reasons.append("artifact_hash_mismatch")
            else:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    reasons.append("artifact_unreadable")
                else:
                    if not isinstance(payload, Mapping) or payload.get("schema_id") != schema_id:
                        reasons.append("artifact_schema_mismatch")
        rows.append(
            {
                "name": name,
                "schema_id": schema_id,
                "path": pin["path"],
                "sha256": pin["sha256"],
                "ok": not reasons,
                "reasons": reasons,
            }
        )
    return rows


def build_receipt(cfg: Mapping[str, Any]) -> dict[str, Any]:
    validate_config(cfg)
    sources = _source_status(cfg)
    forward = _future_status(cfg)
    safe_hold = _safe_hold_status(cfg)
    inputs = _input_status(cfg)
    blockers = [f"source:{row['name']}" for row in sources if not row["ok"]]
    blockers.extend(f"input:{row['name']}" for row in inputs if not row["ok"])
    if not forward["ok"]:
        blockers.append("untouched_forward_manifest")
    if not safe_hold["ok"]:
        blockers.append("safe_hold_overlay")
    return {
        "schema_version": 2,
        "bakeoff_id": cfg["bakeoff_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "permission": "REPLAY_IMPLEMENTATION_ALLOWED" if not blockers else "BLOCKED_FAIL_CLOSED",
        "performance_computed": False,
        "outcome_files_opened": False,
        "broker_or_network_calls": False,
        "live_writes": False,
        "promotion_authorized": False,
        "safe_hold": safe_hold,
        "sources": sources,
        "untouched_forward_manifest": forward,
        "required_inputs": inputs,
        "arms": expected_arms(),
        "pairwise_contrasts": cfg["pairwise_contrasts"],
        "known_legacy_parity_gaps": cfg["known_legacy_parity_gaps"],
        "blockers": sorted(set(blockers)),
        "next_allowed_action": (
            "implement_one_common_runner_without_reading_forward_outcomes"
            if not blockers
            else "pin_authoritative_inputs_then_rerun_preflight"
        ),
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise BakeoffPreflightError(f"refusing to overwrite immutable receipt: {path}")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    receipt = build_receipt(cfg)
    if args.stdout:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        _atomic_json(args.output, receipt)
        print(args.output)
    return 0 if receipt["permission"] == "REPLAY_IMPLEMENTATION_ALLOWED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
