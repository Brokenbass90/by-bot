#!/usr/bin/env python3
"""Tamper-evident, fail-closed lifecycle ledger for research experiments.

The ledger has research provenance authority only.  It cannot approve capital,
change risk, call a broker, or promote a strategy.  Every record is chained to
the previous record and every referenced artifact is hashed at append time.
Malformed rows, a broken hash chain, an out-of-order stage, changed artifacts,
duplicate terminal stages, or a non-zero independent audit fail closed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_ID = "research_experiment_lifecycle_v1"
AUTHORITY = "research_only_no_live_risk_order_or_promotion_authority"

STAGES = (
    "IDEA_REGISTERED",
    "OWNER_APPROVED",
    "PREREG_FROZEN",
    "SPEC_BOUND",
    "PREFLIGHT_PASSED",
    "PASSPORT_WRITTEN",
    "RESULT_WRITTEN",
    "INDEPENDENT_AUDIT_PASSED",
    "DECISION_ACCEPTED",
)
TERMINAL_REJECT = "DECISION_REJECTED"
AUDIT_FAILED = "INDEPENDENT_AUDIT_FAILED"


class LifecycleError(RuntimeError):
    """The ledger cannot be trusted or the requested transition is invalid."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_id(value: Any) -> str:
    experiment_id = str(value or "").strip()
    if not experiment_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in experiment_id):
        raise LifecycleError("experiment_id must contain only letters, digits, '_' or '-'")
    return experiment_id


