#!/usr/bin/env python3
"""Bounded, offline-only ATT1 research supervisor for a macOS LaunchAgent.

The command list is deliberately compiled into this file.  It never loads an
environment file, accepts a command from the caller, or carries credentials to
its children.  It is a local evidence job, not a strategy, broker, or order
control path.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / "mac_att1_research_job"
SAFE_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (120, 600, 1800)
MAX_CAFFEINATE_SECONDS = 915
HEARTBEAT_SECONDS = 5
SANDBOX_EXEC = "/usr/bin/sandbox-exec"


@dataclass(frozen=True)
class Stage:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: int
    input_paths: tuple[str, ...]


# These are the only child processes this supervisor can launch.  They use
# deterministic local fixtures and do not query a broker or public endpoint.
STAGES = (
    Stage(
        name="binding_tests",
        argv=(sys.executable, "-m", "pytest", "-q", "tests/test_att1_broker_replay_binding.py",
              "tests/test_att1_broker_cash_accounting.py", "tests/test_att1_account_identity.py",
              "tests/test_att1_runtime_identity.py", "tests/test_att1_exclusive_reservation.py",
              "tests/test_att1_broker_snapshot.py"),
        timeout_seconds=300,
        input_paths=(
            "tests/test_att1_broker_replay_binding.py",
            "tests/test_att1_broker_cash_accounting.py",
            "tests/test_att1_account_identity.py",
            "tests/test_att1_runtime_identity.py",
            "tests/test_att1_broker_snapshot.py",
            "tests/test_att1_exclusive_reservation.py",
            "tests/test_att1_lifecycle_coordinator.py",
            "research_lab/att1_lifecycle_profile.py",
            "research_lab/att1_lifecycle_coordinator.py",
            "research_lab/att1_lifecycle_session.py",
            "bot/att1_coordinator_adapter.py",
            "scripts/mac_att1_research_job.py",
        ),
    ),
    Stage(
        name="public_parity_tests",
        argv=(
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_att1_ets2s_signal_shadow_parity.py::test_frozen_fixture_has_automatic_att1_and_ets2s_parity",
        ),
        timeout_seconds=600,
        input_paths=(
            "tests/test_att1_ets2s_signal_shadow_parity.py",
            "research_lab/att1_ets2s_signal_shadow_parity.py",
            "strategies/att1_live.py",
            "strategies/elder_live.py",
            "research_lab/fixtures/paritet_l1",
            "scripts/mac_att1_research_job.py",
        ),
    ),
    Stage(
        name="ws_fairness_canary",
        argv=(sys.executable, "-m", "pytest", "-q", "tests/test_bybit_ws_fairness.py"),
        timeout_seconds=180,
        input_paths=(
            "tests/test_bybit_ws_fairness.py",
            "smart_pump_reversal_bot.py",
            "scripts/mac_att1_research_job.py",
        ),
    ),
    Stage(
        name="lifecycle_inspect",
        argv=(sys.executable, "scripts/verify_att1_lifecycle.py"),
        timeout_seconds=240,
        input_paths=(
            "scripts/verify_att1_lifecycle.py",
            "scripts/run_att1_lifecycle_zero_risk.py",
            "research_lab/att1_lifecycle_profile.py",
            "research_lab/att1_lifecycle_session.py",
            "research_lab/att1_lifecycle_coordinator.py",
            "tests/fixtures/att1_lifecycle/att1_end_to_end_v1.json",
            "configs/research/att1_lifecycle_public_v1.json",
            "scripts/mac_att1_research_job.py",
        ),
    ),
)


class AlreadyRunning(RuntimeError):
    """Another invocation, or an orphaned child, owns the advisory lock."""


class StateViolation(RuntimeError):
    """The durable checkpoint cannot safely be resumed."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_text(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{time.time_ns()}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, _canonical_json(payload))


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise StateViolation(f"invalid checkpoint: {path.name}") from exc
    if not isinstance(value, dict):
        raise StateViolation(f"invalid checkpoint object: {path.name}")
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_input(root: Path, relative: str) -> dict[str, str]:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise StateViolation(f"input escapes project: {relative}") from exc
    if path.is_file():
        return {relative: _sha256_file(path)}
    if not path.is_dir():
        return {relative: "MISSING"}
    result: dict[str, str] = {}
    for candidate in sorted(path.rglob("*")):
        if candidate.is_file() and not candidate.is_symlink():
            key = str(candidate.relative_to(root))
            result[key] = _sha256_file(candidate)
    return result


