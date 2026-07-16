#!/usr/bin/env python3
"""Build the complete public Bybit funding ledger required by the sealed run.

This is a public GET-only, resumable data materializer.  It never reads price
snapshots, imports the trading runner, accesses environment credentials, or
places orders.  Raw API pages are written once under an immutable work folder;
an fsync-backed checkpoint advances only after the page is durable.  Restarting
the command reuses already hashed pages and continues the exact backwards
``endTime`` chain.

The final manifest is emitted only after all 13 symbols bracket the sealed
window and the scorer's strict raw-page/funding validator accepts it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_horizontal_breakout_long_72h_sealed_v1 import (  # noqa: E402
    EXPECTED_FUNDING_KIND,
    EXPECTED_SYMBOLS,
    HOLDOUT_END_MS,
    HOLDOUT_START_MS,
    MAX_FUNDING_GAP_MS,
    canonical_sha256,
    sha256_file,
    validate_funding_manifest,
)


DEFAULT_WORK_DIR = (
    ROOT
    / "data_cache/immutable/"
    "horizontal_breakout_long_72h_funding_v1_20260716"
)
DEFAULT_MANIFEST = DEFAULT_WORK_DIR / "manifest.json"
PUBLIC_BASE_URL = "https://api.bybit.com"
ENDPOINT = "/v5/market/funding/history"
PAGE_LIMIT = 200
FIRST_END_TIME = HOLDOUT_END_MS + MAX_FUNDING_GAP_MS
CHECKPOINT_KIND = "bybit_linear_funding_history_checkpoint_v1"
BUILDER_RELATIVE_PATH = "scripts/materialize_horizontal_breakout_long_72h_funding_v1.py"
FetchJson = Callable[[str, float], Mapping[str, Any]]


class FundingMaterializationError(ValueError):
    """Public funding evidence cannot be materialized honestly."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _repo_relative(root: Path, path: Path) -> str:
    root = root.resolve()
    absolute = path.absolute()
    try:
        relative = absolute.relative_to(root)
    except ValueError as exc:
        raise FundingMaterializationError(f"path must stay inside root: {path}") from exc
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise FundingMaterializationError(f"path contains a symlink: {path}")
    if not relative.parts or ".git" in relative.parts:
        raise FundingMaterializationError(f"unsafe repository path: {path}")
    return relative.as_posix()


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise FundingMaterializationError(f"input is not a regular file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FundingMaterializationError(f"invalid JSON input {path}: {exc}") from exc


def _atomic_replace_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_raw_once(path: Path, payload: Mapping[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if path.exists() or path.is_symlink():
        if path.is_symlink() or path.read_text(encoding="utf-8") != rendered:
            raise FundingMaterializationError(f"existing raw API page differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != rendered:
                raise FundingMaterializationError(f"concurrent raw API page differs: {path}")
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_public_url(symbol: str, end_time: int, *, base_url: str = PUBLIC_BASE_URL) -> str:
    if base_url != PUBLIC_BASE_URL:
        raise FundingMaterializationError("only the official public Bybit base URL is allowed")
    if symbol not in EXPECTED_SYMBOLS:
        raise FundingMaterializationError(f"symbol is outside the frozen cohort: {symbol}")
    if isinstance(end_time, bool) or int(end_time) <= 0:
        raise FundingMaterializationError("endTime must be a positive integer")
    query = urllib.parse.urlencode(
        {
            "category": "linear",
            "symbol": symbol,
            "endTime": int(end_time),
            "limit": PAGE_LIMIT,
        }
    )
    return f"{base_url}{ENDPOINT}?{query}"


def fetch_public_json(url: str, timeout: float) -> Mapping[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.bybit.com"
        or parsed.path != ENDPOINT
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise FundingMaterializationError("refusing a non-public/non-Bybit funding URL")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "bybot-sealed-research-funding-v1/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            if int(getattr(response, "status", 200)) != 200:
                raise FundingMaterializationError(f"Bybit HTTP status {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise FundingMaterializationError(f"public Bybit request failed: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise FundingMaterializationError("public Bybit response root is not an object")
    return payload


def _fetch_with_retry(
    fetcher: FetchJson,
    url: str,
    timeout: float,
    retries: int,
) -> Mapping[str, Any]:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fetcher(url, timeout)
        except Exception as exc:  # caller receives exact final cause
            last = exc
            if attempt >= retries:
                break
            time.sleep(min(4.0, 0.5 * (2**attempt)))
    raise FundingMaterializationError(f"public funding request exhausted retries: {last}")


def parse_page(
    payload: Mapping[str, Any], symbol: str, requested_end_time: int
) -> list[tuple[int, float]]:
    if payload.get("retCode") != 0:
        raise FundingMaterializationError(
            f"Bybit retCode for {symbol}: {payload.get('retCode')} {payload.get('retMsg')}"
        )
    result = payload.get("result")
    if not isinstance(result, Mapping) or result.get("category") != "linear":
        raise FundingMaterializationError(f"Bybit category mismatch for {symbol}")
    rows = result.get("list")
    if not isinstance(rows, list) or not rows or len(rows) > PAGE_LIMIT:
        raise FundingMaterializationError(f"Bybit page row count invalid for {symbol}")
    parsed: list[tuple[int, float]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or set(row) != {
            "symbol", "fundingRate", "fundingRateTimestamp"
        }:
            raise FundingMaterializationError(f"Bybit row schema mismatch for {symbol}:{index}")
        if row.get("symbol") != symbol:
            raise FundingMaterializationError(f"Bybit row symbol mismatch for {symbol}:{index}")
        if isinstance(row.get("fundingRateTimestamp"), bool):
            raise FundingMaterializationError(f"boolean funding timestamp for {symbol}:{index}")
        try:
            ts = int(row["fundingRateTimestamp"])
            rate = float(row["fundingRate"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise FundingMaterializationError(f"invalid funding row for {symbol}:{index}") from exc
        if ts <= 0 or ts > requested_end_time or not math.isfinite(rate) or abs(rate) > 0.05:
            raise FundingMaterializationError(f"funding row out of bounds for {symbol}:{index}")
        parsed.append((ts, rate))
    if len({ts for ts, _ in parsed}) != len(parsed):
        raise FundingMaterializationError(f"duplicate timestamp inside Bybit page for {symbol}")
    return parsed


def _contract() -> dict[str, Any]:
    return {
        "provider": "Bybit_V5_public_funding_history",
        "base_url": PUBLIC_BASE_URL,
        "endpoint": ENDPOINT,
        "category": "linear",
        "limit": PAGE_LIMIT,
        "pagination": "first_end=holdout_end_plus_8h_then_oldest_minus_1",
        "symbols": EXPECTED_SYMBOLS,
        "coverage_start_ts": HOLDOUT_START_MS,
        "coverage_end_ts_exclusive": HOLDOUT_END_MS,
        "first_request_end_time": FIRST_END_TIME,
        "credentials_or_private_endpoints_used": False,
        "price_snapshots_may_be_opened": False,
    }


def _new_checkpoint() -> dict[str, Any]:
    contract = _contract()
    return {
        "schema_version": 1,
        "kind": CHECKPOINT_KIND,
        "contract": contract,
        "contract_fingerprint_sha256": canonical_sha256(contract),
        "symbol_states": {},
        "completed_symbols": [],
        "network_requests_completed": 0,
        "performance_computed": False,
        "price_snapshots_opened": 0,
        "live_or_broker_calls": False,
    }


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _new_checkpoint()
    checkpoint = _read_json(path)
    if not isinstance(checkpoint, dict):
        raise FundingMaterializationError("checkpoint root must be an object")
    contract = _contract()
    if (
        checkpoint.get("schema_version") != 1
        or checkpoint.get("kind") != CHECKPOINT_KIND
        or checkpoint.get("contract") != contract
        or checkpoint.get("contract_fingerprint_sha256") != canonical_sha256(contract)
    ):
        raise FundingMaterializationError("checkpoint contract changed")
    if checkpoint.get("performance_computed") is not False or checkpoint.get("price_snapshots_opened") != 0 or checkpoint.get("live_or_broker_calls") is not False:
        raise FundingMaterializationError("checkpoint safety flags changed")
    if not isinstance(checkpoint.get("symbol_states"), Mapping) or not isinstance(checkpoint.get("completed_symbols"), list):
        raise FundingMaterializationError("checkpoint state is malformed")
    return checkpoint


def _page_receipt(
    root: Path,
    path: Path,
    page_index: int,
    requested_end_time: int,
    events: Sequence[tuple[int, float]],
) -> dict[str, Any]:
    return {
        "page_index": page_index,
        "request_end_time": requested_end_time,
        "raw_path": _repo_relative(root, path),
        "raw_sha256": sha256_file(path),
        "response_rows": len(events),
        "newest_returned_ts": max(ts for ts, _ in events),
        "oldest_returned_ts": min(ts for ts, _ in events),
    }


def _validate_state_pages(
    root: Path, symbol: str, state: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[int, float]]:
    pages = state.get("api_pages")
    if not isinstance(pages, list):
        raise FundingMaterializationError(f"checkpoint pages malformed for {symbol}")
    expected_end = FIRST_END_TIME
    union: dict[int, float] = {}
    validated: list[dict[str, Any]] = []
    for page_index, raw_receipt in enumerate(pages):
        if not isinstance(raw_receipt, Mapping) or raw_receipt.get("page_index") != page_index or raw_receipt.get("request_end_time") != expected_end:
            raise FundingMaterializationError(f"checkpoint pagination chain broke for {symbol}")
        path = root / str(raw_receipt.get("raw_path") or "")
        if not path.is_file() or path.is_symlink() or sha256_file(path) != raw_receipt.get("raw_sha256"):
            raise FundingMaterializationError(f"checkpoint raw page changed for {symbol}:{page_index}")
        payload = _read_json(path)
        events = parse_page(payload, symbol, expected_end)
        receipt = _page_receipt(root, path, page_index, expected_end, events)
        if receipt != dict(raw_receipt):
            raise FundingMaterializationError(f"checkpoint page receipt changed for {symbol}")
        for ts, rate in events:
            prior = union.get(ts)
            if prior is not None and prior != rate:
                raise FundingMaterializationError(f"conflicting duplicate funding event for {symbol}")
            union[ts] = rate
        validated.append(receipt)
        expected_end = receipt["oldest_returned_ts"] - 1
    if state.get("next_end_time") != expected_end:
        raise FundingMaterializationError(f"checkpoint cursor changed for {symbol}")
    completed = bool(validated) and validated[0]["newest_returned_ts"] >= HOLDOUT_END_MS and validated[-1]["oldest_returned_ts"] <= HOLDOUT_START_MS
    if state.get("complete") is not completed:
        raise FundingMaterializationError(f"checkpoint completion flag changed for {symbol}")
    return validated, union


def _final_manifest(
    root: Path, checkpoint: Mapping[str, Any]
) -> dict[str, Any]:
    states = checkpoint["symbol_states"]
    histories: dict[str, Any] = {}
    for symbol in EXPECTED_SYMBOLS:
        state = states.get(symbol)
        if not isinstance(state, Mapping) or state.get("complete") is not True:
            raise FundingMaterializationError(f"funding collection is incomplete for {symbol}")
        pages, union = _validate_state_pages(root, symbol, state)
        ordered = sorted(union.items())
        if not ordered:
            raise FundingMaterializationError(f"funding ledger is empty for {symbol}")
        histories[symbol] = {
            "query_complete": True,
            "oldest_returned_ts": ordered[0][0],
            "newest_returned_ts": ordered[-1][0],
            "api_pages": pages,
            "events": [
                {"funding_ts": ts, "funding_rate": rate} for ts, rate in ordered
            ],
        }
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": EXPECTED_FUNDING_KIND,
        "generated_at_utc": _utc_now(),
        "research_only": True,
        "provider": "Bybit_V5_public_funding_history",
        "category": "linear",
        "credentials_or_private_endpoints_used": False,
        "pagination_complete": True,
        "builder": {
            "path": BUILDER_RELATIVE_PATH,
            "sha256": sha256_file(Path(__file__)),
            "official_api_documentation": "https://bybit-exchange.github.io/docs/v5/market/history-fund-rate",
        },
        "symbols": EXPECTED_SYMBOLS,
        "window": {
            "coverage_start_ts": HOLDOUT_START_MS,
            "coverage_end_ts_exclusive": HOLDOUT_END_MS,
            "event_inclusion": "entry_ts_lte_funding_ts_lt_exit_ts",
            "actual_symbol_specific_timestamps": True,
            "fixed_8h_schedule_assumed": False,
            "maximum_gap_validation_ms": MAX_FUNDING_GAP_MS,
        },
        "histories": histories,
    }
    manifest["manifest_fingerprint_sha256"] = canonical_sha256(manifest)
    return manifest


def materialize(
    root: Path,
    work_dir: Path,
    manifest_path: Path,
    *,
    fetcher: FetchJson = fetch_public_json,
    timeout: float = 20.0,
    retries: int = 3,
    page_budget: int = 0,
    request_interval_seconds: float = 0.15,
) -> dict[str, Any]:
    root = root.resolve()
    _repo_relative(root, work_dir)
    manifest_relative = _repo_relative(root, manifest_path)
    checkpoint_path = work_dir / "checkpoint.json"
    if manifest_path.exists():
        gate = {
            "manifest_path": manifest_relative,
            "manifest_sha256": sha256_file(manifest_path),
        }
        histories, validation = validate_funding_manifest(root, gate)
        return {
            "schema": "horizontal_breakout_long_72h_funding_materialization_v1",
            "status": "COMPLETE_REUSED",
            "manifest": manifest_relative,
            "manifest_sha256": gate["manifest_sha256"],
            "manifest_fingerprint_sha256": validation["manifest_fingerprint_sha256"],
            "symbols_complete": len(histories),
            "network_requests_this_run": 0,
            "price_snapshots_opened": 0,
            "performance_computed": False,
            "live_or_broker_calls": False,
        }
    checkpoint = _load_checkpoint(checkpoint_path)
    pages_this_run = 0
    for symbol in EXPECTED_SYMBOLS:
        raw_state = checkpoint["symbol_states"].get(symbol)
        if raw_state is None:
            state: dict[str, Any] = {
                "next_end_time": FIRST_END_TIME,
                "api_pages": [],
                "complete": False,
            }
        elif isinstance(raw_state, Mapping):
            state = dict(raw_state)
            _validate_state_pages(root, symbol, state)
        else:
            raise FundingMaterializationError(f"checkpoint state malformed for {symbol}")
        while not state["complete"]:
            if page_budget > 0 and pages_this_run >= page_budget:
                checkpoint["symbol_states"][symbol] = state
                checkpoint["completed_symbols"] = sorted(
                    name for name, item in checkpoint["symbol_states"].items()
                    if isinstance(item, Mapping) and item.get("complete") is True
                )
                _atomic_replace_json(checkpoint_path, checkpoint)
                return {
                    "schema": "horizontal_breakout_long_72h_funding_materialization_v1",
                    "status": "INCOMPLETE_RESUMABLE",
                    "checkpoint": _repo_relative(root, checkpoint_path),
                    "completed_symbols": len(checkpoint["completed_symbols"]),
                    "network_requests_this_run": pages_this_run,
                    "price_snapshots_opened": 0,
                    "performance_computed": False,
                    "live_or_broker_calls": False,
                }
            end_time = int(state["next_end_time"])
            page_index = len(state["api_pages"])
            raw_path = work_dir / "pages" / symbol / f"end_{end_time}.json"
            if raw_path.exists():
                payload = _read_json(raw_path)
            else:
                url = build_public_url(symbol, end_time)
                payload = _fetch_with_retry(fetcher, url, timeout, retries)
                _write_raw_once(raw_path, payload)
                pages_this_run += 1
                checkpoint["network_requests_completed"] = int(
                    checkpoint.get("network_requests_completed", 0)
                ) + 1
                if request_interval_seconds > 0:
                    time.sleep(min(1.0, request_interval_seconds))
            events = parse_page(payload, symbol, end_time)
            receipt = _page_receipt(root, raw_path, page_index, end_time, events)
            state["api_pages"].append(receipt)
            state["next_end_time"] = receipt["oldest_returned_ts"] - 1
            state["complete"] = bool(
                state["api_pages"][0]["newest_returned_ts"] >= HOLDOUT_END_MS
                and receipt["oldest_returned_ts"] <= HOLDOUT_START_MS
            )
            checkpoint["symbol_states"][symbol] = state
            checkpoint["completed_symbols"] = sorted(
                name for name, item in checkpoint["symbol_states"].items()
                if isinstance(item, Mapping) and item.get("complete") is True
            )
            _atomic_replace_json(checkpoint_path, checkpoint)

    manifest = _final_manifest(root, checkpoint)
    candidate_path = work_dir / ".manifest.validation.json"
    if candidate_path.is_symlink():
        raise FundingMaterializationError("candidate manifest path is a symlink")
    _atomic_replace_json(candidate_path, manifest)
    candidate_gate = {
        "manifest_path": _repo_relative(root, candidate_path),
        "manifest_sha256": sha256_file(candidate_path),
    }
    # Validate raw-page replay, pagination, brackets and maximum gaps before
    # publishing the immutable final name.  A failed candidate remains safely
    # replaceable on resume and can never masquerade as a completed manifest.
    validate_funding_manifest(root, candidate_gate)
    _write_raw_once(manifest_path, manifest)
    gate = {"manifest_path": manifest_relative, "manifest_sha256": sha256_file(manifest_path)}
    histories, validation = validate_funding_manifest(root, gate)
    candidate_path.unlink()
    return {
        "schema": "horizontal_breakout_long_72h_funding_materialization_v1",
        "status": "COMPLETE",
        "manifest": manifest_relative,
        "manifest_sha256": gate["manifest_sha256"],
        "manifest_fingerprint_sha256": validation["manifest_fingerprint_sha256"],
        "symbols_complete": len(histories),
        "api_pages": sum(len(item["api_pages"]) for item in manifest["histories"].values()),
        "funding_events": sum(len(item["events"]) for item in manifest["histories"].values()),
        "network_requests_this_run": pages_this_run,
        "price_snapshots_opened": 0,
        "performance_computed": False,
        "live_or_broker_calls": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--page-budget", type=int, default=0)
    parser.add_argument("--request-interval-seconds", type=float, default=0.15)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    work_dir = args.work_dir if args.work_dir.is_absolute() else ROOT / args.work_dir
    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    try:
        if args.timeout <= 0 or args.retries < 0 or args.page_budget < 0 or args.request_interval_seconds < 0:
            raise FundingMaterializationError("numeric command limits must be non-negative")
        payload = materialize(
            ROOT,
            work_dir,
            manifest_path,
            timeout=args.timeout,
            retries=args.retries,
            page_budget=args.page_budget,
            request_interval_seconds=args.request_interval_seconds,
        )
        exit_code = 0 if payload["status"].startswith("COMPLETE") else 4
    except (OSError, TypeError, ValueError, FundingMaterializationError) as exc:
        payload = {
            "schema": "horizontal_breakout_long_72h_funding_materialization_v1",
            "status": "BLOCKED_FAIL_CLOSED",
            "error": str(exc),
            "price_snapshots_opened": 0,
            "performance_computed": False,
            "live_or_broker_calls": False,
        }
        exit_code = 2
    print(json.dumps(payload, indent=None if args.compact else 2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
