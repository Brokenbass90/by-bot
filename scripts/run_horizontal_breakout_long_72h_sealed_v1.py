#!/usr/bin/env python3
"""One-shot, fail-closed scorer for the frozen 72h H1 breakout-long lead.

The integrity preflight frozen on 2026-07-15 remains unchanged.  This separate
research runner may decode the sealed 120-day price window only after an
authorization file pins this runner, every price source, and complete Bybit
funding history for all thirteen symbols.  A run claim is created atomically
before the first market row is decoded, so a crash consumes the one allowed
performance attempt instead of silently permitting a second look.

There are no network, broker, environment, allocator, or live imports here.
Passing every gate means research PASS only; it never authorizes shadow/live.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.closed_bar_aggregation_v1 import (  # noqa: E402
    ClosedBarAggregationConfigV1,
    aggregate_closed_m5_bars,
)
from scripts.preflight_horizontal_breakout_long_72h_sealed_v1 import (  # noqa: E402
    DEFAULT_CONFIG,
    EXPECTED_SYMBOLS,
    BreakoutLongPreflightError,
    sha256_file,
    validate_preregistration,
)
from scripts.validate_event_long_dev13_uniform_window_v1 import (  # noqa: E402
    UniformWindowError,
    validate_uniform_window_manifest,
)


DEFAULT_AUTHORIZATION = (
    ROOT
    / "configs/preregistered/"
    "horizontal_breakout_long_72h_sealed_v1_scoring_inputs_20260716.json"
)
RUNNER_RELATIVE_PATH = "scripts/run_horizontal_breakout_long_72h_sealed_v1.py"
PREREG_RELATIVE_PATH = (
    "configs/preregistered/horizontal_breakout_long_72h_sealed_v1_20260715.json"
)
UNIFORM_RELATIVE_PATH = (
    "configs/preregistered/event_long_dev13_uniform_m5_window_v1_20260714.json"
)
PREFLIGHT_RELATIVE_PATH = (
    "scripts/preflight_horizontal_breakout_long_72h_sealed_v1.py"
)
AGGREGATION_RELATIVE_PATH = "bot/closed_bar_aggregation_v1.py"
EXPECTED_SOURCE_PINS = {
    "strategy_preregistration": (PREREG_RELATIVE_PATH, "44c8d35a5bae734be0bb47f2bd2ea81cc82c13eac4b8e19356e802350fd6a04a"),
    "uniform_price_manifest": (UNIFORM_RELATIVE_PATH, "16b4f746a982c4e688de1c6766d93fb916173f3f3e636b7230038455d68facfb"),
    "integrity_preflight": (PREFLIGHT_RELATIVE_PATH, "8dce6b2574d91a2c00689d258df349a2696bf99def8c00b34aeb7a375f18cd5e"),
    "closed_bar_aggregation": (AGGREGATION_RELATIVE_PATH, "5ad6b37ee5124b185ae1cefd0b7aed43863d338fed3d3abfcbf2fce96f2d95aa"),
}
EXPECTED_AUTH_KIND = "horizontal_breakout_long_72h_scoring_inputs_v1"
EXPECTED_FUNDING_KIND = "bybit_linear_funding_history_complete_v1"
H1_MS = 3_600_000
M5_MS = 300_000
MAX_FUNDING_GAP_MS = 28_800_000
HOLDOUT_START_MS = 1_772_805_600_000
HOLDOUT_END_MS = 1_783_173_600_000
WARMUP_H1 = 20


class SealedScoringError(ValueError):
    """A frozen input or scoring invariant is invalid."""


class SealedScoringBlocked(SealedScoringError):
    """Required evidence is absent; no sealed row may be opened."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise SealedScoringError(f"input is not a regular file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SealedScoringError(f"invalid JSON input {path}: {exc}") from exc


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
        raise SealedScoringError(f"unsafe repo-relative path: {text!r}")
    cursor = root.resolve()
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise SealedScoringError(f"path contains a symlink: {text!r}")
    if not cursor.is_file():
        raise SealedScoringError(f"required regular file is missing: {text!r}")
    return cursor


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SealedScoringError(f"{label} must be an object")
    return value


