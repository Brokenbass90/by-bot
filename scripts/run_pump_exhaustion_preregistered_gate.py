#!/usr/bin/env python3
"""Strict, fail-closed performance gate for the frozen pump-unwind experiment.

The command has two deliberately separate modes:

* ``--authorize-preflight-only`` verifies the frozen source fingerprint and the
  external immutable-snapshot manifest, then writes deterministic authorization
  evidence.  It never computes a signal or PnL.
* ``--run-performance`` recomputes that preflight and requires an exact match to
  the previously written evidence before it may load the strategy.  It remains
  research-only: no broker/network/live imports or writes are present.

Signals are evaluated from closed M5 bars.  Orders fill at the exact next M5
open, never the signal close.  The event stop remains frozen; 1R/2R targets are
anchored to the actual next-open fill.  A next open at/through the frozen stop is
an execution-integrity blocker rather than a silently skipped or fabricated
trade.  Later adverse stop gaps fill at the bar open.  Intrabar ambiguity is
always stop-first.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import os
import shutil
import sys
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preflight_pump_exhaustion_prereg import (  # noqa: E402
    PreflightError,
    actual_source_hashes,
    compute_state_source_fingerprint,
    sha256_file,
    snapshot_status,
    validate_frozen_contract,
)
from strategies.pump_exhaustion_unwind_short_v1 import (  # noqa: E402
    PumpExhaustionUnwindShortV1Strategy,
    PumpUnwindConfig,
    PumpUnwindShortPlan,
    SleeveState,
    TERMINAL_STAGES,
)


DEFAULT_CONFIG = (
    ROOT / "configs" / "preregistered" / "pump_exhaustion_unwind_short_v1_20260711.json"
)
DEFAULT_MANIFEST = (
    ROOT
    / "data_cache"
    / "immutable"
    / "pump_exhaustion_unwind_short_v1_720d_20260711"
    / "manifest.json"
)
DEFAULT_PREFLIGHT = (
    ROOT
    / "reports"
    / "research"
    / "pump_exhaustion_unwind_short_v1_20260713_performance_authorization.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "reports"
    / "research"
    / "pump_exhaustion_unwind_short_v1_20260713_strict_gate"
)
RUNNER_RELATIVE_PATH = "scripts/run_pump_exhaustion_preregistered_gate.py"
FROZEN_CONFIG_SHA256 = "601ee8fa02c19189f710ef0fd32f872a00959f29300d604347fbc09d79b34505"
RUNTIME_DEPENDENCY_PATHS = (
    "strategies/pump_exhaustion_unwind_short_v1.py",
    "bot/pump_exhaustion_state_store.py",
    "scripts/preflight_pump_exhaustion_prereg.py",
    "bot/inplay_volume_universe.py",
    "bot/market_context.py",
    "bot/pump_exhaustion.py",
    "bot/retest_quality.py",
    "bot/structure_break.py",
    "strategies/signals.py",
)
DAY_MS = 86_400_000
OHLCV_KEYS = ("ts", "o", "h", "l", "c", "v")


class ResearchGateError(ValueError):
    """The frozen performance contract cannot be evaluated safely."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ResearchGateError(f"input is not a regular file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchGateError(f"invalid JSON input {path}: {exc}") from exc


def _repo_relative(root: Path, path: Path) -> str:
    try:
        root_resolved = root.resolve(strict=True)
        absolute = path.absolute()
        relative = absolute.relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        raise ResearchGateError(f"path must be an existing repo file: {path}") from exc
    cursor = root_resolved
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ResearchGateError(f"repo input contains a symlink: {path}")
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as exc:
        raise ResearchGateError(f"path must be an existing repo file: {path}") from exc
    if resolved != absolute:
        raise ResearchGateError(f"repo input resolves through a symlink: {path}")
    if not relative.parts or ".git" in relative.parts:
        raise ResearchGateError(f"unsafe repo input: {path}")
    return relative.as_posix()


def _repo_path(root: Path, raw: object) -> Path:
    text = str(raw or "")
    candidate = Path(text)
    if (
        not text
        or candidate.is_absolute()
        or "\\" in text
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or ".git" in candidate.parts
    ):
        raise ResearchGateError(f"unsafe repo-relative path: {text!r}")
    cursor = root.resolve(strict=True)
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ResearchGateError(f"repo input contains a symlink: {text!r}")
    return cursor


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchGateError(f"{name} must be an object")
    return value


def _validate_manifest_contract(
    root: Path,
    cfg: Mapping[str, Any],
    config_path: Path,
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[dict[str, Any]], list[str]]:
    """Validate external pins without mutating the frozen preregistration."""
    blockers: list[str] = []
    data = _require_mapping(cfg.get("data"), "data")
    symbols = [str(item) for item in data.get("symbols", [])]
    expected_flags = {
        "kind": "pump_exhaustion_immutable_snapshot_manifest",
        "experiment": cfg.get("name"),
        "side_identity": "short_only",
        "network_calls": False,
        "live_state_changed": False,
        "config_edited": False,
        "performance_computed": False,
    }
    for key, expected in expected_flags.items():
        if manifest.get(key) != expected:
            blockers.append(f"manifest_{key}_mismatch")
    if int(manifest.get("schema_version", 0)) != 1:
        blockers.append("manifest_schema_mismatch")
    if int(manifest.get("interval_ms", 0)) != int(data.get("interval_ms", 0)):
        blockers.append("manifest_interval_mismatch")
    try:
        config_rel = _repo_relative(root, config_path)
    except ResearchGateError:
        config_rel = ""
        blockers.append("config_path_outside_repo")
    if manifest.get("config") != config_rel:
        blockers.append("manifest_config_path_mismatch")
    if str(manifest.get("config_sha256") or "") != sha256_file(config_path):
        blockers.append("manifest_config_hash_mismatch")

    # The original prereg remains byte-frozen with an empty pin map.  The
    # independently hashed materialization manifest is the only supplemental
    # pin authority accepted by this runner.
    if data.get("input_snapshots") != {}:
        blockers.append("frozen_config_snapshot_map_was_edited")
    raw_pins = manifest.get("input_snapshots")
    pins: dict[str, Mapping[str, Any]] = {}
    if not isinstance(raw_pins, Mapping) or set(raw_pins) != set(symbols):
        blockers.append("manifest_snapshot_symbol_set_mismatch")
    else:
        for symbol in symbols:
            pin = raw_pins.get(symbol)
            if not isinstance(pin, Mapping):
                blockers.append(f"manifest_pin_invalid:{symbol}")
            else:
                pins[symbol] = dict(pin)

    details = manifest.get("snapshots")
    if not isinstance(details, Mapping) or set(details) != set(symbols):
        blockers.append("manifest_snapshot_detail_set_mismatch")
        details = {}
    quality = manifest.get("quality_gate")
    expected_quality = {
        "min_coverage": float(data.get("min_coverage", 0.0)),
        "max_internal_gap_bars": int(data.get("max_internal_gap_bars", -1)),
    }
    if quality != expected_quality:
        blockers.append("manifest_quality_contract_mismatch")

    statuses: list[dict[str, Any]] = []
    for symbol in symbols:
        pin = pins.get(symbol)
        status = snapshot_status(root, symbol, pin, data)
        statuses.append(status)
        detail = details.get(symbol) if isinstance(details, Mapping) else None
        if not isinstance(detail, Mapping):
            blockers.append(f"manifest_snapshot_detail_invalid:{symbol}")
            continue
        if pin is None or any(
            str(detail.get(key) or "") != str(pin.get(key) or "") for key in ("path", "sha256")
        ):
            blockers.append(f"manifest_detail_pin_mismatch:{symbol}")
        if detail.get("quality_pass") is not True:
            blockers.append(f"manifest_quality_failed:{symbol}")
        if not status.get("ok"):
            blockers.append(f"snapshot_not_ready:{symbol}")
    return pins, statuses, sorted(set(blockers))


