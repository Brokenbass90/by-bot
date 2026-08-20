# -*- coding: utf-8 -*-
"""Клиент MCP-сервера MetaTrader 5. Только стандартная библиотека.

Терминал слушает на 127.0.0.1:22346. Ключ — вкладка Настройки → MCP.
Ордер уходит только если его позвали явно; сам модуль ничего не решает.
"""
from __future__ import annotations

import json
import socket
import urllib.request
import urllib.error
from typing import Any


class MT5Error(RuntimeError):
    pass


class MT5MCP:
    PROTOCOL = "2025-06-18"

    def __init__(self, url: str, token: str, timeout: float = 15.0):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session_id: str | None = None
        self._id = 0

    # ── транспорт ────────────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.PROTOCOL,
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _post(self, payload: dict, timeout: float | None = None) -> tuple[dict | None, dict]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                hdrs = {k.lower(): v for k, v in r.headers.items()}
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                detail = ""
            if e.code == 401:
                raise MT5Error(
                    "ключ доступа к MCP не подошёл. В MetaTrader 5 открой "
                    "Сервис → Настройки → MCP, скопируй поле «Ключ API» и положи "
                    "его в signal_copy/.env строкой SIGCOPY_MT5_TOKEN=<ключ>, "
                    "затем перезапусти app.py"
                ) from None
            raise MT5Error(f"терминал ответил HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            raise MT5Error(f"терминал недоступен ({e.reason}). MT5 запущен?") from None
        except (TimeoutError, socket.timeout):
            # Именно сюда попадали зависания: таймаут ЧТЕНИЯ не является URLError,
            # он летел наверх необработанным и превращался в 500.
            raise MT5Error(
                f"терминал не ответил за {timeout or self.timeout:.0f} с. "
                f"Возможно, в MT5 открыто окно подтверждения — посмотри на терминал."
            ) from None
        except Exception as e:
            raise MT5Error(f"сбой связи с терминалом: {type(e).__name__}: {e}") from None
        return self._decode(raw), hdrs

    @staticmethod
    def _decode(raw: str) -> dict | None:
        """Ответ приходит либо чистым JSON, либо как SSE-поток с 'data: '."""
        raw = raw.strip()
        if not raw:
            return None
        if raw.startswith("{"):
            return json.loads(raw)
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk.startswith("{"):
                    return json.loads(chunk)
        raise MT5Error(f"не разобрал ответ: {raw[:200]}")

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    # ── сессия ───────────────────────────────────────────────────────────
    def connect(self) -> dict:
        self.session_id = None
        resp, hdrs = self._post({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
            "params": {"protocolVersion": self.PROTOCOL, "capabilities": {},
                       "clientInfo": {"name": "signal_copy", "version": "0.1"}},
        })
        self.session_id = hdrs.get("mcp-session-id")
        if not self.session_id:
            raise MT5Error("сервер не выдал Mcp-Session-Id")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return (resp or {}).get("result", {})

    # Торговые вызовы ждём дольше: терминал может показывать окно подтверждения.
    SLOW_TOOLS = ("trade_send_market_order", "trade_send_pending_order",
                  "trade_modify_sl_tp", "trade_close_single_position",
                  "trade_close_by_position", "trade_delete_order")

    def call(self, tool: str, timeout: float | None = None, **args) -> Any:
        """Вызвать инструмент. Полезная нагрузка лежит в content[0].text как JSON-строка."""
        if not self.session_id:
            self.connect()
        if timeout is None:
            timeout = 90.0 if tool in self.SLOW_TOOLS else self.timeout
        resp, _ = self._post(timeout=timeout, payload={
            "jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        })
        if resp is None:
            raise MT5Error(f"{tool}: пустой ответ")
        if "error" in resp:
            raise MT5Error(f"{tool}: {resp['error']}")
        result = resp.get("result", {})
        if result.get("isError"):
            raise MT5Error(f"{tool}: {result}")
        content = result.get("content") or []
        if not content:
            return result
        text = content[0].get("text", "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    # ── удобные обёртки (только чтение) ──────────────────────────────────
    def account(self) -> dict:
        return self.call("get_trading_account_info")["account"]

    def terminal(self) -> dict:
        return self.call("get_trading_account_info")["terminal"]

    def symbols(self, symbol: str | None = None) -> list[dict]:
        args = {"symbol": symbol} if symbol else {}
        return self.call("get_marketwatch_symbols", **args).get("symbols", [])

    def symbol(self, name: str) -> dict:
        rows = self.symbols(name)
        if not rows:
            raise MT5Error(f"символ {name} не найден в Обзоре рынка")
        return rows[0]

    def positions(self) -> list[dict]:
        return self.call("get_trading_open_positions").get("positions", [])

    def add_symbol(self, name: str) -> Any:
        return self.call("add_marketwatch_symbol", symbol=name)
