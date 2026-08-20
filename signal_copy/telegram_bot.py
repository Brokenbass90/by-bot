# -*- coding: utf-8 -*-
"""Ручной Telegram-вход в signal_copy с обязательной кнопкой подтверждения.

Текст никогда не открывает сделку сам: сначала строится та же карточка, что в
локальном веб-интерфейсе, затем владелец нажимает inline-кнопку с одноразовым
5-минутным токеном. Разрешены только chat id из явного allowlist.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import config
import store
from executor import execute_approved, list_positions
from mt5_mcp import MT5MCP, MT5Error
from pipeline import build_cards, persist_and_arm


BOT_TOKEN = os.getenv("SIGCOPY_TG_BOT_TOKEN", "").strip()
ALLOWED_CHAT_IDS = {
    int(value.strip())
    for value in os.getenv("SIGCOPY_TG_CHAT_IDS", "").split(",")
    if value.strip().lstrip("-").isdigit()
}
ALLOWED_USER_IDS = {
    int(value.strip())
    for value in os.getenv("SIGCOPY_TG_USER_IDS", "").split(",")
    if value.strip().lstrip("-").isdigit()
}
PRIVATE_ONLY = os.getenv("SIGCOPY_TG_PRIVATE_ONLY", "1").strip().lower() in {
    "1", "true", "yes", "on",
}
USE_LLM = os.getenv("SIGCOPY_TG_USE_LLM", "0").strip().lower() in {"1", "true", "yes"}


def is_allowed(chat_id: int | str | None, user_id: int | str | None = None,
               chat_type: str | None = None) -> bool:
    try:
        chat_ok = int(chat_id) in ALLOWED_CHAT_IDS
        user_ok = int(user_id) in ALLOWED_USER_IDS
    except (TypeError, ValueError):
        return False
    if PRIVATE_ONLY and str(chat_type or "").lower() != "private":
        return False
    return chat_ok and user_ok


def _api(method: str, payload: dict | None = None, timeout: float = 40.0) -> dict:
    if not BOT_TOKEN:
        raise RuntimeError("не задан SIGCOPY_TG_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            out = json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        # urllib errors may include the bot-token URL. Never echo it to logs/UI.
        raise RuntimeError(f"Telegram API недоступен ({type(exc).__name__})") from None
    if not out.get("ok"):
        raise RuntimeError(f"Telegram API отказал: {out.get('description', 'unknown error')}")
    return out.get("result")


def send(chat_id: int, text: str, keyboard: dict | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
    if keyboard:
        payload["reply_markup"] = keyboard
    _api("sendMessage", payload)


def _n(value, digits: int = 5) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")


def card_text(card) -> str:
    if card.kind != "SIGNAL":
        details = card.blockers or card.warnings
        return f"{card.title or card.kind}\n" + "\n".join(f"• {x}" for x in details)
    digits = 2 if str(card.symbol).startswith("XAU") else 5
    state = "ГОТОВО К РУЧНОМУ ПОДТВЕРЖДЕНИЮ" if card.can_execute else "ЗАБЛОКИРОВАНО"
    lines = [
        f"{state}: {card.symbol} {card.side}",
        f"Рынок: {_n(card.entry_used, digits)}",
        f"Стоп: {_n(card.stop_loss, digits)} · цель: {_n(card.chosen_tp, digits)}",
        f"Лот: {_n(card.lot, 4)} · риск: {_n(card.risk_cash, 2)} {card.currency}",
        f"Осталось: {_n(card.rr, 2)}R",
    ]
    lines.extend(f"⛔ {x}" for x in card.blockers)
    lines.extend(f"⚠ {x}" for x in card.warnings)
    return "\n".join(lines)


def _handle_text(chat_id: int, user_id: int, text: str, mcp: MT5MCP, conn) -> None:
    text = (text or "").strip()
    if text in {"/start", "/help"}:
        send(chat_id, "Пришли сигнал текстом. Я только рассчитаю карточку; сделка откроется "
             "лишь после отдельного нажатия кнопки. /positions — живые позиции MT5.")
        return
    if text == "/positions":
        positions = list_positions(mcp, conn)
        if not positions:
            send(chat_id, "Открытых позиций MT5 нет.")
            return
        send(chat_id, "\n".join(
            f"#{p['ticket']} {p['symbol']} {p['type']} {p['volume']} · "
            f"P/L {p['profit']} · SL {p['sl'] or 'НЕТ'}"
            for p in positions
        ))
        return
    if not text or text.startswith("/"):
        send(chat_id, "Неизвестная команда. Пришли сигнал или используй /positions.")
        return

    cards = build_cards(text, mcp, conn, use_llm=USE_LLM)
    cards = persist_and_arm(
        cards, text, mcp, conn, source=f"telegram:{chat_id}:user:{user_id}",
    )
    if not cards:
        send(chat_id, "Не нашёл сигнала в сообщении.")
        return
    for card in cards:
        keyboard = None
        if card.can_execute and card.token:
            keyboard = {"inline_keyboard": [[{
                "text": f"ОТКРЫТЬ {card.symbol} {card.side} {card.lot}",
                "callback_data": f"open:{card.token}",
            }]]}
        send(chat_id, card_text(card), keyboard)


def _handle_callback(query: dict, mcp: MT5MCP, conn) -> None:
    callback_id = query.get("id")
    message = query.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    user_id = (query.get("from") or {}).get("id")
    if not is_allowed(chat_id, user_id, chat.get("type")):
        if callback_id:
            _api("answerCallbackQuery", {"callback_query_id": callback_id,
                                         "text": "Доступ запрещён", "show_alert": True})
        return
    data = str(query.get("data") or "")
    if not data.startswith("open:") or len(data) > 64:
        _api("answerCallbackQuery", {"callback_query_id": callback_id,
                                     "text": "Неизвестная кнопка", "show_alert": True})
        return
    token = data.split(":", 1)[1]
    result = execute_approved(token, mcp, conn)
    text = (f"Открыто. Тикет #{result.get('ticket')}" if result.get("ok")
            else f"Не исполнено: {result.get('error', 'терминал не подтвердил ордер')}")
    _api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:180],
                                 "show_alert": not result.get("ok")})
    send(int(chat_id), text)


def handle_update(update: dict, mcp: MT5MCP, conn=None) -> bool:
    """Handle one update exactly once, including across process restarts."""
    conn = conn or store.connect()
    try:
        update_id = int(update["update_id"])
    except (KeyError, TypeError, ValueError):
        return False
    if not store.claim_telegram_update(conn, update_id):
        return False
    try:
        query = update.get("callback_query")
        if query:
            message = query.get("message") or {}
            chat = message.get("chat") or {}
            user_id = (query.get("from") or {}).get("id")
            if not is_allowed(chat.get("id"), user_id, chat.get("type")):
                store.finish_telegram_update(conn, update_id, "DENIED")
                return True
            _handle_callback(query, mcp, conn)
            store.finish_telegram_update(conn, update_id, "DONE")
            return True

        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        user_id = (message.get("from") or {}).get("id")
        if not is_allowed(chat_id, user_id, chat.get("type")):
            store.finish_telegram_update(conn, update_id, "DENIED")
            return True
        text = message.get("text") or message.get("caption") or ""
        _handle_text(int(chat_id), int(user_id), text, mcp, conn)
        store.finish_telegram_update(conn, update_id, "DONE")
        return True
    except Exception:
        store.finish_telegram_update(conn, update_id, "ERROR")
        raise


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("SIGCOPY_TG_BOT_TOKEN не задан")
    if not ALLOWED_CHAT_IDS:
        raise SystemExit("SIGCOPY_TG_CHAT_IDS пуст — fail-closed")
    if not ALLOWED_USER_IDS:
        raise SystemExit("SIGCOPY_TG_USER_IDS пуст — fail-closed")
    mcp = MT5MCP(config.MT5_URL, config.MT5_TOKEN)
    conn = store.connect()
    offset = store.last_telegram_update_id(conn) + 1
    print("signal_copy Telegram polling: allowlist включён, автоторговли нет")
    while True:
        try:
            updates = _api("getUpdates", {"offset": offset, "timeout": 30,
                                           "allowed_updates": ["message", "callback_query"]},
                           timeout=40.0) or []
            for update in updates:
                offset = max(offset, int(update.get("update_id", 0)) + 1)
                try:
                    handle_update(update, mcp, conn)
                except (MT5Error, RuntimeError) as exc:
                    message = update.get("message") or (update.get("callback_query") or {}).get("message") or {}
                    chat_id = (message.get("chat") or {}).get("id")
                    user_id = ((update.get("callback_query") or {}).get("from") or
                               message.get("from") or {}).get("id")
                    chat_type = (message.get("chat") or {}).get("type")
                    if is_allowed(chat_id, user_id, chat_type):
                        send(int(chat_id), f"Ошибка: {exc}")
        except Exception as exc:
            print(f"poll error: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()
