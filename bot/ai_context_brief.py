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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["HOUSE_RULES", "DEFAULT_NO_GO", "build_brief", "compose_from_repo"]

# Бриф режется по символам. Очередь исследований стоит последней и лимитирована,
# чтобы обрезание никогда не съедало правила дома и формат ответа.
BRIEF_MAX_CHARS = 7000
QUEUE_MAX_ITEMS = 14
NO_GO_MAX_ITEMS = 18

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
    "Фильтр (новости/режим/киты/китовые потоки) МОЖЕТ помочь, но НЕ создаёт эдж из шума. "
    "Разрешено: фильтр пре-регистрирован ДО прогона, отсекает структурно опознаваемый режим потерь, "
    "и отфильтрованная версия проходит ПОЛНЫЙ гейт самостоятельно, а не только улучшает метрику. "
    "Запрещено: перебирать фильтры на убыточной логике, пока какой-нибудь не выведет её в плюс — "
    "это подгонка. Замер: режим-фильтр на мёртвой логике сдвинул PF 0.58 -> 0.59, то есть никак.",
    "Внутри ОДНОГО семейства параметров переключение на «то, что сейчас лучше идёт» ПРОИГРЫВАЕТ простому удержанию всех вариантов (замерено: адаптив +4/+87/+101% против +108% у равного портфеля, просадка хуже). Не предлагай «переключиться на лучший конфиг». Перевзвешивание уместно только МЕЖДУ классами стратегий, где различия структурные, а не шумовые.",
    "Маркет-мейкинг на ликвидных перпах Bybit при стандартной мейкерской комиссии НЕВОЗМОЖЕН арифметически: медианный спред 0.13-3.19 bps против 4 bps круга. Идеальный ММ без единого промаха теряет -1.09 bps. Предлагать ММ можно ТОЛЬКО с мейкерским ребейтом или на символе со спредом >8 bps.",
    "Издержки исполнения могут быть решающими, а не второстепенными: у портфельного моментума тейкер даёт -6.8% на свежей половине, мейкер +23.7%. Прежде чем хоронить кандидата — проверь, не комиссия ли его убила.",
    "ПЕРЕКРЫВАЮЩИЕСЯ ОКНА — отдельный класс самообмана. События, взятые с каждого бара, "
    "коррелированы: размер выборки завышен, уверенность ложная. Замер: фейд импульса дал +14 bps с перекрытием и +0.25 bps без него — разница в 56 раз, PF 1.002, t=0.06. "
    "Событийное исследование обязано использовать НЕПЕРЕСЕКАЮЩИЕСЯ окна до того, как результат назван кандидатом.",
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
    research_truth: Optional[Sequence[str]] = None,
) -> str:
    lines: List[str] = ["=== ВВОДНАЯ ДЛЯ БОРТОВОГО ИИ (правила дома + память проекта) ==="]

    lines.append("\n-- ПРАВИЛА (нарушать нельзя, предложения в обход = отклоняются автоматически):")
    lines += [f"{i}. {r}" for i, r in enumerate(HOUSE_RULES, 1)]

    lines.append(
        f"\n-- ДАННЫЕ: forensics до {clean_sample_since} включает ГРЯЗНУЮ эпоху "
        "(missing_candles, старые ноги) — выводы «бот убыточен» по этому окну НЕВАЛИДНЫ. "
        "Честная выборка = сделки после этой отметки; при N<20 вердиктов не существует."
    )

    if live_truth:
        lines.append("\n-- LIVE-ПРАВДА СЕЙЧАС:")
        for k, v in live_truth.items():
            lines.append(f"- {k}: {v}")

    if research_truth:
        lines.append("\n-- ЛОКАЛЬНАЯ RESEARCH-ПРАВДА (НЕ LIVE И НЕ РАЗРЕШЕНИЕ НА РИСК):")
        lines += [f"- {item}" for item in research_truth]

    rejected = list(no_go if no_go is not None else DEFAULT_NO_GO)
    lines.append("\n-- УЖЕ УМЕРЛО НА ГЕЙТАХ (не предлагай включать в текущем виде):")
    lines += [f"- {x}" for x in rejected[:NO_GO_MAX_ITEMS]]
    if len(rejected) > NO_GO_MAX_ITEMS:
        lines.append(
            f"- ... и ещё {len(rejected) - NO_GO_MAX_ITEMS} no-go записей "
            "(полный список: configs/ai_operator_canonical_state.json)"
        )

    lines.append(
        "\n-- ФОРМАТ ТВОИХ ПРЕДЛОЖЕНИЙ: {что, данные-обоснование, какие ворота пройдены/не пройдены, "
        "ожидаемый следующий шаг}. Предложение без указания ворот считается неполным."
    )

    if queue:
        # Очередь идёт ПОСЛЕДНЕЙ и ограничена: при переполнении режется именно она,
        # а правила дома и формат ответа сохраняются всегда.
        shown = list(queue)[:QUEUE_MAX_ITEMS]
        lines.append("\n-- ЧТО УЖЕ В ОЧЕРЕДИ (не дублируй как «новую идею»):")
        lines += [f"- {q}" for q in shown]
        if len(queue) > len(shown):
            lines.append(f"- ... и ещё {len(queue) - len(shown)} пунктов "
                         "(полный список: configs/ai_operator_canonical_state.json)")

    return "\n".join(lines)[:BRIEF_MAX_CHARS]


