#!/usr/bin/env python3
"""Run the settlement-lagged public-only event-universe V2 station.

The default command is a no-network/no-write preflight. Collection needs three
explicit research opt-ins and has no credential, private API, broker, order,
transfer, account, risk, allocator, or live-router capability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.event_universe_v1 import (  # noqa: E402
    M5_INTERVAL_MS,
    SOURCE_ID,
    EventScoreV1,
    EventUniverseConfigV1,
    EventUniverseError,
    build_snapshot_payload,
    canonical_bytes,
    closed_contiguous_m5,
    evaluate_market_eligibility,
    score_event_m5,
    select_prefetch_symbols,
    sha256_payload,
    validate_snapshot_payload,
)
from scripts.run_event_universe_v1 import (  # noqa: E402
    PUBLIC_HOST,
    PUBLIC_PATHS,
    ChainState,
    PublicBybitEventClientV1,
    _atomic_write,
    _bind_normalized_replay,
    _exact_int,
    _precycle_storage_guard,
    _read_json_regular,
    _read_snapshot_regular,
    _research_root,
    _single_writer_lock,
    _status_from_chain,
    _validate_latest_state,
    _validate_replay_object,
    persist_snapshot,
)


SPEC_SCHEMA_ID = "event_universe_preregistered_spec_v2"
LAUNCH_SCHEMA_ID = "event_universe_launch_receipt_v2"
COLLECTOR_CONTRACT_SCHEMA_ID = "event_universe_collector_contract_v2"
DEFAULT_SPEC = ROOT / "configs/preregistered/event_universe_v2_20260721.json"
DEFAULT_RUN_ROOT = ROOT / "runtime/research/event_universe_v2_20260721_public1"
IMPLEMENTATION_RELATIVE_PATHS = (
    "bot/event_universe_v1.py",
    "scripts/run_event_universe_v1.py",
    "scripts/run_event_universe_v2.py",
    "scripts/supervise_event_universe_v2.sh",
    "scripts/launch_event_universe_v2.sh",
    "scripts/supervise_event_universe_v2r2.sh",
    "scripts/launch_event_universe_v2r2.sh",
)
FINALITY_POLICY = {
    "schema_id": "event_universe_source_finality_v2",
    "settlement_lag_bars": 1,
    "usable_bar_rule": "bar_start_plus_10m_lte_source_as_of",
    "forming_and_just_closed_bars_forbidden": True,
    "cross_snapshot_immutable_bar_assertion": True,
    "conflict_action": "STOP_FAIL_CLOSED_NO_REWRITE",
}


class ImmutableBarConflict(EventUniverseError):
    """Terminal source-finality violation; the supervisor must not retry it."""


def _load_v2_spec(path: Path) -> tuple[dict[str, Any], EventUniverseConfigV1]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EventUniverseError("event-universe-v2 spec root must be an object")
    if payload.get("schema_id") != SPEC_SCHEMA_ID or payload.get("strategy_id") != "event_universe_v2":
        raise EventUniverseError("event-universe-v2 spec identity mismatch")
    if payload.get("source_id") != SOURCE_ID or payload.get("status") != "RESEARCH_ONLY_DEFAULT_DISABLED":
        raise EventUniverseError("event-universe-v2 source/status mismatch")
    run_revision = payload.get("run_revision")
    if run_revision not in {None, "v2r2_timestamp_corrected"}:
        raise EventUniverseError("event-universe-v2 run revision is invalid")
    expected_authority = {
        "research_only": True,
        "executable": False,
        "private_api_calls": False,
        "api_keys_or_environment_reads": False,
        "broker_calls": False,
        "orders_transfers_withdrawals": False,
        "risk_or_live_router_mutation": False,
        "performance_claims": False,
        "promotion_authority": False,
    }
    if payload.get("authority") != expected_authority:
        raise EventUniverseError("event-universe-v2 authority is not frozen fail-closed")
    if payload.get("source_finality_policy") != FINALITY_POLICY:
        raise EventUniverseError("event-universe-v2 source finality policy changed")
    expected_analysis = {
        "thresholds_and_universe_rules_locked_for_this_run": True,
        "no_midrun_outcome_tuning": True,
        "candidate_labels_are_advisory_not_trade_signals": True,
        "this_discovery_run_cannot_authorize_promotion": True,
        "downstream_long_and_short_consumers_require_separate_preregistration_and_sealed_tests": True,
    }
    if payload.get("analysis_policy") != expected_analysis:
        raise EventUniverseError("event-universe-v2 prospective analysis policy mismatch")
    public_io = payload.get("public_io")
    if not isinstance(public_io, Mapping):
        raise EventUniverseError("event-universe-v2 public I/O contract is missing")
    expected_public = {
        "host": PUBLIC_HOST,
        "method": "GET_ONLY",
        "paths": list(PUBLIC_PATHS),
        "category": "linear",
        "instrument_status": "Trading",
        "instrument_contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "instrument_page_limit": 1000,
        "kline_limit": 77,
        "timeout_seconds": 15,
        "max_retries": 4,
        "backoff_base_seconds": 1.0,
    }
    if dict(public_io) != expected_public:
        raise EventUniverseError("event-universe-v2 public I/O contract changed")
    config_payload = payload.get("config")
    if not isinstance(config_payload, Mapping):
        raise EventUniverseError("event-universe-v2 scoring config is missing")
    config = EventUniverseConfigV1(**dict(config_payload))
    expected_persistence = {
        "immutable_snapshot_files": True,
        "deterministic_gzip_snapshots": True,
        "snapshot_hash_chain": True,
        "delta_score_replay_chain": True,
        "source_hashes_asserted_not_replayed": True,
        "atomic_latest_state": True,
        "file_mode": "0600",
        "retention_action": "STOP_NO_DELETE_NO_ROTATE",
    }
    if payload.get("persistence") != expected_persistence:
        raise EventUniverseError("event-universe-v2 persistence contract changed")
    return payload, config


def _implementation_hashes() -> dict[str, str]:
    return {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in IMPLEMENTATION_RELATIVE_PATHS
    }


def _collector_contract(spec: Mapping[str, Any]) -> dict[str, Any]:
    contract = {
        "schema_id": COLLECTOR_CONTRACT_SCHEMA_ID,
        "collector_id": "event_universe_v2",
        "spec_sha256": sha256_payload(spec),
        "source_finality_policy": FINALITY_POLICY,
    }
    if spec.get("run_revision") is not None:
        contract["run_revision"] = str(spec["run_revision"])
    return contract


def validate_v2_snapshot(
    payload: Mapping[str, Any],
    *,
    spec: Mapping[str, Any],
    config: EventUniverseConfigV1,
) -> None:
    validate_snapshot_payload(payload, config=config, require_replay=True)
    if payload.get("collector_contract") != _collector_contract(spec):
        raise EventUniverseError("snapshot is not bound to the frozen V2 finality contract")


def normalize_settled_m5(
    raw_rows: Sequence[Sequence[Any]],
    *,
    source_as_of_ms: int,
    config: EventUniverseConfigV1,
) -> list[list[Any]]:
    source_as_of_ms = _exact_int(source_as_of_ms, "source as_of_ms", positive=True)
    settled_cutoff_ms = source_as_of_ms - M5_INTERVAL_MS * FINALITY_POLICY["settlement_lag_bars"]
    rows = closed_contiguous_m5(
        raw_rows,
        as_of_ms=settled_cutoff_ms,
        required_bars=config.required_closed_bars,
    )
    normalized = [row.payload() for row in rows]
    if int(normalized[-1][0]) + 2 * M5_INTERVAL_MS > source_as_of_ms:
        raise EventUniverseError("V2 normalized tail violates the frozen +10m settlement lag")
    return normalized


def assert_no_immutable_bar_conflict(
    immutable_rows_by_symbol: Mapping[str, Mapping[int, Sequence[Any]]],
    candidate_rows_by_symbol: Mapping[str, Sequence[Sequence[Any]]],
) -> None:
    for symbol, rows in candidate_rows_by_symbol.items():
        known = immutable_rows_by_symbol.get(symbol, {})
        for raw in rows:
            row = list(raw)
            start_ms = _exact_int(row[0], "immutable M5 start", positive=True)
            previous = known.get(start_ms)
            if previous is not None and list(previous) != row:
                raise ImmutableBarConflict(f"V2 immutable M5 conflict for {symbol} at {start_ms}")


def _merge_immutable_rows(
    immutable_rows_by_symbol: dict[str, dict[int, list[Any]]],
    rows_by_symbol: Mapping[str, Sequence[Sequence[Any]]],
) -> None:
    assert_no_immutable_bar_conflict(immutable_rows_by_symbol, rows_by_symbol)
    for symbol, rows in rows_by_symbol.items():
        known = immutable_rows_by_symbol.setdefault(symbol, {})
        for raw in rows:
            row = list(raw)
            known[int(row[0])] = row


def _load_v2_chain(
    root: Path,
    *,
    spec: Mapping[str, Any],
    config: EventUniverseConfigV1,
) -> tuple[ChainState, dict[str, dict[int, list[Any]]]]:
    root = _research_root(root)
    count = 0
    last_path: Path | None = None
    last_payload: dict[str, Any] | None = None
    previous_normalized: dict[str, list[list[Any]]] = {}
    immutable_rows: dict[str, dict[int, list[Any]]] = {}
    previous_hash: str | None = None
    previous_as_of_ms: int | None = None
    for expected_sequence, path in enumerate(sorted(root.glob("snapshot_*.json.gz")), 1):
        payload = _read_snapshot_regular(path, config=config)
        validate_v2_snapshot(payload, spec=spec, config=config)
        if payload.get("sequence") != expected_sequence:
            raise EventUniverseError("V2 snapshot sequence is not contiguous")
        if payload.get("previous_snapshot_sha256") != previous_hash:
            raise EventUniverseError("V2 snapshot hash chain is broken")
        as_of_ms = _exact_int(payload["as_of_ms"], "V2 snapshot as_of_ms", positive=True)
        if previous_as_of_ms is not None and as_of_ms <= previous_as_of_ms:
            raise EventUniverseError("V2 snapshot chronology is not strictly increasing")
        if path.name != f"snapshot_{expected_sequence:06d}_{as_of_ms}.json.gz":
            raise EventUniverseError("V2 snapshot filename/identity mismatch")
        normalized = _validate_replay_object(
            root,
            payload,
            previous_normalized_m5_by_symbol=previous_normalized,
            config=config,
        )
        for rows in normalized.values():
            if int(rows[-1][0]) + 2 * M5_INTERVAL_MS > as_of_ms:
                raise EventUniverseError("persisted V2 tail violates +10m settlement lag")
        _merge_immutable_rows(immutable_rows, normalized)
        previous_normalized = normalized
        previous_hash = str(payload["snapshot_sha256"])
        previous_as_of_ms = as_of_ms
        count = expected_sequence
        last_path = path
        last_payload = payload
    chain_state: ChainState = (count, last_path, last_payload, previous_normalized)
    _validate_latest_state(root, chain_state, config=config)
    return chain_state, immutable_rows


def _client_from_v2_spec(spec: Mapping[str, Any], config: EventUniverseConfigV1) -> PublicBybitEventClientV1:
    public_io = spec["public_io"]
    return PublicBybitEventClientV1(
        config=config,
        timeout_seconds=float(public_io["timeout_seconds"]),
        max_retries=int(public_io["max_retries"]),
        backoff_base_seconds=float(public_io["backoff_base_seconds"]),
    )


def _collect_once_with_state(
    *,
    root: Path,
    spec: Mapping[str, Any],
    config: EventUniverseConfigV1,
    client: PublicBybitEventClientV1,
    chain_state: ChainState,
    immutable_rows: dict[str, dict[int, list[Any]]],
) -> tuple[Path, dict[str, Any], ChainState]:
    root = _research_root(root)
    _precycle_storage_guard(root, config=config)
    client.start_cycle()
    chain_count, _last_path, last_payload, previous_normalized = chain_state
    sequence = chain_count + 1
    previous_hash = last_payload["snapshot_sha256"] if last_payload else None

    instruments, instrument_hashes, instrument_time = client.fetch_instruments()
    tickers, ticker_hash, ticker_time = client.fetch_tickers()
    as_of_ms = max(instrument_time, ticker_time)
    if last_payload is not None and as_of_ms <= int(last_payload["as_of_ms"]):
        raise EventUniverseError("V2 public point-in-time cutoff did not advance")
    ticker_by_symbol = {str(item.get("symbol") or "").upper(): item for item in tickers}
    market_rows = [
        evaluate_market_eligibility(
            instrument,
            ticker_by_symbol.get(str(instrument.get("symbol") or "").upper()),
            as_of_ms=as_of_ms,
            config=config,
        )
        for instrument in instruments
    ]
    prefetch = select_prefetch_symbols(market_rows, config=config)
    market_by_symbol = {row.symbol: row for row in market_rows}
    scores: list[EventScoreV1] = []
    errors: dict[str, str] = {}
    kline_hashes: dict[str, str] = {}
    normalized_m5_by_symbol: dict[str, list[list[Any]]] = {}
    kline_limit = _exact_int(spec["public_io"]["kline_limit"], "V2 kline limit", positive=True)
    minimum_limit = config.required_closed_bars + FINALITY_POLICY["settlement_lag_bars"] + 1
    if kline_limit < minimum_limit or kline_limit > 1000:
        raise EventUniverseError("V2 frozen kline limit cannot provide settled closed tail")
    for symbol in prefetch:
        try:
            raw_rows, source_hash = client.fetch_m5(symbol, as_of_ms=as_of_ms, limit=kline_limit)
            kline_hashes[symbol] = source_hash
            normalized_payload = normalize_settled_m5(
                raw_rows,
                source_as_of_ms=as_of_ms,
                config=config,
            )
            scores.append(
                score_event_m5(
                    symbol,
                    normalized_payload,
                    as_of_ms=as_of_ms,
                    listing_tier=market_by_symbol[symbol].listing_tier,
                    config=config,
                )
            )
            normalized_m5_by_symbol[symbol] = normalized_payload
        except (EventUniverseError, KeyError, TypeError, ValueError) as exc:
            errors[symbol] = f"{type(exc).__name__}:{exc}"

    # The conflict assertion is outside the per-symbol diagnostic catch. A
    # source revision is terminal for the entire tape, never a skipped symbol.
    assert_no_immutable_bar_conflict(immutable_rows, normalized_m5_by_symbol)
    payload = build_snapshot_payload(
        as_of_ms=as_of_ms,
        config=config,
        instruments_page_sha256=instrument_hashes,
        tickers_sha256=ticker_hash,
        market_rows=market_rows,
        prefetch_symbols=prefetch,
        scores=scores,
        errors_by_symbol=errors,
        sequence=sequence,
        previous_snapshot_sha256=previous_hash,
    )
    payload["source_receipts"]["kline_sha256_by_symbol"] = dict(sorted(kline_hashes.items()))
    payload["collector_contract"] = _collector_contract(spec)
    payload.pop("snapshot_sha256")
    payload["snapshot_sha256"] = sha256_payload(payload)
    payload, replay_bytes = _bind_normalized_replay(
        payload,
        normalized_m5_by_symbol,
        previous_normalized_m5_by_symbol=previous_normalized,
        config=config,
    )
    validate_v2_snapshot(payload, spec=spec, config=config)
    path = persist_snapshot(
        root,
        payload,
        replay_bytes=replay_bytes,
        config=config,
        chain_state=chain_state,
    )
    _merge_immutable_rows(immutable_rows, normalized_m5_by_symbol)
    next_state: ChainState = (sequence, path, payload, normalized_m5_by_symbol)
    return path, payload, next_state


def _launch_receipt(root: Path, *, spec: Mapping[str, Any], config: EventUniverseConfigV1) -> dict[str, Any]:
    root = _research_root(root)
    path = root / "launch_receipt_v2.json"
    frozen_identity = {
        "research_only": True,
        "executable": False,
        "api_keys_or_environment_reads": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_or_risk_mutation": False,
        "spec_sha256": sha256_payload(spec),
        "config_sha256": config.config_sha256,
        "collector_contract": _collector_contract(spec),
        "implementation_sha256_by_path": _implementation_hashes(),
        "poll_interval_seconds": config.poll_interval_seconds,
        "max_snapshots": config.max_snapshots,
        "max_total_bytes": config.max_total_bytes,
    }
    if path.exists():
        payload = _read_json_regular(path)
        body = dict(payload)
        observed_hash = str(body.pop("launch_sha256", ""))
        if payload.get("schema_id") != LAUNCH_SCHEMA_ID or observed_hash != sha256_payload(body):
            raise EventUniverseError("V2 launch receipt checksum/identity mismatch")
        if any(payload.get(key) != value for key, value in frozen_identity.items()):
            raise EventUniverseError("V2 launch receipt no longer matches frozen implementation")
        started_ms = _exact_int(payload.get("started_at_ms"), "V2 launch started_at_ms", positive=True)
        deadline_ms = _exact_int(payload.get("deadline_at_ms"), "V2 launch deadline_at_ms", positive=True)
        if deadline_ms != started_ms + config.max_runtime_seconds * 1000:
            raise EventUniverseError("V2 launch deadline bound is invalid")
        if int(time.time() * 1000) >= deadline_ms:
            raise EventUniverseError("event-universe-v2 launch deadline has expired")
        return payload
    started_ms = int(time.time() * 1000)
    body: dict[str, Any] = {
        "schema_id": LAUNCH_SCHEMA_ID,
        **frozen_identity,
        "started_at_ms": started_ms,
        "deadline_at_ms": started_ms + config.max_runtime_seconds * 1000,
    }
    body["launch_sha256"] = sha256_payload(body)
    _atomic_write(path, canonical_bytes(body) + b"\n", replace=False)
    return body


def _require_opt_ins(args: argparse.Namespace) -> None:
    missing = []
    if not args.allow_public_network:
        missing.append("--allow-public-network")
    if not args.enable_durable_collector:
        missing.append("--enable-durable-collector")
    if not args.acknowledge_research_only:
        missing.append("--acknowledge-research-only")
    if missing:
        raise EventUniverseError("V2 collection requires explicit opt-ins: " + ", ".join(missing))


def _preflight(spec_path: Path, spec: Mapping[str, Any], config: EventUniverseConfigV1) -> dict[str, Any]:
    return {
        "schema_id": "event_universe_preflight_v2",
        "ok": True,
        "status": spec["status"],
        "spec": str(spec_path),
        "spec_sha256": sha256_payload(spec),
        "config_sha256": config.config_sha256,
        "collector_contract": _collector_contract(spec),
        "implementation_sha256_by_path": _implementation_hashes(),
        "default_enabled": False,
        "network_calls": False,
        "filesystem_writes": False,
        "daemon_started": False,
        "public_method": "GET_ONLY",
        "public_host": PUBLIC_HOST,
        "public_paths": list(PUBLIC_PATHS),
        "api_keys_or_environment_reads": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_transfers_withdrawals": False,
        "risk_or_live_router_mutation": False,
        "executable": False,
        "performance_claims": False,
        "promotion_authority": False,
        "bounds": {
            "poll_interval_seconds": config.poll_interval_seconds,
            "max_runtime_seconds": config.max_runtime_seconds,
            "max_snapshots": config.max_snapshots,
            "max_total_bytes": config.max_total_bytes,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("preflight", help="No-network/no-write safety receipt (default).")
    status = sub.add_parser("status", help="No-network deterministic V2 chain status.")
    status.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    for name in ("collect-once", "run"):
        cmd = sub.add_parser(name, help="Public research collection; no credentials or execution.")
        cmd.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
        cmd.add_argument("--allow-public-network", action="store_true")
        cmd.add_argument("--enable-durable-collector", action="store_true")
        cmd.add_argument("--acknowledge-research-only", action="store_true")
        if name == "run":
            cmd.add_argument("--max-cycles-this-process", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "preflight"
    try:
        spec, config = _load_v2_spec(args.spec)
        if command == "preflight":
            print(json.dumps(_preflight(args.spec, spec, config), indent=2, sort_keys=True))
            return 0
        if command == "status":
            chain_state, immutable_rows = _load_v2_chain(args.run_root, spec=spec, config=config)
            status = _status_from_chain(chain_state, config=config)
            status.update(
                {
                    "collector_id": "event_universe_v2",
                    "source_finality_policy": FINALITY_POLICY,
                    "immutable_symbol_count": len(immutable_rows),
                }
            )
            print(json.dumps(status, indent=2, sort_keys=True))
            return 0

        _require_opt_ins(args)
        client = _client_from_v2_spec(spec, config)
        with _single_writer_lock(args.run_root):
            launch = _launch_receipt(args.run_root, spec=spec, config=config)
            chain_state, immutable_rows = _load_v2_chain(args.run_root, spec=spec, config=config)
            if command == "collect-once":
                path, payload, _chain_state = _collect_once_with_state(
                    root=args.run_root,
                    spec=spec,
                    config=config,
                    client=client,
                    chain_state=chain_state,
                    immutable_rows=immutable_rows,
                )
                print(
                    json.dumps(
                        {
                            "snapshot": str(path),
                            "sequence": payload["sequence"],
                            "as_of_ms": payload["as_of_ms"],
                            "score_count": payload["score_count"],
                            "event_candidate_count": payload["event_candidate_count"],
                            "research_only": True,
                            "executable": False,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0

            max_cycles = args.max_cycles_this_process
            if max_cycles is not None and max_cycles <= 0:
                raise EventUniverseError("V2 max cycles must be positive")
            completed = 0
            while int(time.time() * 1000) < int(launch["deadline_at_ms"]):
                if chain_state[0] >= config.max_snapshots:
                    break
                cycle_started = time.monotonic()
                path, payload, chain_state = _collect_once_with_state(
                    root=args.run_root,
                    spec=spec,
                    config=config,
                    client=client,
                    chain_state=chain_state,
                    immutable_rows=immutable_rows,
                )
                completed += 1
                print(
                    json.dumps(
                        {
                            "snapshot": str(path),
                            "sequence": payload["sequence"],
                            "as_of_ms": payload["as_of_ms"],
                            "score_count": payload["score_count"],
                            "event_candidate_count": payload["event_candidate_count"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                if max_cycles is not None and completed >= max_cycles:
                    break
                remaining = config.poll_interval_seconds - (time.monotonic() - cycle_started)
                if remaining > 0:
                    time.sleep(remaining)
            print(json.dumps(_status_from_chain(chain_state, config=config), indent=2, sort_keys=True))
            return 0
    except ImmutableBarConflict as exc:
        print(json.dumps({"ok": False, "terminal": True, "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True), file=sys.stderr)
        return 3
    except (EventUniverseError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