def _resolve_artifacts(project_root: Path, paths: Iterable[str]) -> list[dict[str, Any]]:
    root = project_root.resolve()
    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in paths:
        if not isinstance(raw, str) or not raw.strip() or any(ch in raw for ch in "*?["):
            raise LifecycleError("artifact paths must be explicit non-glob strings")
        unresolved = Path(raw).expanduser()
        path = (unresolved if unresolved.is_absolute() else root / unresolved).resolve()
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise LifecycleError(f"artifact escapes project root: {path}") from exc
        if not path.is_file():
            raise LifecycleError(f"artifact is not a file: {path}")
        key = relative.as_posix()
        if key in seen:
            raise LifecycleError(f"duplicate artifact: {key}")
        seen.add(key)
        artifacts.append({"path": key, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    return artifacts


def _record_hash(record: Mapping[str, Any]) -> str:
    unsigned = dict(record)
    unsigned.pop("record_sha256", None)
    return _sha256_bytes(_canonical_json(unsigned))


class LifecycleLedger:
    """Append-only lifecycle ledger with a global SHA256 record chain."""

    def __init__(self, path: Path, *, project_root: Path) -> None:
        self.path = path.resolve()
        self.project_root = project_root.resolve()

    def read_verified(self, *, verify_artifacts: bool = False) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        previous: str | None = None
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    raise LifecycleError(f"blank ledger row at line {line_number}")
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LifecycleError(f"invalid JSON at ledger line {line_number}") from exc
                if not isinstance(record, dict) or record.get("schema_id") != SCHEMA_ID:
                    raise LifecycleError(f"invalid schema at ledger line {line_number}")
                if record.get("authority") != AUTHORITY:
                    raise LifecycleError(f"invalid authority at ledger line {line_number}")
                if record.get("previous_record_sha256") != previous:
                    raise LifecycleError(f"broken hash chain at ledger line {line_number}")
                expected = record.get("record_sha256")
                actual = _record_hash(record)
                if expected != actual:
                    raise LifecycleError(f"record hash mismatch at ledger line {line_number}")
                if verify_artifacts:
                    for artifact in record.get("artifacts") or []:
                        path = (self.project_root / artifact["path"]).resolve()
                        try:
                            path.relative_to(self.project_root)
                        except ValueError as exc:
                            raise LifecycleError(f"artifact escapes project root at line {line_number}") from exc
                        if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                            raise LifecycleError(f"artifact changed or missing: {artifact.get('path')}")
                records.append(record)
                previous = expected
        self._validate_histories(records)
        return records

    @staticmethod
    def _validate_histories(records: list[dict[str, Any]]) -> None:
        histories: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            experiment_id = _validate_id(record.get("experiment_id"))
            histories.setdefault(experiment_id, []).append(record)
        for experiment_id, history in histories.items():
            for index, record in enumerate(history):
                stage = record.get("stage")
                prior_stages = [item.get("stage") for item in history[:index]]
                if index == 0 and stage != "IDEA_REGISTERED":
                    raise LifecycleError(f"{experiment_id}: first stage must be IDEA_REGISTERED")
                if stage in prior_stages:
                    raise LifecycleError(f"{experiment_id}: duplicate stage {stage}")
                if prior_stages and prior_stages[-1] in {TERMINAL_REJECT, "DECISION_ACCEPTED"}:
                    raise LifecycleError(f"{experiment_id}: event after terminal decision")
                if stage == TERMINAL_REJECT:
                    if not prior_stages:
                        raise LifecycleError(f"{experiment_id}: rejection without registered idea")
                    continue
                if stage == AUDIT_FAILED:
                    if "RESULT_WRITTEN" not in prior_stages:
                        raise LifecycleError(f"{experiment_id}: audit before result")
                    continue
                if stage not in STAGES:
                    raise LifecycleError(f"{experiment_id}: unknown stage {stage!r}")
                expected_index = len(prior_stages)
                if AUDIT_FAILED in prior_stages:
                    raise LifecycleError(f"{experiment_id}: only rejection may follow failed audit")
                if expected_index >= len(STAGES) or stage != STAGES[expected_index]:
                    raise LifecycleError(
                        f"{experiment_id}: out-of-order stage {stage}; expected {STAGES[expected_index]}"
                    )
                payload = record.get("payload") or {}
                if stage == "OWNER_APPROVED":
                    if payload.get("subject_record_sha256") != history[index - 1].get("record_sha256"):
                        raise LifecycleError(f"{experiment_id}: approval is not bound to prior record hash")
                    if not str(payload.get("approved_by") or "").strip():
                        raise LifecycleError(f"{experiment_id}: approved_by is required")
                if stage == "PREFLIGHT_PASSED" and payload.get("exit_code") != 0:
                    raise LifecycleError(f"{experiment_id}: nonzero preflight cannot pass")
                if stage == "INDEPENDENT_AUDIT_PASSED" and payload.get("exit_code") != 0:
                    raise LifecycleError(f"{experiment_id}: nonzero audit cannot pass")
                if stage in {"PREREG_FROZEN", "SPEC_BOUND", "PREFLIGHT_PASSED", "PASSPORT_WRITTEN", "RESULT_WRITTEN", "INDEPENDENT_AUDIT_PASSED"}:
                    if not record.get("artifacts"):
                        raise LifecycleError(f"{experiment_id}: {stage} requires hashed artifacts")

    def append(
        self,
        *,
        experiment_id: str,
        stage: str,
        payload: Mapping[str, Any] | None = None,
        artifact_paths: Iterable[str] = (),
        created_at_utc: str | None = None,
    ) -> dict[str, Any]:
        experiment_id = _validate_id(experiment_id)
        records = self.read_verified(verify_artifacts=False)
        artifacts = _resolve_artifacts(self.project_root, artifact_paths)
        previous = records[-1]["record_sha256"] if records else None
        record: dict[str, Any] = {
            "schema_id": SCHEMA_ID,
            "authority": AUTHORITY,
            "experiment_id": experiment_id,
            "stage": stage,
            "created_at_utc": created_at_utc or _utc_now(),
            "previous_record_sha256": previous,
            "artifacts": artifacts,
            "payload": dict(payload or {}),
            "live_or_broker_calls": False,
            "capital_or_promotion_authority": False,
        }
        record["record_sha256"] = _record_hash(record)
        candidate = [*records, record]
        self._validate_histories(candidate)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        fd = os.open(self.path, flags, 0o600)
        try:
            os.write(fd, _canonical_json(record))
            os.fsync(fd)
        finally:
            os.close(fd)
        return record

    def summary(self, *, verify_artifacts: bool = True) -> dict[str, Any]:
        records = self.read_verified(verify_artifacts=verify_artifacts)
        by_experiment: dict[str, dict[str, Any]] = {}
        for record in records:
            item = by_experiment.setdefault(record["experiment_id"], {"stages": []})
            item["stages"].append(record["stage"])
            item["last_record_sha256"] = record["record_sha256"]
        for item in by_experiment.values():
            stages = item["stages"]
            item["terminal"] = stages[-1] in {TERMINAL_REJECT, "DECISION_ACCEPTED"}
            item["status"] = stages[-1]
        return {
            "schema_id": "research_experiment_lifecycle_summary_v1",
            "authority": AUTHORITY,
            "integrity_pass": True,
            "artifacts_verified": bool(verify_artifacts),
            "records": len(records),
            "experiments": by_experiment,
            "live_or_broker_calls": False,
            "capital_or_promotion_authority": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("runtime/research/experiment_lifecycle.jsonl"))
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)

    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--no-artifact-check", action="store_true")
    audit_parser.add_argument(
        "--output",
        type=Path,
        help="Optional receipt path, written atomically after a successful audit.",
    )

    append_parser = sub.add_parser("append")
    append_parser.add_argument("--experiment-id", required=True)
    append_parser.add_argument("--stage", required=True)
    append_parser.add_argument("--payload-json", default="{}")
    append_parser.add_argument("--artifact", action="append", default=[])

    args = parser.parse_args()
    ledger = LifecycleLedger(args.ledger, project_root=args.project_root)
    if args.command == "audit":
        result = ledger.summary(verify_artifacts=not args.no_artifact_check)
    else:
        payload = json.loads(args.payload_json)
        if not isinstance(payload, dict):
            raise LifecycleError("--payload-json must decode to an object")
        result = ledger.append(
            experiment_id=args.experiment_id,
            stage=args.stage,
            payload=payload,
            artifact_paths=args.artifact,
        )
    rendered = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.command == "audit" and args.output:
        output = args.output if args.output.is_absolute() else args.project_root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(output)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
