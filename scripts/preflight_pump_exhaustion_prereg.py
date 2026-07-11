#!/usr/bin/env python3
"""Strict cache/source preflight for pump-exhaustion research.

This command never evaluates PnL, contacts an exchange, changes live state, or
promotes a sleeve.  It only proves whether the already-frozen short-only
experiment has exact source code and immutable, quality-valid input snapshots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "preregistered" / "pump_exhaustion_unwind_short_v1_20260711.json"
DEFAULT_OUTPUT = ROOT / "reports" / "research" / "pump_exhaustion_unwind_short_v1_20260711_preflight.json"
SOURCE_PATHS = {
    "strategy_sha256": "strategies/pump_exhaustion_unwind_short_v1.py",
    "state_store_sha256": "bot/pump_exhaustion_state_store.py",
    "preflight_sha256": "scripts/preflight_pump_exhaustion_prereg.py",
}


class PreflightError(ValueError):
    """Frozen contract or filesystem input is unsafe to evaluate."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _repo_file(root: Path, raw: object) -> Path:
    text = str(raw or "")
    candidate = Path(text)
    if not text or candidate.is_absolute() or "\\" in text:
        raise PreflightError(f"artifact path must be repo-relative: {text!r}")
    parts = candidate.parts
    if not parts or any(part in {"", ".", ".."} for part in parts) or ".git" in parts:
        raise PreflightError(f"unsafe artifact path: {text!r}")
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PreflightError(f"artifact path contains a symlink: {text!r}")
    return cursor


def validate_frozen_contract(cfg: Mapping[str, Any]) -> None:
    required_true = ("research_only", "frozen_before_results", "no_parameter_scan")
    if not all(cfg.get(key) is True for key in required_true):
        raise PreflightError("experiment must be frozen research-only with no parameter scan")
    if cfg.get("live_or_broker_calls") is not False:
        raise PreflightError("live_or_broker_calls must be false")
    strategy = cfg.get("strategy")
    if not isinstance(strategy, Mapping):
        raise PreflightError("strategy contract is missing")
    if (
        strategy.get("id") != "pump_exhaustion_unwind_short_v1"
        or strategy.get("physical_side_identity") != "short_only"
        or strategy.get("signal_side") != "short"
        or strategy.get("live_ready") is not False
        or strategy.get("persisted_event_state_required") is not True
    ):
        raise PreflightError("strategy identity must remain physical short-only/research-only/persisted")

    execution = cfg.get("execution_contract")
    if not isinstance(execution, Mapping):
        raise PreflightError("execution contract is missing")
    if execution.get("entry") != "next_5m_open_after_closed_signal_bar":
        raise PreflightError("entry must be next-open after a closed signal bar")
    if execution.get("same_bar_fill_allowed") is not False:
        raise PreflightError("same-bar fills are forbidden")
    if execution.get("risk_pct") != 0:
        raise PreflightError("preflight experiment risk_pct must remain zero")
    for cost_name in ("base_costs_bps_per_side", "stress_costs_bps_per_side"):
        costs = execution.get(cost_name)
        if not isinstance(costs, Mapping):
            raise PreflightError(f"{cost_name} is missing")
        try:
            total = float(costs.get("fee")) + float(costs.get("slippage"))
        except (TypeError, ValueError) as exc:
            raise PreflightError(f"{cost_name} is invalid") from exc
        if total <= 0:
            raise PreflightError(f"{cost_name} must be adverse and positive")

    evaluation = cfg.get("evaluation_contract")
    if not isinstance(evaluation, Mapping):
        raise PreflightError("evaluation contract is missing")
    if (
        int(evaluation.get("chronological_folds", 0)) < 4
        or int(evaluation.get("embargo_bars", 0)) <= 0
        or int(evaluation.get("untouched_holdout_days", 0)) < 90
    ):
        raise PreflightError("folds, embargo and untouched holdout are mandatory")

    gate = cfg.get("research_pass_gate")
    if not isinstance(gate, Mapping):
        raise PreflightError("research pass gate is missing")
    if (
        float(gate.get("stress_pf_min", 0)) < 1.20
        or int(gate.get("min_trades", 0)) < 40
        or int(gate.get("positive_folds_min", 0)) < 3
        or int(gate.get("min_traded_symbols", 0)) < 3
        or int(gate.get("min_positive_symbols", 0)) < 2
        or float(gate.get("max_profit_concentration_pct", 100)) > 35
    ):
        raise PreflightError("research pass gates are weaker than project policy")

    data = cfg.get("data")
    if not isinstance(data, Mapping):
        raise PreflightError("data contract is missing")
    symbols = data.get("symbols")
    if not isinstance(symbols, list) or len(symbols) < 3 or len(symbols) != len(set(symbols)):
        raise PreflightError("data symbols must contain at least three unique entries")
    if not all(isinstance(symbol, str) and symbol.endswith("USDT") for symbol in symbols):
        raise PreflightError("data symbols must be canonical USDT symbols")
    start = int(data.get("window_start_ts", 0))
    end = int(data.get("window_end_ts_exclusive", 0))
    if start <= 0 or end <= start:
        raise PreflightError("data window is invalid")
    if int(data.get("interval_ms", 0)) != 300_000:
        raise PreflightError("pump prereg interval must remain five minutes")


