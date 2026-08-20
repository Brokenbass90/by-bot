# -*- coding: utf-8 -*-
"""Слой ИИ — вызывается ТОЛЬКО когда правила не справились.

Зачем он нужен: канал пишет на разных языках и свободным текстом
(«переносите стоп в безубыток», «move SL to BE», «закрыл половину»).
Правила такое не покрывают.

Чего он не может: выдумать число. Каждое числовое значение из ответа модели
проверяется на дословное присутствие в исходном тексте. Не нашли — поле
отбрасывается. Решение об открытии сделки модель не принимает никогда.
"""
from __future__ import annotations

import json
import math
import os
import re
import urllib.request

import config

SYSTEM = """Ты разбираешь сообщения трейдингового канала. Отвечай ТОЛЬКО JSON, без пояснений.

Поля:
  action  — одно из: OPEN, MOVE_SL, CLOSE_PARTIAL, CLOSE_ALL, RESULT, NOISE, UNKNOWN
  symbol  — тикер в виде XAUUSD, EURUSD, AUDUSD (или null)
  side    — BUY или SELL (или null)
  entry_min, entry_max, stop_loss — числа или null
  take_profits — массив чисел (может быть пустым)
  new_stop_loss — число, либо строка "BREAK_EVEN", либо null
  close_fraction — доля закрытия 0..1 или null
  language — язык сообщения (ru/en/…)
  notes   — очень кратко, что понял

ЗАПРЕЩЕНО придумывать числа. Бери только те, что дословно есть в тексте.
Если данных не хватает — ставь null. Пустой ответ лучше выдуманного."""

NUM_RE = re.compile(r"(?<![\w.])[+-]?\d+(?:[.,]\d+)?")
NUM_VALUE_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


def _canonical_number(value) -> tuple[float | None, str | None]:
    """Coerce JSON numbers and numeric strings to one finite representation."""
    if value is None or isinstance(value, bool):
        return None, None
    if isinstance(value, str):
        value = value.strip()
        if not NUM_VALUE_RE.fullmatch(value):
            return None, None
        value = value.replace(",", ".")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, None
    if not math.isfinite(number):
        return None, None
    canonical = format(number, ".15g")
    return number, canonical


def _numbers_in(text: str) -> set[str]:
    """Все числа исходника в нормализованном виде (запятая → точка, без хвостовых нулей)."""
    out = set()
    for m in NUM_RE.finditer(text):
        _number, canonical = _canonical_number(m.group(0))
        if canonical is not None:
            out.add(canonical)
    return out


def verify_numbers(parsed: dict, source: str) -> tuple[dict, list[str]]:
    """Выбрасывает из ответа модели любое число, которого нет в исходном тексте."""
    allowed = _numbers_in(source)
    dropped: list[str] = []

    def checked(value, *, allow_break_even: bool = False):
        if value is None:
            return None, True
        if allow_break_even and isinstance(value, str) and value.strip().upper() == "BREAK_EVEN":
            return "BREAK_EVEN", True
        number, canonical = _canonical_number(value)
        return number, canonical in allowed if canonical is not None else False

    clean = dict(parsed)
    for key in ("entry_min", "entry_max", "stop_loss", "new_stop_loss"):
        if key not in clean:
            continue
        value, valid = checked(clean[key], allow_break_even=key == "new_stop_loss")
        if not valid:
            dropped.append(f"{key}={clean[key]}")
            value = None
        clean[key] = value
    tps = clean.get("take_profits") or []
    if not isinstance(tps, list):
        dropped.append("take_profits: ожидался массив")
        tps = []
    kept = []
    for target in tps:
        value, valid = checked(target)
        if valid and value is not None:
            kept.append(value)
        else:
            dropped.append(f"take_profit={target}")
    clean["take_profits"] = kept
    if "close_fraction" in clean:
        value, valid = checked(clean["close_fraction"])
        if not valid or value is None or not 0 < value <= 1:
            dropped.append(f"close_fraction={clean['close_fraction']}")
            value = None
        clean["close_fraction"] = value
    return clean, dropped


# ── провайдеры ───────────────────────────────────────────────────────────
def _post_json(url: str, payload: dict, headers: dict, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text)
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < 0:
        raise ValueError(f"в ответе модели нет JSON: {text[:200]}")
    return json.loads(text[i:j + 1])


def ask_deepseek(text: str, model: str | None = None) -> dict:
    if not config.ALLOW_REMOTE_LLM:
        raise RuntimeError("remote LLM выключен: SIGCOPY_ALLOW_REMOTE_LLM=0")
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("нет DEEPSEEK_API_KEY")
    model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    r = _post_json("https://api.deepseek.com/chat/completions",
                   {"model": model, "temperature": 0,
                    "max_tokens": 300,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": text}]},
                   {"Authorization": f"Bearer {key}"})
    return _extract_json(r["choices"][0]["message"]["content"])


def ask_ollama(text: str, model: str | None = None) -> dict:
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    r = _post_json(f"{host}/api/chat",
                   {"model": model, "stream": False, "format": "json",
                    "options": {"temperature": 0, "num_predict": 300},
                    "messages": [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": text}]}, {})
    return _extract_json(r["message"]["content"])


def parse_with_llm(text: str, prefer: str | None = None) -> tuple[dict | None, str]:
    """Пробуем провайдеров по очереди. Возвращаем (очищенный разбор, описание)."""
    prefer = (prefer or os.getenv("SIGCOPY_LLM", "ollama")).lower()
    if prefer == "deepseek" and config.ALLOW_REMOTE_LLM:
        order = ["deepseek", "ollama"]
    else:
        order = ["ollama"]
        if config.ALLOW_REMOTE_LLM:
            order.append("deepseek")
    errors = []
    for name in order:
        try:
            raw = ask_deepseek(text) if name == "deepseek" else ask_ollama(text)
            clean, dropped = verify_numbers(raw, text)
            note = f"{name}"
            if dropped:
                note += f" · отброшены выдуманные значения: {', '.join(dropped)}"
            return clean, note
        except Exception as e:
            errors.append(f"{name}: {e}")
    return None, "; ".join(errors)
