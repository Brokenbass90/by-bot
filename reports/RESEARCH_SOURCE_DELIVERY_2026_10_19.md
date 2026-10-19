# Polymarket и BIL/SGOV: фактическая DATA_ONLY поставка

19 октября 2026. Запросы приняты из published research `7a80470d0b928b8fbdf41d69d88570105d2803a4`.
Один присланный документ — предыдущий отчёт Codex по Monthly/Elder; второй —
исследовательский отчёт Claude. Новый PM документ не отменяет Money Lane P0.
Здесь выполнена поставка двух независимых источников, без research judge/экрана/PnL.

**BIL/SGOV — DATA_ACQUIRED_QA_PASS. Polymarket — PARTIAL, NOT_SCREEN_READY.**
Это разные вердикты; ни один не создаёт новых финансовых полномочий.

## BIL/SGOV: DONE

Данные реально доставлены в отдельную папку Claude:
`../bybit-bot-clean-v28/research_lab/data/alpaca_bil_sgov_20261019/`.

| Инструмент | Первое наблюдение | Последнее | all | split | Пропущенные сессии после первого наблюдения |
|---|---|---|---:|---:|---:|
| BIL |2016-01-04|2026-10-16|2713|2713|0|
| SGOV |2020-05-28|2026-10-16|1606|1606|0|

