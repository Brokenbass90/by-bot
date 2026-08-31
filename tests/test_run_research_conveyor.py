import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

from research_lab.research_conveyor_contract import ContractError, load_manifest
from scripts.run_research_conveyor import run_conveyor


AUTH = "research_only_no_live_risk_order_promotion_or_private_api_authority"

_ADAPTER = r'''import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--run-dir", required=True)
parser.add_argument("--hypothesis-id", required=True)
parser.add_argument("--phase", required=True)
parser.add_argument("--receipt", required=True)
parser.add_argument("--behavior", default="pass")
args = parser.parse_args()

if args.behavior == "timeout":
    time.sleep(5)
if args.behavior == "timeout_child":
    marker = repr(str(Path(args.run_dir) / "orphaned-child.txt"))
    subprocess.Popen([sys.executable, "-c", "import time; from pathlib import Path; time.sleep(1); Path(" + marker + ").write_text('orphaned', encoding='utf-8')"])
    time.sleep(5)
if args.behavior == "timeout_term_ignoring_child":
    marker = repr(str(Path(args.run_dir) / "term-ignoring-child.txt"))
    child = "import signal, time; from pathlib import Path; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(2); Path(" + marker + ").write_text('survived', encoding='utf-8')"
    subprocess.Popen([sys.executable, "-c", child])
    signal.signal(signal.SIGTERM, lambda *_: raise_system_exit())
    def raise_system_exit():
        raise SystemExit(0)
    time.sleep(5)
if args.behavior == "nonzero":
    raise SystemExit(7)
if args.behavior == "missing":
    raise SystemExit(0)
if args.behavior == "flood":
    sys.stdout.write("o" * 200000)
    sys.stderr.write("e" * 200000)

run_dir = Path(args.run_dir)
launches = run_dir / "phase-launches.txt"
with launches.open("a", encoding="utf-8") as stream:
    stream.write(args.hypothesis_id + ":" + args.phase + "\n")
if any(any(word in name.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "PRIVATE")) for name in os.environ):
    (run_dir / "secret_seen").write_text("yes", encoding="utf-8")
if args.behavior == "mutate_contract":
    (Path.cwd() / "contract.txt").write_text("changed\n", encoding="utf-8")
if args.behavior == "mutate_final_contract" and args.phase == "stress":
    (Path.cwd() / "contract.txt").write_text("changed-at-final-phase\n", encoding="utf-8")
if args.behavior == "mutate_adapter":
    Path(sys.argv[0]).write_text("# adapter drift\n", encoding="utf-8")

if args.behavior == "tampered":
    Path(args.receipt).write_text('{"tampered":true}', encoding="utf-8")
    raise SystemExit(0)

manifest = json.loads((run_dir / "manifest_snapshot.json").read_text(encoding="utf-8"))
hypothesis = next(item for item in manifest["hypotheses"] if item["id"] == args.hypothesis_id)
canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
payload = {
    "schema_id": "research_conveyor_phase_receipt_v1",
    "authority": "research_only_no_live_risk_order_promotion_or_private_api_authority",
    "hypothesis_id": args.hypothesis_id,
    "phase": args.phase,
    "status": "PASS",
    "manifest_sha256": hashlib.sha256(canonical(manifest)).hexdigest(),
    "preregistration_sha256": hashlib.sha256(canonical(hypothesis["preregistration"])).hexdigest(),
    "adapter_argv_sha256": hashlib.sha256(canonical([sys.executable, *sys.argv])).hexdigest(),
    "input_artifacts": [],
    "output_artifacts": [],
    "metrics": {},
    "live_or_broker_calls": False,
    "private_api_calls": False,
    "capital_or_promotion_authority": False,
}
if args.behavior == "reject":
    payload["status"] = "REJECT"
elif args.behavior == "bad_metrics":
    payload["metrics"] = []
elif args.behavior == "bad_boolean":
    payload["private_api_calls"] = 0
elif args.behavior.startswith("artifact"):
    output = run_dir / ("artifact-" + args.phase + ".txt")
    output.write_text("output-" + args.phase + "\n", encoding="utf-8")
    input_path = "contract.txt"
    output_path = str(output.relative_to(Path.cwd()))
    if args.behavior == "artifact_missing":
        input_path = "missing.txt"
    elif args.behavior == "artifact_escape":
        input_path = "../contract.txt"
    elif args.behavior == "artifact_absolute":
        input_path = str((Path.cwd() / "contract.txt").resolve())
    elif args.behavior == "artifact_glob":
        input_path = "*.txt"
    elif args.behavior == "artifact_input_symlink":
        link = Path.cwd() / "input-link.txt"
        link.symlink_to(Path.cwd() / "contract.txt")
        input_path = "input-link.txt"
    elif args.behavior == "artifact_symlink":
        link = run_dir / "output-link.txt"
        link.symlink_to(output)
        output_path = str(link.relative_to(Path.cwd()))
    elif args.behavior == "artifact_output_escape":
        output_path = "contract.txt"
    payload["input_artifacts"] = [{"path": input_path, "sha256": hashlib.sha256((Path.cwd() / "contract.txt").read_bytes()).hexdigest()}]
    payload["output_artifacts"] = [{"path": output_path, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}]
    if args.behavior == "artifact_stale":
        output.write_text("changed-after-hash\n", encoding="utf-8")
    elif args.behavior == "artifact_fake_hash":
        payload["input_artifacts"][0]["sha256"] = "0" * 64
payload["receipt_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
Path(args.receipt).parent.mkdir(parents=True, exist_ok=True)
Path(args.receipt).write_text(json.dumps(payload), encoding="utf-8")
'''


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def _card(identifier, priority, state="RUNNABLE", behavior="pass"):
    card = {
        "id": identifier,
        "title": identifier,
        "market": "test",
        "family": "test",
        "priority": priority,
        "state": state,
        "reopen_when": "test adapter exists",
        "contract_refs": ["contract.txt", "scripts/research_conveyor_phase_adapter.py"],
        "data_refs": [{"path": "data.csv", "min_count": 1, "sha256": hashlib.sha256(b"data\n").hexdigest()}],
        "preregistration": {name: name for name in ("hypothesis", "universe", "signal", "entry", "exit", "costs", "control", "stress", "concentration", "death_criteria", "acceptance_gate")},
    }
    if state == "RUNNABLE":
        card["adapters"] = {
            phase: ["{python}", "scripts/research_conveyor_phase_adapter.py", "--run-dir", "{run_dir}", "--hypothesis-id", "{hypothesis_id}", "--phase", "{phase}", "--receipt", "{receipt}", "--behavior", behavior]
            for phase in ("prereg", "replay", "random_control", "stress")
        }
    return card


