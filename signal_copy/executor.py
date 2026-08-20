# -*- coding: utf-8 -*-
"""The only module allowed to send money-changing MT5 requests.

Every action is fail-closed: an approval is one-use, an idempotency record is
written before transport, the exact account is allowlisted, and a successful
terminal response is not enough without direct broker-state reconciliation.
"""
from __future__ import annotations

import secrets
from typing import Any

import config
import store
from mt5_mcp import MT5MCP
from sizing import calculate_lot, quotes_from_symbols


FULL_SUCCESS_RETCODES = {10008, 10009}  # PLACED, DONE; state must still reconcile.
PARTIAL_RETCODES = {10010}              # DONE_PARTIAL is never a full success.


def _dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _dicts(child)


def _trade_response_state(resp: Any) -> tuple[str, str]:
    """Return ``success``, ``partial``, ``failure`` or ``unknown``.

    A ticket/order id is never evidence of success by itself.  Partial fills
    are classified separately because they create exposure that must not be
    retried, while also not satisfying the confirmed request.
    """
    explicit_true = False
    explicit_false = False
    retcodes: list[int] = []
    for row in _dicts(resp):
        for key in ("success", "ok"):
            if key in row:
                explicit_true = explicit_true or row[key] is True
                explicit_false = explicit_false or row[key] is False
        if row.get("retcode") is not None:
            try:
                retcodes.append(int(row["retcode"]))
            except (TypeError, ValueError):
                return "unknown", f"неизвестный retcode={row.get('retcode')}"

    if any(code in PARTIAL_RETCODES for code in retcodes):
        return "partial", "MT5 исполнил заявку частично; нужна ручная сверка"
    bad = [code for code in retcodes if code not in FULL_SUCCESS_RETCODES]
    if bad:
        return "failure", f"MT5 retcode отказа: {bad[0]}"
    if explicit_false:
        return "failure", "терминал вернул success/ok=false"
    if retcodes and all(code in FULL_SUCCESS_RETCODES for code in retcodes):
        return "success", ""
    if explicit_true:
        return "success", ""
    return "unknown", "терминал не вернул явного успешного retcode"


def _trade_response_ok(resp: Any) -> tuple[bool, str]:
    """Compatibility wrapper used by older local tests."""
    state, reason = _trade_response_state(resp)
    return state == "success", reason


def _pos_field(pos: dict, *names, default=None):
    for name in names:
        if pos.get(name) not in (None, ""):
            return pos[name]
    return default


def _position_ticket(pos: dict):
    return _pos_field(pos, "ticket", "position_ticket", "position", "id")


def _position_side(pos: dict) -> str:
    raw = _pos_field(pos, "type", "position_type", default="")
    if isinstance(raw, (int, float)) or str(raw).strip().isdigit():
        return "buy" if int(raw) == 0 else "sell" if int(raw) == 1 else "unknown"
    text = str(raw).strip().lower()
    if "buy" in text or text in {"long", "b"}:
        return "buy"
    if "sell" in text or text in {"short", "s"}:
        return "sell"
    return "unknown"


def _account_type(account: dict) -> str:
    raw = _pos_field(account, "type", "account_type", "trade_mode", default="")
    if isinstance(raw, (int, float)) or str(raw).strip().isdigit():
        return {0: "demo", 1: "contest", 2: "real"}.get(int(raw), "unknown")
    text = str(raw).strip().lower()
    if "demo" in text:
        return "demo"
    if "contest" in text:
        return "contest"
    if "real" in text or "live" in text:
        return "real"
    return text or "unknown"


def _account_login(account: dict) -> int | None:
    raw = _pos_field(account, "login", "account_login", "account", default=None)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _execution_enabled() -> tuple[bool, str]:
    if not config.EXECUTION_ENABLE:
        return False, "исполнение выключено: SIGCOPY_EXECUTION_ENABLE=0"
    return True, ""