def _validate_runner_semantics(cfg: Mapping[str, Any]) -> None:
    """Reject any weakening of mechanics not covered by the legacy validator."""
    execution = _require_mapping(cfg.get("execution_contract"), "execution_contract")
    exact_execution = {
        "entry": "next_5m_open_after_closed_signal_bar",
        "same_bar_fill_allowed": False,
        "gap_policy": "adverse_next_open_fill_then_stop_target_path",
        "risk_pct": 0,
        "simulation_risk_pct": 0.005,
        "starting_equity": 100,
        "max_positions": 4,
        "cap_notional_usd": 30,
        "allocator": "off",
        "regime_router": "off",
        "broker_calls": False,
    }
    if any(execution.get(key) != expected for key, expected in exact_execution.items()):
        raise ResearchGateError("execution mechanics differ from the frozen contract")
    if execution.get("base_costs_bps_per_side") != {"fee": 6, "slippage": 2}:
        raise ResearchGateError("base costs differ from the frozen contract")
    if execution.get("stress_costs_bps_per_side") != {"fee": 10, "slippage": 5}:
        raise ResearchGateError("stress costs differ from the frozen contract")

    exit_contract = _require_mapping(cfg.get("exit_contract"), "exit_contract")
    exact_exit = {
        "stop": "frozen event peak plus 0.15 ATR",
        "tp1_rr": 1.0,
        "tp1_fraction": 0.5,
        "tp2_rr": 2.0,
        "remaining_fraction": 0.5,
        "max_hold_bars": 96,
        "ambiguous_same_bar_stop_target": "stop_first",
    }
    if any(exit_contract.get(key) != expected for key, expected in exact_exit.items()):
        raise ResearchGateError("exit mechanics differ from the frozen contract")

    evaluation = _require_mapping(cfg.get("evaluation_contract"), "evaluation_contract")
    exact_evaluation = {
        "chronological_folds": 4,
        "embargo_bars": 2016,
        "untouched_holdout_days": 120,
        "symbol_loso_required": True,
        "timestamp_portfolio_occupancy": True,
        "event_id_duplicates_allowed": 0,
        "plan_id_duplicates_allowed": 0,
    }
    if any(evaluation.get(key) != expected for key, expected in exact_evaluation.items()):
        raise ResearchGateError("evaluation mechanics differ from the frozen contract")


def build_preflight_evidence(
    root: Path,
    config_path: Path,
    manifest_path: Path,
    *,
    runner_path: Path | None = None,
    expected_config_sha256: str | None = FROZEN_CONFIG_SHA256,
) -> dict[str, Any]:
    """Build deterministic, hash-bound authorization evidence (no performance)."""
    runner_path = runner_path or root / RUNNER_RELATIVE_PATH
    cfg = _require_mapping(_read_json(config_path), "preregistration")
    manifest = _require_mapping(_read_json(manifest_path), "snapshot manifest")
    try:
        validate_frozen_contract(cfg)
    except PreflightError as exc:
        raise ResearchGateError(f"frozen contract invalid: {exc}") from exc
    _validate_runner_semantics(cfg)

    actual_sources = actual_source_hashes(root)
    expected_sources = _require_mapping(cfg.get("source_code"), "source_code")
    source_mismatches = sorted(
        key
        for key, actual in actual_sources.items()
        if str(expected_sources.get(key) or "") != actual
    )
    fingerprint = compute_state_source_fingerprint(cfg, actual_sources)
    fingerprint_ok = fingerprint == str(cfg.get("state_source_fingerprint") or "")
    _, statuses, blockers = _validate_manifest_contract(
        root, cfg, config_path, manifest
    )
    blockers = list(blockers)
    if expected_config_sha256 is not None and sha256_file(config_path) != expected_config_sha256:
        blockers.append("known_frozen_config_hash_mismatch")
    if source_mismatches:
        blockers.append("frozen_source_hash_mismatch")
    if not fingerprint_ok:
        blockers.append("state_source_fingerprint_mismatch")
    try:
        runner_rel = _repo_relative(root, runner_path)
        runner_sha = sha256_file(runner_path)
    except (OSError, ResearchGateError):
        runner_rel = RUNNER_RELATIVE_PATH
        runner_sha = ""
        blockers.append("runner_source_unavailable")
    runtime_dependencies: dict[str, str] = {}
    for relative in RUNTIME_DEPENDENCY_PATHS:
        try:
            dependency = _repo_path(root, relative)
            if not dependency.is_file():
                raise ResearchGateError(f"runtime dependency is not a file: {relative}")
            runtime_dependencies[relative] = sha256_file(dependency)
        except (OSError, ResearchGateError):
            blockers.append(f"runtime_dependency_unavailable:{relative}")

    config_rel = _repo_relative(root, config_path)
    manifest_rel = _repo_relative(root, manifest_path)
    blockers = sorted(set(blockers))
    return {
        "schema_version": 1,
        "kind": "pump_exhaustion_performance_authorization",
        "experiment": cfg.get("name"),
        "strategy": "pump_exhaustion_unwind_short_v1",
        "side_identity": "short_only",
        "permission": "PERFORMANCE_RESEARCH_ALLOWED" if not blockers else "BLOCKED_FAIL_CLOSED",
        "blockers": blockers,
        "config": {"path": config_rel, "sha256": sha256_file(config_path)},
        "immutable_manifest": {
            "path": manifest_rel,
            "sha256": sha256_file(manifest_path),
        },
        "runner": {"path": runner_rel, "sha256": runner_sha},
        "runtime_dependency_hashes": runtime_dependencies,
        "frozen_source_hashes": actual_sources,
        "source_mismatches": source_mismatches,
        "state_source_fingerprint": fingerprint,
        "state_source_fingerprint_ok": fingerprint_ok,
        "snapshots": statuses,
        "performance_computed": False,
        "network_calls": False,
        "live_or_broker_calls": False,
        "live_state_changed": False,
        "promotion_authorized": False,
    }


def verify_preflight_evidence(expected: Mapping[str, Any], path: Path) -> None:
    actual = _require_mapping(_read_json(path), "preflight evidence")
    if actual.get("permission") != "PERFORMANCE_RESEARCH_ALLOWED":
        raise ResearchGateError("preflight evidence is not successful")
    if expected.get("permission") != "PERFORMANCE_RESEARCH_ALLOWED":
        raise ResearchGateError("fresh preflight is blocked")
    if dict(actual) != dict(expected):
        raise ResearchGateError("preflight evidence is stale or not bound to current hashes")


def _atomic_json(path: Path, payload: Any) -> None:
    if path.exists() or path.is_symlink():
        raise ResearchGateError(f"refusing to overwrite: {path}")
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


