# Trading OS — Dynamic / KITY: результат инженерного цикла, 17 октября 2026

**Код:** `469a9eddf27fd40d38f71ba2db783522fb38b25c` поверх
`577f7958189721c9508e58eebec45a52c0d9be06`.
**Проверенный research origin:** `211ed6442f3966f8731440cc1c5de4a49a493ccc`.
**Последний runtime sample:** 17:55 UTC. Это результат конкретного цикла,
а не объявление всей Trading OS готовой или прибыльной.

## Что исправлено и доказано

1. **Разделены Dynamic и Monthly.** Восстановлены исходные обязательства
   Dynamic: недельный список, покупка на освободившийся подтверждённый слот,
   защита и последующее сопровождение. Это было реализовано и тестировалось.
   Свежий повторный отбор всего рынка после каждого выхода в исходном V1
   отсутствовал. Поздняя проверка TTL запретила повторное использование недельного
   списка, но не добавила внеочередной отбор. Поэтому часть замен перестала
   проходить. Это конкретная причина функционального разрыва, а не отсутствие
   нового календарного месяца.
2. **Реализован отдельный Dynamic event-reselection ORDERS_OFF-кандидат.**
   Полный owned exit до открытия → новый отбор по последней завершённой сессии
   → максимум одна резервируемая покупка на ближайшем открытии. Использованы
   прежние slot/risk/cash/fee/cooldown/restart механизмы, собственная исследовательская
   книга. Чужая LIVE-книга отвергается. Нет брокерского исполнения или новых
   финансовых полномочий. Вариант требует исследовательского принятия и не
   выдается за уже проверенную доходную стратегию.
3. **Закрыта фактическая нехватка данных Dynamic.** Его исходный universe —59,
   Monthly —57+SPY=58. Найден единственный недостающий QQQ, получены данные тем
   же загрузчиком, проверены200 сессий по broker calendar до16 октября.
   GET брокера подтвердил доступность всех59 инструментов, ошибок0. Непрерывное
   обновление59 ещё не развёрнуто; существующий Monthly58 не подменяется.
4. **KITY закрыт как NO_SEND/SPENT, не execution PASS.** Независимые полностью
   пагинированные broker GET подтвердили0 позиций/ордеров/исполнений/истории
   ордеров/транзакций после личной команды. На точном capture доказано:
   BTW minimum10 при росте цены2.03797→2.38853 поднял общий целевой размер.
   Минимально допустимый gross по неизменному алгоритму229.584550 против215.
   Это CAPACITY_BLOCKED; лимит и стратегия сохранены.
5. **Добавлена предденежная проверка KITY и регрессии.** На реальных сохранённых
   книгах воспроизводит207.668760 и229.584550. Инертный будущий packet автоматически
   блокируется, если корзина не помещается. Улучшена безопасная причина NO_SEND.
   Активный финансовый writer не изменён и сегодняшняя попытка не повторялась.
6. **329 focused tests PASS:**79 KITY +250 Alpaca; compile/default no-network
   commands/diff check PASS. Полный suite не перезапускался; предыдущие60 FAIL
   не скрыты. Тесты не означают доходность или реальное исполнение стратегии.

## Что реально готово к LIVE

| Направление | Подтверждённая готовность | Что мешает первой новой сделке |
|---|---|---|
| Alpaca Monthly | Независимый strategy parity PASS, DATA_READY58, действующий source/schedule ORDERS_OFF, disabled V3 | Денежный transport/custody binding, точный activation packet, отдельный OWNER GO; календарь2 ноября |
| Dynamic исходный Weekly | Контракт/реальная история реализации восстановлены, source59 и broker eligibility PASS | Свежесть против weekly-reuse, реальные slot/exit/NET ownership, актуальный проверенный риск/исполнительный packet; доказательство Weekly net edge не подменяется чужим backtest |
| Dynamic после выхода | Реализован и протестирован отдельный ORDERS_OFF-кандидат | Принятие версии семантики, сопоставимая проверка результатов, непрерывный source59, authenticated account/slot admission и один financial owner |
| KITY micro | Действующий batch/WS контур и точная диагностика отказа | Не помещается в215 на сохранённых ценах; использованное разрешение; нового GO нет;10/10 execution не достигнут |
| NET | Существующее сопровождение и GET-only DAY monitor сохранены | Фактическое подтверждение защиты на открытии19 октября ещё невозможно доказать субботним snapshot |

**Сопоставимое net-сравнение Weekly / event-reselection / Monthly на одинаковых
данных и издержках в этом цикле не выполнено.** Старые Dynamic/V2 скрипты имеют
другие universe/выходы и не служат доказательством. Не запускался новый sealed
judge, не читались закрытые будущие outcomes, не подбирались параметры.

## Execution board: следующий незакрытый gate