def _validate_account(mcp: MT5MCP) -> tuple[dict | None, dict | None, str]:
    """Re-read and validate server, login and account type before each action."""
    account = mcp.account()
    terminal = mcp.terminal()
    if not terminal.get("server_connected"):
        return None, terminal, "терминал потерял связь с брокером"
    if not terminal.get("mcp_trade_allowed"):
        return None, terminal, "торговля через MCP выключена в настройках"
    if account.get("read_only"):
        return None, terminal, "счёт только для чтения"

    server = str(account.get("server") or "")
    if not config.ALLOWED_SERVERS or server not in config.ALLOWED_SERVERS:
        return None, terminal, f"сервер {server or 'unknown'} отсутствует в точном allowlist"

    login = _account_login(account)
    if not config.ALLOWED_ACCOUNT_LOGINS:
        return None, terminal, "allowlist логинов пуст; укажи SIGCOPY_ALLOWED_ACCOUNT_LOGINS"
    if login is None or login not in config.ALLOWED_ACCOUNT_LOGINS:
        return None, terminal, f"логин {login if login is not None else 'unknown'} не разрешён"

    kind = _account_type(account)
    if not config.ALLOWED_ACCOUNT_TYPES or kind not in config.ALLOWED_ACCOUNT_TYPES:
        return None, terminal, f"тип счёта {kind} отсутствует в allowlist"
    if kind != "demo" and not config.ALLOW_LIVE:
        return None, terminal, "реальный/недемо счёт запрещён: SIGCOPY_ALLOW_LIVE=0"
    return account, terminal, ""


def _group_value(group, name: str, default=None):
    try:
        return group[name]
    except (IndexError, KeyError):
        return default


def _same_captured_account(group, account: dict) -> str:
    current_login = _account_login(account)
    captured_login = _group_value(group, "account_login")
    if captured_login is not None and int(captured_login) != current_login:
        return "карточка была рассчитана для другого логина; пересчитай сигнал"
    captured_type = _group_value(group, "trade_mode")
    if captured_type and _account_type({"type": captured_type}) != _account_type(account):
        return "карточка была рассчитана для другого типа счёта; пересчитай сигнал"
    captured_server = _group_value(group, "broker_server")
    if captured_server and str(captured_server) != str(account.get("server") or ""):
        return "карточка была рассчитана для другого сервера; пересчитай сигнал"
    return ""


