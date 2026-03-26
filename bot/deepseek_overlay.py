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
    audit_log_path: Path
    approval_queue_path: Path
    shadow_enabled: bool
    shadow_log_path: Path
    max_history_messages: int
    max_answer_chars: int
    daily_request_cap: int
    shadow_max_items: int


def _load_config() -> DeepSeekConfig:
    return DeepSeekConfig(
        enabled=_env_bool("DEEPSEEK_ENABLE", False),
        api_key=str(os.getenv("DEEPSEEK_API_KEY", "") or "").strip(),
        base_url=str(os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") or "https://api.deepseek.com").strip(),
        model=str(os.getenv("DEEPSEEK_MODEL", "deepseek-chat") or "deepseek-chat").strip(),
        timeout_sec=float(os.getenv("DEEPSEEK_TIMEOUT_SEC", "20") or 20),
        history_path=Path(str(os.getenv("DEEPSEEK_CHAT_STATE_PATH", "/root/by-bot/data/deepseek_chat.json") or "/root/by-bot/data/deepseek_chat.json")),
        audit_log_path=Path(str(os.getenv("DEEPSEEK_AUDIT_LOG_PATH", "/root/by-bot/data/deepseek_audit.jsonl") or "/root/by-bot/data/deepseek_audit.jsonl")),
        approval_queue_path=Path(str(os.getenv("DEEPSEEK_APPROVAL_QUEUE_PATH", "/root/by-bot/data/deepseek_approval_queue.json") or "/root/by-bot/data/deepseek_approval_queue.json")),
        shadow_enabled=_env_bool("DEEPSEEK_SHADOW_ENABLE", True),
        shadow_log_path=Path(str(os.getenv("DEEPSEEK_SHADOW_LOG_PATH", "/root/by-bot/data/deepseek_shadow.json") or "/root/by-bot/data/deepseek_shadow.json")),
        max_history_messages=max(0, int(os.getenv("DEEPSEEK_HISTORY_MAX_MESSAGES", "16") or 16)),
        max_answer_chars=max(600, int(os.getenv("DEEPSEEK_MAX_ANSWER_CHARS", "3500") or 3500)),
        daily_request_cap=max(1, int(os.getenv("DEEPSEEK_DAILY_REQUEST_CAP", "60") or 60)),
        shadow_max_items=max(10, int(os.getenv("DEEPSEEK_SHADOW_MAX_ITEMS", "200") or 200)),
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
            f"audit={self.cfg.audit_log_path}\n"
            f"approval_queue={self.cfg.approval_queue_path}\n"
            f"shadow={'ON' if self.cfg.shadow_enabled else 'OFF'}\n"
            f"shadow_log={self.cfg.shadow_log_path}\n"
            f"daily_request_cap={self.cfg.daily_request_cap}\n"
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

    def _append_audit(self, payload: dict[str, Any]) -> None:
        try:
            self.cfg.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cfg.audit_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _count_today_requests(self) -> int:
        path = self.cfg.audit_log_path
        if not path.exists():
            return 0
        day = time.strftime("%Y-%m-%d", time.gmtime())
        count = 0
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    ts = int(row.get("ts") or 0)
                    row_day = time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts else ""
                    if row_day == day:
                        count += 1
        except Exception:
            return 0
        return count

    def budget_status_text(self) -> str:
        self.reload()
        used = self._count_today_requests()
        left = max(0, self.cfg.daily_request_cap - used)
        return (
            "DeepSeek budget:\n"
            f"used_today={used}\n"
            f"daily_cap={self.cfg.daily_request_cap}\n"
            f"remaining={left}"
        )

    def _load_shadow_items(self) -> list[dict[str, Any]]:
        path = self.cfg.shadow_log_path
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f) or []
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except Exception:
            pass
        return []

    def _save_shadow_items(self, items: list[dict[str, Any]]) -> None:
        try:
            self.cfg.shadow_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cfg.shadow_log_path.open("w", encoding="utf-8") as f:
                json.dump(items[-self.cfg.shadow_max_items :], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def append_shadow_recommendation(
        self,
        summary: str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "manual",
        recommendation_type: str = "advisory",
    ) -> None:
        self.reload()
        if not self.cfg.shadow_enabled:
            return
        items = self._load_shadow_items()
        items.append(
            {
                "id": 1 + max([int(x.get("id") or 0) for x in items] or [0]),
                "ts": int(time.time()),
                "source": str(source or "manual"),
                "type": str(recommendation_type or "advisory"),
                "summary": str(summary or "").strip(),
                "payload": payload or {},
            }
        )
        self._save_shadow_items(items)

    def shadow_status_text(self, limit: int = 5) -> str:
        self.reload()
        items = self._load_shadow_items()
        lines = [
            "DeepSeek shadow mode:",
            f"enabled={'yes' if self.cfg.shadow_enabled else 'no'}",
            f"log={self.cfg.shadow_log_path}",
            f"stored={len(items)}",
        ]
        if not items:
            lines.append("recent=none")
            return "\n".join(lines)
        lines.append("recent:")
        for item in items[-max(1, limit) :]:
            ts = int(item.get("ts") or 0)
            stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts)) if ts else "unknown"
            lines.append(
                f"- id={item.get('id')} ts={stamp} type={item.get('type','advisory')} "
                f"source={item.get('source','manual')} summary={item.get('summary','')}"
            )
        return "\n".join(lines)

    def reset_shadow_log(self) -> str:
        self.reload()
        try:
            if self.cfg.shadow_log_path.exists():
                self.cfg.shadow_log_path.unlink()
            return "DeepSeek shadow log reset."
        except Exception as e:
            return f"DeepSeek shadow log reset failed: {e}"

    def _load_approval_queue(self) -> list[dict[str, Any]]:
        path = self.cfg.approval_queue_path
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f) or []
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except Exception:
            pass
        return []

    def _save_approval_queue(self, items: list[dict[str, Any]]) -> None:
        try:
            self.cfg.approval_queue_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cfg.approval_queue_path.open("w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def pending_actions_text(self) -> str:
        self.reload()
        items = [x for x in self._load_approval_queue() if str(x.get("status", "pending")) == "pending"]
        if not items:
            return "DeepSeek approval queue: пусто."
        lines = ["DeepSeek approval queue:"]
        for item in items[:10]:
            lines.append(
                f"- id={item.get('id')} kind={item.get('kind','proposal')} "
                f"status={item.get('status','pending')} summary={item.get('summary','')}"
            )
        return "\n".join(lines)

    def submit_proposal(self, summary: str, payload: dict[str, Any] | None = None, kind: str = "proposal") -> str:
        self.reload()
        items = self._load_approval_queue()
        next_id = 1 + max([int(x.get("id") or 0) for x in items] or [0])
        item = {
            "id": next_id,
            "kind": kind,
            "status": "pending",
            "summary": str(summary or "").strip(),
            "payload": payload or {},
            "created_ts": int(time.time()),
        }
        items.append(item)
        self._save_approval_queue(items)
        return f"DeepSeek proposal queued: id={next_id}"

    def decide_proposal(self, proposal_id: int, approve: bool) -> str:
        self.reload()
        items = self._load_approval_queue()
        for item in items:
            if int(item.get("id") or 0) != int(proposal_id):
                continue
            if str(item.get("status", "pending")) != "pending":
                return f"Proposal {proposal_id} уже не pending."
            item["status"] = "approved" if approve else "rejected"
            item["decided_ts"] = int(time.time())
            self._save_approval_queue(items)
            return f"Proposal {proposal_id} {'approved' if approve else 'rejected'}."
        return f"Proposal {proposal_id} not found."

    def ask(self, question: str, snapshot: dict[str, Any]) -> str:
        self.reload()
        q = str(question or "").strip()
        if not q:
            return "Usage: /ai <question>"
        if not self.cfg.enabled:
            return "DeepSeek overlay выключен. Включи `DEEPSEEK_ENABLE=1` и добавь `DEEPSEEK_API_KEY`."
        if not self.cfg.api_key:
            return "DeepSeek API key не задан. Нужен `DEEPSEEK_API_KEY`."
        if self._count_today_requests() >= self.cfg.daily_request_cap:
            return "DeepSeek budget exhausted for today. Увеличь `DEEPSEEK_DAILY_REQUEST_CAP` или дождись следующего дня."

        system_prompt = (
            "Ты — senior партнёр и аналитик алготрейдингового бота на Bybit perpetual futures.\n"
            "Ты можешь свободно общаться: отвечать на вопросы о стратегиях, рынке, коде, риск-менеджменте,\n"
            "давать мнения об улучшениях, обсуждать идеи. Веди диалог как опытный коллега.\n\n"
            "== АРХИТЕКТУРА БОТА ==\n"
            "Бот написан на Python, торгует на Bybit через WebSocket + REST.\n"
            "Файлы: smart_pump_reversal_bot.py (главный цикл), bot/deepseek_overlay.py (ты),\n"
            "bot/deepseek_autoresearch_agent.py (autoresearch + аудит), strategies/*.py.\n\n"
            "== АКТИВНЫЕ СТРАТЕГИИ (5 штук) ==\n"
            "1. alt_sloped_channel_v1 (ASC1) — SHORT от верхней границы наклонного канала.\n"
            "   Монеты: ATOM, LINK, DOT (расширено 2026-03-26, было только ATOM+LINK).\n"
            "   Trailing stop: отключён (ASC1_TRAIL_ATR_MULT=0). Можно включить.\n"
            "   Лучший backtest: WR 80%, PF 8.94, DD 0.88%, 0 красных месяцев.\n"
            "   С DOT: net=+19.41%, PF=2.683, WR=52.8%, DD=1.91%.\n\n"
            "2. alt_resistance_fade_v1 (ARF1) — SHORT от зон горизонтального сопротивления.\n"
            "   Монеты: LINK, LTC, SUI, DOT, ADA, BCH (6 монет с 2026-03-25).\n"
            "   Trailing stop: отключён. Можно включить: ARF1_TRAIL_ATR_MULT.\n"
            "   Backtest 6 монет: net=+37.48%, PF=3.495, WR=52.6%, DD=1.59%, 0 красных месяцев.\n\n"
            "3. inplay_breakout — лонги на пробой уровней, top 10 монет по объёму.\n"
            "   Trailing stop: BREAKOUT_TRAIL_ATR_MULT=2.2 (активен!).\n"
            "   Quality filter: BREAKOUT_QUALITY_MIN_SCORE=0.48 (оптимизирован autoresearch).\n"
            "   Backtest: ~346 trades/year, WR 65.6%, PF 1.399, DD 2.95%.\n\n"
            "4. btc_eth_midterm_pullback — среднесрок BTC+ETH на откатах к уровням.\n"
            "   Trailing stop: MTPB_TRAIL_ATR_MULT=1.1 (активен).\n"
            "   Backtest: 71 trades/year, WR 46%, PF 1.3. Слабейшая из 5 — нужен autoresearch.\n\n"
            "5. alt_inplay_breakdown_v1 — SHORT пробои вниз. ✅ АКТИВНА в live с 2026-03-25.\n"
            "   Монеты: BTC, ETH, SOL, LINK, ATOM, LTC (расширено 2026-03-26, было BTC+ETH+SOL).\n"
            "   Trailing stop: отключён (fixed exit оптимальнее по бэктестам).\n"
            "   Backtest 6 монет: net=+81.22%, PF=2.118, WR=57.4%, DD=4.8%, 10/12 зелёных месяцев.\n\n"
            "== ПОРТФЕЛЬ (360d backtest) ==\n"
            "Вся стека: $100 → ~$200+ (+100%+), PF=2.08, DD=3.65%, 446 trades, 0 красных месяцев.\n"
            "Депозит живой: ~$103. Риск на сделку: 0.1% от депо (~$5 нотионал при 3x плечо).\n\n"
            "== AUTORESEARCH (grid-search backtest) ==\n"
            "scripts/run_strategy_autoresearch.py --spec <config.json>\n"
            "Прогоны: breakdown_expansion_v1 (лучш 6 монет), asc1_expansion_v1 (лучш +DOT),\n"
            "triple_screen_elder_friend_v11 (1024 комб, в процессе).\n\n"
            "== ВЫХОД ИЗ ПОЗИЦИИ ==\n"
            "TradeSignal: entry, sl, tp, be_trigger_rr, trailing_atr_mult (0=выкл), time_stop_bars.\n"
            "ATR trailing: SL следует за хаем/лоем позиции с отступом X*ATR.\n\n"
            "== КАК ОБЩАТЬСЯ ==\n"
            "Отвечай на русском. Давай своё мнение — это твоя экспертиза.\n"
            "На вопросы типа 'как улучшить бот?', 'что думаешь о стратегии X?' — отвечай развёрнуто.\n"
            "Не выдумывай цифры без основания — опирайся на snapshot и данные выше.\n"
            "Если не знаешь точно — скажи честно, но поделись рассуждением."
        )
        snapshot_text = _safe_json(snapshot)
        history = self._load_history()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "system",
                "content": (
                    "Ниже живой snapshot бота (текущий момент). "
                    "Используй как источник правды о текущих сделках, балансе и статистике.\n"
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
                answer = "DeepSeek не вернул содержательный ответ."
                self._append_audit({
                    "ts": int(time.time()),
                    "model": self.cfg.model,
                    "question": q,
                    "answer": answer,
                    "status": "empty",
                })
                return answer
            answer = content[: self.cfg.max_answer_chars].strip()
            history.extend([
                {"role": "user", "content": q},
                {"role": "assistant", "content": answer},
            ])
            self._save_history(history)
            self.append_shadow_recommendation(
                summary=answer[:240],
                payload={"question": q, "model": self.cfg.model},
                source="telegram_ai",
                recommendation_type="advisory_reply",
            )
            self._append_audit({
                "ts": int(time.time()),
                "model": self.cfg.model,
                "question": q,
                "answer": answer,
                "status": "ok",
            })
            return answer
        except Exception as e:
            answer = f"DeepSeek request failed: {e}"
            self._append_audit({
                "ts": int(time.time()),
                "model": self.cfg.model,
                "question": q,
                "answer": answer,
                "status": "error",
            })
            return answer