def _stage_source_manifest(root: Path, stages: Iterable[Stage]) -> dict[str, str]:
    result: dict[str, str] = {}
    for stage in stages:
        for relative in stage.input_paths:
            for key, digest in _hash_input(root, relative).items():
                old = result.setdefault(key, digest)
                if old != digest:
                    raise StateViolation(f"inconsistent input hash: {key}")
    # Bind imported first-party code too; never scan result/private/runtime trees.
    for directory in ('bot', 'research_lab', 'strategies'):
        for candidate in sorted((root / directory).glob('*.py')):
            if not candidate.is_symlink():
                result[str(candidate.relative_to(root))] = _sha256_file(candidate)
    return dict(sorted(result.items()))


def _source_identity(root: Path, stages: tuple[Stage, ...]) -> dict[str, Any]:
    inputs = _stage_source_manifest(root, stages)
    stage_specs = [
        {
            "name": stage.name,
            "argv": list(stage.argv),
            "timeout_seconds": stage.timeout_seconds,
            "input_paths": list(stage.input_paths),
        }
        for stage in stages
    ]
    payload = {"schema_id": "mac_att1_research_job_source_v1", "stages": stage_specs, "inputs": inputs}
    return {
        "source_input_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
        "source_inputs": inputs,
        "stage_specs": stage_specs,
    }


def sanitized_environment(runtime_dir: Path) -> dict[str, str]:
    """Return a fresh allowlist; nothing from the parent environment is copied."""
    return {
        "PATH": SAFE_PATH,
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONHASHSEED": "0",
        "RESEARCH_ONLY": "true",
        "NETWORK_AUTHORITY": "false",
        "PRIVATE_API_AUTHORITY": "false",
        "ORDER_AUTHORITY": "false",
        "LIVE_WRITE_AUTHORITY": "false",
        "PROMOTION_AUTHORITY": "false",
        "TMPDIR": str(runtime_dir / "tmp"),
    }


def caffeinate_argv(pid: int, seconds: int) -> list[str]:
    bounded = min(MAX_CAFFEINATE_SECONDS, max(1, int(seconds)))
    return ["/usr/bin/caffeinate", "-i", "-t", str(bounded), "-w", str(pid)]


def _profile_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def sandbox_profile(root: Path) -> str:
    """Deny all child networking and known credential stores at the OS boundary."""
    home = Path.home()
    private_paths = (
        home / ".ssh",
        home / ".aws",
        home / ".codex",
        home / ".config" / "gcloud",
        home / "Library" / "Keychains",
        root / ".env",
        root / ".private",
        root.parent / ".private",
    )
    rules = ["(version 1)", "(allow default)", "(deny network*)"]
    rules.extend(f'(deny file-read-data (subpath "{_profile_path(path)}"))' for path in private_paths)
    return "\n".join(rules)


