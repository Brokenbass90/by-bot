# Monthly cost source / Brain integrity — 19 October 2026

**Завершён локальный ORDERS_OFF компонент автоматического cost-finality.**
Реальные broker GET/fees/cash проверены отдельно от моделируемого Monthly цикла.
Новая денежная версия не активирована; financial standing GO отсутствует.
Следующий P0 — один production runner, серверная репетиция и NET handoff/rollback.

## DONE / TESTED

- Существующий exact-host client получил отдельный raw GET метод для clock,
  account и полностью пагинируемых activities. Он не расширяет order routes или
  permits. Запрос использует creation-time after/until, сохраняет raw bytes/hash,
  HTTP status, времена и не фильтрует позднюю комиссию по дате её сделки.
  Неполная пагинация, потерянный ответ, HTTP/JSON/UTF-8 ошибка сохраняют evidence
  и прекращают обработку; автоматической повторной заявки нет.
- Новый getter и collector проверены четырьмя настоящими GET на VPS в12:17UTC:
  7 FILL /6 FEE. Выполнялись только извлечённые stdlib функции; financial controller,
  broker writes и изменения файлов VPS —0. Сохранённые ответы воспроизведены офлайн.
- Четыре полных account-day совпали с pinned retail fee model:1/5/7/15Oct,
  суммарно **$0.06**. Считаются количества/стоимость исполнений и суммы assessments,
  включая partial fills; равенство числа fills и fees не требуется. Instrument
  class/currency/asset identity и full New York day coverage проверяются явно.
- Реальный cash trace: сохранённый остаток8Oct **$496.12 − NET buy $101.20 − CAT
  $0.01 = $394.91**, совпадает с broker source19Oct. Это legacy NET с открытой
  позицией, **не terminal Monthly trade и не перенос NET в новую книгу**.
- До native dispatch сохраняется immutable cash anchor. Автоматический producer
  сопоставляет exact owned entry/exit IDs и все account cash movements с existing
  Monthly book, выпускает pinned input для **существующего** finalizer. Второй
  финансовый ledger/manager не создаётся. Callback подключается к existing `tick`.
- Account-day pennies распределяются детерминированно по базе CAT shares / SEC
  sell value с largest remainder и tie по order ID. Сумма сохраняется точно.
  Это явная accounting allocation, **не broker per-order fee attribution**.
  Actual activity economics, отображаемая средняя и cash-cent rounding разделены;
  `other_cash` не подгоняется под нужный остаток.
- Source/pins/cash/order mismatch, отсутствующая или поздняя комиссия, неизвестная
  операция и новая fresh liability блокируют finality. Защита вызывается раньше
  accounting в existing dispatcher. Повторный импорт/вызов/restart сохраняет
  исходный source и не создаёт новый вход. Изменившееся уже принятое распределение
  расходов выдаёт `MONTHLY_FINALIZED_ALLOCATION_REVISED`, а не перезаписывает net.
- Полный локальный тест использует frozen **57+SPY**, настоящий selector и native
  lifecycle, затем automatic raw source → delayed fees → existing finalizer → cash
  release после stop exit → следующий месячный отбор. Это не доказательство
  заменяющей покупки сразу после rotation exit в том же opening window.
  Quotes/calendar/fills/fees в этой репетиции
  **synthetic**; сетевых и реальных денежных запросов нет. Другие tests покрывают
  несколько одновременно учтённых бумаг и unequal-price fractional fills.

Исходные счётчики, SHA, команды и область каждого теста:
[verification.json](evidence/monthly_cost_finality_20261019/verification.json).
Test counts пересекаются и не складываются. Raw account payloads, account IDs,
профили и credentials остаются в `.private`, в Git попадают sanitized receipts.

Один независимый reviewer проверил четыре последовательных новых участка:
collector, account-day proof, owned producer, raw transport. Runtime подтверждён
как **gpt-6-astra/high**, не по самоотчёту.8 Important findings исправлены с RED/GREEN
regressions; повторного независимого signoff после исправлений не было. Последние
fixture/asset-conflict дополнения проверял primary; financial signoff не заявлен.

## REMAINING / реальные границы

| Уровень | Что доказано / что остаётся |
|---|---|
| LOCAL_SIM | Source/owned accounting/restart/delayed-fee/frozen-selector E2E PASS; подробные pins в verification |
| ACTUAL BROKER SOURCE | Настоящие fills/fees и cash chain PASS; это не actual Monthly execution |
| SERVER STAGING | Предыдущий44-file348690be остаётся CODE_ONLY_UNSELECTED; новый50-file cost candidate пока LOCAL_ONLY |
| SERVER REHEARSAL | Полная репетиция нового точного кандидата на VPS ещё не выполнена |
| LIVE EXECUTION | Новая Monthly не торговала; standing authority не выдана |

**Незакрытые инженерные задачи:** applying wrapper/schedule через один dispatcher,
exact server acceptance, safe NET handoff/rollback и конкретный bounded owner packet.
Они не требуют ожидания30Oct. Массовая уборка и сокращение START HERE отложены.

