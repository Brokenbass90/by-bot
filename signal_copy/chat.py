# -*- coding: utf-8 -*-
"""Разговор с ботом о торговле.

Модель видит живой снимок: счёт, открытые позиции с их стопами и целями,
последние разобранные сигналы. Отвечает текстом.

Действия с деньгами модель НЕ выполняет. Максимум, что она может — предложить
действие; оно превращается в кнопку, которую жмёт человек. Тот же принцип,
что и с сигналами: ИИ разбирает и подсказывает, исполняет человек.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

import config
import store

MAX_HISTORY = 10

SYSTEM = """Ты — помощник трейдера внутри инструмента signal_copy.
Он полуавтоматически копирует сигналы из Telegram-канала в MetaTrader 5.

Тебе дают СНИМОК состояния: счёт, открытые позиции (с ценой входа, стопом,
целью, текущей прибылью) и последние разобранные сигналы. Отвечай на его основе.

Правила:
- Отвечай кратко и по делу, на языке собеседника.
- Числа бери только из снимка. Не помнишь — скажи «не вижу в данных».
- Ты НЕ можешь открывать, закрывать и менять сделки сам.
- Если человек просит действие (закрыть, перенести стоп, в безубыток),
  объясни, что предлагаешь, и добавь В САМОМ КОНЦЕ блок:
```action
{"action": "close" | "breakeven" | "none", "ticket": <число>, "symbol": "<тикер>", "why": "<коротко>"}
```
  Человек увидит кнопку и решит сам. Если действие не нужно — блок не добавляй.
- Если просят оценить сигнал, считай отношение прибыли к риску и говори,
  какой винрейт нужен, чтобы не терять.
