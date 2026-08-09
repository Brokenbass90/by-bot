#!/usr/bin/env python3
"""Interactive, proposal-only project chat backed by local Ollama.

The model receives a bounded allowlist of project status artifacts.  It never
reads environment files, API keys, broker credentials, or live order methods.
This is a human-facing analysis surface, not a trading authority.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SAFE_CONTEXT_FILES = (
    "reports/CODEX_PROGRESS_2026_08_09.md",
    "PROJECT_MAP.md",
    "reports/PROJECT_STATE_LEDGER.md",
    "reports/RESEARCH_STATION_LTC_AND_FX_GRID_2026_08_08.md",
    "runtime/local_research_station/status.json",
    "runtime/project_audit/supervisor_status.json",
    "runtime/project_audit/registry.md",
    "runtime/alpaca_adaptive_v1_shadow_latest.json",
    "runtime/funding_positioning_dynamic_shadow_summary.json",
    "runtime/funding_positioning_post_n42_frozen_summary.json",
    "runtime/fx_smart_grid_v1_latest.json",
)

SYSTEM_RULES = """Ты локальный AI-аудитор торговой станции. Отвечай по-русски.
Твоя роль proposal-only: анализировать, объяснять и предлагать проверки.
Ты не имеешь права открывать ордера, менять риск, ключи, live-конфиги или
утверждать, что исследовательский результат готов к деньгам. Различай Git,
деплой, heartbeat, shadow и прямую брокерскую истину. Всегда называй дату и
источник изменчивого факта. Если контекст не доказывает утверждение, прямо
говори «не подтверждено текущими источниками». Не обещай доходность.
"""


def verified_status_text() -> str:
    """Return deterministic facts without asking the language model."""
    return "\n".join((
        "VERIFIED STATUS (без генерации Ollama)",
        "- Весь проект проверен: НЕТ.",
        "- Аудит: 272 записи; 210 актуальных; 5 требуют разбора; 187 inventory.",
        "- SBR1 bug: tf_ts в ms, retest-window ошибочно прибавлялся в sec.",
        "- SBR1 fix: retest_window_bars * tf_seconds * 1000; 2 unit-теста.",
        "- SBR1 liveness после fix: 9 сигналов на SOLUSDT.",
        "- SBR1 economics 120d SOL: 10 сделок, net -0.65%, PF 0.305; не кандидат.",
        "- FX smart-grid v1: stress PF 0.8783, 0/4 positive folds; rebuild/close.",
        "Изменчивый live truth проверяйте отдельным direct broker/VPS запросом.",
    ))


def _read_bounded(path: Path, limit: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _fact_index(root: Path) -> str:
    station = _json_object(root / "runtime/local_research_station/status.json")
    audit = _json_object(root / "runtime/project_audit/supervisor_status.json")
    fx_grid = _json_object(root / "runtime/fx_smart_grid_v1_latest.json")
    alpaca = _json_object(root / "runtime/alpaca_adaptive_v1_shadow_latest.json")
    funding = _json_object(root / "runtime/funding_positioning_dynamic_shadow_summary.json")
    facts = {
        "verification_scope": {
            "whole_project_verified": False,
            "audit_registry_total": 272,
            "audit_registry_current": 210,
            "audit_registry_needs_review": 5,
            "technology_inventory_items": 187,
        },
        "validated_repairs": {
            "sloped_break_retest_v1": {
                "bug": "tf_ts is milliseconds but retest window was added as seconds",
                "fix": "multiply retest_window_bars * tf_seconds by 1000",
                "unit_tests": 2,
                "liveness_after_fix_signals": 9,
                "economic_check": {
                    "symbol": "SOLUSDT",
                    "days": 120,
                    "trades": 10,
                    "net_pct": -0.65,
                    "profit_factor": 0.305,
                    "candidate_for_money": False,
                },
            },
        },
        "research_station": {
            "generated_at_utc": station.get("generated_at_utc"),
            "healthy": station.get("healthy"),
            "summary": station.get("summary"),
            "research_only": station.get("research_only"),
        },
        "project_audit": {
            "last_success_utc": audit.get("last_success_utc"),
            "proposal_only": audit.get("proposal_only"),
            "live_mutation": audit.get("live_mutation"),
            "registry_summary": audit.get("registry_summary"),
        },
        "fx_smart_grid": {
            "generated_at_utc": fx_grid.get("generated_at_utc"),
            "decision": fx_grid.get("decision"),
            "best_stress": fx_grid.get("best_stress"),
        },
        "alpaca_adaptive": {
            "generated_at_utc": alpaca.get("generated_at_utc"),
            "mode": alpaca.get("mode"),
            "reason": alpaca.get("reason"),
            "decision_id": alpaca.get("decision_id"),
        },
        "funding_shadow": {
            "generated_at_utc": funding.get("generated_at_utc"),
            "trials": funding.get("trials"),
            "closed": funding.get("closed"),
            "open": funding.get("open"),
            "capital_authorized": funding.get("capital_authorized"),
        },
    }
    return "FACT_INDEX=" + json.dumps(facts, ensure_ascii=False, sort_keys=True)


def build_project_context(
    root: Path = ROOT,
    *,
    per_file_limit: int = 6_000,
    total_limit: int = 30_000,
) -> tuple[str, list[str]]:
    chunks: list[str] = []
    sources: list[str] = []
    used = 0
    for relative in SAFE_CONTEXT_FILES:
        path = root / relative
        if not path.is_file():
            continue
        remaining = total_limit - used
        if remaining <= 0:
            break
        body = _read_bounded(path, min(per_file_limit, remaining))
        if not body:
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            modified = "unknown"
        block = f"\n--- SOURCE {relative} mtime_utc={modified} ---\n{body}\n"
        chunks.append(block)
        sources.append(relative)
        used += len(block)
    header = (
        f"CONTEXT_GENERATED_UTC={datetime.now(timezone.utc).isoformat()}\n"
        "Only the explicitly listed status and documentation files follow.\n"
        + _fact_index(root)
        + "\n"
    )
    return header + "".join(chunks), sources


def ollama_chat(
    messages: list[dict[str, str]],
    *,
    model: str,
    base_url: str,
    timeout: float = 180.0,
) -> str:
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    message = body.get("message") if isinstance(body.get("message"), dict) else {}
    content = str(message.get("content") or "").strip()
    if not content:
        raise RuntimeError("Ollama returned an empty response")
    return content


def _messages(context: str, history: list[dict[str, str]], question: str) -> list[dict[str, str]]:
    # Bound conversational memory so a long terminal session cannot exhaust
    # the local model's context window.
    return [
        {"role": "system", "content": SYSTEM_RULES + "\n" + context},
        *history[-12:],
        {"role": "user", "content": question},
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--once", default="", help="Ask one question and exit")
    parser.add_argument("--no-project-context", action="store_true")
    args = parser.parse_args()

    context, sources = ("", []) if args.no_project_context else build_project_context()
    history: list[dict[str, str]] = []

    print(f"Local Trading Station AI | model={args.model} | proposal-only")
    print(f"Project sources loaded: {len(sources)}")
    print("Commands: /status, /refresh, /sources, /clear, /exit")

    def ask(question: str) -> str:
        answer = ollama_chat(
            _messages(context, history, question),
            model=args.model,
            base_url=args.base_url,
        )
        history.extend((
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ))
        return answer

    if args.once:
        print(ask(args.once))
        return 0

    while True:
        try:
            question = input("\nВы> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nЗавершено.")
            return 0
        if not question:
            continue
        if question == "/exit":
            return 0
        if question == "/clear":
            history.clear()
            print("История беседы очищена.")
            continue
        if question == "/status":
            print(verified_status_text())
            continue
        if question == "/sources":
            print("\n".join(sources) if sources else "Контекст отключён.")
            continue
        if question == "/refresh":
            context, sources = build_project_context()
            print(f"Контекст обновлён: {len(sources)} источников.")
            continue
        try:
            print("\nOllama> " + ask(question))
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
            print(f"\nOllama недоступна: {exc}", file=sys.stderr)
            print("Проверьте: brew services start ollama", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
