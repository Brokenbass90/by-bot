from __future__ import annotations

import json

import pytest

from web import auth
from web.reset_password import reset_user_password


def _write_user(path, *, password: str = "old-password-long") -> None:
    path.write_text(
        json.dumps(
            {
                "users": {
                    "owner@example.com": {
                        "hashed_password": auth.hash_password(password),
                        "totp_secret": "JBSWY3DPEHPK3PXP",
                        "enabled": True,
                        "is_admin": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_password_only_reset_preserves_totp_and_role(tmp_path, monkeypatch) -> None:
    config = tmp_path / "web_config.json"
    _write_user(config)
    monkeypatch.setattr(auth, "_CONFIG_PATH", config)

    receipt = reset_user_password(" Owner@Example.com ", "new-password-long")
    stored = json.loads(config.read_text(encoding="utf-8"))["users"]["owner@example.com"]

    assert auth.verify_password("new-password-long", stored["hashed_password"])
    assert not auth.verify_password("old-password-long", stored["hashed_password"])
    assert stored["totp_secret"] == "JBSWY3DPEHPK3PXP"
    assert stored["is_admin"] is True
    assert receipt["totp_preserved"] is True
    assert receipt["role_preserved"] is True
    assert len(str(receipt["hash_fingerprint"])) == 12
    assert config.stat().st_mode & 0o777 == 0o600


def test_reset_refuses_unknown_user_without_creating_one(tmp_path, monkeypatch) -> None:
    config = tmp_path / "web_config.json"
    _write_user(config)
    monkeypatch.setattr(auth, "_CONFIG_PATH", config)

    with pytest.raises(KeyError):
        reset_user_password("other@example.com", "new-password-long")

    assert set(auth._load_config()["users"]) == {"owner@example.com"}


def test_reset_refuses_short_password(tmp_path, monkeypatch) -> None:
    config = tmp_path / "web_config.json"
    _write_user(config)
    monkeypatch.setattr(auth, "_CONFIG_PATH", config)

    with pytest.raises(ValueError, match="at least 12"):
        reset_user_password("owner@example.com", "too-short")
