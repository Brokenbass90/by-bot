#!/usr/bin/env python3
"""validate_bybit_keys.py — быстрая проверка ключей Bybit перед заливкой на сервер.

Запуск:
    cd ~/Documents/Work/bot-new/bybit-bot-clean-v28
    source .venv/bin/activate
    python3 scripts/validate_bybit_keys.py

Скрипт:
    1. Читает BYBIT_ACCOUNTS_JSON из локального .env
    2. Для каждого аккаунта пробует /v5/account/wallet-balance
    3. Печатает PASS / FAIL с понятным сообщением
    4. Если есть невидимые символы (пробелы, \\n) в key/secret — алертит

Если PASS — можно безопасно заливать на сервер.
Если FAIL — фиксишь и пробуешь снова локально, не трогая сервер.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from urllib import error, request


def _read_env_file(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _check_for_invisible(s: str, label: str) -> list:
    issues = []
    if s != s.strip():
        issues.append(f"{label}: содержит leading/trailing whitespace")
    if "\n" in s or "\r" in s:
        issues.append(f"{label}: содержит перенос строки")
    if "\t" in s:
        issues.append(f"{label}: содержит tab")
    if " " in s:
        issues.append(f"{label}: содержит пробел внутри")
    # Common typo: copied from "Show" button сразу с скобками
    for ch in "<>[]{}()":
        if ch in s:
            issues.append(f"{label}: содержит подозрительный символ '{ch}' (скорее всего скопировал лишнее)")
    return issues


def _bybit_check_auth(key: str, secret: str, base: str) -> dict:
    """Calls /v5/account/wallet-balance. Returns dict with status."""
    ts = str(int(time.time() * 1000))
    recv = "5000"
    qs = "accountType=UNIFIED"
    prehash = f"{ts}{key}{recv}{qs}"
    sign = hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-BAPI-API-KEY": key,
        "X-BAPI-SIGN": sign,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": recv,
    }
    url = f"{base.rstrip('/')}/v5/account/wallet-balance?{qs}"
    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        return {"http": 200, "retCode": str(data.get("retCode")), "retMsg": data.get("retMsg", "")}
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {"http": e.code, "retCode": "?", "retMsg": body[:200]}
    except Exception as e:
        return {"http": -1, "retCode": "?", "retMsg": str(e)[:200]}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    env = _read_env_file(env_path)

    accs_raw = env.get("BYBIT_ACCOUNTS_JSON", "")
    if not accs_raw:
        print(f"❌ BYBIT_ACCOUNTS_JSON not found in {env_path}")
        return 1

    try:
        accs = json.loads(accs_raw)
    except Exception as e:
        print(f"❌ BYBIT_ACCOUNTS_JSON invalid JSON: {e}")
        print(f"   raw[:200] = {accs_raw[:200]}")
        return 1

    overall_ok = True

    for acc in accs:
        name = acc.get("name", "?")
        key = acc.get("key", "")
        secret = acc.get("secret", "")
        base = acc.get("base", "https://api.bybit.com")

        print(f"\n=== Account: {name} ===")
        print(f"  key length: {len(key)}  | prefix: {key[:6]}... | suffix: ...{key[-4:]}")
        print(f"  secret length: {len(secret)}  | prefix: {secret[:6]}... | suffix: ...{secret[-4:]}")
        print(f"  base: {base}")

        # 1. Visible string sanity
        issues = _check_for_invisible(key, "key") + _check_for_invisible(secret, "secret")
        if issues:
            print("  ⚠️ ВНИМАНИЕ — найдены подозрительные символы:")
            for iss in issues:
                print(f"     - {iss}")
            print("     Перепроверь .env файл: открой через nano/VS Code и убедись что")
            print("     key и secret в одной строке без пробелов/переносов.")
            overall_ok = False

        if not key or not secret:
            print(f"  ❌ FAIL: key или secret пустые")
            overall_ok = False
            continue

        if len(key) < 12:
            print(f"  ⚠️  key подозрительно короткий ({len(key)} chars). Bybit обычно 18-20.")
        if len(secret) < 30:
            print(f"  ⚠️  secret подозрительно короткий ({len(secret)} chars). Bybit обычно 36-40.")

        # 2. Real API check
        print(f"  → Calling Bybit /v5/account/wallet-balance ...")
        r = _bybit_check_auth(key, secret, base)
        rc = r["retCode"]
        msg = r["retMsg"]

        if rc == "0":
            print(f"  ✅ PASS — auth работает! Можно заливать на сервер.")
        elif rc == "10004":
            print(f"  ❌ FAIL: 10004 'Error sign' — secret НЕПРАВИЛЬНЫЙ")
            print(f"     Возможно: неполный secret скопировался, лишний символ, или secret от другого ключа.")
            print(f"     Решение: создай НОВЫЙ key+secret на Bybit, скопируй в .env.")
            overall_ok = False
        elif rc == "33004":
            print(f"  ❌ FAIL: 33004 'API key has expired' — ключ протух. Создай новый.")
            overall_ok = False
        elif rc in ("10003", "10002"):
            print(f"  ❌ FAIL: {rc} '{msg}' — invalid API key или IP not whitelisted.")
            print(f"     Проверь: ключ существует на Bybit И IP-whitelist разрешает твой IP.")
            overall_ok = False
        else:
            print(f"  ❌ FAIL: HTTP {r['http']} retCode={rc} retMsg={msg}")
            overall_ok = False

    print()
    if overall_ok:
        print("✅✅✅ ВСЕ АККАУНТЫ ПРОВЕРЕНЫ — auth работает.")
        print("Теперь безопасно: scp .env root@64.226.73.119:/root/by-bot/.env")
        return 0
    else:
        print("❌❌❌ ЕСТЬ ПРОБЛЕМЫ — НЕ заливай на сервер пока не починишь.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
