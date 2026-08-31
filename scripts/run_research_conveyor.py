#!/usr/bin/env python3
"""Fail-closed, research-only runner for Research Conveyor V1."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from research_lab.research_conveyor_contract import (
    AUTHORITY,
    ContractError,
    freeze_hypothesis,
    load_manifest,
    read_verified_receipt,
    write_self_hashed_json,
)


PHASES = ("prereg", "replay", "random_control", "stress")
PHASE_SCHEMA = "research_conveyor_phase_receipt_v1"
LOG_LIMIT_BYTES = 64 * 1024
PROCESS_GROUP_GRACE_SECONDS = 0.25
POST_KILL_DRAIN_SECONDS = 0.25
SECRET_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "PRIVATE")
RESEARCH_STATES = {"PASS", "REJECT", "INCONCLUSIVE", "BLOCKED_DATA_OR_PARITY", "FAILED_TECHNICAL"}
HEX64 = set("0123456789abcdef")
HYPOTHESIS_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def _safe_environment() -> dict[str, str]:
    allowed = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR"}
    environment = {key: value for key, value in os.environ.items() if key in allowed and isinstance(value, str)}
    return {
        key: value for key, value in environment.items()
        if not any(word in key.upper() for word in SECRET_WORDS)
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(_canonical(value) + b"\n")


class _BoundedCapture:
    """Drain a pipe continuously without retaining more than the log budget."""

    def __init__(self) -> None:
        self.value = bytearray()
        self.discarded = 0

    def append(self, chunk: bytes) -> None:
        available = LOG_LIMIT_BYTES - len(self.value)
        self.value.extend(chunk[:available])
        self.discarded += max(0, len(chunk) - available)

    def rendered(self) -> str:
        if not self.discarded:
            return bytes(self.value).decode("utf-8", errors="replace")
        marker = f"\n[research_conveyor_log_truncated discarded_bytes={self.discarded}]\n".encode("ascii")
        retained = bytes(self.value[:LOG_LIMIT_BYTES - len(marker)])
        return (retained + marker).decode("utf-8", errors="replace")


def _write_capture(path: Path, capture: _BoundedCapture) -> None:
    path.write_text(capture.rendered(), encoding="utf-8")


def _signal_process_group(process_group: int, sig: signal.Signals) -> None:
    try:
        os.killpg(process_group, sig)
    except ProcessLookupError:
        pass


def _close_registered_pipes(pipes: selectors.BaseSelector) -> None:
    for key in list(pipes.get_map().values()):
        pipes.unregister(key.fileobj)
        key.fileobj.close()


def _run_adapter(argv: list[str], *, root: Path, environment: Mapping[str, str], timeout: float) -> tuple[int, bool, _BoundedCapture, _BoundedCapture]:
    """Run one adapter in a process group while continuously draining both pipes."""
    process = subprocess.Popen(
        argv, shell=False, cwd=root, env=dict(environment), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    stdout, stderr = _BoundedCapture(), _BoundedCapture()
    pipes = selectors.DefaultSelector()
    assert process.stdout is not None and process.stderr is not None
    pipes.register(process.stdout, selectors.EVENT_READ, stdout)
    pipes.register(process.stderr, selectors.EVENT_READ, stderr)
    deadline = time.monotonic() + timeout
    process_group = process.pid  # start_new_session makes this a unique group while descendants exist.
    timed_out = False
    kill_at: float | None = None
    drain_deadline: float | None = None
    try:
        while pipes.get_map():
            current = time.monotonic()
            remaining = deadline - current
            if not timed_out and remaining <= 0:
                timed_out = True
                _signal_process_group(process_group, signal.SIGTERM)
                kill_at = current + PROCESS_GROUP_GRACE_SECONDS
                drain_deadline = kill_at + POST_KILL_DRAIN_SECONDS
            if timed_out and kill_at is not None and current >= kill_at:
                # The group ID cannot be reused while a descendant keeps the inherited
                # pipe open; signal it even when the direct parent has already exited.
                _signal_process_group(process_group, signal.SIGKILL)
                kill_at = None
            if timed_out and drain_deadline is not None and current >= drain_deadline:
                _close_registered_pipes(pipes)
                break
            wait_for = 0.05 if timed_out else min(0.05, max(remaining, 0))
            events = pipes.select(timeout=wait_for)
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                if chunk:
                    key.data.append(chunk)
                else:
                    pipes.unregister(key.fileobj)
        try:
            return process.wait(timeout=POST_KILL_DRAIN_SECONDS), timed_out, stdout, stderr
        except subprocess.TimeoutExpired:
            _signal_process_group(process_group, signal.SIGKILL)
            return -signal.SIGKILL, timed_out, stdout, stderr
    finally:
        pipes.close()
        if process.poll() is None:
            _signal_process_group(process_group, signal.SIGKILL)


def _acquire_lock(root: Path) -> Path:
    lock = root / ".research_conveyor_v1.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ContractError("research conveyor lock already exists") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(str(os.getpid()) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return lock


def _release_lock(lock: Path) -> None:
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def _expand_argv(template: list[str], *, run_dir: Path, hypothesis_id: str, phase: str, receipt: Path) -> list[str]:
    values = {
        "{python}": sys.executable,
        "{run_dir}": str(run_dir),
        "{hypothesis_id}": hypothesis_id,
        "{phase}": phase,
        "{receipt}": str(receipt),
    }
    try:
        return [values.get(item, item) for item in template]
    except TypeError as exc:
        raise ContractError("adapter argv must be strings") from exc


def _safe_artifact_path(root: Path, boundary: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts or any(char in value for char in "*?[]"):
        return None
    candidate = root / value
    current = root
    for part in Path(value).parts:
        current /= part
        if current.is_symlink():
            return None
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(boundary.resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifacts_are_valid(artifacts: Any, *, root: Path, boundary: Path) -> bool:
    if not isinstance(artifacts, list):
        return False
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            return False
        path = _safe_artifact_path(root, boundary, artifact.get("path"))
        if path is None or not _is_sha256(artifact.get("sha256")) or _file_sha256(path) != artifact["sha256"]:
            return False
    return True


def _phase_receipt_is_valid(receipt: Mapping[str, Any], *, root: Path, run_dir: Path, hypothesis_id: str, phase: str, freeze: Mapping[str, Any], argv: list[str]) -> bool:
    if receipt.get("authority") != AUTHORITY:
        return False
    if receipt.get("hypothesis_id") != hypothesis_id or receipt.get("phase") != phase:
        return False
    if receipt.get("status") not in RESEARCH_STATES:
        return False
    if receipt.get("manifest_sha256") != freeze["manifest_sha256"]:
        return False
    if receipt.get("preregistration_sha256") != freeze["preregistration_sha256"]:
        return False
    if receipt.get("adapter_argv_sha256") != _sha(argv):
        return False
    if not all(_is_sha256(receipt.get(field)) for field in ("manifest_sha256", "preregistration_sha256", "adapter_argv_sha256")):
        return False
    if not _artifacts_are_valid(receipt.get("input_artifacts"), root=root, boundary=root):
        return False
    if not _artifacts_are_valid(receipt.get("output_artifacts"), root=root, boundary=run_dir):
        return False
    if not isinstance(receipt.get("metrics"), dict):
        return False
    try:
        _canonical(receipt["metrics"])
    except (TypeError, ValueError):
        return False
    return all(receipt.get(field) is False for field in (
        "live_or_broker_calls", "private_api_calls", "capital_or_promotion_authority",
    ))


def _terminal(hypothesis_id: str, state: str, phase: str | None) -> dict[str, Any]:
    return {"hypothesis_id": hypothesis_id, "state": state, "phase": phase}


def _write_terminal(run_dir: Path, terminal: Mapping[str, Any]) -> None:
    path = run_dir / "hypotheses" / terminal["hypothesis_id"] / "terminal_receipt.json"
    write_self_hashed_json(path, {
        "schema_id": "research_conveyor_hypothesis_terminal_receipt_v1",
        "authority": AUTHORITY,
        **terminal,
    })


def _write_preregistration(run_dir: Path, hypothesis: Mapping[str, Any], freeze: Mapping[str, Any]) -> None:
    write_self_hashed_json(run_dir / "hypotheses" / hypothesis["id"] / "preregistration.json", {
        "schema_id": "research_conveyor_normalized_preregistration_v1",
        "authority": AUTHORITY,
        "hypothesis_id": hypothesis["id"],
        "manifest_sha256": freeze["manifest_sha256"],
        "preregistration_sha256": freeze["preregistration_sha256"],
        "contract_hashes": freeze["contract_hashes"],
        "data_hashes": freeze["data_hashes"],
        "preregistration": hypothesis["preregistration"],
    })


def _fresh_freeze(root: Path, config_path: Path, initial_sha: str, hypothesis_id: str, expected_freeze: Mapping[str, Any]) -> dict[str, Any]:
    manifest = load_manifest(root, config_path)
    if manifest.sha256 != initial_sha:
        raise ContractError("manifest changed during conveyor run")
    freeze = freeze_hypothesis(root, manifest, hypothesis_id)
    if freeze != expected_freeze:
        raise ContractError("frozen hypothesis changed during conveyor run")
    return freeze


def run_conveyor(root: Path, config_path: Path, run_dir: Path, mode: str, now: datetime | None = None) -> dict[str, Any]:
    """Run one deterministic, non-promotional research conveyor invocation."""
    if mode not in {"dry-run", "preflight", "run"}:
        raise ValueError("mode must be dry-run, preflight, or run")
    root = Path(root).resolve()
    config_path = Path(config_path).resolve()
    run_dir = Path(run_dir).resolve()
    if run_dir.exists():
        raise ValueError("run directory must be new and exclusive")
    if root not in (run_dir, *run_dir.parents):
        raise ValueError("run directory escapes repository root")

    lock = _acquire_lock(root)
    try:
        manifest = load_manifest(root, config_path)
        run_dir.mkdir(parents=True)
        _write_json(run_dir / "manifest_snapshot.json", manifest.payload)
        _write_json(run_dir / "manifest_snapshot.sha256.json", {"manifest_sha256": manifest.sha256})
        initial_sha = manifest.sha256
        deadline = time.monotonic() + manifest.payload["max_runtime_seconds"]
        terminals: list[dict[str, Any]] = []
        launched = 0

        for hypothesis in sorted(manifest.hypotheses, key=lambda item: (item["priority"], item["id"])):
            hypothesis_id = hypothesis["id"]
            if not HYPOTHESIS_ID.fullmatch(hypothesis_id):
                raise ContractError("hypothesis ID is not a safe path component")
            state = hypothesis["state"]
            terminal: dict[str, Any]
            try:
                frozen = freeze_hypothesis(root, manifest, hypothesis_id)
                _write_preregistration(run_dir, hypothesis, frozen)
            except ContractError:
                terminal = _terminal(hypothesis_id, "FAILED_TECHNICAL", None)
            else:
                terminal = _terminal(hypothesis_id, "PASS_DIAGNOSTIC", None)
            if terminal["state"] == "FAILED_TECHNICAL":
                pass
            elif not manifest.payload["enabled"]:
                terminal = _terminal(hypothesis_id, "DISABLED", None)
            elif state != "RUNNABLE":
                terminal = _terminal(hypothesis_id, state, None)
            elif mode == "dry-run":
                terminal = _terminal(hypothesis_id, "DRY_RUN", None)
            elif mode == "preflight":
                terminal = _terminal(hypothesis_id, "PREFLIGHT", None)
            elif launched >= manifest.payload["max_jobs_per_run"]:
                terminal = _terminal(hypothesis_id, "RESOURCE_GUARD", None)
            elif shutil.disk_usage(root).free < manifest.payload["min_free_bytes"] or time.monotonic() >= deadline:
                terminal = _terminal(hypothesis_id, "RESOURCE_GUARD", None)
            else:
                launched += 1
                terminal = _terminal(hypothesis_id, "PASS_DIAGNOSTIC", None)
                for phase in PHASES:
                    try:
                        freeze = _fresh_freeze(root, config_path, initial_sha, hypothesis_id, frozen)
                    except ContractError:
                        terminal = _terminal(hypothesis_id, "FAILED_TECHNICAL", phase)
                        break
                    if shutil.disk_usage(root).free < manifest.payload["min_free_bytes"] or time.monotonic() >= deadline:
                        terminal = _terminal(hypothesis_id, "RESOURCE_GUARD", phase)
                        break
                    receipt_path = run_dir / "hypotheses" / hypothesis_id / "phases" / f"{phase}.json"
                    argv = _expand_argv(hypothesis["adapters"][phase], run_dir=run_dir, hypothesis_id=hypothesis_id, phase=phase, receipt=receipt_path)
                    phase_dir = receipt_path.parent
                    phase_dir.mkdir(parents=True, exist_ok=True)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        terminal = _terminal(hypothesis_id, "RESOURCE_GUARD", phase)
                        break
                    try:
                        return_code, timed_out, stdout, stderr = _run_adapter(argv, root=root, environment=_safe_environment(), timeout=remaining)
                    except OSError:
                        terminal = _terminal(hypothesis_id, "FAILED_TECHNICAL", phase)
                        break
                    _write_capture(phase_dir / f"{phase}.stdout.log", stdout)
                    _write_capture(phase_dir / f"{phase}.stderr.log", stderr)
                    try:
                        post_freeze = _fresh_freeze(root, config_path, initial_sha, hypothesis_id, freeze)
                    except ContractError:
                        terminal = _terminal(hypothesis_id, "FAILED_TECHNICAL", phase)
                        break
                    if post_freeze != freeze or timed_out or return_code != 0:
                        terminal = _terminal(hypothesis_id, "FAILED_TECHNICAL", phase)
                        break
                    try:
                        receipt = read_verified_receipt(receipt_path, expected_schema=PHASE_SCHEMA)
                    except ContractError:
                        terminal = _terminal(hypothesis_id, "FAILED_TECHNICAL", phase)
                        break
                    if not _phase_receipt_is_valid(receipt, root=root, run_dir=run_dir, hypothesis_id=hypothesis_id, phase=phase, freeze=post_freeze, argv=argv):
                        terminal = _terminal(hypothesis_id, "FAILED_TECHNICAL", phase)
                        break
                    if receipt["status"] != "PASS":
                        terminal = _terminal(hypothesis_id, receipt["status"], phase)
                        break
            terminals.append(terminal)
            _write_terminal(run_dir, terminal)

        counts: dict[str, int] = {}
        for terminal in terminals:
            counts[terminal["state"]] = counts.get(terminal["state"], 0) + 1
        aggregate = {
            "schema_id": "research_conveyor_terminal_receipt_v1",
            "authority": AUTHORITY,
            "mode": mode,
            "manifest_sha256": initial_sha,
            "terminals": terminals,
            "counts": counts,
        }
        written = write_self_hashed_json(run_dir / "terminal_receipt.json", aggregate)
        return {key: written[key] for key in ("authority", "mode", "manifest_sha256", "terminals", "counts")}
    finally:
        _release_lock(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--run", action="store_true")
    args = parser.parse_args()
    mode = "dry-run" if args.dry_run else "preflight" if args.preflight else "run"
    result = run_conveyor(Path.cwd(), args.config, args.run_dir, mode)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