def _repository(tmp_path, cards, *, runtime=10, min_free=1):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "research_conveyor_phase_adapter.py").write_text(_ADAPTER, encoding="utf-8")
    (tmp_path / "contract.txt").write_text("stable\n", encoding="utf-8")
    (tmp_path / "data.csv").write_text("data\n", encoding="utf-8")
    manifest = {
        "schema_id": "research_conveyor_manifest_v1",
        "authority": AUTH,
        "enabled": True,
        "max_jobs_per_run": 10,
        "max_runtime_seconds": runtime,
        "min_free_bytes": min_free,
        "allowed_script_roots": ["scripts"],
        "hypotheses": cards,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _run(tmp_path, config, mode="run"):
    return run_conveyor(tmp_path, config, tmp_path / "run", mode)


def _verify_self_hash(value):
    unsigned = {key: item for key, item in value.items() if key != "receipt_sha256"}
    assert value["receipt_sha256"] == _sha(unsigned)


def test_runs_valid_phases_in_deterministic_order_and_aggregates(tmp_path: Path):
    config = _repository(tmp_path, [_card("second", 2), _card("first", 1)])

    result = _run(tmp_path, config)

    assert [item["hypothesis_id"] for item in result["terminals"]] == ["first", "second"]
    assert [item["state"] for item in result["terminals"]] == ["PASS_DIAGNOSTIC", "PASS_DIAGNOSTIC"]
    assert result["counts"] == {"PASS_DIAGNOSTIC": 2}
    assert (tmp_path / "run" / "phase-launches.txt").read_text().splitlines() == [
        "first:prereg", "first:replay", "first:random_control", "first:stress",
        "second:prereg", "second:replay", "second:random_control", "second:stress",
    ]
    _verify_self_hash(json.loads((tmp_path / "run" / "terminal_receipt.json").read_text()))


def test_blocked_cards_and_nonlaunch_modes_never_start_an_adapter(tmp_path: Path):
    config = _repository(tmp_path, [_card("ready", 1), _card("blocked", 2, "BLOCKED_ADAPTER")])

    dry = _run(tmp_path, config, "dry-run")
    assert dry["counts"] == {"DRY_RUN": 1, "BLOCKED_ADAPTER": 1}
    assert not (tmp_path / "run" / "phase-launches.txt").exists()

    preflight_dir = tmp_path / "preflight"
    preflight = run_conveyor(tmp_path, config, preflight_dir, "preflight")
    assert preflight["counts"] == {"PREFLIGHT": 1, "BLOCKED_ADAPTER": 1}
    assert not (preflight_dir / "phase-launches.txt").exists()


@pytest.mark.parametrize("behavior", ["missing", "tampered", "nonzero", "timeout", "bad_metrics", "bad_boolean"])
def test_transport_and_receipt_failures_are_technical(tmp_path: Path, behavior: str):
    config = _repository(tmp_path, [_card("h1", 1, behavior=behavior)], runtime=1 if behavior == "timeout" else 10)

    result = _run(tmp_path, config)

    assert result["terminals"] == [{"hypothesis_id": "h1", "state": "FAILED_TECHNICAL", "phase": "prereg"}]


def test_valid_negative_research_receipt_stops_that_hypothesis(tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1, behavior="reject")])

    result = _run(tmp_path, config)

    assert result["terminals"] == [{"hypothesis_id": "h1", "state": "REJECT", "phase": "prereg"}]
    assert (tmp_path / "run" / "phase-launches.txt").read_text().splitlines() == ["h1:prereg"]