def _validate_open(payload: dict, mcp: MT5MCP, conn):
    gid = int(payload.get("group_id") or 0)
    group = conn.execute("SELECT * FROM signal_group WHERE id=?", (gid,)).fetchone()
    if not group:
        return None, [], None, "исходная карточка сделки не найдена"
    symbol = str(payload.get("symbol") or "")
    side = str(payload.get("side") or "").upper()
    if side not in {"BUY", "SELL"}:
        return None, [], None, "неизвестная сторона сделки"
    if symbol != str(group["symbol"]) or side != str(group["side"]).upper():
        return None, [], None, "payload не совпадает с сохранённой карточкой"

    account, _terminal, account_error = _validate_account(mcp)
    if account is None:
        return None, [], None, account_error
    captured_error = _same_captured_account(group, account)
    if captured_error:
        return None, [], None, captured_error

    before = mcp.positions()
    if len(before) >= config.MAX_POSITIONS:
        return None, before, None, "лимит одновременных позиций достигнут"
    if any(str(_pos_field(p, "symbol", default="")) == symbol for p in before):
        return None, before, None, f"по {symbol} уже есть позиция; добавление запрещено"

    specs = mcp.symbols()
    spec = next((row for row in specs if str(row.get("symbol")) == symbol), None)
    if not spec:
        return None, before, None, f"символ {symbol} не найден в свежем Market Watch"
    entry = float(spec.get("ask") or 0) if side == "BUY" else float(spec.get("bid") or 0)
    stop = float(payload.get("sl") or 0)
    target = float(payload.get("tp") or 0) if payload.get("tp") else 0.0
    if entry <= 0 or stop <= 0:
        return None, before, spec, "нет свежей цены или стопа"
    if (side == "BUY" and stop >= entry) or (side == "SELL" and stop <= entry):
        return None, before, spec, "стоп оказался с неверной стороны от свежей цены"
    if target and ((side == "BUY" and target <= entry) or (side == "SELL" and target >= entry)):
        return None, before, spec, "цель уже пройдена или оказалась с неверной стороны"

    entry_values = [group["entry_min"], group["entry_max"]]
    entry_values = [float(value) for value in entry_values if value is not None]
    if not entry_values:
        return None, before, spec, "в исходной карточке нет зоны входа"
    low, high = min(entry_values), max(entry_values)
    outside = (low - entry) if entry < low else (entry - high) if entry > high else 0.0
    risk_dist = abs(entry - stop)
    if risk_dist <= 0:
        return None, before, spec, "нулевое расстояние до стопа"
    drift_r = outside / risk_dist
    if drift_r > config.MAX_ENTRY_DRIFT_R:
        return None, before, spec, f"цена уже на {drift_r:.2f}R вне зоны; нужна новая карточка"
    if target and abs(target - entry) / risk_dist < config.MIN_RR:
        return None, before, spec, "после обновления цены отношение прибыль/риск ниже минимума"

    equity = float(account.get("equity") or 0)
    if equity <= 0:
        return None, before, spec, "MT5 не вернул положительный equity"
    decision = calculate_lot(
        spec=spec, entry=entry, stop=stop, equity=equity,
        risk_pct=config.RISK_PCT, account_ccy=str(account.get("currency") or "USD"),
        quotes=quotes_from_symbols(specs), max_lot=config.MAX_LOT,
        max_risk_pct=config.MAX_RISK_PCT,
    )
    if not decision.accepted:
        reason = f"свежий пересчёт риска отказал: {decision.reason} {decision.note}".strip()
        return None, before, spec, reason
    confirmed_lot = float(payload.get("lot") or 0)
    actual_pct = confirmed_lot * decision.loss_per_lot / equity * 100
    if confirmed_lot <= 0 or confirmed_lot > decision.lot + 1e-9:
        return None, before, spec, "подтверждённый лот выше свежего безопасного лота"
    if actual_pct > min(config.RISK_PCT, config.MAX_RISK_PCT) + 1e-9:
        return None, before, spec, f"свежий риск {actual_pct:.2f}% выше разрешённого"

    request = {
        "symbol": symbol,
        "type": "buy" if side == "BUY" else "sell",
        "volume": confirmed_lot,
        "sl": stop,
        "comment": str(payload.get("client_id") or "")[:31],
    }
    if target:
        request["tp"] = target
    return request, before, spec, ""


def _find_ticket(resp) -> int | None:
    if isinstance(resp, dict):
        for key in ("position_ticket", "position", "order", "deal", "ticket", "order_ticket"):
            value = resp.get(key)
            if isinstance(value, (int, float)) and int(value) > 0:
                return int(value)
        for value in resp.values():
            got = _find_ticket(value)
            if got:
                return got
    elif isinstance(resp, list):
        for value in resp:
            got = _find_ticket(value)
            if got:
                return got
    return None


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _price_tolerance(spec: dict, expected: float) -> float:
    tick = abs(_number(spec.get("tick_size")))
    point = abs(_number(spec.get("point")))
    return max(tick, point, abs(expected) * 1e-8, 1e-9)


def _position_mismatches(position: dict, request: dict, spec: dict) -> list[str]:
    errors: list[str] = []
    if not _position_ticket(position):
        errors.append("нет ticket")
    if str(_pos_field(position, "symbol", default="")) != str(request["symbol"]):
        errors.append("symbol")
    if _position_side(position) != request["type"]:
        errors.append("side")
    volume = _number(_pos_field(position, "volume", "lots", default=0))
    step = abs(_number(spec.get("volume_step")))
    volume_tolerance = max(step * 1e-6, 1e-9)
    if abs(volume - float(request["volume"])) > volume_tolerance:
        errors.append(f"volume={volume}")
    for field, aliases in (
        ("sl", ("sl", "stop_loss")),
        ("tp", ("tp", "take_profit")),
    ):
        if field not in request:
            continue
        expected = float(request[field])
        actual = _number(_pos_field(position, *aliases, default=0))
        if actual <= 0 or abs(actual - expected) > _price_tolerance(spec, expected):
            errors.append(f"{field}={actual}")
    return errors


