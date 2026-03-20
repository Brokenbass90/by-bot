from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


@dataclass
class DeepSeekConfig:
    enabled: bool
    api_key: str
    base_url: str
    model: str
    timeout_sec: float
    history_path: Path
    max_history_messages: int
    max_answer_chars: int


def _load_config() -> DeepSeekConfig:
    return DeepSeekConfig(
        enabled=_env_bool("DEEPSEEK_ENABLE", False),
        api_key=str(os.getenv("DEEPSEEK_API_KEY", "") or "").strip(),
        base_url=str(os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") or "https://api.deepseek.com").strip(),
        model=str(os.getenv("DEEPSEEK_MODEL", "deepseek-chat") or "deepseek-chat").strip(),
        timeout_sec=float(os.getenv("DEEPSEEK_TIMEOUT_SEC", "8") or 8),
        history_path=Path(str(os.getenv("DEEPSEEK_CHAT_STATE_PATH", "/tmp/bybot_deepseek_chat.json") or "/tmp/bybot_deepseek_chat.json")),
        max_history_messages=max(0, int(os.getenv("DEEPSEEK_HISTORY_MAX_MESSAGES", "8") or 8)),
        max_answer_chars=max(600, int(os.getenv("DEEPSEEK_MAX_ANSWER_CHARS", "3500") or 3500)),
    )


def _safe_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(data)


class DeepSeekOverlay:
    def __init__(self) -> None:
        self.cfg = _load_config()

    def reload(self) -> None:
        self.cfg = _load_config()

    def is_ready(self) -> bool:
        self.reload()
        return bool(self.cfg.enabled and self.cfg.api_key)

    def status_text(self) -> str:
        self.reload()
        return (
            f"DeepSeek: {'ON' if self.cfg.enabled else 'OFF'}\n"
            f"model={self.cfg.model}\n"
            f"base_url={self.cfg.base_url}\n"
            f"history={self.cfg.history_path}\n"
            f"api_key={'set' if self.cfg.api_key else 'missing'}"
        )

    def reset_history(self) -> None:
        try:
            if self.cfg.history_path.exists():
                self.cfg.history_path.unlink()
        except Exception:
            pass

    def _load_history(self) -> list[dict[str, str]]:
        path = self.cfg.history_path
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f) or []
            out: list[dict[str, str]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role", "") or "").strip()
                content = str(item.get("content", "") or "").strip()
                if role in {"user", "assistant"} and content:
                    out.append({"role": role, "content": content})
            return out[-self.cfg.max_history_messages :]
        except Exception:
            return []

    def _save_history(self, messages: list[dict[str, str]]) -> None:
        try:
            self.cfg.history_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cfg.history_path.open("w", encoding="utf-8") as f:
                json.dump(messages[-self.cfg.max_history_messages :], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def ask(self, question: str, snapshot: dict[str, Any]) -> str:
        self.reload()
        q = str(question or "").strip()
        if not q:
            return "Usage: /ai <question>"
        if not self.cfg.enabled:
            return "DeepSeek overlay выключен. Включи `DEEPSEEK_ENABLE=1` и добавь `DEEPSEEK_API_KEY`."
        if not self.cfg.api_key:
            return "DeepSeek API key не задан. Нужен `DEEPSEEK_API_KEY`."

        system_prompt = (
            "Ты — advisory-менеджер торгового бота. "
            "Ты не управляешь ордерами и не меняешь настройки напрямую. "
            "Отвечай кратко, по делу, на русском. "
            "Опирайся только на локальный snapshot бота и вопрос пользователя. "
            "Если данных мало, прямо скажи это. "
            "Не выдумывай сделки, PnL или состояние рынка."
        )
        snapshot_text = _safe_json(snapshot)
        history = self._load_history()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "system",
                "content": (
                    "Ниже локальный snapshot бота. "
                    "Используй его как источник правды, а не догадки.\n"
                    f"{snapshot_text}"
                ),
            },
        ]
        messages.extend(history)
        messages.append({"role": "user", "content": q})

        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
            "max_tokens": 500,
        }
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.cfg.timeout_sec)
            resp.raise_for_status()
            data = resp.json() or {}
            choices = data.get("choices") or []
            content = ""
            if choices:
                msg = choices[0].get("message") or {}
                content = str(msg.get("content") or "").strip()
            if not content:
                return "DeepSeek не вернул содержательный ответ."
            answer = content[: self.cfg.max_answer_chars].strip()
            history.extend([
                {"role": "user", "content": q},
                {"role": "assistant", "content": answer},
            ])
            self._save_history(history)
            return answer
        except Exception as e:
            return f"DeepSeek request failed: {e}"
