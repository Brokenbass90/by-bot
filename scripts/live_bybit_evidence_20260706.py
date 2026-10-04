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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Fail closed instead of following a signed request to another URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


class StrictAtt1ReadClient:
    """Signed, bounded Bybit V5 evidence reader with no mutable API surface.

    It accepts exactly one selected account mapping and never reads credentials
    from the environment or account fallback lists.  Responses remain raw full
    Bybit envelopes so the ATT1 lifecycle owner can persist and validate them.
    """

    BASE_URL = "https://api.bybit.com"
    TIMEOUT_SECONDS = 10
    MAX_RESPONSE_BYTES = 1_000_000
    MAX_PAGES = 16
    MAX_AGE_MS = 60_000
    _ALLOWLIST = {
        "/v5/user/query-api": frozenset(),
        "/v5/position/list": frozenset({"category", "symbol", "settleCoin", "limit", "cursor"}),
        "/v5/order/realtime": frozenset({"category", "symbol", "baseCoin", "settleCoin", "orderId", "orderLinkId", "openOnly", "limit", "cursor"}),
        "/v5/order/history": frozenset({"category", "symbol", "baseCoin", "orderId", "orderLinkId", "startTime", "endTime", "limit", "cursor"}),
        "/v5/execution/list": frozenset({"category", "symbol", "baseCoin", "orderId", "orderLinkId", "execType", "startTime", "endTime", "limit", "cursor"}),
        "/v5/account/transaction-log": frozenset({"category", "accountType", "currency", "baseCoin", "type", "startTime", "endTime", "limit", "cursor"}),
        "/v5/market/funding/history": frozenset({"category", "symbol", "startTime", "endTime", "limit"}),
        "/v5/market/instruments-info": frozenset({"category", "symbol"}),
        "/v5/account/fee-rate": frozenset({"category", "symbol"}),
        "/v5/account/wallet-balance": frozenset({"accountType", "coin"}),
    }
    _PAGE_ENDPOINTS = frozenset({
        "/v5/position/list", "/v5/order/realtime", "/v5/order/history",
        "/v5/execution/list", "/v5/account/transaction-log",
    })
    _LIMIT_MAX = {
        "/v5/position/list": 200,
        "/v5/order/realtime": 50,
        "/v5/order/history": 50,
        "/v5/execution/list": 100,
        "/v5/account/transaction-log": 50,
        "/v5/market/funding/history": 200,
    }

    def __init__(self, config: dict[str, str], *, opener=None, clock_ms=None):
        if not isinstance(config, dict) or set(config) != {"key", "secret", "base"}:
            raise ValueError("explicit selected ATT1 account config required")
        key, secret, base = config["key"], config["secret"], config["base"]
        if (not all(isinstance(value, str) and value for value in (key, secret, base))
                or base.rstrip("/") != self.BASE_URL):
            raise ValueError("ATT1 endpoint or credentials rejected")
        self._key = key
        self._secret = secret
        self._base = self.BASE_URL
        self._opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect(),
        )
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self.last_received_ms: int | None = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}(config={{'key': '<redacted>', 'base': {self._base!r}}})"

    @property
    def timeout_seconds(self) -> int:
        return self.TIMEOUT_SECONDS

    @property
    def config(self) -> dict[str, str]:
        """Return the selected public config without the signing secret."""
        return {"key": self._key, "base": self._base}

    @property
    def redacted_config(self) -> dict[str, str]:
        return self.config

    @staticmethod
    def _text(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value:
            raise ValueError(f"invalid {name}")
        return value

    def _validated_params(self, path: str, params: dict[str, Any]) -> dict[str, str]:
        if path not in self._ALLOWLIST or not isinstance(params, dict):
            raise ValueError("GET path or params rejected")
        if set(params) - self._ALLOWLIST[path]:
            raise ValueError("GET params not allowlisted")
        if path == "/v5/user/query-api" and params:
            raise ValueError("query-api parameters rejected")
        normalized: dict[str, str] = {}
        for key, value in params.items():
            if not isinstance(key, str) or not key.isascii():
                raise ValueError("invalid GET parameter name")
            if isinstance(value, bool):
                raise ValueError("invalid GET parameter value")
            if isinstance(value, int):
                if value < 0:
                    raise ValueError("invalid GET parameter value")
                text = str(value)
            else:
                text = self._text(value, "GET parameter value")
            normalized[key] = text
        if path == "/v5/account/wallet-balance":
            if normalized != {"accountType":"UNIFIED", "coin":"USDT"}:
                raise ValueError("exact selected UNIFIED USDT wallet required")
        elif path != "/v5/user/query-api" and normalized.get("category") != "linear":
            raise ValueError("ATT1 category must be linear")
        if "limit" in normalized:
            try:
                limit = int(normalized["limit"])
            except ValueError as exc:
                raise ValueError("invalid page limit") from exc
            if (not 1 <= limit <= self._LIMIT_MAX[path]
                    or str(limit) != normalized["limit"]):
                raise ValueError("invalid page limit")
        timestamps: dict[str, int] = {}
        for name in ("startTime", "endTime"):
            if name in normalized:
                try:
                    parsed = int(normalized[name])
                except ValueError as exc:
                    raise ValueError("invalid evidence time window") from exc
                if parsed <= 0 or str(parsed) != normalized[name]:
                    raise ValueError("invalid evidence time window")
                timestamps[name] = parsed
        if path == "/v5/account/transaction-log" and len(timestamps) == 2:
            if not 0 <= timestamps["endTime"] - timestamps["startTime"] <= 7 * 24 * 60 * 60 * 1000:
                raise ValueError("transaction-log time window exceeds seven days")
        if path == "/v5/market/funding/history" and "symbol" not in normalized:
            raise ValueError("funding history symbol required")
        if path in {"/v5/market/instruments-info", "/v5/account/fee-rate"}:
            symbol = normalized.get("symbol", "")
            if (not symbol.endswith("USDT") or not symbol.isascii()
                    or not symbol.isalnum() or symbol != symbol.upper()):
                raise ValueError("exact uppercase USDT symbol required")
        return normalized

    def _request_url(self, path: str, params: dict[str, str]) -> tuple[str, str]:
        query = urllib.parse.urlencode(sorted(params.items()), safe="")
        return self._base + path + (("?" + query) if query else ""), query

    def _validate_envelope(self, envelope: Any, received_ms: int) -> dict[str, Any]:
        if (not isinstance(envelope, dict) or type(envelope.get("retCode")) is not int
                or envelope["retCode"] != 0 or type(envelope.get("time")) is not int
                or not isinstance(envelope.get("result"), dict)):
            raise ValueError("malformed Bybit evidence envelope")
        response_ms = envelope["time"]
        if not 0 < response_ms <= received_ms or received_ms - response_ms > self.MAX_AGE_MS:
            raise ValueError("stale or future Bybit evidence envelope")
        return envelope

    @staticmethod
    def _strict_object(pairs):
        parsed = {}
        for key, value in pairs:
            if key in parsed:
                raise ValueError("duplicate JSON key")
            parsed[key] = value
        return parsed

    @staticmethod
    def _reject_nonfinite_json(value):
        raise ValueError("non-finite JSON literal: " + value)

    def _validate_result_category(self, path: str, result: dict[str, Any]) -> None:
        if path == "/v5/user/query-api":
            return
        if path == "/v5/account/wallet-balance":
            rows = result.get('list')
            if (not isinstance(rows, list) or len(rows)!=1 or not isinstance(rows[0], dict)
                    or rows[0].get('accountType')!='UNIFIED'
                    or not isinstance(rows[0].get('coin'), list) or len(rows[0]['coin'])!=1
                    or not isinstance(rows[0]['coin'][0], dict) or rows[0]['coin'][0].get('coin')!='USDT'):
                raise ValueError('selected UNIFIED USDT wallet response rejected')
            return
        if path == "/v5/account/fee-rate":
            # Official derivatives response omits category; request is pinned
            # to linear and the pure mapper requires the exact symbol.
            if ('category' in result or not isinstance(result.get('list'), list)):
                raise ValueError("derivatives fee response rejected")
            return
        if path == "/v5/account/transaction-log":
            rows = result.get("list")
            if not isinstance(rows, list):
                raise ValueError("transaction-log result rows rejected")
            for row in rows:
                if not isinstance(row, dict) or row.get("category") != "linear":
                    raise ValueError("transaction-log row category rejected")
            return
        if result.get("category") != "linear":
            raise ValueError("Bybit response category rejected")
        if path == "/v5/market/funding/history" and not isinstance(result.get("list"), list):
            raise ValueError("funding history result rows rejected")

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch one exact signed GET envelope from the pinned Bybit endpoint."""
        normalized = self._validated_params(path, params)
        url, query = self._request_url(path, normalized)
        timestamp = str(int(self._clock_ms()))
        if not timestamp.isdecimal() or int(timestamp) <= 0:
            raise ValueError("invalid local receive clock")
        recv_window = "5000"
        signature = hmac.new(
            self._secret.encode(),
            (timestamp + self._key + recv_window + query).encode(),
            hashlib.sha256,
        ).hexdigest()
        request = urllib.request.Request(
            url,
            headers={
                "X-BAPI-API-KEY": self._key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": recv_window,
                "X-BAPI-SIGN": signature,
            },
            method="GET",
        )
        with self._opener.open(request, timeout=self.TIMEOUT_SECONDS) as response:
            if response.geturl() != url:
                raise ValueError("Bybit redirect rejected")
            raw = response.read(self.MAX_RESPONSE_BYTES + 1)
        if not isinstance(raw, bytes) or len(raw) > self.MAX_RESPONSE_BYTES:
            raise ValueError("Bybit response exceeds bounded size")
        try:
            envelope = json.loads(
                raw.decode("utf-8"), object_pairs_hook=self._strict_object,
                parse_constant=self._reject_nonfinite_json,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("Bybit response is not JSON") from exc
        received_ms = int(self._clock_ms())
        if received_ms <= 0:
            raise ValueError("invalid local receive clock")
        envelope = self._validate_envelope(envelope, received_ms)
        self._validate_result_category(path, envelope["result"])
        self.last_received_ms = received_ms
        return envelope

    def pages(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Return a complete, bounded, non-cyclic linear pagination chain."""
        base_params = self._validated_params(path, params)
        if path not in self._PAGE_ENDPOINTS or "cursor" in base_params:
            raise ValueError("pagination path or initial cursor rejected")
        pages: list[dict[str, Any]] = []
        seen_cursors: set[str] = set()
        cursor = ""
        while True:
            request_params = dict(base_params)
            if cursor:
                request_params["cursor"] = cursor
            envelope = self.get(path, request_params)
            result = envelope["result"]
            next_cursor = result.get("nextPageCursor")
            # Observed on the authenticated UTA endpoint: empty list with an
            # explicit JSON null cursor. Preserve the raw envelope unchanged.
            if (path == "/v5/account/transaction-log" and result.get("list") == []
                    and "nextPageCursor" in result and next_cursor is None):
                next_cursor = ""
            if not isinstance(result.get("list"), list) or not isinstance(next_cursor, str):
                raise ValueError("malformed Bybit linear page")
            pages.append(envelope)
            if not next_cursor:
                return pages
            if next_cursor in seen_cursors or len(pages) >= self.MAX_PAGES:
                raise ValueError("cyclic or oversized Bybit pagination")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

    def identity(self):
        """Refresh a redacted UID binding from the pinned signed query-api call."""
        envelope = self.get("/v5/user/query-api", {})
        if self.last_received_ms is None:  # Defensive: get only sets it after validation.
            raise ValueError("identity receive clock missing")
        if str(ROOT) not in os.sys.path:
            os.sys.path.insert(0, str(ROOT))
        from bot.att1_coordinator_adapter import validate_old_att1_broker_identity

        return validate_old_att1_broker_identity(
            self.config, envelope, received_ms=self.last_received_ms,
        )


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
