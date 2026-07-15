from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_web_live_mirror.sh"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _fake_transport(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "ssh",
        "#!/bin/bash\n"
        "# Every requested fixture exists; command execution itself is a no-op.\n"
        "exit 0\n",
    )
    _write_executable(
        fake_bin / "scp",
        "#!/bin/bash\n"
        "argc=$#\n"
        "eval 'src=${'\"$((argc-1))\"'}'\n"
        "eval 'dst=${'\"$argc\"'}'\n"
        "# Upload back to the fake server.\n"
        "if [[ \"$dst\" == *:* ]]; then exit 0; fi\n"
        "mkdir -p \"$(dirname \"$dst\")\"\n"
        "case \"$src\" in\n"
        "  *.json) printf '{}\\n' > \"$dst\" ;;\n"
        "  *.jsonl) : > \"$dst\" ;;\n"
        "  *.csv) printf 'field\\n' > \"$dst\" ;;\n"
        "  *.env) printf 'KEY=value\\n' > \"$dst\" ;;\n"
        "  *) printf 'fixture\\n' > \"$dst\" ;;\n"
        "esac\n",
    )
    return fake_bin


def test_sync_completes_when_failure_arrays_are_empty(tmp_path: Path) -> None:
    mirror = tmp_path / "mirror"
    fake_bin = _fake_transport(tmp_path)
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "MIRROR_ROOT": str(mirror),
            "CHAT_LOCAL_PATH": str(mirror / "deepseek_chat.json"),
            "SSH_KEY": str(tmp_path / "missing-key"),
        }
    )

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((mirror / "sync_bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["failures"] == []
    assert all(row["present"] for row in manifest["critical_files"].values())
    assert not (mirror / ".sync_lock").exists()


def test_overlapping_sync_is_skipped_without_touching_bundle(tmp_path: Path) -> None:
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / ".sync_lock").mkdir()
    manifest = mirror / "sync_bundle_manifest.json"
    manifest.write_text('{"status":"complete","marker":"unchanged"}\n', encoding="utf-8")
    env = dict(os.environ)
    env.update({"MIRROR_ROOT": str(mirror), "SSH_KEY": str(tmp_path / "missing-key")})

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    assert "another sync is active" in result.stdout
    assert json.loads(manifest.read_text(encoding="utf-8"))["marker"] == "unchanged"
