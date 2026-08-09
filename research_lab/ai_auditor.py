"""НОЧНОЙ АУДИТОР ПРОЕКТА.

Замысел. Локальная модель должна круглосуточно просматривать проект и искать
уязвимости. Но начинать с модели неправильно: большая часть находок, которые
реально нужны, **детерминированы** и модели не требуют вовсе.

Поэтому здесь два слоя:

  СЛОЙ 1 (работает всегда, модель не нужна)
      проверки, которые либо находят расхождение, либо нет. Ошибиться
      они не могут — сравнивают заявленное с фактическим.

  СЛОЙ 2 (опционально, если поднята локальная модель)
      модель читает то, что не формализуется: журналы, диффы, тексты
      отчётов. Её находки помечаются отдельно и ВСЕГДА требуют проверки.

ФОРМАТ НАХОДКИ — обязательный. Находка без поля «как опровергнуть»
не принимается: это то же правило, по которому мы работаем с гипотезами,
применённое к самому аудитору.

ИЗМЕРЕНИЕ АУДИТОРА. Каждая находка получает статус confirmed/rejected
человеком. Доля подтверждений считается по накопленным файлам:
  выше 30% — расширяем охват; ниже 10% — сужаем или отключаем.

Запуск:
    python3 research_lab/ai_auditor.py                 # только слой 1
    python3 research_lab/ai_auditor.py --with-model    # + локальная модель
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "runtime", "ai_audit")
MONOLITH = os.path.join(ROOT, "smart_pump_reversal_bot.py")


@dataclass
class Finding:
    check: str
    what: str                    # что найдено, одной строкой
    where: str                   # файл:строка или запрос к данным
    why: str                     # механизм, а не «выглядит подозрительно»
    how_to_verify: str           # команда, которую можно запустить
    how_to_falsify: str          # что должно быть видно, если находка ложная
    severity: str = "medium"     # low | medium | high
    source: str = "deterministic"  # deterministic | model
    status: str = "new"          # new | confirmed | rejected | unverifiable


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except Exception:
        return ""


def _age_days(path: str) -> float | None:
    try:
        return (dt.datetime.now().timestamp() - os.path.getmtime(path)) / 86400
    except Exception:
        return None


# ────────────────────────── СЛОЙ 1: детерминированные ──────────────────────

def live_reachable_modules(mono: str) -> set[str]:
    """Модули bot/, достижимые из монолита ТРАНЗИТИВНО.

    Важно: модуль может не упоминаться в монолите напрямую, но импортироваться
    другим модулем, который в живом пути есть. Первая версия этой проверки
    этого не учитывала и давала ложные срабатывания (например position_sizing
    импортируется из risk_manager и decision_bus). Считаем замыкание.
    """
    all_mods = {os.path.basename(p)[:-3]
                for p in glob.glob(os.path.join(ROOT, "bot", "*.py"))
                if not os.path.basename(p).startswith("_")}
    imports: dict[str, set[str]] = {}
    for m in all_mods:
        txt = _read(os.path.join(ROOT, "bot", f"{m}.py"))
        found = set()
        for other in all_mods:
            if other == m:
                continue
            if re.search(rf"\b(?:from\s+bot\.{other}\b|import\s+bot\.{other}\b"
                         rf"|from\s+\.{other}\b|import\s+{other}\b)", txt):
                found.add(other)
        imports[m] = found

    frontier = {m for m in all_mods
                if re.search(rf"\b(?:from\s+bot\.{m}\b|import\s+bot\.{m}\b)", mono)}
    seen = set(frontier)
    while frontier:
        nxt = set()
        for m in frontier:
            for dep in imports.get(m, ()):
                if dep not in seen:
                    seen.add(dep)
                    nxt.add(dep)
        frontier = nxt
    return seen


def check_claimed_but_unwired(mono: str) -> list[Finding]:
    """Модуль покрыт тестами и обсуждается, но недостижим из живого пути.

    ПОПРАВКА ПОСЛЕ СПОТ-ПРОВЕРКИ. Первая версия заявляла «отчёт утверждает,
    что модуль подключён». Ручная проверка четырёх находок показала, что
    в трёх случаях отчёт утверждает ПРОТИВОПОЛОЖНОЕ («написан и не подключён»,
    «не используется в проде»). Факт (модуль недостижим) был верен, а
    формулировка — нет.

    Поэтому проверка переименована в то, что она действительно измеряет:
    модуль существует, покрыт тестами, обсуждается в отчётах — и при этом
    недостижим из живого пути. Это инвентарная проблема, а не ложь отчётов.
    """
    out = []
    mods = [os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "bot", "*.py"))
            if not os.path.basename(p).startswith("_")]
    reachable = live_reachable_modules(mono)
    orphans = []
    for mod in mods:
        if mod in reachable:
            continue                                  # достижим транзитивно
        tested = bool(glob.glob(os.path.join(ROOT, "tests", f"*{mod}*")))
        mentions = sum(1 for rep in glob.glob(os.path.join(ROOT, "reports", "*.md"))
                       if mod in _read(rep))
        if tested and mentions >= 2:
            orphans.append((mod, mentions))
    if not orphans:
        return out
    orphans.sort(key=lambda x: -x[1])
    names = ", ".join(f"{m} ({n} отч.)" for m, n in orphans[:6])
    out.append(Finding(
        check="tested_but_unreachable",
        what=f"{len(orphans)} модулей покрыты тестами и обсуждаются в отчётах, "
             f"но недостижимы из живого пути",
        where="bot/ — например: " + names,
        why="это механизм центральной патологии проекта: строим модули, "
            "они не подключаются, ИИ и человек про них забывают, "
            "и вместо соединения существующего строится новое",
        how_to_verify="python3 -c \"import sys;sys.path.insert(0,'.');"
                      "from research_lab.ai_auditor import live_reachable_modules,_read;"
                      "print(sorted(live_reachable_modules(_read('smart_pump_reversal_bot.py'))))\"",
        how_to_falsify="если модуль вызывается через importlib по строке "
                       "или из scripts/, а не из монолита — находка ложная",
        severity="high",
    ))
    return out


def check_stale_runtime(paths_days: dict[str, float]) -> list[Finding]:
    """Файлы, которые обязаны обновляться, но перестали."""
    out = []
    for rel, max_days in paths_days.items():
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            out.append(Finding(
                check="stale_runtime",
                what=f"`{rel}` отсутствует",
                where=rel,
                why="потребители читают этот файл и получат пустоту или старое",
                how_to_verify=f"ls -la {rel}",
                how_to_falsify="если файл переехал — обновить путь в проверке",
                severity="medium",
            ))
            continue
        age = _age_days(p)
        if age is not None and age > max_days:
            out.append(Finding(
                check="stale_runtime",
                what=f"`{rel}` не обновлялся {age:.1f} дней (порог {max_days})",
                where=rel,
                why="устаревшие данные опаснее отсутствующих: отсутствие видно, "
                    "устаревание нет — потребитель считает их свежими",
                how_to_verify=f"ls -la {rel}",
                how_to_falsify="если файл обновляется только по событию, "
                               "которого не было — находка ложная",
                severity="high" if age > max_days * 3 else "medium",
            ))
    return out


def check_config_drift(mono: str) -> list[Finding]:
    """Значения в отчётах против фактических дефолтов в коде."""
    out = []
    pat = re.compile(r"^([A-Z][A-Z0-9_]{3,})\s*=\s*([0-9.]+)\s*(?:#|$)", re.M)
    code_vals = {m.group(1): m.group(2) for m in pat.finditer(mono)}
    watch = ("CAP_NOTIONAL_TO_EQUITY", "RESERVE_EQUITY_FRAC", "MAX_POSITIONS",
             "BYBIT_LEVERAGE", "ENTRY_RESERVATION_TTL_SEC")
    for name in watch:
        if name not in code_vals:
            continue
        val = code_vals[name]
        for rep in sorted(glob.glob(os.path.join(ROOT, "reports", "*.md")),
                          key=os.path.getmtime, reverse=True)[:25]:
            txt = _read(rep)
            for m in re.finditer(rf"{name}\s*=\s*([0-9.]+)", txt):
                if m.group(1) != val:
                    out.append(Finding(
                        check="config_drift",
                        what=f"{name}: в коде `{val}`, в отчёте `{m.group(1)}`",
                        where=f"smart_pump_reversal_bot.py vs {os.path.basename(rep)}",
                        why="решения принимаются по отчёту, а торгует код; "
                            "расхождение означает решение по неверным данным",
                        how_to_verify=f'grep -n "^{name}" smart_pump_reversal_bot.py',
                        how_to_falsify="если отчёт описывает исторический момент "
                                       "или другое окружение — находка ложная",
                        severity="medium",
                    ))
                    break
    return out


def check_data_collectors() -> list[Finding]:
    """Сборщики данных, которые перестали писать."""
    out = []
    targets = {
        "runtime/liquidations/bybit_liquidations.jsonl": 1.0,
    }
    for rel, max_days in targets.items():
        p = os.path.join(ROOT, rel)
        age = _age_days(p)
        if age is None:
            continue
        if age > max_days:
            out.append(Finding(
                check="data_collector_stopped",
                what=f"сборщик не пишет в `{rel}` уже {age:.1f} дней",
                where=rel,
                why="данные бесплатны и непрерывны; каждый день простоя — "
                    "безвозвратно потерянная выборка, которую нельзя добрать задним числом",
                how_to_verify=f"wc -l {rel}   # повторить через минуту, число должно расти",
                how_to_falsify="если сбор намеренно остановлен — отметить rejected "
                               "и добавить файл в исключения",
                severity="high",
            ))
    return out


def check_untested_research_scripts() -> list[Finding]:
    """Скрипты research_lab без самопроверки — риск тихой ошибки.

    АГРЕГИРУЕТСЯ в одну находку. Первая версия выдавала по находке на файл
    и утопила 21 важную находку в 81 мелкой. Сто находок — это не аудит,
    это шум: их никто не разметит, и метрика полезности потеряет смысл.
    """
    bad = []
    for p in sorted(glob.glob(os.path.join(ROOT, "research_lab", "*.py"))):
        name = os.path.basename(p)
        if name.startswith("_"):
            continue
        txt = _read(p)
        if "_self_test" in txt or "assert" in txt:
            continue
        bad.append(name)
    if not bad:
        return []
    total = len(glob.glob(os.path.join(ROOT, "research_lab", "*.py")))
    return [Finding(
        check="research_without_selftest",
        what=f"{len(bad)} из {total} скриптов research_lab без единой проверки",
        where="research_lab/ — например: " + ", ".join(sorted(bad)[:5]),
        why="за неделю три ошибки нашлись в инструменте, а не в стратегиях; "
            "скрипт без самопроверки даёт цифры, которые некому опровергнуть",
        how_to_verify="grep -L assert research_lab/*.py | wc -l",
        how_to_falsify="если скрипты покрыты тестами в tests/ — находка ложная",
        severity="low",
    )]


# ──────────────────────────── СЛОЙ 2: модель ───────────────────────────────

def parse_model_payload(text: str) -> list[Finding]:
    """Parse Ollama's bounded JSON response into proposal-only findings."""
    cleaned = re.sub(r"<think>.*?</think>", "", str(text or ""), flags=re.S).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except (TypeError, ValueError):
        return []
    rows = payload.get("findings") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    findings: list[Finding] = []
    for raw in rows[:3]:
        if not isinstance(raw, dict):
            continue
        required = ("what", "where", "why", "how_to_verify", "how_to_falsify")
        if any(not str(raw.get(key) or "").strip() for key in required):
            continue
        severity = str(raw.get("severity") or "low").lower()
        if severity not in {"low", "medium", "high"}:
            severity = "low"
        findings.append(Finding(
            check="model_review",
            what=str(raw["what"]).strip()[:300],
            where=str(raw["where"]).strip()[:300],
            why=str(raw["why"]).strip()[:600],
            how_to_verify=str(raw["how_to_verify"]).strip()[:600],
            how_to_falsify=str(raw["how_to_falsify"]).strip()[:600],
            severity=severity,
            source="model",
        ))
    return findings


