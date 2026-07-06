"""AI context brief — give the ONBOARD AI our memory and house rules.

Diagnosis (2026-07-08): the bot's onboard AI recommends harmful actions
(enable unproven sleeves off one screener card, raise risk_mult without OOS,
directional ML) not because it is dumb, but because it lacks two things the
human+Claude+Codex team has: PROJECT MEMORY (which ideas already died at the
gates and why) and HOUSE RULES (activation must be earned through gates).

This module composes a compact, injectable brief (<4KB) from static rules +
runtime facts. Codex prepends it to the onboard AI's context. Optional
overrides live in runtime/ai_brief_extra.json:
    {"no_go": [...], "queue": [...], "clean_sample_since": "..."}
so the ledger keeps feeding fresh verdicts into the AI's head without code
changes. Fault-tolerant like the digest: missing files never break the brief.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["HOUSE_RULES", "DEFAULT_NO_GO", "build_brief", "compose_from_repo"]

HOUSE_RULES: List[str] = [
    "Включение стратегии/риска надо ЗАСЛУЖИТЬ: data-gate -> backtest -> stress-издержки -> "
    "time-OOS -> symbol-OOS -> shadow -> телеметрия -> tiny canary. Рекомендации в обход ворот запрещены.",
    "Одна красивая карта скринера / карман на выбранных монетах / tiny-N — НЕ эдж. "
    "Selection bias — главный убийца проекта (пойман 5+ раз: ARF2, ARS1, XAU, universe...).",
    "Risk_mult поднимается ТОЛЬКО по пре-регистрированной лестнице после N healthy live-сделок. "
    "Предлагать «поднять риск, слишком мало» без выборки — запрещено.",
    "Направленное ML-предсказание цены (4-8ч и т.п.) отвергнуто осознанно: наш ML = мета-лейблинг "
    "на СВОИХ размеченных сделках, после сотен примеров.",
    "Частота умножает ЗНАК ожидания: чаще торговать с минусом = быстрее слить.",
    "Redкий рукав в чужом режиме МОЛЧИТ по построению (short-only в bull) — это не поломка.",
    "Ты ПРЕДЛАГАЕШЬ, человек одобряет. Каждое предложение снабжай данными и указывай, какие "
    "ворота оно ещё не прошло.",
]

DEFAULT_NO_GO: List[str] = [
    "ARF2 failed-breakout (OOS-symbols -15R)", "ARS1/пила dynamic picker (216/216 FAIL)",
    "raw BOS/CHoCH (все стороны минус)", "XAU round_sweep (обе стороны)",
    "ATT1-long (PF 1.06)", "ATT1 universe +11 монет (PF 1.08 < 1.15)",
    "midterm v2/v3 на свежем окне", "HZBO long", "IVB1 в деньги (symbol-OOS FAIL; только shadow)",
    "FX фейды/EURUSD-вердикты на грязных данных", "каскады строгим триггером (0 входов — копить поток)",
]


def _load_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_brief(
    *,
    no_go: Optional[Sequence[str]] = None,
    queue: Optional[Sequence[str]] = None,
    clean_sample_since: str = "включения телеметрии (ATT1_EDGE_START_TS)",
    live_truth: Optional[Dict[str, Any]] = None,
) -> str:
    lines: List[str] = ["=== ВВОДНАЯ ДЛЯ БОРТОВОГО ИИ (правила дома + память проекта) ==="]

    lines.append("\n-- ПРАВИЛА (нарушать нельзя, предложения в обход = отклоняются автоматически):")
    lines += [f"{i}. {r}" for i, r in enumerate(HOUSE_RULES, 1)]

    lines.append("\n-- УЖЕ УМЕРЛО НА ГЕЙТАХ (не предлагай включать в текущем виде):")
    lines += [f"- {x}" for x in (no_go if no_go is not None else DEFAULT_NO_GO)]

    lines.append(
        f"\n-- ДАННЫЕ: forensics до {clean_sample_since} включает ГРЯЗНУЮ эпоху "
        "(missing_candles, старые ноги) — выводы «бот убыточен» по этому окну НЕВАЛИДНЫ. "
        "Честная выборка = сделки после этой отметки; при N<20 вердиктов не существует."
    )

    if live_truth:
        lines.append("\n-- LIVE-ПРАВДА СЕЙЧАС:")
        for k, v in live_truth.items():
            lines.append(f"- {k}: {v}")

    if queue:
        lines.append("\n-- ЧТО УЖЕ В ОЧЕРЕДИ (не дублируй как «новую идею»):")
        lines += [f"- {q}" for q in queue]

    lines.append(
        "\n-- ФОРМАТ ТВОИХ ПРЕДЛОЖЕНИЙ: {что, данные-обоснование, какие ворота пройдены/не пройдены, "
        "ожидаемый следующий шаг}. Предложение без указания ворот считается неполным."
    )
    return "\n".join(lines)[:3900]


def compose_from_repo(root: Path | str = ".") -> str:
    """Build the brief from runtime overrides + heartbeat facts (fault-tolerant)."""
    root = Path(root)
    extra = _load_json(root / "runtime" / "ai_brief_extra.json") or {}
    hb = _load_json(root / "runtime" / "bot_heartbeat.json")
    live: Dict[str, Any] = {}
    if isinstance(hb, dict):
        live["режим"] = hb.get("regime", "?")
        live["торгует"] = bool(hb.get("trade_on")) and not bool(hb.get("dry_run"))
        live["open_trades"] = hb.get("open_trades", "?")
    return build_brief(
        no_go=extra.get("no_go"),
        queue=extra.get("queue"),
        clean_sample_since=str(extra.get("clean_sample_since")
                               or "включения телеметрии (ATT1_EDGE_START_TS)"),
        live_truth=live or None,
    )


if __name__ == "__main__":  # pragma: no cover - CLI for injection
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    print(compose_from_repo(args.root))
