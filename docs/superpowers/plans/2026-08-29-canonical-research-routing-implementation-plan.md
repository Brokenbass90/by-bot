# Canonical Research Station Routing and Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every approved zero-risk research loop into the recovery tree and migrate legacy screen sessions only after receipt-backed identity, authority, evidence, and parity checks pass.

**Architecture:** A pure Python contract module parses legacy process evidence, validates the canonical job manifest, compares deterministic decisions, closed market snapshots, or immutable collector snapshots, and records hash-bound receipts. A CLI orchestrates inventory, canonical launch, verification, and conditional shutdown; the existing local station supervisor consumes the same manifest and publishes a status that names factual evidence paths. Every unknown identity, hash drift, missing common snapshot, authority mismatch, duplicate run identity, or incomplete Station V3 completion fails closed and leaves the old process running.

**Tech Stack:** Python 3, pytest, JSON/JSONL manifests and receipts, SHA-256, `screen -ls`, `ps`, `lsof`, existing shell research loops, `research_lab/station_v3.py` completion proofs, atomic file writes.

**Spec:** `docs/superpowers/specs/2026-08-29-money-research-sprint-v1-design.md` (Section 3, canonical research station)

## Global Constraints

- Authority is `research-only; без live, broker orders, изменения риска, promotion или money authority`.
- Every canonical manifest must contain exactly `authority=research_only_no_live_or_promotion`, `promotion_authority=false`, `network_authority=false`, `private_api_authority=false`, `order_authority=false`, and `live_write_authority=false`; missing or different values fail closed.
- Migration is non-destructive: old runtime files are retained as read-only historical evidence, and no command may unlink, truncate, or overwrite a legacy-root file.
- If command/config identity cannot be reconstructed, record `NOT_CONFIRMED` and do not stop that legacy process automatically.
- Canonical launches use `research_only=true`, a unique `evidence_epoch`, and an epoch-specific runtime directory under the recovery tree.
- Deterministic decision loops require exact decision IDs and all economic fields for identical source timestamp/config/input; market-snapshot loops require a shared closed source timestamp; collector/supervisor loops compare immutable snapshot source identities, counts, and hashes while allowing freshness timestamps to differ.
- Station V3 completion is proved only by `completion.json` bound to the manifest hash and ledger-tail hash; log text is never state.
- A run ID may map to one identity fingerprint only; conflicting identities are `FAIL_CLOSED` and are never merged into one statistic.
- Historical old and canonical epochs remain separate evidence populations and are never combined for scoring.
- Existing public-data/shadow loops remain zero-risk; no credentials, private endpoints, orders, risk changes, or promotion paths may be introduced.
- Missing, stale, malformed, or hash-mismatched station inputs stop the run; exceptions are recorded as technical failures and never become an empty/no-signal success.
- Future/open-bar, non-causal, duplicate, or boundary evidence creates a terminal integrity receipt; unfinished outcomes remain `pending`/`censored` rather than being dropped.
- Every migration artifact includes a terminal decision and reopen condition, and only terminal receipts or explicit `IN_PROGRESS` run IDs may enter the canonical roadmap.

---

### Task 1: Freeze the canonical station contract and job manifest

**Files:**
- Create: `configs/research/canonical_station_v1.json`
- Create: `tests/test_canonical_station_contract.py`
- Create: `research_lab/canonical_station.py`

**Interfaces:**
- Consumes: JSON manifest, explicit project root, explicit legacy root, and filesystem/process receipts.
- Produces: `AUTHORITY`, `MANIFEST_SCHEMA_ID`, `ProcessKind`, `ParityState`, `MigrationError`, `CanonicalJob`, `ProcessReceipt`, `ParityReceipt`, `load_manifest(path, project_root) -> dict[str, Any]`, `validate_authority_manifest(manifest) -> None`, `identity_fingerprint(receipt) -> str`, and `atomic_write_json(path, payload) -> None`.

- [ ] **Step 1: Write the failing contract tests**

