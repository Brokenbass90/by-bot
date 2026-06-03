#!/usr/bin/env python3
"""Read-only multi-exchange account status helper.

Polls Bybit + Binance + Bitget account endpoints with read-only API keys
and writes a single consolidated snapshot to
`runtime/arb/exchange_account_status.json`. No orders, no writes to any exchange,
no withdrawal calls. Cron every 5 minutes.

Per-exchange keys are read from environment variables (server `.env` only):

    BYBIT_API_KEY / BYBIT_API_SECRET                  (already used by bot)
    BINANCE_API_KEY / BINANCE_API_SECRET
    BITGET_API_KEY / BITGET_API_SECRET / BITGET_API_PASSPHRASE
    MEXC_API_KEY   / MEXC_API_SECRET                          (added 2026-06-03)

If any of the keys is missing, that exchange is reported with ok=false and a
reason="missing_keys". The script never fails the whole run because of one
missing exchange — partial data is still useful for the AI context.

This script intentionally does NOT print or log any secret material. All
credentials stay inside the signed-request preparation and are scrubbed from
exception messages.

Author: Claude Opus, 2026-06-02. Read-only, no orders.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import sys
import time
import urllib.parse
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "arb" / "exchange_account_status.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE lines without printing secrets."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _f(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _http_get(url: str, *, headers: dict[str, str] | None = None, timeout: float = 12.0) -> Any:
    req = request.Request(url, headers=headers or {})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            body = ""
        raise RuntimeError(f"http_{exc.code} {body}") from None
    except Exception as exc:
        raise RuntimeError(f"http_error {type(exc).__name__}") from None


# ---------------------------------------------------------------------------
# Binance — futures
# ---------------------------------------------------------------------------

BINANCE_FAPI = "https://fapi.binance.com"


def _binance_signed(path: str, key: str, secret: str, params: dict[str, Any] | None = None) -> Any:
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 5000
    query = urllib.parse.urlencode(params, doseq=True)
    sig = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f"{BINANCE_FAPI}{path}?{query}&signature={sig}"
    return _http_get(url, headers={"X-MBX-APIKEY": key})


def fetch_binance() -> dict[str, Any]:
    key = (os.getenv("BINANCE_API_KEY") or "").strip()
    secret = (os.getenv("BINANCE_API_SECRET") or "").strip()
    if not (key and secret):
        return {"ok": False, "reason": "missing_keys"}
    try:
        acct = _binance_signed("/fapi/v2/account", key, secret)
    except RuntimeError as exc:
        return {"ok": False, "reason": str(exc)}
    if not isinstance(acct, dict):
        return {"ok": False, "reason": "bad_response_shape"}

    total_wallet = _f(acct.get("totalWalletBalance"))
    total_margin = _f(acct.get("totalMarginBalance"))
    available = _f(acct.get("availableBalance"))
    can_trade = bool(acct.get("canTrade"))
    can_withdraw = bool(acct.get("canWithdraw"))
    can_deposit = bool(acct.get("canDeposit"))

    return {
        "ok": True,
        "equity_usdt": round(total_margin, 4),
        "wallet_usdt": round(total_wallet, 4),
        "available_usdt": round(available, 4),
        "permissions": {
            "api_key_scope": "read_only_balance_check_only",
            "account_can_trade_flag": can_trade,
            "account_can_withdraw_flag": can_withdraw,
            "account_can_deposit_flag": can_deposit,
        },
    }


# ---------------------------------------------------------------------------
# Bitget — USDT-M perpetuals
# ---------------------------------------------------------------------------

BITGET_REST = "https://api.bitget.com"


def _bitget_signed(path: str, key: str, secret: str, passphrase: str) -> Any:
    ts = str(int(time.time() * 1000))
    body = ""  # GET, no body
    prehash = f"{ts}GET{path}{body}"
    sign = b64encode(hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()).decode()
    headers = {
        "ACCESS-KEY": key,
        "ACCESS-SIGN": sign,
        "ACCESS-TIMESTAMP": ts,
        "ACCESS-PASSPHRASE": passphrase,
        "Content-Type": "application/json",
    }
    return _http_get(f"{BITGET_REST}{path}", headers=headers)


def fetch_bitget() -> dict[str, Any]:
    key = (os.getenv("BITGET_API_KEY") or "").strip()
    secret = (os.getenv("BITGET_API_SECRET") or "").strip()
    passphrase = (os.getenv("BITGET_API_PASSPHRASE") or "").strip()
    if not (key and secret and passphrase):
        return {"ok": False, "reason": "missing_keys"}

    path = "/api/v2/mix/account/accounts?productType=USDT-FUTURES"
    try:
        body = _bitget_signed(path, key, secret, passphrase)
    except RuntimeError as exc:
        return {"ok": False, "reason": str(exc)}

    if not isinstance(body, dict) or str(body.get("code") or "") not in {"0", "00000"}:
        return {"ok": False, "reason": f"api_error code={body.get('code') if isinstance(body, dict) else 'n/a'}"}

    rows = body.get("data") or []
    usdt = next((r for r in rows if str(r.get("marginCoin") or "").upper() == "USDT"), None)
    if usdt is None:
        return {"ok": True, "equity_usdt": 0.0, "available_usdt": 0.0, "permissions": {}}

    return {
        "ok": True,
        "equity_usdt": round(_f(usdt.get("equity") or usdt.get("accountEquity")), 4),
        "available_usdt": round(_f(usdt.get("available") or usdt.get("crossMaxAvailable")), 4),
        "permissions": {
            "api_key_scope": "read_only_balance_check_only",
            "account_can_trade_flag": None,
            "account_can_withdraw_flag": None,
        },
    }


# ---------------------------------------------------------------------------
# MEXC — USDT-M perpetual futures
# ---------------------------------------------------------------------------

MEXC_FAPI = "https://contract.mexc.com"


def _mexc_signed_get(path: str, key: str, secret: str, params: dict[str, Any] | None = None) -> Any:
    params = dict(params or {})
    ts = str(int(time.time() * 1000))
    param_str = urllib.parse.urlencode(sorted(params.items())) if params else ""
    # MEXC futures signature: HMAC_SHA256(secret, apiKey + timestamp + paramStr)
    sign_src = f"{key}{ts}{param_str}"
    sign = hmac.new(secret.encode(), sign_src.encode(), hashlib.sha256).hexdigest()
    url = f"{MEXC_FAPI}{path}" + (f"?{param_str}" if param_str else "")
    headers = {
        "ApiKey": key,
        "Request-Time": ts,
        "Signature": sign,
        "Content-Type": "application/json",
    }
    return _http_get(url, headers=headers)


def fetch_mexc() -> dict[str, Any]:
    key = (os.getenv("MEXC_API_KEY") or "").strip()
    secret = (os.getenv("MEXC_API_SECRET") or "").strip()
    if not (key and secret):
        return {"ok": False, "reason": "missing_keys"}

    try:
        body = _mexc_signed_get("/api/v1/private/account/assets", key, secret)
    except RuntimeError as exc:
        return {"ok": False, "reason": str(exc)}

    if not isinstance(body, dict) or not body.get("success", False):
        msg = body.get("message") if isinstance(body, dict) else "bad_response_shape"
        return {"ok": False, "reason": f"api_error: {msg}"}

    rows = body.get("data") or []
    usdt = next((r for r in rows if str(r.get("currency") or "").upper() == "USDT"), None)
    if usdt is None:
        return {"ok": True, "equity_usdt": 0.0, "available_usdt": 0.0, "permissions": {}}

    return {
        "ok": True,
        "equity_usdt": round(_f(usdt.get("equity")), 4),
        "available_usdt": round(_f(usdt.get("availableBalance") or usdt.get("availableCash")), 4),
        "permissions": {
            "api_key_scope": "read_only_balance_check_only",
            "account_can_trade_flag": None,
            "account_can_withdraw_flag": None,
        },
    }


# ---------------------------------------------------------------------------
# Bybit — v5 unified
# ---------------------------------------------------------------------------

BYBIT_REST = "https://api.bybit.com"


def _bybit_signed(path: str, key: str, secret: str, params: dict[str, Any] | None = None) -> Any:
    params = dict(params or {})
    ts = str(int(time.time() * 1000))
    recv = "5000"
    query = urllib.parse.urlencode(params, doseq=True) if params else ""
    sign_payload = f"{ts}{key}{recv}{query}"
    sign = hmac.new(secret.encode(), sign_payload.encode(), hashlib.sha256).hexdigest()
    url = f"{BYBIT_REST}{path}" + (f"?{query}" if query else "")
    headers = {
        "X-BAPI-API-KEY": key,
        "X-BAPI-TIMESTAMP": ts,
        "X-BAPI-RECV-WINDOW": recv,
        "X-BAPI-SIGN": sign,
    }
    return _http_get(url, headers=headers)


def _bybit_keys(account_name: str = "main") -> tuple[str, str]:
    raw = (os.getenv("BYBIT_ACCOUNTS_JSON") or "").strip()
    if raw:
        try:
            accounts = json.loads(raw)
            if isinstance(accounts, list):
                target = next(
                    (a for a in accounts if isinstance(a, dict) and a.get("name") == account_name),
                    accounts[0] if accounts else None,
                )
                if isinstance(target, dict):
                    return str(target.get("key") or ""), str(target.get("secret") or "")
        except Exception:
            pass
    return (os.getenv("BYBIT_API_KEY") or "").strip(), (os.getenv("BYBIT_API_SECRET") or "").strip()


def fetch_bybit(account_name: str = "main") -> dict[str, Any]:
    key, secret = _bybit_keys(account_name)
    if not (key and secret):
        return {"ok": False, "reason": "missing_keys"}

    try:
        body = _bybit_signed("/v5/account/wallet-balance", key, secret, {"accountType": "UNIFIED"})
    except RuntimeError as exc:
        return {"ok": False, "reason": str(exc)}

    if not isinstance(body, dict) or int(body.get("retCode", -1)) != 0:
        return {"ok": False, "reason": f"api_error code={body.get('retCode') if isinstance(body, dict) else 'n/a'}"}

    result = body.get("result") or {}
    rows = result.get("list") or []
    if not rows:
        return {"ok": True, "equity_usdt": 0.0, "available_usdt": 0.0}

    acct = rows[0] or {}
    equity = _f(acct.get("totalEquity"))
    available = _f(acct.get("totalAvailableBalance"))
    return {
        "ok": True,
        "equity_usdt": round(equity, 4),
        "available_usdt": round(available, 4),
        "permissions": {
            "api_key_scope": "existing_bybit_bot_key_balance_check_only",
            "account_can_trade_flag": None,
            "account_can_withdraw_flag": None,
        },
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _load_validated_pairs() -> list[dict[str, Any]]:
    paths = [
        ROOT / "runtime" / "arb" / "cross_exchange_funding_validated.json",
        ROOT / "runtime" / "cross_exchange_funding_validated.json",
    ]
    p = next((candidate for candidate in paths if candidate.exists()), None)
    if p is None:
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        return list(data.get("items") or data.get("pairs") or data.get("validated") or [])
    if isinstance(data, list):
        return data
    return []


def _readiness_summary(
    exchanges: dict[str, dict[str, Any]],
    pairs: list[dict[str, Any]],
    min_leg_usdt: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pair in pairs:
        sym = str(pair.get("symbol") or "").upper()
        long_exch = str(pair.get("exchange_long") or pair.get("long_exchange") or "").lower()
        short_exch = str(pair.get("exchange_short") or pair.get("short_exchange") or "").lower()
        if not sym or not long_exch or not short_exch:
            continue
        long_ok = exchanges.get(long_exch, {}).get("ok") and _f(exchanges[long_exch].get("available_usdt")) >= min_leg_usdt
        short_ok = exchanges.get(short_exch, {}).get("ok") and _f(exchanges[short_exch].get("available_usdt")) >= min_leg_usdt
        out.append({
            "symbol": sym,
            "exchange_long": long_exch,
            "exchange_short": short_exch,
            "long_funds_ok": bool(long_ok),
            "short_funds_ok": bool(short_ok),
        "expected_apr_pct": _f(pair.get("apr_pct") or pair.get("expected_apr_pct") or pair.get("spread_apr_pct")),
        "estimated_net_pct_for_hold": _f(pair.get("estimated_net_pct_for_hold")),
        "notional_usd_per_leg": _f(pair.get("notional_usd_per_leg")),
        "ready_for_dry_run": bool(long_ok and short_ok),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only multi-exchange account status snapshot")
    ap.add_argument("--out", default=str(OUT), help="Output JSON path")
    ap.add_argument("--env", default=str(ROOT / ".env"), help="Optional .env file to load without printing secrets")
    ap.add_argument("--min-leg-usdt", type=float, default=100.0, help="Min available per leg to mark ready")
    ap.add_argument("--quiet", action="store_true", help="Suppress stdout summary")
    args = ap.parse_args()

    _load_env_file(Path(args.env))

    exchanges = {
        "bybit": fetch_bybit(account_name="main"),
        "binance": fetch_binance(),
        "bitget": fetch_bitget(),
        "mexc": fetch_mexc(),
    }
    pairs = _load_validated_pairs()
    readiness = _readiness_summary(exchanges, pairs, args.min_leg_usdt)

    snapshot = {
        "generated_at_utc": _utc_now_iso(),
        "schema_version": "1.0",
        "exchanges": exchanges,
        "validated_pair_count": len(pairs),
        "validated_pairs_ready": readiness,
        "min_leg_usdt": args.min_leg_usdt,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

    if not args.quiet:
        ready_n = sum(1 for r in readiness if r["ready_for_dry_run"])
        ok_n = sum(1 for v in exchanges.values() if v.get("ok"))
        print(
            f"[exchange_status] exchanges_ok={ok_n}/4 pairs={len(pairs)} ready={ready_n} -> {out_path}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
