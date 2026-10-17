# CRO handoff (Claude) — 17.10.2026 утро. Читать первым в новой сессии.

Роль: CRO — исследования, Factory, Brain, научная проверка, roadmap. Репо research: `bybit-bot-clean-v28`, ветка
`research/fabrika-v1` (коммиты только plumbing через временный GIT_INDEX_FILE; пушит владелец). Репо Codex
`bybit-bot-recovery-20260824` — только чтение. LIVE/деньги — только по письменному GO владельца.
Протокол: тезис → измерения без доходностей → заморозка → один PnL-тест; бюджет спасения ≤2 диагностики + 1 вариант;
каждый KILL → 2 новых независимых механизма; статусы PASS/FAIL/UNKNOWN/BLOCKED; каждый FAIL → лучшая следующая гипотеза.

## Состояние
- **Alpaca:** эталон `981b62f` (core 2347a7ec606cd845). Codex `b95550b` = monthly контур; моё ревью `7800b72`:
  логика PASS, размер позиции UNKNOWN → после sizing-replay выдать ALPACA_STRATEGY_PARITY_PASS. NET 15.10 = OFF_PROTOCOL.
  Дробные ордера только DAY → нужна проверка стопа при открытии сессии (Codex).
- **ETF_POTOK:** BLOCKED_DATA (`ITOG_ETF_DANNYE_2026_10_16.md`), заявки в очереди не прогонялись.
- **Elder:** standalone KILL; CRASH HEDGE (REZHIM) DEV_PASS, контракт заморожен, Codex — orders-OFF адаптер.
- **Brain Shadow v1.2** идёт через storozh (часовой проход ~:32 UTC); причинные записи из ten_ETS2S.
- **KITY C1:** неделя 1 OPERATIONAL_PASS; Codex — batch/private WS.
- Резерв (`data/factory_v3/KANDIDATY_V_OCHEREDI.json`): KITY_V2_NECRYPTO, POLY_FED_SDVIG, ETF_PREMIYA.

## Следующие шаги (по порядку)
1. prereg POLY_FED_SDVIG: порог скачка п.п., дедуп, правило времени, знак +1, окно 1–3 дня, шаблон `shablony_v2:sobytie`;
   сначала покрытие истории fed_* без доходностей.
2. ETF_PREMIYA: 3 измерения без доходностей (корр. премии IBIT/ETHA с потоками Farside; устойчивость BTC/пай; покрытие);
   данные `data/akcii_grouped` + часовые Binance.
3. Ревью sizing-теста Codex → PARITY_PASS/расхождение.
4. Поддерживать резерв ≥3; после каждого KILL — 2 новых механизма.