```python
import json
from pathlib import Path

import pytest

from research_lab.canonical_station import (
    AUTHORITY,
    MANIFEST_SCHEMA_ID,
    MigrationError,
    load_manifest,
)


def _manifest() -> dict:
    return {
        "schema_id": MANIFEST_SCHEMA_ID,
        "authority": AUTHORITY,
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "canonical_runtime_root": "runtime/local_research_station",
        "jobs": [{
            "name": "fixture",
            "process_kind": "deterministic_decision_loop",
            "screen_session": "canonical_fixture",
            "launcher": ["scripts/fixture.sh"],
            "evidence_paths": ["runtime/fixture/decision.json"],
        }],
    }


def test_manifest_requires_all_exact_authority_fields(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/fixture.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    path = tmp_path / "station.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")
    assert load_manifest(path, project_root=tmp_path)["authority"] == AUTHORITY

    broken = _manifest()
    del broken["live_write_authority"]
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(MigrationError, match="live_write_authority"):
        load_manifest(path, project_root=tmp_path)


def test_manifest_rejects_network_order_and_private_authority(tmp_path: Path) -> None:
    for field in ("network_authority", "private_api_authority", "order_authority"):
        broken = _manifest()
        broken[field] = True
        path = tmp_path / f"{field}.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(MigrationError, match=field):
            load_manifest(path, project_root=tmp_path)


def test_manifest_rejects_globs_and_absolute_job_paths(tmp_path: Path) -> None:
    for value in ("runtime/*.json", "/tmp/unsafe.json"):
        broken = _manifest()
        broken["jobs"][0]["evidence_paths"] = [value]
        path = tmp_path / "station.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        with pytest.raises(MigrationError, match="explicit"):
            load_manifest(path, project_root=tmp_path)
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `python3 -m pytest -q tests/test_canonical_station_contract.py`

Expected: FAIL during import with `ModuleNotFoundError: No module named 'research_lab.canonical_station'`.

- [ ] **Step 3: Implement the minimal immutable contract**

Implement `research_lab/canonical_station.py` with frozen dataclasses and explicit path validation. `load_manifest` must reject duplicate JSON keys, non-object manifests, unsupported `schema_id`, every authority field that is not the exact required value, empty jobs, unknown `process_kind`, duplicate job names, globs, absolute launcher/evidence paths, forbidden credential/private/order argument fragments, and any launcher argument containing `--live`, `--place-order`, `--private-api`, or a credential token. `identity_fingerprint` must SHA-256 canonical JSON of the identity fields and must exclude freshness timestamps.

Write `configs/research/canonical_station_v1.json` with this exact job registry (the `source_paths`, `config_paths`, and `input_paths` lists are the files to hash into each launch/status receipt):

```json
{
  "schema_id": "canonical_research_station_v1",
  "authority": "research_only_no_live_or_promotion",
  "promotion_authority": false,
  "network_authority": false,
  "private_api_authority": false,
  "order_authority": false,
  "live_write_authority": false,
  "canonical_runtime_root": "runtime/local_research_station",
  "jobs": [
    {"name": "alpaca_adaptive_shadow", "process_kind": "deterministic_decision_loop", "screen_session": "canonical_alpaca_adaptive", "launcher": ["scripts/run_alpaca_adaptive_shadow_loop.sh"], "evidence_paths": ["runtime/alpaca_adaptive_v1_shadow_latest.json", "runtime/alpaca_adaptive_v1_shadow_ledger.jsonl"], "source_paths": ["scripts/alpaca_adaptive_shadow.py", "scripts/run_alpaca_adaptive_shadow_loop.sh"], "config_paths": ["configs/preregistered/alpaca_adaptive_historical_proxy_20260728.json"], "input_paths": ["research_lab/data/alpaca_pit_daily_v1/status.json"]},
    {"name": "xsec_v3_shadow", "process_kind": "market_snapshot_loop", "screen_session": "canonical_xsec_v3", "launcher": ["scripts/run_xsec_shadow_loop.sh"], "evidence_paths": ["runtime/xsec_v3_shadow/decision_latest.json", "runtime/xsec_v3_shadow/ledger.jsonl"], "source_paths": ["scripts/xsec_shadow_cycle.py", "research_lab/xsec_v3_reference.py", "scripts/run_xsec_shadow_loop.sh"], "config_paths": ["configs/preregistered/xsec_v4_family_landscape_20260728.json"], "input_paths": ["research_lab/data/bybit_instruments_linear.json"]},
    {"name": "funding_positioning_dynamic_shadow", "process_kind": "market_snapshot_loop", "screen_session": "canonical_funding_dynamic", "launcher": ["scripts/run_funding_positioning_dynamic_shadow_loop.sh"], "evidence_paths": ["runtime/funding_positioning_dynamic_shadow_summary.json", "runtime/funding_positioning_dynamic_shadow_ledger.jsonl"], "source_paths": ["scripts/build_funding_positioning_dynamic_universe.py", "scripts/funding_positioning_v4_shadow.py", "scripts/run_funding_positioning_dynamic_shadow_loop.sh"], "config_paths": ["configs/research/funding_positioning_dynamic_universe_prereg_20260729.json"], "input_paths": ["research_lab/data/cross_exchange_funding_history_180d.json"]},
    {"name": "funding_positioning_frozen_shadow", "process_kind": "market_snapshot_loop", "screen_session": "canonical_funding_frozen", "launcher": ["scripts/run_funding_positioning_post_n42_frozen_loop.sh"], "evidence_paths": ["runtime/funding_positioning_post_n42_frozen_summary.json", "runtime/funding_positioning_post_n42_frozen_ledger.jsonl"], "source_paths": ["scripts/funding_positioning_v4_shadow.py", "scripts/run_funding_positioning_post_n42_frozen_loop.sh"], "config_paths": ["configs/research/funding_positioning_post_n42_frozen_20260808.json"], "input_paths": ["research_lab/data/cross_exchange_funding_history_180d.json"]},
    {"name": "project_audit", "process_kind": "collector_supervisor", "screen_session": "canonical_project_audit", "launcher": ["scripts/run_project_audit_supervisor.sh", "--with-model", "--auto-full", "--loop", "--interval-sec", "21600"], "evidence_paths": ["runtime/project_audit/supervisor_status.json", "runtime/project_audit/registry.json"], "source_paths": ["scripts/run_project_audit_supervisor.sh", "research_lab/continuous_audit.py", "research_lab/ai_auditor.py"], "config_paths": [], "input_paths": ["configs/project_capability_registry_v1.json"]},
    {"name": "inplay_eth_prospective_shadow", "process_kind": "market_snapshot_loop", "screen_session": "canonical_inplay_prospective", "launcher": ["scripts/run_inplay_prospective_shadow_loop.sh"], "evidence_paths": ["runtime/inplay_prospective_shadow_v1/status.json"], "source_paths": ["scripts/run_inplay_prospective_shadow_loop.py", "scripts/collect_inplay_prospective_shadow.py"], "config_paths": ["research_lab/prereg/PREREG_INPLAY_CAUSAL_REPLAY_20260812.json"], "input_paths": ["research_lab/data/bybit_eth_m5_preholdout_20240301_20250930/status.json"]}
  ]
}
```

```python
MANIFEST_SCHEMA_ID = "canonical_research_station_v1"
AUTHORITY = "research_only_no_live_or_promotion"
REQUIRED_FALSE_AUTHORITY = (
    "promotion_authority", "network_authority", "private_api_authority",
    "order_authority", "live_write_authority",
)

def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")

class ProcessKind(str, Enum):
    DETERMINISTIC = "deterministic_decision_loop"
    MARKET_SNAPSHOT = "market_snapshot_loop"
    COLLECTOR = "collector_supervisor"

class ParityState(str, Enum):
    PASS = "PASS"
    FAIL_CLOSED = "FAIL_CLOSED"
    NOT_CONFIRMED = "NOT_CONFIRMED"

@dataclass(frozen=True)
class CanonicalJob:
    name: str
    process_kind: ProcessKind
    screen_session: str
    launcher: Sequence[str]
    evidence_paths: Sequence[str]
    evidence_epoch_env: str = "RESEARCH_STATION_EVIDENCE_EPOCH"

@dataclass(frozen=True)
class ProcessReceipt:
    job_name: str
    screen_name: str
    pid: int | None
    cwd: str | None
    command: str
    process_kind: ProcessKind
    identity: dict[str, str | None]
    counters: dict[str, int]
    timestamps: dict[str, str]
    evidence_paths: Sequence[str]
    evidence_epoch: str | None
    authority: dict[str, Any]
    status: ParityState

@dataclass(frozen=True)
class ParityReceipt:
    state: ParityState
    reason: str
    stop_allowed: bool
    compared_fields: Sequence[str] = ()
    observed_at_utc: str | None = None

def identity_fingerprint(receipt: ProcessReceipt) -> str:
    return hashlib.sha256(_canonical_json({
        "job_name": receipt.job_name,
        "screen_name": receipt.screen_name,
        "process_kind": receipt.process_kind.value,
        "identity": receipt.identity,
        "evidence_paths": receipt.evidence_paths,
        "evidence_epoch": receipt.evidence_epoch,
    })).hexdigest()

def validate_authority_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_id") != MANIFEST_SCHEMA_ID or manifest.get("authority") != AUTHORITY:
        raise MigrationError("canonical station schema or authority mismatch")
    for key in REQUIRED_FALSE_AUTHORITY:
        if manifest.get(key) is not False:
            raise MigrationError(f"{key} must be false")
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise MigrationError("jobs must be a non-empty list")
    names: set[str] = set()
    for index, job in enumerate(jobs):
        if not isinstance(job, dict) or not isinstance(job.get("name"), str):
            raise MigrationError(f"jobs[{index}].name is required")
        if job["name"] in names:
            raise MigrationError(f"duplicate job name: {job['name']}")
        names.add(job["name"])
        if job.get("process_kind") not in {kind.value for kind in ProcessKind}:
            raise MigrationError(f"jobs[{index}].process_kind is unsupported")
        for field in ("launcher", "evidence_paths", "source_paths", "config_paths", "input_paths"):
            values = job.get(field, [])
            if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                raise MigrationError(f"jobs[{index}].{field} must be explicit paths")
            if any(Path(value).is_absolute() or any(char in value for char in "*?[") for value in values):
                raise MigrationError(f"jobs[{index}].{field} must contain explicit relative paths")

