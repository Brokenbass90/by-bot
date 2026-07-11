#!/usr/bin/env python3
"""Atomically rotate the server-only Web JWT secret without printing it."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def rotate_secret(env_file: Path, backup_dir: Path, *, nbytes: int = 32) -> dict[str, str | int | bool]:
    if nbytes < 32:
        raise ValueError("JWT secret must contain at least 32 random bytes")
    env_file = env_file.expanduser()
    if env_file.is_symlink():
        raise ValueError("refusing to rotate through a symlink")
    env_file = env_file.resolve()
    backup_dir = backup_dir.expanduser().resolve()

    original = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    rows = original.splitlines()
    secret = secrets.token_hex(nbytes)
    replacement = f"WEB_JWT_SECRET={secret}"
    out: list[str] = []
    replaced = False
    for row in rows:
        if row.startswith("WEB_JWT_SECRET="):
            if not replaced:
                out.append(replacement)
                replaced = True
            continue
        out.append(row)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(replacement)
    payload = "\n".join(out) + "\n"

    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(backup_dir, 0o700)
    backup = ""
    if env_file.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"{env_file.name}.{stamp}.web_jwt_rotate.bak"
        shutil.copy2(env_file, backup_path)
        os.chmod(backup_path, 0o600)
        backup = str(backup_path)

    env_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{env_file.name}.", dir=str(env_file.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, env_file)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)

    return {
        "rotated": True,
        "env_file": str(env_file),
        "backup": backup,
        "secret_bytes": nbytes,
        "secret_printed": False,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=root / ".env.local")
    parser.add_argument("--backup-dir", type=Path, default=root / "state" / "env_backups")
    parser.add_argument("--bytes", type=int, default=32)
    args = parser.parse_args()
    print(json.dumps(rotate_secret(args.env_file, args.backup_dir, nbytes=args.bytes), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