def _new_positions(before: list[dict], after: list[dict]) -> list[dict]:
    before_tickets = {
        str(_position_ticket(position)) for position in before if _position_ticket(position)
    }
    return [
        position for position in after
        if _position_ticket(position) and str(_position_ticket(position)) not in before_tickets
    ]


def _reconcile_open(before: list[dict], after: list[dict], request: dict,
                    spec: dict, hinted_ticket: int | None) -> tuple[dict | None, str]:
    candidates = _new_positions(before, after)
    hinted = [
        position for position in candidates
        if hinted_ticket is not None and str(_position_ticket(position)) == str(hinted_ticket)
    ]
    if hinted:
        candidates = hinted
    exact = [position for position in candidates if not _position_mismatches(position, request, spec)]
    if len(exact) == 1:
        return exact[0], ""
    diagnostics = [
        {"ticket": _position_ticket(position),
         "mismatches": _position_mismatches(position, request, spec)}
        for position in candidates
    ]
    return None, f"позиция не сверилась точно: {diagnostics or 'новой позиции нет'}"


def _mark_unknown(conn, group_id: int | None, client_id: str, action: str,
                  response: Any, ticket: int | None, message: str) -> dict:
    store.finish_execution(conn, client_id, action, response, False, ticket, message)
    if group_id:
        store.set_status(conn, int(group_id), "UNKNOWN", message)
    return {"ok": False, "unknown": True, "error": message, "response": response}


def execute_approved(token: str, mcp: MT5MCP, conn) -> dict:
    enabled, error = _execution_enabled()
    if not enabled:
        return {"ok": False, "error": error}
    payload, error = store.redeem_approval(conn, token)
    if payload is None:
        return {"ok": False, "error": error}

    gid = int(payload["group_id"])
    client_id = str(payload.get("client_id") or "")
    if not client_id:
        return {"ok": False, "error": "старая карточка без idempotency key; пересчитай сигнал"}
    try:
        request, before, spec, validation_error = _validate_open(payload, mcp, conn)
    except Exception as exc:
        store.set_status(conn, gid, "BLOCKED", f"не удалось проверить MT5: {type(exc).__name__}")
        return {"ok": False, "error": "не удалось получить свежий снимок MT5; ордер не отправлен"}
    if request is None:
        store.set_status(conn, gid, "BLOCKED", validation_error)
        return {"ok": False, "error": validation_error}
    reserved, reserve_error = store.begin_execution(conn, gid, "OPEN", client_id, request)
    if not reserved:
        return {"ok": False, "error": reserve_error}

    store.log(conn, gid, "order_request", request)
    try:
        response = mcp.call("trade_send_market_order", **request)
    except Exception as exc:
        return _mark_unknown(
            conn, gid, client_id, "OPEN", {}, None,
            f"ответ терминала потерян ({type(exc).__name__}); сверь MT5 и не повторяй",
        )

    state, response_error = _trade_response_state(response)
    hinted_ticket = _find_ticket(response)
    if state == "failure":
        store.finish_execution(conn, client_id, "OPEN", response, False, hinted_ticket,
                               response_error)
        store.set_status(conn, gid, "FAILED", response_error)
        return {"ok": False, "error": response_error, "response": response}
    if state != "success":
        try:
            observed = mcp.positions()
        except Exception:
            observed = "broker_state_unavailable"
        evidence = {"terminal_response": response, "observed_positions": observed}
        return _mark_unknown(conn, gid, client_id, "OPEN", evidence, hinted_ticket,
                             response_error)

    try:
        after = mcp.positions()
    except Exception as exc:
        evidence = {"terminal_response": response, "positions_error": type(exc).__name__}
        return _mark_unknown(
            conn, gid, client_id, "OPEN", evidence, hinted_ticket,
            "MT5 ответил успехом, но позиции не удалось перечитать; сверь терминал",
        )
    position, reconcile_error = _reconcile_open(before, after, request, spec, hinted_ticket)
    if position is None:
        evidence = {"terminal_response": response, "positions_after": after}
        return _mark_unknown(
            conn, gid, client_id, "OPEN", evidence, hinted_ticket,
            f"MT5 ответил успехом, но {reconcile_error}; не повторяй",
        )

    ticket = int(_position_ticket(position))
    evidence = {"terminal_response": response, "position": position}
    store.finish_execution(conn, client_id, "OPEN", evidence, True, ticket, "")
    store.log(conn, gid, "order_response", evidence)
    store.set_status(conn, gid, "OPEN")
    return {"ok": True, "ticket": ticket, "response": response, "request": request,
            "group_id": gid, "client_id": client_id}


