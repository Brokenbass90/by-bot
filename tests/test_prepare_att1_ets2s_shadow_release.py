from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from bot.att1_ets2s_signal_shadow_contract import (
    DEPLOYMENT_ANCHOR_PATH,
    PRIVILEGED_LAUNCHER_INSTALL_PATH,
    SOURCE_PATHS,
    TRUSTED_CONFIG_PATH,
    TRUSTED_MANIFEST_PATH,
    load_contract_from_deployment_anchor,
)
from scripts import prepare_att1_ets2s_shadow_release as release_tool


ROOT = Path(__file__).resolve().parents[1]


def test_prepare_release_enables_only_copy_and_emits_external_anchors(tmp_path: Path) -> None:
    release = tmp_path / "release"
    for relative in sorted(set(SOURCE_PATHS) | {TRUSTED_MANIFEST_PATH}):
        destination = release / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)

    receipt = release_tool.prepare_in_place(release, git_commit_sha="1" * 40)
    config = release / TRUSTED_CONFIG_PATH
    manifest = release / TRUSTED_MANIFEST_PATH

    assert json.loads(config.read_text(encoding="utf-8"))["enabled"] is True
    assert receipt["config_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
    assert receipt["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert receipt["privileged_launcher_sha256"] == hashlib.sha256(
        (release / "scripts/launch_att1_ets2s_shadow.py").read_bytes()
    ).hexdigest()
    anchor_path = tmp_path / "root-owned-anchor.json"
    release_tool.write_deployment_anchor(
        anchor_path,
        receipt,
        expected_owner_uid=os.geteuid(),
    )
    info = anchor_path.stat()
    assert info.st_uid == os.geteuid()
    assert info.st_mode & 0o777 == 0o600
    contract, loaded_anchor = load_contract_from_deployment_anchor(
        release,
        config,
        anchor_path,
        expected_owner_uid=os.geteuid(),
    )
    assert contract.enabled is True
    assert loaded_anchor == receipt
    assert receipt["money_authority"] is False


def test_anchor_tamper_or_wrong_ownership_fails_before_contract_load(tmp_path: Path) -> None:
    release = tmp_path / "release"
    for relative in sorted(set(SOURCE_PATHS) | {TRUSTED_MANIFEST_PATH}):
        destination = release / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    receipt = release_tool.prepare_in_place(release, git_commit_sha="2" * 40)
    anchor_path = tmp_path / "anchor.json"
    release_tool.write_deployment_anchor(
        anchor_path,
        receipt,
        expected_owner_uid=os.geteuid(),
    )

    with pytest.raises(ValueError, match="deployment_anchor_owner"):
        load_contract_from_deployment_anchor(
            release,
            release / TRUSTED_CONFIG_PATH,
            anchor_path,
            expected_owner_uid=os.geteuid() + 1,
        )

    raw = json.loads(anchor_path.read_text(encoding="utf-8"))
    raw["config_sha256"] = "0" * 64
    anchor_path.write_text(json.dumps(raw), encoding="utf-8")
    os.chmod(anchor_path, 0o600)
    with pytest.raises(ValueError, match="config_hash_mismatch"):
        load_contract_from_deployment_anchor(
            release,
            release / TRUSTED_CONFIG_PATH,
            anchor_path,
            expected_owner_uid=os.geteuid(),
        )


def test_release_cli_is_fail_closed_for_non_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(release_tool.os, "geteuid", lambda: 501)
    with pytest.raises(SystemExit, match="must run as root"):
        release_tool.main(["--root", str(tmp_path), "--git-commit-sha", "3" * 40])


def test_production_anchor_path_is_fixed_under_etc() -> None:
    assert DEPLOYMENT_ANCHOR_PATH == "/etc/bybot-research/att1-ets2s-signal-shadow.anchor.json"
    assert PRIVILEGED_LAUNCHER_INSTALL_PATH == "/usr/local/libexec/att1-ets2s-shadow-launcher"


def test_release_cli_atomically_installs_external_launcher_and_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    release = tmp_path / "release"
    for relative in sorted(set(SOURCE_PATHS) | {TRUSTED_MANIFEST_PATH}):
        destination = release / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    libexec = tmp_path / "libexec"
    libexec.mkdir(mode=0o700)
    installed_launcher = libexec / "att1-ets2s-shadow-launcher"
    anchor_path = tmp_path / "att1-ets2s-shadow.anchor.json"
    monkeypatch.setattr(release_tool, "PRIVILEGED_LAUNCHER_INSTALL_PATH", str(installed_launcher))
    monkeypatch.setattr(release_tool, "DEPLOYMENT_ANCHOR_PATH", str(anchor_path))

    code = release_tool.main(
        ["--root", str(release), "--git-commit-sha", "6" * 40],
        expected_owner_uid=os.geteuid(),
    )
    assert code == 0
    receipt = json.loads(capsys.readouterr().out)
    assert installed_launcher.read_bytes() == (release / "scripts/launch_att1_ets2s_shadow.py").read_bytes()
    assert installed_launcher.stat().st_mode & 0o777 == 0o755
    assert hashlib.sha256(installed_launcher.read_bytes()).hexdigest() == receipt["privileged_launcher_sha256"]
    assert anchor_path.stat().st_mode & 0o777 == 0o600
