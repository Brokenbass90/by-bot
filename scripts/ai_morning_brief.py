#!/usr/bin/env python3
"""ai_morning_brief.py — утренний дайджест от DeepSeek в TG в 07:00 МСК.

Собирает за прошлые 24 часа: трейды, PnL, allocator decisions, текущие setups,
Alpaca позиции — упаковывает в один prompt, шлёт DeepSeek, форматирует ответ
и шлёт в TG юзеру.

Cron:
    0 7 * * * cd /root/by-bot && /root/by-bot/.venv/bin/python scripts/ai_morning_brief.py >> logs/ai_morning.log 2>&1

Зависит от:
    - runtime/trades_journal.jsonl
    - runtime/allocator_decisions.jsonl
    - runtime/scanner_full_snapshot.json (или setups_snapshot.json)
    - runtime/equity_snapshot.json
    - runtime/live_mirror/regime/orchestrator_state.json
    - .env: DEEPSEEK_API_KEY, TG_TOKEN, TG_CHAT
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request, parse, error


PROJECT_ROOT = Path("/root/by-bot")
RUNTIME = PROJECT_ROOT / "runtime"

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

TG_URL_TMPL = "https://api.telegram.org/bot{token}/sendMessage"


def _read_env(path: Path = PROJECT_ROOT / ".env") -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _read_jsonl_last_n(path: Path, n: int = 50, since_ts: int | None = None) -> list:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    out = []
    for line in lines[-n * 4:]:  # читаем с запасом, потом фильтруем
        try:
            obj = json.loads(line)
            if since_ts and obj.get("ts", 0) < since_ts:
                continue
            out.append(obj)
        except Exception:
            continue
    return out[-n:]


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def collect_context() -> dict:
    """Собирает context за последние 24 часа."""
    now = int(time.time())
    yesterday = now - 86400

    trades_24h = _read_jsonl_last_n(RUNTIME / "trades_journal.jsonl", n=100, since_ts=yesterday)
    allocator_24h = _read_jsonl_last_n(RUNTIME / "allocator_decisions.jsonl", n=200, since_ts=yesterday)
    scanner = _read_json(RUNTIME / "scanner_full_snapshot.json") or _read_json(RUNTIME / "setups_snapshot.json") or {}
    equity = _read_json(RUNTIME / "equity_snapshot.json") or {}
    regime = _read_json(RUNTIME / "live_mirror" / "regime" / "orchestrator_state.json") or {}
    alpaca_peaks = _read_json(RUNTIME / "alpaca_peaks.json") or {}

    pnl_24h = sum(float(t.get("pnl", 0) or 0) for t in trades_24h)
    win_count = sum(1 for t in trades_24h if float(t.get("pnl", 0) or 0) > 0)
    loss_count = sum(1 for t in trades_24h if float(t.get("pnl", 0) or 0) < 0)

    approved = sum(1 for d in allocator_24h if d.get("result") == "approved")
    blocked = sum(1 for d in allocator_24h if d.get("result") == "blocked")

    return {
        "trades_24h": trades_24h,
        "pnl_24h": pnl_24h,
        "win_count": win_count,
        "loss_count": loss_count,
        "allocator_approved": approved,
        "allocator_blocked": blocked,
        "allocator_mode": os.environ.get("ALLOCATOR_MODE", "auto"),
        "setups_current": (scanner.get("setups", []) or scanner.get("ranked", []))[:10],
        "regime": regime.get("regime", "?"),
        "regime_conf": regime.get("confidence", "?"),
        "macro": regime.get("macro", "?"),
        "btc_dominance": regime.get("btc_dominance", "?"),
        "bybit_equity": equity.get("bybit", "?"),
        "alpaca_equity": equity.get("alpaca", "?"),
        "alpaca_positions": equity.get("alpaca_positions", []),
        "alpaca_peaks": alpaca_peaks,
    }


def build_prompt(ctx: dict) -> str:
    setups_str = "\n".join(
        f"  - {s.get('symbol', '?')} {s.get('strategy', '?')}: {s.get('reason', '')[:80]}"
        for s in ctx["setups_current"][:5]
    ) or "  (нет активных setups)"

    alpaca_positions_str = "\n".join(
        f"  - {p.get('symbol', '?')}: qty={p.get('qty', '?')} pnl={p.get('unrealized_pnl_pct', '?')}%"
        for p in ctx["alpaca_positions"]
    ) or "  (нет позиций)"

    last_trades_str = "\n".join(
        f"  - {t.get('symbol', '?')} {t.get('side', '?')} pnl={t.get('pnl', 0):.2f} ({t.get('strategy', '?')})"
        for t in ctx["trades_24h"][-5:]
    ) or "  (трейдов нет)"

    return f"""Ты ИИ-оператор торгового бота. Анализируешь прошедшие 24 часа и даёшь УТРЕННИЙ ДАЙДЖЕСТ юзеру в Telegram. Будь конкретен, без воды, по-русски, максимум 8 строк.