def move_sl(group_id: int, new_sl: float, mcp: MT5MCP, conn) -> dict:
    return {"ok": False, "error": "произвольный move_sl выключен; используй безубыток"}


def _group_id_for_ticket(conn, ticket: int, symbol: str) -> int | None:
    row = conn.execute(
        "SELECT group_id FROM execution WHERE action='OPEN' AND ok=1 AND ticket=? "
        "AND group_id IS NOT NULL ORDER BY id DESC LIMIT 1",
        (int(ticket),),
    ).fetchone()
    if row:
        return int(row["group_id"])
    rows = list(conn.execute(
        "SELECT id FROM signal_group WHERE status='OPEN' AND symbol=? ORDER BY id DESC",
        (symbol,),
    ))
    return int(rows[0]["id"]) if len(rows) == 1 else None


def list_positions(mcp: MT5MCP, conn) -> list[dict]:
    out = []
    for position in mcp.positions():
        symbol = str(_pos_field(position, "symbol", default=""))
        ticket = _position_ticket(position)
        out.append({
            "raw": position,
            "symbol": symbol,
            "ticket": ticket,
            "type": _position_side(position),
            "volume": _pos_field(position, "volume", "lots", default=0),
            "price_open": _pos_field(position, "price_open", "open_price", "price", default=0),
            "price_current": _pos_field(position, "price_current", "current_price", default=0),
            "sl": _pos_field(position, "sl", "stop_loss", default=0),
            "tp": _pos_field(position, "tp", "take_profit", default=0),
            "profit": _pos_field(position, "profit", default=0),
            "swap": _pos_field(position, "swap", default=0),
            "group_id": _group_id_for_ticket(conn, int(ticket), symbol) if ticket else None,
        })
    return out


def prepare_position_action(action: str, ticket: int, symbol: str,
                            mcp: MT5MCP, conn) -> dict:
    """Create a short-lived approval after a fresh read-only position check."""
    enabled, error = _execution_enabled()
    if not enabled:
        return {"ok": False, "error": error}
    normalized = str(action or "").strip().lower()
    if normalized not in {"close", "breakeven"}:
        return {"ok": False, "error": "разрешены только close и breakeven"}
    try:
        account, _terminal, account_error = _validate_account(mcp)
        if account is None:
            return {"ok": False, "error": account_error}
        positions = list_positions(mcp, conn)
    except Exception:
        return {"ok": False, "error": "не удалось перечитать счёт/позиции; подтверждение не создано"}
    target = next((row for row in positions if str(row["ticket"]) == str(ticket)), None)
    if target is None or str(target["symbol"]) != str(symbol):
        return {"ok": False, "error": "позиция не найдена или тикет не совпал с символом"}
    payload = {
        "ticket": int(ticket),
        "symbol": str(symbol),
        "client_id": f"sigcopy-{normalized}-{ticket}-{secrets.token_hex(8)}",
    }
    token = store.issue_action_approval(conn, normalized, payload, ttl_sec=90)
    store.log(conn, target.get("group_id"), "action_preview", {
        "action": normalized,
        "ticket": int(ticket),
        "symbol": str(symbol),
        "expires_in_sec": 90,
    })
    return {
        "ok": True,
        "action": normalized,
        "ticket": int(ticket),
        "symbol": str(symbol),
        "token": token,
        "expires_in_sec": 90,
    }


