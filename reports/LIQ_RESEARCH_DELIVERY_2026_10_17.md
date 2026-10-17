# Trading OS — LIQ передан Claude; P0 Dynamic59 source закрыт, 17 октября

Код LIQ: `01c85ca533c9d7e03ee14f5b56cd50b04bfaea31`.
Усиление бюджета источника: `131558261875d0905836e13ca5c9fd766c252c7f`.
Код Dynamic59: `a18c951978c217a5c398afa5d632a568f5d8d258`.
Проверенный published research: `431cc92817a7ba3b48549113c50c0c0e2d67e862`;
использованы существующий запрос экспорта и досье `b2cf5af`, без нового контракта
сигнала. Новые финансовые полномочия и LIVE-стратегии не активировались.

## Фактически выполнено

**LIQ export / доставка — PASS инженерного контура, не research gate.**
Первый cumulative snapshot содержит **24 863 исходные записи, все25 монет**.
Файлы реально находятся в
`/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/research_lab/data/liq_v2_1/`:

- `normalized-20261017.jsonl`: исходные normalized bytes, без фильтрации/дедупликации;
- `.receipt.json`: исходный export receipt с prefix hashes журнала;
- `.heartbeat.json`: неизменяемый heartbeat на момент снимка;
- `.qa.json`: наблюдавшиеся gaps/process controls, timestamps и latency;
- `.delivery.json`: последний публикуемый seal, связывающий все hashes;
- `instrument-fee-20261017.json`: свежие параметры25 инструментов и аккаунтный тариф;
- `CODEX_DELIVERY_20261017.md`: короткая дельта для Claude, без редактирования его кода.

Normalized SHA256:
`4680ea71264c993c2b7287d321ce66d196b1259f1796be5b79e62c69f789abf3`.
Seal:
`ffbb0f4d7999c586f97be4337672d1c3f89a0188f8a7c1c08b50d4ef9a3a4158`.
Повторный реальный SCP/import вернул `already_imported=true`, тот же seal и
тот же счётчик записей. Повторная доставка не создаёт дубли; исходные дубликаты
в ленте сохраняются для исследовательских правил Claude.

Существующий exporter использован без изменения. Рядом добавлены собственный
lock, immutable sidecars и commit-last receipt. После сбоя с сохранённым исходным
export receipt возобновляется публикация sidecars без повторного экспорта.
Одинокий normalized-файл без receipt блокируется для read-only reconciliation,
никогда не перезаписывается. Крупные файлы копируются потоком.

**Наблюдавшаяся QA:** latency p50=359ms, p90=566ms, max=3254ms; отрицательных
latencies0. Сохранены две записи с регрессией event time и один наблюдавшийся
reconnect gap **10 149ms**. Полнота биржи остаётся
`UNKNOWN_NO_SEQUENCE_OR_BACKFILL`, неизвестные интервалы не являются нулями.
Это raw observations, не BASE events/сделки. BASE count не вычислялся;
prospective decisions0, strategy/judge/PnL не запускались. Ежедневно найденные
сигналы задним числом остаются `V_EPOHE_RETRO`, не CONFIRM.

**Пункт для Claude:** на проверенном research431cc92 `liq_v2_1_konveyer.py`
читает только normalized rows и подставляет0 для отсутствующих часов, не
применяя heartbeat/gap sidecars. Перед source-QA PASS нужно подтвердить корректную
обработку этих UNKNOWN-интервалов по действующему контракту. Codex не менял
конвейер, `VOROTA.json`, `KARTA_PROEKTA.md`, thresholds или outcomes.

## Расписание и сборщик