"""


def snapshot(mcp, conn) -> str:
    """Живое состояние в текстовом виде — это и есть «память» модели."""
    parts = []
    try:
        a = mcp.account()
        t = mcp.terminal()
        parts.append(
            f"СЧЁТ: {a['login']} · {a['server']} · {a['type']} · {a['margin_mode']}\n"
            f"средства {a['equity']:.2f} {a['currency']}, свободно {a.get('margin_free', 0):.2f}, "
            f"связь с брокером: {'есть' if t.get('server_connected') else 'НЕТ'}")
    except Exception as e:
        parts.append(f"СЧЁТ: недоступен ({e})")

    try:
        from executor import list_positions
        pos = list_positions(mcp, conn)
        if not pos:
            parts.append("ОТКРЫТЫХ ПОЗИЦИЙ НЕТ.")
        else:
            rows = ["ОТКРЫТЫЕ ПОЗИЦИИ:"]
            for p in pos:
                rows.append(
                    f"  тикет {p['ticket']} · {p['symbol']} {p['type']} {p['volume']} лота · "
                    f"вход {p['price_open']} · сейчас {p['price_current']} · "
                    f"стоп {p['sl'] or 'НЕТ'} · цель {p['tp'] or 'нет'} · "
                    f"прибыль {p['profit']} · своп {p['swap']}")
            parts.append("\n".join(rows))
    except Exception as e:
        parts.append(f"ПОЗИЦИИ: недоступны ({e})")

    try:
        rows = store.recent_groups(conn, 8)
        if rows:
            lines = ["ПОСЛЕДНИЕ РАЗОБРАННЫЕ СИГНАЛЫ:"]
            for r in rows:
                lines.append(
                    f"  #{r['id']} {r['symbol']} {r['side']} · вход {r['entry_min']}–{r['entry_max']}"
                    f" · стоп {r['stop_loss']} · цель {r['chosen_tp']} · статус {r['status']}")
            parts.append("\n".join(lines))
    except Exception:
        pass

    parts.append(
        f"НАСТРОЙКИ: риск {config.RISK_PCT}% на сделку, потолок {config.MAX_RISK_PCT}%, "
        f"максимум {config.MAX_POSITIONS} позиций, берём цель TP{config.DEFAULT_TP}, "
        f"реальные деньги {'РАЗРЕШЕНЫ' if config.ALLOW_LIVE else 'запрещены'}.")
    return "\n\n".join(parts)


# ── история разговора ────────────────────────────────────────────────────
HISTORY_PATH = None


def _hist_path():
    global HISTORY_PATH
    if HISTORY_PATH is None:
        from pathlib import Path
        HISTORY_PATH = Path(__file__).parent / "data" / "chat_history.json"
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    return HISTORY_PATH


def load_history() -> list[dict]:
    p = _hist_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))[-MAX_HISTORY:]
    except Exception:
        return []


def save_history(h: list[dict]) -> None:
    _hist_path().write_text(json.dumps(h[-MAX_HISTORY:], ensure_ascii=False, indent=1),
                            encoding="utf-8")


def clear_history() -> None:
    p = _hist_path()
    if p.exists():
        p.unlink()


# ── провайдеры ───────────────────────────────────────────────────────────
def _post(url: str, payload: dict, headers: dict, timeout: float = 90.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _deepseek(messages: list[dict]) -> str:
    if not config.ALLOW_REMOTE_LLM:
        raise RuntimeError("remote LLM выключен: SIGCOPY_ALLOW_REMOTE_LLM=0")
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("нет DEEPSEEK_API_KEY в .env")
    r = _post("https://api.deepseek.com/chat/completions",
              {"model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
               "temperature": 0.3, "max_tokens": 500, "messages": messages},
              {"Authorization": f"Bearer {key}"})
    return r["choices"][0]["message"]["content"]


def _ollama(messages: list[dict], images: list[str] | None = None) -> str:
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    if images:
        model = os.getenv("OLLAMA_VISION_MODEL", "llava")
        messages = list(messages)
        messages[-1] = {**messages[-1], "images": images}
    r = _post(f"{host}/api/chat",
              {"model": model, "stream": False,
               "options": {"temperature": 0.3, "num_predict": 500},
               "messages": messages})
    return r["message"]["content"]


ACTION_RE = re.compile(r"```action\s*(\{.*?\})\s*```", re.S)


def ask(user_text: str, mcp, conn, images: list[str] | None = None,
        prefer: str | None = None) -> dict:
    """Один ход разговора. Возвращает текст ответа и предложенное действие."""
    history = load_history()
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "system", "content": "СНИМОК СОСТОЯНИЯ:\n" + snapshot(mcp, conn)}]
    messages += [{"role": h["role"], "content": h["content"]} for h in history]
    messages.append({"role": "user", "content": user_text or "(картинка без текста)"})

    prefer = (prefer or os.getenv("SIGCOPY_LLM", "ollama")).lower()
    # Images always stay local. Text can leave the machine only after a
    # separate explicit privacy opt-in; an API key alone is insufficient.
    if images:
        order = ["ollama"]
    elif prefer == "deepseek" and config.ALLOW_REMOTE_LLM:
        order = ["deepseek", "ollama"]
    else:
        order = ["ollama"]
        if config.ALLOW_REMOTE_LLM:
            order.append("deepseek")
    errors = []
    reply, used = None, ""
    for name in order:
        try:
            reply = _ollama(messages, images) if name == "ollama" else _deepseek(messages)
            used = name
            break
        except Exception as e:
            errors.append(f"{name}: {e}")
    if reply is None:
        hint = ""
        if images:
            hint = ("\n\nДля картинок нужна локальная зрячая модель. Поставь её и укажи "
                    "в .env: OLLAMA_VISION_MODEL=llava (или другая с поддержкой изображений).")
        return {"ok": False, "error": "; ".join(errors) + hint}

    action = None
    m = ACTION_RE.search(reply)
    if m:
        try:
            a = json.loads(m.group(1))
            if a.get("action") in ("close", "breakeven"):
                action = a
        except Exception:
            pass
        reply = ACTION_RE.sub("", reply).strip()

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply})
    save_history(history)
    store.log(conn, None, "chat", {"user": user_text, "reply": reply,
                                   "action": action, "engine": used,
                                   "images": len(images or [])})
    return {"ok": True, "reply": reply, "action": action, "engine": used}
