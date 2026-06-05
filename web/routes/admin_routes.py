"""Admin routes: user management + daily P&L stats."""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import _load_config, _save_config, hash_password
from ..deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ROOT = Path(__file__).parent.parent.parent
_RUNTIME_ROOT = Path(os.getenv("WEB_RUNTIME_ROOT", str(_ROOT / "runtime")))


def _rt(*p: str) -> Path:
    return _RUNTIME_ROOT / Path(*p)


def _env_text_value(text: str, key: str) -> str:
    prefix = f"{key}="
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip('"').strip("'")
    return ""


def _load_runtime_arb_account_status() -> Dict[str, Any]:
    """Read scrubbed exchange account status written by the arb read-only helper."""
    for path in (
        _rt("arb", "exchange_account_status.json"),
        _ROOT / "runtime" / "arb" / "exchange_account_status.json",
    ):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return {}


# ── User management ───────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(email: str = Depends(require_admin)):
    """List all users in web_config.json."""
    cfg = _load_config()
    users = []
    for em, data in cfg.get("users", {}).items():
        users.append({
            "email": em,
            "enabled": data.get("enabled", True),
            "has_totp": bool(data.get("totp_secret")),
            "has_password": bool(data.get("hashed_password")),
            "note": data.get("note", ""),
        })
    return {"users": users}


class AddUserRequest(BaseModel):
    email: str
    note: Optional[str] = ""


@router.post("/users")
async def add_user(body: AddUserRequest, email: str = Depends(require_admin)):
    """Pre-create user slot (TOTP setup still required via CLI)."""
    target = body.email.strip().lower()
    if not target or "@" not in target:
        raise HTTPException(status_code=400, detail="Invalid email")

    cfg = _load_config()
    cfg.setdefault("users", {})[target] = {
        "enabled": False,
        "is_admin": False,
        "note": body.note or "pending_totp_setup",
    }
    _save_config(cfg)
    return {"created": target, "message": f"Slot created. Run: python3 web/setup_totp.py --email {target}"}


@router.delete("/users/{target_email}")
async def remove_user(target_email: str, email: str = Depends(require_admin)):
    target = target_email.strip().lower()
    if target == email:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    cfg = _load_config()
    users = cfg.get("users", {})
    if target not in users:
        raise HTTPException(status_code=404, detail="User not found")

    del users[target]
    cfg["users"] = users
    _save_config(cfg)
    return {"removed": target}


@router.post("/users/{target_email}/toggle")
async def toggle_user(target_email: str, email: str = Depends(require_admin)):
    target = target_email.strip().lower()
    if target == email:
        raise HTTPException(status_code=400, detail="Cannot disable yourself")

    cfg = _load_config()
    users = cfg.get("users", {})
    if target not in users:
        raise HTTPException(status_code=404, detail="User not found")

    current = users[target].get("enabled", True)
    users[target]["enabled"] = not current
    cfg["users"] = users
    _save_config(cfg)
    return {"email": target, "enabled": not current}


# ── Daily P&L stats ───────────────────────────────────────────────────────────

def _normalise_ts(raw: str) -> str:
    """Convert ms-epoch or ISO timestamp to YYYY-MM-DD HH:MM string."""
    if raw and str(raw).isdigit():
        try:
            return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    return str(raw)