def execute_position_action(token: str, mcp: MT5MCP, conn) -> dict:
    """Redeem an exact action token and execute it once."""
    enabled, error = _execution_enabled()
    if not enabled:
        return {"ok": False, "error": error}
    action, payload, error = store.redeem_action_approval(conn, token)
    if payload is None or action is None:
        return {"ok": False, "error": error}
    common = {
        "ticket": int(payload["ticket"]),
        "symbol": str(payload["symbol"]),
        "mcp": mcp,
        "conn": conn,
        "client_id": str(payload["client_id"]),
    }
    if action == "close":
        return close_position(**common)
    if action == "breakeven":
        return breakeven(**common)
    return {"ok": False, "error": "неизвестное действие в подтверждении"}


def close_position(ticket: int, symbol: str, mcp: MT5MCP, conn,
                   client_id: str | None = None) -> dict:
    enabled, error = _execution_enabled()
    if not enabled:
        return {"ok": False, "error": error}
    try:
        account, _terminal, account_error = _validate_account(mcp)
        if account is None:
            return {"ok": False, "error": account_error}
        before = mcp.positions()
    except Exception:
        return {"ok": False, "error": "не удалось проверить текущий счёт/позиции; запрос не отправлен"}
    target = next((p for p in before if str(_position_ticket(p)) == str(ticket)), None)
    if target is None or str(_pos_field(target, "symbol", default="")) != str(symbol):
        return {"ok": False, "error": "позиция уже не найдена или тикет не совпал с символом"}
    group_id = _group_id_for_ticket(conn, int(ticket), symbol)
    request = {"symbol": symbol, "position_ticket": int(ticket)}
    client_id = str(client_id or f"close-{ticket}")
    reserved, reserve_error = store.begin_execution(conn, group_id, "CLOSE", client_id, request)
    if not reserved:
        return {"ok": False, "error": reserve_error}
    store.log(conn, group_id, "close_request", request)
    try:
        response = mcp.call("trade_close_single_position", **request)
    except Exception as exc:
        return _mark_unknown(
            conn, group_id, client_id, "CLOSE", {}, int(ticket),
            f"ответ закрытия потерян ({type(exc).__name__}); сверь MT5",
        )
    state, response_error = _trade_response_state(response)
    if state == "failure":
        store.finish_execution(conn, client_id, "CLOSE", response, False, int(ticket),
                               response_error)
        return {"ok": False, "error": response_error}
    if state != "success":
        return _mark_unknown(conn, group_id, client_id, "CLOSE", response, int(ticket),
                             response_error)
    try:
        after = mcp.positions()
    except Exception as exc:
        evidence = {"terminal_response": response, "positions_error": type(exc).__name__}
        return _mark_unknown(
            conn, group_id, client_id, "CLOSE", evidence, int(ticket),
            "MT5 ответил успехом, но закрытие не удалось сверить",
        )
    if any(str(_position_ticket(p)) == str(ticket) for p in after):
        evidence = {"terminal_response": response, "positions_after": after}
        return _mark_unknown(
            conn, group_id, client_id, "CLOSE", evidence, int(ticket),
            "MT5 ответил успехом, но позиция всё ещё открыта; не повторяй без сверки",
        )
    store.finish_execution(conn, client_id, "CLOSE", response, True, int(ticket), "")
    if group_id:
        store.set_status(conn, group_id, "CLOSED")
    return {"ok": True, "response": response}