class MacATT1ResearchJob:
    def __init__(self, *, root: Path = ROOT, runtime_dir: Path = RUNTIME):
        self.root = Path(root).resolve()
        self.runtime_dir = Path(runtime_dir).resolve()
        self.state_path = self.runtime_dir / "state.json"
        self.status_path = self.runtime_dir / "status.json"
        self.result_path = self.runtime_dir / "result.json"
        self.heartbeat_path = self.runtime_dir / "heartbeat.json"
        self.lock_path = self.runtime_dir / "supervisor.lock"
        self.logs_dir = self.runtime_dir / "logs"

    def _lock(self) -> int:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise AlreadyRunning("mac ATT1 research job already running") from exc
        return fd

    @staticmethod
    def _unlock(fd: int) -> None:
        # Last inherited descriptor releases flock. Do not explicitly unlock
        # an orphaned child if the supervisor exits through an exception.
        os.close(fd)

    def _new_state(self, identity: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_id": "mac_att1_research_job_state_v1",
            "status": "PENDING",
            "created_at_utc": _utc_text(),
            **identity,
            "current_stage": None,
            "completed_stages": [],
            "stages": {stage.name: {"state": "PENDING", "attempts": 0} for stage in STAGES},
        }

    def _load_state(self, identity: dict[str, Any]) -> dict[str, Any]:
        state = _read_json(self.state_path)
        if state is None:
            state = self._new_state(identity)
            _atomic_json(self.state_path, state)
            return state
        if state.get("schema_id") != "mac_att1_research_job_state_v1":
            raise StateViolation("unknown checkpoint schema")
        if state.get("source_input_sha256") != identity["source_input_sha256"]:
            state["status"] = "SOURCE_INPUT_CHANGED"
            state["current_stage"] = None
            state["source_input_observed_sha256"] = identity["source_input_sha256"]
            state["updated_at_utc"] = _utc_text()
            _atomic_json(self.state_path, state)
        return state

    def _publish(self, state: dict[str, Any]) -> None:
        now = _utc_text()
        compact = {
            "schema_id": "mac_att1_research_job_status_v1",
            "status": state["status"],
            "current_stage": state.get("current_stage"),
            "completed_stage_names": [row["name"] for row in state.get("completed_stages", [])],
            "source_input_sha256": state["source_input_sha256"],
            "updated_at_utc": now,
            "research_only": True,
            "network_authority": False,
            "private_api_authority": False,
            "order_authority": False,
            "promotion_authority": False,
        }
        _atomic_json(self.status_path, compact)
        _atomic_json(self.heartbeat_path, {
            "schema_id": "mac_att1_research_job_heartbeat_v1",
            "ts_utc": now,
            "status": state["status"],
            "current_stage": state.get("current_stage"),
            "pid": os.getpid(),
            "research_only": True,
            "order_authority": False,
        })

    def _publish_result(self, state: dict[str, Any]) -> None:
        _atomic_json(self.result_path, {
            "schema_id": "mac_att1_research_job_result_v1",
            "status": state["status"],
            "source_input_sha256": state["source_input_sha256"],
            "completed_stages": state.get("completed_stages", []),
            "stages": state.get("stages", {}),
            "finished_at_utc": _utc_text(),
            "research_only": True,
            "network_authority": False,
            "private_api_authority": False,
            "order_authority": False,
            "promotion_authority": False,
        })

    def _next_stage(self, state: dict[str, Any]) -> Stage | None:
        completed = [row.get("name") for row in state.get("completed_stages", [])]
        expected = [stage.name for stage in STAGES]
        if completed != expected[:len(completed)]:
            raise StateViolation("completed stages are not an ordered prefix")
        return STAGES[len(completed)] if len(completed) < len(STAGES) else None

    def _start_command(self, stage: Stage, env: dict[str, str], lock_fd: int):
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        tmp_log = self.logs_dir / f".{stage.name}.log.tmp.{os.getpid()}.{time.time_ns()}"
        log_handle = tmp_log.open("wb", buffering=0)
        try:
            if not Path(SANDBOX_EXEC).is_file():
                raise StateViolation("sandbox-exec unavailable; refusing unsandboxed child")
            process = subprocess.Popen(
                [SANDBOX_EXEC, "-p", sandbox_profile(self.root), sys.executable, "-c",
                 "import os,signal,sys; signal.alarm(int(sys.argv[1])); os.execv(sys.argv[2],sys.argv[2:])",
                 str(stage.timeout_seconds + 5), *stage.argv],
                cwd=str(self.root),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                close_fds=True,
                pass_fds=(lock_fd,),
                start_new_session=True,
            )
        except BaseException:
            log_handle.close()
            if tmp_log.exists():
                tmp_log.unlink()
            raise
        return process, log_handle, tmp_log

    def _finalize_log(self, stage: Stage, handle, tmp_log: Path) -> tuple[Path, str]:
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        target = self.logs_dir / f"{stage.name}.log"
        os.replace(tmp_log, target)
        return target, _sha256_file(target)

    @staticmethod
    def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)

    @staticmethod
    def _stop_caffeinate(process: subprocess.Popen[bytes] | None) -> None:
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _run_stage(self, stage: Stage, env: dict[str, str], lock_fd: int) -> dict[str, Any]:
        started = time.monotonic()
        process, log_handle, tmp_log = self._start_command(stage, env, lock_fd)
        caffeine: subprocess.Popen[bytes] | None = None
        timed_out = False
        try:
            # It exists only while this bounded child is alive.  The child also
            # keeps the lock FD, so an abrupt supervisor exit cannot overlap it.
            caffeine = subprocess.Popen(
                caffeinate_argv(process.pid, min(MAX_CAFFEINATE_SECONDS, stage.timeout_seconds + 15)),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            while True:
                remaining = stage.timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    timed_out = True
                    self._stop_process_group(process)
                    returncode = process.returncode if process.returncode is not None else -signal.SIGKILL
                    break
                try:
                    returncode = process.wait(timeout=min(HEARTBEAT_SECONDS, remaining))
                    break
                except subprocess.TimeoutExpired:
                    self._publish(_read_json(self.state_path))
        finally:
            self._stop_process_group(process)
            self._stop_caffeinate(caffeine)
        log_path, log_sha = self._finalize_log(stage, log_handle, tmp_log)
        return {
            "returncode": int(returncode),
            "timed_out": timed_out,
            "duration_seconds": round(time.monotonic() - started, 3),
            "log_path": str(log_path.relative_to(self.runtime_dir)),
            "log_sha256": log_sha,
        }

    def _commit_stage_success(self, stage: Stage, *, state: dict[str, Any], outcome: dict[str, Any]) -> None:
        state["stages"][stage.name] = {
            "state": "COMPLETE",
            "attempts": state["stages"][stage.name].get("attempts", 0),
            "completed_at_utc": _utc_text(),
            "outcome": outcome,
        }
        state["completed_stages"].append({"name": stage.name, **outcome})
        state["updated_at_utc"] = _utc_text()
        _atomic_json(self.state_path, state)

    def _record_failure(self, stage: Stage, state: dict[str, Any], outcome: dict[str, Any]) -> None:
        prior = state["stages"][stage.name]
        attempts = int(prior.get("attempts", 0))
        item: dict[str, Any] = {"state": "FAILED", "attempts": attempts, "outcome": outcome}
        if attempts >= MAX_ATTEMPTS:
            state["status"] = "FAILED"
            state["current_stage"] = stage.name
            item["terminal"] = True
        else:
            delay = RETRY_BACKOFF_SECONDS[min(attempts - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
            item["state"] = "RETRY_WAIT"
            item["next_retry_utc"] = _utc_text(_utc_now() + timedelta(seconds=delay))
            state["status"] = "RETRY_WAIT"
            state["current_stage"] = stage.name
        state["stages"][stage.name] = item
        state["updated_at_utc"] = _utc_text()
        _atomic_json(self.state_path, state)
        self._publish(state)
        if state["status"] == "FAILED":
            self._publish_result(state)

    def run(self) -> dict[str, str]:
        identity = _source_identity(self.root, STAGES)
        lock_fd = self._lock()
        try:
            (self.runtime_dir / 'tmp').mkdir(exist_ok=True)
            state = self._load_state(identity)
            if state["status"] == "SOURCE_INPUT_CHANGED":
                self._publish(state)
                self._publish_result(state)
                return {"state": "SOURCE_INPUT_CHANGED", "action": "refuse"}
            if state["status"] == "COMPLETE":
                return {"state": "COMPLETE", "action": "noop"}
            if state["status"] == "FAILED":
                self._publish(state)
                return {"state": "FAILED", "action": "no_retry"}
            while True:
                stage = self._next_stage(state)
                if stage is None:
                    state["status"] = "COMPLETE"
                    state["current_stage"] = None
                    state["completed_at_utc"] = _utc_text()
                    _atomic_json(self.state_path, state)
                    self._publish(state)
                    self._publish_result(state)
                    return {"state": "COMPLETE", "action": "finished"}
                item = state["stages"][stage.name]
                if item.get('state') == 'RUNNING':
                    self._record_failure(stage, state, {
                        'returncode': -1, 'timed_out': False, 'reason': 'interrupted_attempt'})
                    return {'state': state['status'], 'action': 'recovered_interruption'}
                retry_at = item.get("next_retry_utc")
                if state["status"] == "RETRY_WAIT" and retry_at and _utc_text() < retry_at:
                    self._publish(state)
                    return {"state": "RETRY_WAIT", "action": "backoff"}
                state["status"] = "PENDING"
                state["current_stage"] = None
                state["status"] = "RUNNING"
                state["current_stage"] = stage.name
                state["stages"][stage.name] = {"state": "RUNNING", "attempts": int(item.get("attempts", 0)) + 1}
                state["updated_at_utc"] = _utc_text()
                _atomic_json(self.state_path, state)
                self._publish(state)
                try:
                    outcome = self._run_stage(stage, sanitized_environment(self.runtime_dir), lock_fd)
                except (OSError, StateViolation) as exc:
                    outcome = {'returncode': -1, 'timed_out': False, 'reason': type(exc).__name__}
                if _source_identity(self.root, STAGES)['source_input_sha256'] != identity['source_input_sha256']:
                    state['status'] = 'SOURCE_INPUT_CHANGED'
                    _atomic_json(self.state_path, state)
                    self._publish(state)
                    return {'state': state['status'], 'action': 'refuse_mixed_inputs'}
                if outcome["returncode"] == 0 and not outcome["timed_out"]:
                    self._commit_stage_success(stage, state=state, outcome=outcome)
                    state["status"] = "PENDING"
                    state["current_stage"] = None
                    _atomic_json(self.state_path, state)
                    self._publish(state)
                    continue
                self._record_failure(stage, state, outcome)
                return {"state": state["status"], "action": "recorded"}
        finally:
            self._unlock(lock_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-plan", action="store_true", help="print the reviewed fixed stage names only")
    args = parser.parse_args(argv)
    if args.print_plan:
        print(json.dumps({"stages": [stage.name for stage in STAGES], "research_only": True}, sort_keys=True))
        return 0
    result = MacATT1ResearchJob().run()
    print(json.dumps(result, sort_keys=True))
    # launchd retries on its interval, not via KeepAlive or a nonzero restart loop.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