def test_changed_contract_is_revalidated_before_the_next_phase(tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1, behavior="mutate_contract")])

    result = _run(tmp_path, config)

    assert result["terminals"] == [{"hypothesis_id": "h1", "state": "FAILED_TECHNICAL", "phase": "prereg"}]
    assert (tmp_path / "run" / "phase-launches.txt").read_text().splitlines() == ["h1:prereg"]


def test_resource_guard_prevents_launch(monkeypatch, tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1)], min_free=10)
    monkeypatch.setattr("scripts.run_research_conveyor.shutil.disk_usage", lambda _: type("Usage", (), {"free": 0})())

    result = _run(tmp_path, config)

    assert result["terminals"] == [{"hypothesis_id": "h1", "state": "RESOURCE_GUARD", "phase": None}]
    assert not (tmp_path / "run" / "phase-launches.txt").exists()


def test_secret_named_environment_variables_are_not_passed_to_adapter(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("RESEARCH_CONVEYOR_TEST_TOKEN", "must-not-cross-boundary")
    config = _repository(tmp_path, [_card("h1", 1)])

    result = _run(tmp_path, config)

    assert result["counts"] == {"PASS_DIAGNOSTIC": 1}
    assert not (tmp_path / "run" / "secret_seen").exists()


def test_existing_run_directory_is_rejected(tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1)])
    (tmp_path / "run").mkdir()

    with pytest.raises(ValueError, match="new"):
        _run(tmp_path, config)


def test_phase_output_flood_is_bounded_and_marked(tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1, behavior="flood")])

    result = _run(tmp_path, config)

    assert result["counts"] == {"PASS_DIAGNOSTIC": 1}
    log = tmp_path / "run" / "hypotheses" / "h1" / "phases" / "prereg.stdout.log"
    assert log.stat().st_size <= 64 * 1024
    assert "truncated" in log.read_text(encoding="utf-8")