def compose_from_repo(root: Path | str = ".") -> str:
    """Build the brief from runtime overrides + heartbeat facts (fault-tolerant)."""
    root = Path(root)
    extra = _load_json(root / "runtime" / "ai_brief_extra.json") or {}
    canonical = _load_json(root / "configs" / "ai_operator_canonical_state.json") or {}
    research_overlay = _load_json(root / "configs" / "ai_operator_research_overlay.json") or {}
    hb = _load_json(root / "runtime" / "bot_heartbeat.json")
    live: Dict[str, Any] = {}
    if isinstance(hb, dict):
        hb_ts = hb.get("ts")
        hb_age = int(time.time() - float(hb_ts)) if isinstance(hb_ts, (int, float)) else None
        runtime_cfg = hb.get("strategy_runtime_config")
        runtime_cfg = runtime_cfg if isinstance(runtime_cfg, dict) else {}
        enabled = runtime_cfg.get("enabled") if isinstance(runtime_cfg.get("enabled"), dict) else {}
        risk_mult = runtime_cfg.get("risk_mult") if isinstance(runtime_cfg.get("risk_mult"), dict) else {}
        money = sorted(
            str(name) for name, value in risk_mult.items()
            if bool(enabled.get(name)) and isinstance(value, (int, float)) and float(value) > 0.0
        )
        live["режим"] = hb.get("regime", "?")
        live["торгует"] = bool(hb.get("trade_on")) and not bool(hb.get("dry_run"))
        live["open_trades"] = hb.get("open_trades", "?")
        live["heartbeat_age_sec"] = hb_age if hb_age is not None else "unknown"
        live["live_money_sleeves_by_heartbeat"] = money
        live["strategy_runtime_summary"] = {
            "enabled": sorted(str(name) for name, value in enabled.items() if bool(value)),
            "positive_risk_mult": {
                str(name): value
                for name, value in risk_mult.items()
                if isinstance(value, (int, float)) and float(value) > 0.0
            },
        }
        if hb_age is None or hb_age > 120:
            live["TRUTH_WARNING"] = "STALE_HEARTBEAT_NO_LIVE_CONTROL_RECOMMENDATIONS"
    canonical_live = canonical.get("live") if isinstance(canonical.get("live"), dict) else {}
    if canonical_live:
        live["human_reviewed_canonical_live"] = canonical_live
    canonical_no_go = list(canonical.get("no_promotion") or [])
    extra_no_go = extra.get("no_go")
    no_go = list(extra_no_go) if isinstance(extra_no_go, list) else list(DEFAULT_NO_GO)
    no_go.extend(x for x in canonical_no_go if x not in no_go)
    canonical_queue = list(canonical.get("research_queue") or [])
    extra_queue = extra.get("queue")
    queue = list(extra_queue) if isinstance(extra_queue, list) else []
    queue.extend(x for x in canonical_queue if x not in queue)
    research_truth: List[str] = []
    if isinstance(research_overlay, dict):
        generated_at_epoch = research_overlay.get("generated_at_epoch")
        max_age_hours = research_overlay.get("max_age_hours", 48)
        overlay_age_h: Optional[float] = None
        if isinstance(generated_at_epoch, (int, float)):
            overlay_age_h = max(0.0, (time.time() - float(generated_at_epoch)) / 3600.0)
        if overlay_age_h is None or overlay_age_h > float(max_age_hours):
            research_truth.append(
                "RESEARCH_OVERLAY_STALE: не утверждай, что локальные процессы всё ещё активны; "
                "нужна новая синхронизация с owner host"
            )
        else:
            facts = research_overlay.get("facts")
            if isinstance(facts, list):
                research_truth.extend(str(item) for item in facts[:12])
    return build_brief(
        no_go=no_go,
        queue=queue,
        clean_sample_since=str(extra.get("clean_sample_since")
                               or "включения телеметрии (ATT1_EDGE_START_TS)"),
        live_truth=live or None,
        research_truth=research_truth or None,
    )


if __name__ == "__main__":  # pragma: no cover - CLI for injection
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    print(compose_from_repo(args.root))
