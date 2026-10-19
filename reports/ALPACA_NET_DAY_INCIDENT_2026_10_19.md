# NET DAY: причина тревоги и восстановление, 19 октября

**Исправлен наблюдатель; действующая защита и NET lifecycle не менялись.**
Штатный сервис в17:04:17UTC /20:04:17Asia/Nicosia получил
`DAY_PROTECTION_CONFIRMED`. Telegram подтвердил доставку `RECOVERED`, HTTP200,
message15236. [Receipt](evidence/net_day_incident_20261019/receipt.json).

## Что произошло

Тревога `a24fe646…10a489` возникла в13:30:00.657UTC. `collect()` до первого
broker GET проверял95 source pins и получал `FileNotFoundError` для
`alpaca_bridge_0d0c322aef55c952.paper-kill/.paper-entry-halt.json`.
Остальные94 pins совпадали. UNKNOWN был корректным результатом отказа захвата,
но он не доказывал отсутствие нативного стопа у брокера.

Несмотря на PAPER в пути, это **LIVE entry HALT из binding**, а не ненужный
исторический файл. Личная owner-arm команда18Oct штатно переместила его в архив;
текущий архив имеет исходный SHA `f650419b…50c115`. При отмене SHOP arm/claims и
архив не сбрасывались. Ошибка интеграции: изменяемый entry guard оказался в списке
неизменяемых источников наблюдения за уже существующей NET. Возвращать HALT ради
наблюдателя или ослаблять финансовые entry guards не требовалось.

## Фактический broker readback

Первый текущий независимый GET выполнен в16:56:42UTC. Наблюдение13:35UTC
**пропущено**, оно не становится своевременным PASS задним числом.
Брокер сообщает создание сегодняшнего стопа в13:30:04.264290453UTC; непрерывную
полноту защиты между всеми моментами по этим снимкам утверждать нельзя.

Снимок штатного восстановленного сервиса17:04UTC:

| Факт | Значение |
|---|---|
| NET remaining / covered qty |0.325167779 /0.325167779 |
| Исходная entry price |$311.222 |
| Текущая snapshot price |$299.62 |
| Unrealized от покупки |−$3.772597 |
| Unrealized intraday |+$1.079557 |
| Native sell STOP |$277.69, `new`, DAY, filled0 |
| Stop ID |62edc8cd-abef-4525-8073-f06b32a0fdfd |
| Expiry |19Oct20:00UTC /23:00Asia/Nicosia |
| Сохранённый HWM |$315.505, ниже trigger |
| Trigger существующего ratchet |entry+3.5%, около$322.11477 |

Это обычный native STOP под существующим программным ratchet, не брокерский
`trailing_stop`. Установленный runtime и его overlay используют activate3.5%,
trail3.5%, minimum lock0.5%, minimum raise10bps. Условие активации ещё не достигнуто
по сохранённому HWM. Зелёный дневной результат не означает прибыль от покупки;
текущий stop не фиксирует прибыль. Legacy NET не принята в новый Monthly book.

## Исправление и его граница

После конкретного предложения владелец явно разрешил **только наблюдатель**.
Новый конфиг отличается удалением ровно одного entry-HALT pin. Сохранены94 других
pins, четыре observer code pins, binding, scope, output/state и все запреты.
Единственное изменение service — `--spec` и `--spec-sha256`. Timer не менялся.
Исходные spec/service сохранены; журнал, claims, архив HALT и lock813893 сохранены.
Ни финансовый manager, ни ордера, ни торговые полномочия не изменялись.

- New spec SHA: `d6abec21a8debe9d33e44134cbce354fad394e5fce4068797a8694b0cb64b5ba`.
- New observer service SHA: `dc59842b320e144fdbf8530178bfe763991fd7f32198303485673f83ad5479db`.
- Old service SHA: `08e66161d72d3ee5b3cd354f2ac4aef492d44b78e5636b81f8459d058471ae47`.
- New config: `/opt/bybot-research/alpaca-net-day-monitor-20261017/day-monitor-spec-net-only-v2.json`.
- Rollback copy: `/opt/bybot-research/alpaca-net-day-monitor-20261017/day-monitor-service-before-20261019-repair.service`.

Возврат старого service снова вызовет известный отказ pin; это технический rollback,
не исправление финансового состояния. Старые private preservation scripts с pin
старого observer unit теперь исторические: не восстанавливать старый hash поверх
этого owner-authorized изменения. Actual financial pins остаются обязательными.

SHOP timer disabled/inactive, entry service ни разу не запускался, новой позиции
или открытого ордера SHOP нет. Отмена владельцем сохранена; это не execution FAIL.

### Зависимость отменённого SHOP и второе узкое разрешение

В следующем штатном цикле17:05 первый NET child вернул `LIVE_PROTECTED/0`, однако
второй, пустой SHOP companion — `NEXT_SELECTED_UNIT_DRIFT/2`: frozen next-entry
spec ожидает старый observer unit hash. Итог общей обёртки стал exit2. Это реальная
неучтённая зависимость первого исправления, а не отсутствие защиты NET; результат
после установки проверен и не скрыт за успешным observer receipt.

