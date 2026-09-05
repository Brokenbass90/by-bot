#!/usr/bin/env python3
"""Prepare an enabled, hash-bound ATT1+ETS2S VPS shadow release in place."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.att1_ets2s_signal_shadow_contract import (
    ACK,
    DEPLOYMENT_ANCHOR_PATH,
    DEPLOYMENT_ANCHOR_SCHEMA_ID,
    PRIVILEGED_LAUNCHER_INSTALL_PATH,
    PRIVILEGED_LAUNCHER_SOURCE_PATH,
    SOURCE_PATHS,
    TRUSTED_CONFIG_PATH,
    TRUSTED_MANIFEST_PATH,
    load_contract,
    load_contract_from_deployment_anchor,
    require_operator_ack,
)


_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _write_json(path: Path, payload: object, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    os.chmod(path, mode)


def write_deployment_anchor(
    path: Path,
    payload: Mapping[str, object],
    *,
    expected_owner_uid: int = 0,
) -> None:
    """Atomically install and verify a privilege-separated deployment anchor."""

    path = Path(os.path.abspath(os.fspath(path)))
    path.parent.mkdir(parents=True, exist_ok=True)
    parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    temp_name = f".{path.name}.tmp-{os.getpid()}-{os.urandom(8).hex()}"
    file_fd = -1
    try:
        file_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        os.fchmod(file_fd, 0o600)
        data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        view = memoryview(data)
        while view:
            view = view[os.write(file_fd, view):]
        os.fsync(file_fd)
        os.close(file_fd)
        file_fd = -1
        os.replace(temp_name, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)
    info = path.stat(follow_symlinks=False)
    if not info.st_uid == expected_owner_uid:
        raise ValueError("deployment_anchor_owner_mismatch")
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
        raise ValueError("deployment_anchor_mode_or_type_mismatch")


def install_privileged_launcher(
    source: Path,
    destination: Path,
    *,
    expected_owner_uid: int = 0,
) -> str:
    """Atomically install and re-read the root-owned external launcher."""

    source = Path(os.path.abspath(os.fspath(source)))
    destination = Path(os.path.abspath(os.fspath(destination)))
    data = source.read_bytes()
    expected_sha = hashlib.sha256(data).hexdigest()
    destination.parent.mkdir(parents=True, exist_ok=True)
    parent_fd = os.open(
        destination.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    parent_info = os.fstat(parent_fd)
    if (not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != expected_owner_uid
            or parent_info.st_mode & 0o022):
        os.close(parent_fd)
        raise ValueError("privileged_launcher_parent_untrusted")
    temp_name = f".{destination.name}.tmp-{os.getpid()}-{os.urandom(8).hex()}"
    file_fd = -1
    try:
        file_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o755,
            dir_fd=parent_fd,
        )
        os.fchmod(file_fd, 0o755)
        view = memoryview(data)
        while view:
            view = view[os.write(file_fd, view):]
        os.fsync(file_fd)
        os.close(file_fd)
        file_fd = -1
        os.replace(temp_name, destination.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
        installed_fd = os.open(
            destination.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        try:
            info = os.fstat(installed_fd)
            installed = b""
            while True:
                chunk = os.read(installed_fd, 1024 * 1024)
                if not chunk:
                    break
                installed += chunk
        finally:
            os.close(installed_fd)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != expected_owner_uid
                or stat.S_IMODE(info.st_mode) != 0o755
                or info.st_nlink != 1
                or hashlib.sha256(installed).hexdigest() != expected_sha):
            raise ValueError("privileged_launcher_install_verification_failed")
        return expected_sha
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def prepare_in_place(root: Path, *, git_commit_sha: str) -> dict[str, object]:
    root = Path(os.path.abspath(os.fspath(root)))
    if _GIT_SHA.fullmatch(git_commit_sha) is None:
        raise ValueError("git_commit_sha must be a full lowercase SHA")
    config_path = root / TRUSTED_CONFIG_PATH
    manifest_path = root / TRUSTED_MANIFEST_PATH
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("default_off") is not True or config.get("enabled") is not False:
        raise ValueError("release source config must be repository default-off")
    config["enabled"] = True
    _write_json(config_path, config, mode=0o640)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_rows = []
    for relative in sorted(SOURCE_PATHS):
        data = (root / relative).read_bytes()
        source_rows.append(
            {"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )
    manifest["source_files"] = source_rows
    manifest["source_closure_sha256"] = hashlib.sha256(
        _canonical({"files": source_rows, "schema_id": "att1_ets2s_source_closure_v1"})
    ).hexdigest()
    _write_json(manifest_path, manifest, mode=0o640)

    config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    contract = load_contract(
        root,
        config_path,
        expected_config_sha256=config_sha,
        expected_manifest_sha256=manifest_sha,
    )
    require_operator_ack(contract, ACK)
    return {
        "schema_id": DEPLOYMENT_ANCHOR_SCHEMA_ID,
        "git_commit_sha": git_commit_sha,
        "config_path": TRUSTED_CONFIG_PATH,
        "config_sha256": config_sha,
        "manifest_path": TRUSTED_MANIFEST_PATH,
        "manifest_sha256": manifest_sha,
        "source_closure_sha256": contract.source_closure_sha256,
        "privileged_launcher_sha256": hashlib.sha256(
            (root / PRIVILEGED_LAUNCHER_SOURCE_PATH).read_bytes()
        ).hexdigest(),
        "acknowledgement": ACK,
        "enabled": True,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
    }


def main(argv: list[str] | None = None, *, expected_owner_uid: int = 0) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--git-commit-sha", required=True)
    args = parser.parse_args(argv)
    if os.geteuid() != expected_owner_uid:
        raise SystemExit("release preparation must run as root")
    receipt = prepare_in_place(args.root, git_commit_sha=args.git_commit_sha)
    installed_sha = install_privileged_launcher(
        args.root / PRIVILEGED_LAUNCHER_SOURCE_PATH,
        Path(PRIVILEGED_LAUNCHER_INSTALL_PATH),
        expected_owner_uid=expected_owner_uid,
    )
    if installed_sha != receipt["privileged_launcher_sha256"]:
        raise SystemExit("installed privileged launcher hash mismatch")
    write_deployment_anchor(
        Path(DEPLOYMENT_ANCHOR_PATH),
        receipt,
        expected_owner_uid=expected_owner_uid,
    )
    load_contract_from_deployment_anchor(
        args.root,
        args.root / TRUSTED_CONFIG_PATH,
        DEPLOYMENT_ANCHOR_PATH,
        expected_owner_uid=expected_owner_uid,
    )
    print(_canonical(receipt).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
