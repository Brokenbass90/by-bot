#!/usr/bin/env python3
"""Collect sanitized live evidence for one Bybit linear symbol.

This script is intended to run on the VPS where live env files exist. It does
not print API keys or secrets; Bybit responses used here do not include them.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> dict[str, str]:
    vals: dict[str, str] = {}
    if not path.exists():
        return vals
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        vals[key.strip()] = val.strip().strip('"').strip("'")
    return vals


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for rel in (".env", "configs/bybit_live.env", "configs/live.env"):
        env.update(_load_env_file(ROOT / rel))
    for key in ("BYBIT_API_KEY", "BYBIT_API_SECRET", "BYBIT_BASE_URL"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def _ts_utc(epoch: float | int | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch or time.time()))


def _runtime_json(rel: str) -> dict[str, Any]:
    path = ROOT / rel
    if not path.exists():
        return {"missing": True}
    try:
        data: Any = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 - evidence collector
        data = {"_read_error": repr(exc)}
    return {"mtime_utc": _ts_utc(path.stat().st_mtime), "data": data}


def _jsonl_tail_hits(rel: str, symbol: str, max_bytes: int = 512_000) -> dict[str, Any]:
    path = ROOT / rel
    if not path.exists():
        return {"missing": True}
    hits: list[str] = []
    token = symbol.replace("USDT", "")
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - max_bytes), os.SEEK_SET)
        for raw in fh.read().splitlines():
            line = raw.decode("utf-8", "replace")
            if symbol in line or token in line:
                hits.append(line[:2000])
    return {
        "mtime_utc": _ts_utc(path.stat().st_mtime),
        "hit_count_tail": len(hits),
        "tail_hits": hits[-40:],
    }


def _db_rows(symbol: str) -> dict[str, Any]:
    path = ROOT / "runtime/trades.db"
    if not path.exists():
        return {"missing": True}
    out: dict[str, Any] = {"mtime_utc": _ts_utc(path.stat().st_mtime), "tables": {}}
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        tables = [
            row[0]
            for row in con.execute(
                "select name from sqlite_master where type='table' order by name"
            )
        ]
        token = symbol.replace("USDT", "")
        for table in tables:
            cols = [row[1] for row in con.execute(f"pragma table_info({table})")]
            table_out: dict[str, Any] = {"columns": cols, "symbol_rows": []}
            out["tables"][table] = table_out
            predicates = []
            for col in cols:
                lower = col.lower()
                if any(
                    needle in lower
                    for needle in (
                        "symbol",
                        "pair",
                        "raw",
                        "json",
                        "event",
                        "message",
                        "side",
                        "strategy",
                        "instrument",
                    )
                ):
                    predicates.append(
                        f"(CAST({col} AS TEXT) LIKE ? OR CAST({col} AS TEXT) LIKE ?)"
                    )
            if not predicates:
                continue
            query = f"select * from {table} where {' or '.join(predicates)} limit 80"
            args: list[str] = []
            for _ in predicates:
                args.extend([f"%{symbol}%", f"%{token}%"])
            try:
                rows = [dict(row) for row in con.execute(query, args)]
                table_out["symbol_rows"] = rows[-30:]
            except Exception as exc:  # noqa: BLE001 - evidence collector
                table_out["query_error"] = repr(exc)
    finally:
        con.close()
    return out


class BybitClient:
    def __init__(self, env: dict[str, str]):
        self.api_key = env.get("BYBIT_API_KEY") or env.get("BYBIT_KEY") or ""
        self.api_secret = env.get("BYBIT_API_SECRET") or env.get("BYBIT_SECRET") or ""
        self.base_url = (
            env.get("BYBIT_BASE_URL") or env.get("BYBIT_BASE") or "https://api.bybit.com"
        )
        if self.api_key and self.api_secret:
            return
        raw_accounts = env.get("BYBIT_ACCOUNTS_JSON") or ""
        if not raw_accounts:
            return
        try:
            accounts = json.loads(raw_accounts)
        except Exception:
            return
        if not accounts:
            return
        account = accounts[0]
        self.api_key = str(account.get("key") or "")
        self.api_secret = str(account.get("secret") or "")
        self.base_url = str(account.get("base") or self.base_url)

    def get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.api_key or not self.api_secret:
            return {"_error": "missing_api_keys_in_env"}
        ts = str(int(time.time() * 1000))
        recv_window = "5000"
        query = urllib.parse.urlencode(sorted(params.items()))
        payload = ts + self.api_key + recv_window + query
        sig = hmac.new(self.api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        request = urllib.request.Request(
            self.base_url.rstrip("/") + path + "?" + query,
            headers={
                "X-BAPI-API-KEY": self.api_key,
                "X-BAPI-TIMESTAMP": ts,
                "X-BAPI-RECV-WINDOW": recv_window,
                "X-BAPI-SIGN": sig,
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))


def _bybit_evidence(symbol: str, lookback_hours: int) -> dict[str, Any]:
    client = BybitClient(_load_env())
    end = int(time.time() * 1000)
    start = end - lookback_hours * 3600 * 1000
    calls = {
        "position_list": (
            "/v5/position/list",
            {"category": "linear", "symbol": symbol},
        ),
        "execution_list": (
            "/v5/execution/list",
            {
                "category": "linear",
                "symbol": symbol,
                "startTime": str(start),
                "endTime": str(end),
                "limit": "100",
            },
        ),
        "order_history": (
            "/v5/order/history",
            {
                "category": "linear",
                "symbol": symbol,
                "startTime": str(start),
                "endTime": str(end),
                "limit": "100",
            },
        ),
        "closed_pnl": (
            "/v5/position/closed-pnl",
            {
                "category": "linear",
                "symbol": symbol,
                "startTime": str(start),
                "endTime": str(end),
                "limit": "50",
            },
        ),
    }
    out: dict[str, Any] = {}
    for label, (path, params) in calls.items():
        try:
            out[label] = client.get(path, params)
        except Exception as exc:  # noqa: BLE001 - evidence collector
            out[label] = {"_error": repr(exc)}
    return out


def _conclusion(api: dict[str, Any]) -> dict[str, Any]:
    positions = (
        ((api.get("position_list") or {}).get("result") or {}).get("list") or []
        if isinstance(api.get("position_list"), dict)
        else []
    )
    closed = (
        ((api.get("closed_pnl") or {}).get("result") or {}).get("list") or []
        if isinstance(api.get("closed_pnl"), dict)
        else []
    )
    executions = (
        ((api.get("execution_list") or {}).get("result") or {}).get("list") or []
        if isinstance(api.get("execution_list"), dict)
        else []
    )
    return {
        "open_positions_nonzero": [
            pos for pos in positions if float(pos.get("size") or 0) != 0
        ],
        "closed_pnl_count": len(closed),
        "execution_count": len(executions),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="ADAUSDT")
    parser.add_argument("--lookback-hours", type=int, default=72)
    args = parser.parse_args()

    api = _bybit_evidence(args.symbol, args.lookback_hours)
    report = {
        "checked_at_utc": _ts_utc(),
        "root": str(ROOT),
        "symbol": args.symbol,
        "lookback_hours": args.lookback_hours,
        "runtime": {
            "live_positions": _runtime_json("runtime/live_positions.json"),
            "bot_heartbeat": _runtime_json("runtime/bot_heartbeat.json"),
            "live_trade_events_tail": _jsonl_tail_hits(
                "runtime/live_trade_events.jsonl", args.symbol
            ),
            "decision_bus_tail": _jsonl_tail_hits("runtime/decision_bus.jsonl", args.symbol),
            "telegram_outbox_tail": _jsonl_tail_hits(
                "runtime/telegram_outbox.jsonl", args.symbol
            ),
            "trades_db": _db_rows(args.symbol),
        },
        "bybit_api": api,
        "conclusion": _conclusion(api),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
