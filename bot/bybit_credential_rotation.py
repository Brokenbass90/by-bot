"""Safe Bybit credential rotation primitives.

The module deliberately returns only redacted metadata.  Credential values are
never written to logs, status files, audit records, or command-line arguments.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request


class RotationError(RuntimeError):
    """A safe, user-displayable rotation failure without secret material."""


def credential_fingerprint(value: str) -> str:
    """One-way identifier used only to correlate stored/applied credentials."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _signed_get(
    *,
    key: str,
    secret: str,
    base_url: str,
    path: str,
    params: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    query = parse.urlencode(sorted((params or {}).items()))
    timestamp = str(int(time.time() * 1000))
    recv_window = "10000"
    prehash = f"{timestamp}{key}{recv_window}{query}"
    signature = hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).hexdigest()
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"
    req = request.Request(
        url,
        headers={
            "X-BAPI-API-KEY": key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except error.HTTPError as exc:
        return {"retCode": exc.code, "retMsg": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"retCode": -1, "retMsg": f"{type(exc).__name__}: {str(exc)[:120]}"}


def validate_candidate_credentials(
    *,
    key: str,
    secret: str,
    base_url: str = "https://api.bybit.com",
    getter: Callable[..., dict[str, Any]] = _signed_get,
) -> dict[str, Any]:
    """Validate identity, permissions and flatness using the candidate key."""
    api_info = getter(
        key=key,
        secret=secret,
        base_url=base_url,
        path="/v5/user/query-api",
        params=None,
    )
    if str(api_info.get("retCode")) != "0":
        raise RotationError(
            f"candidate key rejected by Bybit: retCode={api_info.get('retCode')} "
            f"{str(api_info.get('retMsg') or '')[:100]}"
        )

    info = api_info.get("result") or {}
    permissions = info.get("permissions") or {}
    contract_permissions = set(permissions.get("ContractTrade") or [])
    wallet_permissions = set(permissions.get("Wallet") or [])
    required = {"Order", "Position"}
    if not required.issubset(contract_permissions):
        raise RotationError("candidate key lacks ContractTrade Order/Position permissions")
    if wallet_permissions:
        raise RotationError("candidate key has Wallet/transfer/withdraw permissions; refuse rotation")

    positions = getter(
        key=key,
        secret=secret,
        base_url=base_url,
        path="/v5/position/list",
        params={"category": "linear", "settleCoin": "USDT", "limit": "200"},
    )
    if str(positions.get("retCode")) != "0":
        raise RotationError(
            f"candidate key cannot query positions: retCode={positions.get('retCode')} "
            f"{str(positions.get('retMsg') or '')[:100]}"
        )
    position_rows = (positions.get("result") or {}).get("list") or []
    open_positions = [
        row for row in position_rows
        if isinstance(row, dict) and abs(float(row.get("size") or 0.0)) > 0.0
    ]
    ips = [str(value) for value in (info.get("ips") or [])]
    non_contract_scopes = sorted(
        name for name, values in permissions.items()
        if name not in {"ContractTrade", "Wallet"} and values
    )
    return {
        "ok": True,
        "key_fingerprint": credential_fingerprint(key),
        "expires_at": info.get("expiredAt"),
        "read_only": bool(int(info.get("readOnly") or 0)),
        "required_contract_permissions": True,
        "withdrawal_permissions": False,
        "ip_restricted": bool(ips and ips != ["*"]),
        "non_contract_scopes": non_contract_scopes,
        "open_position_count": len(open_positions),
        "open_symbols": sorted({str(row.get("symbol")) for row in open_positions if row.get("symbol")}),
    }


def _parse_accounts(text: str) -> tuple[list[dict[str, Any]], str]:
    prefix = "BYBIT_ACCOUNTS_JSON="
    for line in text.splitlines():
        if line.startswith(prefix):
            raw = line[len(prefix):].strip()
            try:
                accounts = json.loads(raw)
            except Exception as exc:
                raise RotationError(f"BYBIT_ACCOUNTS_JSON parse error: {exc}") from exc
            if not isinstance(accounts, list):
                raise RotationError("BYBIT_ACCOUNTS_JSON must be a list")
            return accounts, line
    raise RotationError("BYBIT_ACCOUNTS_JSON not found")


def _private_atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(raw_tmp)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        path.chmod(0o600)
    finally:
        if tmp.exists():
            tmp.unlink()


def replace_account_credentials(
    *,
    env_path: Path,
    backup_dir: Path,
    account_name: str,
    new_key: str,
    new_secret: str,
) -> tuple[Path, str]:
    """Backup then atomically replace one account; return backup and fingerprint."""
    if env_path.is_symlink():
        raise RotationError("refusing to rotate credentials through a symlinked env file")
    if not env_path.is_file():
        raise RotationError(f"env file not found: {env_path}")
    old_text = env_path.read_text(encoding="utf-8")
    accounts, old_line = _parse_accounts(old_text)
    matches = [row for row in accounts if isinstance(row, dict) and row.get("name") == account_name]
    if len(matches) != 1:
        raise RotationError(f"expected exactly one account named {account_name!r}, found {len(matches)}")
    matches[0]["key"] = new_key
    matches[0]["secret"] = new_secret
    new_line = "BYBIT_ACCOUNTS_JSON=" + json.dumps(accounts, separators=(",", ":"))
    new_text = old_text.replace(old_line, new_line, 1)

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup = backup_dir / f".env.{stamp}.bybit_key_rotate.bak"
    _private_atomic_write(backup, old_text)
    _private_atomic_write(env_path, new_text)
    return backup, credential_fingerprint(new_key)


def restore_backup(*, env_path: Path, backup_path: Path) -> None:
    if not backup_path.is_file():
        raise RotationError("credential rollback backup is missing")
    _private_atomic_write(env_path, backup_path.read_text(encoding="utf-8"))


def write_safe_rotation_status(path: Path, payload: dict[str, Any]) -> None:
    safe = dict(payload)
    for forbidden in ("key", "secret", "new_key", "new_secret"):
        safe.pop(forbidden, None)
    safe["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    _private_atomic_write(path, json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def restart_and_verify(
    *,
    service: str,
    repo_root: Path,
    timeout_sec: float = 30.0,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Restart systemd service and require fresh heartbeat plus startup auth OK."""
    started = time.time()
    runner(["systemctl", "restart", service], check=True, capture_output=True, text=True)
    deadline = started + timeout_sec
    heartbeat_path = repo_root / "runtime" / "bot_heartbeat.json"
    startup_path = repo_root / "runtime" / "startup_notify_state.json"
    while time.time() < deadline:
        try:
            heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            startup = json.loads(startup_path.read_text(encoding="utf-8"))
            startup_auth = startup.get("startup_auth") or {}
            heartbeat_ts = float(heartbeat.get("ts") or 0.0)
            auth_ts = float(startup_auth.get("ts") or 0.0)
            auth_text = str(startup_auth.get("text") or "")
            if heartbeat_ts >= started - 2 and auth_ts >= started - 2 and "auth OK" in auth_text:
                return {
                    "ok": True,
                    "service": service,
                    "heartbeat_ts": int(heartbeat_ts),
                    "auth_verified": True,
                    "trade_on": bool(heartbeat.get("trade_on")),
                    "dry_run": bool(heartbeat.get("dry_run")),
                    "open_trades": int(heartbeat.get("open_trades") or 0),
                }
        except Exception:
            pass
        time.sleep(1.0)
    raise RotationError("service restarted but fresh heartbeat with auth OK was not observed")


def rotate_and_optionally_apply(
    *,
    repo_root: Path,
    account_name: str,
    new_key: str,
    new_secret: str,
    apply_when_flat: bool,
    service: str = "bybot.service",
    validator: Callable[..., dict[str, Any]] = validate_candidate_credentials,
    restarter: Callable[..., dict[str, Any]] = restart_and_verify,
) -> dict[str, Any]:
    """End-to-end transaction with preflight, atomic write and rollback."""
    env_path = repo_root / ".env"
    backup_dir = repo_root / "state" / "env_backups"
    status_path = repo_root / "runtime" / "bybit_credential_rotation_status.json"
    text = env_path.read_text(encoding="utf-8")
    accounts, _ = _parse_accounts(text)
    target = next((row for row in accounts if isinstance(row, dict) and row.get("name") == account_name), None)
    if target is None:
        raise RotationError(f"account {account_name!r} not found")
    base_url = str(target.get("base") or "https://api.bybit.com")
    preflight = validator(key=new_key, secret=new_secret, base_url=base_url)
    backup, fingerprint = replace_account_credentials(
        env_path=env_path,
        backup_dir=backup_dir,
        account_name=account_name,
        new_key=new_key,
        new_secret=new_secret,
    )
    result: dict[str, Any] = {
        "status": "stored_pending_restart",
        "account": account_name,
        "key_fingerprint": fingerprint,
        "preflight": preflight,
        "protected_backup_created": True,
        "credential_values_returned": False,
        "need_restart": True,
    }
    write_safe_rotation_status(status_path, result)
    if not apply_when_flat or int(preflight.get("open_position_count") or 0) > 0:
        return result
    try:
        verification = restarter(service=service, repo_root=repo_root)
    except Exception as exc:
        rollback_ok = False
        try:
            restore_backup(env_path=env_path, backup_path=backup)
            restarter(service=service, repo_root=repo_root)
            rollback_ok = True
        except Exception:
            pass
        failed = {
            **result,
            "status": "apply_failed_rolled_back" if rollback_ok else "apply_failed_rollback_failed",
            "need_restart": not rollback_ok,
            "error": f"{type(exc).__name__}: {str(exc)[:180]}",
            "rollback_ok": rollback_ok,
        }
        write_safe_rotation_status(status_path, failed)
        raise RotationError(f"credential apply failed; rollback_ok={rollback_ok}") from exc
    result.update({"status": "applied_verified", "need_restart": False, "verification": verification})
    write_safe_rotation_status(status_path, result)
    return result


def verify_current_configuration(
    *,
    repo_root: Path,
    account_name: str = "main",
    validator: Callable[..., dict[str, Any]] = validate_candidate_credentials,
) -> dict[str, Any]:
    """Materialize safe evidence for credentials already present in ``.env``."""
    env_path = repo_root / ".env"
    accounts, _ = _parse_accounts(env_path.read_text(encoding="utf-8"))
    target = next((row for row in accounts if isinstance(row, dict) and row.get("name") == account_name), None)
    if target is None:
        raise RotationError(f"account {account_name!r} not found")
    key = str(target.get("key") or "")
    secret = str(target.get("secret") or "")
    if not key or not secret:
        raise RotationError("configured account has missing key or secret")
    preflight = validator(
        key=key,
        secret=secret,
        base_url=str(target.get("base") or "https://api.bybit.com"),
    )
    env_mtime = env_path.stat().st_mtime
    heartbeat: dict[str, Any] = {}
    startup_auth: dict[str, Any] = {}
    try:
        heartbeat = json.loads((repo_root / "runtime" / "bot_heartbeat.json").read_text(encoding="utf-8"))
        startup = json.loads((repo_root / "runtime" / "startup_notify_state.json").read_text(encoding="utf-8"))
        startup_auth = startup.get("startup_auth") or {}
    except Exception:
        pass
    heartbeat_ts = float(heartbeat.get("ts") or 0.0)
    auth_ts = float(startup_auth.get("ts") or 0.0)
    auth_ok = "auth OK" in str(startup_auth.get("text") or "")
    applied = heartbeat_ts >= env_mtime and auth_ts >= env_mtime and auth_ok
    result = {
        "status": "applied_verified" if applied else "stored_pending_restart",
        "account": account_name,
        "key_fingerprint": credential_fingerprint(key),
        "preflight": preflight,
        "credential_values_returned": False,
        "need_restart": not applied,
        "verification": {
            "auth_verified": applied,
            "heartbeat_ts": int(heartbeat_ts) if heartbeat_ts else None,
            "startup_auth_ts": int(auth_ts) if auth_ts else None,
            "env_mtime": int(env_mtime),
            "trade_on": bool(heartbeat.get("trade_on")),
            "dry_run": bool(heartbeat.get("dry_run")),
            "open_trades": int(heartbeat.get("open_trades") or 0),
        },
    }
    write_safe_rotation_status(
        repo_root / "runtime" / "bybit_credential_rotation_status.json",
        result,
    )
    return result
