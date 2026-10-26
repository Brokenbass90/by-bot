# PUMP4: очередность CATCHUP_REPLAY — 26 октября 2026

**Установлено ORDERS_OFF. Проверка новой H1 назначена существующим таймером
на 09:00 UTC; до её результата timeliness PASS не заявляется. TINY_NOT_READY.**

## Измеренная причина и исправление

Фактическая H1 25Oct18:137 публикаций,127 intakePASS,15 публикаций≤60s;
median87.974s/max107.326s,95 источников≤60s,0 сигналов. Полный seal и childexit0
получены, но 60s gate не пройден. Агрегатный peak≈254MiB при лимите768MiB;
childCPU30.469s. Семь CATCHUP заняли34.545s родительского времени,120 CURRENT —
62.009s. Исторические повторы в начале очереди задерживали свежие свечи.
[Фактическая18H1](evidence/pump4_capture_process_20261025/actual-18h-summary.json),
[стоимость режимов](evidence/pump4_capture_process_20261025/actual-18h-mode-costs.json).
Это сравнение разных часов рынка; оно не является контролируемым speed benchmark.

В том же Supervisor добавлен advisory classifier. Откладываются только уже
существующие последовательности с несколькими пропущенными свечами и валидной
эпохой. Bootstrap, seed-only, recovery и сомнительные случаи идут прежним путём.
Свежий CURRENT обрабатывается сразу после проверенного notice источника.
Отложенный CATCHUP запускается лишь после childexit0,137 notices и полного
проверенного seal/context; перед обработкой повторно сверяются хеши journal,
epoch и отсутствие новой recovery batch. Ошибка не превращается в новый вход.

Оригинальный `_stream_symbol` выполняет все проверки и публикации. Родитель
остаётся единственным journal writer; стратегия, intake, universe137,60s,
исторические cursors/epochs и финансовые лимиты не изменены. Все действия
CATCHUP остаются historical/non-entry. Новые timestamp диагностики отдельно
показывают source arrival, классификацию, реальное начало и durable finish.

## Проверка и установленный путь

79 целевых проверок; полный закреплённый пакет283 local /283 VPS PASS,
108 исходников,48 imports,16 test modules,0 fallback/real broker calls;
сеть отключена, на VPS также `unshare --net`. Локально131 и на VPS132 fixture
receipts: это артефакты pytest разных сред, не рыночные сделки.
20 local /20 VPS handoff/rollback tests PASS.
Независимый `gpt-6-astra/high` review:0 Critical/Important,24 отдельно повторённых
case; runtime model/effort проверены по turn_context. Reviewer отдельно отметил:
classifier добавляет чтение/проверку journal; чистая польза требует реальной H1.

Material `5882783b99ca5c4883f8ad6c68e3fc681a0ed029c5f4f164efa8d1d8669a7ea5`.
DATA установлен 08:18:22UTC через существующий service/timer:
`/opt/bybot-research/pump4-server-orders-off-20261023/candidate-5882783b99ca5c48/app/.private/pump4-supervisor-v1`.
Binding `ea4c86992aaf2ac13c262c86c6c3a76969b5e7d15f33fa4665db2720d6f0ab23`.
Сохранены21 376 файлов истории; старый корень, все scopes/claims остаются.
DATA ceiling2cores/aggregate768MiB сохранён. Новых сервисов/коллекторов нет.

Тот же sole financial unit и принятый app30677ce6 остаются `--orders-off`.
Конфиг `priority-handoff-20261026/owner-review-stream-v1/runner.json`,
SHA256 `125b0ae6afc42582e83dea2bceead8f6826f41e1b5b7ad9e90cfcd10cf769b16`;
scope `a527f12c85a362675220a845d6723732e21917f47f9f192d4406f4bc3f04bb28`.
Новый PID2955754, исходный account lock818853; свежие две GET-only проверки
flat/no open orders; NO_NEW_SIGNAL,0 broker writes/ownerGO. Это технический OFF
handoff, а не денежная активация. Monthly v6 unit SHA256
`9d94467d301cf5f545bee18e50b838623c061b72f46a2fbdd9b7d1991932cc1d`
при свежем snapshot совпал; Monthly не переключался.
Private rollback: `priority-handoff-20261026/ops.py`, SHA256
`baf11ac21deedb7c3fbad3e234c239871d6d49367fc1c114fcdbe782b68466e6`.
Никакого автоматического rollback/повторного claim или финансового reset.

## Финансовое продолжение

[Сверка точных51](PUMP4_SIGNAL_RECONCILIATION_2026_10_26.md) доказала механизм
ошибки исследовательской обёртки; старая экономика не стала экономикой корректного
производителя. [CR300](PUMP4_ENTRY_WINDOW_300_CR_2026_10_26.md) отделён и не применён.
Даже успешная новая H1 сама по себе не открывает TINY. Нужны подтверждённая
signal/state lineage корректного потока, приемлемая net экономика и свежий
конкретный account/fee/funding/lot/oneway/protection допуск. Финансовый GO — только
владельца; готовой команды GO при нынешних блокерах нет.

[Evidence](evidence/pump4_catchup_priority_20261026/).