def test_timeout_kills_the_entire_adapter_process_group(tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1, behavior="timeout_child")], runtime=1)

    result = _run(tmp_path, config)
    time.sleep(1.2)

    assert result["counts"] == {"FAILED_TECHNICAL": 1}
    assert not (tmp_path / "run" / "orphaned-child.txt").exists()


def test_timeout_does_not_wait_for_term_ignoring_descendant_pipe(tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1, behavior="timeout_term_ignoring_child")], runtime=1)

    started = time.monotonic()
    result = _run(tmp_path, config)
    elapsed = time.monotonic() - started

    assert result["counts"] == {"FAILED_TECHNICAL": 1}
    assert elapsed < 1.6
    time.sleep(1.1)
    assert not (tmp_path / "run" / "term-ignoring-child.txt").exists()


@pytest.mark.parametrize("identifier", ["", "../escape", "/absolute", "nested/path", "x" * 129])
def test_hypothesis_id_must_be_a_safe_single_path_component(tmp_path: Path, identifier: str):
    config = _repository(tmp_path, [_card(identifier, 1)])

    with pytest.raises(ContractError):
        load_manifest(tmp_path, config)


def test_runnable_adapter_must_be_bound_by_a_contract_reference(tmp_path: Path):
    card = _card("h1", 1)
    card["contract_refs"].remove("scripts/research_conveyor_phase_adapter.py")
    config = _repository(tmp_path, [card])

    with pytest.raises(ContractError, match="adapter script"):
        load_manifest(tmp_path, config)


@pytest.mark.parametrize("behavior", ["artifact_missing", "artifact_escape", "artifact_absolute", "artifact_glob", "artifact_input_symlink", "artifact_symlink", "artifact_output_escape", "artifact_stale", "artifact_fake_hash"])
def test_artifacts_must_be_real_contained_nonsymlink_files_with_current_hashes(tmp_path: Path, behavior: str):
    config = _repository(tmp_path, [_card("h1", 1, behavior=behavior)])

    result = _run(tmp_path, config)

    assert result["terminals"] == [{"hypothesis_id": "h1", "state": "FAILED_TECHNICAL", "phase": "prereg"}]


def test_artifacts_are_verified_when_receipt_is_otherwise_valid(tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1, behavior="artifact")])

    result = _run(tmp_path, config)

    assert result["counts"] == {"PASS_DIAGNOSTIC": 1}


def test_final_phase_input_mutation_is_detected_before_receipt_acceptance(tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1, behavior="mutate_final_contract")])

    result = _run(tmp_path, config)

    assert result["terminals"] == [{"hypothesis_id": "h1", "state": "FAILED_TECHNICAL", "phase": "stress"}]


def test_adapter_script_drift_is_detected_while_the_phase_is_still_untrusted(tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1, behavior="mutate_adapter")])

    result = _run(tmp_path, config)

    assert result["terminals"] == [{"hypothesis_id": "h1", "state": "FAILED_TECHNICAL", "phase": "prereg"}]


def test_preregistration_artifact_is_deterministic_and_bound_to_freeze(tmp_path: Path):
    config = _repository(tmp_path, [_card("h1", 1)])

    _run(tmp_path, config)

    artifact = json.loads((tmp_path / "run" / "hypotheses" / "h1" / "preregistration.json").read_text(encoding="utf-8"))
    _verify_self_hash(artifact)
    assert artifact["hypothesis_id"] == "h1"
    assert artifact["manifest_sha256"] == _sha(json.loads(config.read_text(encoding="utf-8")))
    assert artifact["preregistration_sha256"] == _sha(_card("h1", 1)["preregistration"])
    assert artifact["contract_hashes"]["scripts/research_conveyor_phase_adapter.py"] == hashlib.sha256((tmp_path / "scripts" / "research_conveyor_phase_adapter.py").read_bytes()).hexdigest()
