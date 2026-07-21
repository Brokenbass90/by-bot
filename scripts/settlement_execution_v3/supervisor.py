"""Single-process, fail-closed supervisor for settlement_execution_v3.

The supervisor has no networking dependency.  It consumes one local bundle of
normalized public responses and moves it through the ten frozen stages under a
single non-blocking flock.
"""

from __future__ import annotations

import copy
import json
import math
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .roi import build_roi
from .scanner import (
    InputContractError,
    VENUES,
    build_funding_snapshot,
    build_metadata_snapshot,
    scan_candidates,
)
from .shadow import (
    MODEL_VERSION,
    close_due_positions,
    derive_state,
    open_new_positions,
    reconcile_settlements,
)
from .storage import (
    ExclusiveFileLock,
    StorageError,
    append_jsonl_idempotent,
    atomic_write_json,
    read_json,
    read_jsonl,
    read_verified_json,
    sha256_file,
    sha256_json,
    write_immutable_json,
)
from .validator import validate_candidates


SCHEMA_VERSION = "settlement_execution_v3_run_manifest_v1"
PUBLIC_BUNDLE_SCHEMA = "settlement_execution_v3_public_bundle_v1"
STAGE_ORDER = (
    "metadata_snapshot",
    "funding_snapshot",
    "scan",
    "validate",
    "update_open_positions_and_settlements",
    "close_due_positions",
    "open_new_positions",
    "commit_state_and_append_receipts",
    "build_roi",
    "publish_latest_manifest",
)

StageHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc_ms(value: Any, field: str) -> int:
    if not isinstance(value, str) or not value:
        raise InputContractError(f"{field} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputContractError(f"invalid {field}: {value}") from exc
    if parsed.tzinfo is None:
        raise InputContractError(f"{field} must include a timezone")
    return int(parsed.timestamp() * 1000)


class AlreadyRunning(RuntimeError):
    """Raised when another v3 supervisor owns the station flock."""


class StageFailure(RuntimeError):
    """A stage failed after an immutable failed-run manifest was produced."""

    def __init__(self, stage: str, run_id: str, manifest_path: Path, cause: BaseException):
        super().__init__(f"{stage} failed for {run_id}: {type(cause).__name__}: {cause}")
        self.stage = stage
        self.run_id = run_id
        self.manifest_path = manifest_path
        self.cause = cause


@dataclass(frozen=True)
class ArtifactRef:
    path: Path
    sha256: str


class SettlementExecutionV3Supervisor:
    def __init__(
        self,
        *,
        runtime_root: Path,
        config_path: Path,
        stage_overrides: Mapping[str, StageHandler] | None = None,
        stage_observer: Callable[[str], None] | None = None,
    ):
        self.runtime_root = Path(runtime_root)
        self.config_path = Path(config_path)
        self.runs_dir = self.runtime_root / "runs"
        self.state_path = self.runtime_root / "state" / "state.json"
        self.funding_receipts_path = (
            self.runtime_root / "receipts" / "funding_receipts.jsonl"
        )
        self.cycle_receipts_path = (
            self.runtime_root / "receipts" / "cycle_receipts.jsonl"
        )
        self.latest_path = self.runtime_root / "latest.json"
        self.lock_path = self.runtime_root / "supervisor.lock"
        self.stage_observer = stage_observer
        handlers: dict[str, StageHandler] = {
            "metadata_snapshot": self._metadata_snapshot,
            "funding_snapshot": self._funding_snapshot,
            "scan": self._scan,
            "validate": self._validate,
            "update_open_positions_and_settlements": self._update,
            "close_due_positions": self._close,
            "open_new_positions": self._open,
            "commit_state_and_append_receipts": self._commit,
            "build_roi": self._roi,
            "publish_latest_manifest": self._publication_payload,
        }
        for name, handler in (stage_overrides or {}).items():
            if name not in STAGE_ORDER:
                raise ValueError(f"unknown v3 stage override: {name}")
            handlers[name] = handler
        self._handlers = handlers

    @staticmethod
    def _validate_config(config: dict[str, Any]) -> None:
        exact = {
            "schema_version": "settlement_execution_v3_config_v1",
            "model_version": MODEL_VERSION,
            "research_only": True,
            "network_calls": False,
            "private_api_calls": False,
            "orders_enabled": False,
            "transfers_enabled": False,
            "withdrawals_enabled": False,
            "live_capital_usd": 0,
        }
        for field, expected in exact.items():
            if config.get(field) != expected:
                raise InputContractError(
                    f"unsafe or invalid config {field}: expected {expected!r}"
                )
        if (config.get("roi") or {}).get("monetary_projection_enabled") is not False:
            raise InputContractError("v3 research skeleton forbids monetary projections")
        required_positive = (
            ("ranking", "minimum_predicted_spread_apr_pct"),
            ("execution", "virtual_notional_usd_per_leg"),
            ("execution", "virtual_hold_hours"),
            ("execution", "max_book_age_ms"),
            ("execution", "max_pair_skew_ms"),
            ("execution", "max_predicted_age_ms"),
            ("execution", "max_predicted_pair_skew_ms"),
            ("execution", "max_actual_basis_pct"),
            ("execution", "max_entry_slippage_bps_per_leg"),
            ("execution", "max_open_virtual_routes"),
            ("settlement", "max_missing_receipt_attempts"),
            ("exit_retry", "deadline_ms"),
            ("exit_retry", "max_attempts"),
        )
        for section, field in required_positive:
            value = (config.get(section) or {}).get(field)
            try:
                parsed = float(value)
            except (TypeError, ValueError) as exc:
                raise InputContractError(f"config {section}.{field} must be numeric") from exc
            if not math.isfinite(parsed) or parsed <= 0:
                raise InputContractError(f"config {section}.{field} must be positive")
        for venue in sorted(VENUES):
            fee = (config.get("venue_fee_contracts") or {}).get(venue)
            if not isinstance(fee, dict):
                raise InputContractError(f"missing {venue} fee contract")
            if fee.get("fee_kind") != "assumed_conservative_public_only":
                raise InputContractError(f"{venue} fee must be explicitly assumed")
            for field in ("entry_fee_bps", "exit_fee_bps"):
                try:
                    value = float(fee[field])
                except (KeyError, TypeError, ValueError) as exc:
                    raise InputContractError(f"invalid {venue} {field}") from exc
                if not math.isfinite(value) or value < 0:
                    raise InputContractError(f"invalid {venue} {field}")
            _parse_utc_ms(fee.get("valid_at_utc"), f"{venue}.valid_at_utc")
            if not str(fee.get("source") or ""):
                raise InputContractError(f"missing {venue} fee source")

    @staticmethod
    def _normalize_public_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
        guards = {
            "schema_version": PUBLIC_BUNDLE_SCHEMA,
            "research_only": True,
            "source_policy": "public_endpoints_only",
            "private_api_calls": False,
            "authenticated_requests": False,
            "orders_or_transfers": False,
        }
        for field, expected in guards.items():
            if bundle.get(field) != expected:
                raise InputContractError(
                    f"public bundle guard {field} must equal {expected!r}"
                )
        as_of_utc = bundle.get("as_of_utc")
        as_of_ms = _parse_utc_ms(as_of_utc, "as_of_utc")
        responses = bundle.get("responses")
        if not isinstance(responses, list):
            raise InputContractError("public bundle responses must be a list")
        allowed_endpoint_classes = {
            "instrument_metadata",
            "predicted_funding",
            "funding_history",
            "validation_orderbook",
            "entry_orderbook",
            "exit_orderbook",
        }
        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(responses):
            if not isinstance(raw, dict):
                raise InputContractError(f"public response {index} must be an object")
            if raw.get("public") is not True:
                raise InputContractError(f"public response {index} is not marked public")
            venue = str(raw.get("venue") or "").lower()
            endpoint_class = str(raw.get("endpoint_class") or "")
            if venue not in VENUES:
                raise InputContractError(f"unsupported public response venue: {venue}")
            if endpoint_class not in allowed_endpoint_classes:
                raise InputContractError(
                    f"unsupported public endpoint class: {endpoint_class}"
                )
            try:
                exchange_timestamp_ms = int(raw.get("exchange_timestamp_ms"))
            except (TypeError, ValueError) as exc:
                raise InputContractError(
                    f"response {index} missing exchange/server timestamp"
                ) from exc
            if exchange_timestamp_ms <= 0:
                raise InputContractError(
                    f"response {index} exchange/server timestamp must be positive"
                )
            received_at_utc = raw.get("received_at_utc")
            received_ms = _parse_utc_ms(received_at_utc, "received_at_utc")
            if received_ms > as_of_ms:
                raise InputContractError(
                    f"response {index} was received after bundle as_of_utc"
                )
            if exchange_timestamp_ms > as_of_ms:
                raise InputContractError(
                    f"response {index} exchange/server timestamp is after bundle as_of_utc"
                )
            payload = raw.get("normalized_payload")
            if not isinstance(payload, dict):
                raise InputContractError(
                    f"response {index} normalized_payload must be an object"
                )
            normalized.append(
                {
                    "venue": venue,
                    "endpoint_class": endpoint_class,
                    "public": True,
                    "exchange_timestamp_ms": exchange_timestamp_ms,
                    "received_at_utc": received_at_utc,
                    "received_timestamp_ms": received_ms,
                    "normalized_payload_sha256": sha256_json(payload),
                    "normalized_payload": copy.deepcopy(payload),
                }
            )
        return {
            "schema_version": PUBLIC_BUNDLE_SCHEMA,
            "research_only": True,
            "as_of_utc": as_of_utc,
            "as_of_ms": as_of_ms,
            "responses": normalized,
        }

    @staticmethod
    def _public_manifest_rows(public_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "venue": response["venue"],
                "endpoint_class": response["endpoint_class"],
                "exchange_or_server_timestamp_ms": response[
                    "exchange_timestamp_ms"
                ],
                "local_received_at_utc": response["received_at_utc"],
                "normalized_payload_sha256": response[
                    "normalized_payload_sha256"
                ],
            }
            for response in public_snapshot.get("responses") or []
        ]

    def _git_sha(self) -> str:
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parents[2],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            return "unavailable"
        return completed.stdout.strip() or "unavailable"

    @staticmethod
    def _module_hashes() -> dict[str, str]:
        package = Path(__file__).resolve().parent
        scripts_root = package.parent
        files = {
            "package_init": package / "__init__.py",
            "scanner": package / "scanner.py",
            "validator": package / "validator.py",
            "shadow": package / "shadow.py",
            "roi": package / "roi.py",
            "storage": package / "storage.py",
            "supervisor": package / "supervisor.py",
            "runner": scripts_root / "run_settlement_execution_v3.py",
        }
        return {name: sha256_file(path) for name, path in files.items()}

    @staticmethod
    def _metrics(output: dict[str, Any]) -> dict[str, Any]:
        metrics = output.get("metrics")
        return copy.deepcopy(metrics) if isinstance(metrics, dict) else {}

    @staticmethod
    def _row_counts(name: str, output: dict[str, Any]) -> dict[str, int]:
        if name == "metadata_snapshot":
            return {"metadata_records": len(output.get("records") or [])}
        if name == "funding_snapshot":
            return {
                "predicted_funding_records": len(output.get("predicted") or []),
                "public_settlement_records": len(
                    output.get("settlement_history") or []
                ),
            }
        if name == "scan":
            return {"candidates": len(output.get("candidates") or [])}
        if name == "validate":
            return {"accepted": len(output.get("accepted") or [])}
        if name in {
            "update_open_positions_and_settlements",
            "close_due_positions",
            "open_new_positions",
        }:
            return {
                "positions": len((output.get("state") or {}).get("positions") or []),
                "new_funding_receipts": len(
                    output.get("new_funding_receipts") or []
                ),
                "new_cycle_receipts": len(output.get("new_cycle_receipts") or []),
            }
        if name == "commit_state_and_append_receipts":
            return {
                "positions": len((output.get("state") or {}).get("positions") or [])
            }
        if name == "build_roi":
            return {
                "eligible_closed_cycles": int(
                    output.get("eligible_closed_cycles") or 0
                ),
                "excluded_cycles": int(output.get("excluded_cycles") or 0),
            }
        if name == "publish_latest_manifest":
            return {"latest_pointer": 1}
        return {}

    def _artifact(
        self, run_dir: Path, relative_path: str, value: Any
    ) -> ArtifactRef:
        path = run_dir / relative_path
        digest = write_immutable_json(path, value)
        return ArtifactRef(path=path, sha256=digest)

    @staticmethod
    def _load_inputs(refs: Mapping[str, ArtifactRef]) -> dict[str, Any]:
        return {
            name: read_verified_json(ref.path, ref.sha256) for name, ref in refs.items()
        }

    def _run_stage(
        self,
        *,
        name: str,
        position: int,
        refs: Mapping[str, ArtifactRef],
        run_dir: Path,
        context: dict[str, Any],
        manifest: dict[str, Any],
    ) -> ArtifactRef:
        started = _utc_now()
        input_hashes = {key: value.sha256 for key, value in sorted(refs.items())}
        if self.stage_observer:
            self.stage_observer(name)
        try:
            inputs = self._load_inputs(refs)
            output = self._handlers[name](inputs, context)
            if not isinstance(output, dict):
                raise InputContractError(f"stage {name} did not return an object")
            ref = self._artifact(
                run_dir, f"stages/{position:02d}_{name}.json", output
            )
        except BaseException as exc:
            manifest["stages"].append(
                {
                    "position": position,
                    "name": name,
                    "status": "failed",
                    "started_at_utc": started,
                    "completed_at_utc": _utc_now(),
                    "input_artifact_sha256": input_hashes,
                    "output_sha256": None,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            raise
        manifest["stages"].append(
            {
                "position": position,
                "name": name,
                "status": "complete",
                "started_at_utc": started,
                "completed_at_utc": _utc_now(),
                "input_artifact_sha256": input_hashes,
                "output_sha256": ref.sha256,
                "metrics": self._metrics(output),
                "row_counts": self._row_counts(name, output),
                "reject_counters": copy.deepcopy(
                    output.get("reject_counters") or {}
                ),
            }
        )
        return ref

    def _metadata_snapshot(
        self, inputs: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        public_snapshot = self._normalize_public_bundle(inputs["public_input"])
        metadata = build_metadata_snapshot(public_snapshot)
        metadata["public_snapshot"] = public_snapshot
        return metadata

    @staticmethod
    def _funding_snapshot(
        inputs: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        metadata = inputs["metadata_snapshot"]
        return build_funding_snapshot(metadata["public_snapshot"], metadata)

    @staticmethod
    def _scan(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return scan_candidates(
            inputs["metadata_snapshot"],
            inputs["funding_snapshot"],
            inputs["config"],
        )

    @staticmethod
    def _validate(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return validate_candidates(
            list(inputs["scan"].get("candidates") or []),
            inputs["metadata_snapshot"]["public_snapshot"],
            inputs["config"],
            phase="validation_orderbook",
        )

    @staticmethod
    def _update(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return reconcile_settlements(
            inputs["state_before"],
            inputs["funding_snapshot"],
            list(inputs["funding_receipts_before"]),
            as_of_ms=context["as_of_ms"],
            as_of_utc=context["as_of_utc"],
            run_id=context["run_id"],
            config=inputs["config"],
        )

    @staticmethod
    def _close(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return close_due_positions(
            inputs["settlement_update"],
            inputs["metadata_snapshot"]["public_snapshot"],
            as_of_ms=context["as_of_ms"],
            as_of_utc=context["as_of_utc"],
            run_id=context["run_id"],
            config=inputs["config"],
        )

    @staticmethod
    def _open(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return open_new_positions(
            inputs["close_update"],
            inputs["validation"],
            inputs["metadata_snapshot"]["public_snapshot"],
            as_of_utc=context["as_of_utc"],
            run_id=context["run_id"],
            config=inputs["config"],
        )

    def _commit(self, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        update = inputs["open_update"]
        funding_added, funding_skipped = append_jsonl_idempotent(
            self.funding_receipts_path,
            list(update.get("new_funding_receipts") or []),
        )
        cycles_added, cycles_skipped = append_jsonl_idempotent(
            self.cycle_receipts_path,
            list(update.get("new_cycle_receipts") or []),
        )
        funding_receipts = read_jsonl(self.funding_receipts_path)
        cycle_receipts = read_jsonl(self.cycle_receipts_path)
        state = derive_state(
            cycle_receipts,
            funding_receipts,
            as_of_utc=context["as_of_utc"],
        )
        state_hash = atomic_write_json(self.state_path, state)
        return {
            "schema_version": "settlement_execution_v3_commit_v1",
            "state": state,
            "committed_state_sha256": state_hash,
            "funding_receipts_ledger_sha256": sha256_file(self.funding_receipts_path)
            if self.funding_receipts_path.exists()
            else None,
            "cycle_receipts_ledger_sha256": sha256_file(self.cycle_receipts_path)
            if self.cycle_receipts_path.exists()
            else None,
            "metrics": {
                "funding_receipts_appended": funding_added,
                "funding_receipts_idempotent_replays": funding_skipped,
                "cycle_receipts_appended": cycles_added,
                "cycle_receipts_idempotent_replays": cycles_skipped,
                **state["metrics"],
            },
        }

    @staticmethod
    def _roi(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return build_roi(inputs["commit"]["state"])

    @staticmethod
    def _publication_payload(
        inputs: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "schema_version": "settlement_execution_v3_latest_pointer_v1",
            "model_version": MODEL_VERSION,
            "research_only": True,
            "run_id": context["run_id"],
            "completed_at_utc": context["publication_completed_at_utc"],
            "immutable_manifest_relative_path": context[
                "manifest_relative_path"
            ],
            "committed_state_sha256": inputs["commit"][
                "committed_state_sha256"
            ],
            "roi_output_sha256": context["roi_output_sha256"],
            "edge_proven": False,
            "ready_for_live": False,
        }

    def run(self, public_bundle: dict[str, Any]) -> dict[str, Any]:
        try:
            lock = ExclusiveFileLock(self.lock_path)
            lock.__enter__()
        except BlockingIOError as exc:
            raise AlreadyRunning(
                f"another settlement_execution_v3 supervisor holds {self.lock_path}"
            ) from exc
        try:
            return self._run_locked(public_bundle)
        finally:
            lock.__exit__(None, None, None)

    def _run_locked(self, public_bundle: dict[str, Any]) -> dict[str, Any]:
        started_at = _utc_now()
        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            + "-"
            + uuid.uuid4().hex[:12]
        )
        run_dir = self.runs_dir / run_id
        manifest_path = run_dir / "manifest.json"
        config = read_json(self.config_path)
        if not isinstance(config, dict):
            raise InputContractError("v3 config root must be an object")
        self._validate_config(config)
        config_hash = sha256_file(self.config_path)
        as_of_utc = str(public_bundle.get("as_of_utc") or "")
        as_of_ms = _parse_utc_ms(as_of_utc, "as_of_utc")

        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "model_version": MODEL_VERSION,
            "run_id": run_id,
            "status": "running",
            "started_at_utc": started_at,
            "completed_at_utc": None,
            "research_guards": {
                "research_only": True,
                "network_calls": False,
                "private_api_calls": False,
                "orders": False,
                "transfers": False,
                "withdrawals": False,
                "live_capital_usd": 0,
                "v2_state_read_or_written": False,
            },
            "code": {
                "git_sha": self._git_sha(),
                "module_sha256": self._module_hashes(),
            },
            "config_sha256": config_hash,
            "public_input_sha256": sha256_json(public_bundle),
            "public_responses": [],
            "previous_state_sha256": sha256_file(self.state_path)
            if self.state_path.exists()
            else None,
            "committed_state_sha256": None,
            "state_rebuilt_from_append_only_receipts": False,
            "stages": [],
        }
        context = {
            "config": config,
            "run_id": run_id,
            "as_of_utc": as_of_utc,
            "as_of_ms": as_of_ms,
        }
        current_stage = "initialization"
        try:
            public_ref = self._artifact(run_dir, "inputs/public_input.json", public_bundle)
            config_ref = self._artifact(run_dir, "inputs/config.json", config)
            cycle_before = read_jsonl(self.cycle_receipts_path)
            funding_before = read_jsonl(self.funding_receipts_path)
            persisted_state = None
            if self.state_path.exists():
                persisted_state = read_json(self.state_path)
                if not isinstance(persisted_state, dict):
                    raise StorageError("persisted v3 state is not an object")
                if persisted_state.get("model_version") != MODEL_VERSION:
                    raise StorageError("persisted state has a foreign model version")
            comparison_as_of = (
                str(persisted_state.get("as_of_utc"))
                if persisted_state is not None
                else as_of_utc
            )
            rebuilt = derive_state(
                cycle_before, funding_before, as_of_utc=comparison_as_of
            )
            if persisted_state is not None and sha256_json(persisted_state) != sha256_json(rebuilt):
                manifest["state_rebuilt_from_append_only_receipts"] = True
            rebuilt["as_of_utc"] = as_of_utc
            state_before_ref = self._artifact(
                run_dir, "inputs/state_before.json", rebuilt
            )
            cycle_before_ref = self._artifact(
                run_dir, "inputs/cycle_receipts_before.json", cycle_before
            )
            funding_before_ref = self._artifact(
                run_dir, "inputs/funding_receipts_before.json", funding_before
            )

            refs: dict[str, ArtifactRef] = {
                "public_input": public_ref,
                "config": config_ref,
                "state_before": state_before_ref,
                "cycle_receipts_before": cycle_before_ref,
                "funding_receipts_before": funding_before_ref,
            }
            plan: list[tuple[str, dict[str, str], str]] = [
                ("metadata_snapshot", {"public_input": "public_input"}, "metadata_snapshot"),
                (
                    "funding_snapshot",
                    {"metadata_snapshot": "metadata_snapshot"},
                    "funding_snapshot",
                ),
                (
                    "scan",
                    {
                        "metadata_snapshot": "metadata_snapshot",
                        "funding_snapshot": "funding_snapshot",
                        "config": "config",
                    },
                    "scan",
                ),
                (
                    "validate",
                    {
                        "scan": "scan",
                        "metadata_snapshot": "metadata_snapshot",
                        "config": "config",
                    },
                    "validation",
                ),
                (
                    "update_open_positions_and_settlements",
                    {
                        "state_before": "state_before",
                        "funding_snapshot": "funding_snapshot",
                        "funding_receipts_before": "funding_receipts_before",
                        "config": "config",
                    },
                    "settlement_update",
                ),
                (
                    "close_due_positions",
                    {
                        "settlement_update": "settlement_update",
                        "metadata_snapshot": "metadata_snapshot",
                        "config": "config",
                    },
                    "close_update",
                ),
                (
                    "open_new_positions",
                    {
                        "close_update": "close_update",
                        "validation": "validation",
                        "metadata_snapshot": "metadata_snapshot",
                        "config": "config",
                    },
                    "open_update",
                ),
                (
                    "commit_state_and_append_receipts",
                    {
                        "open_update": "open_update",
                        "cycle_receipts_before": "cycle_receipts_before",
                        "funding_receipts_before": "funding_receipts_before",
                    },
                    "commit",
                ),
                ("build_roi", {"commit": "commit"}, "roi"),
            ]
            for position, (stage_name, input_names, output_name) in enumerate(plan, 1):
                current_stage = stage_name
                stage_refs = {name: refs[source] for name, source in input_names.items()}
                refs[output_name] = self._run_stage(
                    name=stage_name,
                    position=position,
                    refs=stage_refs,
                    run_dir=run_dir,
                    context=context,
                    manifest=manifest,
                )
                if stage_name == "metadata_snapshot":
                    metadata = read_verified_json(
                        refs[output_name].path, refs[output_name].sha256
                    )
                    manifest["public_responses"] = self._public_manifest_rows(
                        metadata["public_snapshot"]
                    )
                elif stage_name == "commit_state_and_append_receipts":
                    commit = read_verified_json(
                        refs[output_name].path, refs[output_name].sha256
                    )
                    manifest["committed_state_sha256"] = commit[
                        "committed_state_sha256"
                    ]

            completed_at = _utc_now()
            context.update(
                {
                    "publication_completed_at_utc": completed_at,
                    "manifest_relative_path": str(
                        manifest_path.relative_to(self.runtime_root)
                    ),
                    "roi_output_sha256": refs["roi"].sha256,
                }
            )
            current_stage = "publish_latest_manifest"
            refs["latest_pointer"] = self._run_stage(
                name="publish_latest_manifest",
                position=10,
                refs={"commit": refs["commit"], "roi": refs["roi"]},
                run_dir=run_dir,
                context=context,
                manifest=manifest,
            )
            manifest["status"] = "complete"
            manifest["completed_at_utc"] = completed_at
            manifest_hash = write_immutable_json(manifest_path, manifest)
            latest_payload = read_verified_json(
                refs["latest_pointer"].path, refs["latest_pointer"].sha256
            )
            atomic_write_json(self.latest_path, latest_payload)
            return {
                "run_id": run_id,
                "manifest_path": str(manifest_path),
                "manifest_sha256": manifest_hash,
                "latest_path": str(self.latest_path),
                "committed_state_sha256": manifest["committed_state_sha256"],
                "roi": read_verified_json(refs["roi"].path, refs["roi"].sha256),
            }
        except BaseException as exc:
            manifest["status"] = "failed"
            manifest["completed_at_utc"] = _utc_now()
            manifest["failure"] = {
                "stage": current_stage,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            if not manifest_path.exists():
                try:
                    write_immutable_json(manifest_path, manifest)
                except BaseException:
                    pass
            raise StageFailure(current_stage, run_id, manifest_path, exc) from exc
