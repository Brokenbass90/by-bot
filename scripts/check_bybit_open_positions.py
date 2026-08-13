#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> dict[str, str]:
    vals: dict[str, str] = {}
    if not path.exists():
        return vals
    for raw in path.read_text(errors="ignore").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, val = raw.split("=", 1)
        vals[key.strip()] = val.strip().strip("'\"")
    return vals


def _first_bybit_account(env: dict[str, str]) -> tuple[str, str, str]:
    key = env.get("BYBIT_API_KEY") or env.get("BYBIT_KEY") or ""
    secret = env.get("BYBIT_API_SECRET") or env.get("BYBIT_SECRET") or ""
    base = env.get("BYBIT_BASE_URL") or env.get("BYBIT_BASE") or "https://api.bybit.com"
    if key and secret:
        return key, secret, base

    raw_accounts = env.get("BYBIT_ACCOUNTS_JSON") or ""
    if raw_accounts:
        accounts = json.loads(raw_accounts)
        if accounts:
            acc = accounts[0]
            return str(acc.get("key") or ""), str(acc.get("secret") or ""), str(acc.get("base") or base)
    return "", "", base


def _bybit_get(base: str, key: str, secret: str, path: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(sorted(params.items()))
    ts = str(int(time.time() * 1000))
    recv_window = "10000"
    signature = hmac.new(
        secret.encode(),
        (ts + key + recv_window + query).encode(),
        hashlib.sha256,
    ).hexdigest()
    url = base.rstrip("/") + path + ("?" + query if query else "")
    req = urllib.request.Request(
        url,
        headers={
            "X-BAPI-API-KEY": key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv_window,
            "X-BAPI-SIGN": signature,
            "User-Agent": "by-bot-position-check/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _position_snapshot(data: dict) -> dict:
    ret_code = data.get("retCode")
    if ret_code != 0:
        return {
            "retCode": ret_code,
            "retMsg": data.get("retMsg"),
            "broker_state": "NOT_CONFIRMED",
            "open_position_count": None,
            "positions": None,
        }

    rows = []
    for pos in (((data or {}).get("result") or {}).get("list") or []):
        try:
            size = abs(float(pos.get("size") or 0.0))
        except Exception:
            size = 0.0
        if size <= 0:
            continue
        rows.append(
            {
                "symbol": pos.get("symbol"),
                "side": pos.get("side"),
                "size": size,
                "avgPrice": pos.get("avgPrice"),
                "unrealisedPnl": pos.get("unrealisedPnl"),
                "takeProfit": pos.get("takeProfit"),
                "stopLoss": pos.get("stopLoss"),
            }
        )
    return {
        "retCode": ret_code,
        "retMsg": data.get("retMsg"),
        "broker_state": "CONFIRMED",
        "open_position_count": len(rows),
        "positions": rows,
    }


def main() -> int:
    env = {**os.environ, **_load_env(ROOT / ".env")}
    key, secret, base = _first_bybit_account(env)
    if not key or not secret:
        print(json.dumps({"error": "missing_bybit_credentials", "broker_state": "NOT_CONFIRMED"}))
        return 2

    data = _bybit_get(
        base,
        key,
        secret,
        "/v5/position/list",
        {"category": "linear", "settleCoin": "USDT"},
    )
    print(json.dumps(_position_snapshot(data), ensure_ascii=False))
    return 0 if data.get("retCode") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