def _exact_keys(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    mapped = _mapping(value, label)
    if set(mapped) != expected:
        raise SealedScoringError(f"{label} schema keys changed")
    return mapped


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise SealedScoringError(f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SealedScoringError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise SealedScoringError(f"{label} must be finite")
    return result


def _validate_authorization_header(
    root: Path, authorization_path: Path
) -> tuple[dict[str, Any], list[str]]:
    authorization = _read_json(authorization_path)
    if not isinstance(authorization, dict):
        raise SealedScoringError("scoring authorization root must be an object")
    fingerprint = authorization.get("authorization_fingerprint_sha256")
    frozen = dict(authorization)
    frozen.pop("authorization_fingerprint_sha256", None)
    if fingerprint != canonical_sha256(frozen):
        raise SealedScoringError("scoring authorization fingerprint mismatch")
    if authorization.get("schema_version") != 1 or authorization.get("kind") != EXPECTED_AUTH_KIND:
        raise SealedScoringError("scoring authorization schema/kind mismatch")
    if authorization.get("research_only") is not True:
        raise SealedScoringError("scoring authorization must remain research-only")
    if authorization.get("one_shot_performance_run") is not True:
        raise SealedScoringError("one-shot performance rule changed")
    if authorization.get("automatic_shadow_or_live_authorization") is not False:
        raise SealedScoringError("automatic shadow/live authorization is forbidden")

    pins = authorization.get("source_pins")
    if not isinstance(pins, list) or len(pins) != len(EXPECTED_SOURCE_PINS) + 1:
        raise SealedScoringError("source pin set is incomplete")
    by_role = {str(row.get("role")): row for row in pins if isinstance(row, Mapping)}
    expected_roles = set(EXPECTED_SOURCE_PINS) | {"sealed_scorer"}
    if set(by_role) != expected_roles:
        raise SealedScoringError("source pin roles changed")
    for role, (path, expected_sha) in EXPECTED_SOURCE_PINS.items():
        row = _exact_keys(by_role[role], {"role", "path", "sha256"}, f"pin {role}")
        if row.get("path") != path or row.get("sha256") != expected_sha:
            raise SealedScoringError(f"frozen source pin changed: {role}")
        if sha256_file(_repo_file(root, path)) != expected_sha:
            raise SealedScoringError(f"frozen source bytes changed: {role}")
    scorer = _exact_keys(
        by_role["sealed_scorer"], {"role", "path", "sha256"}, "pin sealed_scorer"
    )
    if scorer.get("path") != RUNNER_RELATIVE_PATH:
        raise SealedScoringError("sealed scorer path changed")
    if sha256_file(_repo_file(root, RUNNER_RELATIVE_PATH)) != scorer.get("sha256"):
        raise SealedScoringError("sealed scorer bytes changed after authorization")

    side = authorization.get("side_and_execution_contract")
    if side != {
        "candidate_id": "horizontal_breakout_long_72h_v1",
        "physical_side": "long_only",
        "entry": "next_completed_H1_open",
        "exit": "close_of_72nd_completed_H1_after_entry",
        "short_logic_allowed": False,
        "post_hoc_filters_allowed": False,
    }:
        raise SealedScoringError("side/execution authorization changed")
    window = authorization.get("sealed_window")
    if window != {
        "start_ts": HOLDOUT_START_MS,
        "end_ts_exclusive": HOLDOUT_END_MS,
        "warmup_completed_h1": WARMUP_H1,
        "price_rows_may_be_opened_only_after_all_other_gates_pass": True,
    }:
        raise SealedScoringError("sealed window authorization changed")
    output = _exact_keys(
        authorization.get("output_contract"),
        {"directory", "claim", "receipt", "trades", "refuse_overwrite"},
        "output contract",
    )
    if output.get("refuse_overwrite") is not True:
        raise SealedScoringError("one-shot output overwrite protection changed")
    if output.get("claim") != "run_claim.json" or output.get("receipt") != "receipt.json" or output.get("trades") != "trades.json":
        raise SealedScoringError("one-shot output filenames changed")
    directory = Path(str(output.get("directory") or ""))
    if directory.is_absolute() or ".." in directory.parts or not directory.parts:
        raise SealedScoringError("unsafe one-shot output directory")

    funding = _exact_keys(
        authorization.get("funding_history"),
        {
            "required", "status", "manifest_path", "manifest_sha256",
            "required_manifest_kind", "symbols", "coverage_start_ts",
            "coverage_end_ts_exclusive", "max_allowed_event_gap_ms",
            "negative_rate_credit_bps",
        },
        "funding history gate",
    )
    blockers: list[str] = []
    if funding.get("required") is not True:
        raise SealedScoringError("funding history may not be disabled")
    if funding.get("required_manifest_kind") != EXPECTED_FUNDING_KIND:
        raise SealedScoringError("funding manifest kind changed")
    if funding.get("symbols") != EXPECTED_SYMBOLS:
        raise SealedScoringError("funding symbol cohort changed")
    if funding.get("coverage_start_ts") != HOLDOUT_START_MS or funding.get("coverage_end_ts_exclusive") != HOLDOUT_END_MS:
        raise SealedScoringError("funding coverage window changed")
    if funding.get("max_allowed_event_gap_ms") != MAX_FUNDING_GAP_MS:
        raise SealedScoringError("funding maximum-gap rule changed")
    if funding.get("negative_rate_credit_bps") != 0.0:
        raise SealedScoringError("negative funding credit must remain zero")
    if funding.get("status") != "HASH_PINNED_COMPLETE":
        blockers.extend(
            [
                "funding_manifest_not_hash_pinned_complete",
                "funding_cohort_13_of_13_not_proven",
                "funding_coverage_through_2026_07_04_not_proven",
            ]
        )
    elif not funding.get("manifest_path") or not funding.get("manifest_sha256"):
        blockers.append("funding_manifest_path_or_hash_missing")
    return authorization, blockers


def validate_funding_manifest(
    root: Path,
    gate: Mapping[str, Any],
) -> tuple[dict[str, tuple[tuple[int, float], ...]], dict[str, Any]]:
    path = _repo_file(root, gate.get("manifest_path"))
    expected_sha = str(gate.get("manifest_sha256") or "")
    if sha256_file(path) != expected_sha:
        raise SealedScoringError("funding manifest hash mismatch")
    manifest = _read_json(path)
    if not isinstance(manifest, dict):
        raise SealedScoringError("funding manifest root must be an object")
    fingerprint = manifest.get("manifest_fingerprint_sha256")
    frozen = dict(manifest)
    frozen.pop("manifest_fingerprint_sha256", None)
    if fingerprint != canonical_sha256(frozen):
        raise SealedScoringError("funding manifest fingerprint mismatch")
    if manifest.get("schema_version") != 1 or manifest.get("kind") != EXPECTED_FUNDING_KIND:
        raise SealedScoringError("funding manifest schema/kind mismatch")
    exact_flags = {
        "research_only": True,
        "provider": "Bybit_V5_public_funding_history",
        "category": "linear",
        "credentials_or_private_endpoints_used": False,
        "pagination_complete": True,
    }
    if any(manifest.get(key) != expected for key, expected in exact_flags.items()):
        raise SealedScoringError("funding provenance/completeness flags changed")
    if manifest.get("symbols") != EXPECTED_SYMBOLS:
        raise SealedScoringError("funding manifest symbol cohort changed")
    if manifest.get("window") != {
        "coverage_start_ts": HOLDOUT_START_MS,
        "coverage_end_ts_exclusive": HOLDOUT_END_MS,
        "event_inclusion": "entry_ts_lte_funding_ts_lt_exit_ts",
        "actual_symbol_specific_timestamps": True,
        "fixed_8h_schedule_assumed": False,
        "maximum_gap_validation_ms": MAX_FUNDING_GAP_MS,
    }:
        raise SealedScoringError("funding manifest window/interval contract changed")
    histories = manifest.get("histories")
    if not isinstance(histories, Mapping) or set(histories) != set(EXPECTED_SYMBOLS):
        raise SealedScoringError("funding histories are not complete for 13/13 symbols")

    parsed: dict[str, tuple[tuple[int, float], ...]] = {}
    quality: list[dict[str, Any]] = []
    for symbol in EXPECTED_SYMBOLS:
        history = _exact_keys(
            histories[symbol],
            {
                "query_complete", "oldest_returned_ts", "newest_returned_ts",
                "api_pages", "events",
            },
            f"funding history {symbol}",
        )
        if history.get("query_complete") is not True:
            raise SealedScoringError(f"funding pagination is incomplete for {symbol}")
        pages = history.get("api_pages")
        if not isinstance(pages, list) or not pages:
            raise SealedScoringError(f"funding API page evidence is empty for {symbol}")
        raw_union: dict[int, float] = {}
        expected_end_time = HOLDOUT_END_MS + MAX_FUNDING_GAP_MS
        for page_index, raw_page_receipt in enumerate(pages):
            page = _exact_keys(
                raw_page_receipt,
                {
                    "page_index", "request_end_time", "raw_path", "raw_sha256",
                    "response_rows", "newest_returned_ts", "oldest_returned_ts",
                },
                f"funding page receipt {symbol}:{page_index}",
            )
            if page.get("page_index") != page_index:
                raise SealedScoringError(f"funding page index changed for {symbol}:{page_index}")
            if page.get("request_end_time") != expected_end_time:
                raise SealedScoringError(f"funding pagination chain broke for {symbol}:{page_index}")
            raw_path = _repo_file(root, page.get("raw_path"))
            if sha256_file(raw_path) != page.get("raw_sha256"):
                raise SealedScoringError(f"raw funding page hash mismatch for {symbol}:{page_index}")
            raw_payload = _read_json(raw_path)
            if not isinstance(raw_payload, Mapping) or raw_payload.get("retCode") != 0:
                raise SealedScoringError(f"raw funding page is not a successful response for {symbol}:{page_index}")
            result = raw_payload.get("result")
            if not isinstance(result, Mapping) or result.get("category") != "linear":
                raise SealedScoringError(f"raw funding page category changed for {symbol}:{page_index}")
            raw_rows = result.get("list")
            if not isinstance(raw_rows, list) or not raw_rows or len(raw_rows) > 200:
                raise SealedScoringError(f"raw funding page row count is invalid for {symbol}:{page_index}")
            page_events: list[tuple[int, float]] = []
            for row_index, raw_event in enumerate(raw_rows):
                if not isinstance(raw_event, Mapping) or set(raw_event) != {
                    "symbol", "fundingRate", "fundingRateTimestamp"
                }:
                    raise SealedScoringError(
                        f"raw funding row schema changed for {symbol}:{page_index}:{row_index}"
                    )
                if raw_event.get("symbol") != symbol:
                    raise SealedScoringError(f"raw funding row symbol mismatch for {symbol}")
                try:
                    event_ts = int(raw_event["fundingRateTimestamp"])
                except (TypeError, ValueError, OverflowError) as exc:
                    raise SealedScoringError(f"invalid raw funding timestamp for {symbol}") from exc
                event_rate = _finite(raw_event.get("fundingRate"), f"raw funding rate {symbol}")
                if event_ts > expected_end_time or abs(event_rate) > 0.05:
                    raise SealedScoringError(f"invalid raw funding event for {symbol}:{page_index}")
                page_events.append((event_ts, event_rate))
                prior_rate = raw_union.get(event_ts)
                if prior_rate is not None and prior_rate != event_rate:
                    raise SealedScoringError(f"conflicting duplicate funding event for {symbol}")
                raw_union[event_ts] = event_rate
            newest = max(ts for ts, _ in page_events)
            oldest = min(ts for ts, _ in page_events)
            if (
                page.get("response_rows") != len(page_events)
                or page.get("newest_returned_ts") != newest
                or page.get("oldest_returned_ts") != oldest
            ):
                raise SealedScoringError(f"funding page receipt disagrees with raw bytes for {symbol}")
            expected_end_time = oldest - 1
        if int(pages[0]["newest_returned_ts"]) < HOLDOUT_END_MS:
            raise SealedScoringError(f"first funding page does not bracket holdout end for {symbol}")
        if int(pages[-1]["oldest_returned_ts"]) > HOLDOUT_START_MS:
            raise SealedScoringError(f"funding pagination did not reach holdout start for {symbol}")
        events_raw = history.get("events")
        if not isinstance(events_raw, list) or not events_raw:
            raise SealedScoringError(f"funding events are empty for {symbol}")
        events: list[tuple[int, float]] = []
        for index, raw in enumerate(events_raw):
            row = _exact_keys(raw, {"funding_ts", "funding_rate"}, f"funding event {symbol}:{index}")
            if isinstance(row.get("funding_ts"), bool):
                raise SealedScoringError(f"boolean funding timestamp for {symbol}:{index}")
            try:
                ts = int(row["funding_ts"])
            except (TypeError, ValueError, OverflowError) as exc:
                raise SealedScoringError(f"invalid funding timestamp for {symbol}:{index}") from exc
            rate = _finite(row.get("funding_rate"), f"funding rate {symbol}:{index}")
            if abs(rate) > 0.05:
                raise SealedScoringError(f"implausible funding rate for {symbol}:{index}")
            if events and ts <= events[-1][0]:
                raise SealedScoringError(f"duplicate/out-of-order funding event for {symbol}")
            events.append((ts, rate))
        if events != sorted(raw_union.items()):
            raise SealedScoringError(f"funding event ledger differs from raw API pages for {symbol}")
        oldest = int(history.get("oldest_returned_ts") or 0)
        newest = int(history.get("newest_returned_ts") or 0)
        if oldest != events[0][0] or newest != events[-1][0]:
            raise SealedScoringError(f"funding edge timestamps disagree for {symbol}")
        before = [event for event in events if event[0] <= HOLDOUT_START_MS]
        after = [event for event in events if event[0] >= HOLDOUT_END_MS]
        if not before or not after:
            raise SealedScoringError(f"funding coverage is not bracketed for {symbol}")
        relevant = [event for event in events if before[-1][0] <= event[0] <= after[0][0]]
        gaps = [right[0] - left[0] for left, right in zip(relevant, relevant[1:])]
        max_gap = max(gaps, default=0)
        if max_gap <= 0 or max_gap > MAX_FUNDING_GAP_MS:
            raise SealedScoringError(f"funding gap exceeds 8h completeness ceiling for {symbol}")
        parsed[symbol] = tuple(events)
        quality.append(
            {
                "symbol": symbol,
                "event_count": len(events),
                "oldest_returned_ts": oldest,
                "newest_returned_ts": newest,
                "max_gap_ms": max_gap,
                "coverage_bracketed": True,
            }
        )
    return parsed, {
        "manifest": str(gate["manifest_path"]),
        "manifest_sha256": expected_sha,
        "manifest_fingerprint_sha256": fingerprint,
        "symbols_complete": len(parsed),
        "quality": quality,
    }


def build_preflight(
    root: Path,
    strategy_config: Path,
    authorization_path: Path,
) -> tuple[dict[str, Any], dict[str, tuple[tuple[int, float], ...]] | None]:
    """Validate all non-price gates; never decode a market snapshot."""
    integrity = validate_preregistration(root, strategy_config)
    authorization, blockers = _validate_authorization_header(root, authorization_path)
    uniform = validate_uniform_window_manifest(
        root, root / UNIFORM_RELATIVE_PATH, verify_rows=False
    )
    if uniform.get("symbols") != EXPECTED_SYMBOLS:
        raise SealedScoringError("uniform price cohort changed")
    funding_events = None
    funding_receipt = None
    if not blockers:
        funding_events, funding_receipt = validate_funding_manifest(
            root, _mapping(authorization["funding_history"], "funding history gate")
        )
    output = authorization["output_contract"]
    output_dir = root / str(output["directory"])
    claim_path = output_dir / str(output["claim"])
    if claim_path.exists() or claim_path.is_symlink():
        blockers.append("one_shot_performance_attempt_already_claimed")
    receipt = {
        "schema": "horizontal_breakout_long_72h_sealed_v1_preperformance_receipt",
        "generated_at_utc": _utc_now(),
        "permission": "PERFORMANCE_RESEARCH_ALLOWED" if not blockers else "BLOCKED_FAIL_CLOSED",
        "blockers": sorted(set(blockers)),
        "strategy_integrity": integrity,
        "authorization": {
            "path": authorization_path.relative_to(root).as_posix(),
            "sha256": sha256_file(authorization_path),
            "fingerprint": authorization["authorization_fingerprint_sha256"],
        },
        "uniform_price_integrity": {
            "manifest": uniform["manifest"],
            "manifest_sha256": uniform["manifest_sha256"],
            "symbols": len(uniform["symbols"]),
            "source_hashes_verified": uniform["source_hashes_verified"],
        },
        "funding_integrity": funding_receipt,
        "market_snapshots_opened": 0,
        "sealed_holdout_rows_decoded": 0,
        "performance_computed": False,
        "network_or_broker_calls": False,
        "promotion_authorized": False,
    }
    return receipt, funding_events


def _atomic_json(path: Path, payload: Any) -> None:
    if path.exists() or path.is_symlink():
        raise SealedScoringError(f"refusing to overwrite one-shot artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def claim_one_shot(output_dir: Path, preflight: Mapping[str, Any]) -> Path:
    claim_path = output_dir / "run_claim.json"
    claim_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "horizontal_breakout_long_72h_sealed_v1_one_shot_claim",
        "claimed_at_utc": _utc_now(),
        "authorization_sha256": preflight["authorization"]["sha256"],
        "authorization_fingerprint": preflight["authorization"]["fingerprint"],
        "runner_sha256": sha256_file(ROOT / RUNNER_RELATIVE_PATH),
        "sealed_window": [HOLDOUT_START_MS, HOLDOUT_END_MS],
        "performance_attempt_consumed": True,
        "live_or_broker_calls": False,
    }
    # The final path itself is created with O_EXCL.  A partial file after a
    # crash intentionally still consumes the attempt; no check+replace race can
    # allow two concurrent sealed readers.
    try:
        with claim_path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise SealedScoringError(
            f"refusing to overwrite one-shot artifact: {claim_path}"
        ) from exc
    directory_fd = os.open(claim_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return claim_path


def _load_price_slice(
    root: Path,
    uniform_manifest: Mapping[str, Any],
    symbol: str,
) -> list[tuple[int, float, float, float, float, float]]:
    warmup_start = HOLDOUT_START_MS - WARMUP_H1 * H1_MS
    expected_rows = (HOLDOUT_END_MS - warmup_start) // M5_MS
    snapshot = _mapping(uniform_manifest["snapshots"][symbol], f"price snapshot {symbol}")
    source = _repo_file(root, snapshot["source_path"])
    if sha256_file(source) != snapshot.get("source_sha256"):
        raise SealedScoringError(f"price source changed after claim for {symbol}")
    payload = _read_json(source)
    if not isinstance(payload, list):
        raise SealedScoringError(f"price source is not an array for {symbol}")
    rows: list[tuple[int, float, float, float, float, float]] = []
    expected_ts = warmup_start
    for index, raw in enumerate(payload):
        if not isinstance(raw, Mapping) or set(raw) != {"ts", "o", "h", "l", "c", "v"}:
            raise SealedScoringError(f"non-canonical price row {symbol}:{index}")
        if isinstance(raw.get("ts"), bool):
            raise SealedScoringError(f"boolean price timestamp {symbol}:{index}")
        try:
            ts = int(raw["ts"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise SealedScoringError(f"invalid price timestamp {symbol}:{index}") from exc
        if ts < warmup_start or ts >= HOLDOUT_END_MS:
            continue
        if ts != expected_ts:
            raise SealedScoringError(
                f"price slice gap for {symbol}: expected {expected_ts}, got {ts}"
            )
        o, high, low, close, volume = (
            _finite(raw[key], f"price {symbol}:{index}:{key}") for key in ("o", "h", "l", "c", "v")
        )
        if min(o, high, low, close) <= 0 or volume < 0 or high < max(o, close) or low > min(o, close):
            raise SealedScoringError(f"invalid OHLCV geometry {symbol}:{index}")
        rows.append((ts, o, high, low, close, volume))
        expected_ts += M5_MS
    if len(rows) != expected_rows or expected_ts != HOLDOUT_END_MS:
        raise SealedScoringError(
            f"incomplete price slice for {symbol}: {len(rows)} != {expected_rows}"
        )
    return rows


def _folds(config: Mapping[str, Any]) -> list[dict[str, int | str]]:
    result: list[dict[str, int | str]] = []
    for raw in config["temporal_partition"]["folds"]:
        start = int(datetime.fromisoformat(raw["start_utc"].replace("Z", "+00:00")).timestamp() * 1000)
        end = int(datetime.fromisoformat(raw["end_utc_exclusive"].replace("Z", "+00:00")).timestamp() * 1000)
        result.append({"id": str(raw["id"]), "start": start, "end": end})
    return result


def _event_funding_debits(
    events: Sequence[tuple[int, float]], entry_ts: int, exit_ts: int
) -> tuple[float, float, int]:
    selected = [rate * 10_000.0 for ts, rate in events if entry_ts <= ts < exit_ts]
    base = math.fsum(max(value, 0.0) for value in selected)
    stress = math.fsum(max(value, 5.0) for value in selected)
    return base, stress, len(selected)


def score_symbol(
    symbol: str,
    bars: Sequence[Sequence[float]],
    funding_events: Sequence[tuple[int, float]],
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Apply exactly one prior-20 breakout, next-open entry, fixed 72h exit."""
    folds = _folds(config)
    cooldown = int(config["strategy_contract"]["overlap_and_state"]["same_symbol_pattern_cooldown_h1"])
    base_costs = config["execution_and_cost_contract"]["base_costs"]
    stress_costs = config["execution_and_cost_contract"]["stress_costs"]
    notional = float(config["execution_and_cost_contract"]["portfolio"]["fixed_notional_per_trade_usd"])
    last_signal_index: int | None = None
    trades: list[dict[str, Any]] = []
    counters: defaultdict[str, int] = defaultdict(int)

    for index in range(WARMUP_H1, len(bars)):
        bar = bars[index]
        signal_open_ts = int(bar[0])
        signal_close_ts = signal_open_ts + H1_MS
        if signal_open_ts < HOLDOUT_START_MS or signal_close_ts >= HOLDOUT_END_MS:
            continue
        prior_high = max(float(prior[2]) for prior in bars[index - WARMUP_H1:index])
        if not (float(bar[1]) <= prior_high and float(bar[4]) > prior_high):
            continue
        counters["detected_signals"] += 1
        if last_signal_index is not None and index - last_signal_index < cooldown:
            counters["excluded_cooldown"] += 1
            continue
        last_signal_index = index
        fold_index = next(
            (
                position
                for position, fold in enumerate(folds)
                if int(fold["start"]) <= signal_close_ts < int(fold["end"])
            ),
            None,
        )
        if fold_index is None:
            counters["excluded_outside_fold"] += 1
            continue
        fold = folds[fold_index]
        if fold_index > 0 and signal_close_ts <= int(fold["start"]) + 72 * H1_MS:
            counters["excluded_internal_embargo"] += 1
            continue
        entry_index = index + 1
        exit_index = entry_index + 71
        if exit_index >= len(bars):
            counters["excluded_incomplete_horizon"] += 1
            continue
        entry_ts = int(bars[entry_index][0])
        exit_ts = int(bars[exit_index][0]) + H1_MS
        if entry_ts < int(fold["start"]) or exit_ts >= int(fold["end"]):
            counters["excluded_cross_fold_or_boundary"] += 1
            continue
        entry_open = float(bars[entry_index][1])
        exit_close = float(bars[exit_index][4])
        base_entry = entry_open * (1.0 + float(base_costs["slippage_bps_per_side"]) / 10_000.0)
        base_exit = exit_close * (1.0 - float(base_costs["slippage_bps_per_side"]) / 10_000.0)
        stress_entry = entry_open * (1.0 + float(stress_costs["slippage_bps_per_side"]) / 10_000.0)
        stress_exit = exit_close * (1.0 - float(stress_costs["slippage_bps_per_side"]) / 10_000.0)
        base_funding, stress_funding, funding_count = _event_funding_debits(
            funding_events, entry_ts, exit_ts
        )
        base_price_bps = (base_exit / base_entry - 1.0) * 10_000.0
        stress_price_bps = (stress_exit / stress_entry - 1.0) * 10_000.0
        base_net_bps = base_price_bps - 2.0 * float(base_costs["fee_bps_per_side"]) - base_funding
        stress_net_bps = stress_price_bps - 2.0 * float(stress_costs["fee_bps_per_side"]) - stress_funding
        event_id = hashlib.sha256(
            f"horizontal_breakout_long_72h_v1|{symbol}|{signal_close_ts}".encode("ascii")
        ).hexdigest()[:32]
        trades.append(
            {
                "event_id": event_id,
                "candidate_id": "horizontal_breakout_long_72h_v1",
                "symbol": symbol,
                "side": "long",
                "fold": fold["id"],
                "signal_open_ts": signal_open_ts,
                "signal_close_ts": signal_close_ts,
                "frozen_level": prior_high,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "entry_open": entry_open,
                "exit_close": exit_close,
                "base_entry_fill": base_entry,
                "base_exit_fill": base_exit,
                "stress_entry_fill": stress_entry,
                "stress_exit_fill": stress_exit,
                "funding_events": funding_count,
                "base_funding_debit_bps": base_funding,
                "stress_funding_debit_bps": stress_funding,
                "base_net_bps": base_net_bps,
                "stress_net_bps": stress_net_bps,
                "base_net_pnl_usd": notional * base_net_bps / 10_000.0,
                "stress_net_pnl_usd": notional * stress_net_bps / 10_000.0,
            }
        )
        counters["scored_trades"] += 1
    return trades, dict(sorted(counters.items()))


def enforce_portfolio_occupancy(
    trades: Sequence[Mapping[str, Any]], max_open: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active: list[Mapping[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in sorted(trades, key=lambda row: (int(row["entry_ts"]), str(row["symbol"]))):
        trade = dict(raw)
        active = [row for row in active if int(row["exit_ts"]) > int(trade["entry_ts"])]
        event_id = str(trade["event_id"])
        if event_id in seen_ids:
            invalid.append({"event_id": event_id, "reason": "duplicate_event_id"})
            continue
        if any(str(row["symbol"]) == str(trade["symbol"]) for row in active):
            invalid.append({"event_id": event_id, "reason": "same_symbol_overlap"})
            continue
        if len(active) >= max_open:
            invalid.append({"event_id": event_id, "reason": "global_occupancy_exceeded"})
            continue
        seen_ids.add(event_id)
        active.append(trade)
        accepted.append(trade)
    return accepted, invalid


def _profit_factor(values: Sequence[float]) -> tuple[float | None, bool]:
    gains = math.fsum(value for value in values if value > 0)
    losses = -math.fsum(value for value in values if value < 0)
    if losses == 0:
        return None, gains > 0
    return gains / losses, False


def _winsorized_mean_95(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    low_index = int(math.floor((len(ordered) - 1) * 0.025))
    high_index = int(math.ceil((len(ordered) - 1) * 0.975))
    low, high = ordered[low_index], ordered[high_index]
    return statistics.fmean(min(max(value, low), high) for value in ordered)


def _pf_pass(pf: float | None, infinite: bool, minimum: float) -> bool:
    return infinite or (pf is not None and pf >= minimum)


def _max_drawdown_pct(
    trades: Sequence[Mapping[str, Any]],
    bars_by_symbol: Mapping[str, Sequence[Sequence[float]]],
    funding_by_symbol: Mapping[str, Sequence[tuple[int, float]]],
    *,
    scenario: str,
    starting_equity: float,
    notional: float,
    fee_bps_per_side: float,
    slippage_bps_per_side: float,
) -> float:
    closes = {
        symbol: {int(bar[0]) + H1_MS: float(bar[4]) for bar in bars}
        for symbol, bars in bars_by_symbol.items()
    }
    mark_timestamps = set(range(HOLDOUT_START_MS, HOLDOUT_END_MS, H1_MS))
    mark_timestamps.update(int(row["entry_ts"]) for row in trades)
    peak = starting_equity
    maximum = 0.0
    for mark_ts in sorted(mark_timestamps):
        equity = starting_equity
        for trade in trades:
            entry_ts, exit_ts = int(trade["entry_ts"]), int(trade["exit_ts"])
            if entry_ts > mark_ts:
                continue
            if exit_ts <= mark_ts:
                equity += float(trade[f"{scenario}_net_pnl_usd"])
                continue
            symbol = str(trade["symbol"])
            mark = (
                float(trade["entry_open"])
                if mark_ts == entry_ts
                else closes[symbol].get(mark_ts)
            )
            if mark is None:
                raise SealedScoringError(f"missing H1 mark for {symbol} at {mark_ts}")
            entry_fill = float(trade[f"{scenario}_entry_fill"])
            # A funding event exactly at this H1 mark has already settled while
            # the position is still open.  The full-trade exit contract remains
            # entry <= event < exit; +1 is only the inclusive MTM cut-off.
            base_debit, stress_debit, _ = _event_funding_debits(
                funding_by_symbol[symbol], entry_ts, mark_ts + 1
            )
            funding_debit = stress_debit if scenario == "stress" else base_debit
            liquidation_fill = mark * (1.0 - slippage_bps_per_side / 10_000.0)
            unrealized_bps = (
                (liquidation_fill / entry_fill - 1.0) * 10_000.0
                - 2.0 * fee_bps_per_side
                - funding_debit
            )
            equity += notional * unrealized_bps / 10_000.0
        peak = max(peak, equity)
        if peak > 0:
            maximum = max(maximum, (peak - equity) / peak * 100.0)
    return maximum


def evaluate_gates(
    trades: Sequence[Mapping[str, Any]],
    invalid: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    bars_by_symbol: Mapping[str, Sequence[Sequence[float]]],
    funding_by_symbol: Mapping[str, Sequence[tuple[int, float]]],
) -> dict[str, Any]:
    gates = config["promotion_gates"]
    base = [float(row["base_net_bps"]) for row in trades]
    stress = [float(row["stress_net_bps"]) for row in trades]
    base_pf, base_inf = _profit_factor(base)
    stress_pf, stress_inf = _profit_factor(stress)
    by_fold: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for trade in trades:
        by_fold[str(trade["fold"])].append(trade)
        by_symbol[str(trade["symbol"])].append(trade)
    fold_rows: list[dict[str, Any]] = []
    for fold in ("fold_1", "fold_2", "fold_3", "fold_4"):
        rows = by_fold.get(fold, [])
        values = [float(row["stress_net_bps"]) for row in rows]
        pf, infinite = _profit_factor(values)
        fold_rows.append(
            {
                "fold": fold,
                "trades": len(rows),
                "stress_net_bps": math.fsum(values),
                "stress_profit_factor": pf,
                "stress_profit_factor_infinite": infinite,
            }
        )
    symbol_rows: list[dict[str, Any]] = []
    for symbol in EXPECTED_SYMBOLS:
        rows = by_symbol.get(symbol, [])
        values = [float(row["stress_net_bps"]) for row in rows]
        pf, infinite = _profit_factor(values)
        symbol_rows.append(
            {
                "symbol": symbol,
                "trades": len(rows),
                "stress_net_bps": math.fsum(values),
                "stress_profit_factor": pf,
                "stress_profit_factor_infinite": infinite,
            }
        )
    count = len(trades)
    counts = [len(rows) for rows in by_symbol.values()]
    largest_share = max(counts, default=0) / count if count else 1.0
    hhi = math.fsum((value / count) ** 2 for value in counts) if count else 1.0
    positive_symbol_pnl = sorted(
        (row["stress_net_bps"] for row in symbol_rows if row["stress_net_bps"] > 0),
        reverse=True,
    )
    positive_trade_pnl = sorted((value for value in stress if value > 0), reverse=True)
    top_symbol_share = (
        positive_symbol_pnl[0] / math.fsum(positive_symbol_pnl)
        if positive_symbol_pnl else 1.0
    )
    top_trade_count = max(1, math.ceil(count * 0.10)) if count else 0
    top_trade_share = (
        math.fsum(positive_trade_pnl[:top_trade_count]) / math.fsum(positive_trade_pnl)
        if positive_trade_pnl else 1.0
    )
    loso: list[dict[str, Any]] = []
    for symbol in EXPECTED_SYMBOLS:
        values = [float(row["stress_net_bps"]) for row in trades if row["symbol"] != symbol]
        pf, infinite = _profit_factor(values)
        loso.append(
            {
                "excluded_symbol": symbol,
                "stress_net_bps": math.fsum(values),
                "stress_profit_factor": pf,
                "stress_profit_factor_infinite": infinite,
            }
        )
    portfolio = config["execution_and_cost_contract"]["portfolio"]
    stress_costs = config["execution_and_cost_contract"]["stress_costs"]
    stress_dd = _max_drawdown_pct(
        trades,
        bars_by_symbol,
        funding_by_symbol,
        scenario="stress",
        starting_equity=float(portfolio["starting_equity_usd"]),
        notional=float(portfolio["fixed_notional_per_trade_usd"]),
        fee_bps_per_side=float(stress_costs["fee_bps_per_side"]),
        slippage_bps_per_side=float(stress_costs["slippage_bps_per_side"]),
    )
    aggregate = gates["aggregate"]
    fold_gate = gates["folds"]
    breadth = gates["breadth_and_concentration"]
    fold_pfs = [
        math.inf if row["stress_profit_factor_infinite"] else float(row["stress_profit_factor"] or 0.0)
        for row in fold_rows
    ]
    checks = [
        ("stress_closed_trades_min", count >= int(aggregate["stress_closed_trades_min"]), count),
        ("base_profit_factor_min", _pf_pass(base_pf, base_inf, float(aggregate["base_profit_factor_min"])), base_pf),
        ("stress_profit_factor_min", _pf_pass(stress_pf, stress_inf, float(aggregate["stress_profit_factor_min"])), stress_pf),
        ("stress_net_pnl_positive", math.fsum(stress) > 0, math.fsum(stress)),
        ("stress_winsorized_mean_positive", (_winsorized_mean_95(stress) or 0.0) > 0, _winsorized_mean_95(stress)),
        ("stress_timestamp_max_drawdown", stress_dd <= float(aggregate["stress_timestamp_portfolio_max_drawdown_pct_max"]), stress_dd),
        ("invalid_or_censored_trades", len(invalid) <= int(aggregate["invalid_or_censored_trades_max"]), len(invalid)),
        ("long_side_purity", (100.0 * sum(row["side"] == "long" for row in trades) / count if count else 0.0) >= float(aggregate["long_side_purity_pct_min"]), 100.0 * sum(row["side"] == "long" for row in trades) / count if count else 0.0),
        ("stress_trades_per_fold_min", all(row["trades"] >= int(fold_gate["stress_trades_per_fold_min"]) for row in fold_rows), min((row["trades"] for row in fold_rows), default=0)),
        ("stress_net_positive_folds_min", sum(row["stress_net_bps"] > 0 for row in fold_rows) >= int(fold_gate["stress_net_positive_folds_min"]), sum(row["stress_net_bps"] > 0 for row in fold_rows)),
        ("stress_median_fold_profit_factor_min", statistics.median(fold_pfs) >= float(fold_gate["stress_median_fold_profit_factor_min"]), statistics.median(fold_pfs)),
        ("traded_symbols_min", len(by_symbol) >= int(breadth["traded_symbols_min"]), len(by_symbol)),
        ("stress_positive_symbols_min", sum(row["stress_net_bps"] > 0 for row in symbol_rows) >= int(breadth["stress_positive_symbols_min"]), sum(row["stress_net_bps"] > 0 for row in symbol_rows)),
        ("largest_symbol_trade_count_share_max", largest_share <= float(breadth["largest_symbol_trade_count_share_max"]), largest_share),
        ("symbol_trade_count_hhi_max", hhi <= float(breadth["symbol_trade_count_hhi_max"]), hhi),
        ("top_symbol_positive_net_contribution_share_max", top_symbol_share <= float(breadth["top_symbol_positive_net_contribution_share_max"]), top_symbol_share),
        ("top_10pct_trades_positive_net_contribution_share_max", top_trade_share <= float(breadth["top_10pct_trades_positive_net_contribution_share_max"]), top_trade_share),
        ("leave_one_symbol_out_stress_net_positive", all(row["stress_net_bps"] > 0 for row in loso), min((row["stress_net_bps"] for row in loso), default=0.0)),
        ("leave_one_symbol_out_worst_stress_profit_factor_min", all(_pf_pass(row["stress_profit_factor"], row["stress_profit_factor_infinite"], float(breadth["leave_one_symbol_out_worst_stress_profit_factor_min"])) for row in loso), min((math.inf if row["stress_profit_factor_infinite"] else float(row["stress_profit_factor"] or 0.0) for row in loso), default=0.0)),
    ]
    rendered_checks = [
        {"gate": name, "pass": bool(passed), "actual": None if actual == math.inf else actual}
        for name, passed, actual in checks
    ]
    return {
        "research_gate_pass": all(row["pass"] for row in rendered_checks),
        "checks": rendered_checks,
        "aggregate": {
            "closed_trades": count,
            "base_net_bps": math.fsum(base),
            "stress_net_bps": math.fsum(stress),
            "base_profit_factor": base_pf,
            "base_profit_factor_infinite": base_inf,
            "stress_profit_factor": stress_pf,
            "stress_profit_factor_infinite": stress_inf,
            "stress_winsorized_mean_net_bps": _winsorized_mean_95(stress),
            "stress_timestamp_portfolio_max_drawdown_pct": stress_dd,
            "invalid_or_censored_trades": len(invalid),
        },
        "folds": fold_rows,
        "symbols": symbol_rows,
        "concentration": {
            "largest_symbol_trade_count_share": largest_share,
            "symbol_trade_count_hhi": hhi,
            "top_symbol_positive_net_contribution_share": top_symbol_share,
            "top_10pct_trades_positive_net_contribution_share": top_trade_share,
        },
        "leave_one_symbol_out": loso,
        "winsorization_definition": "symmetric_2.5pct_each_tail_nearest_observed_bounds",
    }


def run_performance(
    root: Path,
    strategy_config: Path,
    authorization_path: Path,
) -> dict[str, Any]:
    preflight, funding = build_preflight(root, strategy_config, authorization_path)
    if preflight["permission"] != "PERFORMANCE_RESEARCH_ALLOWED" or funding is None:
        raise SealedScoringBlocked(
            "sealed performance blocked before market access: "
            + ",".join(preflight["blockers"])
        )
    authorization = _read_json(authorization_path)
    output_dir = root / authorization["output_contract"]["directory"]
    claim_one_shot(output_dir, preflight)
    config = _read_json(strategy_config)
    uniform = _read_json(root / UNIFORM_RELATIVE_PATH)
    bars_by_symbol: dict[str, tuple[tuple[int, float, float, float, float, float], ...]] = {}
    all_trades: list[dict[str, Any]] = []
    counters: dict[str, dict[str, int]] = {}
    aggregation_receipts: list[dict[str, Any]] = []
    try:
        for symbol in EXPECTED_SYMBOLS:
            m5 = _load_price_slice(root, uniform, symbol)
            aggregated = aggregate_closed_m5_bars(
                m5,
                as_of_ms=HOLDOUT_END_MS,
                provider_identity="immutable_dev13_sealed_holdout_v1",
                provider_fingerprint=preflight["uniform_price_integrity"]["manifest_sha256"],
                config=ClosedBarAggregationConfigV1(target_timeframe="H1"),
            )
            bars_by_symbol[symbol] = aggregated.output_bars
            symbol_trades, symbol_counters = score_symbol(
                symbol, aggregated.output_bars, funding[symbol], config
            )
            all_trades.extend(symbol_trades)
            counters[symbol] = symbol_counters
            aggregation_receipts.append(
                {
                    "symbol": symbol,
                    "selected_m5_rows_decoded": len(m5),
                    "sealed_m5_rows_decoded": (HOLDOUT_END_MS - HOLDOUT_START_MS) // M5_MS,
                    "warmup_m5_rows_decoded": WARMUP_H1 * H1_MS // M5_MS,
                    "h1_rows": aggregated.output_count,
                    "h1_sha256": aggregated.output_sha256,
                    "config_fingerprint": aggregated.config_fingerprint,
                }
            )
        max_open = int(config["execution_and_cost_contract"]["portfolio"]["max_global_open_positions"])
        trades, invalid = enforce_portfolio_occupancy(all_trades, max_open)
        evaluation = evaluate_gates(trades, invalid, config, bars_by_symbol, funding)
        result = {
            "schema": "horizontal_breakout_long_72h_sealed_v1_performance_receipt",
            "generated_at_utc": _utc_now(),
            "one_shot_performance_run": 1,
            "candidate_id": "horizontal_breakout_long_72h_v1",
            "physical_side": "long_only",
            "sealed_window": [HOLDOUT_START_MS, HOLDOUT_END_MS],
            "strategy_config_sha256": sha256_file(strategy_config),
            "authorization_sha256": sha256_file(authorization_path),
            "runner_sha256": sha256_file(root / RUNNER_RELATIVE_PATH),
            "funding_manifest_sha256": preflight["funding_integrity"]["manifest_sha256"],
            "market_snapshots_opened": len(EXPECTED_SYMBOLS),
            "sealed_holdout_rows_decoded": len(EXPECTED_SYMBOLS) * ((HOLDOUT_END_MS - HOLDOUT_START_MS) // M5_MS),
            "performance_computed": True,
            "parameter_search_performed": False,
            "network_or_broker_calls": False,
            "automatic_shadow_or_live_authorization": False,
            "decision": (
                "SEALED_RESEARCH_PASS_REQUIRES_INDEPENDENT_PARITY_AND_PROSPECTIVE_PAPER"
                if evaluation["research_gate_pass"]
                else "NO_PROMOTION"
            ),
            "evaluation": evaluation,
            "invalid_or_censored": invalid,
            "signal_counters": counters,
            "aggregation_receipts": aggregation_receipts,
        }
        _atomic_json(output_dir / "trades.json", {"trades": trades})
        _atomic_json(output_dir / "receipt.json", result)
        return result
    except Exception as exc:
        failure = output_dir / "run_failure.json"
        if not failure.exists():
            _atomic_json(
                failure,
                {
                    "schema": "horizontal_breakout_long_72h_sealed_v1_run_failure",
                    "failed_at_utc": _utc_now(),
                    "performance_attempt_consumed": True,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "automatic_retry_allowed": False,
                    "live_or_broker_calls": False,
                },
            )
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--run-performance", action="store_true")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    config = args.config if args.config.is_absolute() else ROOT / args.config
    authorization = args.authorization if args.authorization.is_absolute() else ROOT / args.authorization
    try:
        if args.preflight_only:
            payload, _ = build_preflight(ROOT, config, authorization)
            exit_code = 0 if payload["permission"] == "PERFORMANCE_RESEARCH_ALLOWED" else 3
        else:
            payload = run_performance(ROOT, config, authorization)
            exit_code = 0
    except SealedScoringBlocked as exc:
        payload = {
            "schema": "horizontal_breakout_long_72h_sealed_v1_performance_receipt",
            "permission": "BLOCKED_FAIL_CLOSED",
            "performance_computed": False,
            "market_snapshots_opened": 0,
            "sealed_holdout_rows_decoded": 0,
            "promotion_authorized": False,
            "network_or_broker_calls": False,
            "error": str(exc),
        }
        exit_code = 3
    except (OSError, TypeError, ValueError, BreakoutLongPreflightError, UniformWindowError, SealedScoringError) as exc:
        payload = {
            "schema": "horizontal_breakout_long_72h_sealed_v1_performance_receipt",
            "permission": "BLOCKED_FAIL_CLOSED",
            "performance_computed": False,
            "market_snapshots_opened": 0,
            "sealed_holdout_rows_decoded": 0,
            "promotion_authorized": False,
            "network_or_broker_calls": False,
            "error": str(exc),
        }
        exit_code = 2
    print(json.dumps(payload, indent=None if args.compact else 2, sort_keys=True, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
