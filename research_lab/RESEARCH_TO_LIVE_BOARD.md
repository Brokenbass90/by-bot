# RESEARCH-TO-LIVE BOARD — указатель (с 18.10.2026)
Решение PM 18.10 (п.7): **единая доска готовности — в репозитории исполнения**:
`bybit-bot-recovery-20260824 / research_lab/RESEARCH_TO_LIVE_BOARD.md` (Codex, сверено 18.10 ~07:20 UTC, коммит `b4176b2`).
Здесь второго источника финансового статуса нет. Исследовательская сторона хранит:
- **паспорта стратегий** — реестр `data/factory_v3/reestr_v1.jsonl`, записи `tip=pasport` (версии не перезаписываются);
- **доказательства** — документы и квитанции, на которые ссылаются паспорта.

## Сверка доски Codex с паспортами (18.10 ~07:20 UTC)
| стратегия | доска Codex | паспорт Claude | совпадает |
|---|---|---|---|
| KITY_BYBIT | ECONOMIC_INCONCLUSIVE, 10/10 исполнение | ECONOMIC_INCONCLUSIVE / EXECUTION_PASS (техн.) | да |
| Alpaca Weekly Dynamic | ECONOMIC_FAIL по правилу замены; SHOP 19.10 отменён владельцем | ECONOMIC_FAIL | да |
| Alpaca EventReselection | ECONOMIC_FAIL | ECONOMIC_FAIL | да |
| Alpaca Monthly | выбранный кандидат 8.48 %/DD 16.17 % | ECONOMIC_PASS (история, не независимая) | да; формулировка Codex точнее — «выбранный кандидат», не независимый PASS |
| Elder Hedge V1.1 | DEV_PASS режимного хеджа, standalone KILL | ECONOMIC_INCONCLUSIVE | да |
| ETF_PREMIYA_BTC | DEV candidate, prospective/QA не завершены | ECONOMIC_INCONCLUSIVE | да |
| LIQ_OTSKOK_4H_V2 | raw records не edge | NET_DANNYH | да |
| Brain V2 | INCONCLUSIVE | — | да |
| ATT1 | нет строки | ECONOMIC_FAIL (одновременный контроль, 18.10) | **добавить у Codex** |
| ASM1_FIKS | нет строки | NET_DANNYH (тень вперёд) | исследовательская тень, денег нет — можно не добавлять |
| KITY_M3_KRIPTO | «улучшение отозвано» | ECONOMIC_FAIL | да |
Расхождений по статусам нет; для Codex — одна строка ATT1.
Прежняя версия этой доски (17–18.10) сохранена в истории git.