На VPS включён отдельный `liq-research-export-v1.timer`: ежедневно **00:10UTC**,
первый следующий запуск18 октября. Версия app-v2 сохраняет исходный резерв
диска collector и дополнительно проверяет место под верхнюю границу снимка и
sidecars; при нехватке места — BLOCKED, без удаления данных. Timeout900сек
учитывает рост cumulative journal, CPU20%/низкий приоритет сохраняются. Старый
app/unit archived, снимки неизменны; [v2 receipt](evidence/liq_research_delivery_20261017/upgrade-v2.json).
Новый unit не имеет доступа к credentials
или сети; writable только собственный каталог exports. Старые snapshots не
перезаписываются, эпохи не смешиваются.

Collector `bybit-liquidation-source-v2_1.service` сохранил **PID2095785,
NRestarts0**, unit hash и эпоху `0688909d05884004b991bec76c6e4847` от14 октября.
Его исполняемый код, config и source manifest не менялись. Агент не изменял
журнал/heartbeat сборщика; добавлены только собственные export-файлы под
`runtime/exports`.

В приложении создан отдельный heartbeat `liq-claude`: ежедневный импорт
**03:40 Кипр**, догрузка пропущенных immutable snapshots после сна Mac.
Сервер экспортирует независимо от Mac; локальная доставка требует доступного
Mac/приложения. Штатные повторения проходят тихо, уведомления только о сбое,
конфликте или необходимом действии владельца. Сообщений Claude не отправлялось;
данные и дельта доступны в его именованной data-папке.

## Свежие инструментальные факты

GET подтвердил для всех25 точные `minQty`, `qtyStep`, `minNotional`, `tickSize`,
`fundingIntervalMinutes`; данные привязаны к request/receive timestamps и полным
raw hashes. **Тариф taker выбранного существующего аккаунта —0.00055, то есть
0,055% /5,5bps за сторону для каждой из25 монет.** Это действующий fee-rate GET,
не квитанция о комиссии несуществующей LIQ-сделки и не полная оценка издержек.

Минимальный `minNotional=5` у всех не означает возможность позиции ровно5USDT:
минимальное количество и цена также ограничивают размер. Funding intervals
240/480 минут сохранены по каждому symbol. Замороженная модель исследования
12bps круг+funding не изменялась; market slippage/PnL не проверялись.
Тариф/метаданные — датированный снимок, перед будущим финансовым досье обновить.

[Факты25/fee](evidence/liq_research_delivery_20261017/instrument_fee_facts.json),
[actual delivery/QA](evidence/liq_research_delivery_20261017/actual_delivery.json),
[повторный импорт](evidence/liq_research_delivery_20261017/reimport.json),
[серверный install receipt](evidence/liq_research_delivery_20261017/installation.json).

## Money Lane: конкретная дельта

**Dynamic59 постоянный source — фактический PASS.** Новый40-file DATA-only kit
и timer уже на сервере. Bootstrap собрал все59 инструментов, проверил полные200
сессий каждого по broker calendar; closed source16 октября →opening19 октября.
Отдельная повторная сборка из сохранённых raw CSV/calendar без новых source GET
дала идентичный source_id:
`aa97a0132440068a1a9f0928bc989dcda8a6b56b66605c63202a1b9134843b94`.
Spec `668fa945f225e688d32d353dfa16b1c30eae5edcceff850b820f5d4cd2ff07ef`.

Повторно использованы прежние frozen fetch/aggregation и полная200-session QA.
Общие примитивы выделены без изменения default Monthly58 поведения. На VPS
старые Monthly37/V3 и текущий NET не обновлялись. Новый Dynamic59 имеет отдельные
schema, каталог, source-only book/receipts и расписание **13:30/16:30 New York**
для сокращённых/обычных закрытий. Поздние/неполные данные блокируются; ranking,
портфельные решения, покупка, сопровождение или финансовый transport не запускаются.

225 исходных protected/source pins, KITY/ATT1/LIQ PIDs и crontab сохранены.
[Actual source install](evidence/liq_research_delivery_20261017/dynamic-source-installation.json),
[отдельный raw-source rebuild](evidence/liq_research_delivery_20261017/dynamic-source-readback.json).
Экономическое сравнение фиксированных Dynamic/Weekly/Monthly, полный lifecycle
ORDERS_OFF с ownership и денежный single-owner binding ещё **OPEN**.