def model_findings(
    model: str,
    base_url: str,
    deterministic: list[Finding] | None = None,
) -> tuple[list[Finding], str]:
    """Опционально: локальная модель через OpenAI-совместимый API (Ollama).

    Молча возвращает пустой список, если модель недоступна — слой 1
    от этого не страдает.
    """
    try:
        import urllib.request
    except Exception:
        return [], ""
    try:
        log = subprocess.run(
            ["git", "-C", ROOT, "log", "--since=1 day ago", "--stat"],
            capture_output=True, text=True, timeout=20).stdout[:6000]
    except Exception:
        log = ""
    if not log.strip():
        return [], ""
    deterministic_context = json.dumps(
        [asdict(item) for item in list(deterministic or [])[:8]],
        ensure_ascii=False,
    )
    prompt = (
        "Ты proposal-only аудитор торгового бота. Проанализируй изменения за "
        "сутки и детерминированные находки. Верни ТОЛЬКО JSON вида "
        "{\"findings\":[{\"what\":\"...\",\"where\":\"реальный путь/строка\","
        "\"why\":\"механизм\",\"how_to_verify\":\"безопасная read-only команда\","
        "\"how_to_falsify\":\"что опровергает\",\"severity\":\"low|medium|high\"}]}. "
        "Максимум три находки. Не повторяй детерминированную находку без новой "
        "проверяемой детали. Не придумывай файлы. Не предлагай менять риск или "
        "ордера. Если новых кандидатов нет, верни {\"findings\":[]}.\n\n"
        "DETERMINISTIC:\n" + deterministic_context + "\n\nGIT:\n" + log
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }).encode()
    try:
        req = urllib.request.Request(
            f"{base_url}/api/chat", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            txt = json.loads(r.read())["message"]["content"]
    except Exception as e:
        print(f"[модель недоступна: {e}] — слой 1 отработал без неё")
        return [], ""
    return parse_model_payload(txt), txt


# ──────────────────────────────── отчёт ────────────────────────────────────

def render(findings: list[Finding], model_text: str = "") -> str:
    today = dt.date.today().isoformat()
    by_sev = {"high": [], "medium": [], "low": []}
    for f in findings:
        by_sev.setdefault(f.severity, []).append(f)
    lines = [f"# Аудит проекта — {today}", ""]
    lines.append(f"Находок: **{len(findings)}** "
                 f"(высоких {len(by_sev['high'])}, средних {len(by_sev['medium'])}, "
                 f"низких {len(by_sev['low'])})")
    lines += ["", "Разметить каждую находку как `confirmed` или `rejected`. "
                  "Доля подтверждений — метрика полезности аудитора.", ""]
    n = 0
    for sev in ("high", "medium", "low"):
        for f in by_sev[sev]:
            n += 1
            lines += [
                f"## {n}. [{sev}] {f.what}",
                "",
                f"- **где:** `{f.where}`",
                f"- **почему:** {f.why}",
                f"- **проверить:** `{f.how_to_verify}`",
                f"- **опровергнуть:** {f.how_to_falsify}",
                f"- **источник:** {f.source}",
                f"- **статус:** `{f.status}`  <!-- заменить на confirmed/rejected -->",
                "",
            ]
    if model_text:
        lines += ["---", "", "## Текст модели (требует проверки)", "",
                  "```", model_text.strip()[:4000], "```", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-model", action="store_true")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--base-url", default="http://localhost:11434")
    ap.add_argument("--print-only", action="store_true")
    args = ap.parse_args()

    mono = _read(MONOLITH)
    findings: list[Finding] = []
    findings += check_claimed_but_unwired(mono)
    # Audit the atomic VPS mirror actually consumed by local Web/AI tooling.
    # The old runtime/ai_context path is a historical local build and its age
    # does not prove that the VPS context is stale.
    findings += check_stale_runtime({
        "runtime/live_mirror/ai_context/full_context.json": 0.05,
        "runtime/live_mirror/sync_bundle_manifest.json": 0.05,
    })
    findings += check_config_drift(mono)
    findings += check_data_collectors()
    findings += check_untested_research_scripts()

    model_text = ""
    if args.with_model:
        mf, model_text = model_findings(args.model, args.base_url, findings)
        findings += mf

    report = render(findings, model_text)
    if args.print_only:
        print(report)
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{dt.date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report)
    with open(path.replace(".md", ".json"), "w", encoding="utf-8") as fh:
        json.dump([asdict(f) for f in findings], fh, ensure_ascii=False, indent=2)
    print(f"находок: {len(findings)} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