Источник Alpaca SIP, `1Day`, `asof=-`; каждый adjustment — отдельный запрос и файл.
`all` — provider corrections, включая dividends/splits/spin-offs; `split` — только
splits. Второе преобразование или reinvestment/PnL поверх данных не выполнялись.
[Официальная семантика](https://docs.alpaca.markets/us/reference/stockbars).

Формат существующего deep archive сохранён: `records` с `o/h/l/c/v/vw/n/t`,
`t` в epoch milliseconds и payload SHA; legacy schema name не подменяет источник
Massive. Фактический provider/adjustment явно записаны в каждом документе.
Внутри `all/bars/` и `split/bars/`, общий `calendar.json`, raw GET receipts и
commit-last `delivery.json`. Всего5 GET: календарь и4 серии; только market data.

Проверены строгий порядок/уникальность timestamps, OHLC/volume/trades, полный broker
calendar после первого наблюдения, одинаковые timestamps all/split. До первого
SGOV наблюдения1107 calendar sessions сохранены как отсутствие наблюдений, не
синтезированы и не объявлены датой листинга. Историческая vintage корректировок
NOT_PROVEN; сегодняшняя adjusted history не становится point-in-time снимком 2016.

Seal SHA `e6dae44c3516fb063ef81fadbf01e83ebb3cfa0454275bcc7fdb15a9bd32166c`.
[Summary](evidence/research_sources_20261019/bil-sgov-summary.json).
BIL/SGOV не объявлены безрисковым кэшем. Monthly/Yahoo source не заменён SIP.
Claude может готовить prereg overlay; текущая стратегия/капитал/отбор не меняются.

## Polymarket: источник доступен, полный контракт ещё не закрыт

Фактическая папка Claude:
`../bybit-bot-clean-v28/research_lab/data/polymarket_source_20261019/`.

Это **первичная проверка доступности**, а не полный census из6548410:
40 закрытых рынков,10 первых по id в каждой группе planned endDate2023/24/25/26,
80 outcome tokens, последние14 дней до actual closedTime, `fidelity=60`.
Выборка не случайная, не репрезентативная и не пригодна для вывода об edge.
Период запроса заканчивается18Oct, будущая часть октября не придумывалась.

Получено **20 752 точки,62 токена с историей**.18 токенов проверенной2023 группы
остались без истории. Пустая история не заменена нулевой ценой; raw сохранён.

| Группа planned endDate | Рынков | Токенов с историей | Точек |
|---|---:|---:|---:|
|2023|10|2|646|
|2024|10|20|6718|
|2025|10|20|6720|
|2026|10|20|6668|

### Конкретный источник ошибки, устранённый в сборе

`interval=max&fidelity=60` вернул пустые history для всех80 токенов. Это **не**
доказательство недоступности всей старой истории. Явные `startTs/endTs` на тех же
старых токенах вернули реальные данные: в диагностических14-day окнах2024/25 по336
точек. Рабочий сбор теперь использует явные14-day windows с точным согласованием
перекрытий. Конфликт одной timestamp/разных prices блокируется, raw не дедуплицируется;
нормализованный ряд объединяет только тождественные перекрытия.

Сохранены исходные max-ответы и explicit responses с request/receive timestamps,
полными SHA, текущие fee/tick GET и текущие CLOB resolution snapshots где доступны.
`markets.jsonl` и `prices/<token>.json` совместимы с загрузчиком Claude.
[Параметры CLOB](https://docs.polymarket.com/api-reference/markets/get-prices-history),
[API checks](evidence/research_sources_20261019/history-followup-summary.json).
Отдельно проверенный Data API v2 не подмешан в CLOB history: его coarse series и
политика retention отличаются;3-hour observations не названы часовыми.

По текущей микроструктуре: spread404 у80 токенов закрытых рынков; fee/tick404 у18;
CLOB market404 у9. Это UNKNOWN, **не** zero spread/fee. Сегодняшний доступный тариф
не выдан за исторический. Authoritative winner/time availability здесь не вычислялись
из outcomePrices>=0.99; closedTime не приравнен к времени доступности settlement.
[QA](evidence/research_sources_20261019/polymarket-qa.json).

Seal SHA `74164c7903a207776243b60e87a9fa0bbc8c8adfc40b2a628df88725960b4b5b`.
[Summary](evidence/research_sources_20261019/polymarket-explicit-summary.json).

**REMAINING:** полный versioned census всех нужных рынков, вся доступная lifetime
history явными окнами, coverage/empty classification, research policy по missing
истории, историческим costs и известности settlement/group membership. Последние14
дней pilot не выданы за полный срок жизни. Нужная для реального sum<1 проверка
exhaustive/mutually-exclusive groups и синхронные executable quotes NOT_PROVEN.
Нет economic screen, forward или financial PASS.

### Передать Claude перед использованием стенда

Опубликованный `polymarket_stend.py` возвращает стратегии объекты `Rynok`, содержащие
`pobeditel`, `zakryt` и полный `ceny`. Обычные методы ограничивают timestamp, но объект
сам по себе не исключает доступ к исходу/будущему. Поэтому6 unit tests не доказывают
изоляцию произвольной AI strategy. Нужен отдельный read-only strategy view; Codex
исследовательский код не исправлял и не запускал. Final Gamma metadata получены
задним числом; историческая доступность category/endDate/volume не доказана.

Это наблюдение о границе данных, не повтор исследования/новый financial gate.
Prereg, правило выборки, источник исхода и последующий экран остаются за Claude.

## Доставка, tests, сохранность

Оба набора реально скопированы create-exclusive, seal последним. Повторная доставка
сверила каждый hash, полный inventory и исходный mtime local seal; `already_imported=true`,
ни один файл не перезаписан. Source-receive/import/first-seal clocks разделены.
[Фактические receipts](evidence/research_sources_20261019/local-delivery.json).

**27 targeted PASS**: ingestion/immutable replay/route allowlist, полная pagination,
разделение adjustments/сессии, sparse/empty prices, explicit-window overlap/conflict,
новый файл после sealing, частичная локальная доставка. Полный repo suite не запускался.
Один независимый astra/high review выявил Important inventory hole; исправлен и
regressed. Runtime проверен. Последующие explicit-window и local-copy расширения
проверены root и tests; второго независимого final review/financial signoff нет.
[Tests](evidence/research_sources_20261019/tests.xml),
[Review](evidence/research_sources_20261019/review.json).

Ни ордеров, ни wallets/credentials в export, ни financial controller constructors,
ни VPS/code transfer, ни NET/SHOP/units/risk/frozen strategy изменений. Текущий
проектный allowlist сохранён отдельно. Research code/KARTA/VOROTA/Factory/judge/
outcomes не редактировались и сообщения Claude не отправлялись. SEC запрос прочитан
и сохранён в очереди; его выгрузка в этот этап не включалась по последнему акценту владельца.

Следующий Money Lane P0 остаётся Monthly automatic real broker cost-finality →
единственный applying runner/handoff/rollback → concrete bounded standing packet.
Сегодня19Oct исходная NET DAY protection13:30UTC и independent readback13:35UTC
остаются в прежнем плане; текущий отчёт не утверждает, что будущий стоп уже проверен.