def actual_source_hashes(root: Path) -> dict[str, str]:
    return {key: sha256_file(_repo_file(root, rel)) for key, rel in SOURCE_PATHS.items()}


def compute_state_source_fingerprint(
    cfg: Mapping[str, Any], source_hashes: Mapping[str, str]
) -> str:
    return _canonical_sha(
        {
            "strategy": cfg.get("strategy"),
            "source_code": dict(source_hashes),
            "data": cfg.get("data"),
            "execution_contract": cfg.get("execution_contract"),
            "evaluation_contract": cfg.get("evaluation_contract"),
            "research_pass_gate": cfg.get("research_pass_gate"),
        }
    )


def snapshot_status(root: Path, symbol: str, contract: object, data: Mapping[str, Any]) -> dict[str, Any]:
    base = {"symbol": symbol, "ok": False, "reasons": []}
    if not isinstance(contract, Mapping):
        base["reasons"] = ["snapshot_unpinned"]
        return base
    expected = str(contract.get("sha256") or "")
    try:
        path = _repo_file(root, contract.get("path"))
    except PreflightError as exc:
        base["reasons"] = [f"unsafe_path:{exc}"]
        return base
    base["path"] = str(path.relative_to(root))
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        base["reasons"] = ["snapshot_unpinned"]
        return base
    if not path.is_file():
        base["reasons"] = ["snapshot_missing"]
        return base
    actual = sha256_file(path)
    base["sha256"] = actual
    if actual != expected:
        base["reasons"] = ["snapshot_hash_mismatch"]
        return base
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        base["reasons"] = [f"snapshot_json_invalid:{type(exc).__name__}"]
        return base
    if not isinstance(payload, list):
        base["reasons"] = ["snapshot_rows_not_list"]
        return base

    start = int(data["window_start_ts"])
    end = int(data["window_end_ts_exclusive"])
    interval = int(data["interval_ms"])
    rows: list[tuple[int, float, float, float, float, float]] = []
    invalid = 0
    for raw in payload:
        try:
            ts = int(raw["ts"])
            o, h, l, c, v = (float(raw[key]) for key in ("o", "h", "l", "c", "v"))
        except (KeyError, TypeError, ValueError):
            invalid += 1
            continue
        if not all(math.isfinite(value) for value in (o, h, l, c, v)):
            invalid += 1
            continue
        if o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0 or h < max(o, c, l) or l > min(o, c, h):
            invalid += 1
            continue
        if start <= ts < end:
            rows.append((ts, o, h, l, c, v))
    timestamps = [row[0] for row in rows]
    duplicate_count = len(timestamps) - len(set(timestamps))
    ordered = timestamps == sorted(timestamps)
    max_gap_bars = 0
    if ordered and duplicate_count == 0:
        max_gap_bars = max(
            (max(0, (right - left) // interval - 1) for left, right in zip(timestamps, timestamps[1:])),
            default=0,
        )
    expected_rows = max(1, (end - start) // interval)
    coverage = len(rows) / expected_rows
    reasons: list[str] = []
    if invalid:
        reasons.append("invalid_rows")
    if duplicate_count:
        reasons.append("duplicate_timestamps")
    if not ordered:
        reasons.append("timestamps_not_sorted")
    if coverage < float(data["min_coverage"]):
        reasons.append("coverage_below_gate")
    if max_gap_bars > int(data["max_internal_gap_bars"]):
        reasons.append("gap_above_gate")
    base.update(
        {
            "rows": len(rows),
            "invalid_rows": invalid,
            "duplicate_timestamps": duplicate_count,
            "ordered": ordered,
            "coverage": coverage,
            "max_internal_gap_bars": max_gap_bars,
            "reasons": reasons,
            "ok": not reasons,
        }
    )
    return base


def evaluate_preflight(root: Path, cfg: Mapping[str, Any]) -> dict[str, Any]:
    validate_frozen_contract(cfg)
    actual_sources = actual_source_hashes(root)
    expected_sources = cfg.get("source_code") if isinstance(cfg.get("source_code"), Mapping) else {}
    source_mismatches = [
        key for key, actual in actual_sources.items() if str(expected_sources.get(key) or "") != actual
    ]
    expected_fingerprint = str(cfg.get("state_source_fingerprint") or "")
    actual_fingerprint = compute_state_source_fingerprint(cfg, actual_sources)
    fingerprint_ok = expected_fingerprint == actual_fingerprint

    data = cfg["data"]
    snapshots = data.get("input_snapshots") if isinstance(data.get("input_snapshots"), Mapping) else {}
    statuses = [snapshot_status(root, symbol, snapshots.get(symbol), data) for symbol in data["symbols"]]
    blockers: list[str] = []
    if source_mismatches:
        blockers.append("frozen_source_hash_mismatch")
    if not fingerprint_ok:
        blockers.append("state_source_fingerprint_mismatch")
    if not statuses or any(not row["ok"] for row in statuses):
        blockers.append("immutable_input_snapshots_not_ready")
    permission = "PERFORMANCE_RESEARCH_ALLOWED" if not blockers else "BLOCKED_FAIL_CLOSED"
    return {
        "schema_version": 1,
        "experiment": cfg.get("name"),
        "strategy": "pump_exhaustion_unwind_short_v1",
        "side_identity": "short_only",
        "permission": permission,
        "blockers": blockers,
        "source_mismatches": source_mismatches,
        "state_source_fingerprint_ok": fingerprint_ok,
        "snapshots": statuses,
        "performance_computed": False,
        "live_or_broker_calls": False,
        "promotion_authorized": False,
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.is_symlink():
        raise PreflightError("refusing output symlink")
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    output_path = args.output.resolve()
    try:
        output_path.relative_to(ROOT / "reports" / "research")
    except ValueError as exc:
        raise SystemExit("output must remain under reports/research") from exc
    if output_path.exists():
        raise SystemExit(f"refusing to overwrite evidence: {output_path}")
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        result = evaluate_preflight(ROOT, cfg)
        _atomic_json(output_path, result)
    except (OSError, json.JSONDecodeError, PreflightError) as exc:
        raise SystemExit(f"pump prereg preflight refused: {exc}") from exc
    print(json.dumps({"output": str(output_path), **result}, sort_keys=True))
    return 0 if result["permission"] == "PERFORMANCE_RESEARCH_ALLOWED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