ДАННЫЕ ЗА 24Ч:

Bybit equity: ${ctx['bybit_equity']}
Alpaca equity: ${ctx['alpaca_equity']}

Трейдов 24ч: {len(ctx['trades_24h'])} (wins {ctx['win_count']}, losses {ctx['loss_count']})
PnL 24ч: ${ctx['pnl_24h']:.2f}

Последние трейды:
{last_trades_str}

Alpaca позиции:
{alpaca_positions_str}

Allocator (mode={ctx['allocator_mode']}): {ctx['allocator_approved']} approved / {ctx['allocator_blocked']} blocked decisions

Текущий режим: {ctx['regime']} (conf {ctx['regime_conf']}), BTC dom {ctx['btc_dominance']}%, macro {ctx['macro']}

Топ setups сейчас:
{setups_str}

ФОРМАТ ОТВЕТА (строго):
📊 ВЧЕРА: <короткое резюме PnL + трейды>
📈 СЕГОДНЯ: <что в setups, какой режим>
💡 РЕКОМЕНДАЦИЯ: <одно конкретное действие — например "включи bypass_haircuts" / "не трогай ничего" / "проверь почему ATT1 не сигналит">
⚠️ ВНИМАНИЕ: <если есть что критично — иначе пропусти>

Не пиши «возможно», «вероятно». Говори прямо. Если данных мало — скажи «нужно больше дней наблюдений»."""


def call_deepseek(prompt: str, api_key: str) -> str:
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600,
        "temperature": 0.3,
    }
    data = json.dumps(body).encode("utf-8")
    req = request.Request(
        DEEPSEEK_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        out = json.loads(raw)
        return out["choices"][0]["message"]["content"].strip()
    except error.HTTPError as e:
        return f"❌ DeepSeek HTTP {e.code}: {e.read().decode('utf-8')[:200]}"
    except Exception as e:
        return f"❌ DeepSeek error: {e}"


def send_tg(text: str, token: str, chat: str):
    url = TG_URL_TMPL.format(token=token)
    body = parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = request.Request(url, data=body, method="POST")
    try:
        with request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"TG send error: {e}")


def main() -> int:
    env = _read_env()
    os.environ.update(env)

    api_key = env.get("DEEPSEEK_API_KEY")
    tg_token = env.get("TG_TOKEN")
    tg_chat = env.get("TG_CHAT")

    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set in .env")
        return 1
    if not tg_token or not tg_chat:
        print("ERROR: TG_TOKEN / TG_CHAT not set in .env")
        return 1

    ctx = collect_context()
    print(f"Context: {len(ctx['trades_24h'])} trades, ${ctx['pnl_24h']:.2f} pnl, {len(ctx['setups_current'])} setups")

    prompt = build_prompt(ctx)
    print(f"Prompt size: {len(prompt)} chars")

    reply = call_deepseek(prompt, api_key)
    print(f"DeepSeek reply ({len(reply)} chars):\n{reply}\n")

    # Префикс с датой
    today = datetime.now().strftime("%d.%m.%Y")
    full_msg = f"🌅 <b>Утренний дайджест {today}</b>\n\n{reply}\n\n— DeepSeek operator"

    send_tg(full_msg, tg_token, tg_chat)
    print("✅ Sent to TG")

    # Архив для аудита
    archive_dir = RUNTIME / "morning_briefs"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{datetime.now().strftime('%Y%m%d')}.txt").write_text(full_msg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
