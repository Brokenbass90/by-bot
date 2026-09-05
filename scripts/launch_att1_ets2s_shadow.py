#!/usr/bin/env python3
"""Root-owned stdlib-only launcher for the ATT1+ETS2S public shadow.

Installed outside the application tree, this verifies its own externally
anchored hash and the complete app closure before executing any app code.
It then drops groups/GID/UID and passes the same root-opened anchor FD to the
unprivileged public runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import stat
import sys
from pathlib import Path
from typing import Mapping


APP_ROOT = Path("/opt/bybot-research/att1-ets2s-signal-shadow/app")
APP_TRUST_BOUNDARY = Path("/opt")
DEPLOYMENT_ANCHOR_PATH = "/etc/bybot-research/att1-ets2s-signal-shadow.anchor.json"
ANCHOR_TRUST_BOUNDARY = Path("/etc/bybot-research")
PRIVILEGED_LAUNCHER_PATH = Path("/usr/local/libexec/att1-ets2s-shadow-launcher")
LAUNCHER_TRUST_BOUNDARY = Path("/usr/local/libexec")
TRUSTED_CONFIG_PATH = "configs/att1_ets2s_signal_shadow_v1.json"
TRUSTED_MANIFEST_PATH = "configs/research/att1_ets2s_signal_shadow_manifest_v1.json"
ANCHOR_SCHEMA = "att1_ets2s_signal_shadow_deployment_anchor_v1"
ACK = "ATT1_ETS2S_SIGNAL_SHADOW"
SERVICE_USER = "bybot-research"
_SHA_FIELDS = {
    "config_sha256",
    "manifest_sha256",
    "source_closure_sha256",
    "privileged_launcher_sha256",
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _check_trusted_stat(info: os.stat_result, *, owner_uid: int, directory: bool) -> None:
    expected_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not expected_type or info.st_uid != owner_uid or info.st_mode & 0o022:
        raise SystemExit("untrusted privileged path ownership or mode")


def _open_directory_chain(boundary: Path, target: Path, *, owner_uid: int) -> int:
    boundary = Path(os.path.abspath(os.fspath(boundary)))
    target = Path(os.path.abspath(os.fspath(target)))
    try:
        relative = target.relative_to(boundary)
    except ValueError as exc:
        raise SystemExit("privileged path escapes trust boundary") from exc
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        current = os.open(boundary, flags)
        _check_trusted_stat(os.fstat(current), owner_uid=owner_uid, directory=True)
        for part in relative.parts:
            next_fd = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = next_fd
            _check_trusted_stat(os.fstat(current), owner_uid=owner_uid, directory=True)
        return current
    except OSError as exc:
        try:
            os.close(current)
        except (OSError, UnboundLocalError):
            pass
        raise SystemExit("cannot open trusted privileged directory") from exc


def _open_relative_file(root_fd: int, relative: str, *, owner_uid: int) -> int:
    path = Path(str(relative))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise SystemExit("unsafe manifest source path")
    current = os.dup(root_fd)
    try:
        for part in path.parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            os.close(current)
            current = next_fd
            _check_trusted_stat(os.fstat(current), owner_uid=owner_uid, directory=True)
        result = os.open(path.parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=current)
        _check_trusted_stat(os.fstat(result), owner_uid=owner_uid, directory=False)
        return result
    except SystemExit:
        raise
    except OSError as exc:
        raise SystemExit("cannot open trusted source file") from exc
    finally:
        os.close(current)


def _read_fd(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _read_relative(root_fd: int, relative: str, *, owner_uid: int) -> bytes:
    fd = _open_relative_file(root_fd, relative, owner_uid=owner_uid)
    try:
        return _read_fd(fd)
    finally:
        os.close(fd)


def _parse_anchor(data: bytes) -> dict[str, object]:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("deployment anchor unreadable") from exc
    fields = {
        "schema_id",
        "git_commit_sha",
        "config_path",
        "config_sha256",
        "manifest_path",
        "manifest_sha256",
        "source_closure_sha256",
        "privileged_launcher_sha256",
        "acknowledgement",
        "enabled",
        "money_authority",
        "orders_allowed",
        "private_api_allowed",
    }
    if not isinstance(raw, Mapping) or set(raw) != fields:
        raise SystemExit("deployment anchor fields mismatch")
    if raw.get("schema_id") != ANCHOR_SCHEMA:
        raise SystemExit("deployment anchor schema mismatch")
    if raw.get("config_path") != TRUSTED_CONFIG_PATH or raw.get("manifest_path") != TRUSTED_MANIFEST_PATH:
        raise SystemExit("deployment anchor paths mismatch")
    if raw.get("acknowledgement") != ACK or raw.get("enabled") is not True:
        raise SystemExit("deployment anchor authorization mismatch")
    if any(raw.get(field) is not False for field in ("money_authority", "orders_allowed", "private_api_allowed")):
        raise SystemExit("unsafe deployment anchor authority")
    git_sha = str(raw.get("git_commit_sha") or "")
    if len(git_sha) != 40 or any(char not in "0123456789abcdef" for char in git_sha):
        raise SystemExit("deployment anchor git SHA invalid")
    for field in _SHA_FIELDS:
        value = str(raw.get(field) or "")
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise SystemExit(f"deployment anchor {field} invalid")
    return dict(raw)


def verify_privileged_inputs(*, expected_owner_uid: int = 0) -> tuple[int, dict[str, object]]:
    anchor_dir_fd = _open_directory_chain(
        ANCHOR_TRUST_BOUNDARY,
        Path(DEPLOYMENT_ANCHOR_PATH).parent,
        owner_uid=expected_owner_uid,
    )
    try:
        anchor_fd = _open_relative_file(
            anchor_dir_fd,
            Path(DEPLOYMENT_ANCHOR_PATH).name,
            owner_uid=expected_owner_uid,
        )
    finally:
        os.close(anchor_dir_fd)
    info = os.fstat(anchor_fd)
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
        os.close(anchor_fd)
        raise SystemExit("deployment anchor must be a root-owned 0600 single-link file")
    anchor = _parse_anchor(_read_fd(anchor_fd))

    launcher_dir_fd = _open_directory_chain(
        LAUNCHER_TRUST_BOUNDARY,
        PRIVILEGED_LAUNCHER_PATH.parent,
        owner_uid=expected_owner_uid,
    )
    try:
        launcher_bytes = _read_relative(
            launcher_dir_fd,
            PRIVILEGED_LAUNCHER_PATH.name,
            owner_uid=expected_owner_uid,
        )
    finally:
        os.close(launcher_dir_fd)
    if hashlib.sha256(launcher_bytes).hexdigest() != anchor["privileged_launcher_sha256"]:
        os.close(anchor_fd)
        raise SystemExit("privileged launcher hash mismatch")

    app_fd = _open_directory_chain(APP_TRUST_BOUNDARY, APP_ROOT, owner_uid=expected_owner_uid)
    try:
        config_bytes = _read_relative(app_fd, TRUSTED_CONFIG_PATH, owner_uid=expected_owner_uid)
        if hashlib.sha256(config_bytes).hexdigest() != anchor["config_sha256"]:
            raise SystemExit("config hash mismatch")
        manifest_bytes = _read_relative(app_fd, TRUSTED_MANIFEST_PATH, owner_uid=expected_owner_uid)
        if hashlib.sha256(manifest_bytes).hexdigest() != anchor["manifest_sha256"]:
            raise SystemExit("manifest hash mismatch")
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SystemExit("manifest unreadable") from exc
        rows = manifest.get("source_files") if isinstance(manifest, Mapping) else None
        if not isinstance(rows, list) or not rows:
            raise SystemExit("manifest source rows missing")
        normalized: list[dict[str, object]] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
                raise SystemExit("manifest source row invalid")
            relative = str(row["path"])
            if relative in seen:
                raise SystemExit("duplicate manifest source path")
            seen.add(relative)
            data = _read_relative(app_fd, relative, owner_uid=expected_owner_uid)
            actual = {
                "path": relative,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            if dict(row) != actual:
                raise SystemExit("manifest source row hash mismatch")
            normalized.append(actual)
        closure = hashlib.sha256(
            _canonical(
                {
                    "files": sorted(normalized, key=lambda item: str(item["path"])),
                    "schema_id": "att1_ets2s_source_closure_v1",
                }
            )
        ).hexdigest()
        if closure != anchor["source_closure_sha256"] or closure != manifest.get("source_closure_sha256"):
            raise SystemExit("source closure hash mismatch")
    except BaseException:
        os.close(anchor_fd)
        raise
    finally:
        os.close(app_fd)
    return anchor_fd, anchor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        raise SystemExit("shadow launcher must run as root")

    anchor_fd, _anchor = verify_privileged_inputs()
    try:
        account = pwd.getpwnam(SERVICE_USER)
        if account.pw_uid == 0 or account.pw_gid == 0:
            raise SystemExit("shadow service account must be unprivileged")
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
        if os.getuid() != account.pw_uid or os.getgid() != account.pw_gid:
            raise SystemExit("shadow launcher failed to drop privileges")
        os.set_inheritable(anchor_fd, True)
        config_path = APP_ROOT / TRUSTED_CONFIG_PATH
        command = [
            sys.executable,
            str(APP_ROOT / "scripts/run_att1_ets2s_signal_shadow.py"),
            "--root",
            str(APP_ROOT),
            "--config",
            str(config_path),
            "--deployment-anchor-fd",
            str(anchor_fd),
        ]
        if args.once:
            command.append("--once")
        clean_env = {
            "LANG": "C.UTF-8",
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        os.execve(sys.executable, command, clean_env)
    finally:
        os.close(anchor_fd)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
