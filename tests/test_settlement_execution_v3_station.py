from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.settlement_execution_v3 import (
    STAGE_ORDER,
    AlreadyRunning,
    SettlementExecutionV3Supervisor,
    StageFailure,
)
from scripts.settlement_execution_v3.scanner import build_metadata_snapshot
from scripts.settlement_execution_v3.storage import (
    ExclusiveFileLock,
    StorageError,
    append_jsonl_idempotent,
    read_json,
    read_jsonl,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    ROOT / "configs/preregistered/settlement_execution_v3_research_v1.json"
)
BASE_MS = 1_784_636_400_000


def _iso(timestamp_ms: int) -> str:
    return (
        datetime.fromtimestamp(timestamp_ms / 1000.0, timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _response(
    venue: str,
    endpoint_class: str,
    payload: dict,
    *,
    as_of_ms: int,
    server_ms: int | None = None,
) -> dict:
    return {
        "venue": venue,
        "endpoint_class": endpoint_class,
        "public": True,
        "exchange_timestamp_ms": server_ms or as_of_ms - 100,
        "received_at_utc": _iso(as_of_ms - 50),
        "normalized_payload": payload,
    }


def _metadata(venue: str, next_settlement_ms: int, *, stock: bool = False) -> dict:
    common = {
        "symbol": "BTCUSDT" if not stock else "SKHYNIXUSDT",
        "asset_class": "crypto" if not stock else "equity",
        "underlying_id": "BTC" if not stock else "KR:000660",
        "identity_mapping_version": "public_identity_v1",
        "funding_interval_hours": 1.0,
        "next_settlement_ts_ms": next_settlement_ms,
        "quote_asset": "USDT",
        "settle_asset": "USDT",
    }
    if venue == "bybit":
        return {
            **common,
            "contract_type": "LinearPerpetual",
            "status": "Trading",
            "symbol_type": "stock" if stock else "crypto",
        }
    if venue == "binance":
        return {
            **common,
            "contract_type": "TRADIFI_PERPETUAL" if stock else "PERPETUAL",
            "status": "TRADING",
            "underlying_type": "KR_EQUITY" if stock else "COIN",
        }
    raise AssertionError(venue)


def _book(symbol: str = "BTCUSDT") -> dict:
    return {
        "symbol": symbol,
        "bids": [["100.0", "20.0"]],
        "asks": [["100.0", "20.0"]],
    }


def _bundle(
    *,
    as_of_ms: int,
    next_settlement_ms: int,
    history: list[tuple[str, float, int] | tuple[str, float, int, float]] | None = None,
    include_exit_books: bool = False,
) -> dict:
    responses = [
        _response(
            "bybit",
            "instrument_metadata",
            {"records": [_metadata("bybit", next_settlement_ms)]},
            as_of_ms=as_of_ms,
        ),
        _response(
            "binance",
            "instrument_metadata",
            {"records": [_metadata("binance", next_settlement_ms)]},
            as_of_ms=as_of_ms,
        ),
        _response(
            "bybit",
            "predicted_funding",
            {
                "records": [
                    {
                        "symbol": "BTCUSDT",
                        "funding_rate": 0.001,
                        "funding_interval_hours": 1.0,
                        "next_settlement_ts_ms": next_settlement_ms,
                    }
                ]
            },
            as_of_ms=as_of_ms,
        ),
        _response(
            "binance",
            "predicted_funding",
            {
                "records": [
                    {
                        "symbol": "BTCUSDT",
                        "funding_rate": 0.0,
                        "funding_interval_hours": 1.0,
                        "next_settlement_ts_ms": next_settlement_ms,
                    }
                ]
            },
            as_of_ms=as_of_ms,
        ),
    ]
    history_by_venue = {"bybit": [], "binance": []}
    for item in history or []:
        venue, rate, settlement_ms = item[:3]
        settlement_mark_price = float(item[3]) if len(item) == 4 else 100.0
        history_by_venue[venue].append(
            {
                "symbol": "BTCUSDT",
                "funding_rate": rate,
                "settlement_ts_ms": settlement_ms,
                "settlement_mark_price": settlement_mark_price,
                "settlement_mark_ts_ms": settlement_ms,
            }
        )
    for venue in ("bybit", "binance"):
        responses.append(
            _response(
                venue,
                "funding_history",
                {"records": history_by_venue[venue]},
                as_of_ms=as_of_ms,
            )
        )
        for phase in ("validation_orderbook", "entry_orderbook"):
            responses.append(
                _response(venue, phase, _book(), as_of_ms=as_of_ms)
            )
        if include_exit_books:
            responses.append(
                _response(venue, "exit_orderbook", _book(), as_of_ms=as_of_ms)
            )
    return {
        "schema_version": "settlement_execution_v3_public_bundle_v1",
        "research_only": True,
        "source_policy": "public_endpoints_only",
        "private_api_calls": False,
        "authenticated_requests": False,
        "orders_or_transfers": False,
        "as_of_utc": _iso(as_of_ms),
        "responses": responses,
    }


def _supervisor(tmp_path: Path, **kwargs) -> SettlementExecutionV3Supervisor:
    return SettlementExecutionV3Supervisor(
        runtime_root=tmp_path / "runtime",
        config_path=kwargs.pop("config_path", DEFAULT_CONFIG),
        **kwargs,
    )


def test_single_supervisor_is_flocked(tmp_path: Path):
    supervisor = _supervisor(tmp_path)
    with ExclusiveFileLock(supervisor.lock_path):
        with pytest.raises(AlreadyRunning):
            supervisor.run(
                _bundle(
                    as_of_ms=BASE_MS,
                    next_settlement_ms=BASE_MS + 60_000,
                )
            )


def test_stage_failure_is_sequential_and_leaves_latest_untouched(tmp_path: Path):
    observed: list[str] = []

    def fail_validate(inputs, context):
        raise RuntimeError("injected validation failure")

    supervisor = _supervisor(
        tmp_path,
        stage_overrides={"validate": fail_validate},
        stage_observer=observed.append,
    )
    supervisor.latest_path.parent.mkdir(parents=True)
    supervisor.latest_path.write_text('{"sentinel":"old"}\n', encoding="utf-8")
    with pytest.raises(StageFailure) as caught:
        supervisor.run(
            _bundle(
                as_of_ms=BASE_MS,
                next_settlement_ms=BASE_MS + 60_000,
            )
        )

    assert observed == list(STAGE_ORDER[:4])
    assert read_json(supervisor.latest_path) == {"sentinel": "old"}
    assert not supervisor.state_path.exists()
    manifest = read_json(caught.value.manifest_path)
    assert manifest["status"] == "failed"
    assert manifest["failure"]["stage"] == "validate"
    assert [row["name"] for row in manifest["stages"]] == list(STAGE_ORDER[:4])


def test_manifest_lineage_and_new_v3_paths_are_complete(tmp_path: Path):
    supervisor = _supervisor(tmp_path)
    result = supervisor.run(
        _bundle(
            as_of_ms=BASE_MS,
            next_settlement_ms=BASE_MS + 60_000,
        )
    )
    manifest_path = Path(result["manifest_path"])
    before = manifest_path.read_bytes()
    manifest = read_json(manifest_path)

    assert manifest["model_version"] == "settlement_execution_v3"
    assert manifest["status"] == "complete"
    assert manifest["research_guards"]["v2_state_read_or_written"] is False
    assert set(manifest["code"]["module_sha256"]) == {
        "package_init",
        "scanner",
        "validator",
        "shadow",
        "roi",
        "storage",
        "supervisor",
        "runner",
    }
    assert all(len(value) == 64 for value in manifest["code"]["module_sha256"].values())
    assert len(manifest["public_responses"]) == len(
        _bundle(as_of_ms=BASE_MS, next_settlement_ms=BASE_MS + 60_000)[
            "responses"
        ]
    )
    assert all(
        len(row["normalized_payload_sha256"]) == 64
        and row["exchange_or_server_timestamp_ms"] > 0
        and row["local_received_at_utc"].endswith("Z")
        for row in manifest["public_responses"]
    )
    assert [row["name"] for row in manifest["stages"]] == list(STAGE_ORDER)
    assert all(row["status"] == "complete" for row in manifest["stages"])
    assert all(row["output_sha256"] for row in manifest["stages"])
    assert all(row["row_counts"] for row in manifest["stages"])
    assert manifest["committed_state_sha256"] == result["committed_state_sha256"]
    assert read_json(supervisor.latest_path)["run_id"] == result["run_id"]

    # A later run creates a new immutable directory and cannot rewrite lineage.
    supervisor.run(
        _bundle(
            as_of_ms=BASE_MS + 1000,
            next_settlement_ms=BASE_MS + 60_000,
        )
    )
    assert manifest_path.read_bytes() == before


def test_stock_and_unknown_taxonomy_fail_closed_before_scan():
    as_of_ms = BASE_MS
    raw = {
        "schema_version": "settlement_execution_v3_public_bundle_v1",
        "research_only": True,
        "source_policy": "public_endpoints_only",
        "private_api_calls": False,
        "authenticated_requests": False,
        "orders_or_transfers": False,
        "as_of_utc": _iso(as_of_ms),
        "responses": [
            _response(
                "bybit",
                "instrument_metadata",
                {"records": [_metadata("bybit", as_of_ms + 60_000, stock=True)]},
                as_of_ms=as_of_ms,
            ),
            _response(
                "binance",
                "instrument_metadata",
                {"records": [_metadata("binance", as_of_ms + 60_000, stock=True)]},
                as_of_ms=as_of_ms,
            ),
        ],
    }
    public = SettlementExecutionV3Supervisor._normalize_public_bundle(raw)
    metadata = build_metadata_snapshot(public)
    assert metadata["records"] == []
    assert metadata["metrics"]["reject_count"] == 2
    assert metadata["reject_counters"]["non_crypto_asset_class"] == 2


def test_missing_public_settlement_receipts_stay_pending_then_credit_exact_history(
    tmp_path: Path,
):
    supervisor = _supervisor(tmp_path)
    settlement_ms = BASE_MS + 60_000
    supervisor.run(
        _bundle(as_of_ms=BASE_MS, next_settlement_ms=settlement_ms)
    )

    # After the due timestamp, empty public history means unknown, not zero.
    supervisor.run(
        _bundle(
            as_of_ms=settlement_ms + 1000,
            next_settlement_ms=settlement_ms + 3_600_000,
            history=[],
        )
    )
    state = read_json(supervisor.state_path)
    position = state["positions"][0]
    assert position["settlement_status"] == "settlement_pending"
    assert len(position["pending_settlements"]) == 2
    assert position["earned_funding_usd"] == 0.0
    assert read_jsonl(supervisor.funding_receipts_path) == []
    assert read_json(supervisor.latest_path)["edge_proven"] is False

    # Exact public history rows create one idempotent receipt per leg.
    result = supervisor.run(
        _bundle(
            as_of_ms=settlement_ms + 2000,
            next_settlement_ms=settlement_ms + 3_600_000,
            history=[
                ("bybit", 0.0007, settlement_ms),
                ("binance", -0.0002, settlement_ms),
            ],
        )
    )
    receipts = read_jsonl(supervisor.funding_receipts_path)
    assert len(receipts) == 2
    assert all(row["actual_public_settlement_receipt"] is True for row in receipts)
    state = read_json(supervisor.state_path)
    position = state["positions"][0]
    assert position["settlement_status"] == "complete"
    assert position["pending_settlements"] == []
    assert position["earned_funding_usd"] == pytest.approx(0.09)
    assert result["roi"]["eligible_closed_cycles"] == 0


def test_receipt_append_is_idempotent_and_conflicts_fail_closed(tmp_path: Path):
    path = tmp_path / "receipts.jsonl"
    receipt = {"idempotency_key": "cycle|venue|symbol|short|1", "value": 1}
    assert append_jsonl_idempotent(path, [receipt]) == (1, 0)
    assert append_jsonl_idempotent(path, [receipt]) == (0, 1)
    assert len(read_jsonl(path)) == 1
    with pytest.raises(StorageError, match="conflicting receipt replay"):
        append_jsonl_idempotent(path, [{**receipt, "value": 2}])


def test_executable_close_uses_public_funding_and_total_capital_denominator(
    tmp_path: Path,
):
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    config["execution"]["virtual_hold_hours"] = 61.0 / 3600.0
    config["execution"]["minimum_predicted_net_bps_pair_sum"] = -100.0
    config_path = tmp_path / "config-close.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    supervisor = _supervisor(tmp_path, config_path=config_path)
    settlement_ms = BASE_MS + 60_000

    supervisor.run(_bundle(as_of_ms=BASE_MS, next_settlement_ms=settlement_ms))
    result = supervisor.run(
        _bundle(
            as_of_ms=BASE_MS + 62_000,
            next_settlement_ms=settlement_ms + 3_600_000,
            history=[
                ("bybit", 0.0007, settlement_ms),
                ("binance", -0.0002, settlement_ms),
            ],
            include_exit_books=True,
        )
    )

    closed = [
        row
        for row in read_json(supervisor.state_path)["positions"]
        if row["status"] == "closed_complete"
    ]
    assert len(closed) == 1
    cycle = closed[0]
    assert cycle["price_pnl_usd"] == pytest.approx(0.0)
    assert cycle["earned_funding_usd"] == pytest.approx(0.09)
    assert cycle["fee_cost_usd"] == pytest.approx(0.4)
    assert cycle["total_deployed_capital_usd"] == pytest.approx(200.0)
    assert cycle["net_pnl_pct_total_deployed_capital"] == pytest.approx(-0.155)
    assert result["roi"]["eligible_closed_cycles"] == 1


def test_funding_uses_settlement_mark_position_value_not_entry_notional(
    tmp_path: Path,
):
    supervisor = _supervisor(tmp_path)
    settlement_ms = BASE_MS + 60_000
    supervisor.run(_bundle(as_of_ms=BASE_MS, next_settlement_ms=settlement_ms))

    supervisor.run(
        _bundle(
            as_of_ms=settlement_ms + 2000,
            next_settlement_ms=settlement_ms + 3_600_000,
            history=[
                ("bybit", 0.0007, settlement_ms, 120.0),
                ("binance", -0.0002, settlement_ms, 80.0),
            ],
        )
    )
    receipts = read_jsonl(supervisor.funding_receipts_path)
    by_venue = {row["venue"]: row for row in receipts}
    assert by_venue["bybit"]["settlement_position_value_usd"] == pytest.approx(120.0)
    assert by_venue["binance"]["settlement_position_value_usd"] == pytest.approx(80.0)
    assert by_venue["bybit"]["earned_funding_usd"] == pytest.approx(0.084)
    assert by_venue["binance"]["earned_funding_usd"] == pytest.approx(0.016)
    assert read_json(supervisor.state_path)["positions"][0][
        "earned_funding_usd"
    ] == pytest.approx(0.1)


def test_temporal_chain_rejects_validation_or_entry_before_predecessor(tmp_path: Path):
    validation_early = _bundle(
        as_of_ms=BASE_MS,
        next_settlement_ms=BASE_MS + 60_000,
    )
    for response in validation_early["responses"]:
        if response["endpoint_class"] == "validation_orderbook":
            response["exchange_timestamp_ms"] = BASE_MS - 200
            response["received_at_utc"] = _iso(BASE_MS - 100)
    validation_supervisor = SettlementExecutionV3Supervisor(
        runtime_root=tmp_path / "validation-runtime",
        config_path=DEFAULT_CONFIG,
    )
    result = validation_supervisor.run(validation_early)
    manifest = read_json(Path(result["manifest_path"]))
    validate_stage = next(row for row in manifest["stages"] if row["name"] == "validate")
    assert validate_stage["reject_counters"]["validation_before_signal"] == 1
    assert read_json(validation_supervisor.state_path)["positions"] == []

    entry_early = _bundle(
        as_of_ms=BASE_MS,
        next_settlement_ms=BASE_MS + 60_000,
    )
    for response in entry_early["responses"]:
        if response["endpoint_class"] == "entry_orderbook":
            response["exchange_timestamp_ms"] = BASE_MS - 200
            response["received_at_utc"] = _iso(BASE_MS - 100)
    entry_supervisor = SettlementExecutionV3Supervisor(
        runtime_root=tmp_path / "entry-runtime",
        config_path=DEFAULT_CONFIG,
    )
    entry_supervisor.run(entry_early)
    state = read_json(entry_supervisor.state_path)
    assert state["positions"] == []
    open_stage = read_json(
        sorted((tmp_path / "entry-runtime" / "runs").glob("*/stages/07_open_new_positions.json"))[0]
    )
    assert open_stage["metrics"]["entry_recheck_entry_before_validation"] == 1


def test_temporal_chain_rejects_stale_prediction_and_pre_settlement_history(
    tmp_path: Path,
):
    stale = _bundle(
        as_of_ms=BASE_MS,
        next_settlement_ms=BASE_MS + 60_000,
    )
    for response in stale["responses"]:
        if response["endpoint_class"] == "predicted_funding":
            response["exchange_timestamp_ms"] = BASE_MS - 6000
            response["received_at_utc"] = _iso(BASE_MS - 6000)
    stale_supervisor = SettlementExecutionV3Supervisor(
        runtime_root=tmp_path / "stale-runtime",
        config_path=DEFAULT_CONFIG,
    )
    stale_result = stale_supervisor.run(stale)
    stale_manifest = read_json(Path(stale_result["manifest_path"]))
    scan_stage = next(row for row in stale_manifest["stages"] if row["name"] == "scan")
    assert scan_stage["reject_counters"]["stale_or_future_predicted_funding"] == 2
    assert read_json(stale_supervisor.state_path)["positions"] == []

    settlement_ms = BASE_MS + 60_000
    settlement_supervisor = SettlementExecutionV3Supervisor(
        runtime_root=tmp_path / "settlement-runtime",
        config_path=DEFAULT_CONFIG,
    )
    settlement_supervisor.run(
        _bundle(as_of_ms=BASE_MS, next_settlement_ms=settlement_ms)
    )
    premature = _bundle(
        as_of_ms=settlement_ms + 2000,
        next_settlement_ms=settlement_ms + 3_600_000,
        history=[
            ("bybit", 0.0007, settlement_ms),
            ("binance", -0.0002, settlement_ms),
        ],
    )
    for response in premature["responses"]:
        if response["endpoint_class"] == "funding_history":
            response["exchange_timestamp_ms"] = settlement_ms - 1
            response["received_at_utc"] = _iso(settlement_ms - 1)
    premature_result = settlement_supervisor.run(premature)
    premature_manifest = read_json(Path(premature_result["manifest_path"]))
    funding_stage = next(
        row for row in premature_manifest["stages"] if row["name"] == "funding_snapshot"
    )
    assert funding_stage["reject_counters"]["history_observed_before_settlement"] == 2
    assert read_jsonl(settlement_supervisor.funding_receipts_path) == []
    assert read_json(settlement_supervisor.state_path)["positions"][0][
        "settlement_status"
    ] == "settlement_pending"


def test_exit_failure_never_creates_zero_pnl_and_becomes_invalid_after_bound(
    tmp_path: Path,
):
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    config["execution"]["virtual_hold_hours"] = 1.0 / 3600.0
    config["execution"]["minimum_predicted_net_bps_pair_sum"] = -100.0
    config["exit_retry"]["deadline_ms"] = 10_000
    config["exit_retry"]["max_attempts"] = 2
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    supervisor = _supervisor(tmp_path, config_path=config_path)
    settlement_ms = BASE_MS + 60_000

    supervisor.run(_bundle(as_of_ms=BASE_MS, next_settlement_ms=settlement_ms))
    supervisor.run(
        _bundle(as_of_ms=BASE_MS + 2000, next_settlement_ms=settlement_ms)
    )
    first = read_json(supervisor.state_path)["positions"][0]
    assert first["status"] == "close_pending_data"
    assert "price_pnl_usd" not in first

    result = supervisor.run(
        _bundle(as_of_ms=BASE_MS + 3000, next_settlement_ms=settlement_ms)
    )
    final = read_json(supervisor.state_path)["positions"][0]
    assert final["status"] == "invalid_exit_data"
    assert final["exit_execution_valid"] is False
    assert "price_pnl_usd" not in final
    assert result["roi"]["eligible_closed_cycles"] == 0
    assert result["roi"]["exclusion_counters"]["invalid_exit_data"] == 1
