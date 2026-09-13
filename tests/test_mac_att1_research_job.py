import json
import os
import subprocess
import sys
import time

import pytest

import scripts.mac_att1_research_job as job_module


def _stage(name, code, *, timeout=10, inputs=()):
    return job_module.Stage(
        name=name,
        argv=(sys.executable, "-c", code),
        timeout_seconds=timeout,
        input_paths=inputs,
    )


def _job(tmp_path):
    return job_module.MacATT1ResearchJob(
        root=tmp_path,
        runtime_dir=tmp_path / "runtime",
    )


def _stage_rows(stages):
    return [(stage.name, stage.argv, stage.timeout_seconds, stage.input_paths) for stage in stages]


def test_completed_immutable_job_is_a_noop_on_later_launchd_wakeup(tmp_path, monkeypatch):
    marker = tmp_path / "marker"
    monkeypatch.setattr(job_module, "STAGES", (
        _stage("binding", "from pathlib import Path; Path(%r).write_text('ok')" % str(marker)),
    ))
    runner = _job(tmp_path)

    first = runner.run()
    log_mtime = (runner.logs_dir / "binding.log").stat().st_mtime_ns
    second = runner.run()

    assert first["state"] == "COMPLETE"
    assert second == {"state": "COMPLETE", "action": "noop"}
    assert marker.read_text() == "ok"
    assert (runner.logs_dir / "binding.log").stat().st_mtime_ns == log_mtime
    result = json.loads(runner.result_path.read_text())
    assert result["source_input_sha256"] == json.loads(runner.state_path.read_text())["source_input_sha256"]


def test_changed_hashed_input_refuses_to_reuse_completed_receipt(tmp_path, monkeypatch):
    source = tmp_path / "frozen-input"
    source.write_text("first")
    monkeypatch.setattr(job_module, "STAGES", (
        _stage("binding", "pass", inputs=("frozen-input",)),
    ))
    runner = _job(tmp_path)

    assert runner.run()["state"] == "COMPLETE"
    source.write_text("changed")

    assert runner.run() == {"state": "SOURCE_INPUT_CHANGED", "action": "refuse"}


def test_crash_after_committed_stage_resumes_only_unfinished_stage(tmp_path, monkeypatch):
    one, two = tmp_path / "one", tmp_path / "two"
    stages = (
        _stage("binding", "from pathlib import Path; Path(%r).write_text('one')" % str(one)),
        _stage("public_parity", "from pathlib import Path; Path(%r).write_text('two')" % str(two)),
    )
    monkeypatch.setattr(job_module, "STAGES", stages)
    program = """
import os
from pathlib import Path
import scripts.mac_att1_research_job as m
root = Path(%r)
m.STAGES = tuple(m.Stage(*row) for row in %r)
r = m.MacATT1ResearchJob(root=root, runtime_dir=root / 'runtime')
original = r._commit_stage_success
def crash(stage, **kwargs):
    original(stage, **kwargs)
    os._exit(73)
r._commit_stage_success = crash
r.run()
""" % (str(tmp_path), _stage_rows(stages))
    crashed = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, timeout=20)

    assert crashed.returncode == 73
    assert one.read_text() == "one" and not two.exists()
    resumed = _job(tmp_path).run()

    assert resumed["state"] == "COMPLETE"
    assert one.read_text() == "one" and two.read_text() == "two"
    assert [row["name"] for row in json.loads(_job(tmp_path).state_path.read_text())["completed_stages"]] == ["binding", "public_parity"]


def test_inherited_lock_survives_parent_crash_until_active_child_exits(tmp_path, monkeypatch):
    monkeypatch.setattr(job_module, "STAGES", (
        _stage("binding", "import time; time.sleep(0.7)", timeout=5),
    ))
    program = """
import os
from pathlib import Path
import scripts.mac_att1_research_job as m
root = Path(%r)
m.STAGES = tuple(m.Stage(*row) for row in %r)
r = m.MacATT1ResearchJob(root=root, runtime_dir=root / 'runtime')
original = r._start_command
def crash(stage, env, lock_fd):
    original(stage, env, lock_fd)
    os._exit(74)
r._start_command = crash
r.run()
""" % (str(tmp_path), _stage_rows(job_module.STAGES))
    crashed = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, timeout=20)

    assert crashed.returncode == 74
    with pytest.raises(job_module.AlreadyRunning):
        _job(tmp_path).run()
    time.sleep(0.9)
    monkeypatch.setattr(job_module, 'RETRY_BACKOFF_SECONDS', (0,))
    assert _job(tmp_path).run()['state'] == 'RETRY_WAIT'
    assert _job(tmp_path).run()['state'] == 'COMPLETE'