Вместо переписывания финансового spec/arm владелец **отдельно разрешил** удалить
только вызов сопровождения отменённого SHOP из `manager-wrapper.py`. Fresh GET-only
проверка подтвердила отсутствие его intake/binding/compatibility GO, timer disabled,
service never ran. Patch меняет одну строку commands: NET command и остальной AST
дословно сохранены. Hash `0403e2b9…a8688` → `8bce21a9…c6846`. Атомарная установка
с recoverable backup выполнена17:13UTC, mode/owner сохранены, шесть units, specs,
observer config и lock сохранены. Сам financial manager агентом не запускался.
Первый следующий **существующий** timer17:15UTC прошёл: ровно один NET child
`LIVE_PROTECTED/0`, общий service exit0. Отдельный штатный observer17:15:02UTC
подтвердил full native STOP. Snapshot price$300.93, unrealized−$3.346627,
intraday+$1.505527; qty/stop неизменны. Агент manager не запускал.

Этот шаг удаляет только вызов: старый `control-spec-pin.json` и каталог наблюдений
по-прежнему нужны обёртке и не должны очищаться. Отменённый next-entry spec также
сохраняет старый wrapper pin: он не перепривязан и не получил новую authority;
самостоятельный старый preflight после retirement может fail-closed. Новая
активация SHOP запрещена. Backup:
`/opt/bybot-research/alpaca-next-entry-20261019-v1/owner-packet/manager-wrapper-before-shop-retirement-20261019.py`.

Process correction: перед последующими operator changes учитывать не только
read-only source pins, но и `selected_unit_pins` смежных wrappers. Это узкий
dependency check, не повод начинать новый архитектурный аудит.

## Проверки и дальнейшая работа

Точный установленный collector сначала воспроизвёл отказ с0GET, затем конфиг в
памяти прошёл7GET. `GetReader`, `collect`, `pin_files` совпали по AST с проверенным
кодом; различие остальных частей локального модуля не скрыто. Затем отдельно
подтверждён свежий результат **реального установленного сервиса**, не replay.
48 targeted tests PASS: архивированный HALT, новый HALT, отсутствие его мутации,
сохранение binding-pin fail-closed, DAY evaluator и существующие monitor cases.
Независимый astra/high review выявил два Important; оба закрыты проверяемыми
provenance/AST фактами. Второй независимый signoff не заявляется.

Полный точный пакет после четырёх новых regressions: **239PASS/38imports/0fallback**,
network denied, production material1f02fc49 не менялся. Первый повтор остановился
на test timeout120s в существующей двухцикловой frozen58 fixture; этот лог сохранён,
старый XML не назван новым результатом. Полный повтор с явно указанным **тестовым**
budget300s прошёл за384.54s; та fixture заняла128.236s. Production timeouts/gates
не менялись.48 targeted пересекаются с239, их не складывать. Для нового wrapper
отдельно3fixture checks: protected/blocked/lost-response, ни одного реального
subprocess/broker request. Независимый review нового wrapper slice: Critical0,
Important1 — сохранить старые pin/config/output dependencies; они сохранены.
[Verification](evidence/net_day_incident_20261019/verification.json).

IBIT19Oct23:35Asia/Nicosia остаётся отдельным будущим DATA_ONLY событием;
Massive PENDING. Heartbeat остаётся активным до вечернего контроля и должен быть
приостановлен после него согласно исходной инструкции. Этот repair не меняет
KITY SPENT/ORDERS_OFF или любые crypto research gates.

Следующий Money P0 — минимальная поправка Monthly admission после фактических
измерений, затем один production runner / server ORDERS_OFF handoff и rollback.
См. [измерения и точные guards](evidence/net_day_incident_20261019/monthly-minimal-measurements.json).

## Короткая status delta для Claude

NET: observer incident CLOSED/fresh17:15PROTECTED;13:35window MISSED. SHOP: owner
cancel preserved, empty companion retired by separate owner permission. Monthly:
cost component6ab5d4b published,239exactPASS; actualcash/BP394.91/1x measured,
minimalfee admission CR next; .02illustration is not futurebound/reserveGO.
IBIT: tonight23:35Cyprus stillPENDING/MassivePENDING. No research verdict or
financial authority changes, no message to Claude was sent.

## Intake предложения раннего трейлинга19Oct

Read-only source check: опубликованный research origin`d914fd2`, H4 correction
`60530b9`/blob`68181b0` подтверждены. H4 исследовал отключение трейла/стопов и ATR
трейл; проверенные варианты FAIL, последующая настройка на2016–2026 FROZEN.
Ранние1.5/2/2.5 этим экспериментом не проверялись. Предложение принято в backlog
канонического roadmap после Monthly, без новой приоритетной ветки исследований.

Pure-code diagnostic существующего ratchet на **сохранённом17:15UTC** capture:

| Activation | Trail / min lock | Trigger price | Действие по сохранённому HWM315.505 |
|---|---|---|---|
|3.5%|3.5% /0.5%|322.114770|hold / trail_not_armed |
|1.5%|3.5% /0.5%|315.890330|hold / trail_not_armed |
|2.0%|3.5% /0.5%|317.446440|hold / trail_not_armed |
|2.5%|3.5% /0.5%|319.002550|hold / trail_not_armed |

Это четыре воспроизводимые проверки текущей функции, **не сравнение доходности**.
Новые котировки/исторические пути не получались, broker/runtime не менялись;
сохранённый manager HWM не доказывает полный непрерывный рыночный high.
[Receipt](evidence/net_trailing_intake_20261019/receipt.json).
Legacy quote-HWM/5min и Monthly completed-close/next-session должны проверяться
раздельно. Вариант activation2/trail2.5 меняет два параметра и требует отдельной
гипотезы. Нужны prereg и действительно новые/forward данные; intraday PnL, MaxDD,
premature exits и missed continuation пока UNKNOWN. Остальные параметры и правила
освобождённого капитала фиксировать, сопоставлять полный портфель с baseline.