| Приоритет | Задача | Готовность / критерий завершения |
|---|---|---|
|P0 Dynamic|Зафиксировать новую семантику event-reselection отдельно от Weekly и Monthly; сопоставить фиксированные версии без оптимизации|Версионированный research verdict и одинаковые source/cost assumptions; доходность не предполагается|
|P0 Dynamic|Подключить его59 к существующей source-инфраструктуре; собрать authenticated slots/exits/cash/NET ownership admission|Полный текущий ORDERS_OFF receipt; не выдумывать новый слот и не создавать второго manager|
|P0 Alpaca|Довести выбранный допустимый вариант до disabled single-owner financial binding + точного TINY activation packet|Stop/ratchet/restart/ownership/fees/rollback подтверждены, риск и суммы конкретны; затем отдельный owner financial GO|
|P0 NET|19 октября13:30UTC проверить фактический DAY stop readback/оставшееся qty/владение|Broker order реально принят; иначе FAIL/alert. Monitor уже работает, повторная установка не нужна|
|P0 KITY|Использовать новый feasibility verifier перед следующим денежным решением|При gross>215 CAPACITY_BLOCKED; только свежий PASS ведёт к новому датированному owner packet. Не поллить до PASS и не повторять использованную попытку|
|P0 Monthly|Сохранить parity PASS; завершить денежный binding/packet независимо от Dynamic|30Oct source →31Oct check →1Nov GO →2Nov14:30UTC, без повторного исследования уже принятого baseline|
|P1 Brain/Reporting|Принять опубликованный Brain prereg v1.3 в существующий общий read-only journal|Context → risk → decision → execution.kind linkage, UNKNOWN при отсутствии execution; HEDGE/CONFLICT/INDEPENDENT не смешивать. Реальные сделки не меняются|
|P1 IBIT|Сохранить DATA-only capture/seed; закрыть forward и Massive QA|Первый forward19Oct;81-session historical seed не считается prospective, Massive QA остаётся PENDING|
|P1 Elder/LIQ|Prospective Elder parity; существующий LIQ V2.1 daily export|Замороженные gates не меняются; LIQ epoch/collector не перезапускать, существующий exporter использовать без фильтров/дедупликации|

Ближайшее техническое окно Alpaca Dynamic —**19 октября16:30–16:35 Кипр**,
если к тому моменту выполнены перечисленные условия. Это условное окно, а не
обещанный запуск. Monthly —**2 ноября16:30–16:35 Кипр**. KITY торгуется круглосуточно,
но нового денежного запуска сейчас нет: сначала свежая допустимая корзина и
новое личное разрешение. Позитивный финансовый результат по дате не обещается;
сначала нужны воспроизводимые исполненные циклы с фактическими чистыми издержками.

## Финансовые разрешения и сохранность

- KITY `a1c97e6b94e3d1a1c8927e7dba252cbd12a1c6f49012133587a85c27fb8845c8`:
  **SPENT**, хотя дата истечения17Oct21UTC ещё впереди на момент sample. Старый
  запуск не повторять; новый policy/GO не создан.215/50bps/2s/60s/15trigger/30min
  не изменены. Предденежный PASS не гарантирует будущий post-GO PASS.
- NET: ранее отдельно разрешённый личный owned exit2Nov остаётся NOT_ARMED,
  не даёт права закрыть раньше или передать позицию новому manager.
- Monthly: parity/research/engineering разрешения действуют; monetary activation
  отдельно. Dynamic: текущая просьба разрешает восстановление и ORDERS_OFF,
  не автоматический LIVE или повышение риска.
- Final GET/source sample: исходный KITY lock818853/source23/guards155 и старые34
  wire сохранены. Alpaca shared lock813893/HALT/95 pins проверены; V3 all32 match,
  Monthly source37 и IBIT source6 match, существующие timers active. ATT1/LIQ
  PIDs/эпохи не менялись. Код469a9ed не установлен в денежные units.
- Чужой `configs/allowlist_change_log.json` сохранён с SHA
  `365ff7d6eeb2c0e2427e15345558e098ee55a2e57de2f1c04c8a3ceedecc2e0e`, не включён
  в commit. Приватные captures/credentials/account IDs не публикуются.
- Финальный review root-only по действующему ограничению. Worker broker-readiness
  исчерпал allowance до правок; его не перезапускали и не заменяли. Проверки GET
  выполнил primary. Независимая новая финансовая/research приёмка не заявляется.

## Детальные dossiers / воспроизведение

[Dynamic](ALPACA_DYNAMIC_EXECUTION_READINESS_2026_10_17.md),
[Monthly](ALPACA_MONTHLY_ACTIVATION_READINESS_2026_10_17.md),
[KITY:10legs/minimum/новая процедура](KITY_CAPACITY_READINESS_2026_10_17.md),
[точные команды и hashes проверок](evidence/trading_os_dynamic_kity_20261017/verification.json),
[сохранность runtime](evidence/trading_os_dynamic_kity_20261017/runtime_preservation.json).

## Status delta для Claude — подготовлен, не отправлялся

Production code469a9ed: KITY actual NO_SEND/SPENT, reason GROSS_CAP_EXCEEDED,
229.584550/215, CTS492ms PASS, fully paginated post-GO broker zero. Root cause
BTW10-lot price jump; all10leg replay + pre-money capacity verifier + inert
CAPACITY_BLOCKED packet,79 focusedPASS, financial service unchanged.
Alpaca Dynamic снова P0 отдельно от Monthly. Original weekly replacement existed;
05d77bf strict TTL removed non-weekly reuse without fresh ranking. New versioned
next-open event-reselection candidate delivered ORDERS_OFF, parent risk unchanged,
no LIVE. Need semantic/research acceptance and matched fixed-rule comparison,
not grid/V2 aggregate. Actual59 source incl QQQ + all59 broker assets PASS;
250 focused AlpacaPASS; source59 continuous operation/binding still OPEN.
Monthly accepted parity retained; actual financial transport unbound, next2Nov.
NET19Oct actual DAY gate OPEN. Brain v1.3 and LIQ export at research211ed64
received/queued; IBIT/Massive forward QA PENDING. No financial authority change,
new policy, judge rerun, collector restart or message to Claude.
