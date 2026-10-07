import ast
import json
from pathlib import Path
import subprocess
import sys
import uuid
import pytest

from os2_bridge_fixture import bundle

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/run_os2_shadow_bridge.py"


@pytest.fixture
def area():
    import shutil
    root = REPO / ".private/os2_shadow_bridge_v1" / ("test-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root)


def run(path, runtime):
    return subprocess.run([sys.executable, str(SCRIPT), "--input", str(path), "--runtime-dir", str(runtime)],
                          capture_output=True, text=True, timeout=35)


def test_cli_fixture_and_external_terminal_statuses(area):
    path = area / "source.json"; path.write_text(json.dumps(bundle()))
    r = run(path, area / "store")
    assert r.returncode == 0, r.stderr
    value = json.loads(r.stdout)
    assert value["status"] == "SHADOW_WIRING_PASS"
    assert run(path, area / "store").stdout == r.stdout
    b = bundle(); b["mode"] = "EXTERNAL_PUBLIC"; path.write_text(json.dumps(b))
    r = run(path, area / "external-store")
    assert r.returncode == 2
    assert json.loads(r.stdout)["reason"] == "POLICY_UNAPPROVED"


def test_refuses_arbitrary_source_or_runtime_path(area, tmp_path):
    outside = tmp_path / "credential-looking.json"; outside.write_text("must not read")
    r = run(outside, area / "store")
    assert r.returncode == 2 and "input_path_refused" in r.stdout
    path = area / "source.json"; path.write_text(json.dumps(bundle()))
    r = run(path, tmp_path / "live-runtime")
    assert r.returncode == 3 and "runtime_path_refused" in r.stdout
    assert not (tmp_path / "live-runtime").exists()


@pytest.mark.parametrize("raw", ['{"request_id":"one","request_id":"two"}', '{"x":NaN}', "x" * (2 * 1024 * 1024 + 1), '{"request_id":"one","x":1e309}'], ids=["duplicate-key", "nan", "oversize", "overflow"])
def test_invalid_json_or_size_fails_before_journal(area, raw):
    path = area / "source.json"; path.write_text(raw)
    r = run(path, area / "store")
    assert r.returncode == 2
    assert not (area / "store").exists()


def test_symlink_input_is_refused(area, tmp_path):
    target = tmp_path / "outside.json"; target.write_text(json.dumps(bundle()))
    path = area / "source.json"; path.symlink_to(target)
    r = run(path, area / "store")
    assert r.returncode == 2
    assert not (area / "store").exists()


def test_no_transport_credential_or_live_mutation_imports():
    paths = [SCRIPT, REPO / "research_lab/os2_shadow_bridge.py", REPO / "research_lab/os2_shadow_journal.py"]
    forbidden = {"requests", "httpx", "aiohttp", "urllib", "ccxt", "pybit", "alpaca", "dotenv", "subprocess", "socket"}
    for path in paths:
        source = path.read_text(); tree = ast.parse(source)
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        names = {name.name.split(".")[0] for n in imports if isinstance(n, ast.Import) for name in n.names}
        names |= {n.module.split(".")[0] for n in imports if isinstance(n, ast.ImportFrom)}
        assert not (names & forbidden)
        assert "os.environ" not in source
        assert "os.getenv" not in source
