# Живая управляющая петля — блупринт (2026-07-03, Claude). Динамика + ИИ-надзор в рельсах.

Цель: собрать наши протестированные модули в РАБОТАЮЩУЮ петлю, чтобы отбор был динамическим
(не хардкод-список -> не деградирует), а ИИ надзирал и ПРЕДЛАГАЛ, человек одобрял. Это план
ВПИСЫВАНИЯ (Codex), не новый код. Модули готовы, петля — нет.

## A. Вход каждого рукава (на каждом баре/цикле) — ДИНАМИЧЕСКИ
1. Динамический отбор символов: scanner по УСЛОВИЮ (range_scanner для флет-ног; аналог по
   условию для structure/failed-breakout) -> список «где сетап+режим совпали СЕЙЧАС».
   НИКАКИХ фикс-списков монет в live.
2. Сигнал ноги (failed_breakout / retest_quality / structure_break / breakout_confirm ...).
3. Гейты: regime_hmm.regime_gate (блок high_vol, risk_scalar) + range_filter/elder конфлюэнс.
4. Вход: level_entry (или immediate для reclaim).
5. Размер: risk_manager.smart_risk(base, regime, health, drawdown, vol) — анти-мартингейл.
6. Портфель: exposure_gate (correlation-cap; ATT1-short+ARF2-short не задваивать).
7. Запись: decision_bus (каждое решение+контекст+исход) -> JSONL. ИИ видит ВСЁ.

## B. Непрерывный надзор (фоново)
- edge_monitor.assess_all(decision_bus) -> статус каждого рукава (healthy/watch/degraded/halt).
  degraded -> smart_risk режет; halt -> стоп рукава. Анти-деградация онлайн.
- sleeve_registry: (strategy x side) атомарно, side-specific здоровье/риск.

## C. Еженедельный ИИ-ревью (scheduled) — ПРЕДЛАГАЕТ, человек одобряет
- research_orchestrator.weekly_review(running_sleeves, new_candidates) -> Proposal:
  PROMOTE/DEMOTE/HOLD по рукавам + ранг новых кандидатов (из shadow-свипов) + retest-очередь.
- format_proposal -> в Telegram владельцу на АППРУВ. Ничего не авто-применяется (риск/логика).
- Постоянный теневой поиск: свипы новых сетапов -> preflight -> wf_folds -> oos_selector ->
  кандидаты в Proposal. Так пакет растёт сам, но под контролем.

## D. Почему это НЕ деградирует годами
- Динамический отбор: нет гниющих списков монет.
- edge_monitor: ловит распад эджа онлайн -> throttle/halt до просадки.
- research_orchestrator: еженедельно пере-оценивает + предлагает ротацию.
- champion_challenger: демоут мёртвых, промоут доказанных.
- Всё В РЕЛЬСАХ: ИИ настраивает риск/режим/жизн.цикл, но НЕ свободно оптимизирует параметры live.

## Порядок вписывания (Codex, по мере live-рукавов)
1. С ARF2 (когда PASS): decision_bus-логирование + edge_monitor + smart_risk + exposure-cap.
   Символы — динамически (сканер по условию), не фикс DOGE/XRP/ONDO.
2. Затем research_orchestrator в scheduled (еженедельный Proposal в TG).
3. Range/пила блок — сразу на dynamic range_scanner.
СТАТУС: модули готовы (294 теста), петля собирается по этому блупринту. Это «динамические рельсы + ИИ-аппрувы».
