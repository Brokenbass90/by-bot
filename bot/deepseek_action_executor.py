"""
deepseek_action_executor.py
============================
Executes approved DeepSeek proposals:
  - Reads "changes" list from approval queue item
  - Patches the active local env file
  - Optionally deploys it to the server via SSH

Telegram commands:
  /ai_deploy <id>   – execute an approved proposal (patch env + push to server)
  /ai_diff          – show what would change if all approved proposals were applied
  /ai_rollback      – revert the active env file to the last backup
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

_ENV_BACKUP_DIR = _ROOT / "configs" / "env_backups"


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def _active_local_env() -> Path:
    """
    Resolve which local env file should be patched.

    Default priority:
      1. DEEPSEEK_EXECUTOR_ENV_PATH
      2. repo/.env   (gitignored, preferred for live-aligned local ops)
      3. configs/server_clean.env (legacy fallback)
    """
    raw = _env("DEEPSEEK_EXECUTOR_ENV_PATH", "")
    candidates = []
    if raw:
        candidates.append(Path(raw).expanduser())
    candidates.append(_ROOT / ".env")
    candidates.append(_ROOT / "configs" / "server_clean.env")
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _remote_env_path() -> str:
    return _env("DEEPSEEK_EXECUTOR_REMOTE_ENV_PATH", f"{_SERVER_BOT_DIR}/.env")


def _backup_name(active_env: Path) -> str:
    return f"{active_env.stem}_{time.strftime('%Y%m%d_%H%M%S')}{active_env.suffix or '.env'}"


# ── env patching ──────────────────────────────────────────────────────────────

def _backup_env() -> Path:
    """Save a timestamped copy of the active env file before patching."""
    active_env = _active_local_env()
    _ENV_BACKUP_DIR.mkdir(exist_ok=True)
    dest = _ENV_BACKUP_DIR / _backup_name(active_env)
    shutil.copy2(active_env, dest)
    # keep last 20 backups
    backups = sorted(_ENV_BACKUP_DIR.glob(f"{active_env.stem}_*{active_env.suffix or '.env'}"))
    for old in backups[:-20]:
        old.unlink(missing_ok=True)
    return dest


def patch_env_file(changes: list[dict[str, Any]]) -> list[str]:
    """
    Apply a list of {env_key, new_value} changes to the active env file.
    Returns list of applied change descriptions.
    """
    active_env = _active_local_env()
    if not active_env.exists():
        raise FileNotFoundError(f"Config not found: {active_env}")
    content = active_env.read_text(encoding="utf-8")
    applied: list[str] = []
    for ch in changes:
        key = str(ch.get("env_key") or "").strip()
        val = str(ch.get("new_value") or "").strip()
        if not key:
            continue
        # Replace existing key=... line (handles KEY=VAL and KEY="VAL")
        pattern = re.compile(
            rf"^({re.escape(key)})\s*=.*$", re.MULTILINE
        )
        new_line = f"{key}={val}"
        if pattern.search(content):
            content = pattern.sub(new_line, content)
            applied.append(f"  {key}={val}  (updated)")
        else:
            # Append at end
            content = content.rstrip("\n") + f"\n{new_line}\n"
            applied.append(f"  {key}={val}  (added)")
    active_env.write_text(content, encoding="utf-8")
    return applied


def diff_pending_changes(pending_items: list[dict[str, Any]]) -> str:
    """Show what env changes would be applied if all pending items were deployed."""
    active_env = _active_local_env()
    if not active_env.exists():
        return f"env не найден: {active_env}"
    content = active_env.read_text(encoding="utf-8")
    lines: list[str] = ["Предполагаемые изменения:"]
    for item in pending_items:
        changes = (item.get("payload") or {}).get("changes") or []
        if not changes:
            continue
        lines.append(f"\nProposal id={item.get('id')} ({item.get('summary','')[:60]}…):")
        for ch in changes:
            key = str(ch.get("env_key") or "")
            new_val = str(ch.get("new_value") or "")
            m = re.search(rf"^{re.escape(key)}\s*=(.*)$", content, re.MULTILINE)
            old_val = m.group(1).strip() if m else "(нет)"
            lines.append(f"  {key}: {old_val} → {new_val}")
    return "\n".join(lines) if len(lines) > 1 else "Нет pending изменений."


# ── SSH deploy ────────────────────────────────────────────────────────────────

_SERVER_HOST = "64.226.73.119"
_SERVER_USER = "root"
_SERVER_BOT_DIR = "/root/by-bot"
_SSH_KEY = str(Path.home() / ".ssh" / "by-bot")


def _ssh(cmd: str, timeout: int = 30) -> tuple[str, int]:
    """Run a command on the server via SSH. Returns (output, returncode)."""
    full_cmd = [
        "ssh", "-i", _SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=15",
        f"{_SERVER_USER}@{_SERVER_HOST}",
        cmd,
    ]
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True, text=True, timeout=timeout
        )
        out = (result.stdout + result.stderr).strip()
        return out, result.returncode
    except subprocess.TimeoutExpired:
        return "SSH timeout", 1
    except Exception as e:
        return f"SSH error: {e}", 1


def _scp(local_path: Path, remote_path: str, timeout: int = 30) -> tuple[str, int]:
    """SCP a local file to the server."""
    full_cmd = [
        "scp", "-i", _SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=15",
        str(local_path),
        f"{_SERVER_USER}@{_SERVER_HOST}:{remote_path}",
    ]
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True, text=True, timeout=timeout
        )
        out = (result.stdout + result.stderr).strip()
        return out, result.returncode
    except Exception as e:
        return f"SCP error: {e}", 1


def deploy_env_to_server() -> str:
    """
    Push the active env file to the server and restart the bot.
    Returns a status message for Telegram.
    """
    lines: list[str] = []
    active_env = _active_local_env()
    remote_env = _remote_env_path()

    # 1. SCP the file
    out, rc = _scp(active_env, remote_env)
    if rc != 0:
        return f"❌ SCP failed (rc={rc}):\n{out}"
    lines.append(f"✅ {active_env.name} скопирован на сервер → {remote_env}")

    # 2. Restart service
    out, rc = _ssh("systemctl restart bybot && sleep 3 && systemctl is-active bybot")
    status_line = out.strip().splitlines()[-1] if out.strip() else "unknown"
    if rc == 0 and "active" in status_line.lower():
        lines.append(f"✅ bybot.service перезапущен: {status_line}")
    else:
        lines.append(f"⚠️ bybot.service статус: {status_line}\n{out[:200]}")

    return "\n".join(lines)


def check_server_status() -> str:
    """Quick server health check for Telegram."""
    out, rc = _ssh(
        "systemctl is-active bybot && "
        "journalctl -u bybot -n 5 --no-pager 2>/dev/null | tail -5"
    )
    return f"Сервер ({_SERVER_HOST}):\n{out[:600]}" if out else "Нет ответа от сервера."


# ── main execute function ────────────────────────────────────────────────────

def execute_proposal(
    proposal_id: int,
    approval_queue: list[dict[str, Any]],
    deploy: bool = True,
) -> str:
    """
    Find an approved proposal by id, patch the env, optionally deploy.
    Returns a Telegram message string.
    """
    item = next(
        (x for x in approval_queue if int(x.get("id") or -1) == int(proposal_id)), None
    )
    if not item:
        return f"Proposal {proposal_id} не найден в очереди."

    status = str(item.get("status") or "").strip()
    if status != "approved":
        return f"Proposal {proposal_id} имеет статус '{status}'. Нужен 'approved'."

    changes = (item.get("payload") or {}).get("changes") or []
    if not changes:
        return f"Proposal {proposal_id} не содержит changes."

    lines = [f"🔧 Применяю proposal {proposal_id}:"]

    # Backup + patch
    try:
        backup = _backup_env()
        lines.append(f"  Бэкап: {backup.name}")
        applied = patch_env_file(changes)
        lines.extend(applied)
    except Exception as e:
        return f"❌ Ошибка патча env: {e}"

    # Mark as executed
    item["status"] = "executed"
    item["executed_ts"] = int(time.time())

    if not deploy:
        lines.append("\n⚠️ deploy=False — изменения только локальны.")
        lines.append("Запусти /ai_deploy вручную, когда будешь готов.")
        return "\n".join(lines)

    # Deploy to server
    lines.append("\n📡 Деплоим на сервер...")
    deploy_result = deploy_env_to_server()
    lines.append(deploy_result)

    return "\n".join(lines)


# ── rollback ─────────────────────────────────────────────────────────────────

def rollback_env() -> str:
    """Restore the most recent backup of the active env file."""
    active_env = _active_local_env()
    backups = sorted(_ENV_BACKUP_DIR.glob(f"{active_env.stem}_*{active_env.suffix or '.env'}"))
    if not backups:
        return "Нет бэкапов для отката."
    latest = backups[-1]
    shutil.copy2(latest, active_env)
    return (
        f"↩️ Откат выполнен.\n"
        f"  Восстановлен: {latest.name}\n"
        "Используй /ai_deploy для деплоя на сервер."
    )
