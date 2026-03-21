"""
deepseek_action_executor.py
============================
Executes approved DeepSeek proposals:
  - Reads "changes" list from approval queue item
  - Patches configs/server_clean.env
  - Optionally deploys to server via SSH

Telegram commands:
  /ai_deploy <id>   – execute an approved proposal (patch env + push to server)
  /ai_diff          – show what would change if all approved proposals were applied
  /ai_rollback      – revert server_clean.env to the last backup
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

_SERVER_ENV = _ROOT / "configs" / "server_clean.env"
_ENV_BACKUP_DIR = _ROOT / "configs" / "env_backups"


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


# ── env patching ──────────────────────────────────────────────────────────────

def _backup_env() -> Path:
    """Save a timestamped copy of server_clean.env before patching."""
    _ENV_BACKUP_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = _ENV_BACKUP_DIR / f"server_clean_{stamp}.env"
    shutil.copy2(_SERVER_ENV, dest)
    # keep last 20 backups
    backups = sorted(_ENV_BACKUP_DIR.glob("server_clean_*.env"))
    for old in backups[:-20]:
        old.unlink(missing_ok=True)
    return dest


def patch_env_file(changes: list[dict[str, Any]]) -> list[str]:
    """
    Apply a list of {env_key, new_value} changes to server_clean.env.
    Returns list of applied change descriptions.
    """
    if not _SERVER_ENV.exists():
        raise FileNotFoundError(f"Config not found: {_SERVER_ENV}")
    content = _SERVER_ENV.read_text(encoding="utf-8")
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
    _SERVER_ENV.write_text(content, encoding="utf-8")
    return applied


def diff_pending_changes(pending_items: list[dict[str, Any]]) -> str:
    """Show what env changes would be applied if all pending items were deployed."""
    if not _SERVER_ENV.exists():
        return "server_clean.env не найден."
    content = _SERVER_ENV.read_text(encoding="utf-8")
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
    Push server_clean.env to server and restart the bot.
    Returns a status message for Telegram.
    """
    lines: list[str] = []

    # 1. SCP the file
    remote_env = f"{_SERVER_BOT_DIR}/configs/server_clean.env"
    out, rc = _scp(_SERVER_ENV, remote_env)
    if rc != 0:
        return f"❌ SCP failed (rc={rc}):\n{out}"
    lines.append(f"✅ server_clean.env скопирован на сервер")

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
    """Restore the most recent backup of server_clean.env."""
    backups = sorted(_ENV_BACKUP_DIR.glob("server_clean_*.env"))
    if not backups:
        return "Нет бэкапов для отката."
    latest = backups[-1]
    shutil.copy2(latest, _SERVER_ENV)
    return (
        f"↩️ Откат выполнен.\n"
        f"  Восстановлен: {latest.name}\n"
        "Используй /ai_deploy для деплоя на сервер."
    )