def test_failed_stage_persists_backoff_then_retries_within_attempt_limit(tmp_path, monkeypatch):
    counter = tmp_path / "attempts"
    code = """
from pathlib import Path
p = Path(%r)
n = int(p.read_text()) + 1 if p.exists() else 1
p.write_text(str(n))
raise SystemExit(0 if n == 2 else 7)
""" % str(counter)
    monkeypatch.setattr(job_module, "STAGES", (_stage("binding", code),))
    monkeypatch.setattr(job_module, "RETRY_BACKOFF_SECONDS", (0,))
    runner = _job(tmp_path)

    first = runner.run()
    checkpoint = json.loads(runner.state_path.read_text())
    second = runner.run()

    assert first["state"] == "RETRY_WAIT"
    assert checkpoint["stages"]["binding"]["attempts"] == 1
    assert checkpoint["stages"]["binding"]["next_retry_utc"]
    assert second["state"] == "COMPLETE"
    assert counter.read_text() == "2"


def test_runner_strips_secrets_and_cli_rejects_arbitrary_command_input(tmp_path, monkeypatch):
    monkeypatch.setenv("BYBIT_API_KEY", "must-not-reach-child")
    monkeypatch.setattr(job_module, "STAGES", (
        _stage("binding", "import os; raise SystemExit(1 if os.getenv('BYBIT_API_KEY') else 0)"),
    ))

    assert _job(tmp_path).run()["state"] == "COMPLETE"
    with pytest.raises(SystemExit):
        job_module.main(["--command", "anything"])


def test_caffeinate_process_is_released_when_stage_finishes(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(job_module, "STAGES", (_stage("binding", "pass"),))
    monkeypatch.setattr(
        job_module,
        "caffeinate_argv",
        lambda _pid, _seconds: [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    original = subprocess.Popen

    def observe(argv, *args, **kwargs):
        proc = original(argv, *args, **kwargs)
        if list(argv[:2]) == [sys.executable, "-c"] and "sleep(30)" in argv[2]:
            started.append(proc)
        return proc

    monkeypatch.setattr(job_module.subprocess, "Popen", observe)

    assert _job(tmp_path).run()["state"] == "COMPLETE"
    assert len(started) == 1
    assert started[0].poll() is not None


def test_crashes_consume_persisted_attempt_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(job_module, 'STAGES', (_stage('binding', 'pass'),))
    runner = _job(tmp_path)
    runner.runtime_dir.mkdir()
    identity = job_module._source_identity(tmp_path, job_module.STAGES)
    state = runner._new_state(identity)
    state.update(status='RUNNING', current_stage='binding')
    state['stages']['binding'] = {'state': 'RUNNING', 'attempts': job_module.MAX_ATTEMPTS}
    job_module._atomic_json(runner.state_path, state)
    assert runner.run()['state'] == 'FAILED'


def test_stage_heartbeat_updates_while_child_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(job_module, 'STAGES', (_stage('binding', 'import time; time.sleep(0.15)'),))
    monkeypatch.setattr(job_module, 'HEARTBEAT_SECONDS', 0.03, raising=False)
    runner = _job(tmp_path)
    seen = []
    original = runner._publish
    def publish(state):
        seen.append(state['status'])
        original(state)
    monkeypatch.setattr(runner, '_publish', publish)
    assert runner.run()['state'] == 'COMPLETE'
    assert seen.count('RUNNING') >= 3


def test_spawn_failure_is_durable_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(job_module, 'STAGES', (_stage('binding', 'pass'),))
    runner = _job(tmp_path)
    monkeypatch.setattr(runner, '_start_command', lambda *_: (_ for _ in ()).throw(OSError('fixture spawn error')))
    assert runner.run()['state'] == 'RETRY_WAIT'
    assert json.loads(runner.state_path.read_text())['stages']['binding']['attempts'] == 1


def test_os_sandbox_denies_network_and_local_credentials(tmp_path, monkeypatch):
    (tmp_path / '.env').write_text('FIXTURE_ONLY=not-a-real-key')
    code = '''
from pathlib import Path
import socket
denied = 0
try:
    Path('.env').read_text()
except PermissionError:
    denied += 1
try:
    socket.create_connection(('127.0.0.1', 1), timeout=1)
except PermissionError:
    denied += 1
raise SystemExit(0 if denied == 2 else 5)
'''
    monkeypatch.setattr(job_module, 'STAGES', (_stage('binding', code),))
    assert _job(tmp_path).run()['state'] == 'COMPLETE'