def _number(value: Any, name: str, index: int) -> float:
    if isinstance(value, bool):
        raise ResearchGateError(f"boolean {name} in snapshot row {index}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ResearchGateError(f"non-numeric {name} in snapshot row {index}") from exc
    if not math.isfinite(result):
        raise ResearchGateError(f"non-finite {name} in snapshot row {index}")
    return result


def load_snapshot_rows(
    root: Path,
    pin: Mapping[str, Any],
    data: Mapping[str, Any],
) -> list[list[float]]:
    """Load one already-hash-verified canonical snapshot, fail closed again."""
    path = _repo_path(root, pin.get("path"))
    if sha256_file(path) != str(pin.get("sha256") or ""):
        raise ResearchGateError(f"snapshot changed after preflight: {path}")
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise ResearchGateError(f"snapshot is not an array: {path}")
    start = int(data["window_start_ts"])
    end = int(data["window_end_ts_exclusive"])
    interval = int(data["interval_ms"])
    rows: list[list[float]] = []
    previous = -1
    for index, raw in enumerate(payload):
        if not isinstance(raw, Mapping) or any(key not in raw for key in OHLCV_KEYS):
            raise ResearchGateError(f"non-canonical snapshot row {index}: {path}")
        ts_raw = raw["ts"]
        if isinstance(ts_raw, bool):
            raise ResearchGateError(f"boolean timestamp in snapshot row {index}")
        try:
            ts_float = float(ts_raw)
            ts = int(ts_raw)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ResearchGateError(f"invalid timestamp in snapshot row {index}") from exc
        if not math.isfinite(ts_float) or ts_float != ts:
            raise ResearchGateError(f"inexact timestamp in snapshot row {index}")
        o, h, l, c, v = (_number(raw[key], key, index) for key in OHLCV_KEYS[1:])
        if not (start <= ts < end) or (ts - start) % interval:
            raise ResearchGateError(f"timestamp outside frozen grid in row {index}")
        if ts <= previous:
            raise ResearchGateError(f"snapshot timestamp duplicate/order failure in row {index}")
        if not (o > 0 and h > 0 and l > 0 and c > 0 and v >= 0):
            raise ResearchGateError(f"invalid OHLCV sign in row {index}")
        if h < max(o, l, c) or l > min(o, h, c):
            raise ResearchGateError(f"OHLC invariant failed in row {index}")
        rows.append([float(ts), o, h, l, c, v])
        previous = ts
    return rows


def plan_id(plan: PumpUnwindShortPlan) -> str:
    return hashlib.sha256(_canonical_bytes(asdict(plan))).hexdigest()[:32]


def execute_short_plan(
    plan: PumpUnwindShortPlan,
    rows: Sequence[Sequence[float]],
    *,
    interval_ms: int,
    max_hold_bars: int,
    index_by_ts: Mapping[int, int] | None = None,
) -> dict[str, Any]:
    """Execute one frozen short plan using a causal, next-open OHLC path."""
    pid = plan_id(plan)
    base: dict[str, Any] = {
        "plan_id": pid,
        "event_id": plan.event_id,
        "strategy": plan.strategy,
        "symbol": plan.symbol,
        "side": plan.side,
        "signal_ts": int(plan.signal_ts),
        "valid_from_ts": int(plan.valid_from_ts),
        "plan_entry_reference": float(plan.entry_reference),
        "plan_stop": float(plan.stop),
        "plan_target_1": float(plan.target_1),
        "plan_target_2": float(plan.target_2),
    }
    if plan.side != "short" or plan.strategy != "pump_exhaustion_unwind_short_v1":
        return {**base, "status": "invalid_side_or_strategy"}
    if plan.valid_from_ts != plan.signal_ts + interval_ms:
        return {**base, "status": "invalid_next_open_timestamp"}
    if max_hold_bars <= 0:
        return {**base, "status": "invalid_max_hold"}
    if index_by_ts is None:
        index_by_ts = {int(row[0]): index for index, row in enumerate(rows)}
    entry_index = index_by_ts.get(int(plan.valid_from_ts))
    if entry_index is None:
        return {**base, "status": "missing_exact_next_open"}
    entry_row = rows[entry_index]
    entry = float(entry_row[1])
    stop = float(plan.stop)
    if not math.isfinite(entry) or entry <= 0 or entry >= stop:
        return {
            **base,
            "status": "invalid_adverse_gap_through_stop",
            "entry_ts": int(plan.valid_from_ts),
            "entry": entry,
        }
    risk = stop - entry
    target_1 = entry - risk
    target_2 = entry - 2.0 * risk
    if target_2 <= 0:
        return {
            **base,
            "status": "invalid_actual_fill_geometry",
            "entry_ts": int(plan.valid_from_ts),
            "entry": entry,
            "risk": risk,
        }

    realized_r = 0.0
    remaining = 1.0
    tp1_done = False
    mae_r = 0.0
    mae_ts = int(plan.valid_from_ts)
    exit_legs: list[dict[str, Any]] = []
    last_index = min(len(rows) - 1, entry_index + max_hold_bars - 1)
    expected_ts = int(plan.valid_from_ts)
    for offset, index in enumerate(range(entry_index, last_index + 1), start=1):
        row = rows[index]
        ts = int(row[0])
        if ts != expected_ts:
            return {
                **base,
                "status": "censored_internal_gap",
                "entry_ts": int(plan.valid_from_ts),
                "gap_expected_ts": expected_ts,
                "gap_actual_ts": ts,
            }
        expected_ts += interval_ms
        open_, high, low, close = (float(row[position]) for position in range(1, 5))
        open_position_r = realized_r + remaining * ((entry - high) / risk)
        if open_position_r < mae_r:
            mae_r = open_position_r
            mae_ts = ts

        # Stop is evaluated first on every ambiguous OHLC bar.  A gap through
        # stop exits at the adverse open rather than the ideal stop price.
        if high >= stop:
            stop_fill = max(open_, stop)
            leg_r = (entry - stop_fill) / risk
            realized_r += remaining * leg_r
            if realized_r < mae_r:
                mae_r = realized_r
                mae_ts = ts
            exit_legs.append(
                {"fraction": remaining, "price": stop_fill, "reason": "stop", "r": leg_r}
            )
            return {
                **base,
                "status": "filled_closed",
                "entry_ts": int(plan.valid_from_ts),
                "exit_ts": ts,
                "entry": entry,
                "stop": stop,
                "target_1": target_1,
                "target_2": target_2,
                "risk": risk,
                "risk_fraction": risk / entry,
                "bars_held": offset,
                "gross_r": realized_r,
                "mae_r": mae_r,
                "mae_ts": mae_ts,
                "exit_reason": "stop" if not tp1_done else "tp1_then_stop",
                "exit_legs": exit_legs,
            }

        if not tp1_done and low <= target_2:
            exit_legs.extend(
                (
                    {"fraction": 0.5, "price": target_1, "reason": "tp1", "r": 1.0},
                    {"fraction": 0.5, "price": target_2, "reason": "tp2", "r": 2.0},
                )
            )
            realized_r += 1.5
            return {
                **base,
                "status": "filled_closed",
                "entry_ts": int(plan.valid_from_ts),
                "exit_ts": ts,
                "entry": entry,
                "stop": stop,
                "target_1": target_1,
                "target_2": target_2,
                "risk": risk,
                "risk_fraction": risk / entry,
                "bars_held": offset,
                "gross_r": realized_r,
                "mae_r": mae_r,
                "mae_ts": mae_ts,
                "exit_reason": "tp1_tp2",
                "exit_legs": exit_legs,
            }
        if not tp1_done and low <= target_1:
            tp1_done = True
            remaining = 0.5
            realized_r += 0.5
            exit_legs.append(
                {"fraction": 0.5, "price": target_1, "reason": "tp1", "r": 1.0}
            )
        elif tp1_done and low <= target_2:
            realized_r += 1.0
            exit_legs.append(
                {"fraction": 0.5, "price": target_2, "reason": "tp2", "r": 2.0}
            )
            return {
                **base,
                "status": "filled_closed",
                "entry_ts": int(plan.valid_from_ts),
                "exit_ts": ts,
                "entry": entry,
                "stop": stop,
                "target_1": target_1,
                "target_2": target_2,
                "risk": risk,
                "risk_fraction": risk / entry,
                "bars_held": offset,
                "gross_r": realized_r,
                "mae_r": mae_r,
                "mae_ts": mae_ts,
                "exit_reason": "tp1_tp2",
                "exit_legs": exit_legs,
            }

        if offset == max_hold_bars:
            leg_r = (entry - close) / risk
            realized_r += remaining * leg_r
            if realized_r < mae_r:
                mae_r = realized_r
                mae_ts = ts
            exit_legs.append(
                {"fraction": remaining, "price": close, "reason": "max_hold", "r": leg_r}
            )
            return {
                **base,
                "status": "filled_closed",
                "entry_ts": int(plan.valid_from_ts),
                "exit_ts": ts,
                "entry": entry,
                "stop": stop,
                "target_1": target_1,
                "target_2": target_2,
                "risk": risk,
                "risk_fraction": risk / entry,
                "bars_held": offset,
                "gross_r": realized_r,
                "mae_r": mae_r,
                "mae_ts": mae_ts,
                "exit_reason": "max_hold" if not tp1_done else "tp1_then_max_hold",
                "exit_legs": exit_legs,
            }

    return {
        **base,
        "status": "censored_snapshot_end",
        "entry_ts": int(plan.valid_from_ts),
        "available_bars": max(0, last_index - entry_index + 1),
    }


def apply_costs(outcome: Mapping[str, Any], costs: Mapping[str, Any]) -> dict[str, Any]:
    if outcome.get("status") != "filled_closed":
        raise ResearchGateError("costs may only be applied to closed fills")
    per_side_bps = float(costs["fee"]) + float(costs["slippage"])
    if per_side_bps <= 0:
        raise ResearchGateError("costs must be adverse and positive")
    weighted_exit = sum(
        float(leg["fraction"]) * float(leg["price"])
        for leg in outcome.get("exit_legs", [])
    )
    cost_r = per_side_bps / 10_000.0 * (
        float(outcome["entry"]) + weighted_exit
    ) / float(outcome["risk"])
    return {
        **dict(outcome),
        "cost_bps_per_side": per_side_bps,
        "cost_r": cost_r,
        "net_r": float(outcome["gross_r"]) - cost_r,
        "mae_net_r": float(outcome.get("mae_r", outcome["gross_r"])) - cost_r,
    }


def _expansion_price_prefilter(
    rows: Sequence[Sequence[float]],
    index: int,
    segment_start: int,
    cfg: PumpUnwindConfig,
) -> bool:
    """Cheap necessary-only subset of ``detect_expansion_event``.

    Returning false is guaranteed to mean the frozen detector would also return
    no event; volume and level conditions are intentionally not duplicated.
    This avoids constructing a 145-row detector window on ordinary M5 bars.
    """
    need = max(
        cfg.level_lookback + 1,
        cfg.volume_recent_bars + cfg.volume_baseline_bars,
        cfg.expansion_lookback_bars + 2,
        cfg.atr_period + 3,
    )
    if index - segment_start + 1 < need:
        return False
    event = rows[index]
    o, h, l, c = (float(event[position]) for position in range(1, 5))
    if c <= o:
        return False
    base_price = float(rows[index - int(cfg.expansion_lookback_bars)][4])
    if (c - base_price) / max(1e-12, base_price) < float(cfg.min_expansion_pct):
        return False
    bar_range = h - l
    if abs(c - o) / max(1e-12, bar_range) < float(cfg.min_event_body_frac):
        return False
    true_ranges: list[float] = []
    first = max(segment_start + 1, index - int(cfg.atr_period))
    for cursor in range(first, index):
        row = rows[cursor]
        high = float(row[2])
        low = float(row[3])
        prior_close = float(rows[cursor - 1][4])
        true_ranges.append(max(high - low, abs(high - prior_close), abs(low - prior_close)))
    if not true_ranges:
        return False
    atr_value = sum(true_ranges[-int(cfg.atr_period) :]) / len(
        true_ranges[-int(cfg.atr_period) :]
    )
    return bool(
        math.isfinite(atr_value)
        and atr_value > 0
        and bar_range / atr_value >= float(cfg.min_event_range_atr)
    )


def generate_symbol_result(
    symbol: str,
    pin: Mapping[str, Any],
    cfg: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    """Run causal signal generation and gross path execution for one symbol."""
    data = _require_mapping(cfg.get("data"), "data")
    strategy_cfg = PumpUnwindConfig(**dict(_require_mapping(cfg["strategy"]["parameters"], "parameters")))
    rows = load_snapshot_rows(root, pin, data)
    interval = int(data["interval_ms"])
    index_by_ts = {int(row[0]): index for index, row in enumerate(rows)}
    strategy = PumpExhaustionUnwindShortV1Strategy(strategy_cfg)
    segment_start = 0
    continuity_resets = 0
    reasons: Counter[str] = Counter()
    created_events: list[str] = []
    emitted_plans: list[str] = []
    event_seen_global: set[str] = set()
    plan_seen_global: set[str] = set()
    duplicate_events: list[str] = []
    duplicate_plans: list[str] = []
    candidates: list[dict[str, Any]] = []
    previous_ts: int | None = None
    max_hold = int(cfg["exit_contract"]["max_hold_bars"])

    for index, row in enumerate(rows):
        ts = int(row[0])
        if previous_ts is not None and ts != previous_ts + interval:
            continuity_resets += 1
            segment_start = index
            strategy._states[symbol] = SleeveState()  # deterministic fail-closed reset
        previous_ts = ts
        prior = strategy._states.get(symbol, SleeveState())
        active_nonterminal = bool(
            prior.active is not None and prior.active.stage not in TERMINAL_STAGES
        )
        if not active_nonterminal and not _expansion_price_prefilter(
            rows, index, segment_start, strategy_cfg
        ):
            reasons["necessary_price_prefilter_no_expansion"] += 1
            continue
        detection_need = max(
            strategy_cfg.level_lookback + 1,
            strategy_cfg.volume_recent_bars + strategy_cfg.volume_baseline_bars,
            strategy_cfg.expansion_lookback_bars + 2,
            strategy_cfg.atr_period + 3,
        )
        history = int(strategy_cfg.history_limit) if active_nonterminal else int(detection_need)
        start = max(segment_start, index - history + 1)
        plan = strategy.process_closed_rows(symbol, rows[start : index + 1])
        reasons[str(strategy.last_no_signal_reason or "unknown")] += 1
        current = strategy._states.get(symbol, SleeveState())
        prior_ids = set(prior.seen_event_ids)
        for event_id in current.seen_event_ids:
            if event_id in prior_ids:
                continue
            created_events.append(event_id)
            if event_id in event_seen_global:
                duplicate_events.append(event_id)
            else:
                event_seen_global.add(event_id)
        if plan is None:
            continue
        pid = plan_id(plan)
        emitted_plans.append(pid)
        if pid in plan_seen_global:
            duplicate_plans.append(pid)
            continue
        plan_seen_global.add(pid)
        candidates.append(
            execute_short_plan(
                plan,
                rows,
                interval_ms=interval,
                max_hold_bars=max_hold,
                index_by_ts=index_by_ts,
            )
        )

    return {
        "symbol": symbol,
        "rows": len(rows),
        "first_ts": int(rows[0][0]) if rows else None,
        "last_ts": int(rows[-1][0]) if rows else None,
        "continuity_resets": continuity_resets,
        "event_ids": created_events,
        "plan_ids": emitted_plans,
        "duplicate_event_ids": duplicate_events,
        "duplicate_plan_ids": duplicate_plans,
        "reason_counts": dict(sorted(reasons.items())),
        "candidates": candidates,
    }


def _verify_runtime_pins(
    root: Path,
    dependency_hashes: Mapping[str, Any],
    runner_pin: Mapping[str, Any],
) -> None:
    if set(dependency_hashes) != set(RUNTIME_DEPENDENCY_PATHS):
        raise ResearchGateError("runtime dependency pin set is incomplete")
    for relative in RUNTIME_DEPENDENCY_PATHS:
        path = _repo_path(root, relative)
        if not path.is_file() or sha256_file(path) != str(dependency_hashes[relative]):
            raise ResearchGateError(f"runtime dependency changed after authorization: {relative}")
    runner_path = _repo_path(root, runner_pin.get("path"))
    if (
        runner_pin.get("path") != RUNNER_RELATIVE_PATH
        or not runner_path.is_file()
        or sha256_file(runner_path) != str(runner_pin.get("sha256") or "")
    ):
        raise ResearchGateError("runner changed after authorization")


def _symbol_job(
    args: tuple[
        str,
        Mapping[str, Any],
        Mapping[str, Any],
        str,
        Mapping[str, Any],
        Mapping[str, Any],
    ]
) -> dict[str, Any]:
    symbol, pin, cfg, root_text, dependency_hashes, runner_pin = args
    root = Path(root_text)
    _verify_runtime_pins(root, dependency_hashes, runner_pin)
    return generate_symbol_result(symbol, pin, cfg, root)


def generate_all_symbols(
    root: Path,
    cfg: Mapping[str, Any],
    pins: Mapping[str, Mapping[str, Any]],
    preflight: Mapping[str, Any],
    *,
    workers: int = 1,
) -> list[dict[str, Any]]:
    symbols = [str(symbol) for symbol in cfg["data"]["symbols"]]
    dependency_hashes = _require_mapping(
        preflight.get("runtime_dependency_hashes"), "runtime_dependency_hashes"
    )
    runner_pin = _require_mapping(preflight.get("runner"), "runner")
    jobs = [
        (
            symbol,
            dict(pins[symbol]),
            dict(cfg),
            str(root),
            dict(dependency_hashes),
            dict(runner_pin),
        )
        for symbol in symbols
    ]
    if workers <= 1:
        return [_symbol_job(job) for job in jobs]
    with ProcessPoolExecutor(max_workers=min(int(workers), len(jobs))) as pool:
        return list(pool.map(_symbol_job, jobs))


def apply_portfolio_occupancy(
    candidates: Sequence[Mapping[str, Any]],
    *,
    max_positions: int,
    excluded_symbols: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    if max_positions <= 0:
        raise ResearchGateError("max_positions must be positive")
    excluded = {str(symbol) for symbol in excluded_symbols}
    valid = [
        dict(row)
        for row in candidates
        if row.get("status") == "filled_closed" and str(row.get("symbol")) not in excluded
    ]
    valid.sort(key=lambda row: (int(row["entry_ts"]), str(row["symbol"]), str(row["plan_id"])))
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    active: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for candidate in valid:
        entry_ts = int(candidate["entry_ts"])
        # An exit on the same OHLC timestamp happens after that bar's open, so
        # it still consumes a slot for simultaneous next-open entries.
        active = [row for row in active if int(row["exit_ts"]) >= entry_ts]
        if any(str(row["symbol"]) == str(candidate["symbol"]) for row in active):
            rejected.append({**candidate, "portfolio_status": "rejected_symbol_busy"})
            counters["rejected_symbol_busy"] += 1
            continue
        if len(active) >= max_positions:
            rejected.append({**candidate, "portfolio_status": "rejected_capacity"})
            counters["rejected_capacity"] += 1
            continue
        accepted_row = {**candidate, "portfolio_status": "accepted"}
        accepted.append(accepted_row)
        active.append(accepted_row)
        counters["accepted"] += 1
    counters["closed_candidates"] = len(valid)
    return accepted, rejected, dict(sorted(counters.items()))


def _profit_factor(values: Sequence[float]) -> float:
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    if gross_loss > 0:
        return gross_profit / gross_loss
    return math.inf if gross_profit > 0 else 0.0


def summarize_trades(
    trades: Sequence[Mapping[str, Any]],
    *,
    r_key: str = "net_r",
) -> dict[str, Any]:
    ordered = sorted(
        trades,
        key=lambda row: (int(row["exit_ts"]), str(row["symbol"]), str(row["plan_id"])),
    )
    values = [float(row[r_key]) for row in ordered]
    cumulative = peak = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return {
        "trades": len(values),
        "wins": sum(value > 0 for value in values),
        "losses": sum(value < 0 for value in values),
        "win_rate_pct": 100.0 * sum(value > 0 for value in values) / len(values) if values else 0.0,
        "net_r": sum(values),
        "profit_factor": _profit_factor(values),
        "max_drawdown_r": max_dd,
        "average_r": sum(values) / len(values) if values else 0.0,
    }


def apply_scenario(
    trades: Sequence[Mapping[str, Any]],
    costs: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [apply_costs(row, costs) for row in trades]


def simulate_equity(
    trades: Sequence[Mapping[str, Any]],
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    """Exit-realized equity with timestamp occupancy and frozen sizing rules."""
    starting = float(execution["starting_equity"])
    risk_pct = float(execution["simulation_risk_pct"])
    cap_notional = float(execution["cap_notional_usd"])
    if starting <= 0 or not (0 < risk_pct <= 1) or cap_notional <= 0:
        raise ResearchGateError("invalid simulation sizing contract")
    ordered = sorted(
        (dict(row) for row in trades),
        key=lambda row: (int(row["entry_ts"]), str(row["symbol"]), str(row["plan_id"])),
    )
    equity = starting
    peak = starting
    max_dd_pct = 0.0
    pending: list[tuple[int, str, str, int, dict[str, Any]]] = []
    settled: list[dict[str, Any]] = []
    sequence = 0

    def settle_until(timestamp: int | None) -> None:
        nonlocal equity, peak, max_dd_pct
        while pending and (timestamp is None or pending[0][0] < timestamp):
            _, _, _, _, trade = heapq.heappop(pending)
            before = equity
            pnl = float(trade["risk_usd"]) * float(trade["net_r"])
            equity += pnl
            peak = max(peak, equity)
            if peak > 0:
                max_dd_pct = max(max_dd_pct, 100.0 * (peak - equity) / peak)
            settled.append(
                {
                    **trade,
                    "pnl_usd": pnl,
                    "equity_before_exit": before,
                    "equity_after_exit": equity,
                }
            )

    for trade in ordered:
        entry_ts = int(trade["entry_ts"])
        settle_until(entry_ts)
        desired_risk = max(0.0, equity) * risk_pct
        risk_fraction = float(trade["risk_fraction"])
        actual_risk = min(desired_risk, cap_notional * risk_fraction)
        notional = actual_risk / risk_fraction if risk_fraction > 0 else 0.0
        sized = {
            **trade,
            "risk_usd": actual_risk,
            "notional_usd": notional,
            "entry_equity_basis": equity,
        }
        heapq.heappush(
            pending,
            (
                int(trade["exit_ts"]),
                str(trade["symbol"]),
                str(trade["plan_id"]),
                sequence,
                sized,
            ),
        )
        sequence += 1
    settle_until(None)
    settled.sort(
        key=lambda row: (int(row["exit_ts"]), str(row["symbol"]), str(row["plan_id"])),
    )
    # OHLC cannot reconstruct a tick-level portfolio equity curve.  For the
    # promotion gate we therefore use a deliberately conservative bound: at
    # every entry/exit timestamp all concurrently open positions are marked to
    # each trade's individually observed worst causal M5 high (plus full costs),
    # even when those individual MAEs occurred at different instants.  This can
    # overstate, but cannot disguise, overlapping adverse exposure.
    timestamps = sorted(
        {int(row["entry_ts"]) for row in settled}
        | {int(row["exit_ts"]) for row in settled}
        | {int(row.get("mae_ts", row["entry_ts"])) for row in settled}
    )
    realized_equity = starting
    adverse_peak = starting
    conservative_dd_pct = 0.0
    exits = sorted(
        settled,
        key=lambda row: (int(row["exit_ts"]), str(row["symbol"]), str(row["plan_id"])),
    )
    exit_cursor = 0
    for timestamp in timestamps:
        while exit_cursor < len(exits) and int(exits[exit_cursor]["exit_ts"]) < timestamp:
            realized_equity += float(exits[exit_cursor]["pnl_usd"])
            exit_cursor += 1
        adverse_peak = max(adverse_peak, realized_equity)
        simultaneous_adverse = sum(
            min(0.0, float(row["risk_usd"]) * float(row.get("mae_net_r", row["net_r"])))
            for row in settled
            if int(row["entry_ts"]) <= timestamp <= int(row["exit_ts"])
        )
        adverse_equity = realized_equity + simultaneous_adverse
        if adverse_peak > 0:
            conservative_dd_pct = max(
                conservative_dd_pct,
                100.0 * (adverse_peak - adverse_equity) / adverse_peak,
            )
    conservative_dd_pct = max(conservative_dd_pct, max_dd_pct)
    return {
        "starting_equity": starting,
        "ending_equity": equity,
        "return_pct": 100.0 * (equity / starting - 1.0),
        "max_drawdown_pct": conservative_dd_pct,
        "exit_realized_max_drawdown_pct": max_dd_pct,
        "conservative_overlap_mae_max_drawdown_pct": conservative_dd_pct,
        "drawdown_gate_basis": "max(exit_realized, conservative_simultaneous_overlap_MAE_bound)",
        "sizing": "closed_equity_fixed_fraction_capped_notional",
        "mark_to_market": False,
        "settled_trades": settled,
    }


def fixed_development_folds(
    trades: Sequence[Mapping[str, Any]],
    data: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int], int]:
    end = int(data["window_end_ts_exclusive"])
    holdout_start = end - int(evaluation["untouched_holdout_days"]) * DAY_MS
    start = int(data["window_start_ts"])
    n_folds = int(evaluation["chronological_folds"])
    embargo = int(evaluation["embargo_bars"]) * int(data["interval_ms"])
    span = holdout_start - start
    if span <= 0 or span % n_folds:
        raise ResearchGateError("development window cannot be split into fixed folds")
    edges = [start + index * (span // n_folds) for index in range(n_folds + 1)]
    folds: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    purged = embargoed = 0
    for index, (lo, hi) in enumerate(zip(edges, edges[1:]), start=1):
        selected: list[Mapping[str, Any]] = []
        for trade in trades:
            entry = int(trade["entry_ts"])
            exit_ts = int(trade["exit_ts"])
            if not (lo <= entry < hi):
                continue
            if exit_ts >= hi:
                purged += 1
                continue
            if entry < lo + embargo:
                embargoed += 1
                continue
            selected.append(trade)
            used_ids.add(str(trade["plan_id"]))
        folds.append(
            {
                "fold": index,
                "start_ts": lo,
                "end_ts_exclusive": hi,
                "embargo_start_ts": lo + embargo,
                **summarize_trades(selected),
            }
        )
    dev_entries = sum(
        int(data["window_start_ts"]) <= int(row["entry_ts"]) < holdout_start
        for row in trades
    )
    diagnostics = {
        "development_entries": dev_entries,
        "used": len(used_ids),
        "purged_boundary": purged,
        "embargoed": embargoed,
    }
    return folds, diagnostics, holdout_start


def holdout_trades(
    trades: Sequence[Mapping[str, Any]],
    data: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    end = int(data["window_end_ts_exclusive"])
    start = end - int(evaluation["untouched_holdout_days"]) * DAY_MS
    embargo_ms = int(evaluation["embargo_bars"]) * int(data["interval_ms"])
    selected = [
        dict(row)
        for row in trades
        if int(row["entry_ts"]) >= start + embargo_ms and int(row["exit_ts"]) < end
    ]
    return selected, {
        "start_ts": start,
        "embargo_start_ts": start + embargo_ms,
        "end_ts_exclusive": end,
        **summarize_trades(selected),
    }


def _period_key(ts_ms: int, period: str) -> str:
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y") if period == "annual" else dt.strftime("%Y-%m")


def _calendar_period_keys(start_ts: int, end_ts_exclusive: int, period: str) -> list[str]:
    start = datetime.fromtimestamp(start_ts / 1000.0, tz=timezone.utc)
    last = datetime.fromtimestamp((end_ts_exclusive - 1) / 1000.0, tz=timezone.utc)
    if period == "annual":
        return [str(year) for year in range(start.year, last.year + 1)]
    keys: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (last.year, last.month):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return keys


def period_rows(
    settled_trades: Sequence[Mapping[str, Any]],
    *,
    period: str,
    scenario: str,
    window_start_ts: int,
    window_end_ts_exclusive: int,
    starting_equity: float,
) -> list[dict[str, Any]]:
    groups: MutableMapping[str, list[Mapping[str, Any]]] = defaultdict(list)
    for trade in settled_trades:
        groups[_period_key(int(trade["exit_ts"]), period)].append(trade)
    rows: list[dict[str, Any]] = []
    current_equity = float(starting_equity)
    for key in _calendar_period_keys(window_start_ts, window_end_ts_exclusive, period):
        group = sorted(
            groups.get(key, []),
            key=lambda row: (int(row["exit_ts"]), str(row["symbol"]), str(row["plan_id"])),
        )
        start_equity = float(group[0]["equity_before_exit"]) if group else current_equity
        end_equity = float(group[-1]["equity_after_exit"]) if group else start_equity
        local_peak = start_equity
        local_dd = 0.0
        for trade in group:
            local_peak = max(local_peak, float(trade["equity_after_exit"]))
            if local_peak > 0:
                local_dd = max(
                    local_dd,
                    100.0 * (local_peak - float(trade["equity_after_exit"])) / local_peak,
                )
        rows.append(
            {
                "scenario": scenario,
                "period": key,
                **summarize_trades(group),
                "pnl_usd": sum(float(row["pnl_usd"]) for row in group),
                "return_pct": 100.0 * (end_equity / start_equity - 1.0) if start_equity else 0.0,
                "exit_realized_max_drawdown_pct": local_dd,
                "active": bool(group),
                "red_active": bool(group) and end_equity < start_equity,
            }
        )
        current_equity = end_equity
    return rows


def symbol_rows(trades: Sequence[Mapping[str, Any]], symbols: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {"symbol": symbol, **summarize_trades([row for row in trades if row["symbol"] == symbol])}
        for symbol in symbols
    ]


def _profit_concentration_pct(rows: Sequence[Mapping[str, Any]]) -> float:
    positive = [max(0.0, float(row["net_r"])) for row in rows]
    total = sum(positive)
    return 100.0 * max(positive or [0.0]) / total if total > 0 else 100.0


def loso_rows(
    candidates: Sequence[Mapping[str, Any]],
    symbols: Sequence[str],
    cfg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    execution = cfg["execution_contract"]
    stress_costs = execution["stress_costs_bps_per_side"]
    out: list[dict[str, Any]] = []
    for removed in symbols:
        accepted, rejected, counters = apply_portfolio_occupancy(
            candidates,
            max_positions=int(execution["max_positions"]),
            excluded_symbols={removed},
        )
        stress = apply_scenario(accepted, stress_costs)
        equity = simulate_equity(stress, execution)
        out.append(
            {
                "removed_symbol": removed,
                **summarize_trades(stress),
                "return_pct": equity["return_pct"],
                "max_drawdown_pct": equity["max_drawdown_pct"],
                "capacity_rejections": sum(
                    1 for row in rejected if row["portfolio_status"] == "rejected_capacity"
                ),
                "accepted": counters.get("accepted", 0),
            }
        )
    return out


def build_gate_report(
    cfg: Mapping[str, Any],
    symbol_results: Sequence[Mapping[str, Any]],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    symbols = [str(symbol) for symbol in cfg["data"]["symbols"]]
    all_candidates = [dict(row) for result in symbol_results for row in result["candidates"]]
    event_ids = [str(value) for result in symbol_results for value in result["event_ids"]]
    plan_ids = [str(value) for result in symbol_results for value in result["plan_ids"]]
    event_counts = Counter(event_ids)
    plan_counts = Counter(plan_ids)
    duplicate_events = sorted(key for key, count in event_counts.items() if count > 1)
    duplicate_plans = sorted(key for key, count in plan_counts.items() if count > 1)
    duplicate_events.extend(
        str(value) for result in symbol_results for value in result["duplicate_event_ids"]
    )
    duplicate_plans.extend(
        str(value) for result in symbol_results for value in result["duplicate_plan_ids"]
    )
    duplicate_events = sorted(set(duplicate_events))
    duplicate_plans = sorted(set(duplicate_plans))
    invalid_candidates = [row for row in all_candidates if row.get("status") != "filled_closed"]
    invalid_statuses = Counter(str(row.get("status")) for row in invalid_candidates)

    execution = cfg["execution_contract"]
    accepted, rejected, occupancy = apply_portfolio_occupancy(
        all_candidates,
        max_positions=int(execution["max_positions"]),
    )
    base = apply_scenario(accepted, execution["base_costs_bps_per_side"])
    stress = apply_scenario(accepted, execution["stress_costs_bps_per_side"])
    base_equity = simulate_equity(base, execution)
    stress_equity = simulate_equity(stress, execution)
    folds, fold_diag, holdout_start = fixed_development_folds(
        stress, cfg["data"], cfg["evaluation_contract"]
    )
    holdout_rows_raw, holdout = holdout_trades(
        stress, cfg["data"], cfg["evaluation_contract"]
    )
    symbol_metrics = symbol_rows(stress, symbols)
    loso = loso_rows(all_candidates, symbols, cfg)
    concentration = _profit_concentration_pct(symbol_metrics)
    period_args = {
        "window_start_ts": int(cfg["data"]["window_start_ts"]),
        "window_end_ts_exclusive": int(cfg["data"]["window_end_ts_exclusive"]),
        "starting_equity": float(execution["starting_equity"]),
    }
    annual = period_rows(
        base_equity["settled_trades"], period="annual", scenario="base", **period_args
    )
    annual += period_rows(
        stress_equity["settled_trades"], period="annual", scenario="stress", **period_args
    )
    monthly = period_rows(
        base_equity["settled_trades"], period="monthly", scenario="base", **period_args
    )
    monthly += period_rows(
        stress_equity["settled_trades"], period="monthly", scenario="stress", **period_args
    )

    full_stress = summarize_trades(stress)
    positive_folds = sum(int(row["trades"]) > 0 and float(row["net_r"]) > 0 for row in folds)
    traded_symbols = sum(int(row["trades"]) > 0 for row in symbol_metrics)
    positive_symbols = sum(int(row["trades"]) > 0 and float(row["net_r"]) > 0 for row in symbol_metrics)
    all_sides = [str(row.get("side")) for row in all_candidates]
    gate = cfg["research_pass_gate"]
    evaluation = cfg["evaluation_contract"]
    checks = {
        "preflight_hash_bound": preflight.get("permission") == "PERFORMANCE_RESEARCH_ALLOWED",
        "stress_pf": float(full_stress["profit_factor"]) >= float(gate["stress_pf_min"]),
        "min_trades": int(full_stress["trades"]) >= int(gate["min_trades"]),
        "positive_folds": positive_folds >= int(gate["positive_folds_min"]),
        "holdout_stress_pf": float(holdout["profit_factor"]) >= float(gate["holdout_stress_pf_min"]),
        "holdout_min_trades": int(holdout["trades"]) >= int(gate["holdout_min_trades"]),
        "min_traded_symbols": traded_symbols >= int(gate["min_traded_symbols"]),
        "min_positive_symbols": positive_symbols >= int(gate["min_positive_symbols"]),
        "profit_concentration": concentration <= float(gate["max_profit_concentration_pct"]),
        "max_drawdown": float(stress_equity["max_drawdown_pct"]) <= float(gate["max_drawdown_pct"]),
        "side_purity": bool(all_sides) and set(all_sides) == {"short"},
        "event_id_duplicates": len(duplicate_events) <= int(evaluation["event_id_duplicates_allowed"]),
        "plan_id_duplicates": len(duplicate_plans) <= int(evaluation["plan_id_duplicates_allowed"]),
        "execution_integrity": not invalid_candidates,
        "loso_computed": (
            evaluation.get("symbol_loso_required") is True and len(loso) == len(symbols)
        ),
    }
    verdict = (
        cfg["automatic_verdict"]["all_gates_pass"]
        if all(checks.values())
        else cfg["automatic_verdict"]["any_gate_failure"]
    )
    return {
        "schema_version": 1,
        "experiment": cfg.get("name"),
        "strategy": "pump_exhaustion_unwind_short_v1",
        "side_identity": "short_only",
        "research_only": True,
        "parameter_scan_performed": False,
        "live_or_broker_calls": False,
        "promotion_authorized": False,
        "preflight_sha256": _canonical_sha(preflight),
        "verdict": verdict,
        "gate_checks": checks,
        "failed_gates": sorted(key for key, passed in checks.items() if not passed),
        "metrics": {
            "base": {
                **summarize_trades(base),
                "return_pct": base_equity["return_pct"],
                "max_drawdown_pct": base_equity["max_drawdown_pct"],
                "exit_realized_max_drawdown_pct": base_equity[
                    "exit_realized_max_drawdown_pct"
                ],
                "conservative_overlap_mae_max_drawdown_pct": base_equity[
                    "conservative_overlap_mae_max_drawdown_pct"
                ],
                "ending_equity": base_equity["ending_equity"],
            },
            "stress": {
                **full_stress,
                "return_pct": stress_equity["return_pct"],
                "max_drawdown_pct": stress_equity["max_drawdown_pct"],
                "exit_realized_max_drawdown_pct": stress_equity[
                    "exit_realized_max_drawdown_pct"
                ],
                "conservative_overlap_mae_max_drawdown_pct": stress_equity[
                    "conservative_overlap_mae_max_drawdown_pct"
                ],
                "ending_equity": stress_equity["ending_equity"],
            },
            "holdout_stress": holdout,
            "positive_folds": positive_folds,
            "traded_symbols": traded_symbols,
            "positive_symbols": positive_symbols,
            "max_profit_concentration_pct": concentration,
            "red_active_months_base": sum(
                row["red_active"] for row in monthly if row["scenario"] == "base"
            ),
            "red_active_months_stress": sum(
                row["red_active"] for row in monthly if row["scenario"] == "stress"
            ),
            "active_months_base": sum(
                row["active"] for row in monthly if row["scenario"] == "base"
            ),
            "active_months_stress": sum(
                row["active"] for row in monthly if row["scenario"] == "stress"
            ),
            "active_years_base": sum(
                row["active"] for row in annual if row["scenario"] == "base"
            ),
            "active_years_stress": sum(
                row["active"] for row in annual if row["scenario"] == "stress"
            ),
            "calendar_months_in_window": sum(
                1 for row in monthly if row["scenario"] == "base"
            ),
            "zero_trade_calendar_months_stress": sum(
                not row["active"] for row in monthly if row["scenario"] == "stress"
            ),
        },
        "evaluation": {
            "development_end_ts_exclusive": holdout_start,
            "folds": folds,
            "fold_diagnostics": fold_diag,
            "holdout": holdout,
            "symbols": symbol_metrics,
            "loso": loso,
            "annual": annual,
            "monthly": monthly,
        },
        "diagnostics": {
            "symbol_generation": [
                {
                    key: value
                    for key, value in result.items()
                    if key not in {"candidates", "event_ids", "plan_ids"}
                }
                for result in symbol_results
            ],
            "events_created": len(event_ids),
            "plans_emitted": len(plan_ids),
            "candidate_statuses": dict(sorted(Counter(str(row.get("status")) for row in all_candidates).items())),
            "invalid_candidate_statuses": dict(sorted(invalid_statuses.items())),
            "duplicate_event_ids": duplicate_events,
            "duplicate_plan_ids": duplicate_plans,
            "occupancy": occupancy,
            "capacity_rejections": len(rejected),
            "cost_model": "entry_notional_plus_fraction_weighted_exit_notional",
            "gap_policy": "actual_next_open; targets_reanchored_to_actual_R; gap_through_frozen_stop_blocks",
            "same_bar_policy": "stop_first",
            "equity_model": stress_equity["sizing"],
            "drawdown_gate_basis": stress_equity["drawdown_gate_basis"],
            "drawdown_limitation": (
                "M5 OHLC cannot prove tick-path MTM; gate uses the larger of exit-realized DD "
                "and a conservative bound that marks every overlapping open trade to its own "
                "observed causal M5 MAE simultaneously"
            ),
        },
        "artifacts": {
            "candidates": all_candidates,
            "accepted": accepted,
            "rejected": rejected,
            "base_trades": base_equity["settled_trades"],
            "stress_trades": stress_equity["settled_trades"],
            "holdout_stress_trades": holdout_rows_raw,
        },
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(_json_safe(value), sort_keys=True)
                    if isinstance(value, (dict, list, tuple))
                    else _json_safe(value)
                    for key, value in row.items()
                }
            )


def write_report_directory(
    output_dir: Path,
    report: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> None:
    if output_dir.exists() or output_dir.is_symlink():
        raise ResearchGateError(f"refusing to overwrite output: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.with_name(f".{output_dir.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    if staging.exists():
        raise ResearchGateError(f"staging path exists: {staging}")
    staging.mkdir()
    try:
        artifacts = report["artifacts"]
        _write_csv(staging / "candidates.csv", artifacts["candidates"])
        _write_csv(staging / "accepted.csv", artifacts["accepted"])
        _write_csv(staging / "rejected.csv", artifacts["rejected"])
        trades_wide: list[dict[str, Any]] = []
        base_by_id = {row["plan_id"]: row for row in artifacts["base_trades"]}
        for stress in artifacts["stress_trades"]:
            base = base_by_id[str(stress["plan_id"])]
            trades_wide.append(
                {
                    **{key: value for key, value in stress.items() if key not in {"cost_r", "net_r", "pnl_usd"}},
                    "base_cost_r": base["cost_r"],
                    "base_net_r": base["net_r"],
                    "base_pnl_usd": base["pnl_usd"],
                    "stress_cost_r": stress["cost_r"],
                    "stress_net_r": stress["net_r"],
                    "stress_pnl_usd": stress["pnl_usd"],
                }
            )
        _write_csv(staging / "trades.csv", trades_wide)
        evaluation = report["evaluation"]
        for name in ("folds", "symbols", "loso", "annual", "monthly"):
            _write_csv(staging / f"{name}.csv", evaluation[name])
        _atomic_json(staging / "preflight_evidence.json", _json_safe(preflight))
        report_without_artifacts = {key: value for key, value in report.items() if key != "artifacts"}
        _atomic_json(staging / "metrics.json", _json_safe(report_without_artifacts))
        hashes = {
            path.name: sha256_file(path)
            for path in sorted(staging.iterdir())
            if path.is_file()
        }
        manifest = {
            "schema_version": 1,
            "kind": "pump_exhaustion_strict_gate_artifacts",
            "experiment": report["experiment"],
            "verdict": report["verdict"],
            "research_only": True,
            "promotion_authorized": False,
            "files": hashes,
        }
        _atomic_json(staging / "manifest.json", manifest)
        os.replace(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _require_reports_path(path: Path, *, directory: bool = False) -> Path:
    resolved_parent = path.parent.resolve()
    allowed = (ROOT / "reports" / "research").resolve()
    try:
        resolved_parent.relative_to(allowed)
    except ValueError as exc:
        raise ResearchGateError("outputs must remain under reports/research") from exc
    if directory and path.name in {"", ".", ".."}:
        raise ResearchGateError("invalid output directory")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--preflight-evidence", type=Path, default=DEFAULT_PREFLIGHT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--authorize-preflight-only", action="store_true")
    mode.add_argument("--run-performance", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        config_path = args.config.resolve(strict=True)
        manifest_path = args.manifest.resolve(strict=True)
        evidence_path = _require_reports_path(args.preflight_evidence.absolute())
        preflight = build_preflight_evidence(ROOT, config_path, manifest_path)
        if args.authorize_preflight_only:
            _atomic_json(evidence_path, preflight)
            print(json.dumps({"output": str(evidence_path), "permission": preflight["permission"]}, sort_keys=True))
            return 0 if preflight["permission"] == "PERFORMANCE_RESEARCH_ALLOWED" else 3

        verify_preflight_evidence(preflight, evidence_path)
        if args.workers < 1 or args.workers > 8:
            raise ResearchGateError("workers must be between 1 and 8")
        cfg = _require_mapping(_read_json(config_path), "preregistration")
        manifest = _require_mapping(_read_json(manifest_path), "snapshot manifest")
        pins = _require_mapping(manifest.get("input_snapshots"), "input_snapshots")
        if sha256_file(config_path) != str(preflight["config"]["sha256"]):
            raise ResearchGateError("config changed after authorization")
        if sha256_file(manifest_path) != str(preflight["immutable_manifest"]["sha256"]):
            raise ResearchGateError("manifest changed after authorization")
        results = generate_all_symbols(
            ROOT, cfg, pins, preflight, workers=args.workers
        )
        report = build_gate_report(cfg, results, preflight)
        output_dir = _require_reports_path(args.output_dir.absolute(), directory=True)
        write_report_directory(output_dir, report, preflight)
        print(
            json.dumps(
                {
                    "output": str(output_dir),
                    "verdict": report["verdict"],
                    "failed_gates": report["failed_gates"],
                },
                sort_keys=True,
            )
        )
        return 0 if not report["failed_gates"] else 4
    except (OSError, ResearchGateError, PreflightError) as exc:
        raise SystemExit(f"pump strict gate refused: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
