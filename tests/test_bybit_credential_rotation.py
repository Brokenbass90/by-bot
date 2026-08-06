from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from bot.bybit_credential_rotation import (
    RotationError,
    replace_account_credentials,
    rotate_and_optionally_apply,
    validate_candidate_credentials,
    verify_current_configuration,
)


def _getter_factory(*, wallet=None, positions=None, contract=None, ips=None):
    def getter(**kwargs):
        if kwargs["path"] == "/v5/user/query-api":
            return {
                "retCode": 0,
                "result": {
                    "expiredAt": "2026-11-06T00:00:00Z",
                    "readOnly": 0,
                    "ips": ["1.2.3.4"] if ips is None else ips,
                    "permissions": {
                        "ContractTrade": ["Order", "Position"] if contract is None else contract,
                        "Wallet": [] if wallet is None else wallet,
                        "Spot": ["SpotTrade"],
                    },
                },
            }
        return {"retCode": 0, "result": {"list": positions or []}}
    return getter


def _env(root: Path) -> Path:
    path = root / ".env"
    path.write_text(
        'KEEP=1\nBYBIT_ACCOUNTS_JSON=[{"name":"main","key":"old-key-value","secret":"old-secret-value-which-is-long","trade":{"enabled":true}}]\n',
        encoding="utf-8",
    )
    return path


def test_candidate_preflight_reports_safe_permissions_and_flatness():
    result = validate_candidate_credentials(
        key="new-key-value-123",
        secret="new-secret-value-which-is-long",
        getter=_getter_factory(ips=["*"]),
    )
    assert result["ok"] is True
    assert result["open_position_count"] == 0
    assert result["withdrawal_permissions"] is False
    assert result["ip_restricted"] is False
    assert result["non_contract_scopes"] == ["Spot"]
    assert "new-key" not in json.dumps(result)


def test_candidate_with_withdraw_permission_is_rejected():
    with pytest.raises(RotationError, match="Wallet"):
        validate_candidate_credentials(
            key="new-key-value-123",
            secret="new-secret-value-which-is-long",
            getter=_getter_factory(wallet=["Withdraw"]),
        )


def test_atomic_replacement_preserves_other_fields_and_private_modes(tmp_path):
    env_path = _env(tmp_path)
    backup, fingerprint = replace_account_credentials(
        env_path=env_path,
        backup_dir=tmp_path / "backups",
        account_name="main",
        new_key="new-key-value-123",
        new_secret="new-secret-value-which-is-long",
    )
    text = env_path.read_text(encoding="utf-8")
    assert "KEEP=1" in text
    assert '"enabled":true' in text
    assert "new-key-value-123" in text
    assert "old-key-value" in backup.read_text(encoding="utf-8")
    assert len(fingerprint) == 12
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600


def test_open_position_stores_validated_key_but_defers_restart(tmp_path):
    _env(tmp_path)
    restart_calls = []

    def validator(**_kwargs):
        return {
            "ok": True,
            "key_fingerprint": "candidate",
            "withdrawal_permissions": False,
            "open_position_count": 1,
            "open_symbols": ["BTCUSDT"],
        }

    def restarter(**kwargs):
        restart_calls.append(kwargs)
        return {"ok": True}

    result = rotate_and_optionally_apply(
        repo_root=tmp_path,
        account_name="main",
        new_key="new-key-value-123",
        new_secret="new-secret-value-which-is-long",
        apply_when_flat=True,
        validator=validator,
        restarter=restarter,
    )
    assert result["status"] == "stored_pending_restart"
    assert result["need_restart"] is True
    assert restart_calls == []


def test_flat_rotation_requires_and_records_fresh_restart_proof(tmp_path):
    _env(tmp_path)

    def validator(**_kwargs):
        return {
            "ok": True,
            "key_fingerprint": "candidate",
            "withdrawal_permissions": False,
            "ip_restricted": True,
            "open_position_count": 0,
            "open_symbols": [],
        }

    def restarter(**_kwargs):
        return {"ok": True, "auth_verified": True, "heartbeat_ts": 123}

    result = rotate_and_optionally_apply(
        repo_root=tmp_path,
        account_name="main",
        new_key="new-key-value-123",
        new_secret="new-secret-value-which-is-long",
        apply_when_flat=True,
        validator=validator,
        restarter=restarter,
    )
    status = json.loads((tmp_path / "runtime" / "bybit_credential_rotation_status.json").read_text())
    assert result["status"] == "applied_verified"
    assert result["need_restart"] is False
    assert status["verification"]["auth_verified"] is True
    blob = json.dumps(status)
    assert "new-key-value-123" not in blob
    assert "new-secret-value" not in blob


def test_failed_apply_restores_previous_credentials(tmp_path):
    env_path = _env(tmp_path)
    old_text = env_path.read_text(encoding="utf-8")
    calls = 0

    def validator(**_kwargs):
        return {"ok": True, "withdrawal_permissions": False, "open_position_count": 0}

    def restarter(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RotationError("no fresh heartbeat")
        return {"ok": True, "auth_verified": True}

    with pytest.raises(RotationError, match="rollback_ok=True"):
        rotate_and_optionally_apply(
            repo_root=tmp_path,
            account_name="main",
            new_key="new-key-value-123",
            new_secret="new-secret-value-which-is-long",
            apply_when_flat=True,
            validator=validator,
            restarter=restarter,
        )
    assert env_path.read_text(encoding="utf-8") == old_text


def test_existing_configuration_is_verified_only_after_post_env_auth(tmp_path):
    env_path = _env(tmp_path)
    env_mtime = env_path.stat().st_mtime
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "bot_heartbeat.json").write_text(json.dumps({
        "ts": env_mtime + 5, "trade_on": True, "dry_run": False, "open_trades": 0,
    }))
    (runtime / "startup_notify_state.json").write_text(json.dumps({
        "startup_auth": {"ts": env_mtime + 4, "text": "main: auth OK"},
    }))

    def validator(**_kwargs):
        return {"ok": True, "withdrawal_permissions": False, "open_position_count": 0}

    result = verify_current_configuration(repo_root=tmp_path, validator=validator)
    assert result["status"] == "applied_verified"
    assert result["verification"]["auth_verified"] is True
    assert "old-secret-value" not in json.dumps(result)
