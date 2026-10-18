# После Monthly: KITY safety и реальные первые записи Elder

18 октября 2026. Monthly E2E опубликован коммитом `1bd171f`:
[завершение и activation packet](ALPACA_MONTHLY_E2E_COMPLETION_2026_10_18.md).
Календарь Monthly не остановил следующую доступную работу. Денежные полномочия,
исследованные стратегии, работающие финансовые units и NET не изменены.

## DONE / TESTED — KITY

Свежий authenticated GET: **позиции0 / ордера0**, policy `d848a130…f40a1` SPENT,
controller TERMINAL/ORDERS_OFF, PID2568196, lock inode818853. Все159 исходных guard
pins и23 production source pins совпали. Использованная claim не менялась.

В fault injection проверен production supervisor с реальным saved account
readback: неполный источник вызывает прежний unwind доказанных owned-позиций,
не продлевая deadline и не повторяя вход; полные, но противоречивые позиции/
executions сохраняют sticky custody conflict. Такой конфликт не даёт права
придумать fill из позиции или отправить слепой выход. Требуется выяснить ownership;
native guards не отменяются ради чтения. HTTP/dispatcher в тестах не финансовые.

Health теперь считает UNHEALTHY также ненулевую экспозицию в ORDERS_OFF и terminal
quantity без всех исполнений — раньше свежий process heartbeat мог скрыть это.
Из10 новых cases9 сначала воспроизвели ошибку. **48 focused PASS**, отдельно
**40 PASS на точном candidate /16 source imports /0 checkout fallback**. Числа
перекрываются. На настоящем terminal heartbeat новый assessor возвращает HEALTHY;
это проверка данных, не выбор нового production observer.

24-файловый кандидат установлен **неактивно**, без service registration/restart:
`/opt/bybot-research/kity-safety-20261018/candidate-48020edd4b9d97a9`.
Material SHA `48020edd4b9d97a9cf6140bda66ef69f1ed6e8829d09aa5bd8248c5fbf246a1d`,
spec `6ddc1e9bf517e9fa514564ac39d867361371501b36aa76d17a33dbce7bdf714a`.
На VPS verify-only PASS,159 original guards неизменны. Сохранено инертное
rollout proposal с183 prospective pins, без runtime journal/claim copies и GO.
Работающий controller/observer всё ещё используют прежние исходники; кандидат
**не выбран** и никакая использованная попытка не восстановлена.

Канал KITY по фактическим выбранным config совпадает по token+destination с
каналом успешного безопасного Monthly test15223. Значения не публикуются;
дополнительное сообщение не отправлялось. Это доказательство доставки канала,
а не утверждение, что новый fault assessor уже активен в production.

Остаётся отдельное решение о безопасном выборе новой версии owner/observer с
повторной fresh flat/finality/lock проверкой. Оно не означает новый денежный GO.
Экономический KITY INCONCLUSIVE, прежний normal-hold не доказан; новые paid
attempts не назначены и исследовательские gates не ослаблены.

[Свежая сверка](evidence/kity_safety_20261018/fresh_readback.json),
[точный manifest](evidence/kity_safety_20261018/kity-source-manifest.json),
[VPS readback](evidence/kity_safety_20261018/kity-stage.json),
[fault acceptance](evidence/kity_safety_20261018/verification.json).

## DONE / TESTED — Elder event intake

Новый file-only receiver использует существующие `HedgeBook`, hash-chain reader
Brain и `ReportEvent v1`. Он читает только упорядоченный decision prefix
первой физической ETS2S записи и останавливает декодирование перед полями исхода.
Сохраняются raw-row/prefix hashes, первая геометрия, реальное время приёма и
source provenance. Поздняя строка не заменяет геометрию первой. Никаких terminal R/rr/PnL
значений, исходов judge, future-bar исполнения или генератора стратегий не запущено.

Append-only prefix seals блокируют изменение/усечение источника; partial tail
не чинится. Повторный импорт/restart сохраняет первое время, не создаёт дубли и
не превращает историю в prospective. Context берётся из уже существующего Brain,
без нового regime engine; availability — реальный `t_recorded_ms`, не более ранний
backfilled decision timestamp. Связь по ключу сама по себе не является parity PASS.

**Фактический снимок:**18 813 строк,15 209 первых short records,9381 key-linked
context candidates,540 первых записей с geom. Повторный импорт:15 209 ALREADY,
новых0; prospective credit **0**. Источник/Claude code/KARTA/VOROTA не менялись.
PID16945 работает с17Oct11:09:53Кипр; hash файла producer совпадает с замороженным
`2eb740e6…988d6f`, in-memory source hash этим не доказан.

**Найден реальный BLOCKER:**440 geom записей поздние; все100 своевременных имеют
`stop_x=4`, `max_lev=100`, **f1=.50**, тогда как V1.1 требует **.55**. Старые14 669
geometry-free first records также нельзя дополнять поздней геометрией. Это не
свидетельство отсутствия сигналов и не повод ослаблять frozen validator.

72 targeted PASS включают существующий Elder и Brain receiver, restart/no-dup,
prefix mutation/truncation/partial tail, фактическую availability контекста и
реальный decision-only пример `.50`, который обязан блокироваться на frozen `.55`.
Во время первого настоящего импорта receipt publication отвергла относительный
output path уже после commit книги. Исправлено с регрессией; повторное чтение
восстановило существующие записи без очистки/пересоздания книги и без дублей.

Следующий gate у Claude — **версионированно согласовать f1 producer/контракта**.
Новый receipt не должен задним числом менять старые записи или приписывать им
prospective credit. Затем — точные causal context/risk/instrument snapshots в
существующий frozen adapter; ≥30 hedge events, intentions≥97%/execution≥95%,
latency≤5min в≥95%, zero material defects, restart и ETS2M900 остаются прежними.
Денежного разрешения или второго manager нет. Новый календарный срок не добавлен.

[Фактический приём](evidence/elder_event_intake_20261018/receipt-first.json),
[повтор](evidence/elder_event_intake_20261018/receipt-repeat.json),
[диагностика](evidence/elder_event_intake_20261018/diagnosis.json),
[реальная decision-only fixture](evidence/elder_event_intake_20261018/actual_f1_conflict.json),
[tests](evidence/elder_event_intake_20261018/verification.json).

## REMAINING / BLOCKERS / ближайшие действия

Monthly: actual30Oct closed source/размер, отдельный личный Monthly GO и2Nov fresh
opening/custody/cash/NET finality/single manager handoff. Инженерия E2E закрыта,
покупки19Oct нет. NET:19Oct13:30UTC DAY protection и13:35UTC независимая сверка.
SHOP остаётся отменённым. IBIT19Oct forward/MassivePENDING и LIQ delivery — по
существующим units/heartbeat, без дублирования. KITY и Elder продолжаются по
конкретным gates выше. Статус-дельта для Claude сохранена файлом; сообщение не отправлено.