def breakeven(ticket: int, symbol: str, mcp: MT5MCP, conn,
              client_id: str | None = None) -> dict:
    enabled, error = _execution_enabled()
    if not enabled:
        return {"ok": False, "error": error}
    try:
        account, _terminal, account_error = _validate_account(mcp)
        if account is None:
            return {"ok": False, "error": account_error}
        positions = list_positions(mcp, conn)
    except Exception:
        return {"ok": False, "error": "не удалось проверить текущий счёт/позиции; запрос не отправлен"}
    target = next((p for p in positions if str(p["ticket"]) == str(ticket)), None)
    if target is None or str(target["symbol"]) != str(symbol):
        return {"ok": False, "error": "позиция не найдена или тикет не совпал с символом"}

    entry = _number(target["price_open"])
    current = _number(target["price_current"])
    old_sl = _number(target["sl"])
    side = target["type"]
    if side not in {"buy", "sell"}:
        return {"ok": False, "error": "MT5 вернул неизвестный тип позиции"}
    if entry <= 0 or current <= 0:
        return {"ok": False, "error": "не вижу цену входа/текущую цену"}
    if side == "buy" and current <= entry:
        return {"ok": False, "error": "BUY ещё не выше входа — безубыток не отправлен"}
    if side == "sell" and current >= entry:
        return {"ok": False, "error": "SELL ещё не ниже входа — безубыток не отправлен"}
    if old_sl and ((side == "buy" and old_sl >= entry) or (side == "sell" and old_sl <= entry)):
        return {"ok": False, "error": "стоп уже в безубытке или лучше"}

    request = {"symbol": symbol, "position_ticket": int(ticket), "sl": entry}
    current_tp = _number(target.get("tp"))
    if current_tp > 0:
        request["tp"] = current_tp
    group_id = target["group_id"]
    client_id = str(client_id or f"be-{ticket}")
    reserved, reserve_error = store.begin_execution(
        conn, group_id, "MOVE_SL", client_id, request,
    )
    if not reserved:
        return {"ok": False, "error": reserve_error}
    store.log(conn, group_id, "breakeven_request", request)
    try:
        response = mcp.call("trade_modify_sl_tp", **request)
    except Exception as exc:
        return _mark_unknown(
            conn, group_id, client_id, "MOVE_SL", {}, int(ticket),
            f"ответ изменения стопа потерян ({type(exc).__name__}); сверь MT5",
        )
    state, response_error = _trade_response_state(response)
    if state == "failure":
        store.finish_execution(conn, client_id, "MOVE_SL", response, False, int(ticket),
                               response_error)
        return {"ok": False, "error": response_error}
    if state != "success":
        return _mark_unknown(conn, group_id, client_id, "MOVE_SL", response, int(ticket),
                             response_error)
    try:
        fresh_positions = list_positions(mcp, conn)
    except Exception as exc:
        evidence = {"terminal_response": response, "positions_error": type(exc).__name__}
        return _mark_unknown(
            conn, group_id, client_id, "MOVE_SL", evidence, int(ticket),
            "MT5 ответил успехом, но новый стоп не удалось сверить",
        )
    fresh = next((p for p in fresh_positions if str(p["ticket"]) == str(ticket)), None)
    spec = {"point": max(abs(entry) * 1e-8, 1e-9), "tick_size": 0}
    if fresh is None:
        return _mark_unknown(
            conn, group_id, client_id, "MOVE_SL", response, int(ticket),
            "позиция исчезла во время сверки безубытка; проверь MT5",
        )
    mismatches = []
    if str(fresh["symbol"]) != symbol or fresh["type"] != side:
        mismatches.append("ticket/symbol/side")
    if abs(_number(fresh["sl"]) - entry) > _price_tolerance(spec, entry):
        mismatches.append(f"sl={fresh['sl']}")
    if current_tp > 0 and abs(_number(fresh["tp"]) - current_tp) > _price_tolerance(spec, current_tp):
        mismatches.append(f"tp={fresh['tp']}")
    if mismatches:
        evidence = {"terminal_response": response, "position": fresh}
        return _mark_unknown(
            conn, group_id, client_id, "MOVE_SL", evidence, int(ticket),
            f"новый стоп/TP не подтвердились точно: {mismatches}",
        )
    store.finish_execution(conn, client_id, "MOVE_SL", response, True, int(ticket), "")
    return {"ok": True, "response": response, "new_sl": entry}