**KITY:** выполнен ровно один новый PUBLIC-only pre-money capture20 GET,
без credentials/financial controls/policy или новой попытки. На18:23:36UTC
неизменная математика требует **247.189680USDT**, cap215, excess32.189680;
BTW price2.55570/minQty10. **CAPACITY_BLOCKED** подтверждён уже новым снимком,
не только старым229.584550. Это capacity-only, не account/CTS SEND readiness.
Инертный packet вновь `CAPACITY_BLOCKED_NO_GO_PACKET`; новый financial GO не
создан, старая one-shot policy SPENT и не переиспользуется.
[Свежий расчёт10legs](evidence/liq_research_delivery_20261017/kity_fresh_capacity.json),
[инертный packet](evidence/liq_research_delivery_20261017/kity_fresh_inert_packet.json).

## Board: готово / заблокировано / следующий реальный gate

| Направление | Готово | Открыто / следующий gate |
|---|---|---|
|Alpaca Dynamic P0|Event-reselection ORDERS_OFF кандидат; actual59 continuous source и200-session rebuild PASS|Сопоставимая fixed-rule проверка результата, authenticated slot/cash/NET ownership, полный stop/ratchet/exit/reselection lifecycle и один конкретный financial packet; затем отдельный OWNER GO.19Oct16:30Кипр остаётся условным техническим окном|
|Alpaca Monthly P0|Принятый strategy parity, независимые58source/schedule и disabled V3 сохранены|Monetary binding/packet; отдельный owner activation.30Oct source→2Nov16:30Кипр, не замена Dynamic|
|KITY P0|Причина/регрессии/предденежная проверка; свежий capacity-only capture|247.189680>215, новая попытка не разрешена. Следующий packet только после fresh feasibility PASS; cap/правила не менять|
|NET P0|Работающие прежний manager и GET-only DAY monitor сохранены|19Oct13:30UTC реальное восстановление полной DAY-защиты; отдельная read-only проверка16:35Кипр. Суббота не доказывает Monday protection|
|LIQ P1|Daily export active, actual snapshot+25 metadata+fee доставлены, repeat import PASS|Claude consumer gap handling/source QA; действующие warmup/BASE/breadth gates, не подсчёт raw rows как событий|
|IBIT P1|Существующий DATA-only collector/timer и81-session historical seed сохранены|19Oct первый prospective cycle и передача реальных decision/QA в отдельный Claude journal; Massive QA PENDING, historical≠prospective|

`19-net-ibit` — два разовых read-only контроля19 октября:16:35 и23:35 Кипр.
Вечерняя проверка читает только завершённые actual source/decision/QA, проверяет
полные hashes/время/session и доставляет create-exclusive records в отдельный
`research_lab/data/ibit_adapter_v1/` без изменения ten/outcomes Claude.
При отсутствующих/неподтверждённых данных — BLOCKED/UNKNOWN; после вечерней
проверки heartbeat останавливается независимо от verdict. Пропущенное окно
не выдаётся за своевременный PASS. Массовая сверка без источника остаётся PENDING.

## Проверки и ограничения

65 focused LIQ tests PASS. Dynamic/Monthly source + reselection/native53 PASS,
дополнительный saved-source CLI1 PASS; compile/diff checks PASS. Тесты источника
и raw-source rebuild не являются доказательством экономического преимущества.
Полный suite не перезапускался; предыдущие5474PASS/60FAIL остаются историческим
NOT_GREEN. Финальный review root-only; новая независимая финансовая/исследовательская
приёмка не заявляется. [Точные команды/hashes](evidence/liq_research_delivery_20261017/verification.json).

Foreign allowlist сохранён и не закоммичен. Приватные credentials/raw account
fee response/SSH material не публикуются. Новых брокерских ордеров, финансовых
unit/config/HALT/risk изменений, judge/outcome runs, сообщений Claude нет.
