from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).parents[1]
SETUP = ROOT / "scripts" / "setup_mt5_demo_env.sh"
SHORTCUT = ROOT / "START_MT5_DEMO_KEY_SETUP.command"


def test_setup_writes_demo_only_env_without_echoing_token(tmp_path: Path):
    env_file = tmp_path / ".env"
    token = "private-demo-token-123"
    completed = subprocess.run(
        ["bash", str(SETUP)],
        cwd=ROOT,
        env={**os.environ, "SIGCOPY_SETUP_ENV_FILE": str(env_file)},
        input=f"{token}\n\nBullwaves-Demo\n123456\n",
        text=True,
        capture_output=True,
        check=True,
    )

    payload = env_file.read_text(encoding="utf-8")
    assert f"SIGCOPY_MT5_TOKEN={token}" in payload
    assert "SIGCOPY_EXECUTION_ENABLE=0" in payload
    assert "SIGCOPY_ALLOW_LIVE=0" in payload
    assert "SIGCOPY_ALLOW_REMOTE_LLM=0" in payload
    assert "SIGCOPY_ALLOWED_ACCOUNT_TYPES=demo" in payload
    assert token not in completed.stdout
    assert token not in completed.stderr
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_setup_preserves_unknown_settings_and_backs_up_existing_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CUSTOM_KEEP=1\nSIGCOPY_MT5_TOKEN=old-secret\nSIGCOPY_EXECUTION_ENABLE=1\n",
        encoding="utf-8",
    )

    subprocess.run(
        ["bash", str(SETUP)],
        cwd=ROOT,
        env={**os.environ, "SIGCOPY_SETUP_ENV_FILE": str(env_file)},
        input="new-secret\nhttp://127.0.0.1:22346/mcp\nBullwaves-Demo\n\n",
        text=True,
        capture_output=True,
        check=True,
    )

    payload = env_file.read_text(encoding="utf-8")
    assert "CUSTOM_KEEP=1" in payload
    assert "old-secret" not in payload
    assert payload.count("SIGCOPY_MT5_TOKEN=") == 1
    assert "SIGCOPY_EXECUTION_ENABLE=1" not in payload
    backups = list(tmp_path.glob(".env.bak_*"))
    assert len(backups) == 1
    assert "old-secret" in backups[0].read_text(encoding="utf-8")
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600


def test_shortcut_invokes_only_the_fail_closed_setup_script():
    source = SHORTCUT.read_text(encoding="utf-8")
    assert "scripts/setup_mt5_demo_env.sh" in source
    assert "check_live.py" not in source
    assert "EXECUTION_ENABLE=1" not in source