**Ограничение source semantics:** если broker-reported average отличается от
activity-weighted execution average, нужен отдельный pinned precision contract
с документированным source. Тестовый six-decimal contract работает; действующий
реальный protocol такого дополнения не содержит. Такой фактический случай даст
`ORDER_AVERAGE_PRECISION_UNKNOWN`, без epsilon и без объявления financial PASS.
Fee model также не обещает невозможность будущих broker corrections. Текущая
видимая uncertainty блокирует новый риск; отсутствующая activity не означает ноль.

**Будущие факты:**30Oct actual closed selection;2Nov14:30–14:35UTC fresh gates и GO.
Личный legacy NET exit назначен в то же окно. Известная задержка fee posting может
закрыть окно для Monthly. **Та же проблема существует при будущей обычной Monthly
rotation:** sell old → wait full account-day posted fees → buy new не помещается
в исходные пять минут. Это `ADMISSION_CONTRACT_SAME_WINDOW_CONFLICT`, не отсутствие
нужного cron и не основание переносить покупку на следующий день.

Следующий owner packet должен явно разделить окончательный net PnL и допуск нового
риска: допустим ли ограниченный резерв под source-classified pending costs при
подтверждённых fills/cash/ownership, с консервативным loss admission и остановкой
на неизвестных либо вышедших за границу расходах. Статус расходов остаётся PENDING,
а не становится нулём или FINAL. **Это только предлагаемый CR; reserve/limit/GO
не выданы и код admission здесь не ослаблен.** До решения текущий guard выдаст
NO_SEND. Не менять дату NET exit, frozen calendar или финансовые условия автоматически.

Сегодня19Oct: DAY-защита NET13:30UTC/16:30Cyprus, independent broker readback
13:35UTC/16:35. До фактического события это **PENDING**, не protection PASS.
Read-only проверка12:25UTC:77 protected pins и original lock813893 сохранены;
NET manager/DAY timer active, SHOP timer disabled/inactive. Никаких изменений units.

## Brain P1 — результат независимой проверки

[Integrity receipt](evidence/monthly_cost_finality_20261019/brain-integrity.json):
полные chains22448 opportunities/68878 decisions и точные17Oct byte-prefixes PASS.
Unique opp/policy/version keys без конфликтов; V2 ровно1534 opportunities,
каждая с четырьмя policies:6136 paired decisions.8 receiver receipts совпали
с полными исходными событиями;6128 остаются недоставленными.

8MiB/4096 ограничивают startup replay/in-memory retention исходного OS2 journal,
а не статистику.28.2MB backlog не записывался; нужен controlled continuity/cursor/
rotation через существующий journal. Простое повышение cap не выполнялось.
Это **DELIVERY_BLOCKED**, потеря предоставленной hash chain не обнаружена.
Полный рыночный census, feature-level PIT, outcome attribution и producer code
identity остаются UNKNOWN. Исторические policy hashes не заменены текущими.
Текущие V2 записи — warmup до31Oct14UTC,0 economic prospective credit.
Ни Brain, ни judge/outcomes не запускались; producer/receiver не изменялись.

## Опубликованные запросы Claude / status delta

Origin research **6826315c314326f9570894540087260876678b5a** проверен19Oct;
4587a34 с запросами является его ancestor. Сообщений Claude не отправлялось.

- **U2/H2b:** запрос принят в P1 delivery queue;1Day SIP/split/deep format пока
  DATA_BLOCKED. U58 продолжает отдельную Yahoo Monthly58 delivery;16Oct entry
  BACKFILLED_DIAGNOSTIC. Источники не смешивать, пропуски не превращать в forward.
  Monthly v1 не ждёт экономического результата этого отдельного prereg.
- **BIL/SGOV:** H5B_DEV_PASS принят как CR, не финансовый допуск. В текущем коде
  чужая позиция фонда блокирует новый Monthly entry; требуется отдельный sleeve
  внутри единого account ownership/accounting, без независимого второго manager.
  Account type/settled buying power, interest и actual SGOV execution costs ещё
  не подтверждены. Отсутствующий INT не доказывает нулевую ставку; SGOV fills
  отсутствуют в проверенном capture. Fund exposure сейчас входит в общий gross;
  исключать его из лимита без отдельного risk/ownership CR нельзя.
- **Polymarket:** QA документ опубликован,5 reported tests; поздние коммиты
  сообщают9. Codex эти research tests не запускал. Исторический Favourite study
  NEGATIVE; NO shadow остаётся исследованием, не разрешением торговать.
- **Roadmap:** обновлён существующий канонический файл и derivative execution
  board. P0 Monthly/NET сохранён; KITY SPENT/ORDERS_OFF и Elder prospective gates
  не изменены. Новая research/financial authority не создана.

Официальные API основания: [activity creation-time filters и pagination](https://docs.alpaca.markets/us/reference/getaccountactivities-2),
[account activities](https://docs.alpaca.markets/us/docs/account-activities),
[regulatory assessments](https://docs.alpaca.markets/us/docs/regulatory-fees).
Account-specific ставки взяты из отдельно pinned protocol, не из предположения
«Alpaca бесплатна» и не из произвольно выбранной общей ставки.
