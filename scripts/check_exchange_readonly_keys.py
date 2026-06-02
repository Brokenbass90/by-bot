#!/usr/bin/env python3
"""Check read-only exchange keys without printing secrets.

This is a pre-live safety check for cross-exchange funding/arb research:
- verifies Binance USDT-M futures account read access;
- verifies Bitget USDT futures account read access when keys are present;
- writes a redacted status JSON for the web/AI context.

It never places orders and never returns key fragments.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _json_request(url: str, *, headers: dict[str, str] | None = None, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "by-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _safe_error(exc: Exception) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message": str(exc)[:500],
    }


def check_binance(env: dict[str, str]) -> dict[str, Any]:
    key = env.get("BINANCE_API_KEY", "").strip()
    secret = env.get("BINANCE_API_SECRET", "").strip()
    if not key or not secret:
        return {"configured": False, "ok": False, "reason": "missing_key"}
    try:
        params = {
            "timestamp": str(int(time.time() * 1000)),
            "recvWindow": "5000",
        }
        query = urllib.parse.urlencode(params)
        sig = hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        url = f"https://fapi.binance.com/fapi/v2/balance?{query}&signature={sig}"
        data = _json_request(url, headers={"User-Agent": "by-bot/1.0", "X-MBX-APIKEY": key})
        balances = data if isinstance(data, list) else []
        usdt = next((row for row in balances if row.get("asset") == "USDT"), {})
        return {
            "configured": True,
            "ok": True,
            "scope": "binance_usdt_m_futures_balance_read",
            "assets_count": len(balances),
            "usdt_balance": {
                "balance": _round_str(usdt.get("balance")),
                "available_balance": _round_str(usdt.get("availableBalance")),
                "cross_un_pnl": _round_str(usdt.get("crossUnPnl")),
            },
        }
    except Exception as exc:
        return {
            "configured": True,
            "ok": False,
            "scope": "binance_usdt_m_futures_balance_read",
            "error": _safe_error(exc),
        }


def _round_str(value: Any) -> str | None:
    try:
        return f"{float(value):.4f}"
    except Exception:
        return None


def check_bitget(env: dict[str, str]) -> dict[str, Any]:
    key = env.get("BITGET_API_KEY", "").strip()
    secret = env.get("BITGET_API_SECRET", "").strip()
    passphrase = env.get("BITGET_API_PASSPHRASE", "").strip()
    if not key or not secret or not passphrase:
        return {"configured": bool(key or secret or passphrase), "ok": False, "reason": "missing_key_or_passphrase"}
    try:
        ts = str(int(time.time() * 1000))
        method = "GET"
        request_path = "/api/v2/mix/account/accounts"
        query = "?productType=USDT-FUTURES"
        prehash = f"{ts}{method}{request_path}{query}"
        sign = base64.b64encode(
            hmac.new(secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).digest()
        ).decode("utf-8")
        headers = {
            "User-Agent": "by-bot/1.0",
            "ACCESS-KEY": key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-PASSPHRASE": passphrase,
        }
        url = f"https://api.bitget.com{request_path}{query}"
        data = _json_request(url, headers=headers)
        rows = data.get("data") if isinstance(data, dict) else []
        if not isinstance(rows, list):
            rows = []
        usdt = next((row for row in rows if str(row.get("marginCoin", "")).upper() == "USDT"), {})
        ok = bool(isinstance(data, dict) and str(data.get("code", "")) in {"00000", "0"})
        return {
            "configured": True,
            "ok": ok,
            "scope": "bitget_usdt_futures_account_read",
            "code": data.get("code") if isinstance(data, dict) else None,
            "msg": data.get("msg") if isinstance(data, dict) else None,
            "accounts_count": len(rows),
            "usdt_account": {
                "available": _round_str(usdt.get("available")),
                "equity": _round_str(usdt.get("accountEquity") or usdt.get("equity")),
                "unrealized_pl": _round_str(usdt.get("unrealizedPL")),
            },
        }
    except Exception as exc:
        return {
            "configured": True,
            "ok": False,
            "scope": "bitget_usdt_futures_account_read",
            "error": _safe_error(exc),
        }


def main() -> int:
    ap = argparse.ArgumentParser(description="Check Binance/Bitget read-only keys without printing secrets.")
    ap.add_argument("--env", default=".env")
    ap.add_argument("--out-json", default="runtime/arb/exchange_account_readonly_status.json")
    args = ap.parse_args()

    env = _load_env(ROOT / args.env)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "No secrets or key fragments are included.",
        "binance": check_binance(env),
        "bitget": check_bitget(env),
    }
    out = ROOT / args.out_json
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["binance"].get("ok") and (not payload["bitget"].get("configured") or payload["bitget"].get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