def load_manifest(path: Path, project_root: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_authority_manifest(raw)
    root = project_root.resolve()
    for job in raw["jobs"]:
        launcher = root / job["launcher"][0]
        if not launcher.is_file():
            raise MigrationError(f"launcher does not exist: {launcher}")
    return raw

def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `python3 -m pytest -q tests/test_canonical_station_contract.py`

Expected: PASS with all contract rejection tests green.

- [ ] **Step 5: Commit the contract only**

```bash
git add configs/research/canonical_station_v1.json research_lab/canonical_station.py tests/test_canonical_station_contract.py
git commit -m "feat: define canonical research station contract"
```

### Task 2: Build legacy screen/process inventory receipts

**Files:**
- Modify: `research_lab/canonical_station.py`
- Create: `scripts/canonical_station_migration.py`
- Create: `tests/test_canonical_station_inventory.py`

**Interfaces:**
- Consumes: `screen -ls` output, `ps -eo pid=,ppid=,command=` output, per-PID cwd/command metadata, the canonical job manifest, and explicit legacy root.
- Produces: `parse_screen_sessions(output: str) -> list[str]`, `inventory_legacy_processes(manifest: Mapping[str, Any], screen_output: str, ps_output: str, cwd_by_pid: Mapping[int, str], file_roots: Mapping[str, Path], now_utc: str) -> dict[str, Any]`, `write_inventory_receipt(path: Path, receipt: Mapping[str, Any]) -> Path`, `_resolve_session_process(session: str, ps_output: str) -> tuple[int | None, str]`, `_build_process_receipt(manifest: Mapping[str, Any], session: str, pid: int | None, command: str, cwd_by_pid: Mapping[int, str], file_roots: Mapping[str, Path], now_utc: str) -> dict[str, Any]`, `_sha256_canonical(value: Any) -> str`, and CLI subcommand `inventory` writing `legacy_inventory.json` under `runtime/local_research_station/migrations/epoch_id/`.

- [ ] **Step 1: Write failing inventory tests**

```python
import json
from pathlib import Path

from scripts.canonical_station_migration import inventory_legacy_processes, parse_screen_sessions


def test_inventory_ignores_dead_screen_sockets_and_records_confirmed_identity(tmp_path: Path) -> None:
    screens = """There are screens on:\n\t111.old_xsec\t(Detached)\n\t222.old_funding\t(Dead ???)\n"""
    ps = "111 1 /bin/bash scripts/run_xsec_shadow_loop.sh"
    result = inventory_legacy_processes(
        manifest={"jobs": [{"name": "xsec", "screen_session": "old_xsec", "process_kind": "market_snapshot_loop", "evidence_paths": ["runtime/xsec/decision.json"]}]},
        screen_output=screens,
        ps_output=ps,
        cwd_by_pid={111: str(tmp_path)},
        file_roots={"runtime/xsec/decision.json": tmp_path / "decision.json"},
        now_utc="2026-08-29T10:00:00Z",
    )
    assert result["processes"][0]["status"] == "CONFIRMED"
    assert result["processes"][0]["pid"] == 111
    assert result["processes"][0]["cwd"] == str(tmp_path)


def test_unknown_command_or_config_is_not_confirmed_and_never_auto_stoppable(tmp_path: Path) -> None:
    result = inventory_legacy_processes(
        manifest={"jobs": [{"name": "fixture", "screen_session": "old_fixture", "process_kind": "deterministic_decision_loop", "evidence_paths": []}]},
        screen_output="There are screens on:\n\t333.old_fixture\t(Detached)\n",
        ps_output="333 1 python unknown.py",
        cwd_by_pid={333: str(tmp_path)},
        file_roots={},
        now_utc="2026-08-29T10:00:00Z",
    )
    row = result["processes"][0]
    assert row["status"] == "NOT_CONFIRMED"
    assert row["stop_allowed"] is False
    assert row["identity_reason"] == "command_or_config_identity_unrecoverable"


def test_inventory_receipt_contains_hashes_counters_and_legacy_epoch(tmp_path: Path) -> None:
    artifact = tmp_path / "decision.json"
    artifact.write_text('{"counter": 4}\n', encoding="utf-8")
    receipt = inventory_legacy_processes(
        manifest={"jobs": [{"name": "fixture", "screen_session": "old_fixture", "process_kind": "deterministic_decision_loop", "evidence_paths": ["runtime/fixture/decision.json"]}]},
        screen_output="There are screens on:\n\t444.old_fixture\t(Detached)\n",
        ps_output="444 1 scripts/run_fixture.sh --config configs/fixture.json",
        cwd_by_pid={444: str(tmp_path)},
        file_roots={"runtime/fixture/decision.json": artifact},
        now_utc="2026-08-29T10:00:00Z",
    )
    row = receipt["processes"][0]
    assert row["evidence"][0]["sha256"]
    assert row["counters"] == {"counter": 4}
    assert receipt["legacy_epoch"] == "legacy_2026-08-29T10:00:00Z"
```

- [ ] **Step 2: Run the inventory tests to verify they fail**

Run: `python3 -m pytest -q tests/test_canonical_station_inventory.py`

Expected: FAIL because `scripts.canonical_station_migration` and `inventory_legacy_processes` do not exist.

- [ ] **Step 3: Implement read-only inventory and receipt writing**

Parse only live detached sessions, matching by the manifest’s explicit session marker. Resolve PID command and cwd through injected readers so tests never inspect the host. Hash existing code/config/state/output files under the legacy root, extract integer counters from JSON evidence where present, and set `NOT_CONFIRMED` whenever command, cwd, job, config, or process kind cannot be mapped. The inventory command may create only the new canonical migration directory and receipt; it must never write below `--legacy-root`.

```python
def parse_screen_sessions(output: str) -> list[str]:
    return sorted({
        name for raw in output.splitlines()
        if "dead" not in raw.lower() and "." in raw
        for pid, name in [raw.strip().split("\t", 1)[0].split(".", 1)]
        if pid.isdigit() and name
    })

def inventory_legacy_processes(*, manifest: Mapping[str, Any], screen_output: str,
                               ps_output: str, cwd_by_pid: Mapping[int, str],
                               file_roots: Mapping[str, Path], now_utc: str) -> dict[str, Any]:
    processes = []
    for session in parse_screen_sessions(screen_output):
        pid, command = _resolve_session_process(session, ps_output)
        row = _build_process_receipt(manifest, session, pid, command, cwd_by_pid, file_roots, now_utc)
        processes.append(row)
    receipt = {"schema_id": "canonical_station_legacy_inventory_v1",
               "legacy_epoch": f"legacy_{now_utc}", "observed_at_utc": now_utc,
               "processes": processes}
    receipt["inventory_sha256"] = _sha256_canonical(receipt)
    return receipt

def _sha256_canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _resolve_session_process(session: str, ps_output: str) -> tuple[int | None, str]:
    marker = f".{session}"
    for line in ps_output.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and marker in fields[2]:
            try:
                return int(fields[0]), fields[2]
            except ValueError:
                return None, fields[2]
    return None, ""

def _build_process_receipt(manifest: Mapping[str, Any], session: str, pid: int | None,
                           command: str, cwd_by_pid: Mapping[int, str],
                           file_roots: Mapping[str, Path], now_utc: str) -> dict[str, Any]:
    job = next((item for item in manifest.get("jobs", []) if session == item.get("screen_session")), None)
    confirmed = bool(job and pid is not None and command and cwd_by_pid.get(pid))
    evidence = []
    counters: dict[str, int] = {}
    for logical_path, path in sorted(file_roots.items()):
        if not path.is_file():
            continue
        evidence.append({"path": logical_path, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        if isinstance(payload, dict):
            counters.update({key: int(value) for key, value in payload.items()
                             if isinstance(value, int) and not isinstance(value, bool)})
    return {
        "job_name": job.get("name") if job else None,
        "screen_name": session,
        "pid": pid,
        "cwd": cwd_by_pid.get(pid) if pid is not None else None,
        "command": command,
        "status": "CONFIRMED" if confirmed else "NOT_CONFIRMED",
        "stop_allowed": confirmed,
        "identity_reason": "confirmed" if confirmed else "command_or_config_identity_unrecoverable",
        "evidence": evidence,
        "counters": counters,
        "observed_at_utc": now_utc,
    }

def write_inventory_receipt(path: Path, receipt: Mapping[str, Any]) -> Path:
    atomic_write_json(path, receipt)
    return path
```

Keep process termination out of this module; the CLI layer may only stop an exact session after a hash-bound PASS receipt.

- [ ] **Step 4: Run tests and the read-only CLI smoke check**

Run: `python3 -m pytest -q tests/test_canonical_station_inventory.py`

Expected: PASS.

Run: `python3 scripts/canonical_station_migration.py inventory --project-root . --legacy-root /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28 --manifest configs/research/canonical_station_v1.json --evidence-epoch inventory_test --output /tmp/canonical-station-inventory-test.json`

Expected: exit 0, output JSON contains `legacy_epoch`, `processes`, and `inventory_sha256`; no legacy-root file mtime or bytes change.

- [ ] **Step 5: Commit the inventory layer**

```bash
git add research_lab/canonical_station.py scripts/canonical_station_migration.py tests/test_canonical_station_inventory.py
git commit -m "feat: record legacy research process inventory"
```

### Task 3: Add epoch-specific canonical launch routing and authority receipts

**Files:**
- Modify: `scripts/local_research_station.py`
- Modify: `scripts/run_alpaca_adaptive_shadow_loop.sh`
- Modify: `scripts/run_xsec_shadow_loop.sh`
- Modify: `scripts/run_funding_positioning_dynamic_shadow_loop.sh`
- Modify: `scripts/run_funding_positioning_post_n42_frozen_loop.sh`
- Modify: `scripts/run_inplay_prospective_shadow_loop.sh`
- Modify: `scripts/run_inplay_prospective_shadow_loop.py`
- Modify: `scripts/run_project_audit_supervisor.sh`
- Create: `tests/test_canonical_station_launch.py`

**Interfaces:**
- Consumes: validated `canonical_station_v1.json`, unique epoch, and recovery-tree root.
- Produces: `load_canonical_manifest() -> dict[str, Any]`, `build_canonical_launch_plan(manifest, project_root, epoch) -> Sequence[LaunchSpec]`, `_launch_spec_for_job(job: Mapping[str, Any], root: Path, epoch_root: Path, epoch: str) -> LaunchSpec`, `launch_canonical_jobs(plan: Sequence[LaunchSpec], dry_run: bool) -> dict[str, Any]`, `canonical_status(jobs: Sequence[Mapping[str, Any]], epoch: str, source_hashes: Mapping[str, str], run_id_identities: Mapping[str, str]) -> dict[str, Any]`, and status fields `authority`, all five required false authority fields, `evidence_epoch`, `runtime_root`, `evidence_paths`, `source_hashes`, and `run_id_identities`.

- [ ] **Step 1: Write failing launch/authority tests**

```python
import json
from pathlib import Path

import scripts.local_research_station as station
from scripts.canonical_station_migration import build_canonical_launch_plan


def test_launch_plan_is_epoch_specific_and_research_only(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/run_xsec_shadow_loop.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    manifest = {
        "schema_id": "canonical_research_station_v1",
        "authority": "research_only_no_live_or_promotion",
        "promotion_authority": False, "network_authority": False,
        "private_api_authority": False, "order_authority": False,
        "live_write_authority": False,
        "canonical_runtime_root": "runtime/local_research_station",
        "jobs": [{
            "name": "xsec", "process_kind": "market_snapshot_loop",
            "screen_session": "canonical_xsec",
            "launcher": ["scripts/run_xsec_shadow_loop.sh"],
            "evidence_paths": ["runtime/xsec_v3_shadow/decision_latest.json"],
        }],
    }
    plan = build_canonical_launch_plan(manifest, project_root=tmp_path, epoch="epoch_20260829_100000_abcd")
    assert plan[0].env["RESEARCH_STATION_EVIDENCE_EPOCH"] == "epoch_20260829_100000_abcd"
    assert plan[0].runtime_dir == tmp_path / "runtime/local_research_station/epochs/epoch_20260829_100000_abcd/xsec"
    assert "--live" not in plan[0].argv


def test_status_requires_exact_authority_and_factual_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(station, "ROOT", tmp_path)
    monkeypatch.setattr(station, "RUNTIME", tmp_path / "runtime/local_research_station")
    monkeypatch.setattr(station, "STATUS_PATH", tmp_path / "runtime/local_research_station/status.json")
    monkeypatch.setattr(station, "load_canonical_manifest", lambda: {
        "authority": "research_only_no_live_or_promotion",
        "promotion_authority": False, "network_authority": False,
        "private_api_authority": False, "order_authority": False,
        "live_write_authority": False,
    })
    monkeypatch.setattr(station, "JOBS", ())
    payload = station.run_cycle(start_missing=False)
    assert payload["authority"] == "research_only_no_live_or_promotion"
    assert payload["network_authority"] is False
    assert payload["private_api_authority"] is False
    assert payload["order_authority"] is False
    assert payload["live_write_authority"] is False
    assert payload["evidence_paths"] == []
```

- [ ] **Step 2: Run the launch tests to verify they fail**

Run: `python3 -m pytest -q tests/test_canonical_station_launch.py tests/test_local_research_station.py`

Expected: FAIL because launch planning, manifest loading in the supervisor, epoch routing, and exact authority status fields are not implemented.

- [ ] **Step 3: Implement runtime routing without changing strategy semantics**

Add `--runtime-dir`/epoch handling to each loop that already supports an output directory, and preserve its current defaults when no argument is supplied. For Alpaca pass epoch-specific `--cache-dir`, `--out-json`, `--out-md`, and `--ledger-jsonl`; for XSEC pass epoch-specific `--runtime-dir`; for funding pass epoch-specific state/ledger/summary paths; for Inplay pass epoch-specific `--runtime-dir`; for project audit add a runtime-root argument that relocates only its collector outputs and logs. Keep the existing public-data acknowledgement and lock behavior.

`build_canonical_launch_plan` must resolve all commands relative to the recovery root, create a directory such as `runtime/local_research_station/epochs/epoch_20260829_100000_abcd/xsec_v3_shadow`, set `RESEARCH_STATION_EVIDENCE_EPOCH`, `RESEARCH_ONLY=true`, and the five false authority variables, and reject any job whose command cannot be routed to an epoch-specific path. `local_research_station.py` must load the JSON manifest instead of using hidden job identity, preserve `Job` compatibility for current tests, and publish exact evidence paths and SHA-256 records.

```python
@dataclass(frozen=True)
class LaunchSpec:
    job_name: str
    screen_session: str
    argv: Sequence[str]
    cwd: Path
    runtime_dir: Path
    env: dict[str, str]

def load_canonical_manifest() -> dict[str, Any]:
    return load_manifest(ROOT / "configs/research/canonical_station_v1.json", project_root=ROOT)

def build_canonical_launch_plan(manifest: Mapping[str, Any], *, project_root: Path,
                               epoch: str) -> Sequence[LaunchSpec]:
    validate_authority_manifest(manifest)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{7,63}", epoch):
        raise MigrationError("evidence_epoch must be a unique explicit identifier")
    root = project_root.resolve()
    epoch_root = root / str(manifest["canonical_runtime_root"]) / "epochs" / epoch
    return tuple(_launch_spec_for_job(job, root=root, epoch_root=epoch_root, epoch=epoch)
                 for job in manifest["jobs"])

def _launch_spec_for_job(job: Mapping[str, Any], *, root: Path,
                         epoch_root: Path, epoch: str) -> LaunchSpec:
    runtime_dir = epoch_root / str(job["name"])
    argv = tuple(str(root / job["launcher"][0]), *[str(value) for value in job["launcher"][1:]])
    if "--runtime-dir" not in argv and job["process_kind"] != "collector_supervisor":
        argv = argv + ("--runtime-dir", str(runtime_dir))
    env = {"RESEARCH_STATION_EVIDENCE_EPOCH": epoch, "RESEARCH_ONLY": "true",
           "PROMOTION_AUTHORITY": "false", "NETWORK_AUTHORITY": "false",
           "PRIVATE_API_AUTHORITY": "false", "ORDER_AUTHORITY": "false",
           "LIVE_WRITE_AUTHORITY": "false"}
    return LaunchSpec(job_name=str(job["name"]), screen_session=str(job["screen_session"]),
                      argv=argv, cwd=root, runtime_dir=runtime_dir, env=env)

def launch_canonical_jobs(plan: Sequence[LaunchSpec], dry_run: bool) -> dict[str, Any]:
    rows = []
    for spec in plan:
        spec.runtime_dir.mkdir(parents=True, exist_ok=True)
        if dry_run:
            rows.append({"job_name": spec.job_name, "state": "DRY_RUN", "argv": list(spec.argv)})
            continue
        child = subprocess.Popen(list(spec.argv), cwd=spec.cwd, env={**os.environ, **spec.env})
        rows.append({"job_name": spec.job_name, "state": "STARTED", "pid": child.pid,
                     "screen_session": spec.screen_session, "runtime_dir": str(spec.runtime_dir)})
    return {"schema_id": "canonical_station_launch_v1", "jobs": rows,
            "authority": AUTHORITY, "promotion_authority": False,
            "network_authority": False, "private_api_authority": False,
            "order_authority": False, "live_write_authority": False}

def canonical_status(jobs: Sequence[Mapping[str, Any]], epoch: str,
                     source_hashes: Mapping[str, str], run_id_identities: Mapping[str, str]) -> dict[str, Any]:
    payload = {"schema_id": "local_research_station_status_v1",
               "authority": AUTHORITY, "promotion_authority": False,
               "network_authority": False, "private_api_authority": False,
               "order_authority": False, "live_write_authority": False,
               "research_only": True, "live_order_authority": False,
               "evidence_epoch": epoch, "runtime_root": "runtime/local_research_station",
               "evidence_paths": sorted({path for job in jobs for path in job.get("evidence_paths", [])}),
               "source_hashes": dict(sorted(source_hashes.items())),
               "run_id_identities": dict(sorted(run_id_identities.items())),
               "jobs": list(jobs)}
    payload["healthy"] = bool(jobs) and all(job.get("state") == "healthy" for job in jobs)
    return payload
```

Write the returned launch object atomically to `launch_receipt.json` with PID/session, command, cwd, epoch, runtime path, authority fields, and source/config/input hashes. Validate its authority fields before starting each process; a non-research-only field raises `MigrationError` before `subprocess.Popen`.

- [ ] **Step 4: Run focused tests and shell syntax checks**

Run: `python3 -m pytest -q tests/test_canonical_station_launch.py tests/test_local_research_station.py`

Expected: PASS.

Run: `bash -n scripts/run_alpaca_adaptive_shadow_loop.sh scripts/run_xsec_shadow_loop.sh scripts/run_funding_positioning_dynamic_shadow_loop.sh scripts/run_funding_positioning_post_n42_frozen_loop.sh scripts/run_project_audit_supervisor.sh && python3 -m py_compile scripts/run_inplay_prospective_shadow_loop.py scripts/local_research_station.py scripts/canonical_station_migration.py`

Expected: exit 0 with no output.

- [ ] **Step 5: Commit canonical launch routing**

```bash
git add scripts/local_research_station.py scripts/run_alpaca_adaptive_shadow_loop.sh scripts/run_xsec_shadow_loop.sh scripts/run_funding_positioning_dynamic_shadow_loop.sh scripts/run_funding_positioning_post_n42_frozen_loop.sh scripts/run_inplay_prospective_shadow_loop.py scripts/run_project_audit_supervisor.sh scripts/canonical_station_migration.py tests/test_canonical_station_launch.py
git commit -m "feat: route research loops through canonical evidence epochs"
```

### Task 4: Implement deterministic, snapshot, and collector parity checks

**Files:**
- Modify: `research_lab/canonical_station.py`
- Modify: `scripts/canonical_station_migration.py`
- Create: `tests/test_canonical_station_parity.py`

**Interfaces:**
- Consumes: legacy and canonical `ProcessReceipt` values, immutable evidence snapshots, source/config/input hashes, and Station V3 completion/ledger files.
- Produces: `_validate_receipt_authority(receipt: ProcessReceipt) -> None`, `_compare_identity_and_economics(old: ProcessReceipt, new: ProcessReceipt) -> ParityReceipt`, `compare_deterministic_receipts(old: ProcessReceipt, new: ProcessReceipt) -> ParityReceipt`, `compare_market_snapshot_receipts(old: ProcessReceipt, new: ProcessReceipt) -> ParityReceipt`, `compare_collector_snapshots(old: ProcessReceipt, new: ProcessReceipt) -> ParityReceipt`, `validate_completion_proof(run_dir: Path) -> None`, and `register_run_identity(path: Path, run_id: str, fingerprint: str, receipt: Mapping[str, Any]) -> None`.

- [ ] **Step 1: Write failing parity tests**

```python
import json
from pathlib import Path

from research_lab.canonical_station import (
    ParityState,
    ProcessReceipt,
    compare_collector_snapshots,
    compare_deterministic_receipts,
    compare_market_snapshot_receipts,
    register_run_identity,
)


def receipt(kind: str, **kwargs) -> ProcessReceipt:
    base = dict(job_name="fixture", screen_name="fixture", pid=1, cwd="/repo",
                command="run", process_kind=kind, identity={"config_sha256": "c"},
                counters={"decisions": 1}, timestamps={"source_ts": "2026-08-29T10:00:00Z"},
                evidence_paths=("runtime/fixture.json",), evidence_epoch="e1",
                authority={"authority": "research_only_no_live_or_promotion",
                           "promotion_authority": False, "network_authority": False,
                           "private_api_authority": False, "order_authority": False,
                           "live_write_authority": False}, status=ParityState.PASS)
    base.update(kwargs)
    return ProcessReceipt(**base)


def test_deterministic_parity_requires_exact_decision_and_economic_fields() -> None:
    old = receipt("deterministic_decision_loop", identity={"decision_id": "a", "net_r": "1.0"})
    new = receipt("deterministic_decision_loop", identity={"decision_id": "a", "net_r": "1.0"})
    assert compare_deterministic_receipts(old, new).state == ParityState.PASS
    changed = receipt("deterministic_decision_loop", identity={"decision_id": "a", "net_r": "0.9"})
    assert compare_deterministic_receipts(old, changed).state == ParityState.FAIL_CLOSED


def test_market_snapshot_without_shared_closed_timestamp_stays_not_confirmed() -> None:
    old = receipt("market_snapshot_loop", timestamps={"source_ts": "2026-08-29T10:00:00Z"})
    new = receipt("market_snapshot_loop", timestamps={"source_ts": "2026-08-29T10:01:00Z"})
    result = compare_market_snapshot_receipts(old, new)
    assert result.state == ParityState.NOT_CONFIRMED
    assert result.stop_allowed is False


def test_collector_parity_ignores_freshness_but_requires_content_hashes() -> None:
    old = receipt("collector_supervisor", identity={"source_sha256": "a", "count": 2}, timestamps={"fresh": "1"})
    new = receipt("collector_supervisor", identity={"source_sha256": "a", "count": 2}, timestamps={"fresh": "2"})
    assert compare_collector_snapshots(old, new).state == ParityState.PASS


def test_conflicting_run_identity_is_terminal(tmp_path: Path) -> None:
    path = tmp_path / "run_identity_registry.jsonl"
    register_run_identity(path, "run-1", "hash-a", {"source": "old"})
    try:
        register_run_identity(path, "run-1", "hash-b", {"source": "new"})
    except RuntimeError as exc:
        assert "incompatible identity" in str(exc)
    else:
        raise AssertionError("conflicting run identity was accepted")
```

- [ ] **Step 2: Run the parity tests to verify they fail**

Run: `python3 -m pytest -q tests/test_canonical_station_parity.py`

Expected: FAIL because the parity functions and identity registry do not exist.

- [ ] **Step 3: Implement parity and completion validation**

The deterministic comparator must compare source timestamp, config/input/code hashes, decision ID, intended fill, exit, cost, funding, and every declared economic field. The market comparator must return `NOT_CONFIRMED` (not `FAIL` and never `PASS`) when the closed source timestamp differs or is absent. The collector comparator must compare immutable source identities, counts, file sizes, and SHA-256 content hashes while ignoring only freshness timestamps. Every comparator must validate all authority fields first.

`validate_completion_proof` must load `completion.json`, `manifest.json`, `checkpoint.json`, and `trials.jsonl`, verify `state=COMPLETED`, `authority`, `promotion_authority`, manifest SHA, ledger-tail SHA, and the complete successful ledger. It must ignore any `*.log`. `register_run_identity` must append an fsync’d JSONL row and reject an existing run ID whose fingerprint differs; the rejection is terminal for that run ID.

```python
def compare_market_snapshot_receipts(old: ProcessReceipt, new: ProcessReceipt) -> ParityReceipt:
    _validate_receipt_authority(old)
    _validate_receipt_authority(new)
    left = old.timestamps.get("closed_source_ts") or old.timestamps.get("source_ts")
    right = new.timestamps.get("closed_source_ts") or new.timestamps.get("source_ts")
    if not left or not right or left != right:
        return ParityReceipt(state=ParityState.NOT_CONFIRMED,
                             reason="shared_closed_source_timestamp_unavailable",
                             stop_allowed=False)
    return _compare_identity_and_economics(old, new)

def _validate_receipt_authority(receipt: ProcessReceipt) -> None:
    expected = {"authority": AUTHORITY, "promotion_authority": False,
                "network_authority": False, "private_api_authority": False,
                "order_authority": False, "live_write_authority": False}
    if any(receipt.authority.get(key) != value for key, value in expected.items()):
        raise MigrationError("receipt authority drift")

def _compare_identity_and_economics(old: ProcessReceipt, new: ProcessReceipt) -> ParityReceipt:
    fields = tuple(sorted(set(old.identity) | set(new.identity)))
    if old.process_kind != new.process_kind or any(old.identity.get(key) != new.identity.get(key) for key in fields):
        return ParityReceipt(state=ParityState.FAIL_CLOSED, reason="identity_or_economic_field_mismatch", stop_allowed=False, compared_fields=fields)
    return ParityReceipt(state=ParityState.PASS, reason="identity_and_economics_match", stop_allowed=True, compared_fields=fields)

def compare_deterministic_receipts(old: ProcessReceipt, new: ProcessReceipt) -> ParityReceipt:
    _validate_receipt_authority(old)
    _validate_receipt_authority(new)
    if old.timestamps != new.timestamps or old.evidence_paths != new.evidence_paths:
        return ParityReceipt(state=ParityState.FAIL_CLOSED, reason="source_or_evidence_mismatch", stop_allowed=False)
    return _compare_identity_and_economics(old, new)

def compare_collector_snapshots(old: ProcessReceipt, new: ProcessReceipt) -> ParityReceipt:
    _validate_receipt_authority(old)
    _validate_receipt_authority(new)
    left = {key: value for key, value in old.identity.items() if key not in {"freshness", "updated_at_utc"}}
    right = {key: value for key, value in new.identity.items() if key not in {"freshness", "updated_at_utc"}}
    if left != right:
        return ParityReceipt(state=ParityState.FAIL_CLOSED, reason="immutable_snapshot_mismatch", stop_allowed=False)
    return ParityReceipt(state=ParityState.PASS, reason="immutable_snapshot_match", stop_allowed=True)

def validate_completion_proof(run_dir: Path) -> None:
    completion = json.loads((run_dir / "completion.json").read_text(encoding="utf-8"))
    manifest_bytes = (run_dir / "manifest.json").read_bytes()
    ledger_rows = [json.loads(line) for line in (run_dir / "trials.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if completion.get("state") != "COMPLETED" or completion.get("authority") != AUTHORITY or completion.get("promotion_authority") is not False:
        raise MigrationError("invalid Station V3 completion authority")
    if completion.get("manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest():
        raise MigrationError("Station V3 completion manifest hash mismatch")
    expected_tail = ledger_rows[-1].get("record_sha256") if ledger_rows else "0" * 64
    if completion.get("ledger_tail_sha256") != expected_tail:
        raise MigrationError("Station V3 completion ledger-tail mismatch")

def register_run_identity(path: Path, run_id: str, fingerprint: str, receipt: Mapping[str, Any]) -> None:
    existing = []
    if path.exists():
        existing = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    for row in existing:
        if row.get("run_id") == run_id and row.get("fingerprint") != fingerprint:
            raise MigrationError("incompatible identity for run ID")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"run_id": run_id, "fingerprint": fingerprint, "receipt": dict(receipt)}, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
```

- [ ] **Step 4: Run parity and Station V3 regression tests**

Run: `python3 -m pytest -q tests/test_canonical_station_parity.py tests/test_research_station_v3.py`

Expected: PASS; existing Station V3 completion and hash-drift behavior remains green.

- [ ] **Step 5: Commit parity and identity controls**

```bash
git add research_lab/canonical_station.py scripts/canonical_station_migration.py tests/test_canonical_station_parity.py
git commit -m "feat: enforce canonical station parity and run identity"
```

### Task 5: Orchestrate fail-closed migration and conditional legacy shutdown

**Files:**
- Modify: `scripts/canonical_station_migration.py`
- Create: `tests/test_canonical_station_migration.py`
- Modify: `tests/test_local_research_station.py`

**Interfaces:**
- Consumes: manifest, legacy inventory receipt, canonical launch receipt, fresh heartbeat/evidence receipts, parity results, and explicit screen names.
- Produces: CLI subcommands `inventory`, `launch`, `verify`, `stop`, and `migrate`; `run_migration(manifest: Mapping[str, Any], legacy_inventory: Mapping[str, Any], launch_fn: Callable[[], Mapping[str, Any]], verify_fn: Callable[[], Mapping[str, Any]], stop_fn: Callable[[str], None], output_dir: Path) -> dict[str, Any]`; `stop_legacy_session(screen_name: str, inventory: Mapping[str, Any], parity_receipt: Mapping[str, Any], dry_run: bool = False) -> dict[str, Any]`; migration receipt with terminal `PASS`, `FAIL_CLOSED`, or `NOT_CONFIRMED`.

- [ ] **Step 1: Write failing migration safety tests**

```python
import json
from pathlib import Path

import pytest

from scripts.canonical_station_migration import run_migration


def test_unknown_identity_launches_canonical_copy_but_does_not_stop_legacy(tmp_path: Path) -> None:
    old = {"status": "NOT_CONFIRMED", "screen_name": "old_fixture", "stop_allowed": False}
    new = {"status": "PASS", "screen_name": "canonical_fixture", "evidence_epoch": "e_20260829_abcd"}
    result = run_migration(
        manifest={"jobs": []}, legacy_inventory={"processes": [old]},
        launch_fn=lambda: new, verify_fn=lambda: {"state": "NOT_CONFIRMED", "stop_allowed": False},
        stop_fn=lambda _: (_ for _ in ()).throw(AssertionError("legacy stop must not run")),
        output_dir=tmp_path,
    )
    assert result["state"] == "NOT_CONFIRMED"
    assert result["legacy_stop"] == []


def test_all_parity_pass_stops_only_named_legacy_sessions_and_keeps_files(tmp_path: Path) -> None:
    stopped: list[str] = []
    result = run_migration(
        manifest={"jobs": []},
        legacy_inventory={"processes": [{"status": "CONFIRMED", "screen_name": "old_fixture", "stop_allowed": True}]},
        launch_fn=lambda: {"status": "PASS", "screen_name": "canonical_fixture"},
        verify_fn=lambda: {"state": "PASS", "stop_allowed": True},
        stop_fn=lambda name: stopped.append(name),
        output_dir=tmp_path,
    )
    assert result["state"] == "PASS"
    assert stopped == ["old_fixture"]


def test_parity_failure_is_fail_closed_and_never_stops(tmp_path: Path) -> None:
    stopped: list[str] = []
    result = run_migration(
        manifest={"jobs": []},
        legacy_inventory={"processes": [{"status": "CONFIRMED", "screen_name": "old_fixture", "stop_allowed": True}]},
        launch_fn=lambda: {"status": "PASS"},
        verify_fn=lambda: {"state": "FAIL_CLOSED", "stop_allowed": False, "reason": "authority_drift"},
        stop_fn=stopped.append,
        output_dir=tmp_path,
    )
    assert result["state"] == "FAIL_CLOSED"
    assert stopped == []


def test_stop_command_requires_hash_bound_pass_receipt(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="stop requires PASS"):
        run_migration(
            manifest={"jobs": []}, legacy_inventory={"processes": []},
            launch_fn=lambda: {}, verify_fn=lambda: {"state": "NOT_CONFIRMED"},
            stop_fn=lambda _: None, output_dir=tmp_path,
        )
```

- [ ] **Step 2: Run migration tests to verify they fail**

Run: `python3 -m pytest -q tests/test_canonical_station_migration.py`

Expected: FAIL because `run_migration` does not exist.

- [ ] **Step 3: Implement the fail-closed state machine**

The state machine must write separate inventory, launch, parity, and migration receipts atomically under `runtime/local_research_station/migrations/epoch_id/`. It may launch a canonical job after authority validation even when a legacy identity is `NOT_CONFIRMED`, but it may stop a legacy session only when that exact session is `CONFIRMED`, its canonical replacement has a fresh receipt, its process-kind comparator is `PASS`, all authority fields are exact, completion proof is valid where Station V3 is involved, and the migration receipt is itself hash-bound. A market-snapshot `NOT_CONFIRMED` result leaves the old screen running. Any subprocess launch error, missing heartbeat, stale evidence, hash mismatch, unknown session, or receipt write failure returns `FAIL_CLOSED` and performs no stop.

Use `screen -S old_fixture -X quit` (with the exact validated inventory value substituted) only inside `stop_legacy_session` after validating the name against the inventory receipt and a `PASS` parity receipt. Never use a substring kill, `pkill`, `killall`, or a PID from an unverified command. Record the command, return code, post-stop screen listing, and timestamp; if the session remains present, the migration is `FAIL_CLOSED`.

Implement the state transition as explicit code so no callback can stop a legacy session early:

```python
def run_migration(*, manifest: Mapping[str, Any], legacy_inventory: Mapping[str, Any],
                  launch_fn: Callable[[], Mapping[str, Any]], verify_fn: Callable[[], Mapping[str, Any]],
                  stop_fn: Callable[[str], None], output_dir: Path) -> dict[str, Any]:
    validate_authority_manifest(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    launch_receipt = dict(launch_fn())
    parity_receipt = dict(verify_fn())
    state = str(parity_receipt.get("state"))
    stopped: list[str] = []
    if state == "PASS" and parity_receipt.get("stop_allowed") is True:
        for row in legacy_inventory.get("processes", []):
            if row.get("status") == "CONFIRMED" and row.get("stop_allowed") is True:
                stop_fn(str(row["screen_name"]))
                stopped.append(str(row["screen_name"]))
    elif state not in {"NOT_CONFIRMED", "FAIL_CLOSED"}:
        state = "FAIL_CLOSED"
    result = {"schema_id": "canonical_station_migration_v1", "state": state,
              "launch": launch_receipt, "parity": parity_receipt,
              "legacy_stop": stopped, "reopen_condition": "fresh inventory and parity PASS"}
    atomic_write_json(output_dir / "migration_receipt.json", result)
    return result

def stop_legacy_session(screen_name: str, inventory: Mapping[str, Any],
                        parity_receipt: Mapping[str, Any], dry_run: bool = False) -> dict[str, Any]:
    known = any(row.get("screen_name") == screen_name and row.get("status") == "CONFIRMED"
                and row.get("stop_allowed") is True for row in inventory.get("processes", []))
    if not known or parity_receipt.get("state") != "PASS" or parity_receipt.get("stop_allowed") is not True:
        raise MigrationError("stop requires PASS inventory and parity receipts")
    if dry_run:
        return {"screen_name": screen_name, "state": "DRY_RUN", "command": ["screen", "-S", screen_name, "-X", "quit"]}
    result = subprocess.run(["screen", "-S", screen_name, "-X", "quit"], check=False, capture_output=True, text=True)
    after = subprocess.run(["screen", "-ls"], check=False, capture_output=True, text=True)
    if result.returncode != 0 or screen_name in parse_screen_sessions(after.stdout):
        raise MigrationError(f"legacy session did not stop cleanly: {screen_name}")
    return {"screen_name": screen_name, "state": "STOPPED", "returncode": result.returncode}
```

- [ ] **Step 4: Run focused safety tests and a dry-run CLI**

Run: `python3 -m pytest -q tests/test_canonical_station_migration.py tests/test_local_research_station.py`

Expected: PASS.

Run: `python3 scripts/canonical_station_migration.py migrate --project-root . --legacy-root /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28 --manifest configs/research/canonical_station_v1.json --evidence-epoch dryrun_20260829_abcd --dry-run --output runtime/local_research_station/migrations/dryrun_20260829_abcd`

Expected: exit 0 with a migration receipt whose `state` is `NOT_CONFIRMED` or `FAIL_CLOSED` when live legacy identity/heartbeat cannot be proven; no screen session is stopped and no legacy file changes.

- [ ] **Step 5: Commit the guarded migration state machine**

```bash
git add scripts/canonical_station_migration.py tests/test_canonical_station_migration.py tests/test_local_research_station.py
git commit -m "feat: fail closed during canonical station migration"
```

### Task 6: Enforce the canonical station gate in status/audit and document operations

**Files:**
- Modify: `research_lab/research_pipeline_audit.py`
- Modify: `tests/test_research_pipeline_audit.py`
- Modify: `research_lab/RESEARCH_STATION_V3.md`
- Modify: `START_RESEARCH_STATION.command`
- Modify: `deploy/com.tradingstation.research-station.plist.in`
- Modify: `scripts/install_research_station_launchagent.sh`

**Interfaces:**
- Consumes: `runtime/local_research_station/status.json`, canonical manifest, migration receipts, and Station V3 completion proofs.
- Produces: `canonical_station_gate(status: Mapping[str, Any]) -> tuple[bool, list[str]]`, audit finding `canonical_station_not_confirmed` unless exact authority/path/hash/epoch gates pass, plus operator commands for inventory, dry-run migration, verification, and post-PASS stop.

- [ ] **Step 1: Write failing audit and documentation checks**

```python
import json
from datetime import datetime, timezone

from research_lab.research_pipeline_audit import audit


def test_audit_rejects_legacy_shape_even_when_station_says_healthy(tmp_path) -> None:
    station_dir = tmp_path / "runtime/local_research_station"
    station_dir.mkdir(parents=True)
    (station_dir / "status.json").write_text(json.dumps({
        "generated_at_utc": "2026-08-29T09:59:00Z",
        "healthy": True,
        "live_order_authority": False,
        "jobs": [{"state": "healthy", "live_order_authority": False}],
    }), encoding="utf-8")
    result = audit(tmp_path, now=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc))
    assert "canonical_station_not_confirmed" in result["findings"]
    assert result["continuous_station"]["healthy"] is False


def test_audit_accepts_exact_canonical_authority_paths_and_hashes(tmp_path) -> None:
    station_dir = tmp_path / "runtime/local_research_station"
    station_dir.mkdir(parents=True)
    (station_dir / "status.json").write_text(json.dumps({
        "schema_id": "local_research_station_status_v1",
        "generated_at_utc": "2026-08-29T09:59:00Z",
        "healthy": True,
        "authority": "research_only_no_live_or_promotion",
        "promotion_authority": False, "network_authority": False,
        "private_api_authority": False, "order_authority": False,
        "live_write_authority": False,
        "evidence_epoch": "epoch_20260829_abcd",
        "evidence_paths": ["runtime/fixture/decision.json"],
        "source_hashes": {"scripts/fixture.py": "a" * 64},
        "run_id_identities": {"fixture_run": "b" * 64},
        "jobs": [{"state": "healthy", "live_order_authority": False,
                   "evidence_path": "runtime/fixture/decision.json",
                   "source_hashes": {"scripts/fixture.py": "a" * 64}}],
    }), encoding="utf-8")
    result = audit(tmp_path, now=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc))
    assert result["continuous_station"]["healthy"] is True
```

- [ ] **Step 2: Run the audit tests to verify they fail**

Run: `python3 -m pytest -q tests/test_research_pipeline_audit.py`

Expected: FAIL because the audit currently trusts the old two-field station shape.

- [ ] **Step 3: Implement gate validation and operator documentation**

Update `research_pipeline_audit.py` so station health requires the exact authority fields, non-empty factual evidence paths, source/config/input hashes for every healthy job, one active evidence epoch, and no duplicate/conflicting run identity. Preserve the existing distinction between healthy collectors and an open idea-to-experiment bridge. Add `canonical_station` details to the JSON audit output and retain the read-only/no-promotion authority string.

Implement the gate as a pure validator called by `audit`:

```python
def canonical_station_gate(status: Mapping[str, Any]) -> tuple[bool, list[str]]:
    required = {"authority": "research_only_no_live_or_promotion",
                "promotion_authority": False, "network_authority": False,
                "private_api_authority": False, "order_authority": False,
                "live_write_authority": False}
    failures = [key for key, value in required.items() if status.get(key) != value]
    if not isinstance(status.get("evidence_epoch"), str) or not status["evidence_epoch"]:
        failures.append("evidence_epoch")
    if not status.get("evidence_paths"):
        failures.append("evidence_paths")
    if not status.get("source_hashes") or not status.get("run_id_identities"):
        failures.append("source_or_run_hashes")
    jobs = status.get("jobs") if isinstance(status.get("jobs"), list) else []
    for job in jobs:
        if job.get("state") == "healthy" and (not job.get("evidence_path") or not job.get("source_hashes")):
            failures.append(f"job:{job.get('name', 'unknown')}:evidence_or_hashes")
    return not failures and bool(status.get("healthy")), failures
```

Update the Station V3 guide and launch files with the exact recovery-tree commands:

```bash
python3 scripts/canonical_station_migration.py inventory \
  --project-root . \
  --legacy-root /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28 \
  --manifest configs/research/canonical_station_v1.json \
  --evidence-epoch inventory_20260829_abcd

python3 scripts/canonical_station_migration.py migrate \
  --project-root . \
  --legacy-root /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28 \
  --manifest configs/research/canonical_station_v1.json \
  --evidence-epoch migrate_20260829_abcd

python3 -m pytest -q tests/test_canonical_station_contract.py tests/test_canonical_station_inventory.py tests/test_canonical_station_launch.py tests/test_canonical_station_parity.py tests/test_canonical_station_migration.py tests/test_local_research_station.py tests/test_research_station_v3.py tests/test_research_pipeline_audit.py
```

The launcher/plist must invoke only the recovery-tree script and keep a single supervisor lock. The installer must report the canonical status path and `mode=research_only_no_live_orders`; it must not remove or rewrite any legacy runtime path.

- [ ] **Step 4: Run the complete scoped verification**

Run: `python3 -m pytest -q tests/test_canonical_station_contract.py tests/test_canonical_station_inventory.py tests/test_canonical_station_launch.py tests/test_canonical_station_parity.py tests/test_canonical_station_migration.py tests/test_local_research_station.py tests/test_research_station_v3.py tests/test_research_pipeline_audit.py`

Expected: PASS.

Run: `git diff --check`

Expected: exit 0 with no whitespace errors.

Run: `bash -n START_RESEARCH_STATION.command scripts/install_research_station_launchagent.sh scripts/run_alpaca_adaptive_shadow_loop.sh scripts/run_xsec_shadow_loop.sh scripts/run_funding_positioning_dynamic_shadow_loop.sh scripts/run_funding_positioning_post_n42_frozen_loop.sh scripts/run_inplay_prospective_shadow_loop.sh scripts/run_project_audit_supervisor.sh`

Expected: exit 0 with no shell syntax errors.

Run: `sed 's|__ROOT__|/tmp/canonical-research-root|g' deploy/com.tradingstation.research-station.plist.in | plutil -lint -`

Expected: `plutil` prints `OK`; the source template remains unchanged.

- [ ] **Step 5: Commit the final gate/documentation changes**

```bash
git add research_lab/research_pipeline_audit.py tests/test_research_pipeline_audit.py research_lab/RESEARCH_STATION_V3.md START_RESEARCH_STATION.command deploy/com.tradingstation.research-station.plist.in scripts/install_research_station_launchagent.sh
git commit -m "docs: document canonical research station migration gate"
```

## Self-review checklist

- [ ] Section 3’s six migration steps are represented: legacy receipt, `NOT_CONFIRMED` hold, research-only epoch launch, exact authority manifest, three process-kind parity modes, and stop only after PASS.
- [ ] Station V3 remains the immutable runner and `completion.json`/manifest/ledger-tail proof is explicitly validated; logs never establish completion.
- [ ] Old evidence is retained and separated from canonical epochs; no migration path deletes or overwrites the legacy tree.
- [ ] Status/audit cannot be green on stale legacy shape, missing evidence paths, missing source/config/input hashes, or conflicting run identity.
- [ ] Every implementation unit has red tests, a focused command with an expected result, green tests, and a frequent commit.
- [ ] No task grants live, broker, order, risk, network, private API, money, or promotion authority.
