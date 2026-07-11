from __future__ import annotations

import re
import stat

from scripts.rotate_web_jwt_secret import rotate_secret


def test_rotate_secret_is_atomic_private_and_does_not_return_secret(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("KEEP_ME=1\nWEB_JWT_SECRET=change-me-use-openssl-rand-hex-32\n", encoding="utf-8")
    backup_dir = tmp_path / "backups"

    result = rotate_secret(env_file, backup_dir)
    rows = dict(row.split("=", 1) for row in env_file.read_text(encoding="utf-8").splitlines() if "=" in row)

    assert rows["KEEP_ME"] == "1"
    assert re.fullmatch(r"[0-9a-f]{64}", rows["WEB_JWT_SECRET"])
    assert "secret" not in result or result.get("secret_printed") is False
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    backup = next(backup_dir.iterdir())
    assert "change-me-use-openssl-rand-hex-32" in backup.read_text(encoding="utf-8")
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600


def test_rotate_secret_rejects_short_entropy(tmp_path):
    try:
        rotate_secret(tmp_path / ".env.local", tmp_path / "backups", nbytes=16)
    except ValueError as exc:
        assert "at least 32" in str(exc)
    else:
        raise AssertionError("short JWT secret was accepted")


def test_rotate_secret_rejects_symlink(tmp_path):
    real_env = tmp_path / "real.env"
    real_env.write_text("WEB_JWT_SECRET=old\n", encoding="utf-8")
    linked_env = tmp_path / ".env.local"
    linked_env.symlink_to(real_env)

    try:
        rotate_secret(linked_env, tmp_path / "backups")
    except ValueError as exc:
        assert "symlink" in str(exc)
    else:
        raise AssertionError("symlinked env file was accepted")

    assert real_env.read_text(encoding="utf-8") == "WEB_JWT_SECRET=old\n"