def _load_all_trades() -> List[Dict[str, Any]]:
    """Load trades, normalising both old and new CSV schemas to canonical field names."""
    seen: set = set()
    trades: List[Dict[str, Any]] = []
    paths = sorted(
        list(_RUNTIME_ROOT.glob("**/trades.csv")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    root_csv = _RUNTIME_ROOT / "trades.csv"
    if not root_csv.exists():
        root_csv = _ROOT / "trades.csv"
    if root_csv.exists():
        paths.insert(0, root_csv)

    for csv_path in paths[:5]:
        try:
            with open(csv_path, newline="") as f:
                for row in csv.DictReader(f):
                    t = dict(row)
                    # new schema → canonical
                    if "exit_ts" in t and "close_time" not in t:
                        t["close_time"] = _normalise_ts(t["exit_ts"])
                    if "entry_ts" in t and "open_time" not in t:
                        t["open_time"] = _normalise_ts(t["entry_ts"])
                    if "entry_price" in t and "entry" not in t:
                        t["entry"] = t["entry_price"]
                    if "exit_price" in t and "exit" not in t:
                        t["exit"] = t["exit_price"]
                    if "qty" in t and "size" not in t:
                        t["size"] = t["qty"]
                    if "pnl_pct_equity" in t and "pnl_pct" not in t:
                        t["pnl_pct"] = t["pnl_pct_equity"]

                    key = (t.get("strategy"), t.get("symbol"), t.get("open_time"), t.get("entry"))
                    if key in seen:
                        continue
                    seen.add(key)

                    for field in ("pnl", "entry", "exit", "size", "fees", "pnl_pct"):
                        if t.get(field):
                            try:
                                t[field] = float(t[field])
                            except (ValueError, TypeError):
                                pass
                    trades.append(t)
        except Exception:
            pass

    if trades:
        return trades

    live_jsonl = _rt("live_trade_events.jsonl")
    if live_jsonl.exists():
        buckets: Dict[str, Dict[str, Any]] = {}
        try:
            for raw in live_jsonl.read_text(errors="ignore").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    evt = json.loads(raw)
                except Exception:
                    continue
                event_name = str(evt.get("event") or "").strip().lower()
                if event_name not in {"order_submitted", "entry_filled", "close"}:
                    continue
                order_id = str(evt.get("entry_order_id") or "").strip()
                if not order_id:
                    order_id = "|".join(
                        [
                            str(evt.get("symbol") or ""),
                            str(evt.get("strategy") or ""),
                            str(evt.get("side") or ""),
                            str(evt.get("ts") or ""),
                        ]
                    )
                rec = buckets.setdefault(order_id, {})
                rec.update({k: v for k, v in evt.items() if v not in (None, "")})
                if event_name == "order_submitted":
                    rec.setdefault("entry_ts", int(evt.get("ts") or 0))
                elif event_name == "entry_filled":
                    rec["entry_ts"] = int(evt.get("ts") or rec.get("entry_ts") or 0)
                elif event_name == "close":
                    rec["exit_ts"] = int(evt.get("ts") or 0)
            for rec in buckets.values():
                if not rec.get("exit_ts"):
                    continue
                side_raw = str(rec.get("side") or "").strip().lower()
                side = "short" if side_raw in {"sell", "short"} else "long"
                entry_ts = int(rec.get("entry_ts") or 0)
                exit_ts = int(rec.get("exit_ts") or 0)
                entry_notional = float(rec.get("entry_notional_usd") or 0.0)
                pnl = float(rec.get("pnl") or 0.0)
                trades.append({
                    "strategy": str(rec.get("strategy") or ""),
                    "symbol": str(rec.get("symbol") or "").upper(),
                    "side": side,
                    "open_time": datetime.fromtimestamp(entry_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if entry_ts else "",
                    "close_time": datetime.fromtimestamp(exit_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if exit_ts else "",
                    "entry": float(rec.get("entry_price") or 0.0),
                    "exit": float(rec.get("exit_price") or 0.0),
                    "pnl": pnl,
                    "fees": float(rec.get("fees") or 0.0),
                    "pnl_pct": (pnl / entry_notional * 100.0) if entry_notional > 0 else None,
                })
        except Exception:
            pass
    return trades


@router.get("/stats/daily")
async def daily_stats(_: str = Depends(require_admin)):
    """P&L aggregated by day + strategy breakdown per day."""
    trades = _load_all_trades()

    by_day: Dict[str, dict] = defaultdict(lambda: {
        "date": "",
        "net": 0.0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "by_strategy": defaultdict(float),
    })

    for t in trades:
        pnl = t.get("pnl")
        if not isinstance(pnl, float):
            continue
        # Get date from close_time or time
        raw_time = t.get("close_time") or t.get("time") or ""
        date = str(raw_time)[:10]
        if not date or date == "":
            continue

        rec = by_day[date]
        rec["date"] = date
        rec["net"] = round(rec["net"] + pnl, 6)
        rec["trades"] += 1
        if pnl > 0:
            rec["wins"] += 1
        elif pnl < 0:
            rec["losses"] += 1
        strat = t.get("strategy", "unknown")
        rec["by_strategy"][strat] = round(rec["by_strategy"][strat] + pnl, 6)

    # Convert to list, sort by date
    result = []
    running = 0.0
    for date in sorted(by_day.keys()):
        rec = by_day[date]
        running = round(running + rec["net"], 6)
        result.append({
            "date": date,
            "net": round(rec["net"], 4),
            "cumulative": round(running, 4),
            "trades": rec["trades"],
            "wins": rec["wins"],
            "losses": rec["losses"],
            "by_strategy": dict(rec["by_strategy"]),
        })

    return {
        "days": list(reversed(result)),  # newest first
        "total_days": len(result),
        "green_days": sum(1 for d in result if d["net"] > 0),
        "red_days": sum(1 for d in result if d["net"] < 0),
        "total_net": round(running, 4),
    }


@router.get("/stats/monthly")
async def monthly_stats(_: str = Depends(require_admin)):
    """P&L aggregated by month."""
    trades = _load_all_trades()

    by_month: Dict[str, dict] = defaultdict(lambda: {
        "month": "", "net": 0.0, "trades": 0, "wins": 0, "losses": 0,
    })

    for t in trades:
        pnl = t.get("pnl")
        if not isinstance(pnl, float):
            continue
        raw_time = t.get("close_time") or t.get("time") or ""
        month = str(raw_time)[:7]
        if not month:
            continue
        rec = by_month[month]
        rec["month"] = month
        rec["net"] = round(rec["net"] + pnl, 6)
        rec["trades"] += 1
        if pnl > 0:
            rec["wins"] += 1
        elif pnl < 0:
            rec["losses"] += 1

    result = [by_month[m] for m in sorted(by_month.keys())]
    running = 0.0
    for rec in result:
        running = round(running + rec["net"], 6)
        rec["cumulative"] = round(running, 4)

    return {"months": list(reversed(result))}


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit")
async def get_audit(_: str = Depends(require_admin)):
    """Web command audit log."""
    audit_path = _rt("web_audit_log.jsonl")
    if not audit_path.exists():
        return {"entries": []}
    entries = []
    for line in audit_path.read_text().splitlines()[-100:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return {"entries": list(reversed(entries))}


# ── Bybit API key rotation (NEW 2026-05-XX) ───────────────────────────────────
# Безопасная ротация без SSH+nano. Backup .env, замена key+secret, audit log.

_ENV_PATH = _ROOT / ".env"


class RotateBybitKeyRequest(BaseModel):
    account_name: str = "main"
    new_key: str
    new_secret: str
    confirm_phrase: str  # должен быть "ROTATE BYBIT KEY" — защита от случайного нажатия


def _backup_env(reason: str) -> Path:
    """Backup .env → state/env_backups/.env.<ts>.<reason>.bak. Returns backup path."""
    if not _ENV_PATH.exists():
        raise HTTPException(status_code=500, detail=".env file not found")
    backups_dir = _ROOT / "state" / "env_backups"
    backups_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        backups_dir.chmod(0o700)
    except OSError:
        pass
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bak = backups_dir / f".env.{ts}.{reason}.bak"
    bak.write_text(_ENV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        bak.chmod(0o600)
    except OSError:
        pass
    return bak


def _rotate_key_in_env(account_name: str, new_key: str, new_secret: str) -> Dict[str, Any]:
    """Replace key+secret in BYBIT_ACCOUNTS_JSON without exposing metadata."""
    import re

    text = _ENV_PATH.read_text(encoding="utf-8")
    # Find BYBIT_ACCOUNTS_JSON line
    m = re.search(r"^BYBIT_ACCOUNTS_JSON=(.+)$", text, re.MULTILINE)
    if not m:
        raise HTTPException(status_code=500, detail="BYBIT_ACCOUNTS_JSON not found in .env")
    raw_json = m.group(1).strip()
    try:
        accounts = json.loads(raw_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"BYBIT_ACCOUNTS_JSON parse error: {e}")

    if not isinstance(accounts, list):
        raise HTTPException(status_code=500, detail="BYBIT_ACCOUNTS_JSON must be a list")

    target = None
    for acc in accounts:
        if isinstance(acc, dict) and acc.get("name") == account_name:
            target = acc
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"Account '{account_name}' not found")

    target["key"] = new_key
    target["secret"] = new_secret

    new_json = json.dumps(accounts, separators=(",", ":"))
    new_text = re.sub(
        r"^BYBIT_ACCOUNTS_JSON=.+$",
        f"BYBIT_ACCOUNTS_JSON={new_json}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    _ENV_PATH.write_text(new_text, encoding="utf-8")
    try:
        _ENV_PATH.chmod(0o600)
    except OSError:
        pass
    return {"account": account_name, "configured": True}


def _audit_rotate(email: str, account: str) -> None:
    audit_path = _rt("web_audit_log.jsonl")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": email,
        "action": "rotate_bybit_key",
        "params": {"account": account},
        "result": "credentials replaced; protected backup created; restart required",
    }
    try:
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


@router.post("/rotate-bybit-key")
async def rotate_bybit_key(body: RotateBybitKeyRequest, email: str = Depends(require_admin)):
    """Безопасная ротация Bybit API key через web UI.

    Шаги:
      1. Validate confirm_phrase (защита от accident click).
      2. Backup .env → state/env_backups/.env.<ts>.bybit_key_rotate.bak.
      3. Replace key+secret в BYBIT_ACCOUNTS_JSON для указанного account_name.
      4. Audit log в runtime/web_audit_log.jsonl.
      5. Возвращает только статус + need_restart=True (бот должен перечитать .env).

    Бот сам не перезагружается — это решает админ через systemctl restart
    bybot.service либо через /api/admin/reload-bot endpoint (если есть).
    """
    if body.confirm_phrase != "ROTATE BYBIT KEY":
        raise HTTPException(status_code=400, detail="confirm_phrase must be 'ROTATE BYBIT KEY'")
    if not body.new_key or not body.new_secret:
        raise HTTPException(status_code=400, detail="new_key and new_secret required")
    if len(body.new_key) < 12 or len(body.new_secret) < 20:
        raise HTTPException(status_code=400, detail="key/secret look too short")

    # 1. Backup
    _backup_env("bybit_key_rotate")

    # 2. Rotate
    info = _rotate_key_in_env(body.account_name, body.new_key, body.new_secret)

    # 3. Audit
    _audit_rotate(email, info["account"])

    return {
        "status": "ok",
        "account": info["account"],
        "configured": info["configured"],
        "credential_values_returned": False,
        "protected_backup_created": True,
        "need_restart": True,
        "restart_command": "systemctl restart bybot.service",
        "next_steps": [
            "Run `systemctl restart bybot.service` on the server",
            "Check `journalctl -u bybot.service -n 20 --no-pager` for AUTH FAIL",
            "If no auth errors — rotation successful",
        ],
    }


@router.get("/bybit-key-info")
async def get_bybit_key_info(_: str = Depends(require_admin)):
    """Return account configuration status without credential fragments."""
    if not _ENV_PATH.exists():
        return {"accounts": []}
    text = _ENV_PATH.read_text(encoding="utf-8")
    import re
    m = re.search(r"^BYBIT_ACCOUNTS_JSON=(.+)$", text, re.MULTILINE)
    if not m:
        return {"accounts": [], "error": "BYBIT_ACCOUNTS_JSON not found"}
    try:
        accounts = json.loads(m.group(1).strip())
    except Exception as e:
        return {"accounts": [], "error": f"parse error: {e}"}
    expiry_report: Dict[str, Any] = {}
    expiry_by_account: Dict[str, Dict[str, Any]] = {}
    status_path = _rt("bybit_api_key_expiry_status.json")
    if status_path.exists():
        try:
            expiry_report = json.loads(status_path.read_text(encoding="utf-8"))
            expiry_by_account = {
                str(row.get("name")): row
                for row in expiry_report.get("accounts", [])
                if isinstance(row, dict) and row.get("name")
            }
        except Exception:
            expiry_report = {}
    out = []
    for acc in accounts:
        if not isinstance(acc, dict): continue
        name = str(acc.get("name", "?"))
        out.append({
            "name": name,
            "configured": bool(acc.get("key") and acc.get("secret")),
            "trade_enabled": acc.get("trade", {}).get("enabled", False),
            "leverage": acc.get("trade", {}).get("leverage"),
            "risk_pct": acc.get("trade", {}).get("risk_pct"),
            "expiry": expiry_by_account.get(name, {"status": "unknown"}),
        })
    arb_status = _load_runtime_arb_account_status()
    arb_exchanges_status = arb_status.get("exchanges") or {}

    def _arb_exchange_row(name: str, env_keys: List[str], stage: str) -> Dict[str, Any]:
        status = arb_exchanges_status.get(name) if isinstance(arb_exchanges_status, dict) else None
        status = status if isinstance(status, dict) else {}
        configured_from_env = all(_env_text_value(text, key) for key in env_keys)
        configured_from_runtime = bool(status.get("ok")) or status.get("reason") not in {None, "missing_keys"}
        return {
            "name": name,
            "configured": bool(configured_from_env or configured_from_runtime),
            "role": "cross_exchange_funding",
            "stage": stage,
            "trading_enabled": False,
            "account_ok": bool(status.get("ok")),
            "equity_usdt": status.get("equity_usdt"),
            "available_usdt": status.get("available_usdt"),
            "reason": status.get("reason"),
            "status_source": "runtime/arb/exchange_account_status.json" if status else "env",
        }

    other_exchanges = [
        _arb_exchange_row("binance", ["BINANCE_API_KEY", "BINANCE_API_SECRET"], "readonly_balance_then_dry_run"),
        _arb_exchange_row("bitget", ["BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_API_PASSPHRASE"], "readonly_balance_then_dry_run"),
        _arb_exchange_row("mexc", ["MEXC_API_KEY", "MEXC_API_SECRET"], "optional_later"),
        _arb_exchange_row("okx", ["OKX_API_KEY", "OKX_API_SECRET"], "optional_later"),
    ]
    return {
        "accounts": out,
        "arb_exchanges": other_exchanges,
        "expiry_checked_at_utc": expiry_report.get("checked_at_utc"),
        "arb_status_checked_at_utc": arb_status.get("generated_at_utc"),
        "note": "Credential values and fragments are never returned by this endpoint.",
    }


# ── Bot restart endpoint (NEW 2026-05-XX) ─────────────────────────────────────
# Безопасный restart bybot.service через web после ротации ключей.
# Использует systemctl, нужен systemd-доступ юзера, под которым работает web.

class RestartBotRequest(BaseModel):
    confirm_phrase: str  # "RESTART BOT NOW"
    reason: str = "manual restart from web admin"


@router.post("/restart-bot")
async def restart_bot(body: RestartBotRequest, email: str = Depends(require_admin)):
    """Restart bybot.service через systemctl. Используется после ротации API key
    или экстренного фикса. Логирует в audit + отправляет TG (если configured).
    """
    if body.confirm_phrase != "RESTART BOT NOW":
        raise HTTPException(status_code=400, detail="confirm_phrase must be 'RESTART BOT NOW'")

    import subprocess
    audit_path = _rt("web_audit_log.jsonl")
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Try systemctl first
    cmd_results = []
    try:
        r = subprocess.run(
            ["systemctl", "restart", "bybot.service"],
            capture_output=True, text=True, timeout=30,
        )
        cmd_results.append({"cmd": "systemctl restart bybot.service", "rc": r.returncode,
                            "stderr": (r.stderr or "")[:200]})
        if r.returncode != 0:
            # 2. Fallback: send SIGTERM via pidfile (если systemctl недоступен)
            pidfile = _rt("bot.pid")
            if pidfile.exists():
                try:
                    pid = int(pidfile.read_text().strip())
                    subprocess.run(["kill", "-TERM", str(pid)], timeout=5)
                    cmd_results.append({"cmd": f"kill -TERM {pid}", "rc": 0, "note": "fallback"})
                except Exception as e2:
                    cmd_results.append({"cmd": "kill fallback", "rc": -1, "stderr": str(e2)[:200]})
    except subprocess.TimeoutExpired:
        cmd_results.append({"cmd": "systemctl restart", "rc": -1, "stderr": "timeout"})
    except Exception as e:
        cmd_results.append({"cmd": "systemctl restart", "rc": -1, "stderr": str(e)[:200]})

    # 3. Audit
    try:
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "user": email,
            "action": "restart_bot",
            "params": {"reason": body.reason},
            "result": json.dumps(cmd_results),
        }
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

    success = any(r.get("rc") == 0 for r in cmd_results)
    return {
        "status": "ok" if success else "error",
        "results": cmd_results,
        "next_steps": [
            "Wait 60-120 seconds for bot startup",
            "Check /api/status — heartbeat_age_sec should be < 120",
            "Check TG for 'AUTH FAIL' or 'Started' messages",
        ],
    }
