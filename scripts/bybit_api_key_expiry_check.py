#!/usr/bin/env python3
"""bybit_api_key_expiry_check.py — TG-алерт за 7/3/1 дней до истечения Bybit API key.

Использует Bybit endpoint /v5/user/query-api для получения expiration date ключа.
Шлёт TG-алерт когда осталось ≤7 дней (informational), ≤3 (warning) или ≤1 (CRITICAL).

Запуск (cron на сервере):
    # Каждые 6 часов:
    0 */6 * * * cd /root/by-bot && /root/by-bot/.venv/bin/python3 scripts/bybit_api_key_expiry_check.py >> logs/api_key_expiry.log 2>&1

Env:
    BYBIT_ACCOUNTS_JSON   — credentials (тот же что у бота)
    TG_TOKEN              — telegram bot token
    TG_CHAT_ID            — chat id для алертов
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "runtime" / "bybit_api_key_expiry_status.json"


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return str(v).strip() if v else default


def _load_dotenv_if_needed(path: Path = ROOT / ".env") -> None:
    """Load missing keys from .env without printing secret values."""
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            os.environ[key] = value
    except Exception as exc:
        print(f"ERROR: cannot load env file: {type(exc).__name__}")


def _tg_send(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        print(f"[TG SKIP no creds] {msg}")
        return
    try:
        payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
        req = request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"[TG ERROR] {e}: {msg}")


def _write_status(accounts: list[dict]) -> None:
    """Publish only safe monitoring metadata for web/operator views."""
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "accounts": accounts,
    }
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _query_api_info(key: str, secret: str, base: str) -> dict:
    """Bybit /v5/user/query-api — возвращает info об текущем API key включая expiredAt."""
    ts = str(int(time.time() * 1000))
    recv_window = "5000"
    qs = ""
    prehash = f"{ts}{key}{recv_window}{qs}"
    sign = hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-BAPI-API-KEY": key,
        "X-BAPI-SIGN": sign,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": recv_window,
    }
    url = f"{base.rstrip('/')}/v5/user/query-api"
    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {"retCode": e.code, "retMsg": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"retCode": -1, "retMsg": str(e)[:200]}


def main() -> int:
    _load_dotenv_if_needed()
    accs_json = _env("BYBIT_ACCOUNTS_JSON")
    if not accs_json:
        print("ERROR: BYBIT_ACCOUNTS_JSON not set in env")
        _write_status([{"status": "configuration_missing"}])
        return 1

    try:
        accs = json.loads(accs_json)
    except Exception as e:
        print(f"ERROR: bad BYBIT_ACCOUNTS_JSON: {e}")
        _write_status([{"status": "configuration_invalid"}])
        return 1

    tg_token = _env("TG_TOKEN")
    tg_chat = _env("TG_CHAT_ID") or _env("TG_CHAT")
    now_ms = int(time.time() * 1000)
    any_warn = False
    status_rows: list[dict] = []

    for acc in accs:
        name = acc.get("name", "?")
        key = acc.get("key", "")
        secret = acc.get("secret", "")
        base = acc.get("base", "https://api.bybit.com")
        if not key or not secret:
            status_rows.append({"name": name, "status": "credentials_missing"})
            continue

        info = _query_api_info(key, secret, base)
        rc = str(info.get("retCode"))

        if rc == "33004":
            msg = f"🚨 [CRITICAL] {name}: Bybit API key УЖЕ ИСТЁК (retCode 33004)\nБот не может торговать. Срочно ротация."
            print(msg)
            _tg_send(tg_token, tg_chat, msg)
            any_warn = True
            status_rows.append({"name": name, "status": "expired"})
            continue

        if rc != "0":
            msg = f"⚠️ {name}: query-api error retCode={rc} {info.get('retMsg','')[:100]}"
            print(msg)
            status_rows.append({"name": name, "status": "query_error", "ret_code": rc})
            continue

        result = info.get("result") or {}
        expired_at = result.get("expiredAt", "")
        # Bybit формат: "2026-08-01T00:00:00Z" или unix ms
        if not expired_at:
            print(f"[{name}] no expiredAt in response (forever-key?), skip")
            status_rows.append({"name": name, "status": "expiry_not_provided"})
            continue

        try:
            if isinstance(expired_at, (int, float)):
                exp_ms = int(expired_at) if expired_at > 1e12 else int(expired_at) * 1000
            else:
                # ISO date
                exp_dt = datetime.fromisoformat(str(expired_at).replace("Z", "+00:00"))
                exp_ms = int(exp_dt.timestamp() * 1000)
        except Exception:
            print(f"[{name}] unparseable expiredAt={expired_at}, skip")
            status_rows.append({"name": name, "status": "expiry_unparseable"})
            continue

        days_left = (exp_ms - now_ms) / 1000.0 / 86400.0
        expires_on = str(datetime.fromtimestamp(exp_ms / 1000, timezone.utc).date())
        severity = "ok"
        if days_left < 0:
            severity = "expired"
        elif days_left <= 1:
            severity = "critical"
        elif days_left <= 3:
            severity = "warning"
        elif days_left <= 7:
            severity = "notice"
        status_rows.append({
            "name": name,
            "status": severity,
            "days_left": round(days_left, 1),
            "expires_on": expires_on,
        })
        print(f"[{name}] API key expires in {days_left:.1f} days ({expires_on})")

        if days_left < 0:
            msg = f"🚨 [{name}] API key EXPIRED {-days_left:.1f}d ago. Bot cannot trade. Rotate now."
            _tg_send(tg_token, tg_chat, msg); any_warn = True
        elif days_left <= 1:
            msg = f"🚨 [CRITICAL] {name}: API key expires in {days_left:.1f}d. Rotate IMMEDIATELY."
            _tg_send(tg_token, tg_chat, msg); any_warn = True
        elif days_left <= 3:
            msg = f"⚠️ [WARN] {name}: API key expires in {days_left:.1f}d. Plan rotation."
            _tg_send(tg_token, tg_chat, msg); any_warn = True
        elif days_left <= 7:
            msg = f"ℹ️ [INFO] {name}: API key expires in {days_left:.1f}d. Schedule rotation soon."
            _tg_send(tg_token, tg_chat, msg); any_warn = True
        # > 7 days — silent

    _write_status(status_rows)
    return 0 if not any_warn else 0  # always exit 0 — это monitor, не fail


if __name__ == "__main__":
    sys.exit(main())
