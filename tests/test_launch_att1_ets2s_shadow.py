from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.att1_ets2s_signal_shadow_contract import SOURCE_PATHS, TRUSTED_MANIFEST_PATH
from scripts import launch_att1_ets2s_shadow as launcher
from scripts.prepare_att1_ets2s_shadow_release import prepare_in_place, write_deployment_anchor


ROOT = Path(__file__).resolve().parents[1]


def test_launcher_requires_root_before_opening_anchor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher.os, "geteuid", lambda: 501)
    monkeypatch.setattr(
        launcher.os,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("anchor opened")),
    )
    with pytest.raises(SystemExit, match="must run as root"):
        launcher.main([])


def test_launcher_validates_same_fd_then_drops_privileges_before_exec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor = tmp_path / "anchor.json"
    anchor.write_text("{}", encoding="utf-8")
    events: list[object] = []
    monkeypatch.setattr(launcher.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        launcher.pwd,
        "getpwnam",
        lambda _name: SimpleNamespace(pw_uid=12345, pw_gid=12346),
    )
    monkeypatch.setattr(
        launcher,
        "verify_privileged_inputs",
        lambda: (os.open(anchor, os.O_RDONLY), events.append(("validate",)) or {}),
    )
    monkeypatch.setattr(launcher.os, "setgroups", lambda groups: events.append(("groups", groups)))
    monkeypatch.setattr(launcher.os, "setgid", lambda gid: events.append(("gid", gid)))
    monkeypatch.setattr(launcher.os, "setuid", lambda uid: events.append(("uid", uid)))
    monkeypatch.setattr(launcher.os, "getgid", lambda: 12346)
    monkeypatch.setattr(launcher.os, "getuid", lambda: 12345)
    monkeypatch.setattr(launcher.os, "set_inheritable", lambda fd, value: events.append(("inherit", fd, value)))

    def fake_execve(executable: str, argv: list[str], env: dict[str, str]) -> None:
        events.append(("exec", executable, argv, env))
        raise RuntimeError("exec captured")

    monkeypatch.setattr(launcher.os, "execve", fake_execve)
    with pytest.raises(RuntimeError, match="exec captured"):
        launcher.main(["--once"])

    names = [event[0] for event in events]
    assert names[:5] == ["validate", "groups", "gid", "uid", "inherit"]
    assert names[-1] == "exec"
    argv = events[-1][2]
    assert "--deployment-anchor-fd" in argv
    assert "--once" in argv
    assert "--deployment-anchor" not in argv


def test_privileged_verifier_binds_external_launcher_and_entire_app_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / "release"
    for relative in sorted(set(SOURCE_PATHS) | {TRUSTED_MANIFEST_PATH}):
        destination = release / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    receipt = prepare_in_place(release, git_commit_sha="4" * 40)
    anchor_path = tmp_path / "anchor.json"
    write_deployment_anchor(anchor_path, receipt, expected_owner_uid=os.geteuid())

    monkeypatch.setattr(launcher, "APP_ROOT", release)
    monkeypatch.setattr(launcher, "APP_TRUST_BOUNDARY", release)
    monkeypatch.setattr(launcher, "DEPLOYMENT_ANCHOR_PATH", str(anchor_path))
    monkeypatch.setattr(launcher, "ANCHOR_TRUST_BOUNDARY", tmp_path)
    monkeypatch.setattr(launcher, "PRIVILEGED_LAUNCHER_PATH", ROOT / "scripts/launch_att1_ets2s_shadow.py")
    monkeypatch.setattr(launcher, "LAUNCHER_TRUST_BOUNDARY", ROOT)
    fd, loaded = launcher.verify_privileged_inputs(expected_owner_uid=os.geteuid())
    try:
        assert loaded == receipt
        assert loaded["privileged_launcher_sha256"] == hashlib.sha256(
            (ROOT / "scripts/launch_att1_ets2s_shadow.py").read_bytes()
        ).hexdigest()
    finally:
        os.close(fd)

    manifest = release / TRUSTED_MANIFEST_PATH
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["source_files"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SystemExit, match="manifest hash mismatch"):
        launcher.verify_privileged_inputs(expected_owner_uid=os.geteuid())


def test_launcher_source_has_no_network_broker_or_order_imports() -> None:
    tree = ast.parse((ROOT / "scripts/launch_att1_ets2s_shadow.py").read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        str(node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported.isdisjoint({"bot", "scripts", "urllib", "requests", "ccxt", "pybit", "alpaca", "broker", "orders"})
