#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    raw_accounts = env.get("BYBIT_ACCOUNTS_JSON") or ""
    if (not key or not secret) and raw_accounts:
        accounts = json.loads(raw_accounts)
        if accounts:
            acc = accounts[0]
            key = str(acc.get("key") or "")
            secret = str(acc.get("secret") or "")
            base = str(acc.get("base") or base)
    return key, secret, base


def _sign(secret: str, payload: str, timestamp: str, recv_window: str, api_key: str) -> str:
    return hmac.new(secret.encode(), (timestamp + api_key + recv_window + payload).encode(), hashlib.sha256).hexdigest()


def _request(method: str, base: str, key: str, secret: str, path: str, params_or_body: dict) -> dict:
    ts = str(int(time.time() * 1000))
    recv = "10000"
    if method == "GET":
        payload = urllib.parse.urlencode(sorted(params_or_body.items()))
        url = base.rstrip("/") + path + ("?" + payload if payload else "")
        data = None
    else:
        payload = json.dumps(params_or_body, separators=(",", ":"))
        url = base.rstrip("/") + path
        data = payload.encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "X-BAPI-API-KEY": key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv,
            "X-BAPI-SIGN": _sign(secret, payload, ts, recv, key),
            "Content-Type": "application/json",
            "User-Agent": "by-bot-emergency-sl/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--pct", type=float, default=1.0, help="Emergency SL distance from avg entry, percent.")
    args = ap.parse_args()

    env = {**os.environ, **_load_env(ROOT / ".env")}
    key, secret, base = _first_bybit_account(env)
    if not key or not secret:
        print(json.dumps({"ok": False, "error": "missing_bybit_credentials"}))
        return 2

    symbol = args.symbol.upper()
    data = _request("GET", base, key, secret, "/v5/position/list", {"category": "linear", "symbol": symbol})
    positions = (((data or {}).get("result") or {}).get("list") or [])
    active = None
    for pos in positions:
        try:
            size = abs(float(pos.get("size") or 0.0))
        except Exception:
            size = 0.0
        if size > 0:
            active = pos
            break
    if not active:
        print(json.dumps({"ok": True, "symbol": symbol, "action": "no_position"}))
        return 0

    side = str(active.get("side") or "")
    avg = float(active.get("avgPrice") or 0.0)
    if avg <= 0:
        print(json.dumps({"ok": False, "symbol": symbol, "error": "missing_avg_price"}))
        return 1
    pct = max(0.1, float(args.pct)) / 100.0
    if side == "Sell":
        stop = avg * (1.0 + pct)
    else:
        stop = avg * (1.0 - pct)

    body = {
        "category": "linear",
        "symbol": symbol,
        "tpslMode": "Full",
        "slTriggerBy": "LastPrice",
        "stopLoss": f"{stop:.1f}" if symbol == "BTCUSDT" else f"{stop:.6f}",
    }
    pidx = active.get("positionIdx")
    if pidx not in (None, "", "0", 0):
        body["positionIdx"] = int(pidx)

    resp = _request("POST", base, key, secret, "/v5/position/trading-stop", body)
    print(
        json.dumps(
            {
                "ok": resp.get("retCode") == 0,
                "retCode": resp.get("retCode"),
                "retMsg": resp.get("retMsg"),
                "symbol": symbol,
                "side": side,
                "size": active.get("size"),
                "avgPrice": active.get("avgPrice"),
                "stopLoss": body["stopLoss"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if resp.get("retCode") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
