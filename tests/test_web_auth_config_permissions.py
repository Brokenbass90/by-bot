from __future__ import annotations

import json
import stat

from web import auth


def test_save_config_is_atomic_and_owner_only(monkeypatch, tmp_path) -> None:
    config = tmp_path / "web_config.json"
    config.write_text("{}", encoding="utf-8")
    config.chmod(0o644)
    monkeypatch.setattr(auth, "_CONFIG_PATH", config)

    payload = {"users": {"operator@example.test": {"enabled": True}}}
    auth._save_config(payload)

    assert json.loads(config.read_text(encoding="utf-8")) == payload
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert not config.with_suffix(".tmp").exists()
